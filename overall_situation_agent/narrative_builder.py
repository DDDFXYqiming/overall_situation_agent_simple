from __future__ import annotations

import json
import logging
import math
import re
import time
from typing import Any
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

from .llm_client import OpenAICompatibleClient, parse_json_object
from .taxonomy import CANONICAL_PRIMARY_TERTIARY, primary_top_tertiary_items

logger = logging.getLogger(__name__)



# Map-Reduce dimension analysis constants
DIMENSION_FIELDS = {
    "content": "content_excerpt",
    "cs_reply": "cs_reply_excerpt",
    "customer_appeal": "customer_key_appeal_full",
    "customer_keywords": "customer_keywords",
    "cs_action": "cs_key_action",
    "cs_keywords": "cs_keywords",
}

# 仅保留报告正文真正依赖的核心维度，降低空响应风险。
REQUIRED_MAP_DIMS = ("content", "customer_appeal", "cs_action")

DIMENSION_LABELS = {
    "content": "服务内容",
    "cs_reply": "客服回复",
    "customer_appeal": "客户关键诉求",
    "customer_keywords": "诉求关键词",
    "cs_action": "客服处理动作",
    "cs_keywords": "客服关键词",
}

DIM_PROMPTS = {
    "content": (
        "\u4f60\u662f\u4e00\u4e2a\u6295\u8bc9\u5206\u6790\u52a9\u624b\u3002"
        "\u4ee5\u4e0b\u662f\u6807\u7b7e\u300c{label}\u300d\u4e0b\u7684 {count} \u6761\u5de5\u5355\u5185\u5bb9\u539f\u6587\uff08\u968f\u673a\u91c7\u6837\uff09\uff1a\n"
        "{texts}\n\n"
        "\u8bf7\u5206\u6790\u8fd9 {count} \u6761\u6837\u672c\uff0c\u7528 2-3 \u53e5\u8bdd\u5199\u4e00\u6bb5\u6c47\u603b\u5206\u6790\uff0880-150\u5b57\uff09\uff0c\u8981\u6c42\uff1a\n"
        "- \u5f52\u7eb3\u6574\u4f53\u8d8b\u52bf\u548c\u5178\u578b\u6a21\u5f0f\uff0c\u4e0d\u8981\u9010\u6761\u63cf\u8ff0\n"
        '- \u4f7f\u7528\u300c\u6837\u672c\u663e\u793a\uff0c\u5927\u591a\u6570\u7528\u6237\u2026\u300d\u300c\u7528\u6237\u666e\u904d\u2026\u300d\u7b49\u6c47\u603b\u53e5\u5f0f\n'
        "- \u5177\u4f53\u8bf4\u660e\u7528\u6237\u53cd\u9988\u7684\u5171\u540c\u95ee\u9898\u7c7b\u578b\u548c\u5178\u578b\u573a\u666f\n"
        "- \u4e0d\u8981\u7f57\u5217\u539f\u6587\n"
    ),
    "cs_reply": (
        "\u4f60\u662f\u4e00\u4e2a\u6295\u8bc9\u5206\u6790\u52a9\u624b\u3002"
        "\u4ee5\u4e0b\u662f\u6807\u7b7e\u300c{label}\u300d\u4e0b\u7684 {count} \u6761\u5ba2\u670d\u56de\u590d\u539f\u6587\uff08\u968f\u673a\u91c7\u6837\uff09\uff1a\n"
        "{texts}\n\n"
        "\u8bf7\u5206\u6790\u8fd9 {count} \u6761\u6837\u672c\uff0c\u7528 2-3 \u53e5\u8bdd\u5199\u4e00\u6bb5\u6c47\u603b\u5206\u6790\uff0880-150\u5b57\uff09\uff0c\u8981\u6c42\uff1a\n"
        "- \u5f52\u7eb3\u5ba2\u670d\u7684\u666e\u904d\u56de\u5e94\u6a21\u5f0f\u548c\u8bdd\u672f\u7279\u70b9\n"
        '- \u4f7f\u7528\u300c\u5ba2\u670d\u666e\u904d\u2026\u300d\u300c\u591a\u6570\u56de\u590d\u2026\u300d\u7b49\u53e5\u5f0f\n'
        "- \u8bf4\u660e\u5ba2\u670d\u7684\u5904\u7406\u503e\u5411\u548c\u5e38\u89c1\u5e94\u5bf9\u7b56\u7565\n"
    ),
    "customer_appeal": (
        "\u4f60\u662f\u4e00\u4e2a\u6295\u8bc9\u5206\u6790\u52a9\u624b\u3002"
        "\u4ee5\u4e0b\u662f\u6807\u7b7e\u300c{label}\u300d\u4e0b\u7684 {count} \u6761\u5ba2\u6237\u5173\u952e\u8bc9\u6c42\u539f\u6587\uff08\u968f\u673a\u91c7\u6837\uff09\uff1a\n"
        "{texts}\n\n"
        "\u8bf7\u7528 2-3 \u53e5\u8bdd\u6c47\u603b\u5206\u6790\uff0880-150\u5b57\uff09\uff0c\u5f52\u7eb3\u5ba2\u6237\u7684\u6838\u5fc3\u8bc9\u6c42\u7c7b\u578b\u3001\u8868\u8fbe\u65b9\u5f0f\u548c\u60c5\u7eea\u7279\u5f81\u3002\n"
        '- \u4f7f\u7528\u300c\u7528\u6237\u8bc9\u6c42\u4e3b\u8981\u96c6\u4e2d\u5728\u2026\u300d\u300c\u5173\u952e\u8bcd\u96c6\u4e2d\u5728\u2026\u300d\u7b49\u53e5\u5f0f\n'
    ),
    "customer_keywords": (
        "\u4f60\u662f\u4e00\u4e2a\u6295\u8bc9\u5206\u6790\u52a9\u624b\u3002"
        "\u4ee5\u4e0b\u662f\u6807\u7b7e\u300c{label}\u300d\u4e0b\u7684 {count} \u6761\u5ba2\u6237\u8bc9\u6c42\u5173\u952e\u8bcd\uff08\u968f\u673a\u91c7\u6837\uff09\uff1a\n"
        "{texts}\n\n"
        "\u8bf7\u7528 1-2 \u53e5\u8bdd\u6c47\u603b\u5206\u6790\uff0830-60\u5b57\uff09\uff0c\u5f52\u7eb3\u5173\u952e\u8bcd\u7684\u503e\u5411\u548c\u5206\u5e03\u89c4\u5f8b\u3002\n"
    ),
    "cs_action": (
        "\u4f60\u662f\u4e00\u4e2a\u6295\u8bc9\u5206\u6790\u52a9\u624b\u3002"
        "\u4ee5\u4e0b\u662f\u6807\u7b7e\u300c{label}\u300d\u4e0b\u7684 {count} \u6761\u5ba2\u670d\u5173\u952e\u5904\u7406\u52a8\u4f5c\uff08\u968f\u673a\u91c7\u6837\uff09\uff1a\n"
        "{texts}\n\n"
        "\u8bf7\u7528 2-3 \u53e5\u8bdd\u6c47\u603b\u5206\u6790\uff0880-150\u5b57\uff09\uff0c\u5f52\u7eb3\u5ba2\u670d\u7684\u4e3b\u8981\u5904\u7f6e\u6a21\u5f0f\u3001\u7b56\u7565\u548c\u6d41\u7a0b\u3002\n"
    ),
    "cs_keywords": (
        "\u4f60\u662f\u4e00\u4e2a\u6295\u8bc9\u5206\u6790\u52a9\u624b\u3002"
        "\u4ee5\u4e0b\u662f\u6807\u7b7e\u300c{label}\u300d\u4e0b\u7684 {count} \u6761\u5ba2\u670d\u5904\u7406\u5173\u952e\u8bcd\uff08\u968f\u673a\u91c7\u6837\uff09\uff1a\n"
        "{texts}\n\n"
        "\u8bf7\u7528 1-2 \u53e5\u8bdd\u6c47\u603b\u5206\u6790\uff0830-60\u5b57\uff09\uff0c\u5f52\u7eb3\u8fd9\u4e9b\u5173\u952e\u8bcd\u7684\u5173\u6ce8\u70b9\u548c\u603b\u7ed3\u6a21\u5f0f\u3002\n"
    ),
}


NARRATIVE_KEYS = [
    "executive_summary",
    "distribution_conclusion",
    "distribution_business_dimension",
    "primary_overview",
    "secondary_overview",
    "tertiary_overview",
    "journey_summary",
    "operation_need_summary",
    "member_cluster_summary",
    "case_summary",
    "cause_summary",
    "voice_summary",
    "tertiary_cause_detail",
    "trend_conclusion",
    "anomaly_summary",
    "unlabeled_distribution_summary",
    "unlabeled_trend_summary",
    "trend_chart_summary",
    "trend_voice_summary",
    "cause_voice_sample_summaries",
    "trend_voice_sample_summaries",
    "province_analysis",
    "refund_analysis",
]


def _n(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def _pct(part: float, whole: float) -> str:
    if not whole:
        return "0.0%"
    return f"{part / whole * 100:.1f}%"


def _top(items: list[dict], limit: int = 5) -> list[dict]:
    return [item for item in items if item.get("count", 0) > 0][:limit]


def _top_with_share(items: list[dict], limit: int = 5) -> list[dict]:
    total = _sum_counts(items)
    buckets = []
    for item in _top(items, limit):
        count = item.get("count", 0)
        bucket = dict(item)
        bucket["share"] = count / total if total else 0
        bucket["display"] = f"{item.get('key', '未标注')}（共{_n(count)}条，占比{_pct(count, total)}）"
        buckets.append(bucket)
    return buckets


def _join_items(items: list[dict], limit: int = 3, total: int | None = None) -> str:
    visible = _top(items, limit)
    denominator = total if total is not None else _sum_counts(items)
    return (
        "、".join(
            f"{item['key']}（共{_n(item['count'])}条，占比{_pct(item.get('count', 0), denominator)}）"
            for item in visible
        )
        if visible
        else "无"
    )


def _join_keys(items: list[dict], limit: int = 3) -> str:
    visible = _top(items, limit)
    return "、".join(str(item.get("key")) for item in visible if item.get("key")) if visible else "无"


def _sum_counts(items: list[dict]) -> int:
    return int(sum(item.get("count", 0) for item in items))


def _ratio(part: float, whole: float) -> str:
    return f"{part / whole * 100:.1f}%" if whole else "0.0%"


def _matchday(day: dict[str, Any]) -> dict[str, Any] | None:
    if day.get("is_matchday") and day.get("matchday"):
        return day["matchday"]
    return None


def _matchday_summary(day: dict[str, Any]) -> str:
    payload = _matchday(day)
    return str(payload.get("match_summary", "")).strip() if payload else ""


def _sorted_anomaly_days(anomalies: list[dict]) -> list[dict]:
    return sorted(
        anomalies,
        key=lambda item: (
            -float(item.get("day_over_day_growth") or 0),
            -int(item.get("count") or 0),
            str(item.get("date") or ""),
        ),
    )


def _business_dimension_lines(result: dict[str, Any]) -> list[str]:
    service_type = _top(result.get("service_type", []), 3)
    service_total = _sum_counts(result.get("service_type", []))
    tertiary = _top(result.get("tertiary", []), 3)
    lines: list[str] = []
    if service_type and service_total:
        top = service_type[0]
        issue_text = "、".join(str(item.get("key")) for item in tertiary if item.get("key")) or "订购、权益和观看体验问题"
        lines.append(
            f"业务维度上，用户投诉主要落在{issue_text}，说明当前压力不是单点功能异常，而是订购退订、权益兑现和赛事观看体验在同一服务链路上叠加。"
        )
    return lines


def _trend_matchday_business_lines(result: dict[str, Any], daily: list[dict]) -> list[str]:
    if not daily:
        return []
    matchdays = [day for day in daily if _matchday(day)]
    non_matchdays = [day for day in daily if not _matchday(day)]
    lines: list[str] = []

    if matchdays and non_matchdays:
        matchday_avg = sum(day.get("count", 0) for day in matchdays) / len(matchdays)
        non_matchday_avg = sum(day.get("count", 0) for day in non_matchdays) / len(non_matchdays)
        matchday_dates = "、".join(sorted(str(day.get("date", "")) for day in matchdays if day.get("date")))
        lines.append(
            f"有比赛的是 {len(matchdays)} 天（{matchday_dates}），赛事日日均问题量 {matchday_avg:.1f} 件，非赛事日日均 {non_matchday_avg:.1f} 件。"
        )
    elif matchdays:
        matchday_dates = "、".join(sorted(str(day.get("date", "")) for day in matchdays if day.get("date")))
        total = sum(day.get("count", 0) for day in matchdays)
        lines.append(f"有比赛的是 {len(matchdays)} 天（{matchday_dates}），赛事日合计问题量 {_n(total)} 件。")
    elif (result.get("schedule") or {}).get("status") != "loaded":
        lines.append(_schedule_message(result))
    peak_day = max(daily, key=lambda item: item.get("count", 0), default=None)
    if peak_day:
        services = _join_keys(peak_day.get("top_service_type", []), 2)
        issues = _join_keys(peak_day.get("top_tertiary", []), 3)
        if services != "无" or issues != "无":
            lines.append(
                f"从业务表现看，峰值附近的投诉集中在{services}类服务场景，用户表达的问题多围绕{issues}，赛事前后的即时观看预期会放大退订、权益和多端使用链路的不满。"
            )
    return lines


def _schedule_message(result: dict[str, Any]) -> str:
    schedule = result.get("schedule") or {}
    return str(schedule.get("message") or "未提供赛程文件，1.2 未标注赛事日。")


def _trend_voice_examples(daily: list[dict], anomalies: list[dict], limit: int = 3) -> list[dict]:
    if not daily:
        return []
    peak = max(daily, key=lambda item: item.get("count", 0), default=None)
    peak_date = str(peak.get("date")) if peak else ""
    anomaly_dates = {str(item.get("date")) for item in anomalies if item.get("date")}
    matchday_samples = [day for day in daily if _matchday(day) and day.get("samples")]
    matchday_samples.sort(
        key=lambda item: (
            item.get("date") == peak_date,
            str(item.get("date")) in anomaly_dates,
            item.get("count", 0),
            item.get("negative_ratio", 0),
        ),
        reverse=True,
    )
    selected = []
    seen_dates: set[str] = set()
    for day in matchday_samples:
        date = str(day.get("date") or "")
        if not date or date in seen_dates:
            continue
        seen_dates.add(date)
        selected.append(
            {
                "date": date,
                "count": day.get("count", 0),
                "match_summary": _matchday_summary(day),
                "top_tertiary": _top(day.get("top_tertiary", []), 3),
                "quotes": [sample.get("content_excerpt", "") for sample in day.get("samples", [])[:2]],
                "samples": day.get("samples", [])[:2],
            }
        )
        if len(selected) >= limit:
            break
    return selected


def _summary_payload(result: dict[str, Any]) -> dict[str, Any]:
    daily = result.get("daily", [])
    peak_day = max(daily, key=lambda item: item.get("count", 0), default=None)
    neg_peak = max(daily, key=lambda item: item.get("negative_ratio", 0), default=None)
    anomalies = _sorted_anomaly_days(result.get("anomalies", []))[:5]
    trend_voice_examples = _trend_voice_examples(daily, result.get("anomalies", []))
    matchdays = []
    for day in daily:
        matchday = day.get("matchday")
        if day.get("is_matchday") and matchday:
            matchdays.append({"date": day["date"], "summary": matchday.get("match_summary"), "count": day.get("count", 0)})
            if len(matchdays) >= 5:
                break
    cause_examples = []
    for item in result.get("top_tertiary_examples", [])[:5]:
        cause_examples.append({
            "issue": item.get("key"),
            "count": item.get("count"),
            "appeals": _top(item.get("top_appeals", []), 3),
            "quotes": [sample.get("content_excerpt", "") for sample in item.get("samples", [])[:2]],
        })
    labeled_total = result.get("total", 0)
    unlabeled_analysis = result.get("unlabeled_analysis", {})
    unlabeled_total = unlabeled_analysis.get("unlabeled_total", 0)
    total_with_unlabeled = result.get("total_with_unlabeled", labeled_total)
    unlabeled_ratio = unlabeled_total / total_with_unlabeled if total_with_unlabeled else 0
    unlabeled_trend_analysis = result.get("unlabeled_trend_analysis", {})
    evidence = result.get("tertiary_evidence") or {}
    evidence_labels = evidence.get("labels", [])
    cause_examples_ev = []
    for item in evidence_labels[:5]:
        appeals = [{"key": b["key"], "count": b["count"]} for b in item.get("appeal_agg", [])]
        cs_actions = [{"key": b["key"], "count": b["count"]} for b in item.get("cs_action_agg", [])]
        cause_examples_ev.append({
            "issue": item.get("key"),
            "count": item.get("count"),
            "appeals": appeals,
            "cs_actions": cs_actions,
            "samples": item.get("samples", [])[:5],
        })
    # build appeal_full_texts: per-label full appeal texts for LLM analysis
    appeal_full_texts = {}
    for item in evidence_labels[:5]:
        label = item.get("key", "")
        raw_appeals = [s.get("customer_key_appeal_full", "") or s.get("customer_key_appeal", "") for s in item.get("samples", [])]
        raw_appeals = [a[:300] for a in raw_appeals if a.strip()]
        appeal_full_texts[label] = raw_appeals

    return {
        "appeal_full_texts": appeal_full_texts,
        "tertiary_evidence": evidence,
        "tertiary_evidence_examples": cause_examples_ev,
        "total": total_with_unlabeled,
        "labeled_total": labeled_total,
        "total_with_unlabeled": total_with_unlabeled,
        "unlabeled_total": unlabeled_total,
        "unlabeled_ratio": unlabeled_ratio,
        "unlabeled_samples": unlabeled_analysis.get("samples", [])[:5],
        "unlabeled_emotion": unlabeled_analysis.get("emotion", [])[:3],
        "unlabeled_province": unlabeled_analysis.get("province", [])[:5],
        "unlabeled_csp_name": unlabeled_analysis.get("csp_name", [])[:5],
        "unlabeled_operation_action": unlabeled_analysis.get("operation_action", [])[:5],
        "unlabeled_latent_need": unlabeled_analysis.get("latent_need", [])[:5],
        "unlabeled_customer_key_appeal": unlabeled_analysis.get("customer_key_appeal", [])[:5],
        "unlabeled_has_refund_demand": unlabeled_analysis.get("has_refund_demand", []),
        "unlabeled_has_escalation": unlabeled_analysis.get("has_escalation", []),
        "unlabeled_trend_daily": unlabeled_trend_analysis.get("daily", []),
        "unlabeled_trend_peak_day": unlabeled_trend_analysis.get("peak_day"),
        "unlabeled_trend_emotion_peak": unlabeled_trend_analysis.get("emotion_peak_day"),
        "primary": _top_with_share(result.get("primary", []), 5),
        "secondary": _top_with_share(result.get("secondary", []), 5),
        "tertiary": _top_with_share(result.get("tertiary", []), 5),
        "emotion": _top_with_share(result.get("emotion", []), 5),
        "service_type": _top_with_share(result.get("service_type", []), 5),
        "refund": _top(result.get("refund", []), 5),
        "escalation": _top(result.get("escalation", []), 5),
        "label_group": _top(result.get("label_group", []), 5),
        "insight_dimension": _top(result.get("insight_dimension", []), 5),
        "customer_key_appeal": _top(result.get("customer_key_appeal", []), 5),
        "cs_key_action": _top(result.get("cs_key_action", []), 5),
        "operation_action": _top(result.get("operation_action", []), 5),
        "biz_member_cluster": _top(result.get("biz_member_cluster", []), 5),
        "marketing_activity_page": _top(result.get("marketing_activity_page", []), 5),
        "marketing_activity_match_status": _top(result.get("marketing_activity_match_status", []), 5),
        "marketing_activity_match_keywords": _top(result.get("marketing_activity_match_keywords", []), 5),
        "age_ranges": _top(result.get("age_ranges", []), 6),
        "gender": _top(result.get("gender", []), 5),
        "latent_need": _top(result.get("latent_need_examples", []), 5),
        "time_period": _top(result.get("time_period", []), 5),
        "match_label": _top(result.get("match_label", []), 5),
        "avg_duration_minutes": result.get("avg_duration_minutes"),
        "peak_day": peak_day,
        "negative_peak_day": neg_peak,
        "anomalies": anomalies,
        "matchdays": matchdays,
        "schedule_message": _schedule_message(result),
        "cause_examples": cause_examples,
        "trend_voice_examples": [{"date": item.get("date"), "match_summary": item.get("match_summary"), "top_tertiary": item.get("top_tertiary", []), "quotes": item.get("quotes", [])} for item in trend_voice_examples],
        "operation_need_examples": result.get("operation_need_examples", [])[:5],
        "member_cluster_examples": result.get("member_cluster_examples", [])[:5],
        "latent_need_examples": result.get("latent_need_examples", [])[:5],
        "sample_texts_raw": (result.get("sample_texts") or {}).get("raw", [])[:40],
        "sample_texts_by_primary": (result.get("sample_texts") or {}).get("by_primary", [])[:24],
        "sample_texts_by_service_type": (result.get("sample_texts") or {}).get("by_service_type", [])[:20],
        "sample_texts_matchday": (result.get("sample_texts") or {}).get("matchday", [])[:10],
        "province_tertiary": result.get("province_tertiary", [])[:10],
        "province_refund": result.get("province_refund", [])[:10],
        "refund_tertiary": result.get("refund_tertiary", [])[:3],
    }


def _unlabeled_distribution_summary(result: dict[str, Any]) -> list[str]:
    unlabeled_analysis = result.get("unlabeled_analysis", {})
    unlabeled_total = unlabeled_analysis.get("unlabeled_total", 0)
    if not unlabeled_total:
        return []
    total_with_unlabeled = result.get("total_with_unlabeled", result.get("total", 0))
    unlabeled_pct = _pct(unlabeled_total, total_with_unlabeled)
    emotion = unlabeled_analysis.get("emotion", [])
    csp_name = unlabeled_analysis.get("csp_name", [])
    appeal = unlabeled_analysis.get("customer_key_appeal", [])
    lines = [f"本次共纳入 {_n(total_with_unlabeled)} 条服务数据，其中 {_n(unlabeled_total)} 条（{unlabeled_pct}）一/二/三级标签未标注，已从问题分布统计中排除。"]
    if emotion or appeal or csp_name:
        lines.append(f"从未标注服务数据的内容结构看，情绪以 {_join_keys(emotion, 2)} 为主，诉求集中在 {_join_keys(appeal, 2)}，主要渠道/终端线索为 {_join_keys(csp_name, 2)}，更适合作为待回补标签池单独治理。")
    return lines[:4]


def _unlabeled_trend_summary(result: dict[str, Any]) -> list[str]:
    unlabeled_trend = result.get("unlabeled_trend_analysis", {})
    unlabeled_total = unlabeled_trend.get("unlabeled_total", 0)
    if not unlabeled_total:
        return []
    total_with_unlabeled = result.get("total_with_unlabeled", result.get("total", 0))
    unlabeled_pct = _pct(unlabeled_total, total_with_unlabeled)
    daily = unlabeled_trend.get("daily", [])
    peak = unlabeled_trend.get("peak_day")
    emotion_peak = unlabeled_trend.get("emotion_peak_day")
    lines = [f"本周期共 {_n(unlabeled_total)} 条一/二/三级标签未标注服务数据，占原始总量的 {unlabeled_pct}，未纳入上述趋势计算。"]
    if daily:
        lines.append(f"时间上覆盖 {daily[0]['date']} 至 {daily[-1]['date']}；峰值出现在 {peak['date']}（{_n(peak.get('count', 0))} 件）时，建议核查当日是否存在批量活动咨询、权益问题或导入漏标。" if peak else f"时间上覆盖 {daily[0]['date']} 至 {daily[-1]['date']}，建议作为独立漏标趋势跟踪。")
    if emotion_peak:
        lines.append(f"情绪高峰出现在 {emotion_peak['date']}，负向情绪占比 {emotion_peak.get('negative_ratio', 0) * 100:.1f}%，可优先抽样校验该日未标注文本的真实问题类型。")
    if daily and len(daily) > 1:
        midpoint = len(daily) // 2
        first_half = daily[:midpoint]
        second_half = daily[midpoint:]
        first_avg = sum(day.get("count", 0) for day in first_half) / len(first_half) if first_half else 0
        second_avg = sum(day.get("count", 0) for day in second_half) / len(second_half) if second_half else 0
        if second_avg > first_avg * 1.5:
            lines.append("趋势上后半周期明显抬升，提示后续导入或标注流程可能出现阶段性漏标。")
        elif first_avg > second_avg * 1.5:
            lines.append("趋势上前半周期更集中，后半周期有所回落，建议核对早期批次的标签抽取规则。")
    return lines[:4]


def _llm_business_dimension(result: dict[str, Any], llm, section: str) -> list[str]:
    """LLM-enhanced business dimension analysis. Returns one strict natural-language paragraph."""
    if not llm or not llm.enabled:
        return []

    svc_str = "; ".join(t["display"] for t in _top_with_share(result.get("service_type", []), 5)) or "无"
    tert_str = "; ".join(t["display"] for t in _top_with_share(result.get("tertiary", []), 5)) or "无"
    insight_str = "; ".join(t["display"] for t in _top_with_share(result.get("insight_dimension", []), 3)) or "无"

    evidence = result.get("tertiary_evidence", {})
    appeals: list[str] = []
    actions: list[str] = []
    for label in evidence.get("labels", []):
        for sample in label.get("samples", []):
            appeal = (sample.get("customer_key_appeal_full", "") or sample.get("customer_key_appeal", "") or "").strip()
            if appeal:
                appeals.append(appeal[:500])
            action = (sample.get("cs_key_action", "") or "").strip()
            if action:
                actions.append(action[:500])
    random.shuffle(appeals)
    random.shuffle(actions)

    prompt = "\n".join([
        "你是投诉分析报告撰写助手。",
        "",
        "以下是供你理解业务问题的数据，正文不得直接列出其中的数字或占比：",
        f"服务类型分布：{svc_str}",
        f"三级问题TOP：{tert_str}",
        f"洞察维度：{insight_str}",
        "客户关键诉求样本：",
        "\n---\n".join(appeals[:30]) if appeals else "无",
        "客服处理动作样本：",
        "\n---\n".join(actions[:30]) if actions else "无",
        "",
        "请输出一段自然语言业务分析：",
        "1. 必须以“业务维度上，”开头。",
        "2. 总长度严格控制在180-220字，尽量接近200字。",
        "3. 不要列任何具体数字、百分比、条数、排名或TOP表述。",
        "4. 不要写“服务类型「投诉」占比”“共多少条”“占比多少”等数据化表达。",
        "5. 可基于服务类型、三级问题、用户诉求、客服处理动作做归纳，但不要直接抄输入数据。",
        "6. 重点说明服务流程薄弱环节、用户心理和业务链路矛盾。",
        "7. 只输出最终段落，不要输出思考过程、Markdown或条目列表。",
    ])

    variants = [
        prompt,
        prompt + "\n\n上一轮不合规。请重新输出一段180-220字的自然语言正文，仍以“业务维度上，”开头，正文里不要出现任何数字、百分比、条数、占比或TOP。",
        prompt + "\n\n请最后重写一次：只输出最终段落，180-220字，无数字、无占比、无TOP、无条数。",
    ]
    for idx, variant in enumerate(variants, start=1):
        logger.info("distribution business dimension request section=%s attempt=%s/%s", section, idx, len(variants))
        resp = llm.chat(
            [
                {"role": "system", "content": "你是一个投诉分析报告撰写助手。只输出最终正文，不输出思考过程。"},
                {"role": "user", "content": variant},
            ],
            temperature=0.2,
            max_tokens=520,
            timeout_seconds=max(60, min(getattr(llm, "report_timeout", 60), 75)),
            max_retries=1,
        )
        result_text = _normalize_business_dimension_text(resp.content if (not resp.used_fallback and resp.content) else "")
        ok, reason = _validate_distribution_business_dimension(result_text)
        if ok:
            logger.info(
                "distribution business dimension accepted section=%s attempt=%s/%s chars=%s",
                section,
                idx,
                len(variants),
                _compact_char_len(result_text),
            )
            return [result_text]
        logger.info(
            "distribution business dimension rejected section=%s attempt=%s/%s reason=%s",
            section,
            idx,
            len(variants),
            reason,
        )
    return []


def _compact_char_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def _normalize_business_dimension_text(text: Any) -> str:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^```(?:text|markdown)?", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    cleaned = cleaned.strip("\"'“”‘’")
    cleaned = re.sub(r"\s+", "", cleaned)
    return _fit_business_dimension_length(cleaned)


def _fit_business_dimension_length(text: str) -> str:
    """Trim only the LLM's own paragraph so length is stable without rule fallback text."""
    if _compact_char_len(text) <= 220:
        return text
    compact = re.sub(r"\s+", "", text or "")
    clipped = compact[:220]
    cut_points = [clipped.rfind(mark) for mark in ("。", "；", "，")]
    cut = max(cut_points)
    if cut >= 180:
        clipped = clipped[: cut + 1]
    if _compact_char_len(clipped) < 180:
        clipped = compact[:220]
    if clipped and clipped[-1] != "。":
        clipped = clipped.rstrip("，、；：")
        clipped = (clipped[:219] if _compact_char_len(clipped) >= 220 else clipped) + "。"
    if _compact_char_len(clipped) > 220:
        clipped = clipped[:220]
    for dangling in ("整体来看。", "总体来看。", "综合来看。"):
        if clipped.endswith(dangling) and _compact_char_len(clipped[: -len(dangling)]) >= 180:
            clipped = clipped[: -len(dangling)]
            if clipped and clipped[-1] != "。":
                clipped = clipped.rstrip("，、；：") + "。"
            break
    return clipped


def _validate_distribution_business_dimension(text: str) -> tuple[bool, str]:
    if not text:
        return False, "业务维度段落为空"
    if not text.startswith("业务维度上，"):
        return False, "业务维度段落未以指定前缀开头"
    length = _compact_char_len(text)
    if length < 180 or length > 220:
        return False, f"业务维度段落长度不在180-220字范围内（当前{length}）"
    if not text.endswith("。"):
        return False, "业务维度段落未以句号收尾"
    forbidden_patterns = [
        (r"\d", "包含阿拉伯数字"),
        (r"[%％]", "包含百分号"),
        (r"占比", "包含占比"),
        (r"\bTOP\b|Top|top", "包含TOP表述"),
        (r"排名|排行", "包含排名表述"),
        (r"第[一二三四五六七八九十\d]", "包含排名序号"),
        (r"共\s*[一二三四五六七八九十百千万\d,，.]+\s*条", "包含条数"),
        (r"服务类型「[^」]+」占比", "包含服务类型占比句式"),
    ]
    for pattern, reason in forbidden_patterns:
        if re.search(pattern, text):
            return False, reason
    if _looks_like_reasoning_meta(text):
        return False, "包含思考过程文本"
    if _looks_like_raw_dialogue(text):
        return False, "包含原始工单文本"
    if _looks_like_template_phrase(text):
        return False, "包含模板句"
    return True, ""


def _build_distribution_business_dimension(result: dict[str, Any], llm) -> str:
    lines = _llm_business_dimension(result, llm, "distribution")
    if not lines:
        raise RuntimeError("distribution_business_dimension LLM 失败：未生成合规业务维度段落。")
    text = lines[0]
    ok, reason = _validate_distribution_business_dimension(text)
    if not ok:
        raise RuntimeError(f"distribution_business_dimension LLM 失败：{reason}")
    return text


def _distribution_conclusion_lines(result: dict[str, Any], business_dimension: str | None = None) -> list[str]:
    total = result.get("total_with_unlabeled", result.get("total", 0))
    primary = result.get("primary", [])
    secondary = result.get("secondary", [])
    tertiary = result.get("tertiary", [])
    emotion = result.get("emotion", [])
    lines = [
        f"本周期共纳入 {_n(total)} 条用户投诉数据，一级、二级、三级问题分布基于已完成标签标注的服务数据统计。",
        f"一级问题最集中的是 {_join_items(primary, 2, total)}；二级层面主要集中在 {_join_items(secondary, 2, total)}。",
        f"三级问题中 {_join_items(tertiary, 3, total)} 是当前最值得优先定位的高频痛点。",
    ]
    if business_dimension:
        lines.append(business_dimension)
    else:
        lines.extend(_business_dimension_lines(result))
    if emotion:
        lines.append(f"情绪标签以 {_join_items(emotion, 3, total)} 为主，说明当前投诉以负向体验表达为主。")
    return lines


def _llm_province_analysis(result: dict[str, Any], llm) -> list[str]:
    """LLM-enhanced province analysis. Returns 1 paragraph with 200-300 chars."""
    if not llm.enabled:
        return []

    province_data = result.get("province", [])
    province_tertiary = result.get("province_tertiary", [])
    province_refund = result.get("province_refund", [])

    if not province_data:
        return []

    province_str = "; ".join(
        f"{p.get('key')}（{p.get('count')}条）" for p in _top(province_data, 5)
    ) if province_data else "无"

    province_tertiary_str = ""
    for pt in province_tertiary[:5]:
        tertiary_items = "; ".join(
            f"{t.get('key')}（{t.get('count')}条）" for t in _top(pt.get("top_tertiary", []), 3)
        )
        if tertiary_items:
            province_tertiary_str += f"\n- {pt.get('key')}: {tertiary_items}"

    province_refund_str = ""
    for pr in province_refund[:5]:
        refund_items = "; ".join(
            f"{r.get('key')}（{r.get('count')}条）" for r in pr.get("refund_distribution", [])
        )
        if refund_items:
            province_refund_str += f"\n- {pr.get('key')}: {refund_items}"

    prompt = (
        "你是投诉分析报告撰写助手。以下是省份维度的分析数据：\n\n"
        f"省份分布TOP5：{province_str}\n\n"
        f"各省份主要三级问题：{province_tertiary_str}\n\n"
        f"各省份退费诉求分布：{province_refund_str}\n\n"
        "请根据以上数据，写一段深入分析（200-300字），要求：\n"
        "- 必须以「省份维度上」开头\n"
        "- 分析TOP省份的服务数据分布特征和区域差异\n"
        "- 分析各省份主要问题的差异，哪些省份问题集中在哪些类型\n"
        "- 结合退费诉求分布，识别高退费风险的省份\n"
        "- 最后给出区域运营建议，针对性提出优化方向\n"
        "- 使用具体数字支撑论点，但要融入自然语言叙述中\n"
        "- 语言表达要专业、流畅，符合商业分析报告的风格\n"
    )

    resp = llm.chat(
        [
            {"role": "system", "content": "你是一个投诉分析报告撰写助手。严格按照用户要求的格式输出，不要改变开头词语。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=800,
    )
    if resp.used_fallback or not resp.content.strip():
        return []

    result_text = resp.content.strip()
    if result_text and not result_text.startswith("省份维度上"):
        result_text = "省份维度上，" + result_text
    result_lines = [result_text] if result_text else []
    logger.info("PROVINCE_LLM result_text_len=%s", len(result_text) if result_text else 0)
    return result_lines


def _llm_refund_analysis(result: dict[str, Any], llm) -> list[str]:
    """LLM-enhanced refund analysis. Returns 1 paragraph with 200-300 chars."""
    if not llm.enabled:
        return []

    refund_data = result.get("refund", [])
    refund_tertiary = result.get("refund_tertiary", [])
    escalation_data = result.get("escalation", [])

    if not refund_data:
        return []

    refund_str = "; ".join(
        f"{r.get('key')}（{r.get('count')}条）" for r in refund_data
    ) if refund_data else "无"

    refund_tertiary_str = ""
    for rt in refund_tertiary[:3]:
        tertiary_items = "; ".join(
            f"{t.get('key')}（{t.get('count')}条）" for t in _top(rt.get("top_tertiary", []), 3)
        )
        if tertiary_items:
            refund_tertiary_str += f"\n- 退费诉求={rt.get('key')}: {tertiary_items}"

    escalation_str = "; ".join(
        f"{e.get('key')}（{e.get('count')}条）" for e in escalation_data
    ) if escalation_data else "无"

    prompt = (
        "你是投诉分析报告撰写助手。以下是退费诉求维度的分析数据：\n\n"
        f"退费诉求整体分布：{refund_str}\n\n"
        f"退费诉求与三级问题关联：{refund_tertiary_str}\n\n"
        f"升级投诉倾向分布：{escalation_str}\n\n"
        "请根据以上数据，写一段深入分析（200-300字），要求：\n"
        "- 必须以「退费诉求维度上」开头\n"
        "- 分析退费诉求整体占比和分布特征\n"
        "- 识别高退费风险的问题类型，哪些三级标签最容易引发退费\n"
        "- 结合升级投诉倾向数据，评估退费用户的升级风险\n"
        "- 最后给出退费处理建议，包括流程优化、预警机制等\n"
        "- 使用具体数字支撑论点，但要融入自然语言叙述中\n"
        "- 语言表达要专业、流畅，符合商业分析报告的风格\n"
    )

    resp = llm.chat(
        [
            {"role": "system", "content": "你是一个投诉分析报告撰写助手。严格按照用户要求的格式输出，不要改变开头词语。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=1500,
    )
    if resp.used_fallback or not resp.content.strip():
        return []

    result_text = resp.content.strip()
    # Strip markdown code fences if present
    if result_text.startswith("```"):
        lines = result_text.split("\n")
        result_text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    if result_text and not result_text.startswith("退费诉求维度上"):
        result_text = "退费诉求维度上，" + result_text
    # Truncate at last complete sentence if output is excessively long
    if len(result_text) > 500:
        last_period = max(result_text.rfind("。"), result_text.rfind("；"), result_text.rfind("."))
        if last_period > 300:
            result_text = result_text[:last_period+1]
    result_lines = [result_text] if result_text else []
    logger.info("REFUND_LLM result_text_len=%s", len(result_text) if result_text else 0)
    return result_lines



def _fallback_narratives(result: dict[str, Any], llm=None) -> dict[str, list[str]]:
    labeled_total = result.get("total", 0)
    total = result.get("total_with_unlabeled", labeled_total)
    primary = _top(result.get("primary", []), 3)
    secondary = _top(result.get("secondary", []), 3)
    tertiary = _top(result.get("tertiary", []), 3)
    emotion = _top(result.get("emotion", []), 3)
    label_group = _top(result.get("label_group", []), 3)
    insight_dimension = _top(result.get("insight_dimension", []), 3)
    appeal = _top(result.get("customer_key_appeal", []), 3)
    cs_action = _top(result.get("cs_key_action", []), 3)
    operation_action = _top(result.get("operation_action", []), 3)
    member_cluster = _top(result.get("biz_member_cluster", []), 3)
    marketing_page = _top(result.get("marketing_activity_page", []), 3)
    marketing_status = _top(result.get("marketing_activity_match_status", []), 3)
    age_ranges = _top(result.get("age_ranges", []), 3)
    gender = _top(result.get("gender", []), 3)
    latent_need = _top(result.get("latent_need_examples", []), 3)
    avg_duration = result.get("avg_duration_minutes")
    daily = result.get("daily", [])
    peak_day = max(daily, key=lambda item: item.get("count", 0), default=None)
    neg_peak = max(daily, key=lambda item: item.get("negative_ratio", 0), default=None)
    anomalies = result.get("anomalies", [])
    cause_examples = result.get("top_tertiary_examples", [])[:3]
    matchdays = [day for day in daily if _matchday(day)]
    narratives = {key: [] for key in NARRATIVE_KEYS}
    narratives["unlabeled_distribution_summary"] = _unlabeled_distribution_summary(result)
    narratives["unlabeled_trend_summary"] = _unlabeled_trend_summary(result)
    if total:
        summary = [f"本周期共纳入 {_n(total)} 条用户投诉数据，核心问题集中在 {_join_items(tertiary, 3, total)}，需要优先围绕订购、退订、权益和赛事体验链路定位。", f"一级问题主要集中在 {_join_items(primary, 2, total)}，二级问题主要集中在 {_join_items(secondary, 2, total)}，用于快速判断资源优先级。"]
        if peak_day:
            summary.append(f"趋势峰值出现在 {peak_day['date']}，当日 {_n(peak_day.get('count', 0))} 件，峰值日主要问题为 {_join_items(peak_day.get('top_tertiary', []), 3)}。")
        narratives["executive_summary"] = summary
        # 并行执行3个独立的LLM分析（无依赖关系）
        biz_llm = []
        province_llm = []
        refund_llm = []
        if llm:
            with ThreadPoolExecutor(max_workers=3) as pool:
                fut_biz = pool.submit(_llm_business_dimension, result, llm, "distribution")
                fut_province = pool.submit(_llm_province_analysis, result, llm)
                fut_refund = pool.submit(_llm_refund_analysis, result, llm)
                try:
                    biz_llm = fut_biz.result(timeout=120) or []
                except Exception:
                    biz_llm = []
                try:
                    province_llm = fut_province.result(timeout=120) or []
                except Exception:
                    province_llm = []
                try:
                    refund_llm = fut_refund.result(timeout=120) or []
                except Exception:
                    refund_llm = []
        narratives["distribution_business_dimension"] = biz_llm
        narratives["distribution_conclusion"] = _distribution_conclusion_lines(result, biz_llm[0] if biz_llm else None)
        narratives["province_analysis"] = province_llm if province_llm else ["当前未提供省份维度的深入分析数据。"]
        narratives["refund_analysis"] = refund_llm if refund_llm else ["当前未提供退费诉求维度的深入分析数据。"]
    if primary:
        top_item = primary[0]
        narratives["primary_overview"] = [f"一级问题中 {top_item['key']}（共{_n(top_item['count'])}条，占比{_pct(top_item['count'], total)}）最集中。", f"一级问题整体呈现\u201c头部集中、其余分散\u201d的结构，前几类问题主要是 {_join_items(primary, 3, total)}。"]
    if secondary:
        top_item = secondary[0]
        narratives["secondary_overview"] = [f"二级问题中 {top_item['key']}（共{_n(top_item['count'])}条，占比{_pct(top_item['count'], total)}）最集中。", f"从二级问题集中度看，当前主要压力点落在 {_join_items(secondary, 3, total)} 这些具体业务环节。"]
    if tertiary:
        top_item = tertiary[0]
        narratives["tertiary_overview"] = [f"三级问题中 {top_item['key']}（共{_n(top_item['count'])}条，占比{_pct(top_item['count'], total)}）最集中。", f"三级问题更能直接反映用户痛点，当前高频问题主要集中在 {_join_items(tertiary, 3, total)}。"]
    if tertiary or insight_dimension:
        avg_text = f"，平均处理耗时约 {float(avg_duration):.1f} 分钟" if isinstance(avg_duration, (int, float)) and not math.isnan(float(avg_duration)) else ""
        narratives["journey_summary"] = [f"问题链路上，高频三级问题为 {_join_items(tertiary, 3)}，标签组集中在 {_join_items(label_group, 3)}，对应洞察维度集中在 {_join_items(insight_dimension, 3)}{avg_text}。", f"主诉求集中在 {_join_items(appeal, 2)}，客服动作集中在 {_join_items(cs_action, 2)}；应联动退费诉求、升级倾向和典型原声判断触发原因。"]
    else:
        narratives["journey_summary"] = ["当前未提取到足够的问题链路字段，无法形成稳定的归因摘要。"]
    if operation_action or latent_need:
        narratives["operation_need_summary"] = [f"运营举措中高频项为 {_join_items(operation_action, 3)}，相关隐性需求主要是 {_join_items(latent_need, 3)}。", f"营销活动页面和匹配状态线索分别集中在 {_join_items(marketing_page, 2)}、{_join_items(marketing_status, 2)}；若运营举措对应投诉量高，应进一步拆分活动告知、权益兑现、扣费退订、赛事体验四类原因。"]
    else:
        narratives["operation_need_summary"] = ["当前数据未提供有效运营举措或隐性需求字段，报告仅保留展示口径。"]
    if member_cluster:
        narratives["member_cluster_summary"] = [f"会员/业务聚类投诉最集中在 {_join_items(member_cluster, 3)}，可按会员类型拆分订购、退订、权益、赛事观看体验。", f"年龄段和性别分布可辅助识别客群差异，当前高频年龄段为 {_join_items(age_ranges, 2)}，性别分布为 {_join_items(gender, 2)}。"]
    else:
        narratives["member_cluster_summary"] = ["当前未提取到有效会员/业务聚类字段，无法按会员类型形成排序结论。"]
    top_evidence_labels = (result.get("tertiary_evidence") or {}).get("labels", [])
    md_evidence_labels = (result.get("tertiary_evidence_md") or {}).get("labels", [])
    cause_examples_src = top_evidence_labels or cause_examples
    if cause_examples_src:
        lines = []
        for item in cause_examples_src[:2]:
            appeals = _join_keys(item.get("top_appeals", []) or item.get("appeal_agg", []), 2)
            cs_actions = _join_keys(item.get("cs_action_agg", []), 2)
            reason = f"，客服主要处理动作是 {cs_actions}" if cs_actions != "无" else ""
            lines.append(f"围绕\u300c{item['key']}\u300d的诉求主要是 {appeals}{reason}，说明用户更关注退费、订购和权益处理等直接结果。")
        narratives["cause_summary"] = lines or ["当前未提取到足够的三级问题原因线索。"]
        first = cause_examples_src[0]
        narratives["voice_summary"] = [f"从用户原声看，\u300c{first['key']}\u300d相关投诉最密集，文本中重复出现退费、误订购、自动续费等明确诉求。", "建议结合原声样例判断问题属于资费争议、流程体验问题还是权益兑现问题，再决定优先治理顺序。"]
        narratives["case_summary"] = [f"典型案例优先关注「{first['key']}」相关样例，因其数量最高且常伴随明确诉求。", "案例阅读时建议同时看服务内容、客户关键诉求和三级标签路径，以判断问题属于资费争议、流程体验还是权益兑现。"]
    else:
        narratives["case_summary"] = ["当前未提取到可展示的典型案例样本。"]
    narratives["cause_voice_sample_summaries"] = _build_cause_voice_sample_summaries(cause_examples_src)
    narratives["tertiary_cause_detail"] = _build_tertiary_cause_detail(md_evidence_labels or top_evidence_labels, result)
    if peak_day and neg_peak:
        trend_lines = [f"{peak_day['date']} 的问题量达到峰值 {_n(peak_day['count'])} 件，是当前趋势上的最高波峰。", f"{neg_peak['date']} 的负向情绪占比最高，为 {neg_peak.get('negative_ratio', 0) * 100:.1f}%，说明该日用户情绪最激烈。"]
        biz_trend = _llm_business_dimension(result, llm, "trend") if llm else []
        if biz_trend:
            trend_lines.extend(biz_trend)
        else:
            trend_lines.extend(_trend_matchday_business_lines(result, daily))
    else:
        trend_lines = ["当前周期内未检测到有效趋势数据。"]
    narratives["trend_conclusion"] = trend_lines
    if anomalies:
        first = _sorted_anomaly_days(anomalies)[0]
        narratives["anomaly_summary"] = ["异动节点按日环比增幅、问题量和日期综合排序，报告仅展示最需要优先复盘的前三个节点。", f"排序最高的异动日为 {first['date']}，日环比 {first.get('day_over_day_growth', 0) * 100:.1f}%。"]
    else:
        narratives["anomaly_summary"] = ["当前周期未识别到满足阈值的明显异动日，整体波动相对平稳。"]
    narratives["trend_chart_summary"] = _build_trend_chart_summary_fallback(daily, matchdays, anomalies)
    narratives["trend_voice_summary"] = _build_trend_voice_summary_fallback(matchdays)
    narratives["trend_voice_sample_summaries"] = _build_trend_voice_sample_summaries(_trend_voice_examples(daily, anomalies))
    return narratives


def _extract_plain_messages(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []

    boilerplates = (
        "正在为您转接人工",
        "当前人工MM有点忙",
        "请稍后",
        "请耐心等待",
        "您好，很高兴为您服务",
        "请问有什么可以帮到您",
    )

    def _clean_message(message: Any, limit: int = 120) -> str:
        cleaned = re.sub(r"\s+", " ", str(message or ""))
        cleaned = re.sub(r"[A-Z0-9]{12,}", "", cleaned).strip(" ;；,，。")
        if len(cleaned) > limit:
            cleaned = cleaned[: limit - 1].rstrip() + "…"
        return cleaned

    def _is_boilerplate(message: str) -> bool:
        return any(marker in message for marker in boilerplates)

    def _collect_messages(payload: Any) -> tuple[list[str], list[str]]:
        user_msgs: list[str] = []
        other_msgs: list[str] = []
        if isinstance(payload, list):
            for item in payload:
                u, o = _collect_messages(item)
                user_msgs.extend(u)
                other_msgs.extend(o)
            return user_msgs, other_msgs
        if isinstance(payload, dict):
            message = _clean_message(
                payload.get("消息内容")
                or payload.get("message")
                or payload.get("content")
                or payload.get("工单内容")
                or payload.get("工单投诉内容")
            )
            sender = str(payload.get("发送方") or payload.get("sender") or "")
            if message and not _is_boilerplate(message):
                if "用户" in sender or "客户" in sender:
                    user_msgs.append(message)
                else:
                    other_msgs.append(message)
        return user_msgs, other_msgs

    parsed_messages: list[str] = []
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        payload = None
    if payload is not None:
        user_msgs, other_msgs = _collect_messages(payload)
        parsed_messages = user_msgs or other_msgs

    if not parsed_messages:
        for match in re.findall(r'["“\']?消息内容["”\']?\s*[:：]\s*["“\'](.*?)["”\']', text):
            cleaned = _clean_message(match)
            if cleaned and not _is_boilerplate(cleaned):
                parsed_messages.append(cleaned)

    if not parsed_messages:
        for match in re.findall(r'["“\']?工单投诉内容["”\']?\s*[:：]\s*["“\'](.*?)["”\']', text):
            cleaned = _clean_message(match)
            if cleaned and not _is_boilerplate(cleaned):
                parsed_messages.append(cleaned)

    if not parsed_messages and '"消息内容"' not in text and "“消息内容”" not in text:
        cleaned = _clean_message(text, limit=140)
        if cleaned and not _is_boilerplate(cleaned):
            parsed_messages.append(cleaned)

    messages = parsed_messages
    deduped = []
    seen = set()
    for message in messages:
        if message in seen:
            continue
        seen.add(message)
        deduped.append(message)
    return deduped


def _sample_summary(value: Any, issue: str = "") -> str:
    messages = _extract_plain_messages(value)
    if not messages:
        return "\u7528\u6237\u53cd\u9988\u4e3b\u8981\u6307\u5411\u76f8\u5173\u4e1a\u52a1\u529e\u7406\u6216\u89c2\u770b\u8fc7\u7a0b\u4e2d\u7684\u4f53\u9a8c\u963b\u65ad\u3002"
    combined = " ".join(messages[:3])
    points: list[str] = []
    if any(word in combined for word in ("\u9000\u8d39", "\u9000\u6b3e", "\u9000\u8ba2", "\u4e0d\u9000")):
        points.append("\u9000\u8ba2\u6216\u9000\u8d39\u5904\u7406\u7ed3\u679c\u4e0d\u7b26\u5408\u9884\u671f")
    if any(word in combined for word in ("\u7535\u89c6", "TV", "tv", "\u6295\u5c4f", "\u5927\u5c4f")):
        points.append("\u7535\u89c6\u7aef\u6216\u6295\u5c4f\u89c2\u770b\u6743\u76ca\u53d7\u963b")
    if any(word in combined for word in ("\u624b\u673a", "\u591a\u7aef", "\u56db\u5c4f", "\u4e92\u901a")):
        points.append("\u624b\u673a\u7aef\u4e0e\u7535\u89c6\u7aef\u6743\u76ca\u4e92\u901a\u89c4\u5219\u4e0d\u6e05")
    if any(word in combined for word in ("\u4ef7\u683c", "168", "219", "218", "258", "\u5957\u9910", "\u8865\u5dee")):
        points.append("\u5957\u9910\u4ef7\u683c\u548c\u6743\u76ca\u5dee\u5f02\u7406\u89e3\u6210\u672c\u9ad8")
    if any(word in combined for word in ("\u4f1a\u5458", "\u6743\u76ca", "\u5151\u6362", "\u94bb\u77f3")):
        points.append("\u4f1a\u5458\u6743\u76ca\u5151\u73b0\u4e0e\u7528\u6237\u9884\u671f\u5b58\u5728\u843d\u5dee")
    if any(word in combined for word in ("\u6263\u8d39", "\u8ba2\u8d2d", "\u8bef\u8d2d", "\u81ea\u52a8\u7eed\u8d39", "\u4e0d\u77e5\u60c5")):
        points.append("\u8ba2\u8d2d\u6263\u8d39\u6216\u81ea\u52a8\u7eed\u8d39\u6d41\u7a0b\u5f15\u53d1\u4e89\u8bae")
    if not points:
        points.append("\u76f8\u5173\u4e1a\u52a1\u529e\u7406\u6216\u89c2\u770b\u8fc7\u7a0b\u5b58\u5728\u4f53\u9a8c\u963b\u65ad")
    topic = f"\u300c{issue}\u300d" if issue else "\u8be5\u95ee\u9898"
    _sep = "\uff0c\u5e76\u4e14"
    return f"\u56f4\u7ed5{topic}\u7684\u7528\u6237\u53cd\u9988\uff0c\u4e3b\u8981\u96c6\u4e2d\u5728{_sep.join(dict.fromkeys(points[:3]))}\u3002"


def _build_cause_voice_sample_summaries(cause_examples: list[dict]) -> list[str]:
    summaries = []
    for item in cause_examples:
        samples = item.get("samples") or [{}]
        sample = samples[0] if samples else {}
        content = sample.get("content_excerpt", "") or sample.get("content_excerpt", "")
        cs_reply = sample.get("cs_reply_excerpt", "")
        issue = str(item.get("key") or item.get("issue") or "")
        if content:
            summaries.append(_sample_summary(content, issue))
        elif cs_reply:
            summaries.append(_sample_summary(cs_reply, issue))
        else:
            summaries.append("该问题的用户投诉主要集中在退订或退费处理结果与预期不符。")
    return summaries




def _recover_json_objects(raw: str) -> list[dict] | None:
    """Try to recover individual JSON objects from a malformed or truncated JSON array."""
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    # Find all top-level { ... } blocks in the array
    objects = []
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start >= 0:
                candidate = text[start:i+1]
                try:
                    obj = json.loads(candidate)
                    if isinstance(obj, dict) and obj.get("label"):
                        objects.append(obj)
                except (json.JSONDecodeError, TypeError):
                    pass
                start = -1
    return objects if objects else None


_LLM_DETAIL_FIELDS = (
    "content_summary",
    "cs_reply_summary",
    "customer_appeal_summary",
    "customer_keywords_summary",
    "cs_action_summary",
    "cs_keywords_summary",
    "root_cause",
)

_RAW_DIALOG_TOKENS = (
    "发送方",
    "消息内容",
    "[{",
    "}]",
    "/impng/",
    "子公司流水",
    "支付流水",
    "故此单归档",
)

_REASONING_META_TOKENS = (
    "思考过程",
    "分析步骤",
    "我的思路",
    "我将先",
    "让我先",
    "下面我来",
    "先分析",
    "逐步分析",
    "步骤如下",
)

_TEMPLATE_BAN_PHRASES = (
    "样例中，用户围绕",
    "样本显示，大多数用户",
    "用户普遍投诉",
)


def _compact_text(value: Any, max_len: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def _looks_like_raw_dialogue(value: Any) -> bool:
    text = str(value or "")
    if not text.strip():
        return False
    return any(token in text for token in _RAW_DIALOG_TOKENS)


def _looks_like_reasoning_meta(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    head = text[:120]
    if any(token in head for token in _REASONING_META_TOKENS):
        return True
    return bool(re.search(r"^(好的|我来|我将|下面|先)(分析|说明|总结|判断)", head))


def _looks_like_template_phrase(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return any(phrase in text for phrase in _TEMPLATE_BAN_PHRASES)


def _normalize_llm_detail_item(item: dict[str, Any], expected_label: str) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "label": str(item.get("label") or expected_label).strip(),
        "count": int(item.get("count", 0) or 0),
        "share": str(item.get("share", "")).strip(),
    }
    for field in _LLM_DETAIL_FIELDS:
        max_len = 140 if field in {"customer_keywords_summary", "cs_keywords_summary", "root_cause"} else 260
        text = _compact_text(item.get(field, ""), max_len=max_len)
        if not text:
            raise RuntimeError(f"LLM REDUCE 返回空字段: label={expected_label}, field={field}")
        if _looks_like_raw_dialogue(text):
            raise RuntimeError(f"LLM REDUCE 返回原始会话内容: label={expected_label}, field={field}")
        if _looks_like_reasoning_meta(text):
            raise RuntimeError(f"LLM REDUCE 返回思考过程文本: label={expected_label}, field={field}")
        if _looks_like_template_phrase(text):
            raise RuntimeError(f"LLM REDUCE 返回模板化文本: label={expected_label}, field={field}")
        normalized[field] = text
    return normalized


def _synthesize_root_cause(label: str, appeal_agg: list, cs_action_agg: list) -> str:
    """Synthesize a root cause sentence from appeal labels and CS actions, without LLM."""
    parts = []
    # Extract core appeal patterns
    top_appeals = [a.get("key", "") for a in (appeal_agg or [])[:3] if a.get("key")]
    if top_appeals:
        parts.append("用户核心诉求集中在" + "、".join(top_appeals))
    # Extract CS action patterns
    top_actions = [a.get("key", "") for a in (cs_action_agg or [])[:2] if a.get("key")]
    if top_actions:
        parts.append("客服侧主要通过" + "、".join(top_actions) + "应对")
    # Synthesize with label context
    if label:
        label_short = label.replace("争议", "").replace("困难", "难")[:12]
        if "退款" in label or "退费" in label or "退订" in label:
            parts.append("根因指向付费/退订流程设计与用户预期脱节")
        elif "权益" in label:
            parts.append("根因指向权益规则复杂或宣传与兑现不一致")
        elif "体验" in label or "差异" in label:
            parts.append("根因指向多端产品设计不一致")
        elif "订购" in label:
            parts.append("根因指向订购流程透明度不足或引导设计有缺陷")
        elif "回看" in label or "播放" in label:
            parts.append("根因指向功能限制或技术能力与用户预期不符")
        else:
            parts.append("根因指向" + label_short + "环节的产品或流程设计问题")
    if not parts:
        return "需进一步分析具体服务记录以确定根因。"
    return "；".join(parts) + "。"


def _build_tertiary_cause_detail(evidence_labels, result):
    """Per-label cause analysis from evidence samples."""
    if not evidence_labels:
        return []
    detail = []
    for label_data in evidence_labels:
        samples = label_data.get("samples", [])
        contents = [s.get("content_excerpt", "") for s in samples if s.get("content_excerpt")]
        cs_replies = [s.get("cs_reply_excerpt", "") for s in samples if s.get("cs_reply_excerpt")]
        appeals = [s.get("customer_key_appeal", "") for s in samples if s.get("customer_key_appeal")]
        app_kw = [s.get("customer_keywords", "") for s in samples if s.get("customer_keywords")]
        cs_acts = [s.get("cs_key_action", "") for s in samples if s.get("cs_key_action")]
        cs_kw = [s.get("cs_keywords", "") for s in samples if s.get("cs_keywords")]
        appeal_agg = label_data.get("appeal_agg", [])
        cs_action_agg = label_data.get("cs_action_agg", [])

        def _deduped(items, limit=5):
            seen = set()
            result = []
            for item in items:
                if item not in seen and item.strip():
                    seen.add(item)
                    result.append(item)
                    if len(result) >= limit:
                        break
            return result

        content_summaries = [_sample_summary(content, label_data["key"]) for content in contents[:5] if str(content).strip()]
        reply_summaries = []
        for reply in cs_replies[:5]:
            messages = _extract_plain_messages(reply)
            if messages:
                reply_summaries.append("；".join(messages[:2]))
            else:
                cleaned = re.sub(r"\s+", " ", str(reply)).strip(" ;；,，。")
                if cleaned:
                    reply_summaries.append(cleaned[:100] + ("…" if len(cleaned) > 100 else ""))

        def _short_items(items: list[str], limit: int = 5, max_len: int = 80) -> list[str]:
            compact = []
            for item in items:
                text = re.sub(r"\s+", " ", str(item or "")).strip(" ;；,，。")
                if not text:
                    continue
                if len(text) > max_len:
                    text = text[: max_len - 1].rstrip() + "…"
                compact.append(text)
            return _deduped(compact, limit=limit)

        # Synthesize root_cause from appeal aggregation and label key
        root_cause = _synthesize_root_cause(label_data["key"], appeal_agg, cs_action_agg)
        detail.append({
            "label": label_data["key"],
            "count": label_data["count"],
            "share": f"{label_data.get('share', 0) * 100:.1f}%",
            "content_summary": "\uff1b".join(_deduped(content_summaries, 3)) or "暂无",
            "cs_reply_summary": "\uff1b".join(_deduped(reply_summaries, 3)) or "暂无",
            "customer_appeal_summary": "\uff1b".join(_short_items(appeals, limit=5, max_len=80)) or "暂无",
            "customer_keywords_summary": "\uff1b".join(_short_items(app_kw, limit=5, max_len=60)) or "暂无",
            "cs_action_summary": "\uff1b".join(_short_items(cs_acts, limit=5, max_len=80)) or "暂无",
            "cs_keywords_summary": "\uff1b".join(_short_items(cs_kw, limit=5, max_len=60)) or "暂无",
            "root_cause": root_cause,
            "appeal_agg": appeal_agg,
            "cs_action_agg": cs_action_agg,
        })
    return detail


def _summary_char_len(text: str) -> int:
    cleaned = re.sub(r"\s+", "", text or "")
    cleaned = cleaned.replace("分析小结：", "").replace("分析小结:", "")
    return len(cleaned)


def _normalize_llm_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _user_voice_soft_validation_error(value: str) -> str:
    text = value.strip()
    if text.endswith(("...", "…")):
        return "典型用户原话以省略号结尾"
    length = _summary_char_len(text)
    if length < 100 or length > 150:
        return f"典型用户原话长度{length}字，需100-150字"
    return ""


def _trim_summary_to_max_chars(text: str, max_chars: int = 320) -> str:
    if _summary_char_len(text) <= max_chars:
        return text
    prefix = "分析小结："
    body = text
    if text.startswith("分析小结："):
        body = text[len("分析小结：") :]
    elif text.startswith("分析小结:"):
        body = text[len("分析小结:") :]
    body = re.sub(r"\s+", "", body)
    if len(body) <= max_chars:
        return prefix + body
    clipped = body[:max_chars]
    cut = max(clipped.rfind("。"), clipped.rfind("；"), clipped.rfind("，"))
    if cut >= 210:
        clipped = clipped[: cut + 1]
    return prefix + clipped


def _fit_primary_summary_with_fixed_top3(prefix: str, body: str, max_chars: int = 320) -> str:
    """Keep the canonical Top3 sentence intact and only trim the LLM continuation."""
    prefix = re.sub(r"\s+", "", prefix or "")
    body = re.sub(r"\s+", "", body or "")
    body = re.sub(r"^分析小结[:：]?", "", body)
    if body.startswith(prefix):
        body = body[len(prefix) :]
    body = body.lstrip("。；，,:：")
    available = max_chars - _summary_char_len(prefix)
    if available <= 0:
        return prefix
    if len(body) > available:
        clipped = body[:available]
        cut = max(clipped.rfind("。"), clipped.rfind("；"), clipped.rfind("，"))
        if cut >= max(40, available // 2):
            clipped = clipped[: cut + 1]
        body = clipped
    return prefix + body


def _share_variants(share_text: str) -> list[str]:
    text = str(share_text or "").strip()
    if not text:
        return []
    variants = {text}
    numeric = text.replace("%", "").strip()
    try:
        value = float(numeric)
    except ValueError:
        return list(variants)
    variants.add(f"{value:.1f}%")
    variants.add(f"{int(round(value))}%")
    variants.add(f"{int(value)}%")
    return [v for v in variants if v]


def _validate_primary_summary(summary: str, top3_items: list[dict]) -> tuple[bool, str]:
    text = (summary or "").strip()
    if not text:
        return False, "一级小结为空"
    if _looks_like_raw_dialogue(text):
        return False, "一级小结包含原始工单文本"
    if _looks_like_reasoning_meta(text):
        return False, "一级小结包含思考过程文本"
    if _looks_like_template_phrase(text):
        return False, "一级小结仍为模板句"
    length = _summary_char_len(text)
    if length < 220 or length > 320:
        return False, f"一级小结长度不在 220-320 字范围内（当前 {length}）"
    for item in top3_items[:3]:
        label = str(item.get("key", "")).strip()
        count = int(item.get("count", 0) or 0)
        share = str(item.get("share", "")).strip()
        if label and label not in text:
            return False, f"一级小结缺少 TOP3 标签名：{label}"
        if count > 0 and str(count) not in text:
            return False, f"一级小结缺少 TOP3 条数：{label}/{count}"
        if share:
            variants = _share_variants(share)
            if variants and not any(v in text for v in variants):
                return False, f"一级小结缺少 TOP3 占比：{label}/{share}"
    return True, ""


def _llm_get_text_with_prompt_variants(
    llm,
    prompt_variants: list[str],
    temperature: float,
    max_tokens: int,
    timeout_seconds: int,
    max_retries: int,
    label: str = "",
    reject_reasoning_meta: bool = True,
) -> str:
    last_text = ""
    bounded_variants = prompt_variants[:2]
    for idx, prompt in enumerate(bounded_variants, start=1):
        if label:
            logger.info("LLM variant request label=%s attempt=%s/%s", label, idx, len(bounded_variants))
        resp = llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )
        text = resp.content.strip() if (not resp.used_fallback and resp.content) else ""
        last_text = text or last_text
        if text and ((not reject_reasoning_meta) or (not _looks_like_reasoning_meta(text))):
            if label:
                logger.info("LLM variant accepted label=%s attempt=%s/%s", label, idx, len(bounded_variants))
            return text
        if label:
            reason = "empty" if not text else "reasoning_meta"
            logger.info("LLM variant rejected label=%s attempt=%s/%s reason=%s", label, idx, len(bounded_variants), reason)
    return last_text


def _build_tertiary_cause_detail_llm(evidence_labels: list[dict], llm) -> list[dict]:
    if not evidence_labels:
        raise RuntimeError("缺少三级标签证据，无法生成三级小结。")
    if not llm or not llm.enabled or not getattr(llm, "report_enabled", False):
        raise RuntimeError("三级小结需要 LLM，但当前未启用。")

    details: list[dict] = []
    total_labels = len(evidence_labels)

    def _single_label(label_data: dict, position: int) -> dict:
        label = str(label_data.get("key", "")).strip()
        count = int(label_data.get("count", 0) or 0)
        share = f"{float(label_data.get('share', 0) or 0) * 100:.1f}%"
        samples = label_data.get("samples", [])[:6]
        if not label:
            raise RuntimeError("三级标签缺少 label key。")
        logger.info("tertiary llm start [%s/%s] label=%s", position, total_labels, label)

        content_samples = []
        cs_reply_samples = []
        for sample in samples:
            content = _compact_text(sample.get("content_excerpt", ""), max_len=180)
            cs_reply = _compact_text(sample.get("cs_reply_excerpt", ""), max_len=180)
            if content:
                content_samples.append(content)
            if cs_reply:
                cs_reply_samples.append(cs_reply)
        top_appeals = "、".join(str(item.get("key", "")).strip() for item in label_data.get("appeal_agg", [])[:3] if str(item.get("key", "")).strip())
        top_actions = "、".join(str(item.get("key", "")).strip() for item in label_data.get("cs_action_agg", [])[:3] if str(item.get("key", "")).strip())
        prompt = (
            "你是客服体验分析助手。请基于以下数据，输出严格 JSON（不要 markdown 代码块）：\n"
            "{\n"
            '  "content_summary": "...",\n'
            '  "cs_reply_summary": "...",\n'
            '  "root_cause": "...",\n'
            '  "user_voice_natural": "..."\n'
            "}\n\n"
            f"三级标签：{label}\n"
            f"问题量：{count}，占该一级问题比例：{share}\n"
            f"高频诉求：{top_appeals or '暂无'}\n"
            f"客服处理动作：{top_actions or '暂无'}\n"
            f"用户内容样本：{'；'.join(content_samples) or '暂无'}\n"
            f"客服回复样本：{'；'.join(cs_reply_samples) or '暂无'}\n\n"
            "写作要求：\n"
            "1) content_summary：80-140字，归纳用户问题与场景，不得复述原文。\n"
            "2) cs_reply_summary：80-140字，归纳客服处理方式与共性。\n"
            "3) root_cause：50-100字，给出业务根因判断。\n"
            "4) user_voice_natural：100-150字，自然转述用户原话，并穿插1-2个短引语（不超过12字/条），不要模板句。\n"
            "5) user_voice_natural 必须是完整句子，不要以省略号结尾，不要用“...”或“…”表示未完。\n"
            "6) 严禁输出“样例中，用户围绕…”。\n"
            "7) 严禁输出原始 JSON/工单流水字段（如发送方、消息内容、子公司流水）。\n"
            "8) 只输出 JSON 对象本身。"
        )
        prompt_variants = [
            prompt,
            prompt + "\n\n上一轮输出不合规，请补齐全部字段并严格返回 JSON 对象；特别是 user_voice_natural 必须为100-150字完整句，不能以省略号结尾，不能使用“...”或“…”表示未完。",
        ]
        parsed: dict[str, Any] | None = None
        content_summary = ""
        cs_reply_summary = ""
        root_cause = ""
        user_voice_natural = ""
        last_error = "未知错误"
        for attempt_idx, variant_prompt in enumerate(prompt_variants, start=1):
            text = _llm_get_text_with_prompt_variants(
                llm=llm,
                prompt_variants=[variant_prompt],
                temperature=0.2,
                max_tokens=min(getattr(llm, "report_max_tokens", 4000), 900),
                timeout_seconds=max(60, min(getattr(llm, "report_timeout", 60), 75)),
                max_retries=1,
                label=f"tertiary:{label}",
                reject_reasoning_meta=False,
            )
            if not text:
                last_error = "空输出"
                continue
            try:
                parsed_candidate = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                parsed_candidate = parse_json_object(text)
            if not isinstance(parsed_candidate, dict):
                last_error = "非 JSON 输出"
                continue

            content_summary = _compact_text(parsed_candidate.get("content_summary", ""), max_len=260)
            cs_reply_summary = _compact_text(parsed_candidate.get("cs_reply_summary", ""), max_len=260)
            root_cause = _compact_text(parsed_candidate.get("root_cause", ""), max_len=180)
            user_voice_natural = _normalize_llm_text(parsed_candidate.get("user_voice_natural", ""))
            candidate_ok = True
            for field_name, field_value in [
                ("content_summary", content_summary),
                ("cs_reply_summary", cs_reply_summary),
                ("root_cause", root_cause),
                ("user_voice_natural", user_voice_natural),
            ]:
                if not field_value:
                    last_error = f"字段为空：{field_name}"
                    candidate_ok = False
                    break
                if _looks_like_reasoning_meta(field_value):
                    last_error = f"思考过程文本：{field_name}"
                    candidate_ok = False
                    break
                if _looks_like_raw_dialogue(field_value):
                    last_error = f"原始工单文本：{field_name}"
                    candidate_ok = False
                    break
                if _looks_like_template_phrase(field_value):
                    last_error = f"模板句：{field_name}"
                    candidate_ok = False
                    break
            if candidate_ok:
                soft_error = _user_voice_soft_validation_error(user_voice_natural)
                if soft_error and attempt_idx < len(prompt_variants):
                    last_error = soft_error
                    candidate_ok = False
                else:
                    parsed = parsed_candidate
                    if soft_error:
                        logger.warning(
                            "tertiary llm accepted with soft validation issue [%s/%s] label=%s attempt=%s/2 reason=%s",
                            position,
                            total_labels,
                            label,
                            attempt_idx,
                            soft_error,
                        )
                    else:
                        logger.info("tertiary llm validated [%s/%s] label=%s attempt=%s/2", position, total_labels, label, attempt_idx)
                    break
            logger.info("tertiary llm candidate rejected [%s/%s] label=%s attempt=%s/2 reason=%s", position, total_labels, label, attempt_idx, last_error)

        if not parsed:
            raise RuntimeError(f"三级标签小结失败：{label}（{last_error}）")

        detail = {
            "label": label,
            "count": count,
            "share": share,
            "content_summary": content_summary,
            "cs_reply_summary": cs_reply_summary,
            "root_cause": root_cause,
            "user_voice_natural": user_voice_natural,
            "customer_appeal_summary": _compact_text(parsed.get("customer_appeal_summary", ""), max_len=220),
            "customer_keywords_summary": _compact_text(parsed.get("customer_keywords_summary", ""), max_len=180),
            "cs_action_summary": _compact_text(parsed.get("cs_action_summary", ""), max_len=220),
            "cs_keywords_summary": _compact_text(parsed.get("cs_keywords_summary", ""), max_len=180),
            "appeal_agg": label_data.get("appeal_agg", []),
            "cs_action_agg": label_data.get("cs_action_agg", []),
        }
        logger.info("tertiary llm done [%s/%s] label=%s", position, total_labels, label)
        return detail

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            pool.submit(_single_label, label_data, idx)
            for idx, label_data in enumerate(evidence_labels, start=1)
        ]
        for future in as_completed(futures):
            details.append(future.result(timeout=180))

    # keep stable display order
    by_label = {item["label"]: item for item in details}
    ordered = []
    for item in evidence_labels:
        key = str(item.get("key", "")).strip()
        if key not in by_label:
            raise RuntimeError(f"三级标签小结缺失：{key}")
        ordered.append(by_label[key])
    return ordered


def _build_primary_overall_evaluation(result: dict, primary_summaries: list[dict], llm) -> list[str]:
    if not llm or not llm.enabled or not getattr(llm, "report_enabled", False):
        raise RuntimeError("一级标签综合评价需要 LLM，但当前未启用。")
    primary_top = "、".join(
        f"{item.get('key', '')}（{_n(item.get('count', 0))}条，占比{_pct(item.get('count', 0), result.get('total_with_unlabeled', result.get('total', 0)))}）"
        for item in (result.get("primary", []) or [])[:4]
        if item.get("key")
    )
    summary_inputs = "；".join(_compact_text(item.get("summary", ""), max_len=180) for item in primary_summaries[:4] if item.get("summary"))
    prompt = (
        "你是业务分析报告撰写人。请输出2段“一级标签综合评价”，每段130-220字，整体要偏业务复盘口吻。\n"
        "输出严格 JSON：{\"paragraphs\": [\"第一段\", \"第二段\"]}\n\n"
        f"一级标签分布：{primary_top}\n"
        f"一级标签小结输入：{summary_inputs}\n\n"
        "要求：\n"
        "1) 只写总体态势与治理节奏，不要写条目式优化建议。\n"
        "2) 禁止出现“优化建议：”“【立即优化】”“建议1/2/3”。\n"
        "3) 不要重复同一句话，不要模板腔。\n"
        "4) 仅输出 JSON。"
    )
    text = _llm_get_text_with_prompt_variants(
        llm=llm,
        prompt_variants=[
            prompt,
            prompt + "\n\n上一轮不合规，请严格返回2段JSON。",
        ],
        temperature=0.25,
        max_tokens=min(getattr(llm, "report_max_tokens", 4000), 900),
        timeout_seconds=max(60, min(getattr(llm, "report_timeout", 60), 75)),
        max_retries=1,
        label="primary_overall_evaluation",
        reject_reasoning_meta=False,
    )
    if not text:
        raise RuntimeError("一级标签综合评价 LLM 失败：空输出。")
    parsed = None
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        parsed = parse_json_object(text)
    if not isinstance(parsed, dict):
        raise RuntimeError("一级标签综合评价 LLM 输出非 JSON。")
    paragraphs = parsed.get("paragraphs")
    if not isinstance(paragraphs, list) or len(paragraphs) < 2:
        raise RuntimeError("一级标签综合评价 LLM 输出段落不足2段。")
    cleaned = []
    for paragraph in paragraphs[:2]:
        text_line = _compact_text(paragraph, max_len=360)
        if not text_line:
            raise RuntimeError("一级标签综合评价出现空段落。")
        if _looks_like_reasoning_meta(text_line):
            raise RuntimeError("一级标签综合评价出现思考过程文本。")
        if _looks_like_raw_dialogue(text_line):
            raise RuntimeError("一级标签综合评价出现原始工单文本。")
        if "优化建议" in text_line or "立即优化" in text_line:
            raise RuntimeError("一级标签综合评价出现禁用模板话术。")
        cleaned.append(text_line)
    normalized_a = re.sub(r"[，。；：、\s]", "", cleaned[0])
    normalized_b = re.sub(r"[，。；：、\s]", "", cleaned[1])
    if normalized_a and normalized_b and (normalized_a == normalized_b or normalized_a in normalized_b or normalized_b in normalized_a):
        raise RuntimeError("一级标签综合评价两段内容重复度过高。")
    return cleaned

def _build_trend_voice_sample_summaries(matchdays: list[dict]) -> list[str]:
    summaries = []
    for day in matchdays[:3]:
        samples = day.get("samples") or []
        sample_text = "\uff1b".join(_sample_summary(sample.get("content_excerpt", ""), _join_keys(day.get("top_tertiary", []), 1)) for sample in samples[:2] if sample.get("content_excerpt"))
        summaries.append(sample_text or "\u8be5\u8d5b\u4e8b\u65e5\u6837\u4f8b\u4e3b\u8981\u53cd\u6620\u7528\u6237\u5728\u6bd4\u8d5b\u524d\u540e\u96c6\u4e2d\u54a8\u8be2\u548c\u53cd\u9988\u89c2\u770b\u3001\u8ba2\u8d2d\u6216\u6743\u76ca\u5904\u7406\u95ee\u9898\u3002")
    return summaries


def _build_trend_chart_summary_fallback(daily: list[dict], matchdays: list[dict], anomalies: list[dict]) -> list[str]:
    if not daily:
        return ["\u5f53\u524d\u8d8b\u52bf\u7a97\u53e3\u5185\u65e0\u53ef\u7ed8\u5236\u7684\u6bcf\u65e5\u8d8b\u52bf\u6570\u636e\u3002"]
    peak = max(daily, key=lambda item: item.get("count", 0))
    neg_peak = max(daily, key=lambda item: item.get("negative_ratio", 0))
    lines = [f"\u6298\u7ebf\u56fe\u663e\u793a\u95ee\u9898\u91cf\u5cf0\u503c\u51fa\u73b0\u5728 {peak['date']}\uff0c\u5f53\u65e5\u63d0\u53ca {_n(peak['count'])} \u4ef6\u3002", f"\u8d1f\u5411\u60c5\u7eea\u5360\u6bd4\u6700\u9ad8\u65e5\u4e3a {neg_peak['date']}\uff0c\u5360\u6bd4 {_pct(neg_peak.get('negative_ratio', 0), 1.0)}\u3002"]
    if matchdays and len(matchdays) > 1:
        matchday_total = sum(d.get("count", 0) for d in matchdays)
        lines.append(f"\u8d5b\u4e8b\u65e5\u5408\u8ba1\u63d0\u53ca {matchday_total} \u4ef6\uff0c\u6bd4\u8d5b\u524d\u540e\u7684\u54a8\u8be2\u3001\u9000\u8ba2\u548c\u6743\u76ca\u53cd\u9988\u66f4\u5bb9\u6613\u5f62\u6210\u96c6\u4e2d\u6ce2\u52a8\u3002")
    if anomalies:
        strongest = max(anomalies, key=lambda item: item.get("day_over_day_growth", 0))
        lines.append(f"\u5f02\u52a8\u4e2d\u589e\u5e45\u6700\u9ad8\u8282\u70b9\u4e3a {strongest['date']}\uff0c\u65e5\u73af\u6bd4 {_pct(strongest.get('day_over_day_growth', 0), 1.0)}\u3002")
    return lines


def _build_trend_voice_summary_fallback(matchdays: list[dict]) -> list[str]:
    if not matchdays:
        return ["\u5f53\u524d\u8d8b\u52bf\u7a97\u53e3\u5185\u672a\u63d0\u53d6\u5230\u5e26\u8d5b\u4e8b\u65e5\u6807\u6ce8\u7684\u6837\u4f8b\u539f\u58f0\u3002"]
    lead = max(matchdays, key=lambda item: int(item.get("count", 0) or 0))
    lead_issues = "\u3001".join(item.get("key", "") for item in lead.get("top_tertiary", [])[:3] if item.get("key")) or "\u65e0"
    return [f"\u8d5b\u4e8b\u65e5\u6837\u4f8b\u4e2d\uff0c{lead['date']} \u7684\u6295\u8bc9\u6700\u96c6\u4e2d\uff0c\u5171 {_n(lead['count'])} \u4ef6\uff1b\u76f8\u5173\u539f\u58f0\u4e3b\u8981\u56f4\u7ed5 {lead_issues} \u5c55\u5f00\u3002", "\u4ece\u8d5b\u4e8b\u65e5\u539f\u58f0\u770b\uff0c\u7528\u6237\u66f4\u5bb9\u6613\u5728\u6bd4\u8d5b\u524d\u540e\u96c6\u4e2d\u53cd\u9988\u9000\u8ba2\u3001\u6743\u76ca\u5151\u6362\u3001\u8ba2\u8d2d\u5931\u8d25\u548c\u8986\u76d6\u8303\u56f4\u7b49\u5373\u65f6\u4f53\u9a8c\u95ee\u9898\u3002"]



def _analyze_dimensions(evidence_labels: list[dict], llm) -> dict[str, dict[str, str]]:
    """MAP phase: analyze each of 6 dimensions for each label in parallel."""
    if not evidence_labels:
        raise RuntimeError("LLM MAP 缺少 evidence_labels，无法生成维度分析。")
    if not llm or not llm.enabled:
        raise RuntimeError("LLM MAP 需要启用 LLM，但当前未启用。")
    logger.info("MAP: analyzing %s labels x %s dimensions with ThreadPoolExecutor",
                len(evidence_labels), len(REQUIRED_MAP_DIMS))

    def _prepare_dim_text(raw_value: Any, dim: str) -> str:
        raw_text = str(raw_value or "").strip()
        if not raw_text:
            return ""
        if dim in {"content", "cs_reply"}:
            messages = _extract_plain_messages(raw_text)
            if messages:
                return _compact_text("；".join(messages[:3]), max_len=240)
        return _compact_text(raw_text, max_len=240)

    tasks = []
    for label_data in evidence_labels[:5]:
        label = label_data["key"]
        samples = label_data.get("samples", [])
        for dim in REQUIRED_MAP_DIMS:
            field = DIMENSION_FIELDS[dim]
            texts = [_prepare_dim_text(s.get(field, ""), dim) for s in samples]
            texts = [t for t in texts if t]
            count = len(texts)
            if not texts:
                continue
            joined = "\n---\n".join(texts)
            prompt = DIM_PROMPTS[dim].format(label=label, texts=joined, count=count)
            tasks.append((label, dim, prompt))

    if not tasks:
        logger.warning("MAP: no tasks generated (empty evidence?)")
        return {}

    results: dict[str, dict[str, str]] = {}
    # Initialize all label->dim slots
    for ld in evidence_labels[:5]:
        results[ld["key"]] = {}

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_map = {
            pool.submit(llm.chat, [
                {"role": "user", "content": prompt}
            ], temperature=0.1, max_tokens=300, timeout_seconds=max(getattr(llm, "report_timeout", 60), 120), max_retries=max(2, getattr(llm, "report_max_retries", 1))): (label, dim, prompt)
            for label, dim, prompt in tasks
        }
        for fut in as_completed(fut_map):
            label, dim, prompt = fut_map[fut]
            try:
                resp = fut.result()
                summary_raw = ""
                base_candidates = [
                    prompt,
                    prompt + "\n\n请务必返回非空总结，不要返回空字符串，不要输出思考过程。",
                    prompt + "\n\n上一轮输出为空或含思考过程。请直接输出 1 段 80-150 字结论，禁止输出“首先/我需要/用户请求”等思路文本。",
                ]
                candidates = base_candidates + [base_candidates[-1]] * 7
                for idx, candidate_prompt in enumerate(candidates):
                    candidate_text = resp.content.strip() if (not resp.used_fallback and resp.content) else ""
                    if candidate_text and (not _looks_like_reasoning_meta(candidate_text)):
                        summary_raw = candidate_text
                        break
                    resp = llm.chat(
                        [{"role": "user", "content": candidate_prompt}],
                        temperature=0.1,
                        max_tokens=300,
                        timeout_seconds=max(getattr(llm, "report_timeout", 60), 120),
                        max_retries=max(2, getattr(llm, "report_max_retries", 1)),
                    )
                    if idx < len(candidates) - 1:
                        continue
                    candidate_text = resp.content.strip() if (not resp.used_fallback and resp.content) else ""
                    if candidate_text and (not _looks_like_reasoning_meta(candidate_text)):
                        summary_raw = candidate_text
                        break
                if not summary_raw:
                    raise RuntimeError(f"LLM MAP 调用失败: label={label}, dim={dim}")
                summary = _compact_text(summary_raw, max_len=320)
                if _looks_like_raw_dialogue(summary):
                    raise RuntimeError(f"LLM MAP 返回原始会话文本: label={label}, dim={dim}")
                if _looks_like_reasoning_meta(summary):
                    raise RuntimeError(f"LLM MAP 返回思考过程文本: label={label}, dim={dim}")
            except Exception as exc:
                logger.error("MAP call failed label=%s dim=%s error=%s", label, dim, exc)
                raise RuntimeError(f"LLM MAP 失败: label={label}, dim={dim}, error={exc}") from exc
            results[label][dim] = summary

    logger.info("MAP: completed %s/%s tasks", len(tasks), len(tasks))
    return results



def _sanitize_lines(parsed: dict[str, Any], fallback: dict[str, list[str]]) -> dict[str, list[str]]:
    cleaned: dict[str, list[str]] = {}
    unlabeled_markers = ("\u672a\u6807\u6ce8\u4e00\u4e8c\u4e09\u7ea7\u6807\u7b7e", "\u4e00/\u4e8c/\u4e09\u7ea7\u6807\u7b7e\u672a\u6807\u6ce8", "\u672a\u6807\u6ce8\u5de5\u5355", "\u672a\u6807\u6ce8\u6570\u636e")
    for key in NARRATIVE_KEYS:
        value = parsed.get(key)
        if key == "tertiary_cause_detail":
            if isinstance(value, list) and len(value) > 0:
                if isinstance(value[0], dict) and "label" in value[0]:
                    cleaned[key] = value
                else:
                    cleaned[key] = fallback.get(key, [])
            else:
                cleaned[key] = fallback.get(key, [])
            continue
        if isinstance(value, list):
            lines = [str(item).strip() for item in value if str(item).strip()]
            if key in {"distribution_conclusion", "trend_conclusion"}:
                lines = [line for line in lines if not any(marker in line for marker in unlabeled_markers)]
            if not lines:
                cleaned[key] = fallback[key]
            elif key == "distribution_conclusion":
                cleaned[key] = lines[:6]
            else:
                cleaned[key] = lines[:4]
        else:
            cleaned[key] = fallback[key]
    return cleaned


def build_report_narratives(result: dict[str, Any], llm: OpenAICompatibleClient) -> dict[str, list[str]]:
    narrative_start = time.perf_counter()
    narratives = _fallback_narratives(result, None)
    if not llm.enabled or not getattr(llm, "report_enabled", False):
        raise RuntimeError("报告生成要求启用 LLM（LLM_REPORT_ENABLED=true 且 API KEY 可用），当前未满足。")

    evidence_labels = (result.get("tertiary_evidence") or {}).get("labels", [])
    if not evidence_labels:
        raise RuntimeError("未获取到三级标签证据，无法生成 LLM 小结。")
    md_evidence_labels = (result.get("tertiary_evidence_md") or {}).get("labels", [])
    if not md_evidence_labels:
        raise RuntimeError("未获取到 MD 分章三级标签证据，无法生成报告。")

    tertiary_timeout = min(600, max(300, len(md_evidence_labels) * 20))
    with ThreadPoolExecutor(max_workers=5) as pool:
        fut_exec = pool.submit(_build_executive_summary, result, llm)
        fut_distribution_business = pool.submit(_build_distribution_business_dimension, result, llm)
        fut_primary = pool.submit(_build_primary_level_summaries, result, llm)
        fut_case = pool.submit(_build_typical_case_deep_dive, result, evidence_labels, llm)
        fut_tertiary = pool.submit(_build_tertiary_cause_detail_llm, md_evidence_labels, llm)
        stage_t0 = time.perf_counter()
        narratives["executive_summary"] = fut_exec.result(timeout=180)
        logger.info("narrative stage done: executive_summary elapsed=%.2fs", time.perf_counter() - stage_t0)
        stage_t0 = time.perf_counter()
        distribution_business = fut_distribution_business.result(timeout=180)
        narratives["distribution_business_dimension"] = [distribution_business]
        narratives["distribution_conclusion"] = _distribution_conclusion_lines(result, distribution_business)
        logger.info("narrative stage done: distribution_business_dimension elapsed=%.2fs", time.perf_counter() - stage_t0)
        stage_t0 = time.perf_counter()
        narratives["primary_summaries"] = fut_primary.result(timeout=180) or []
        logger.info("narrative stage done: primary_summaries elapsed=%.2fs", time.perf_counter() - stage_t0)
        stage_t0 = time.perf_counter()
        narratives["typical_case_deep_dive"] = fut_case.result(timeout=180) or []
        logger.info("narrative stage done: typical_case_deep_dive elapsed=%.2fs", time.perf_counter() - stage_t0)
        stage_t0 = time.perf_counter()
        narratives["tertiary_cause_detail"] = fut_tertiary.result(timeout=tertiary_timeout) or []
        logger.info("narrative stage done: tertiary_cause_detail elapsed=%.2fs timeout=%ss", time.perf_counter() - stage_t0, tertiary_timeout)

    if not narratives.get("executive_summary"):
        raise RuntimeError("LLM executive_summary 为空，终止报告生成。")
    if not narratives.get("distribution_business_dimension"):
        raise RuntimeError("LLM distribution_business_dimension 为空，终止报告生成。")
    if not narratives.get("primary_summaries"):
        raise RuntimeError("LLM primary_summaries 为空，终止报告生成。")
    if not narratives.get("typical_case_deep_dive"):
        raise RuntimeError("LLM typical_case_deep_dive 为空，终止报告生成。")
    if not narratives.get("tertiary_cause_detail"):
        raise RuntimeError("LLM tertiary_cause_detail 为空，终止报告生成。")

    primary_labels = [
        str(item.get("key", "")).strip()
        for item in (result.get("primary", []) or [])
        if str(item.get("key", "")).strip() in CANONICAL_PRIMARY_TERTIARY
    ][:5]
    summary_by_label = {str(item.get("label", "")).strip(): item for item in narratives["primary_summaries"]}
    missing_primary = [label for label in primary_labels if label not in summary_by_label]
    if missing_primary:
        raise RuntimeError(f"一级标签小结缺失：{', '.join(missing_primary)}")

    tertiary_by_label = {str(item.get("label", "")).strip(): item for item in narratives["tertiary_cause_detail"]}
    missing_tertiary = []
    for label_data in md_evidence_labels:
        label = str(label_data.get("key", "")).strip()
        if not label:
            continue
        detail = tertiary_by_label.get(label)
        if not detail:
            missing_tertiary.append(label)
            continue
        if not detail.get("user_voice_natural"):
            raise RuntimeError(f"典型用户原话缺失：{label}")
        if _looks_like_template_phrase(detail.get("user_voice_natural", "")):
            raise RuntimeError(f"典型用户原话仍为模板句：{label}")
        for field in ("content_summary", "cs_reply_summary", "root_cause"):
            value = str(detail.get(field, "")).strip()
            if not value:
                raise RuntimeError(f"三级标签分析小结缺失：{label}.{field}")
            if _looks_like_raw_dialogue(value):
                raise RuntimeError(f"三级标签分析小结含原始工单：{label}.{field}")
            if _looks_like_template_phrase(value):
                raise RuntimeError(f"三级标签分析小结含模板句：{label}.{field}")
    if missing_tertiary:
        raise RuntimeError(f"三级标签分析小结缺失：{', '.join(missing_tertiary)}")

    narratives["primary_overall_evaluation"] = _build_primary_overall_evaluation(result, narratives["primary_summaries"], llm)
    if not narratives.get("primary_overall_evaluation") or len(narratives["primary_overall_evaluation"]) < 2:
        raise RuntimeError("一级标签综合评价生成失败。")
    logger.info("narrative stage done: primary_overall_evaluation")

    narratives["methodology_note"] = _build_methodology_note(result)
    logger.info("narratives total elapsed=%.2fs labels=%s", time.perf_counter() - narrative_start, len(md_evidence_labels))
    return narratives


# ══════════════════════════════════════════════════════════════════════
#  NEW: Executive Summary, Primary Summaries, Typical Case Deep Dive,
#       and Methodology Note
# ══════════════════════════════════════════════════════════════════════


_EXECUTIVE_SUMMARY_PROMPT = (
    "你是视频产品用户体验分析专家。请基于以下数据撰写一份面向公司决策层的摘要报告。\n\n"
    "## 数据\n"
    "- 数据周期：{period_start} 至 {period_end}\n"
    "- 服务数据总量：{total} 件（其中投诉数据 {complaint_pct}，咨询数据 {consult_pct}）\n"
    "- 一级标签分布：{primary_dist}\n"
    "- 三级TOP痛点：{tertiary_top}\n"
    "- 赛事日影响：{matchday_impact}\n"
    "- 省份集中度：{province_top}\n\n"
    "## 摘要结构要求（请严格按此顺序撰写）\n"
    "### 一、战略关联\n"
    "说明本周期数据与重点赛事运营战略的关联，如：赛事用户规模变化、会员续费/退费对收入的影响、赛事体验对用户留存的意义等。\n\n"
    "### 二、三大痛点\n"
    "基于三级标签数据，归纳本周期最突出的三个问题：\n"
    "1. 痛点一：[问题描述] — 涉及[服务数据量]件，占比[占比]\n"
    "2. 痛点二：[问题描述] — 涉及[服务数据量]件，占比[占比]\n"
    "3. 痛点三：[问题描述] — 涉及[服务数据量]件，占比[占比]\n\n"
    "### 三、典型案例\n"
    "选取 1 个最具代表性的问题案例，描述其用户原声、处理过程和根因分析。\n\n"
    "### 四、行动建议\n"
    "基于上述分析，提出 2-3 条优先级最高的运营优化建议。\n\n"
    "## 撰写规范\n"
    "1. 面向公司决策层，定性优先于定量\n"
    "2. 控制在 400-500 字\n"
    "3. 不要使用 markdown 格式，直接输出纯文本\n"
    "4. 语言简洁专业，适合高管阅读\n"
    "5. 若涉及退订困难或自动续费争议，行动建议必须聚焦订购、续费、自动扣费前确认、结果通知和规则透明化；"
    "禁止建议增加退订操作阻力，禁止出现“退订二次确认”“退订确认弹窗”等表述。\n"
)


_BANNED_RETENTION_ADVICE_PATTERNS = (
    r"增加[^。；\n]*退订[^。；\n]*二次确认[^。；\n]*[。；]?",
    r"退订[^。；\n]*二次确认[^。；\n]*[。；]?",
    r"退订[^。；\n]*确认弹窗[^。；\n]*[。；]?",
)

_RETENTION_ADVICE_REPLACEMENT = "在订购、续费和自动扣费前增加确认提示，并通过短信或APP推送明确告知订购、退订和退费处理结果。"


def _contains_banned_retention_advice(text: str) -> bool:
    return any(re.search(pattern, text or "") for pattern in _BANNED_RETENTION_ADVICE_PATTERNS)


def _sanitize_executive_summary_actions(text: str) -> str:
    cleaned = text or ""
    for pattern in _BANNED_RETENTION_ADVICE_PATTERNS:
        cleaned = re.sub(pattern, _RETENTION_ADVICE_REPLACEMENT, cleaned)
    return cleaned


def _build_executive_summary(result: dict, llm) -> str:
    """Generate executive summary for decision-makers."""
    total = result.get("total_with_unlabeled", result.get("total", 0))
    period = result.get("period", {})
    period_start = period.get("min", "未知")[:10] if period.get("min") else "未知"
    period_end = period.get("max", "未知")[:10] if period.get("max") else "未知"
    service_types = result.get("service_type", [])
    complaint_count = sum(s["count"] for s in service_types if "投诉" in str(s.get("key", "")))
    consult_count = sum(s["count"] for s in service_types if "咨询" in str(s.get("key", "")))
    complaint_pct = f"{complaint_count / total * 100:.1f}%" if total else "0%"
    consult_pct = f"{consult_count / total * 100:.1f}%" if total else "0%"
    primary = result.get("primary", [])[:5]
    primary_dist = "、".join(
        f"{p.get('key','?')}（{p.get('count',0)}件）"
        for p in primary if p.get("count", 0) > 0
    ) if total else "无"
    tertiary = result.get("tertiary", [])[:5]
    tertiary_top = "、".join(
        f"{t.get('key','?')}（{t.get('count',0)}件）"
        for t in tertiary if t.get("count", 0) > 0
    )
    schedule = result.get("schedule", {})
    matchday_info = schedule.get("message", "")
    daily = result.get("daily", [])
    matchday_count = sum(1 for d in daily if d.get("is_matchday"))
    matchday_impact = (
        f"共 {matchday_count} 个赛事日，{matchday_info}"
        if matchday_info else "无赛事日数据"
    )
    province = result.get("province", [])[:3]
    province_top = "、".join(
        f"{p.get('key','?')}（{p.get('count',0)}件）"
        for p in province if p.get("count", 0) > 0
    )
    if not llm or not llm.enabled or not getattr(llm, "report_enabled", False):
        raise RuntimeError("executive_summary 需要 LLM，但当前未启用。")
    prompt = _EXECUTIVE_SUMMARY_PROMPT.format(
        period_start=period_start, period_end=period_end,
        total=total, complaint_pct=complaint_pct, consult_pct=consult_pct,
        primary_dist=primary_dist, tertiary_top=tertiary_top,
        matchday_impact=matchday_impact, province_top=province_top,
    )
    attempts = [
        prompt,
        prompt + "\n\n请直接输出最终摘要正文，不要输出思考过程，不要解释写作步骤。注意：不得建议增加退订二次确认或退订确认弹窗；应改为订购、续费、自动扣费前确认和结果通知。",
    ]
    response = None
    for idx, candidate in enumerate(attempts):
        response = llm.chat(
            [{"role": "user", "content": candidate}],
            temperature=0.25,
            timeout_seconds=max(60, min(getattr(llm, "report_timeout", 60), 75)),
            max_retries=1,
            max_tokens=llm.report_max_tokens,
        )
        text = response.content.strip() if (not response.used_fallback and response.content) else ""
        if text and (not _looks_like_reasoning_meta(text)):
            if _contains_banned_retention_advice(text) and idx < len(attempts) - 1:
                continue
            return _sanitize_executive_summary_actions(text)
    raise RuntimeError("executive_summary LLM 多轮重试后仍失败。")


def _build_primary_level_summaries(result: dict, llm) -> list[dict]:
    """Generate one required long summary for each primary label."""
    primary = [
        item for item in (result.get("primary", []) or [])
        if str(item.get("key", "")).strip() in CANONICAL_PRIMARY_TERTIARY
    ][:5]
    total = result.get("total_with_unlabeled", result.get("total", 0))
    if not total or not primary:
        return []

    tasks: list[dict[str, Any]] = []
    for p in primary:
        pkey = str(p.get("key", "")).strip()
        pcount = int(p.get("count", 0) or 0)
        if not pkey or pcount <= 0:
            continue
        pct = f"{pcount / total * 100:.1f}%" if total else "0%"
        top3 = primary_top_tertiary_items(result, pkey, pcount, limit=3)
        if not top3:
            raise RuntimeError(f"一级标签无法按权威 taxonomy 找到三级数据：{pkey}")
        tertiary_text = "、".join(
            f"{t.get('key', '?')}（{t.get('count', 0)}条，{t.get('share', '0%')}）"
            for t in top3
            if t.get("key")
        ) or "暂无高频三级问题"
        tasks.append({"label": pkey, "count": pcount, "share": pct, "top3": top3, "top3_text": tertiary_text})

    if not llm or not llm.enabled or not getattr(llm, "report_enabled", False):
        raise RuntimeError("primary_summaries 需要 LLM，但当前未启用。")

    def _analyze_single_primary(task: dict[str, Any]) -> dict[str, Any]:
        pkey = task["label"]
        pcount = int(task["count"])
        pct = str(task["share"])
        top3 = task["top3"]
        tertiary_text = str(task["top3_text"])
        fixed_prefix = f"分析小结：{pkey}类问题共{pcount}条，占总量{pct}；同节表格Top3为{tertiary_text}。"
        prefix_len = _summary_char_len(fixed_prefix)
        min_body_len = max(70, 220 - prefix_len)
        max_body_len = max(min(170, 320 - prefix_len), min_body_len + 20)
        prompt = (
            "你是视频产品业务分析师。请为一级问题分析小结续写业务判断。\n\n"
            f"一级标签：{pkey}\n"
            f"该一级问题量：{pcount}条（占总量{pct}）\n"
            f"该一级Top3三级问题：{tertiary_text}\n\n"
            f"固定开头已经由系统写好，不要重复：{fixed_prefix}\n\n"
            "输出要求：\n"
            f"1) 只输出固定开头之后的续写正文，不要再写“分析小结：”，不要重复Top3清单。\n"
            f"2) 续写正文长度控制在{min_body_len}-{max_body_len}字；系统会和固定开头合并为220-320字的小结。\n"
            "3) 口吻偏业务复盘，文字自然，概括该类问题对用户体验和服务闭环的影响。\n"
            "4) 不要模板句，不要条目格式，不要“优化建议：”等机械话术。\n"
            "5) 禁止输出思考过程、分析步骤、原始工单JSON。\n"
        )
        candidates = [
            prompt,
            prompt + "\n\n上一轮不合规，请只输出固定开头之后的自然业务判断，长度适中，不要重复Top3清单。",
        ]
        for idx, candidate in enumerate(candidates, start=1):
            logger.info("primary summary request label=%s attempt=%s/%s", pkey, idx, len(candidates))
            resp = llm.chat(
                [{"role": "user", "content": candidate}],
                temperature=0.2,
                timeout_seconds=max(60, min(getattr(llm, "report_timeout", 60), 75)),
                max_retries=1,
                max_tokens=min(llm.report_max_tokens, 720),
            )
            summary_text = resp.content.strip() if (not resp.used_fallback and resp.content) else ""
            if not summary_text:
                continue
            summary_text = _fit_primary_summary_with_fixed_top3(fixed_prefix, summary_text, max_chars=320)
            ok, reason = _validate_primary_summary(summary_text, top3)
            if ok:
                logger.info("primary summary accepted label=%s attempt=%s/%s", pkey, idx, len(candidates))
                return {"label": pkey, "count": pcount, "share": pct, "summary": summary_text}
            logger.info("primary summary rejected label=%s attempt=%s/%s reason=%s", pkey, idx, len(candidates), reason)
        raise RuntimeError(f"primary_summaries LLM 失败：{pkey}")

    summaries = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(_analyze_single_primary, task) for task in tasks]
        for fut in as_completed(futures):
            summaries.append(fut.result(timeout=120))
    order = {task["label"]: idx for idx, task in enumerate(tasks)}
    summaries.sort(key=lambda item: order.get(str(item.get("label", "")), 999))
    return summaries


def _build_typical_case_deep_dive(result: dict, evidence_labels: list, llm) -> list[dict]:
    """Generate 2-3 typical case deep-dive analysis blocks."""
    if not evidence_labels:
        raise RuntimeError("typical_case_deep_dive 缺少 evidence_labels。")
    if not llm or not llm.enabled or not getattr(llm, "report_enabled", False):
        raise RuntimeError("typical_case_deep_dive 需要 LLM，但当前未启用。")
    
    # 准备任务列表
    tasks = []
    for label_data in evidence_labels[:3]:
        label = label_data.get("key", "")
        count = label_data.get("count", 0)
        samples = label_data.get("samples", [])[:3]
        sample_texts = "; ".join(s.get("content_excerpt", "")[:120] for s in samples if s.get("content_excerpt"))
        appeal_agg = label_data.get("appeal_agg", [])
        appeal_top = "、".join(a.get("key", "") for a in appeal_agg[:3])
        tasks.append((label, count, sample_texts[:400], appeal_top))
    
    # 并行执行LLM调用
    def _analyze_single_case(label, count, sample_texts, appeal_top):
        prompt = (
            f"你是视频产品服务体验分析师。请对以下问题进行深度剖析。\n\n"
            f"三级标签：「{label}」，共 {count} 件服务数据\n"
            f"用户原声样本：{sample_texts}\n"
            f"主要诉求：{appeal_top}\n\n"
            f"请输出一段 150-200 字的分析，包含：\n"
            f"1. 问题描述（1句话概括）\n"
            f"2. 根因链条（用户原始问题 -> 客服应对 -> 矛盾环节）\n"
            f"3. 商业影响评估\n"
            f"4. 是否可修复（短期/中期/长期），大致思路\n\n"
        )
        candidates = [
            prompt,
            prompt + "\n\n请直接输出最终分析结论，不要输出思考过程。",
        ]
        for candidate in candidates:
            resp = llm.chat(
                [{"role": "user", "content": candidate}],
                temperature=0.25,
                timeout_seconds=max(60, min(getattr(llm, "report_timeout", 60), 75)),
                max_retries=1,
                max_tokens=min(llm.report_max_tokens, 520),
            )
            analysis = resp.content.strip() if (not resp.used_fallback and resp.content) else ""
            if not analysis:
                continue
            analysis = _compact_text(analysis, max_len=420)
            if _looks_like_raw_dialogue(analysis):
                continue
            if _looks_like_reasoning_meta(analysis):
                continue
            if _looks_like_template_phrase(analysis):
                continue
            return {
                "label": label, "count": count,
                "analysis": analysis,
            }
        raise RuntimeError(f"typical_case_deep_dive LLM 失败：{label}")
    
    # 使用ThreadPoolExecutor并行执行3个标签的分析
    deep_dives = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            pool.submit(_analyze_single_case, label, count, sample_texts, appeal_top): label
            for label, count, sample_texts, appeal_top in tasks
        }
        for fut in as_completed(futures):
            result_item = fut.result(timeout=60)
            deep_dives.append(result_item)
    return deep_dives


def _build_methodology_note(result: dict) -> str:
    """Generate a subtle methodology disclaimer."""
    return "本报告基于AI辅助标签分析生成，数据来源为客服服务记录，分析结论仅供参考。"
