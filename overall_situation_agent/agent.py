from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .aggregations import run_overall_aggregations
from .evidence import fetch_tertiary_evidence_for_labels, fetch_tertiary_top_evidence
from .config import Settings
from .es_client import (
    SimpleElasticsearch,
    create_es_client,
    ensure_index,
)
from .import_state import build_import_state, build_import_manifest, load_import_state, save_import_state
from .importer import import_excel_to_es
from .llm_client import OpenAICompatibleClient
from .logging_setup import setup_logging
from .markdown_renderer import render_markdown_report
from .narrative_builder import build_report_narratives
from .output_naming import make_report_path
from .report import render_html_report
from .schedule_loader import enrich_result_with_schedule, load_schedule_context
from .taxonomy import collect_md_tertiary_items

logger = logging.getLogger(__name__)


@dataclass
class ImportResult:
    message: str
    success: bool = True


def _collect_primary_top_tertiary_labels(
    result: dict[str, Any],
    top_primary: int = 5,
    top_tertiary_per_primary: int = 5,
) -> list[str]:
    md_items = collect_md_tertiary_items(result, top_primary=top_primary, top_tertiary_per_primary=top_tertiary_per_primary)
    labels: list[str] = []
    seen: set[str] = set()
    for item in md_items:
        label = str(item.get("source_key", "")).strip()
        if label and label not in seen:
            seen.add(label)
            labels.append(label)
    return labels


def _annotate_md_evidence(evidence: dict[str, Any], md_items: list[dict[str, Any]]) -> dict[str, Any]:
    item_by_source = {str(item.get("source_key", "")).strip(): item for item in md_items}
    for label_data in evidence.get("labels", []):
        source_key = str(label_data.get("key", "")).strip()
        item = item_by_source.get(source_key)
        if not item:
            continue
        label_data["source_key"] = source_key
        label_data["key"] = item["key"]
        label_data["canonical_key"] = item["key"]
        label_data["primary_key"] = item["primary_key"]
        label_data["primary_count"] = item["primary_count"]
        label_data["count"] = item["count"]
        label_data["share"] = (int(item["count"]) / int(item["primary_count"])) if int(item["primary_count"]) else 0
    return evidence


class OverallSituationAgent:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.es: SimpleElasticsearch = create_es_client(settings)
        self.llm = OpenAICompatibleClient(settings)
        setup_logging(settings.logs_dir)

    def import_data(self, input_path: Path, recreate_index: bool = False) -> ImportResult:
        ensure_index(self.es, self.settings.es_index, recreate=recreate_index)
        if recreate_index:
            self.settings.import_state_file.unlink(missing_ok=True)

        if input_path.is_dir():
            files = sorted(
                p for p in input_path.iterdir()
                if p.suffix.lower() in {".xlsx", ".xlsm"} and not p.name.startswith("~$")
            )
            if not files:
                return ImportResult(f"未在目录中找到 .xlsx/.xlsm 文件：{input_path}", success=False)
            import_state = load_import_state(self.settings.import_state_file)
            if (not recreate_index) and import_state and hasattr(import_state, "matches_files") and import_state.matches_files(files, self.settings.es_index):
                return ImportResult(f"该批次文件已导入（{input_path}），跳过。如需重新导入请加 --recreate-index。")
            total = 0
            states = []
            for file in files:
                count = import_excel_to_es(self.es, self.settings.es_index, file, batch_size=self.settings.import_batch_size)
                total += count
                states.append(build_import_state(file, self.settings.es_index, count))
            state = build_import_manifest(input_path, self.settings.es_index, states)
            save_import_state(self.settings.import_state_file, state)
            return ImportResult(f"批量导入完成，共 {total} 条记录。")
        else:
            if not input_path.exists():
                return ImportResult(f"文件不存在：{input_path}", success=False)
            import_state = load_import_state(self.settings.import_state_file)
            if (not recreate_index) and import_state and hasattr(import_state, "matches") and import_state.matches(input_path, self.settings.es_index):
                return ImportResult(f"该文件已导入，跳过。如需重新导入请加 --recreate-index。")
            count = import_excel_to_es(self.es, self.settings.es_index, input_path, batch_size=self.settings.import_batch_size)
            state = build_import_state(input_path, self.settings.es_index, count)
            save_import_state(self.settings.import_state_file, state)
            return ImportResult(f"导入完成：{input_path.name}，共 {count} 条记录。")

    def generate_report(
        self,
        output_path: Path | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        schedule_input: Path | None = None,
    ) -> Path:
        self.settings.outputs_dir.mkdir(parents=True, exist_ok=True)

        if output_path is None:
            output_path = make_report_path(self.settings.outputs_dir)

        logger.info("Running aggregations...")
        result = run_overall_aggregations(self.es, self.settings.es_index, start_date, end_date)

        schedule_context = load_schedule_context(schedule_input)
        result = enrich_result_with_schedule(result, schedule_context)

        logger.info("Fetching tertiary TOP evidence...")
        all_tertiary_total = sum(item.get("count", 0) for item in result.get("tertiary", []))
        evidence = fetch_tertiary_top_evidence(
            self.es, self.settings.es_index,
            total_hits=result.get("total", 0),
            start_date=start_date, end_date=end_date,
            all_tertiary_total=all_tertiary_total,
        )
        result["tertiary_evidence"] = evidence

        md_items = collect_md_tertiary_items(result, top_primary=5, top_tertiary_per_primary=5)
        result["md_tertiary_items"] = md_items
        md_labels = [str(item.get("source_key", "")).strip() for item in md_items if str(item.get("source_key", "")).strip()]
        if md_labels:
            result["tertiary_evidence_md"] = _annotate_md_evidence(fetch_tertiary_evidence_for_labels(
                self.es,
                self.settings.es_index,
                total_hits=result.get("total", 0),
                labels=md_labels,
                start_date=start_date,
                end_date=end_date,
                all_tertiary_total=all_tertiary_total,
            ), md_items)
        else:
            result["tertiary_evidence_md"] = {"labels": [], "sampling": {"per_label": 0, "total_hits": result.get("total", 0)}}

        logger.info("Building narratives...")
        narratives = build_report_narratives(result, self.llm)
        result["narratives"] = narratives

        logger.info("Rendering HTML report...")
        html_path = render_html_report(result, output_path)

        md_path = output_path.with_suffix(".md")
        logger.info("Rendering Markdown report...")
        render_markdown_report(result, md_path)

        logger.info(f"Report generated: {html_path}")
        return html_path

    def run(
        self,
        input_path: Path,
        output_path: Path | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        recreate_index: bool = False,
        schedule_input: Path | None = None,
    ) -> Path:
        result = self.import_data(input_path, recreate_index=recreate_index)
        print(result.message)
        return self.generate_report(
            output_path=output_path,
            start_date=start_date,
            end_date=end_date,
            schedule_input=schedule_input,
        )
