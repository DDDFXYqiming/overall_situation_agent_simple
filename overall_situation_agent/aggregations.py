from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .es_client import SimpleElasticsearch
from .sanitization import sanitize_report_payload
from .schema import NEGATIVE_EMOTIONS


def _date_filter(start_date: str | None, end_date: str | None) -> list[dict]:
    if not start_date and not end_date:
        return []
    range_query: dict[str, str] = {}
    if start_date:
        range_query["gte"] = start_date
    if end_date:
        end_dt = datetime.fromisoformat(end_date) + timedelta(days=1)
        range_query["lt"] = end_dt.strftime("%Y-%m-%d")
    return [{"range": {"service_time": range_query}}]


def _base_query(start_date: str | None, end_date: str | None, exclude_unlabeled: bool = False) -> dict:
    filters = _date_filter(start_date, end_date)
    if exclude_unlabeled:
        filters.append({"exists": {"field": "primary_labels"}})
    return {"bool": {"filter": filters}} if filters else {"match_all": {}}


def _terms(field: str, size: int = 20, exclude: list[str] | None = None) -> dict:
    body: dict[str, Any] = {"field": field, "size": size}
    if exclude:
        body["exclude"] = exclude
    return {"terms": body}


def _text_terms(field: str, size: int = 20) -> dict:
    return {
        "terms": {
            "field": field,
            "size": size,
            "exclude": ["无", "不适用", "{}"],
        }
    }


def _age_ranges() -> dict:
    return {
        "range": {
            "field": "age",
            "ranges": [
                {"key": "18岁以下", "to": 18},
                {"key": "18-25", "from": 18, "to": 26},
                {"key": "26-35", "from": 26, "to": 36},
                {"key": "36-45", "from": 36, "to": 46},
                {"key": "46-60", "from": 46, "to": 61},
                {"key": "60岁以上", "from": 61},
            ],
        }
    }


def run_overall_aggregations(
    es: SimpleElasticsearch,
    index_name: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    total_response = es.search(
        index=index_name,
        body={
            "size": 0,
            "track_total_hits": True,
            "query": _base_query(start_date, end_date),
        },
    )
    total_with_unlabeled = (
        total_response.body["hits"]["total"]["value"]
        if isinstance(total_response.body["hits"]["total"], dict)
        else total_response.body["hits"]["total"]
    )

    query = _base_query(start_date, end_date, exclude_unlabeled=True)
    body = {
        "size": 0,
        "track_total_hits": True,
        "query": query,
        "aggs": {
            "period_min": {"min": {"field": "service_time"}},
            "period_max": {"max": {"field": "service_time"}},
            "primary": _terms("primary_labels", 20),
            "secondary": _terms("secondary_labels", 30),
            "tertiary": _terms("tertiary_labels", 30),
            "emotion": _terms("scene_emotion", 20),
            "service_type": _terms("scene_service_type", 10),
            "province": _terms("province_name", 20),
            "event": _terms("scene_event", 20),
            "source_file": _terms("source_file", 5),
            "refund": _terms("has_refund_demand", 5),
            "escalation": _terms("has_escalation", 5),
            "province_tertiary": {
                "terms": {"field": "province_name", "size": 10},
                "aggs": {
                    "top_tertiary": _terms("tertiary_labels", 5),
                }
            },
            "province_refund": {
                "terms": {"field": "province_name", "size": 10},
                "aggs": {
                    "refund_distribution": _terms("has_refund_demand", 3),
                }
            },
            "refund_tertiary": {
                "terms": {"field": "has_refund_demand", "size": 3},
                "aggs": {
                    "top_tertiary": _terms("tertiary_labels", 5),
                }
            },
            "label_group": _terms("label_group", 20),
            "insight_dimension": _terms("insight_dimension", 10),
            "customer_key_appeal": _terms("customer_key_appeal.keyword", 10),
            "cs_key_action": _text_terms("cs_key_action.keyword", 10),
            "operation_action": _terms("operation_action", 10),
            "four_ops": _terms("four_operation", 10),
            "four_product": _terms("four_product_level", 10),
            "biz_member_cluster": _terms("biz_member_cluster", 12),
            "marketing_activity_page": _terms("marketing_activity_page", 10, exclude=["无", "不适用", "{}", "[]", "未知"]),
            "marketing_activity_match_status": _terms("marketing_activity_match_status", 8, exclude=["无", "否", "不适用", "{}", "[]", "未知"]),
            "marketing_activity_match_keywords": _terms("marketing_activity_match_keywords", 12, exclude=["无", "不适用", "{}", "[]", "未知"]),
            "gender": _terms("gender", 5, exclude=["未知", "无", "不适用"]),
            "age_ranges": _age_ranges(),
            "time_period": _terms("time_period", 8),
            "match_label": _terms("match_label", 10),
            "avg_duration_minutes": {"avg": {"field": "duration_minutes"}},
            "primary_secondary": {
                "terms": {"field": "primary_labels", "size": 20},
                "aggs": {"secondary": _terms("secondary_labels", 10)},
            },
            "primary_secondary_tertiary": {
                "terms": {"field": "primary_labels", "size": 20},
                "aggs": {
                    "secondary": {
                        "terms": {"field": "secondary_labels", "size": 30},
                        "aggs": {
                            "tertiary": _terms("tertiary_labels", 30),
                        },
                    }
                },
            },
            "daily": {
                "date_histogram": {
                    "field": "service_time",
                    "calendar_interval": "day",
                    "format": "yyyy-MM-dd",
                    "min_doc_count": 0,
                },
                "aggs": {
                    "negative": {"filter": {"terms": {"scene_emotion": NEGATIVE_EMOTIONS}}},
                    "top_primary": _terms("primary_labels", 3),
                    "top_secondary": _terms("secondary_labels", 3),
                    "top_tertiary": _terms("tertiary_labels", 3),
                    "top_service_type": _terms("scene_service_type", 3),
                    "top_member_cluster": _terms("biz_member_cluster", 3),
                    "top_events": _terms("scene_event", 3),
                    "top_operations": _terms("operation_action", 3),
                    "top_matches": _terms("match_label", 3),
                    "sample_hits": {
                        "top_hits": {
                            "size": 3,
                            "_source": [
                                "service_time",
                                "content",
                                "customer_key_appeal",
                                "scene_emotion",
                                "primary_labels",
                                "secondary_labels",
                                "tertiary_labels",
                                "operation_action",
                                "biz_member_cluster",
                                "match_label",
                            ],
                        }
                    },
                },
            },
            "top_tertiary_examples": {
                "terms": {"field": "tertiary_labels", "size": 5},
                "aggs": {
                    "top_appeals": _terms("customer_key_appeal.keyword", 3),
                    "sample": {
                        "top_hits": {
                            "size": 2,
                            "_source": [
                                "gd_identity",
                                "province_name",
                                "service_time",
                                "content",
                                "customer_key_appeal",
                                "scene_emotion",
                                "operation_action",
                                "biz_member_cluster",
                                "latent_need",
                            ],
                        }
                    },
                },
            },
            "operation_need_examples": {
                "terms": {"field": "operation_action", "size": 8},
                "aggs": {
                    "top_latent_needs": _text_terms("latent_need.keyword", 5),
                    "top_member_clusters": _terms("biz_member_cluster", 5),
                    "top_tertiary": _terms("tertiary_labels", 5),
                    "sample": {
                        "top_hits": {
                            "size": 2,
                            "_source": [
                                "gd_identity",
                                "service_time",
                                "content",
                                "customer_key_appeal",
                                "operation_action",
                                "latent_need",
                                "latent_need_reason",
                                "biz_member_cluster",
                                "tertiary_labels",
                            ],
                        }
                    },
                },
            },
            "member_cluster_examples": {
                "terms": {"field": "biz_member_cluster", "size": 10},
                "aggs": {
                    "top_tertiary": _terms("tertiary_labels", 5),
                    "top_appeals": _terms("customer_key_appeal.keyword", 5),
                    "sample": {
                        "top_hits": {
                            "size": 2,
                            "_source": [
                                "gd_identity",
                                "service_time",
                                "content",
                                "customer_key_appeal",
                                "biz_member_cluster",
                                "tertiary_labels",
                            ],
                        }
                    },
                },
            },
            "latent_need_examples": {
                "terms": {
                    "field": "latent_need.keyword",
                    "size": 10,
                    "exclude": ["无", "不适用", "{}"],
                },
                "aggs": {
                    "top_operations": _terms("operation_action", 5),
                    "top_members": _terms("biz_member_cluster", 5),
                    "sample": {
                        "top_hits": {
                            "size": 2,
                            "_source": [
                                "gd_identity",
                                "service_time",
                                "content",
                                "latent_need",
                                "latent_need_reason",
                                "operation_action",
                                "biz_member_cluster",
                            ],
                        }
                    },
                },
            },
        },
    }
    response = es.search(index=index_name, body=body)
    result = normalize_aggregations(response.body, start_date, end_date)
    result["total_with_unlabeled"] = total_with_unlabeled
    result["unlabeled_analysis"] = run_unlabeled_analysis(es, index_name, start_date, end_date)
    result["unlabeled_trend_analysis"] = run_unlabeled_trend_analysis(es, index_name, start_date, end_date)
    # Include four operations / four product levels from mapping
    four_ops, four_products, four_mapping_table = _compute_four_dimensions(result.get("tertiary", []))
    result["four_ops_map"] = four_ops
    result["four_products_map"] = four_products
    result["four_mapping_table"] = four_mapping_table
    return result


def _bucket_list(agg: dict) -> list[dict]:
    return [{"key": b["key"], "count": b["doc_count"]} for b in agg.get("buckets", [])]


def _top_bucket(buckets: list[dict]) -> dict | None:
    return buckets[0] if buckets else None


def _sample_hits(agg: dict, limit: int = 3) -> list[dict]:
    samples = []
    hits = agg.get("hits", {}).get("hits", [])
    for hit in hits[:limit]:
        source = hit.get("_source", {})
        content = sanitize_report_payload(str(source.get("content") or "").strip())
        samples.append(
            {
                "service_time": source.get("service_time"),
                "emotion": source.get("scene_emotion"),
                "appeal": source.get("customer_key_appeal"),
                "primary_labels": source.get("primary_labels"),
                "secondary_labels": source.get("secondary_labels"),
                "tertiary_labels": source.get("tertiary_labels"),
                "operation_action": source.get("operation_action"),
                "biz_member_cluster": source.get("biz_member_cluster"),
                "match_label": source.get("match_label"),
                "content_excerpt": content[:180],
            }
        )
    return samples


def _nested_bucket_list(agg: dict, child_key: str | None = None) -> list[dict]:
    rows: list[dict] = []
    for bucket in agg.get("buckets", []):
        item = {"key": bucket["key"], "count": bucket["doc_count"]}
        if child_key:
            item[child_key] = _nested_bucket_list(bucket.get(child_key, {}), "tertiary" if child_key == "secondary" else None)
        rows.append(item)
    return rows


def normalize_aggregations(response: dict, start_date: str | None, end_date: str | None) -> dict[str, Any]:
    aggs = response["aggregations"]
    total = response["hits"]["total"]["value"] if isinstance(response["hits"]["total"], dict) else response["hits"]["total"]

    daily = []
    previous_count: int | None = None
    anomalies = []
    for bucket in aggs["daily"]["buckets"]:
        count = bucket["doc_count"]
        negative_count = bucket["negative"]["doc_count"]
        negative_ratio = round(negative_count / count, 4) if count else 0
        top_primary = _bucket_list(bucket.get("top_primary", {}))
        top_secondary = _bucket_list(bucket.get("top_secondary", {}))
        top_tertiary = _bucket_list(bucket["top_tertiary"])
        top_service_type = _bucket_list(bucket.get("top_service_type", {}))
        top_member_cluster = _bucket_list(bucket.get("top_member_cluster", {}))
        top_events = _bucket_list(bucket["top_events"])
        top_operations = _bucket_list(bucket.get("top_operations", {}))
        top_matches = _bucket_list(bucket.get("top_matches", {}))
        day = {
            "date": bucket["key_as_string"],
            "count": count,
            "negative_count": negative_count,
            "negative_ratio": negative_ratio,
            "top_primary": top_primary,
            "top_secondary": top_secondary,
            "top_tertiary": top_tertiary,
            "top_service_type": top_service_type,
            "top_member_cluster": top_member_cluster,
            "top_events": top_events,
            "top_operations": top_operations,
            "top_matches": top_matches,
            "samples": _sample_hits(bucket.get("sample_hits", {})),
        }
        if previous_count is not None and previous_count > 0:
            growth = (count - previous_count) / previous_count
            day["day_over_day_growth"] = round(growth, 4)
            if growth >= 0.5 and count >= 5:
                anomalies.append(day)
        previous_count = count
        daily.append(day)

    top_tertiary_examples = []
    for bucket in aggs["top_tertiary_examples"]["buckets"]:
        samples = []
        for hit in bucket["sample"]["hits"]["hits"]:
            source = hit["_source"]
            content = sanitize_report_payload(str(source.get("content") or ""))
            samples.append(
                {
                    "gd_identity": sanitize_report_payload({"gd_identity": source.get("gd_identity")})["gd_identity"],
                    "province_name": source.get("province_name"),
                    "service_time": source.get("service_time"),
                    "emotion": source.get("scene_emotion"),
                    "appeal": source.get("customer_key_appeal"),
                    "operation_action": source.get("operation_action"),
                    "biz_member_cluster": source.get("biz_member_cluster"),
                    "latent_need": source.get("latent_need"),
                    "content_excerpt": content[:140],
                }
            )
        top_tertiary_examples.append(
            {
                "key": bucket["key"],
                "count": bucket["doc_count"],
                "top_appeals": _bucket_list(bucket["top_appeals"]),
                "samples": samples,
            }
        )

    def _example_samples(bucket: dict, limit: int = 2) -> list[dict]:
        samples = []
        for hit in bucket.get("sample", {}).get("hits", {}).get("hits", [])[:limit]:
            source = hit.get("_source", {})
            content = sanitize_report_payload(str(source.get("content") or ""))
            samples.append(
                {
                    "gd_identity": sanitize_report_payload({"gd_identity": source.get("gd_identity")})["gd_identity"],
                    "service_time": source.get("service_time"),
                    "appeal": source.get("customer_key_appeal"),
                    "operation_action": source.get("operation_action"),
                    "biz_member_cluster": source.get("biz_member_cluster"),
                    "latent_need": source.get("latent_need"),
                    "latent_need_reason": source.get("latent_need_reason"),
                    "tertiary_labels": source.get("tertiary_labels"),
                    "content_excerpt": content[:160],
                }
            )
        return samples

    operation_need_examples = []
    for bucket in aggs["operation_need_examples"]["buckets"]:
        operation_need_examples.append(
            {
                "key": bucket["key"],
                "count": bucket["doc_count"],
                "top_latent_needs": _bucket_list(bucket["top_latent_needs"]),
                "top_member_clusters": _bucket_list(bucket["top_member_clusters"]),
                "top_tertiary": _bucket_list(bucket["top_tertiary"]),
                "samples": _example_samples(bucket),
            }
        )

    member_cluster_examples = []
    for bucket in aggs["member_cluster_examples"]["buckets"]:
        member_cluster_examples.append(
            {
                "key": bucket["key"],
                "count": bucket["doc_count"],
                "top_tertiary": _bucket_list(bucket["top_tertiary"]),
                "top_appeals": _bucket_list(bucket["top_appeals"]),
                "samples": _example_samples(bucket),
            }
        )

    latent_need_examples = []
    for bucket in aggs["latent_need_examples"]["buckets"]:
        latent_need_examples.append(
            {
                "key": bucket["key"],
                "count": bucket["doc_count"],
                "top_operations": _bucket_list(bucket["top_operations"]),
                "top_members": _bucket_list(bucket["top_members"]),
                "samples": _example_samples(bucket),
            }
        )

    primary_secondary = []
    for bucket in aggs["primary_secondary"]["buckets"]:
        primary_secondary.append(
            {
                "key": bucket["key"],
                "count": bucket["doc_count"],
                "secondary": _bucket_list(bucket["secondary"]),
            }
        )

    primary_secondary_tertiary = []
    for bucket in aggs["primary_secondary_tertiary"]["buckets"]:
        primary_secondary_tertiary.append(
            {
                "key": bucket["key"],
                "count": bucket["doc_count"],
                "secondary": _nested_bucket_list(bucket.get("secondary", {}), "tertiary"),
            }
        )

    def _nested_bucket_list_with_tertiary(bucket: dict, child_key: str) -> list[dict]:
        rows: list[dict] = []
        for b in bucket.get("buckets", []):
            item = {"key": b["key"], "count": b["doc_count"]}
            item[child_key] = _bucket_list(b.get("top_tertiary", {}))
            rows.append(item)
        return rows

    province_tertiary = _nested_bucket_list_with_tertiary(aggs["province_tertiary"], "top_tertiary")
    province_refund = []
    for bucket in aggs["province_refund"].get("buckets", []):
        item = {"key": bucket["key"], "count": bucket["doc_count"]}
        item["refund_distribution"] = _bucket_list(bucket.get("refund_distribution", {}))
        province_refund.append(item)
    refund_tertiary = _nested_bucket_list_with_tertiary(aggs["refund_tertiary"], "top_tertiary")

    result = {
        "filters": {"start_date": start_date, "end_date": end_date},
        "total": total,
        "period": {
            "min": aggs["period_min"].get("value_as_string"),
            "max": aggs["period_max"].get("value_as_string"),
        },
        "primary": _bucket_list(aggs["primary"]),
        "secondary": _bucket_list(aggs["secondary"]),
        "tertiary": _bucket_list(aggs["tertiary"]),
        "emotion": _bucket_list(aggs["emotion"]),
        "service_type": _bucket_list(aggs["service_type"]),
        "province": _bucket_list(aggs["province"]),
        "event": _bucket_list(aggs["event"]),
        "source_files": _bucket_list(aggs["source_file"]),
        "refund": _bucket_list(aggs["refund"]),
        "escalation": _bucket_list(aggs["escalation"]),
        "province_tertiary": province_tertiary,
        "province_refund": province_refund,
        "refund_tertiary": refund_tertiary,
        "label_group": _bucket_list(aggs["label_group"]),
        "insight_dimension": _bucket_list(aggs["insight_dimension"]),
        "customer_key_appeal": _bucket_list(aggs["customer_key_appeal"]),
        "cs_key_action": _bucket_list(aggs["cs_key_action"]),
        "operation_action": _bucket_list(aggs["operation_action"]),
        "biz_member_cluster": _bucket_list(aggs["biz_member_cluster"]),
        "marketing_activity_page": _bucket_list(aggs["marketing_activity_page"]),
        "marketing_activity_match_status": _bucket_list(aggs["marketing_activity_match_status"]),
        "marketing_activity_match_keywords": _bucket_list(aggs["marketing_activity_match_keywords"]),
        "gender": _bucket_list(aggs["gender"]),
        "age_ranges": _bucket_list(aggs["age_ranges"]),
        "time_period": _bucket_list(aggs["time_period"]),
        "match_label": _bucket_list(aggs["match_label"]),
        "avg_duration_minutes": aggs.get("avg_duration_minutes", {}).get("value"),
        "primary_secondary": primary_secondary,
        "primary_secondary_tertiary": primary_secondary_tertiary,
        "daily": daily,
        "anomalies": anomalies,
        "top_tertiary_examples": top_tertiary_examples,
        "operation_need_examples": operation_need_examples,
        "member_cluster_examples": member_cluster_examples,
        "latent_need_examples": latent_need_examples,
    }
    result["insights"] = build_insights(result)
    return sanitize_report_payload(result)


def build_insights(result: dict[str, Any]) -> list[str]:
    labeled_total = result["total"]
    total = result.get("total_with_unlabeled", labeled_total)
    if total == 0:
        return ["当前筛选周期内未检索到可统计的服务数据。"]

    insights = []
    top_primary = _top_bucket(result["primary"])
    top_tertiary = _top_bucket(result["tertiary"])
    top_emotion = _top_bucket(result["emotion"])
    peak_day = max(result["daily"], key=lambda x: x["count"], default=None)

    if top_primary:
        insights.append(f"本周期共纳入 {total} 条用户投诉数据，一级问题中「{top_primary['key']}」占比最高，提及 {top_primary['count']} 次。")
    if top_tertiary:
        insights.append(f"三级问题 TOP 项为「{top_tertiary['key']}」，提及 {top_tertiary['count']} 次，是整体情况中最需要优先定位原因的痛点。")
    if peak_day:
        ratio = f"{peak_day['negative_ratio']:.0%}"
        insights.append(f"按日趋势看，{peak_day['date']} 问题量最高，为 {peak_day['count']} 件，当日负向情绪占比 {ratio}。")
    if result["anomalies"]:
        first = result["anomalies"][0]
        insights.append(f"检测到 {len(result['anomalies'])} 个日环比明显上升节点，首个异动日为 {first['date']}，需结合赛事日或活动节点复盘。")
    elif len(result["daily"]) > 1:
        insights.append("未发现日环比超过 50% 的明显异动节点，整体波动相对平稳。")
    if top_emotion:
        insights.append(f"情绪标签中「{top_emotion['key']}」最多，建议在后续根因分析中结合客服处理动作和用户关键诉求一起判断。")

    return insights


def run_unlabeled_analysis(
    es: SimpleElasticsearch,
    index_name: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    filters = _date_filter(start_date, end_date)
    filters.append({"bool": {"must_not": [{"exists": {"field": "primary_labels"}}]}})
    query = {"bool": {"filter": filters}}
    body = {
        "size": 0,
        "track_total_hits": True,
        "query": query,
        "aggs": {
            "emotion": _terms("scene_emotion", 10),
            "biz_member_cluster": _terms("biz_member_cluster", 10),
            "province": _terms("province_name", 15),
            "service_type": _terms("scene_service_type", 5),
            "csp_name": _terms("csp_name", 10),
            "operation_action": _terms("operation_action", 10),
            "latent_need": _text_terms("latent_need.keyword", 10),
            "customer_key_appeal": _terms("customer_key_appeal.keyword", 10),
            "has_refund_demand": _terms("has_refund_demand", 5),
            "has_escalation": _terms("has_escalation", 5),
            "insight_dimension": _terms("insight_dimension", 10),
            "time_period": _terms("time_period", 8),
            "samples": {
                "top_hits": {
                    "size": 15,
                    "_source": [
                        "gd_identity",
                        "content",
                        "cs_reply",
                        "customer_key_appeal",
                        "operation_action",
                        "latent_need",
                        "latent_need_reason",
                        "biz_member_cluster",
                        "province_name",
                        "scene_emotion",
                        "scene_service_type",
                        "csp_name",
                        "has_refund_demand",
                        "has_escalation",
                        "insight_dimension",
                        "time_period",
                    ],
                }
            },
        },
    }
    response = es.search(index=index_name, body=body)
    return normalize_unlabeled_analysis(response.body)


def normalize_unlabeled_analysis(response: dict) -> dict[str, Any]:
    aggs = response["aggregations"]
    total = response["hits"]["total"]["value"] if isinstance(response["hits"]["total"], dict) else response["hits"]["total"]

    samples = []
    for hit in aggs["samples"]["hits"]["hits"]:
        source = hit.get("_source", {})
        content = sanitize_report_payload(str(source.get("content") or "").strip())
        samples.append({
            "gd_identity": sanitize_report_payload({"gd_identity": source.get("gd_identity")})["gd_identity"],
            "content_excerpt": content[:200],
            "cs_reply": source.get("cs_reply"),
            "customer_key_appeal": source.get("customer_key_appeal"),
            "operation_action": source.get("operation_action"),
            "latent_need": source.get("latent_need"),
            "latent_need_reason": source.get("latent_need_reason"),
            "biz_member_cluster": source.get("biz_member_cluster"),
            "province": source.get("province_name"),
            "emotion": source.get("scene_emotion"),
            "service_type": source.get("scene_service_type"),
            "csp_name": source.get("csp_name"),
            "has_refund_demand": source.get("has_refund_demand"),
            "has_escalation": source.get("has_escalation"),
            "insight_dimension": source.get("insight_dimension"),
            "time_period": source.get("time_period"),
        })

    return sanitize_report_payload({
        "unlabeled_total": total,
        "samples": samples,
        "emotion": _bucket_list(aggs["emotion"]),
        "biz_member_cluster": _bucket_list(aggs["biz_member_cluster"]),
        "province": _bucket_list(aggs["province"]),
        "service_type": _bucket_list(aggs["service_type"]),
        "csp_name": _bucket_list(aggs["csp_name"]),
        "operation_action": _bucket_list(aggs["operation_action"]),
        "latent_need": _bucket_list(aggs["latent_need"]),
        "customer_key_appeal": _bucket_list(aggs["customer_key_appeal"]),
        "has_refund_demand": _bucket_list(aggs["has_refund_demand"]),
        "has_escalation": _bucket_list(aggs["has_escalation"]),
        "insight_dimension": _bucket_list(aggs["insight_dimension"]),
        "time_period": _bucket_list(aggs["time_period"]),
    })


def run_unlabeled_trend_analysis(
    es: SimpleElasticsearch,
    index_name: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    filters = _date_filter(start_date, end_date)
    filters.append({"bool": {"must_not": [{"exists": {"field": "primary_labels"}}]}})
    query = {"bool": {"filter": filters}}
    body = {
        "size": 0,
        "track_total_hits": True,
        "query": query,
        "aggs": {
            "daily": {
                "date_histogram": {
                    "field": "service_time",
                    "calendar_interval": "day",
                    "format": "yyyy-MM-dd",
                    "min_doc_count": 1,
                },
                "aggs": {
                    "emotion": _terms("scene_emotion", 5),
                    "top_appeal": _terms("customer_key_appeal.keyword", 3),
                    "negative": {"filter": {"terms": {"scene_emotion": NEGATIVE_EMOTIONS}}},
                },
            },

        },
    }
    response = es.search(index=index_name, body=body)
    return normalize_unlabeled_trend_analysis(response.body)


def normalize_unlabeled_trend_analysis(response: dict) -> dict[str, Any]:
    aggs = response["aggregations"]
    total = response["hits"]["total"]["value"] if isinstance(response["hits"]["total"], dict) else response["hits"]["total"]

    daily = []
    peak_day_data = None
    emotion_peak_day_data = None

    for bucket in aggs["daily"]["buckets"]:
        count = bucket["doc_count"]
        negative_count = bucket["negative"]["doc_count"]
        negative_ratio = round(negative_count / count, 4) if count else 0
        daily.append({
            "date": bucket["key_as_string"],
            "count": count,
            "negative_count": negative_count,
            "negative_ratio": negative_ratio,
            "emotion": _bucket_list(bucket["emotion"]),
            "top_appeal": _bucket_list(bucket["top_appeal"]),
        })

    if daily:
        peak_day_data = max(daily, key=lambda x: x["count"])
        emotion_peak_day_data = max(daily, key=lambda x: x["negative_ratio"])

    return sanitize_report_payload({
        "unlabeled_total": total,
        "daily": daily,
        "peak_day": peak_day_data,
        "emotion_peak_day": emotion_peak_day_data,
    })


# ── Four Operations / Four Product Level mapping ─────────────────────────

# Static mapping from tertiary label -> (operation_dimension, product_level)
# Loaded from the supplementary labels file at first use.
_FOUR_DIM_CACHE: dict[str, tuple[str, str]] | None = None


def _load_four_dim_mapping() -> dict[str, tuple[str, str]]:
    """Load tertiary-label → (operation, product_level) from supplementary file."""
    global _FOUR_DIM_CACHE
    if _FOUR_DIM_CACHE is not None:
        return _FOUR_DIM_CACHE

    import pandas as pd

    mapping: dict[str, tuple[str, str]] = {}
    mapping_file = os.getenv("FOUR_DIM_MAPPING_FILE") or os.getenv("SUPPLEMENTARY_LABEL_MAPPING_FILE")
    label_file = Path(mapping_file).expanduser() if mapping_file else None

    if label_file is None or not label_file.exists():
        _FOUR_DIM_CACHE = mapping
        return mapping

    try:
        df = pd.read_excel(label_file, sheet_name="三级问题标签")
        # The file structure: col 0 = 一级标签, col 1 = 二级标签, col 2 = 三级标签, col 4 = 四个层次/四个运营
        for _, row in df.iterrows():
            tertiary = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ""
            cat = str(row.iloc[4]).strip() if len(row) > 4 and pd.notna(row.iloc[4]) else ""
            if not tertiary or not cat:
                continue
            # Determine if it's a product level or operation
            if cat in {"平台产品", "内容产品", "功能产品", "工具产品"}:
                # Also set default operation based on product level
                prod_to_ops = {"平台产品": "商业运营", "内容产品": "内容运营", "功能产品": "平台运营", "工具产品": "用户运营"}
                mapping[tertiary] = (prod_to_ops.get(cat, ""), cat)
            elif cat in {"内容运营", "平台运营", "用户运营", "商业运营"}:
                # Also set default product level based on operation
                ops_to_prod = {"商业运营": "平台产品", "内容运营": "内容产品", "平台运营": "功能产品", "用户运营": "工具产品"}
                mapping[tertiary] = (cat, ops_to_prod.get(cat, ""))
            elif tertiary not in mapping:
                mapping[tertiary] = ("", "")
    except Exception:
        pass

    _FOUR_DIM_CACHE = mapping
    return mapping


def _compute_four_dimensions(tertiary_items: list[dict]) -> tuple[list, list, list]:
    """Given tertiary aggregation buckets, compute rolled-up four-ops and
    four-product counts using the supplementary label mapping.
    Returns (ops_result, prod_result, mapping_table) where mapping_table
    lists every tertiary label with its operation and product category."""
    mapping = _load_four_dim_mapping()

    # Hardcoded fallback for ES-style short labels
    _FALLBACK_OPS = {
        "退订困难/自动续费争议": "商业运营", "不知情订购": "商业运营",
        "重复扣费/多扣费": "商业运营", "无法订购/扣费失败": "商业运营",
        "订购入口难找": "商业运营",
        "权益无法兑换/使用": "商业运营", "APP卡顿": "商业运营",
        "APP闪退": "商业运营",
        "奖励/优惠未到账": "用户运营", "快递单号查询": "用户运营",
        "发放周期长": "用户运营", "无法查询中奖记录": "用户运营",
        "活动规则不清晰/找不到": "用户运营", "活动规则不清晰": "用户运营",
        "询问赛事门票发放时间": "用户运营",
        "多端体验差异": "内容运营", "音画不同步": "内容运营",
        "视频资讯资源不足": "内容运营", "赛事覆盖率低": "内容运营",
        "画质效果差": "内容运营", "内容陈旧/更新慢": "内容运营",
        "播放报错（黑屏/解码失败）": "内容运营", "权益价值感低": "内容运营",
    }
    _FALLBACK_PROD = {
        "退订困难/自动续费争议": "平台产品", "不知情订购": "平台产品",
        "重复扣费/多扣费": "平台产品", "无法订购/扣费失败": "平台产品",
        "订购入口难找": "平台产品", "权益无法兑换/使用": "平台产品",
        "APP卡顿": "平台产品", "APP闪退": "平台产品",
        "直播无法回看": "功能产品", "进度拖拽失效": "功能产品",
        "搜索结果不准确": "功能产品", "功能入口难找": "功能产品",
        "播放卡顿（含缓冲慢）": "功能产品", "播放卡顿": "功能产品",
        "权益查询不便": "功能产品", "发票开具困难": "功能产品",
        "多端体验差异": "内容产品", "音画不同步": "内容产品",
        "播放报错（黑屏/解码失败）": "内容产品", "视频资讯资源不足": "内容产品",
        "赛事覆盖率低": "内容产品", "画质效果差": "内容产品",
        "内容陈旧/更新慢": "内容产品", "权益价值感低": "内容产品",
    }

    def _fuzzy_match(label: str) -> tuple[str, str]:
        """Match label via exact, contains, or fallback."""
        if label in mapping:
            return mapping[label]
        # Try fuzzy: label in mapped or mapped in label
        for mapped_label, val in mapping.items():
            if label in mapped_label or mapped_label in label:
                return val
        # Hardcoded fallback
        op = _FALLBACK_OPS.get(label, "")
        prod = _FALLBACK_PROD.get(label, "")
        return (op, prod)

    ops_counts: dict[str, int] = {}
    prod_counts: dict[str, int] = {}
    ops_unmatched = 0
    prod_unmatched = 0
    mapping_table: list[dict] = []

    for item in tertiary_items:
        label = item.get("key", "")
        count = item.get("count", 0)
        op, prod = _fuzzy_match(label)
        if op:
            ops_counts[op] = ops_counts.get(op, 0) + count
        else:
            ops_unmatched += count
        if prod:
            prod_counts[prod] = prod_counts.get(prod, 0) + count
        else:
            prod_unmatched += count
        mapping_table.append({
            "tertiary_label": label,
            "count": count,
            "operation": op or "未归类",
            "product_level": prod or "未归类",
        })

    ops_result = [{"key": k, "count": v} for k, v in sorted(ops_counts.items(), key=lambda x: -x[1])]
    prod_result = [{"key": k, "count": v} for k, v in sorted(prod_counts.items(), key=lambda x: -x[1])]
    if ops_unmatched > 0:
        ops_result.append({"key": "未归类", "count": ops_unmatched})
    if prod_unmatched > 0:
        prod_result.append({"key": "未归类", "count": prod_unmatched})

    return ops_result, prod_result, mapping_table
