from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReportContext:
    query: dict[str, Any]
    section_focus: str
    trend_view: dict[str, Any]
    narratives: dict[str, Any]
    labeled_total: int
    total: int
    period_start: str
    period_end: str


def _display_date(value: Any, fallback: str = "未限定") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    return text[:10] if len(text) > 10 else text


def build_report_context(result: dict[str, Any], trend_view: dict[str, Any]) -> ReportContext:
    query = result.get("query") or {}
    filters = result.get("filters") or {}
    period = result.get("period") or {}
    labeled_total = int(result.get("total", 0) or 0)
    total = int(result.get("total_with_unlabeled", labeled_total) or 0)
    return ReportContext(
        query=query,
        section_focus=str(query.get("section_focus") or "full"),
        trend_view=trend_view,
        narratives=result.get("narratives") or {},
        labeled_total=labeled_total,
        total=total,
        period_start=_display_date(period.get("min") or filters.get("start_date")),
        period_end=_display_date(period.get("max") or filters.get("end_date")),
    )
