from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .report import (
    _analysis_type_text,
    _build_trend_view,
    _distribution_insights,
    _event_label,
    _matchday,
    _matchday_note,
    _matchday_summary,
    _narrative_line_at,
    _natural_sample_summary,
    _pct,
    _query_note_text,
    _safe_ratio,
    _selected_daily_rows,
    _source_files_text,
    _sorted_anomaly_days,
    _strip_emoji,
    _sum_counts,
    _trend_chart_summary,
    _trend_insights,
    _trend_voice_items,
    _trend_voice_summary,
    _unlabeled_dist_lines,
    _unlabeled_trend_lines,
)
from .report_context import build_report_context
from .sanitization import mask_sensitive_text, sanitize_report_payload
from .taxonomy import CANONICAL_PRIMARY_TERTIARY, canonical_tertiary_label, primary_top_tertiary_items


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _md(value: Any) -> str:
    text = _text(value)
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\r\n", "\n").replace("\n", "<br>")


def _n(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return _text(value)


def _truncate(value: Any, limit: int = 160) -> str:
    text = _text(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def _paragraphs(lines: list[str] | None, fallback: list[str] | None = None) -> str:
    selected = [line.strip() for line in (lines or fallback or []) if str(line).strip()]
    if not selected:
        return "暂无可生成的分析内容。"
    return "\n\n".join(_text(line) for line in selected)


def _unlabeled_md_block(lines: list[str], title: str = "未标注一二三级标签服务数据分析") -> str:
    if not lines:
        return ""
    body = "\n\n".join(_text(line) for line in lines)
    return f"#### {title}\n\n{body}"


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "暂无可展示数据。"
    header = "| " + " | ".join(_md(item) for item in headers) + " |"
    divider = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_md(value) for value in row) + " |" for row in rows]
    return "\n".join([header, divider, *body])


def _chart_note(original: str, markdown_view: str = "数据表") -> str:
    return f"<small>原图：{original}；Markdown 展示：{markdown_view}。</small>"


def _sanitize_report_terms(text: str) -> str:
    return mask_sensitive_text((text or "").replace("反馈/投诉", "投诉").replace("反馈", "投诉"))


def _rank_table(items: list[dict], total: int, label_name: str, limit: int = 10) -> str:
    rows = []
    for idx, item in enumerate([entry for entry in items if entry.get("count", 0) > 0][:limit], start=1):
        count = int(item.get("count", 0))
        rows.append([idx, item.get("key", "未标注"), _n(count), _pct(_safe_ratio(count, total))])
    return _table(["排名", label_name, "提及量", "占比"], rows)


def _tag_counts(items: list[dict], limit: int = 5, total: int | None = None) -> str:
    visible = [item for item in items if item.get("count", 0) > 0][:limit]
    if not visible:
        return "无"
    denominator = total if total is not None else _sum_counts(items)
    parts = []
    for item in visible:
        count = int(item.get("count", 0))
        pct = f"{count / denominator * 100:.1f}%" if denominator > 0 else "0.0%"
        parts.append(f"{item.get('key', '未标注')}（共{_n(count)}条，占比{pct}）")
    return "、".join(parts)


def _key_text(items: list[Any], limit: int = 3) -> str:
    keys = []
    for item in (items or [])[:limit]:
        value = item.get("key") if isinstance(item, dict) else item
        text = str(value or "").strip()
        if text:
            keys.append(text)
    return "、".join(keys) or "无"


def _duration_text(value: Any) -> str:
    if isinstance(value, (int, float)) and not math.isnan(float(value)):
        return f"{float(value):.1f} 分钟"
    return "未覆盖"


def _maybe_tag_row(label: str, items: list[dict], limit: int = 5, total: int | None = None) -> list[Any] | None:
    if not any(item.get("count", 0) > 0 for item in items):
        return None
    return [label, _tag_counts(items, limit=limit, total=total)]


def _compact_rows(rows: list[list[Any] | None]) -> list[list[Any]]:
    return [row for row in rows if row]


def _optional_table(title: str, headers: list[str], rows: list[list[Any] | None]) -> str:
    compacted = _compact_rows(rows)
    if not compacted:
        return ""
    return f"**{title}**\n\n{_table(headers, compacted)}"


def _drilldown_markdown(items: list[dict], total: int) -> str:
    if not items:
        return "暂无可展示的标签下钻关系。"

    lines: list[str] = []
    for primary in items:
        primary_count = int(primary.get("count", 0))
        if primary_count <= 0:
            continue
        lines.append(
            f"**一级标签：{_text(primary.get('key', '未标注'))}"
            f"（{_n(primary_count)} 次，占比 {_pct(_safe_ratio(primary_count, total))}）**"
        )
        secondaries = [item for item in primary.get("secondary", []) if item.get("count", 0) > 0]
        if not secondaries:
            lines.append("  - 二级标签：无")
            lines.append("")
            continue

        for secondary in secondaries:
            secondary_count = int(secondary.get("count", 0))
            lines.append(
                f"  - 二级标签：{_text(secondary.get('key', '未标注'))}"
                f"（{_n(secondary_count)} 次，占一级 {_pct(_safe_ratio(secondary_count, primary_count))}）"
            )
            tertiaries = [item for item in secondary.get("tertiary", []) if item.get("count", 0) > 0]
            if not tertiaries:
                lines.append("    - 三级标签：无")
                continue
            for tertiary in tertiaries:
                tertiary_count = int(tertiary.get("count", 0))
                lines.append(
                    f"    - 三级标签：{_text(tertiary.get('key', '未标注'))}"
                    f"（{_n(tertiary_count)} 次，占二级 {_pct(_safe_ratio(tertiary_count, secondary_count))}）"
                )
        lines.append("")
    return "\n".join(lines).strip() or "暂无可展示的标签下钻关系。"


def _cause_table(items: list[dict]) -> str:
    rows = []
    for item in [entry for entry in items if entry.get("count", 0) > 0][:10]:
        samples = []
        for sample in item.get("samples", [])[:2]:
            excerpt = _truncate(sample.get("content_excerpt"), 120)
            if excerpt:
                samples.append(excerpt)
        rows.append(
            [
                item.get("key", "未标注"),
                _n(item.get("count", 0)),
                _tag_counts(item.get("top_appeals", []), limit=3),
                "<br>".join(samples) if samples else "无",
            ]
        )
    return _table(["三级问题", "提及量", "高频诉求", "样例摘要"], rows)


def _operation_need_table(items: list[dict]) -> str:
    rows = []
    for item in [entry for entry in items if entry.get("count", 0) > 0][:8]:
        sample = next(
            (
                _truncate(sample.get("content_excerpt"), 120)
                for sample in item.get("samples", [])[:1]
                if _text(sample.get("content_excerpt"))
            ),
            "无",
        )
        rows.append(
            [
                item.get("key", "未标注"),
                _n(item.get("count", 0)),
                _tag_counts(item.get("top_latent_needs", []), limit=2),
                _tag_counts(item.get("top_member_clusters", []), limit=2),
                _tag_counts(item.get("top_tertiary", []), limit=2),
                sample,
            ]
        )
    return _table(["运营举措", "提及量", "隐性需求", "会员类型", "相关问题", "代表样例"], rows)


def _latent_need_table(items: list[dict]) -> str:
    rows = []
    for item in [entry for entry in items if entry.get("count", 0) > 0][:8]:
        rows.append(
            [
                item.get("key", "未标注"),
                _n(item.get("count", 0)),
                _tag_counts(item.get("top_operations", []), limit=2),
                _tag_counts(item.get("top_members", []), limit=2),
            ]
        )
    return _table(["隐性需求", "提及量", "关联运营举措", "关联会员类型"], rows)


def _member_cluster_table(items: list[dict]) -> str:
    rows = []
    for item in [entry for entry in items if entry.get("count", 0) > 0][:10]:
        rows.append(
            [
                item.get("key", "未标注"),
                _n(item.get("count", 0)),
                _tag_counts(item.get("top_tertiary", []), limit=3),
                _tag_counts(item.get("top_appeals", []), limit=2),
            ]
        )
    return _table(["会员/业务类型", "提及量", "高频问题", "高频诉求"], rows)


def _case_markdown(result: dict) -> str:
    rows = []
    for item in result.get("top_tertiary_examples", [])[:3]:
        for sample in item.get("samples", [])[:1]:
            rows.append(
                [
                    item.get("key", "未标注"),
                    _n(item.get("count", 0)),
                    sample.get("appeal") or "无",
                    _truncate(sample.get("content_excerpt"), 120),
                ]
            )
    return _table(["三级问题", "关联量", "客户诉求", "样例摘要"], rows[:4])


def _merged_cause_voice_markdown(result: dict, narratives: dict[str, list[str]] | None = None) -> str:
    examples = result.get("top_tertiary_examples", [])
    if not examples:
        return ""
    narratives = narratives or {}
    summary_lines = narratives.get("cause_voice_sample_summaries") or []
    rows = []
    for idx, item in enumerate(examples):
        count = int(item.get("count", 0))
        appeal_text = _key_text(item.get("top_appeals", []), 3)
        sample = item.get("samples", [{}])[0] if item.get("samples") else {}
        summary_text = _narrative_line_at(summary_lines, idx) or _natural_sample_summary(
            sample.get("content_excerpt", ""),
            _text(item.get("key") or ""),
        )
        rows.append([item.get("key", "未标注"), f"{_n(count)}条", appeal_text, summary_text])
    return _table(["三级问题", "提及量", "高频诉求", "样例摘要"], rows)


def _matchday_text(day: dict) -> str:
    summary = _matchday_summary(day)
    event = _event_label(day)
    if _matchday(day):
        return f"**[赛事日]** {summary}".strip()
    if event:
        return f"非赛事日；补充线索：{event}"
    return "非赛事日"


def _daily_table(days: list[dict]) -> str:
    rows = []
    for day in days:
        growth = day.get("day_over_day_growth")
        rows.append(
            [
                day.get("date"),
                _n(day.get("count", 0)),
                "首日" if growth is None else _pct(float(growth)),
                _n(day.get("negative_count", 0)),
                _pct(float(day.get("negative_ratio", 0))),
                _matchday_text(day),
                _tag_counts(day.get("top_tertiary", []), limit=3),
            ]
        )
    return _table(["日期", "问题量", "日环比", "负向情绪量", "负向占比", "赛事日", "主要三级问题"], rows)


def _anomaly_table(anomalies: list[dict]) -> str:
    if not anomalies:
        return "当前周期未识别到日环比超过 50% 且当日问题量不少于 5 件的明显异动。"
    rows = []
    for day in _sorted_anomaly_days(anomalies)[:3]:
        day_total = int(day.get("count", 0) or 0)
        rows.append(
            [
                day.get("date"),
                _pct(float(day.get("day_over_day_growth", 0))),
                _pct(float(day.get("negative_ratio", 0))),
                _matchday_text(day),
                _tag_counts(day.get("top_primary", []), limit=2, total=day_total),
                _tag_counts(day.get("top_secondary", []), limit=2, total=day_total),
                _tag_counts(day.get("top_tertiary", []), limit=3, total=day_total),
                f"服务类型：{_tag_counts(day.get('top_service_type', []), limit=2, total=day_total)}；涉及业务/会员类型：{_tag_counts(day.get('top_member_cluster', []), limit=2, total=day_total)}",
            ]
        )
    method = (
        "以上日期基于日聚合口径，日环比增长 ≥ 50% 且当日问题量 ≥ 5 件被识别为异动。"
        "按日环比降序排列，以下列出排名前三的异动节点。"
        "表内所有标签和业务维度占比均以该日问题量为分母；多标签字段可重复，合计可能超过 100%。"
    )
    table = _table(["日期", "日环比", "负向占比", "赛事日", "主要一级问题", "主要二级问题", "主要三级问题", "业务维度热点"], rows)
    return f"{method}\n\n{table}"


def _simple_distribution_table(title: str, items: list[dict], original_chart: str, limit: int = 10) -> str:
    total = _sum_counts(items)
    rows = []
    for idx, item in enumerate([entry for entry in items if entry.get("count", 0) > 0][:limit], start=1):
        count = int(item.get("count", 0))
        rows.append([idx, item.get("key", "未标注"), _n(count), _pct(_safe_ratio(count, total))])
    return f"#### {title}\n\n{_chart_note(original_chart)}\n\n{_table(['排名', '类型', '提及量', '占比'], rows)}"


def _daily_detail_table(trend_view: dict) -> str:
    """Render daily data table for chart reconstruction."""
    days = trend_view.get("days", [])
    anomalies = trend_view.get("anomalies", [])
    if not days:
        return "暂无可展示的每日明细数据。"
    anomaly_dates = {a["date"] for a in anomalies if a.get("date")}
    headers = ["日期", "问题量", "负向占比", "赛事日", "主要三级问题"]
    rows = []
    for day in days:
        date_str = str(day.get("date", ""))
        count = _n(day.get("count", 0))
        neg = _pct(day.get("negative_ratio", 0))
        is_match = "是" if _matchday(day) else "否"
        if date_str in anomaly_dates:
            is_match += " \u26a1\u5f02\u52a8"
        top_tert = "\u3001".join(
            t.get("key", "") for t in (day.get("top_tertiary") or [])[:3]
        ) or "\u2014"
        rows.append([date_str, count, neg, is_match, top_tert])
    return _table(headers, rows)


def _trend_voice_markdown(trend_view: dict[str, Any], narratives: dict[str, list[str]]) -> str:
    items = _trend_voice_items(trend_view)
    summary = narratives.get("trend_voice_summary") or _trend_voice_summary(items)
    summary_lines = narratives.get("trend_voice_sample_summaries") or []
    blocks = [_paragraphs(summary)]
    for idx, item in enumerate(items):
        samples = item.get("samples", [])
        sample_summaries = []
        for sample in samples[:2]:
            text = sample.get("content_excerpt", "")
            if text:
                sample_summaries.append(_natural_sample_summary(text, _key_text(item.get("top_tertiary", []), 1)))
        sample_text = _narrative_line_at(summary_lines, idx) or "；".join(sample_summaries) or "暂无样例。"
        blocks.append(
            "\n".join(
                [
                    f"**{_text(item.get('date'))} 赛事日样例**",
                    f"- 问题量：{_n(item.get('count', 0))} 件",
                    f"- 负向占比：{_pct(float(item.get('negative_ratio', 0)))}",
                    f"- 赛事摘要：{_text(item.get('match_summary') or '赛事日')}",
                    f"- 主要问题：{_tag_counts(item.get('top_tertiary', []), limit=3, total=int(item.get('count', 0) or 0))}",
                    f"- 样例摘要：{sample_text}",
                ]
            )
        )
    return "\n\n".join(blocks)



def _tertiary_cause_detail_md(details) -> str:
    if not details:
        return ""
    headers = ["排名", "三级问题", "提及量/占比",
               "服务内容总结", "客服回复总结",
               "客户关键诉求", "诉求关键词",
               "客服处理动作", "客服关键词", "根因判断"]
    rows = []
    for idx, item in enumerate(details):
        label = str(item.get("label", ""))
        count = _n(item.get("count", 0))
        share = _text(item.get("share", ""))
        rows.append([
            "TOP" + str(idx + 1),
            label,
            count + " / " + share,
            _text(item.get("content_summary", "")),
            _text(item.get("cs_reply_summary", "")),
            _text(item.get("customer_appeal_summary", "")),
            _text(item.get("customer_keywords_summary", "")),
            _text(item.get("cs_action_summary", "")),
            _text(item.get("cs_keywords_summary", "")),
            _text(item.get("root_cause", "")),
        ])
    return _table(headers, rows)



def _province_analysis_md(province_data: list, narratives: dict) -> str:
    if not province_data:
        return ""

    blocks: list[str] = []
    blocks.append("#### 省份投诉分布与区域特征")

    # LLM narrative
    narrative = _paragraphs(narratives.get("province_analysis") or [])
    if narrative:
        blocks.append(narrative)

    # Province distribution table
    blocks.append(_chart_note("省份投诉分布条形图"))
    total = _sum_counts(province_data)
    rows = []
    for idx, item in enumerate([p for p in province_data if p.get("count", 0) > 0][:10], start=1):
        count = int(item.get("count", 0))
        rows.append([idx, item.get("key", "未标注"), _n(count), _pct(_safe_ratio(count, total))])
    if rows:
        blocks.append("**省份投诉分布TOP10**\n")
        blocks.append(_table(["排名", "省份", "提及量", "占比"], rows))

    return "\n\n".join(blocks)


def _refund_analysis_md(refund_data: list, refund_tertiary_data: list, escalation_data: list, narratives: dict) -> str:
    if not refund_data:
        return ""

    blocks: list[str] = []
    blocks.append("#### 退费诉求专题分析")

    # LLM narrative
    narrative = _paragraphs(narratives.get("refund_analysis") or [])
    if narrative:
        blocks.append(narrative)

    # Refund distribution table
    blocks.append(_chart_note("退费诉求分布饼状图"))
    refund_total = _sum_counts(refund_data)
    refund_rows = []
    for idx, item in enumerate([r for r in refund_data if r.get("count", 0) > 0][:5], start=1):
        count = int(item.get("count", 0))
        refund_rows.append([idx, item.get("key", "未标注"), _n(count), _pct(_safe_ratio(count, refund_total))])
    if refund_rows:
        blocks.append("**退费诉求分布**\n")
        blocks.append(_table(["排名", "退费诉求", "提及量", "占比"], refund_rows))

    # Refund-tertiary association
    blocks.append(_chart_note("退费诉求与三级问题关联表格"))
    tert_rows = []
    for rt in refund_tertiary_data[:3]:
        rt_key = str(rt.get("key", "未标注"))
        rt_count = int(rt.get("count", 0))
        tert_items = [t for t in rt.get("top_tertiary", []) if t.get("count", 0) > 0]
        if not tert_items:
            tert_rows.append([rt_key, _n(rt_count), "无", "0", "0.0%"])
            continue
        for tert in tert_items[:3]:
            tert_count = int(tert.get("count", 0))
            tert_rows.append([
                rt_key,
                _n(rt_count),
                tert.get("key", "未标注"),
                _n(tert_count),
                _pct(_safe_ratio(tert_count, rt_count)),
            ])
    if tert_rows:
        blocks.append("**退费诉求与三级问题关联**\n")
        blocks.append(_table(["退费诉求", "服务数据量", "关联三级问题", "提及量", "退费组内占比"], tert_rows))

    # Escalation risk
    if escalation_data:
        blocks.append(_chart_note("升级投诉风险分布图表"))
        esc_total = _sum_counts(escalation_data)
        esc_rows = []
        for idx, item in enumerate([e for e in escalation_data if e.get("count", 0) > 0][:3], start=1):
            count = int(item.get("count", 0))
            esc_rows.append([idx, item.get("key", "未标注"), _n(count), _pct(_safe_ratio(count, esc_total))])
        if esc_rows:
            blocks.append("**升级投诉风险分布**\n")
            blocks.append(_table(["排名", "升级投诉倾向", "提及量", "占比"], esc_rows))

    return "\n\n".join(blocks)


def _executive_summary_md(exec_text: str) -> str:
    """Render the executive summary block in markdown."""
    if not exec_text or not exec_text.strip():
        return ""
    text = exec_text.strip()
    import re
    # Split on section headers: "一、...", "二、...", etc. (may or may not be bold)
    sections = re.split(r'\n(?=\*?\*?\s*[一二三四]、)', text)
    kept = []
    for sec in sections:
        stripped = sec.lstrip('*')
        if stripped.startswith('一、') or stripped.startswith('三、'):
            continue
        kept.append(sec.replace('痛点', '问题'))
    text = '\n'.join(kept)
    # Renumber: remaining 二→一, 四→二
    text = re.sub(r'^(\*?\*?\s*)二、', r'\1一、', text, flags=re.MULTILINE)
    text = re.sub(r'^(\*?\*?\s*)四、', r'\1二、', text, flags=re.MULTILINE)
    text = text.replace('三大问题', '三大问题')
    return f"### 核心摘要与发现\n\n> {text}"


def _primary_detail_breakdown_md(result: dict, narratives: dict, total: int) -> str:
    """Per-primary-label breakdown: each primary has its top tertiary labels
    as '诉求类型', with share of primary count and LLM summary."""
    primary_labels = [
        item for item in (result.get("primary", []) or [])
        if str(item.get("key", "")).strip() in CANONICAL_PRIMARY_TERTIARY
    ]
    if not primary_labels:
        return ""
    primary_labels = [p for p in primary_labels if p.get("count", 0) > 0][:6]
    if not primary_labels:
        return ""

    cause_detail = narratives.get("tertiary_cause_detail") or []
    cause_by_label = {
        canonical_tertiary_label(item.get("label", "")): item
        for item in cause_detail
        if item.get("label")
    }
    primary_summaries = narratives.get("primary_summaries", [])

    cn_numbers = ["一", "二", "三", "四", "五", "六"]
    blocks = []

    for idx, primary_item in enumerate(primary_labels[:6]):
        pkey = primary_item.get("key", "")
        pcount = int(primary_item.get("count", 0))
        pshare = _pct(_safe_ratio(pcount, total))

        heading = f"### {cn_numbers[idx]}、{pkey}（共{_n(pcount)}条，占比{pshare}）"
        parts = [heading]

        llm_summary = ""
        for ps in primary_summaries:
            if ps.get("label") == pkey:
                llm_summary = ps.get("summary", "")
                break
        if not llm_summary:
            raise RuntimeError(f"一级标签小结缺失：{pkey}")

        primary_tertiary = primary_top_tertiary_items(result, pkey, pcount, limit=5)
        if not primary_tertiary:
            raise RuntimeError(f"一级标签无法按权威 taxonomy 找到三级分布：{pkey}")

        if primary_tertiary:
            # Appeal distribution table: rows = tertiary labels under this primary
            parts.append(f"\n**用户核心诉求分布**\n")
            dist_rows = []
            for ti in primary_tertiary[:5]:
                tik = ti.get("key", "")
                tic = int(ti.get("count", 0))
                if tic <= 0:
                    continue
                tipct = str(ti.get("share") or (f"{(tic / pcount * 100):.1f}%" if pcount > 0 else "0.0%"))
                ci = cause_by_label.get(canonical_tertiary_label(tik), {})
                summ = ci.get("user_voice_natural", "") or ci.get("content_summary", "") or ci.get("root_cause", "") or ""
                if not summ:
                    raise RuntimeError(f"典型用户原话缺失：{tik}")
                dist_rows.append([tik, tipct, summ])
            if dist_rows:
                parts.append(_table(["诉求类型", "频次占比", "典型用户原话"], dist_rows))

            # Deep analysis per-top tertiary
            for rank, t in enumerate(primary_tertiary[:3], 1):
                tkey = t.get("key", "")
                tcount = int(t.get("count", 0))
                tshare = _pct(_safe_ratio(tcount, pcount)) if pcount > 0 else "0%"
                parts.append(f"\n### {tkey}（共{_n(tcount)}条，占该一级问题{tshare}）")
                cause = cause_by_label.get(canonical_tertiary_label(tkey), {})
                content_s = cause.get("content_summary", "")
                cs_s = cause.get("cs_reply_summary", "")
                root = cause.get("root_cause", "")
                sp = []
                if content_s and len(content_s.strip()) > 10:
                    sp.append(f"服务内容：{content_s.strip().rstrip('。')}。")
                if cs_s and len(cs_s.strip()) > 10:
                    sp.append(f"客服应对：{cs_s.strip().rstrip('。')}。")
                if root:
                    sp.append(f"根因判断：{root.strip().rstrip('。')}。")
                if sp:
                    parts.append(f"\n**分析小结**：{' '.join(sp)}")
                else:
                    raise RuntimeError(f"三级标签分析小结缺失：{tkey}")

        parts.append(f"\n{llm_summary}")
        blocks.append("\n".join(parts))

    # Natural-language summary across all primaries (LLM generated two paragraphs)
    overall_eval = narratives.get("primary_overall_evaluation") or []
    blocks.append(_build_natural_summary_md(overall_eval, primary_labels))

    return "\n\n---\n\n".join(blocks) if blocks else ""


def _build_natural_summary_md(overall_eval: list[str], primary_labels: list[dict]) -> str:
    """Build a natural-language summary across primary labels."""
    parts = ["### 一级标签综合评价\n"]
    if not isinstance(overall_eval, list) or len(overall_eval) < 2:
        raise RuntimeError("一级标签综合评价缺失，报告生成失败。")
    parts.append(str(overall_eval[0]).strip())
    parts.append(str(overall_eval[1]).strip())
    return "\n\n".join(parts)


def _primary_summaries_md(primary_summaries: list) -> str:
    """Render primary-level summary blocks after rank table."""
    if not primary_summaries:
        return ""
    blocks = []
    for item in primary_summaries:
        label = item.get("label", "未标注")
        count = item.get("count", 0)
        share = item.get("share", "0%")
        summary = item.get("summary", "")
        if summary:
            blocks.append(f"**「{label}」小结**（{count}件，占比{share}）\n>{summary}")
    if blocks:
        return "\n\n".join(blocks)
    return ""


def _four_ops_md(four_ops: list, four_products: list, mapping_table: list, narratives: dict) -> str:
    """Render four operations / four product levels analysis with mapping table."""
    parts = ["#### 四个运营维度分析\n"]
    parts.append('<small>原图：四个运营维度分布图；Markdown 展示：数据表。</small>\n')
    if four_ops:
        rows = []
        for item in four_ops[:5]:
            rows.append([item.get("key", ""), _n(item.get("count", 0))])
        parts.append("**四个运营维度分布**\n")
        parts.append(_table(["运营维度", "问题量"], rows))
    if four_products:
        rows = []
        for item in four_products[:5]:
            rows.append([item.get("key", ""), _n(item.get("count", 0))])
        parts.append("\n**四个产品层次分布**\n")
        parts.append(_table(["产品层次", "问题量"], rows))
    # Mapping table of tertiary labels to four dimensions
    if mapping_table:
        parts.append("\n**三级问题标签 → 四个层次/四个运营 映射表**\n")
        rows = []
        for m in mapping_table:
            rows.append([
                m.get("tertiary_label", ""),
                _n(m.get("count", 0)),
                m.get("operation", ""),
                m.get("product_level", ""),
            ])
        parts.append(_table(["三级标签", "问题量", "归属运营维度", "归属产品层次"], rows))
    return "\n".join(parts)


def _typical_case_deep_dive_md(deep_data: list[dict]) -> str:
    """Render typical case deep dives."""
    if not deep_data:
        return ""
    parts = ["#### 典型问题深度分析\n"]
    parts.append('<small>原图：典型问题案例分析卡片；Markdown 展示：文本摘要。</small>\n')
    for item in deep_data[:3]:
        label = item.get("label", "")
        count = _n(item.get("count", 0))
        analysis = _text(item.get("analysis", ""))
        if analysis:
            parts.append(f"**「{label}」（共{count}件）**\n\n{analysis}\n")
    return "\n".join(parts)


def _methodology_md(methodology_text: str) -> str:
    """Render methodology disclaimer (subtle one-liner)."""
    if not methodology_text or not methodology_text.strip():
        return ""
    # If it's a short one-liner, render as subtle footnote
    if len(methodology_text.strip()) < 80:
        return f"\n---\n*{methodology_text.strip()}*"
    return f"#### 分析方法与局限性\n\n{methodology_text.strip()}"


def render_markdown_report(result: dict, output_path: Path) -> Path:
    result = sanitize_report_payload(result)
    trend_view = _build_trend_view(result.get("daily", []), result.get("filters", {}), result.get("anomalies", []))
    context = build_report_context(result, trend_view)
    section_focus = context.section_focus
    narratives: dict[str, list[str]] = context.narratives
    total = context.total
    period_start = context.period_start
    period_end = context.period_end
    trend_window_note = (
        trend_view.get("note") or "当前按完整查询周期展示每日趋势。"
        if section_focus in {"trend", "full"}
        else "当前报告未展示 1.2 趋势章节。"
    )

    sections: list[str] = [
        "# 一、整体情况",
        "\n".join(
            [
                f"> 数据周期：{period_start} 至 {period_end}  ",
                f"> 总服务数据量：{_n(total)} 件  ",
            ]
        ),
    ]

    if section_focus in {"distribution", "full"}:
        sections.extend(
            [
                "---",
                _executive_summary_md(narratives.get("executive_summary", "")),
                "---",
                "### 1.1 问题分布概览",
                "#### 分析结论",
                _paragraphs(narratives.get("distribution_conclusion"), _distribution_insights(result)),
                _unlabeled_md_block(narratives.get("unlabeled_distribution_summary") or _unlabeled_dist_lines(result)),
                "#### 一级问题概览",
                _chart_note("一级标签类型分布饼状图"),
                _paragraphs(narratives.get("primary_overview")),
                _rank_table(result.get("primary", []), total, "一级标签"),
                _primary_detail_breakdown_md(result, narratives, total),
            ]
        )

    if section_focus in {"trend", "full"}:
        trend_summary = narratives.get("trend_chart_summary") or _trend_chart_summary(trend_view)
        sections.extend(
            [
                "---",
                "### 1.2 投诉趋势与异动表现",
                "#### 分析结论",
                _paragraphs(narratives.get("trend_conclusion"), _trend_insights(result, trend_view)),
                "#### 每日问题提及量与负向情绪占比",
                _chart_note(
                    "每日问题提及量与负向情绪占比双轴折线图（左轴为问题提及量柱状图，右轴为负向情绪占比折线图，赛事日标注红色竖线）",
                    "趋势描述和每日明细表",
                ),
                _paragraphs(trend_summary),
                f"**图表分析总结**：{trend_window_note}",
                "#### 每日明细数据",
                _daily_detail_table(trend_view),
                "#### 赛事日样例原声",
                _chart_note("赛事日样例原声卡片", "文本摘要列表"),
                _trend_voice_markdown(trend_view, narratives),
                "#### 异动节点",
                _chart_note("异动节点卡片", "异动节点表格"),
                _paragraphs(narratives.get("anomaly_summary")),
                _anomaly_table(trend_view.get("anomalies", [])),
                
            ]
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_sanitize_report_terms("\n\n".join(sections) + "\n"), encoding="utf-8")
    return output_path
