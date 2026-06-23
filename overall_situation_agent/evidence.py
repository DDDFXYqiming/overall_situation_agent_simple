from __future__ import annotations

import logging
import re
import random
from typing import Any

from .aggregations import _date_filter, _base_query
from .es_client import SimpleElasticsearch
from .sanitization import mask_sensitive_text, sanitize_report_payload

logger = logging.getLogger(__name__)

_BOILERPLATE = (
    "\u6b63\u5728\u4e3a\u60a8\u8f6c\u63a5\u4eba\u5de5",
    "\u5f53\u524d\u4eba\u5de5MM\u6709\u70b9\u5fd9",
    "\u8bf7\u7a0d\u540e",
    "\u8bf7\u8010\u5fc3\u7b49\u5f85",
    "\u60a8\u597d\uff0c\u5f88\u9ad8\u5174\u4e3a\u60a8\u670d\u52a1",
    "\u8bf7\u95ee\u6709\u4ec0\u4e48\u53ef\u4ee5\u5e2e\u5230\u60a8",
)

_SOURCE_FIELDS = [
    "content", "cs_reply", "customer_key_appeal", "customer_keywords",
    "cs_key_action", "cs_keywords", "service_time", "scene_emotion",
]


def _compute_sample_count(total_hits: int) -> int:
    if total_hits < 5_000:
        return 24
    if total_hits < 10_000:
        return 40
    if total_hits < 20_000:
        return 56
    if total_hits < 30_000:
        return 80
    return 80


def _clean_text(text: str, max_len: int = 300) -> str:
    if not text:
        return ""
    t = str(text)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[A-Z0-9]{12,}", "", t)
    for marker in _BOILERPLATE:
        t = t.replace(marker, "")
    t = mask_sensitive_text(t)
    t = t.strip(" ;\uff1b,,\u3002")
    return t[:max_len]


def _maybe_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return value
    if not value:
        return []
    return [str(value)]


def _fetch_tertiary_buckets(
    es: SimpleElasticsearch,
    index_name: str,
    start_date: str | None,
    end_date: str | None,
    top_n: int,
    labels: list[str] | None = None,
) -> list[dict[str, Any]]:
    labeled_query = _base_query(start_date, end_date, exclude_unlabeled=True)
    terms_body: dict[str, Any] = {"field": "tertiary_labels", "size": top_n}
    if labels:
        terms_body["include"] = labels
    top_body = {
        "size": 0,
        "track_total_hits": True,
        "query": labeled_query,
        "aggs": {
            "tertiary_top": {
                "terms": terms_body,
            },
        },
    }
    top_response = es.search(index=index_name, body=top_body)
    return top_response.body["aggregations"]["tertiary_top"].get("buckets", [])


def _sample_body_for_label(
    label: str,
    sample_size: int,
    start_date: str | None,
    end_date: str | None,
) -> dict[str, Any]:
    return {
        "size": sample_size,
        "track_total_hits": True,
        "query": {
            "bool": {
                "filter": [
                    {"term": {"tertiary_labels": label}},
                    *_date_filter(start_date, end_date),
                    {"exists": {"field": "primary_labels"}},
                ],
            },
        },
        "_source": _SOURCE_FIELDS,
        "aggs": {
            "appeal_agg": {"terms": {"field": "customer_key_appeal.keyword", "size": 5}},
            "cs_action_agg": {"terms": {"field": "cs_key_action.keyword", "size": 5}},
        },
    }


def _response_body(response: Any) -> dict[str, Any]:
    if hasattr(response, "body"):
        return response.body
    return response if isinstance(response, dict) else {}


def _label_evidence_from_response(
    bucket: dict[str, Any],
    response_body: dict[str, Any],
    tertiary_total: int,
) -> dict[str, Any]:
    label = bucket["key"]
    count = int(bucket.get("doc_count", 0) or 0)
    agg_data = response_body.get("aggregations", {})
    hits = list(response_body.get("hits", {}).get("hits", []))
    random.shuffle(hits)

    samples = []
    for hit in hits:
        src = hit.get("_source", {})
        content_raw = str(src.get("content") or "")
        cs_raw = str(src.get("cs_reply") or "")
        appeal_raw = str(src.get("customer_key_appeal") or "")
        samples.append({
            "content_excerpt": _clean_text(content_raw, 300),
            "cs_reply_excerpt": _clean_text(cs_raw, 220),
            "customer_key_appeal": _clean_text(appeal_raw, 120),
            "customer_key_appeal_full": mask_sensitive_text(appeal_raw)[:1000],
            "customer_keywords": _clean_text(str(src.get("customer_keywords") or ""), 120),
            "cs_key_action": _clean_text(str(src.get("cs_key_action") or ""), 120),
            "cs_keywords": _clean_text(str(src.get("cs_keywords") or ""), 120),
            "service_time": src.get("service_time"),
            "emotion": src.get("scene_emotion"),
        })

    return sanitize_report_payload({
        "key": label,
        "count": count,
        "share": round(count / tertiary_total, 4) if tertiary_total else 0,
        "samples": samples,
        "appeal_agg": [
            {"key": b["key"], "count": b["doc_count"]}
            for b in agg_data.get("appeal_agg", {}).get("buckets", [])
        ],
        "cs_action_agg": [
            {"key": b["key"], "count": b["doc_count"]}
            for b in agg_data.get("cs_action_agg", {}).get("buckets", [])
        ],
    })


def _build_evidence_from_buckets(
    es: SimpleElasticsearch,
    index_name: str,
    total_hits: int,
    buckets: list[dict[str, Any]],
    start_date: str | None = None,
    end_date: str | None = None,
    all_tertiary_total: int | None = None,
) -> dict[str, Any]:
    if not buckets:
        return {"labels": [], "sampling": {"per_label": 0, "total_hits": total_hits}}

    per_label = _compute_sample_count(total_hits)
    tertiary_total = all_tertiary_total if all_tertiary_total else sum(b.get("doc_count", 0) for b in buckets)
    sample_bodies = [
        _sample_body_for_label(
            label=str(bucket["key"]),
            sample_size=min(per_label, int(bucket.get("doc_count", 0) or 0)),
            start_date=start_date,
            end_date=end_date,
        )
        for bucket in buckets
    ]
    msearch = getattr(es, "msearch", None)
    if callable(msearch):
        sample_responses = msearch(index_name, sample_bodies)
    else:
        sample_responses = [es.search(index=index_name, body=body) for body in sample_bodies]
    if len(sample_responses) != len(buckets):
        raise RuntimeError(f"证据采样响应数量不匹配：expect={len(buckets)} got={len(sample_responses)}")

    labels = [
        _label_evidence_from_response(bucket, _response_body(response), tertiary_total)
        for bucket, response in zip(buckets, sample_responses)
    ]

    logger.info(
        "fetched evidence total=%s labels=%s per_label=%s samples=%s",
        total_hits,
        len(labels),
        per_label,
        sum(len(lb["samples"]) for lb in labels),
    )

    return {
        "labels": labels,
        "sampling": {"per_label": per_label, "total_hits": total_hits},
    }


def fetch_tertiary_top_evidence(
    es: SimpleElasticsearch,
    index_name: str,
    total_hits: int,
    start_date: str | None = None,
    end_date: str | None = None,
    top_n: int = 5,
    all_tertiary_total: int | None = None,
) -> dict[str, Any]:
    top_buckets = _fetch_tertiary_buckets(
        es=es,
        index_name=index_name,
        start_date=start_date,
        end_date=end_date,
        top_n=top_n,
    )
    return _build_evidence_from_buckets(
        es=es,
        index_name=index_name,
        total_hits=total_hits,
        buckets=top_buckets,
        start_date=start_date,
        end_date=end_date,
        all_tertiary_total=all_tertiary_total,
    )


def fetch_tertiary_evidence_for_labels(
    es: SimpleElasticsearch,
    index_name: str,
    total_hits: int,
    labels: list[str],
    start_date: str | None = None,
    end_date: str | None = None,
    all_tertiary_total: int | None = None,
) -> dict[str, Any]:
    ordered_labels = []
    seen: set[str] = set()
    for label in labels:
        text = str(label or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered_labels.append(text)
    if not ordered_labels:
        return {"labels": [], "sampling": {"per_label": 0, "total_hits": total_hits}}

    buckets = _fetch_tertiary_buckets(
        es=es,
        index_name=index_name,
        start_date=start_date,
        end_date=end_date,
        top_n=max(len(ordered_labels), 1),
        labels=ordered_labels,
    )
    bucket_by_key = {str(bucket.get("key")): bucket for bucket in buckets}
    ordered_buckets = [bucket_by_key[label] for label in ordered_labels if label in bucket_by_key]
    return _build_evidence_from_buckets(
        es=es,
        index_name=index_name,
        total_hits=total_hits,
        buckets=ordered_buckets,
        start_date=start_date,
        end_date=end_date,
        all_tertiary_total=all_tertiary_total,
    )
