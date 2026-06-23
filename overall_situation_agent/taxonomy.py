from __future__ import annotations

import re
from typing import Any


CANONICAL_PRIMARY_TERTIARY: dict[str, list[str]] = {
    "使用体验": [
        "直播无法回看",
        "进度拖拽失效",
        "音画不同步",
        "搜索结果不准确（无法精准搜索、搜不到内容）",
        "功能、活动等入口难找",
        "多端体验有差异（操作一致性）",
        "播放卡顿（含缓冲慢）",
        "播放报错（含黑屏、解码失败）",
        "APP卡顿、打开速度慢",
        "APP闪退（特定版本/机型崩溃）",
    ],
    "内容体验": [
        "视频、资讯资源不足",
        "赛事覆盖率低",
        "画质效果差",
        "内容陈旧/更新慢",
    ],
    "业务体验": [
        "权益无法兑换/使用（如不知如何兑换、兑换失败）",
        "权益查询不便（如VIP权益入口）",
        "权益价值感低（如VIP权益可看内容少）",
        "发票开具困难（开发票慢、流程复杂等）",
        "无法订购/扣费失败",
        "订购入口难找",
        "不知情订购",
        "重复扣费/多扣费",
        "退订困难/自动续费争议",
    ],
    "营销活动": [
        "活动规则不清晰，找不到",
        "询问赛事门票发放时间",
        "奖励/优惠未到账，包括省侧流量、省侧话费、电影券未到账",
        "活动中奖后无法查询中奖记录",
        "咨询快递单号，中奖奖品快递单号无法在活动页面查看",
        "活动奖品发放周期过长，咨询实物奖品发放情况",
    ],
}


_ALIASES_BY_CANONICAL: dict[str, set[str]] = {
    "搜索结果不准确（无法精准搜索、搜不到内容）": {"搜索结果不准确", "无法精准搜索", "搜不到内容"},
    "功能、活动等入口难找": {"功能入口难找", "活动入口难找"},
    "多端体验有差异（操作一致性）": {"多端体验差异", "多端体验有差异"},
    "播放卡顿（含缓冲慢）": {"播放卡顿", "缓冲慢"},
    "播放报错（含黑屏、解码失败）": {"播放报错", "黑屏", "解码失败"},
    "视频、资讯资源不足": {"视频资讯资源不足", "视频资源不足", "资讯资源不足"},
    "权益无法兑换/使用（如不知如何兑换、兑换失败）": {"权益无法兑换/使用", "权益无法兑换", "兑换失败"},
    "权益查询不便（如VIP权益入口）": {"权益查询不便", "VIP权益入口"},
    "权益价值感低（如VIP权益可看内容少）": {"权益价值感低", "VIP权益可看内容少"},
    "发票开具困难（开发票慢、流程复杂等）": {"发票开具困难", "开发票慢"},
    "活动规则不清晰，找不到": {"活动规则不清晰/找不到", "活动规则不清晰", "找不到活动规则"},
    "奖励/优惠未到账，包括省侧流量、省侧话费、电影券未到账": {"奖励/优惠未到账", "省侧流量未到账", "省侧话费未到账", "电影券未到账"},
    "咨询快递单号，中奖奖品快递单号无法在活动页面查看": {"快递单号查询", "咨询快递单号"},
    "活动奖品发放周期过长，咨询实物奖品发放情况": {"发放周期长", "活动奖品发放周期过长"},
}


def _norm(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", "", text)
    return (
        text.replace("(", "（")
        .replace(")", "）")
        .replace(",", "，")
        .replace("、", "")
        .replace("，", "")
    )


_CANONICAL_BY_NORM: dict[str, str] = {}
_PRIMARY_BY_CANONICAL: dict[str, str] = {}
for _primary, _labels in CANONICAL_PRIMARY_TERTIARY.items():
    for _label in _labels:
        _PRIMARY_BY_CANONICAL[_label] = _primary
        _CANONICAL_BY_NORM[_norm(_label)] = _label
        for _alias in _ALIASES_BY_CANONICAL.get(_label, set()):
            _CANONICAL_BY_NORM[_norm(_alias)] = _label


def canonical_tertiary_label(label: Any) -> str:
    text = str(label or "").strip()
    if not text:
        return ""
    return _CANONICAL_BY_NORM.get(_norm(text), text)


def canonical_primary_for_tertiary(label: Any) -> str:
    return _PRIMARY_BY_CANONICAL.get(canonical_tertiary_label(label), "")


def _canonical_tertiary_counts(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    counts: dict[str, dict[str, Any]] = {}
    for item in result.get("tertiary", []) or []:
        raw_key = str(item.get("key", "")).strip()
        count = int(item.get("count", 0) or 0)
        canonical = canonical_tertiary_label(raw_key)
        if not raw_key or count <= 0 or canonical not in _PRIMARY_BY_CANONICAL:
            continue
        data = counts.setdefault(canonical, {"key": canonical, "count": 0, "source_counts": {}})
        data["count"] += count
        data["source_counts"][raw_key] = data["source_counts"].get(raw_key, 0) + count
    return counts


def primary_top_tertiary_items(
    result: dict[str, Any],
    primary_label: str,
    primary_count: int,
    limit: int = 5,
) -> list[dict[str, Any]]:
    allowed = CANONICAL_PRIMARY_TERTIARY.get(str(primary_label or "").strip(), [])
    canonical_counts = _canonical_tertiary_counts(result)
    items: list[dict[str, Any]] = []
    for canonical in allowed:
        data = canonical_counts.get(canonical)
        if not data:
            continue
        source_counts = data.get("source_counts", {})
        source_key = max(source_counts.items(), key=lambda pair: pair[1])[0] if source_counts else canonical
        count = int(data.get("count", 0) or 0)
        items.append(
            {
                "key": canonical,
                "source_key": source_key,
                "count": count,
                "share": f"{(count / primary_count * 100):.1f}%" if primary_count else "0.0%",
            }
        )
    return sorted(items, key=lambda item: int(item.get("count", 0) or 0), reverse=True)[:limit]


def collect_md_tertiary_items(
    result: dict[str, Any],
    top_primary: int = 5,
    top_tertiary_per_primary: int = 5,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    primary_items = [
        item for item in (result.get("primary", []) or [])
        if str(item.get("key", "")).strip() in CANONICAL_PRIMARY_TERTIARY
    ][:top_primary]
    for primary in primary_items:
        primary_key = str(primary.get("key", "")).strip()
        primary_count = int(primary.get("count", 0) or 0)
        top_items = primary_top_tertiary_items(result, primary_key, primary_count, limit=top_tertiary_per_primary)
        if not top_items:
            raise RuntimeError(f"一级标签无法按权威 taxonomy 找到三级数据：{primary_key}")
        for item in top_items:
            canonical = str(item.get("key", "")).strip()
            if canonical in seen:
                continue
            seen.add(canonical)
            items.append({**item, "primary_key": primary_key, "primary_count": primary_count})
    return items

