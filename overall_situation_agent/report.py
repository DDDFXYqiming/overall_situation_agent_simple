from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from html import escape
from pathlib import Path
from typing import Any

from .report_context import build_report_context
from .sanitization import mask_sensitive_text, sanitize_report_payload
from .style_guard import enforce_style_contract
from .taxonomy import CANONICAL_PRIMARY_TERTIARY, canonical_tertiary_label, primary_top_tertiary_items

CHART_COLORS = ["#0052FF", "#4D7CFF", "#38BDF8", "#22C55E", "#F97316", "#A855F7", "#64748B", "#0F172A"]


# ── 四个运营维度 & 四个产品层次映射 ──────────────────────────────────
# Based on: supplementary tertiary-label mapping file
FOUR_OPS_MAP = {
    # 商业运营
    "无法订购/扣费失败": "商业运营",
    "订购入口难找": "商业运营",
    "不知情订购": "商业运营",
    "重复扣费/多扣费": "商业运营",
    "退订困难/自动续费争议": "商业运营",
    "发票开具困难": "商业运营",
    "APP卡顿": "商业运营",
    "APP卡顿、打开速度慢": "商业运营",
    "APP闪退": "商业运营",
    "APP闪退（特定版本/机型崩溃）": "商业运营",
    "权益无法兑换/使用": "商业运营",
    "权益无法兑换/使用（如不知如何兑换、兑换失败）": "商业运营",
    # 用户运营
    "活动规则不清晰/找不到": "用户运营",
    "活动规则不清晰，找不到": "用户运营",
    "活动规则不清晰": "用户运营",
    "询问赛事门票发放时间": "用户运营",
    "奖励/优惠未到账": "用户运营",
    "奖励/优惠未到账，包括省侧流量、省侧话费、电影券未到账": "用户运营",
    "快递单号查询": "用户运营",
    "咨询快递单号，中奖奖品快递单号无法在活动页面查看": "用户运营",
    "发放周期长": "用户运营",
    "活动奖品发放周期过长，咨询实物奖品发放情况": "用户运营",
    "无法查询中奖记录": "用户运营",
    "活动中奖后无法查询中奖记录": "用户运营",
    # 内容运营
    "视频资讯资源不足": "内容运营",
    "视频、资讯资源不足": "内容运营",
    "赛事覆盖率低": "内容运营",
    "画质效果差": "内容运营",
    "内容陈旧/更新慢": "内容运营",
    "音画不同步": "内容运营",
    "多端体验差异": "内容运营",
    "多端体验有差异": "内容运营",
    "多端体验有差异（操作一致性）": "内容运营",
    "播放报错（黑屏/解码失败）": "内容运营",
    "播放报错": "内容运营",
    "权益价值感低": "内容运营",
    "权益价值感低（如VIP权益可看内容少）": "内容运营",
    # 平台运营
    "直播无法回看": "平台运营",
    "进度拖拽失效": "平台运营",
    "搜索结果不准确": "平台运营",
    "搜索结果不准确（无法精准搜索、搜不到内容）": "平台运营",
    "功能入口难找": "平台运营",
    "功能、活动等入口难找": "平台运营",
    "播放卡顿（含缓冲慢）": "平台运营",
    "播放卡顿": "平台运营",
    "权益查询不便": "平台运营",
    "权益查询不便（如VIP权益入口）": "平台运营",
    "发票开具困难（开发票慢、流程复杂等）": "平台运营",
}

FOUR_PRODUCTS_MAP = {
    # 平台产品
    "APP卡顿": "平台产品",
    "APP卡顿、打开速度慢": "平台产品",
    "APP闪退": "平台产品",
    "APP闪退（特定版本/机型崩溃）": "平台产品",
    "权益无法兑换/使用": "平台产品",
    "权益无法兑换/使用（如不知如何兑换、兑换失败）": "平台产品",
    "无法订购/扣费失败": "平台产品",
    "订购入口难找": "平台产品",
    "不知情订购": "平台产品",
    "重复扣费/多扣费": "平台产品",
    "退订困难/自动续费争议": "平台产品",
    # 内容产品
    "音画不同步": "内容产品",
    "多端体验差异": "内容产品",
    "多端体验有差异": "内容产品",
    "多端体验有差异（操作一致性）": "内容产品",
    "播放报错（黑屏/解码失败）": "内容产品",
    "播放报错": "内容产品",
    "视频资讯资源不足": "内容产品",
    "视频、资讯资源不足": "内容产品",
    "赛事覆盖率低": "内容产品",
    "画质效果差": "内容产品",
    "内容陈旧/更新慢": "内容产品",
    "权益价值感低": "内容产品",
    "权益价值感低（如VIP权益可看内容少）": "内容产品",
    # 功能产品
    "直播无法回看": "功能产品",
    "进度拖拽失效": "功能产品",
    "搜索结果不准确": "功能产品",
    "搜索结果不准确（无法精准搜索、搜不到内容）": "功能产品",
    "功能入口难找": "功能产品",
    "功能、活动等入口难找": "功能产品",
    "播放卡顿（含缓冲慢）": "功能产品",
    "播放卡顿": "功能产品",
    "权益查询不便": "功能产品",
    "权益查询不便（如VIP权益入口）": "功能产品",
    "发票开具困难": "功能产品",
    "发票开具困难（开发票慢、流程复杂等）": "功能产品",
    # 工具产品
    "活动规则不清晰/找不到": "工具产品",
    "活动规则不清晰，找不到": "工具产品",
    "活动规则不清晰": "工具产品",
    "询问赛事门票发放时间": "工具产品",
    "奖励/优惠未到账": "工具产品",
    "奖励/优惠未到账，包括省侧流量、省侧话费、电影券未到账": "工具产品",
    "快递单号查询": "工具产品",
    "咨询快递单号，中奖奖品快递单号无法在活动页面查看": "工具产品",
    "发放周期长": "工具产品",
    "活动奖品发放周期过长，咨询实物奖品发放情况": "工具产品",
    "无法查询中奖记录": "工具产品",
    "活动中奖后无法查询中奖记录": "工具产品",
}

def _map_tertiary_to_ops(label: str) -> str:
    """Map a tertiary label to its four-ops dimension."""
    if label in FOUR_OPS_MAP:
        return FOUR_OPS_MAP[label]
    # Fuzzy match: try partial match
    for key, val in FOUR_OPS_MAP.items():
        if key in label or label in key:
            return val
    return "平台运营"

def _map_tertiary_to_product(label: str) -> str:
    """Map a tertiary label to its four-products level."""
    if label in FOUR_PRODUCTS_MAP:
        return FOUR_PRODUCTS_MAP[label]
    for key, val in FOUR_PRODUCTS_MAP.items():
        if key in label or label in key:
            return val
    return "工具产品"



def _e(value: Any) -> str:
    return escape("" if value is None else str(value))


def _n(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return _e(value)


def _strip_emoji(text: str) -> str:
    try:
        import re
        emoji_pattern = re.compile(
            "[\U0001F600-\U0001F64F"       # Emoticons
            "\U0001F300-\U0001F5FF"        # Misc Symbols and Pictographs
            "\U0001F680-\U0001F6FF"        # Transport and Map
            "\U0001F1E0-\U0001F1FF"        # Flags (Regional Indicators)
            "\U00002702-\U000027B0"        # Dingbats
            "\U0001F900-\U0001F9FF"        # Supplemental Symbols
            "\U00002300-\U000023FF"        # Miscellaneous Technical
            "\U00002B50\U00002B55"         # Star, Heavy Circle
            "\U0000FE00-\U0000FE0F"        # Variation Selectors
            "\U0000200D"                   # Zero Width Joiner
            "\U000020E3"                   # Combining Enclosing Keycap
            "]",
            flags=re.UNICODE)
        return emoji_pattern.sub("", text).strip()
    except Exception:
        return text.strip()


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _sum_counts(items: list[dict]) -> int:
    return int(sum(item.get("count", 0) for item in items))


def _safe_ratio(part: float, whole: float) -> float:
    return part / whole if whole else 0


def _tags(items: list[dict], total: int | None = None) -> str:
    denom = total if total is not None else sum(item.get("count", 0) for item in items)
    tags = []
    for item in items:
        count = item.get("count", 0)
        pct = f"{count / denom * 100:.1f}%" if denom > 0 else "0.0%"
        tags.append(
            f'<span class="tag"><span class="tag-text">{_e(item["key"])}</span><strong>共{_n(count)}条，占比{pct}</strong></span>'
        )
    return "".join(tags)


def _key_text(items: list[Any], limit: int = 3) -> str:
    keys = []
    for item in (items or [])[:limit]:
        value = item.get("key") if isinstance(item, dict) else item
        text = str(value or "").strip()
        if text:
            keys.append(text)
    return "、".join(keys) or "无"


_RAW_DIALOG_MARKERS = ('"消息内容"', "'消息内容'", '{"发送方"', "[{")
_BOILERPLATE_MARKERS = (
    "正在为您转接人工",
    "当前人工MM有点忙",
    "请稍后",
    "请耐心等待",
    "您好，很高兴为您服务",
    "请问有什么可以帮到您",
)


def _looks_like_raw_dialog(value: Any) -> bool:
    text = str(value or "")
    return any(marker in text for marker in _RAW_DIALOG_MARKERS)


def _clean_message_text(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[A-Z0-9]{12,}", "", text)
    return text.strip(" ;；,，。")


def _extract_dialog_messages(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []

    def collect(payload: Any) -> tuple[list[str], list[str]]:
        user_messages: list[str] = []
        other_messages: list[str] = []
        if isinstance(payload, list):
            for entry in payload:
                user_part, other_part = collect(entry)
                user_messages.extend(user_part)
                other_messages.extend(other_part)
        elif isinstance(payload, dict):
            message = _clean_message_text(
                payload.get("消息内容")
                or payload.get("message")
                or payload.get("content")
                or payload.get("工单内容")
                or payload.get("工单投诉内容")
            )
            sender = str(payload.get("发送方") or payload.get("sender") or "")
            if message:
                if any(marker in message for marker in _BOILERPLATE_MARKERS):
                    return user_messages, other_messages
                if "用户" in sender or "客户" in sender:
                    user_messages.append(message)
                else:
                    other_messages.append(message)
        return user_messages, other_messages

    parsed_messages: list[str] = []
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed = None
    if parsed is not None:
        user_messages, other_messages = collect(parsed)
        parsed_messages = user_messages or other_messages

    if not parsed_messages:
        matches = re.findall(r'["“]消息内容["”]\s*[:：]\s*["“](.*?)["”]', text)
        parsed_messages = [_clean_message_text(match) for match in matches]

    if not parsed_messages and not _looks_like_raw_dialog(text):
        parsed_messages = [_clean_message_text(text)]

    deduped: list[str] = []
    seen: set[str] = set()
    for message in parsed_messages:
        if not message or any(marker in message for marker in _BOILERPLATE_MARKERS):
            continue
        if message in seen:
            continue
        seen.add(message)
        deduped.append(message)
    return deduped


def _natural_sample_summary(value: Any, issue: str = "") -> str:
    messages = _extract_dialog_messages(value)
    if not messages:
        return "样例主要反映用户在相关业务办理或观看过程中遇到体验阻断，需要结合问题标签进一步核验。"
    combined = " ".join(messages[:3])
    points: list[str] = []
    if any(word in combined for word in ("退费", "退款", "退订", "不退")):
        points.append("退订或退费处理结果不符合预期")
    if any(word in combined for word in ("电视", "TV", "tv", "投屏", "大屏")):
        points.append("电视端或投屏观看权益受阻")
    if any(word in combined for word in ("手机", "多端", "四屏", "互通")):
        points.append("手机端与电视端权益互通规则不清")
    if any(word in combined for word in ("价格", "168", "219", "218", "258", "套餐", "补差")):
        points.append("套餐价格和权益差异理解成本高")
    if any(word in combined for word in ("会员", "权益", "兑换", "钻石")):
        points.append("会员权益兑现与用户预期存在落差")
    if any(word in combined for word in ("扣费", "订购", "误购", "自动续费", "不知情")):
        points.append("订购扣费或自动续费流程引发争议")
    if not points:
        points.append("相关业务办理或观看过程存在体验阻断")
    joined = "，并且".join(dict.fromkeys(points[:3]))
    topic = f"「{issue}」" if issue else "该问题"
    return f"样例中，用户围绕{topic}主要投诉{joined}。"


def _narrative_line_at(lines: list[str] | None, index: int) -> str:
    if not lines or index >= len(lines):
        return ""
    line = str(lines[index] or "").strip()
    return "" if _looks_like_raw_dialog(line) else line


def _bar_rows(items: list[dict], alt: bool = False, total: int | None = None) -> str:
    visible = [item for item in items if item.get("count", 0) > 0]
    if not visible:
        return '<p class="subtle">暂无可展示数据。</p>'
    max_value = max(item["count"] for item in visible) or 1
    denom = total if total is not None else sum(item["count"] for item in visible)
    cls = "bar-fill alt" if alt else "bar-fill"
    rows = []
    for item in visible:
        count = item["count"]
        width = round(count / max_value * 100, 1) if max_value else 0
        pct = f"{count / denom * 100:.1f}%" if denom > 0 else "0.0%"
        rows.append(
            f"""
            <div class="bar-row">
              <div class="bar-label">{_e(item["key"])}</div>
              <div class="bar-track"><div class="{cls}" style="--target-width:{width}%"></div></div>
              <div class="bar-value">共{_n(count)}条，占比{pct}</div>
            </div>
            """
        )
    return "".join(rows)


def _polar_to_xy(cx: float, cy: float, radius: float, angle: float) -> tuple[float, float]:
    radians = math.radians(angle - 90)
    return cx + radius * math.cos(radians), cy + radius * math.sin(radians)


def _wedge_path(cx: float, cy: float, radius: float, start_angle: float, end_angle: float) -> str:
    start_x, start_y = _polar_to_xy(cx, cy, radius, start_angle)
    end_x, end_y = _polar_to_xy(cx, cy, radius, end_angle)
    large_arc = 1 if end_angle - start_angle > 180 else 0
    return f"M {cx:.2f} {cy:.2f} L {start_x:.2f} {start_y:.2f} A {radius:.2f} {radius:.2f} 0 {large_arc} 1 {end_x:.2f} {end_y:.2f} Z"


def _donut_chart(items: list[dict], title: str, total_label: str) -> str:
    positive = [item for item in items if item.get("count", 0) > 0]
    if len(positive) > 6:
        visible = [dict(item) for item in positive[:5]]
        remainder_count = _sum_counts(positive[5:])
        other_bucket = next((item for item in visible if item.get("key") == "其他"), None)
        if other_bucket:
            other_bucket["count"] = int(other_bucket.get("count", 0)) + remainder_count
        else:
            visible.append({"key": "其他", "count": remainder_count})
    else:
        visible = positive[:6]
    total = _sum_counts(visible)
    if not visible or total == 0:
        return '<section class="chart-card" data-reveal="card"><p class="subtle">暂无可绘制的类型分布数据。</p></section>'

    cx, cy, radius = 116, 116, 88
    angle = 0.0
    slices = []
    legend = []
    for idx, item in enumerate(visible):
        color = CHART_COLORS[idx % len(CHART_COLORS)]
        share = _safe_ratio(item["count"], total)
        next_angle = angle + share * 360
        if share >= 0.999:
            slices.append(f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="{color}" />')
        else:
            slices.append(f'<path d="{_wedge_path(cx, cy, radius, angle, next_angle)}" fill="{color}" />')
        legend.append(
            f"""
            <div class="legend-row">
              <span class="legend-swatch" style="background:{color}"></span>
              <span class="legend-name">{_e(item["key"])}</span>
              <strong>{item["count"]}</strong>
              <span class="legend-share">{_pct(share)}</span>
            </div>
            """
        )
        angle = next_angle

    return f"""
    <section class="chart-card chart-card-highlight" data-reveal="card">
      <div class="chart-header">
        <div>
          <span class="chart-kicker">PIE CHART</span>
          <h3>{_e(title)}</h3>
        </div>
      </div>
      <div class="pie-layout">
        <svg class="donut-chart" viewBox="0 0 232 232" role="img" aria-label="{_e(title)}">
          {''.join(slices)}
          <circle cx="{cx}" cy="{cy}" r="50" fill="#FFFFFF" />
          <text x="{cx}" y="{cy - 3}" text-anchor="middle" class="donut-total">{total}</text>
          <text x="{cx}" y="{cy + 19}" text-anchor="middle" class="donut-caption">{_e(total_label)}</text>
        </svg>
        <div class="legend-stack">{''.join(legend)}</div>
      </div>
    </section>
    """


def _top_bar_chart(items: list[dict]) -> str:
    visible = [item for item in items[:5] if item.get("count", 0) > 0]
    if not visible:
        return '<section class="chart-card" data-reveal="card"><p class="subtle">暂无 TOP 问题数据。</p></section>'
    max_value = max(item["count"] for item in visible) or 1
    rows = []
    for idx, item in enumerate(visible, start=1):
        width = round(item["count"] / max_value * 100, 1)
        rows.append(
            f"""
            <div class="rank-row">
              <div class="rank-index">{idx:02d}</div>
              <div class="rank-label">{_e(item["key"])}</div>
              <div class="rank-track"><div class="rank-fill" style="--target-width:{width}%"></div></div>
              <div class="rank-value">{item["count"]}</div>
            </div>
            """
        )
    return f"""
    <section class="chart-card" data-reveal="card">
      <div class="chart-header">
        <div>
          <span class="chart-kicker">BAR CHART</span>
          <h3>TOP5 三级问题提及量</h3>
        </div>
      </div>
      <div class="rank-chart">{''.join(rows)}</div>
    </section>
    """


def _label_drilldown_table(items: list[dict], total: int) -> str:
    if not items:
        return '<section class="chart-card chart-grid-wide" data-reveal="card"><p class="subtle">暂无可展示的标签下钻关系。</p></section>'

    rows = []
    for primary in items:
        primary_count = int(primary.get("count", 0))
        secondaries = [item for item in primary.get("secondary", []) if item.get("count", 0) > 0]
        if not secondaries:
            rows.append(
                f"""
                <tr>
                  <td>{_e(primary["key"])}</td>
                  <td>{_n(primary_count)}</td>
                  <td>{_pct(_safe_ratio(primary_count, total))}</td>
                  <td>无</td>
                  <td>0</td>
                  <td>0.0%</td>
                  <td>无</td>
                  <td>0</td>
                  <td>0.0%</td>
                </tr>
                """
            )
            continue

        for secondary in secondaries:
            secondary_count = int(secondary.get("count", 0))
            tertiaries = [item for item in secondary.get("tertiary", []) if item.get("count", 0) > 0]
            if not tertiaries:
                rows.append(
                    f"""
                    <tr>
                      <td>{_e(primary["key"])}</td>
                      <td>{_n(primary_count)}</td>
                      <td>{_pct(_safe_ratio(primary_count, total))}</td>
                      <td>{_e(secondary["key"])}</td>
                      <td>{_n(secondary_count)}</td>
                      <td>{_pct(_safe_ratio(secondary_count, primary_count))}</td>
                      <td>无</td>
                      <td>0</td>
                      <td>0.0%</td>
                    </tr>
                    """
                )
                continue

            for tertiary in tertiaries:
                tertiary_count = int(tertiary.get("count", 0))
                rows.append(
                    f"""
                    <tr>
                      <td>{_e(primary["key"])}</td>
                      <td>{_n(primary_count)}</td>
                      <td>{_pct(_safe_ratio(primary_count, total))}</td>
                      <td>{_e(secondary["key"])}</td>
                      <td>{_n(secondary_count)}</td>
                      <td>{_pct(_safe_ratio(secondary_count, primary_count))}</td>
                      <td>{_e(tertiary["key"])}</td>
                      <td>{_n(tertiary_count)}</td>
                      <td>{_pct(_safe_ratio(tertiary_count, secondary_count))}</td>
                    </tr>
                    """
                )

    return f"""
    <section class="chart-card chart-grid-wide" data-reveal="card">
      <div class="chart-header">
        <div>
          <span class="chart-kicker">LABEL DRILLDOWN</span>
          <h3>各级标签下钻关系表</h3>
        </div>
      </div>
      <div class="narrative-stack">
        <p>按“一级标签 → 二级标签 → 三级标签”路径展开，展示每级标签在当前层级中的占比，以及它与上下级标签的对应关系。</p>
      </div>
      <div class="table-scroll">
        <table class="data-table drilldown-table">
          <thead>
            <tr>
              <th>一级标签</th>
              <th>一级提及量</th>
              <th>一级占比</th>
              <th>二级标签</th>
              <th>二级提及量</th>
              <th>二级在一级内占比</th>
              <th>三级标签</th>
              <th>三级提及量</th>
              <th>三级在二级内占比</th>
            </tr>
          </thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    </section>
    """


def _event_label(day: dict) -> str:
    events = []
    for item in day.get("top_events", []):
        key = str(item.get("key", ""))
        if key and key not in {"无", "其他", "未标注", "不适用"}:
            events.append(f"{key}({item.get('count', 0)})")
    return "、".join(events[:2])


def _matchday(day: dict) -> dict[str, Any] | None:
    if day.get("is_matchday") and day.get("matchday"):
        return day["matchday"]
    return None


def _matchday_summary(day: dict) -> str:
    payload = _matchday(day)
    if not payload:
        return ""
    return str(payload.get("match_summary", "")).strip()


def _matchday_round_text(day: dict) -> str:
    payload = _matchday(day)
    if not payload:
        return ""
    rounds = [str(item).strip() for item in payload.get("rounds", []) if str(item).strip()]
    return "、".join(rounds)


def _matchday_count(day: dict) -> int:
    payload = _matchday(day)
    return int(payload.get("match_count", 0)) if payload else 0


def _schedule_status(result: dict) -> dict[str, Any]:
    return result.get("schedule") or {"status": "missing", "message": "未提供赛程文件，1.2 未标注赛事日。", "days": {}}


def _matchday_pill(day: dict, dark: bool = False) -> str:
    if _matchday(day):
        cls = "match-pill match-pill-dark" if dark else "match-pill"
        return f'<span class="{cls}">赛事日</span>'
    cls = "match-pill match-pill-muted-dark" if dark else "match-pill match-pill-muted"
    return f'<span class="{cls}">非赛事日</span>'


def _matchday_cell(day: dict, dark: bool = False) -> str:
    summary = _matchday_summary(day)
    scene_event = _event_label(day)
    parts = [f'<div class="day-marker">', _matchday_pill(day, dark)]
    if summary:
        parts.append(f'<div class="day-marker-copy"><strong>{_e(summary)}</strong>')
        if scene_event:
            parts.append(f'<span class="day-marker-subtle">补充线索：{_e(scene_event)}</span>')
        parts.append("</div>")
    else:
        parts.append('<div class="day-marker-copy"><strong>当日未匹配到活动日历</strong>')
        if scene_event:
            parts.append(f'<span class="day-marker-subtle">补充线索：{_e(scene_event)}</span>')
        parts.append("</div>")
    parts.append("</div>")
    return "".join(parts)


def _matchday_note(result: dict, trend_view: dict[str, Any]) -> str:
    schedule = _schedule_status(result)
    if schedule.get("status") == "loaded":
        if any(_matchday(day) for day in trend_view.get("days", [])):
            return f"赛事日根据运行时传入的赛程文件《{_e(schedule.get('source_name'))}》按日期标注。"
        return f"已加载赛程文件《{_e(schedule.get('source_name'))}》，但当前趋势窗口未匹配到赛程日期。"
    return str(schedule.get("message") or "未提供赛程文件，1.2 未标注赛事日。")


def _parse_day(value: str) -> date:
    return datetime.fromisoformat(value[:10]).date()


def _nice_upper_bound(value: int) -> int:
    if value <= 0:
        return 1
    magnitude = 10 ** int(math.floor(math.log10(value)))
    normalized = value / magnitude
    if normalized <= 1:
        factor = 1
    elif normalized <= 2:
        factor = 2
    elif normalized <= 3:
        factor = 3
    elif normalized <= 4:
        factor = 4
    elif normalized <= 5:
        factor = 5
    elif normalized <= 6:
        factor = 6
    elif normalized <= 8:
        factor = 8
    else:
        factor = 10
    return int(factor * magnitude)


def _build_trend_view(daily: list[dict], filters: dict | None = None, anomalies: list[dict] | None = None) -> dict[str, Any]:
    anomalies = anomalies or []
    if not daily:
        return {
            "days": [],
            "anomalies": [],
            "used_focus_window": False,
            "start": None,
            "end": None,
            "trimmed_count": 0,
            "trimmed_active_days": 0,
            "note": "",
        }

    filters = filters or {}
    if filters.get("start_date") or filters.get("end_date"):
        return {
            "days": daily,
            "anomalies": anomalies,
            "used_focus_window": False,
            "start": daily[0]["date"],
            "end": daily[-1]["date"],
            "trimmed_count": 0,
            "trimmed_active_days": 0,
            "note": "当前按用户指定的完整查询周期展示每日趋势。",
        }

    active_entries = [(index, day, _parse_day(day["date"])) for index, day in enumerate(daily) if day.get("count", 0) > 0]
    if len(active_entries) <= 1:
        return {
            "days": daily,
            "anomalies": anomalies,
            "used_focus_window": False,
            "start": daily[0]["date"],
            "end": daily[-1]["date"],
            "trimmed_count": 0,
            "trimmed_active_days": 0,
            "note": "当前按完整查询周期展示每日趋势。",
        }

    segments: list[dict[str, Any]] = []
    current = {
        "start_index": active_entries[0][0],
        "end_index": active_entries[0][0],
        "start_date": active_entries[0][1]["date"],
        "end_date": active_entries[0][1]["date"],
        "total_count": active_entries[0][1]["count"],
        "active_days": 1,
    }
    previous_date = active_entries[0][2]

    for index, day, current_date in active_entries[1:]:
        if (current_date - previous_date).days > 14:
            segments.append(current)
            current = {
                "start_index": index,
                "end_index": index,
                "start_date": day["date"],
                "end_date": day["date"],
                "total_count": day["count"],
                "active_days": 1,
            }
        else:
            current["end_index"] = index
            current["end_date"] = day["date"]
            current["total_count"] += day["count"]
            current["active_days"] += 1
        previous_date = current_date
    segments.append(current)

    if len(segments) == 1:
        return {
            "days": daily,
            "anomalies": anomalies,
            "used_focus_window": False,
            "start": daily[0]["date"],
            "end": daily[-1]["date"],
            "trimmed_count": 0,
            "trimmed_active_days": 0,
            "note": "当前按完整查询周期展示每日趋势。",
        }

    total_count = sum(day.get("count", 0) for day in daily)
    active_total = sum(1 for day in daily if day.get("count", 0) > 0)
    dominant = max(segments, key=lambda item: (item["total_count"], item["active_days"]))
    trimmed_count = total_count - int(dominant["total_count"])
    trimmed_active_days = active_total - int(dominant["active_days"])
    dominant_span = int(dominant["end_index"]) - int(dominant["start_index"]) + 1

    if total_count == 0 or trimmed_count <= 0 or dominant["total_count"] / total_count < 0.85 or dominant_span >= len(daily) * 0.85:
        return {
            "days": daily,
            "anomalies": anomalies,
            "used_focus_window": False,
            "start": daily[0]["date"],
            "end": daily[-1]["date"],
            "trimmed_count": 0,
            "trimmed_active_days": 0,
            "note": "当前按完整查询周期展示每日趋势。",
        }

    view_days = daily[int(dominant["start_index"]) : int(dominant["end_index"]) + 1]
    start_date = view_days[0]["date"]
    end_date = view_days[-1]["date"]
    view_anomalies = [day for day in anomalies if start_date <= day["date"] <= end_date]
    return {
        "days": view_days,
        "anomalies": view_anomalies,
        "used_focus_window": True,
        "start": start_date,
        "end": end_date,
        "trimmed_count": trimmed_count,
        "trimmed_active_days": trimmed_active_days,
        "note": (
            f"图表聚焦主分析时段 {start_date} 至 {end_date}；未绘制此前 {trimmed_active_days} 个零散活跃日"
            f"（共 {trimmed_count} 件），避免稀疏历史点压缩当前趋势。"
        ),
    }


def _source_files_text(items: list[dict]) -> str:
    names = [str(item.get("key", "")).strip() for item in items if str(item.get("key", "")).strip()]
    return "、".join(names) if names else "当前导入的已打标服务数据"


def _trend_svg(daily: list[dict], focus_note: str | None = None) -> str:
    if not daily:
        return '<section class="chart-card" data-reveal="card"><p class="subtle">暂无趋势数据。</p></section>'

    width, height = 1120, 460
    left, right, top, bottom = 74, 92, 58, 90
    plot_w = width - left - right
    plot_h = height - top - bottom
    max_count = max(day["count"] for day in daily) or 1
    count_axis_max = _nice_upper_bound(max_count)
    denom = len(daily) - 1 if len(daily) > 1 else 1

    def x_at(index: int) -> float:
        return left + index * plot_w / denom

    def y_count(value: float) -> float:
        return top + (1 - value / count_axis_max) * plot_h

    def y_ratio(value: float) -> float:
        return top + (1 - value) * plot_h

    count_points = [(x_at(i), y_count(day["count"])) for i, day in enumerate(daily)]
    ratio_points = [(x_at(i), y_ratio(day["negative_ratio"])) for i, day in enumerate(daily)]
    count_path = " ".join(f"{x:.1f},{y:.1f}" for x, y in count_points)
    ratio_path = " ".join(f"{x:.1f},{y:.1f}" for x, y in ratio_points)

    grid_lines = []
    for i in range(5):
        y = top + i * plot_h / 4
        count_tick = int(round(count_axis_max * (1 - i / 4)))
        ratio_tick = 1 - i / 4
        grid_lines.append(
            f"""
            <line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" stroke="rgba(15,23,42,0.09)" />
            <text x="{left - 14}" y="{y + 4:.1f}" text-anchor="end" class="axis-tick">{count_tick}</text>
            <text x="{width - right + 14}" y="{y + 4:.1f}" class="axis-tick">{ratio_tick:.2f}</text>
            """
        )

    x_labels = []
    event_marks = []
    point_marks = []
    label_step = max(1, math.ceil(len(daily) / 8))
    event_candidates = [(idx, day) for idx, day in enumerate(daily) if day.get("count", 0) > 0 and _matchday(day)]
    if len(event_candidates) > 8:
        event_candidates = sorted(event_candidates, key=lambda item: item[1].get("count", 0), reverse=True)[:8]
        event_candidates.sort(key=lambda item: item[0])
    event_index_set = {idx for idx, _ in event_candidates}

    peak = max(daily, key=lambda item: item["count"])
    peak_idx = daily.index(peak)
    marker_step = max(1, len(daily) // 24)
    marker_indices = set(range(0, len(daily), marker_step))
    marker_indices.update({0, len(daily) - 1, peak_idx})
    marker_indices.update(event_index_set)
    event_summary = []

    for idx, day in enumerate(daily):
        x = x_at(idx)
        if idx % label_step == 0 or idx == len(daily) - 1:
            x_labels.append(f'<text x="{x:.1f}" y="{height - 34}" text-anchor="middle" class="axis-tick">{_e(day["date"][5:])}</text>')

        if idx in marker_indices:
            cx, cy = count_points[idx]
            rx, ry = ratio_points[idx]
            outer_circle = ""
            if day.get("day_over_day_growth", 0) >= 0.5 and _matchday(day):
                outer_circle = f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="9" fill="none" stroke="#9EB6FF" stroke-width="2" />'
            point_marks.append(
                f"""
                {outer_circle}
                <circle cx="{cx:.1f}" cy="{cy:.1f}" r="4.6" fill="#4D7CFF" />
                <circle cx="{rx:.1f}" cy="{ry:.1f}" r="4.6" fill="#F97316" />
                """
            )

        if idx in event_index_set:
            event = _matchday_summary(day)
            highlight_cls = "event-pill event-pill-strong"
            if day["date"] == peak["date"]:
                highlight_cls += " event-pill-peak"
            event_summary.append(
                f'<span class="{highlight_cls}"><strong>{_e(day["date"][5:])}</strong><span>{_e(event)}</span></span>'
            )
            event_marks.append(
                f"""
                <line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{height - bottom}" stroke="rgba(77,124,255,0.46)" stroke-dasharray="4 7" />
                """
            )

    peak_x, peak_y = count_points[peak_idx]
    peak_box_width = 168
    peak_box_x = min(max(peak_x + 14, left + 10), width - right - peak_box_width)
    peak_box_y = max(16, peak_y - 48)
    peak_box_fill = "rgba(0,82,255,0.10)" if _matchday(peak) else "rgba(255,255,255,0.92)"
    peak_box_stroke = "rgba(0,82,255,0.34)" if _matchday(peak) else "rgba(15,23,42,0.08)"
    peak_text = f"峰值 {peak['date'][5:]} | {peak['count']} 件"
    if _matchday(peak):
        peak_text += " | 赛事日"
    focus_note_html = f'<p class="trend-note">{_e(focus_note)}</p>' if focus_note else ""

    return f"""
    <section class="chart-card chart-card-highlight" data-reveal="card">
      <div class="chart-header">
        <div>
          <span class="chart-kicker">LINE CHART</span>
          <h3>每日问题提及量与负向情绪占比</h3>
        </div>
      </div>
      <svg class="trend-svg" viewBox="0 0 {width} {height}" role="img" aria-label="每日问题提及量与负向情绪占比折线图">
        <defs>
          <linearGradient id="countGlow" x1="0%" x2="100%">
            <stop offset="0%" stop-color="#0052FF" />
            <stop offset="100%" stop-color="#4D7CFF" />
          </linearGradient>
          <linearGradient id="ratioGlow" x1="0%" x2="100%">
            <stop offset="0%" stop-color="#F97316" />
            <stop offset="100%" stop-color="#FDBA74" />
          </linearGradient>
        </defs>
        <rect x="0" y="0" width="{width}" height="{height}" rx="8" fill="#FFFFFF" stroke="rgba(15,23,42,0.08)" />
        {''.join(grid_lines)}
        <line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" stroke="rgba(15,23,42,0.14)" />
        <line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" stroke="rgba(15,23,42,0.14)" />
        <line x1="{width - right}" y1="{top}" x2="{width - right}" y2="{height - bottom}" stroke="rgba(15,23,42,0.14)" />
        {''.join(event_marks)}
        <polyline points="{count_path}" fill="none" stroke="url(#countGlow)" stroke-width="4.5" stroke-linejoin="round" stroke-linecap="round" />
        <polyline points="{ratio_path}" fill="none" stroke="url(#ratioGlow)" stroke-width="4.5" stroke-linejoin="round" stroke-linecap="round" />
        {''.join(point_marks)}
        <g>
          <rect x="{peak_box_x:.1f}" y="{peak_box_y:.1f}" width="{peak_box_width}" height="32" rx="8" fill="{peak_box_fill}" stroke="{peak_box_stroke}" />
          <text x="{peak_box_x + peak_box_width / 2:.1f}" y="{peak_box_y + 21:.1f}" text-anchor="middle" fill="#0F172A" font-size="13">{_e(peak_text)}</text>
        </g>
        {''.join(x_labels)}
        <text x="{left}" y="30" class="axis-title">问题量</text>
        <text x="{width - right}" y="30" text-anchor="end" class="axis-title">负向情绪占比</text>
      </svg>
      <div class="legend">
        <span><i class="dot count"></i>问题量</span>
        <span><i class="dot negative"></i>负向情绪占比（替代指数）</span>
        <span><i class="dot event"></i>赛事日</span>
      </div>
      <div class="event-summary">{''.join(event_summary) if event_summary else '<span class="subtle">当前周期未匹配到可标注的赛事日。</span>'}</div>
      {focus_note_html}
    </section>
    """


def _daily_rows(daily: list[dict]) -> str:
    rows = []
    for day in daily:
        growth = day.get("day_over_day_growth")
        growth_text = "首日" if growth is None else _pct(growth)
        rows.append(
            f"""
            <tr>
              <td>{_e(day["date"])}</td>
              <td>{day["count"]}</td>
              <td>{growth_text}</td>
              <td>{day["negative_count"]}</td>
              <td>{_pct(day["negative_ratio"])}</td>
              <td>{_matchday_cell(day)}</td>
              <td>{_tags(day.get("top_tertiary", []))}</td>
            </tr>
            """
        )
    return "".join(rows)


def _anomaly_cards(anomalies: list[dict]) -> str:
    if not anomalies:
        return '<div class="analysis-box" data-reveal="card"><strong>异动判断</strong><p>当前周期未识别到日环比超过 50% 且当日问题量不少于 5 件的明显异动。</p></div>'
    sorted_days = _sorted_anomaly_days(anomalies)[:3]
    cards = []
    for day in sorted_days:
        cards.append(
            f"""
            <article class="signal-card" data-reveal="item">
              <div class="signal-card-head">
                <strong>{_e(day["date"])}</strong>
                <span class="signal-chip">日环比 { _pct(day.get("day_over_day_growth", 0)) }</span>
              </div>
              <p>问题量 {day["count"]}，负向占比 {_pct(day["negative_ratio"])}</p>
              <div class="signal-meta">
                <div><span>赛事日标注</span><p>{_matchday_pill(day)} {_e(_matchday_summary(day) or '')}</p></div>
                <div><span>主要问题</span><p>{"、".join(item["key"] for item in day.get("top_tertiary", [])) or '无'}</p></div>
              </div>
              <p class="signal-note">{_e('补充线索：' + _event_label(day) if _event_label(day) else '补充线索：无')}</p>
            </article>
            """
        )
    return f'<div class="signal-grid">{"".join(cards)}</div>'


def _primary_secondary_cards(items: list[dict], total: int) -> str:
    cards = []
    for item in items:
        cards.append(
            f"""
            <article class="detail-card" data-reveal="item">
              <div class="detail-head">
                <div>
                  <h4>{_e(item["key"])}</h4>
                  <p>提及 {item["count"]} 次，占比 {_pct(_safe_ratio(item["count"], total))}</p>
                </div>
                <span class="detail-count">{item["count"]}</span>
              </div>
              <div class="chip-cloud">{_tags(item.get("secondary", []))}</div>
            </article>
            """
        )
    return "".join(cards)


def _cause_cards(items: list[dict], total: int) -> str:
    cards = []
    for item in items:
        cards.append(
            f"""
            <article class="detail-card" data-reveal="item">
              <div class="detail-head">
                <div>
                  <h4>{_e(item["key"])}</h4>
                  <p>提及 {item["count"]} 次，占比 {_pct(_safe_ratio(item["count"], total))}</p>
                </div>
                <span class="detail-count">{item["count"]}</span>
              </div>
              <div class="chip-cloud">{_tags(item.get("top_appeals", []))}</div>
            </article>
            """
        )
    return "".join(cards)


def _voice_cards(items: list[dict]) -> str:
    cards = []
    for item in items:
        quotes = "".join(f'<div class="quote">{_e(sample.get("content_excerpt", ""))}</div>' for sample in item.get("samples", []))
        cards.append(
            f"""
            <article class="voice-card" data-reveal="item">
              <div class="voice-head">
                <h4>{_e(item["key"])}</h4>
                <span>{item["count"]} 次</span>
              </div>
              <div class="chip-cloud">{_tags(item.get("top_appeals", []))}</div>
              <div class="voice-body">{quotes}</div>
            </article>
            """
        )
    return "".join(cards)


def _render_executive_summary_html(exec_text: str) -> str:
    """Render the executive summary block in HTML."""
    if not exec_text or not exec_text.strip():
        return ""
    return f'''      <div id="executive-summary" class="section-heading" style="margin-top:20px">
        <div>
          <span class="chart-kicker">核心摘要与发现</span>
          <h2>核心摘要与发现</h2>
          <div class="insight-block" style="background:var(--panel-bg,#f8f9fb);border-radius:12px;padding:24px;margin-top:12px">
            <p style="font-size:15px;line-height:1.9;color:var(--text,#2d2d2d)">{_e(exec_text)}</p>
          </div>
        </div>
      </div>'''


def _render_four_ops_html(four_ops: list, four_products: list, mapping_table: list) -> str:
    """Render four operations / four product levels analysis in HTML."""
    if not four_ops and not four_products:
        return ""
    parts = ['''      <div id="four-ops" class="section-heading" style="margin-top:20px">
        <div>
          <span class="chart-kicker">STRATEGIC DIMENSION</span>
          <h2>四个运营维度分析</h2>''']
    if four_ops:
        parts.append('''          <h3 style="margin-top:16px">四个运营维度分布</h3>
          <div class="table-scroll"><table class="data-table"><thead><tr><th>运营维度</th><th>问题量</th></tr></thead><tbody>''')
        for item in four_ops[:5]:
            parts.append(f'<tr><td>{_e(item.get("key",""))}</td><td>{_n(item.get("count",0))}</td></tr>')
        parts.append('</tbody></table></div>')
    if four_products:
        parts.append('''          <h3 style="margin-top:16px">四个产品层次分布</h3>
          <div class="table-scroll"><table class="data-table"><thead><tr><th>产品层次</th><th>问题量</th></tr></thead><tbody>''')
        for item in four_products[:5]:
            parts.append(f'<tr><td>{_e(item.get("key",""))}</td><td>{_n(item.get("count",0))}</td></tr>')
        parts.append('</tbody></table></div>')
    if mapping_table:
        parts.append('''          <h3 style="margin-top:16px">三级问题标签到四个层次/四个运营映射表</h3>
          <div class="table-scroll"><table class="data-table"><thead><tr><th>三级标签</th><th>问题量</th><th>归属运营维度</th><th>归属产品层次</th></tr></thead><tbody>''')
        for m in mapping_table:
            parts.append(f'<tr><td>{_e(m.get("tertiary_label",""))}</td><td>{_n(m.get("count",0))}</td><td>{_e(m.get("operation",""))}</td><td>{_e(m.get("product_level",""))}</td></tr>')
        parts.append('</tbody></table></div>')
    parts.append('''        </div></div>''')
    return "\n".join(parts)


def _render_typical_case_deep_dive_html(deep_data: list[dict]) -> str:
    """Render typical case deep dives in HTML."""
    if not deep_data:
        return ""
    parts = ['''      <div id="typical-case" class="section-heading" style="margin-top:20px">
        <div>
          <span class="chart-kicker">TYPICAL CASE</span>
          <h2>典型问题深度分析</h2>''']
    for item in deep_data[:3]:
        label = _e(item.get("label", ""))
        count = _n(item.get("count", 0))
        analysis = _e(item.get("analysis", ""))
        if analysis:
            parts.append(f'''          <div class="insight-block" style="background:var(--panel-bg,#f8f9fb);border-radius:12px;padding:20px;margin-top:16px">
            <h4>「{label}」（共{count}件）</h4>
            <p style="font-size:14px;line-height:1.8">{analysis}</p>
          </div>''')
    parts.append('''        </div></div>''')
    return "\n".join(parts)


def _render_tertiary_cause_detail_section(details) -> str:
    if not details:
        return ""
    headers = ["\u6392\u540d", "\u4e09\u7ea7\u95ee\u9898", "\u63d0\u53ca\u91cf/\u5360\u6bd4",
               "\u5de5\u5355\u5185\u5bb9\u603b\u7ed3", "\u5ba2\u670d\u56de\u590d\u603b\u7ed3",
               "\u5ba2\u6237\u5173\u952e\u8bc9\u6c42", "\u8bc9\u6c42\u5173\u952e\u8bcd",
               "\u5ba2\u670d\u5904\u7406\u52a8\u4f5c", "\u5ba2\u670d\u5173\u952e\u8bcd", "\u6839\u56e0\u5224\u65ad"]
    thead = "".join(f'<th>{h}</th>' for h in headers)
    trows = []
    for idx, item in enumerate(details):
        label = _e(str(item.get("label", "")))
        count = _n(item.get("count", 0))
        share = _e(str(item.get("share", "")))
        dims = [
            _e(item.get("content_summary", "")),
            _e(item.get("cs_reply_summary", "")),
            _e(item.get("customer_appeal_summary", "")),
            _e(item.get("customer_keywords_summary", "")),
            _e(item.get("cs_action_summary", "")),
            _e(item.get("cs_keywords_summary", "")),
            _e(item.get("root_cause", "")),
        ]
        trows.append(
            "<tr>"
            f'<td><strong>TOP{idx+1}</strong></td>'
            f'<td>{label}</td>'
            f'<td>{count} / {share}</td>'
            + "".join(f'<td style="word-break:break-word;max-width:280px">{d}</td>' for d in dims)
            + "</tr>"
        )
    table = (
        f'<section class="chart-card chart-grid-wide" data-reveal="card">'
        f'<div class="chart-header"><div><span class="chart-kicker">CAUSE DETAIL</span>'
        f'<h3>\u5404\u4e09\u7ea7\u95ee\u9898\u539f\u56e0\u5206\u6790\u8be6\u60c5</h3></div></div>'
        f'<div class="table-scroll"><table class="data-table"><thead><tr>{thead}</tr></thead>'
        f'<tbody>{"".join(trows)}</tbody></table></div></section>'
    )
    return table



def _province_analysis_section(province_data: list, refund_data: list, narratives: dict) -> str:
    if not province_data:
        return ""

    # Province distribution bar chart (TOP10)
    all_province_total = sum(item.get("count", 0) for item in province_data)
    bar_rows_html = _bar_rows(province_data[:10], total=all_province_total)

    # LLM narrative
    narrative_html = _narrative_stack(narratives.get("province_analysis") or [])

    return f"""
    <section class="chart-card chart-grid-wide" data-reveal="card">
      <div class="chart-header">
        <div>
          <span class="chart-kicker">PROVINCE ANALYSIS</span>
          <h3>省份投诉分布与区域特征</h3>
        </div>
      </div>
      {narrative_html}
      <div class="bar-chart-area">{bar_rows_html}</div>
    </section>
    """


def _refund_analysis_section(refund_data: list, refund_tertiary_data: list, escalation_data: list, narratives: dict) -> str:
    if not refund_data:
        return ""

    # Refund distribution table
    refund_total = _sum_counts(refund_data)
    refund_rows = []
    for idx, item in enumerate([r for r in refund_data if r.get("count", 0) > 0][:5], start=1):
        count = int(item.get("count", 0))
        refund_rows.append(
            f"<tr><td>{idx:02d}</td><td>{_e(item['key'])}</td><td>{_n(count)}</td>"
            f"<td>{_pct(_safe_ratio(count, refund_total))}</td></tr>"
        )

    refund_table = ""
    if refund_rows:
        refund_table = f"""
        <div class="table-scroll">
          <table class="data-table">
            <thead><tr><th>排名</th><th>退费诉求</th><th>提及量</th><th>占比</th></tr></thead>
            <tbody>{''.join(refund_rows)}</tbody>
          </table>
        </div>
        """

    # Refund-tertiary association table
    tertiary_rows = []
    for rt in refund_tertiary_data[:3]:
        rt_key = _e(rt.get("key", "未标注"))
        rt_count = int(rt.get("count", 0))
        tert_items = [t for t in rt.get("top_tertiary", []) if t.get("count", 0) > 0]
        if not tert_items:
            tertiary_rows.append(
                f"<tr><td>{rt_key}</td><td>{_n(rt_count)}</td><td>无</td><td>0</td><td>0.0%</td></tr>"
            )
            continue
        for tert in tert_items[:3]:
            tert_count = int(tert.get("count", 0))
            tertiary_rows.append(
                f"<tr><td>{rt_key}</td><td>{_n(rt_count)}</td>"
                f"<td>{_e(tert['key'])}</td><td>{_n(tert_count)}</td>"
                f"<td>{_pct(_safe_ratio(tert_count, rt_count))}</td></tr>"
            )

    tertiary_table = ""
    if tertiary_rows:
        tertiary_table = f"""
        <div class="table-scroll" style="margin-top:16px">
          <table class="data-table">
            <thead><tr><th>退费诉求</th><th>服务数据量</th><th>关联三级问题</th><th>提及量</th><th>退费组内占比</th></tr></thead>
            <tbody>{''.join(tertiary_rows)}</tbody>
          </table>
        </div>
        """

    # Escalation risk
    escalation_html = ""
    if escalation_data:
        esc_total = _sum_counts(escalation_data)
        esc_tags = _tags(escalation_data[:3], total=esc_total)
        escalation_html = f"""
        <div style="margin-top:16px">
          <h4 style="margin:0 0 8px">升级投诉风险分布</h4>
          <div class="chip-cloud">{esc_tags}</div>
        </div>
        """

    # LLM narrative
    narrative_html = _narrative_stack(narratives.get("refund_analysis") or [])

    return f"""
    <section class="chart-card chart-grid-wide" data-reveal="card">
      <div class="chart-header">
        <div>
          <span class="chart-kicker">REFUND ANALYSIS</span>
          <h3>退费诉求专题分析</h3>
        </div>
      </div>
      {narrative_html}
      {refund_table}
      {tertiary_table}
      {escalation_html}
    </section>
    """


def _merged_cause_voice_table(result: dict, narratives: dict[str, list[str]] | None = None) -> str:
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
            str(item.get("key") or ""),
        )
        rows.append(f"""
        <tr>
          <td>{_e(item.get("key", "未标注"))}</td>
          <td>{_n(count)}条</td>
          <td>{_e(appeal_text)}</td>
          <td>{_e(summary_text)}</td>
        </tr>
        """)
    table = f"""
    <table class="data-table">
      <thead>
        <tr>
          <th>三级问题</th>
          <th>提及量</th>
          <th>高频诉求</th>
          <th>样例摘要</th>
        </tr>
      </thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
    """
    return table


def _overview_table(title: str, kicker: str, items: list[dict], total: int, summary: str | list[str]) -> str:
    visible = [item for item in items if item.get("count", 0) > 0][:3]
    highlights = "".join(
        f'<span class="metric-pill"><strong>{_e(item["key"])}</strong><span>{_n(item["count"])}</span></span>'
        for item in visible
    )
    summary_html = _narrative_stack(summary if isinstance(summary, list) else [summary])
    return f"""
    <section class="chart-card" data-reveal="card">
      <div class="chart-header">
        <div>
          <span class="chart-kicker">{_e(kicker)}</span>
          <h3>{_e(title)}</h3>
        </div>
      </div>
      {summary_html}
      <div class="metric-pill-row">{highlights or '<span class="subtle">暂无可展示数据。</span>'}</div>
    </section>
    """


def _primary_detail_breakdown_html(result: dict, narratives: dict[str, Any], total: int) -> str:
    primary_labels = [
        item for item in (result.get("primary", []) or [])
        if str(item.get("key", "")).strip() in CANONICAL_PRIMARY_TERTIARY and item.get("count", 0) > 0
    ][:6]
    if not primary_labels:
        return ""

    cause_by_label = {
        canonical_tertiary_label(item.get("label", "")): item
        for item in (narratives.get("tertiary_cause_detail") or [])
        if item.get("label")
    }
    summary_by_label = {
        str(item.get("label", "")).strip(): item
        for item in (narratives.get("primary_summaries") or [])
        if item.get("label")
    }
    cn_numbers = ["一", "二", "三", "四", "五", "六"]
    cards: list[str] = []

    for idx, primary_item in enumerate(primary_labels):
        pkey = str(primary_item.get("key", "")).strip()
        pcount = int(primary_item.get("count", 0) or 0)
        pshare = _pct(_safe_ratio(pcount, total))
        llm_summary = str(summary_by_label.get(pkey, {}).get("summary", "")).strip()
        if not llm_summary:
            raise RuntimeError(f"一级标签小结缺失：{pkey}")

        primary_tertiary = primary_top_tertiary_items(result, pkey, pcount, limit=5)
        if not primary_tertiary:
            raise RuntimeError(f"一级标签无法按权威 taxonomy 找到三级分布：{pkey}")

        dist_rows: list[list[Any]] = []
        for tertiary_item in primary_tertiary[:5]:
            tkey = str(tertiary_item.get("key", "")).strip()
            tcount = int(tertiary_item.get("count", 0) or 0)
            if not tkey or tcount <= 0:
                continue
            detail = cause_by_label.get(canonical_tertiary_label(tkey), {})
            quote = (
                detail.get("user_voice_natural")
                or detail.get("content_summary")
                or detail.get("root_cause")
                or ""
            )
            quote = str(quote).strip()
            if not quote:
                raise RuntimeError(f"典型用户原话缺失：{tkey}")
            dist_rows.append([tkey, tertiary_item.get("share") or _pct(_safe_ratio(tcount, pcount)), quote])

        tertiary_blocks: list[str] = []
        for tertiary_item in primary_tertiary[:3]:
            tkey = str(tertiary_item.get("key", "")).strip()
            tcount = int(tertiary_item.get("count", 0) or 0)
            tshare = _pct(_safe_ratio(tcount, pcount)) if pcount else "0.0%"
            detail = cause_by_label.get(canonical_tertiary_label(tkey), {})
            snippets: list[str] = []
            content_summary = str(detail.get("content_summary", "")).strip()
            cs_summary = str(detail.get("cs_reply_summary", "")).strip()
            root_cause = str(detail.get("root_cause", "")).strip()
            if content_summary and len(content_summary) > 10:
                snippets.append(f"<p><strong>服务内容：</strong>{_e(content_summary.rstrip('。'))}。</p>")
            if cs_summary and len(cs_summary) > 10:
                snippets.append(f"<p><strong>客服应对：</strong>{_e(cs_summary.rstrip('。'))}。</p>")
            if root_cause:
                snippets.append(f"<p><strong>根因判断：</strong>{_e(root_cause.rstrip('。'))}。</p>")
            if not snippets:
                raise RuntimeError(f"三级标签分析小结缺失：{tkey}")
            tertiary_blocks.append(
                f"""
                <article class="tertiary-detail">
                  <h4>{_e(tkey)}（共{_n(tcount)}条，占该一级问题{_e(tshare)}）</h4>
                  <div class="narrative-stack">{''.join(snippets)}</div>
                </article>
                """
            )

        cards.append(
            f"""
            <section class="chart-card chart-grid-wide primary-detail-card" data-reveal="card">
              <div class="chart-header">
                <div>
                  <span class="chart-kicker">PRIMARY DETAIL</span>
                  <h3>{cn_numbers[idx]}、{_e(pkey)}（共{_n(pcount)}条，占比{_e(pshare)}）</h3>
                </div>
              </div>
              <h4>用户核心诉求分布</h4>
              {_simple_table(["诉求类型", "频次占比", "典型用户原话"], dist_rows)}
              <div class="tertiary-detail-list">{''.join(tertiary_blocks)}</div>
              {_narrative_stack([llm_summary])}
            </section>
            """
        )

    overall_eval = narratives.get("primary_overall_evaluation") or []
    if not isinstance(overall_eval, list) or len(overall_eval) < 2:
        raise RuntimeError("一级标签综合评价缺失，报告生成失败。")
    cards.append(
        f"""
        <section class="chart-card chart-grid-wide primary-detail-card" data-reveal="card">
          <div class="chart-header">
            <div>
              <span class="chart-kicker">PRIMARY SUMMARY</span>
              <h3>一级标签综合评价</h3>
            </div>
          </div>
          {_narrative_stack([str(overall_eval[0]).strip(), str(overall_eval[1]).strip()])}
        </section>
        """
    )
    return f'<div class="section-stack chart-grid primary-detail-grid">{"".join(cards)}</div>'


def _daily_detail_table_html(days: list[dict], anomalies: list[dict]) -> str:
    anomaly_dates = {str(item.get("date")) for item in anomalies if item.get("date")}
    rows: list[list[Any]] = []
    for day in days:
        date_text = str(day.get("date", ""))
        match_text = "是" if _matchday(day) else "否"
        if date_text in anomaly_dates:
            match_text += " 异动"
        top_tertiary = "、".join(str(item.get("key", "")) for item in (day.get("top_tertiary") or [])[:3] if item.get("key")) or "-"
        rows.append([date_text, _n(day.get("count", 0)), _pct(day.get("negative_ratio", 0)), match_text, top_tertiary])

    return f"""
    <section class="chart-card chart-grid-wide" data-reveal="card">
      <div class="chart-header">
        <div>
          <span class="chart-kicker">DAILY DETAIL</span>
          <h3>每日明细数据</h3>
        </div>
      </div>
      {_simple_table(["日期", "问题量", "负向占比", "赛事日", "主要三级问题"], rows, "暂无可展示的每日明细数据。")}
    </section>
    """


def _narrative_stack(lines: list[str], dark: bool = False) -> str:
    cls = "narrative-stack narrative-stack-dark" if dark else "narrative-stack"
    if not lines:
        return f'<div class="{cls}"><p>暂无可生成的分析内容。</p></div>'
    return f'<div class="{cls}">{"".join(f"<p>{_e(line)}</p>" for line in lines)}</div>'


def _selected_daily_rows(days: list[dict], anomalies: list[dict] | None = None, limit: int = 12) -> list[dict]:
    if len(days) <= limit:
        return days
    selected_dates: set[str] = set()
    selected: list[dict] = []
    days_by_date = {day.get("date"): day for day in days if day.get("date")}

    def add(day: dict | None) -> None:
        if not day:
            return
        date = day.get("date")
        if not date or date in selected_dates:
            return
        selected_dates.add(date)
        selected.append(day)

    add(max(days, key=lambda item: item.get("count", 0), default=None))
    add(max(days, key=lambda item: item.get("negative_ratio", 0), default=None))
    for anomaly in anomalies or []:
        add(days_by_date.get(anomaly.get("date")) or anomaly)
    for day in sorted(days, key=lambda item: item.get("count", 0), reverse=True):
        add(day)
        if len(selected) >= limit:
            break
    return sorted(selected[:limit], key=lambda item: str(item.get("date", "")))


def _tag_text(items: list[dict], limit: int = 3, total: int | None = None) -> str:
    visible = [item for item in items if item.get("count", 0) > 0][:limit]
    denominator = total if total is not None else _sum_counts(items)
    return (
        "、".join(
            f"{item.get('key', '未标注')}（共{_n(item.get('count', 0))}条，占比{_pct(_safe_ratio(item.get('count', 0), denominator))}）"
            for item in visible
        )
        or "无"
    )


def _tag_key_text(items: list[dict], limit: int = 3) -> str:
    visible = [item for item in items if item.get("count", 0) > 0][:limit]
    return "、".join(str(item.get("key", "未标注")) for item in visible if item.get("key")) or "无"


def _sorted_anomaly_days(anomalies: list[dict]) -> list[dict]:
    return sorted(
        anomalies,
        key=lambda item: (
            -float(item.get("day_over_day_growth") or 0),
            -int(item.get("count") or 0),
            str(item.get("date") or ""),
        ),
    )


def _sanitize_report_terms(text: str) -> str:
    return mask_sensitive_text((text or "").replace("反馈/投诉", "投诉").replace("反馈", "投诉"))


def _business_dimension_lines(result: dict) -> list[str]:
    service_type = result.get("service_type", [])
    service_total = _sum_counts(service_type)
    member_cluster = result.get("biz_member_cluster", [])
    tertiary = result.get("tertiary", [])
    if not service_total and not member_cluster:
        return []

    lines: list[str] = []
    if service_type and service_total:
        top = service_type[0]
        lines.append(
            f"业务维度上，用户投诉主要集中在订购退订、权益兑现和赛事观看体验等连续服务链路，"
            f"说明当前问题更接近流程与规则理解叠加后的体验压力，而不是单一功能点异常。"
        )
    return lines


def _trend_matchday_business_lines(result: dict, trend_view: dict[str, Any]) -> list[str]:
    days = trend_view.get("days", [])
    if not days:
        return []

    schedule = _schedule_status(result)
    matchdays = [day for day in days if _matchday(day)]
    non_matchdays = [day for day in days if not _matchday(day)]
    lines: list[str] = []

    if matchdays and non_matchdays:
        matchday_avg = sum(day.get("count", 0) for day in matchdays) / len(matchdays)
        non_matchday_avg = sum(day.get("count", 0) for day in non_matchdays) / len(non_matchdays)
        matchday_dates = ", ".join(sorted(day.get("date", "") for day in matchdays))
        lines.append(
            f"有比赛的是 {len(matchdays)} 天（{matchday_dates}），"
            f"赛事日日均问题量 {matchday_avg:.1f} 件，非赛事日日均 {non_matchday_avg:.1f} 件。"
        )
    elif matchdays:
        matchday_total = sum(day.get("count", 0) for day in matchdays)
        matchday_dates = ", ".join(sorted(day.get("date", "") for day in matchdays))
        lines.append(
            f"有比赛的是 {len(matchdays)} 天（{matchday_dates}），"
            f"赛事日合计问题量 {_n(matchday_total)} 件。"
        )
    return lines


def _chip_row(label: str, items: list[dict], limit: int = 5) -> str:
    visible = [item for item in items if item.get("count", 0) > 0][:limit]
    if not visible:
        return ""
    return f'<div class="risk-row"><span>{_e(label)}</span><div class="chip-cloud">{_tags(visible)}</div></div>'


def _chip_rows(rows: list[tuple[str, list[dict], int]]) -> str:
    html = "".join(_chip_row(label, items, limit) for label, items, limit in rows)
    return f'<div class="risk-stack">{html}</div>' if html else ""


def _simple_table(headers: list[str], rows: list[list[Any]], empty_text: str = "暂无可展示数据。") -> str:
    if not rows:
        return f'<p class="subtle">{_e(empty_text)}</p>'
    header_html = "".join(f"<th>{_e(header)}</th>" for header in headers)
    rows_html = "".join(
        "<tr>" + "".join(f"<td>{_e(value)}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f"""
    <div class="table-scroll">
      <table class="data-table">
        <thead><tr>{header_html}</tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
    """


def _summary_card(title: str, kicker: str, lines: list[str], items: list[dict]) -> str:
    return f"""
    <section class="chart-card" data-reveal="card">
      <div class="chart-header">
        <div>
          <span class="chart-kicker">{_e(kicker)}</span>
          <h3>{_e(title)}</h3>
        </div>
      </div>
      {_narrative_stack(lines)}
      <div class="chip-cloud">{_tags(items) or '<span class="subtle">暂无可展示数据。</span>'}</div>
    </section>
    """


def _executive_summary_section(result: dict, narratives: dict[str, list[str]], trend_view: dict[str, Any]) -> str:
    lines = narratives.get("executive_summary") or _distribution_insights(result)[:3]
    return f"""
    <section class="report-section" data-reveal="section" data-lazy="section">
      <div class="section-label"><span class="pulse-dot"></span><strong>SUMMARY</strong></div>
      <div class="section-heading">
        <div>
          <h2>核心摘要</h2>
          <p>围绕 1.1 问题分布和 1.2 投诉趋势前置关键结论，便于快速判断本报告重点。</p>
        </div>
      </div>
      <div class="analysis-box analysis-box-gradient" data-reveal="card">
        <div class="analysis-header">
          <span class="chart-kicker">KEY TAKEAWAYS</span>
          <h3>先看结论</h3>
        </div>
        {_narrative_stack(lines)}
      </div>
    </section>
    """


def _operation_need_table(items: list[dict]) -> str:
    rows = []
    for item in [entry for entry in items if entry.get("count", 0) > 0][:8]:
        samples = "；".join(
            sample.get("content_excerpt", "")
            for sample in item.get("samples", [])[:1]
            if sample.get("content_excerpt")
        )
        rows.append(
            [
                item.get("key", "未标注"),
                _n(item.get("count", 0)),
                _tag_text(item.get("top_latent_needs", []), 2),
                _tag_text(item.get("top_member_clusters", []), 2),
                _tag_text(item.get("top_tertiary", []), 2),
                samples or "无",
            ]
        )
    return _simple_table(["运营举措", "提及量", "隐性需求", "会员类型", "相关问题", "代表样例"], rows)


def _member_cluster_table(items: list[dict]) -> str:
    rows = []
    for item in [entry for entry in items if entry.get("count", 0) > 0][:10]:
        rows.append(
            [
                item.get("key", "未标注"),
                _n(item.get("count", 0)),
                _tag_text(item.get("top_tertiary", []), 3),
                _tag_text(item.get("top_appeals", []), 2),
            ]
        )
    return _simple_table(["会员/业务类型", "提及量", "高频问题", "高频诉求"], rows)


def _latent_need_table(items: list[dict]) -> str:
    rows = []
    for item in [entry for entry in items if entry.get("count", 0) > 0][:8]:
        rows.append(
            [
                item.get("key", "未标注"),
                _n(item.get("count", 0)),
                _tag_text(item.get("top_operations", []), 2),
                _tag_text(item.get("top_members", []), 2),
            ]
        )
    return _simple_table(["隐性需求", "提及量", "关联运营举措", "关联会员类型"], rows)


def _case_cards(result: dict) -> str:
    cases: list[dict[str, Any]] = []
    for item in result.get("top_tertiary_examples", [])[:3]:
        for sample in item.get("samples", [])[:1]:
            cases.append(
                {
                    "title": item.get("key", "典型问题"),
                    "count": item.get("count", 0),
                    "content": sample.get("content_excerpt", ""),
                    "meta": [
                        sample.get("appeal"),
                    ],
                }
            )
    if not cases:
        return '<p class="subtle">当前未提取到可展示的典型案例。</p>'
    cards = []
    for item in cases[:4]:
        meta_items = [{"key": value, "count": ""} for value in item.get("meta", []) if value]
        cards.append(
            f"""
            <article class="voice-card" data-reveal="item">
              <div class="voice-head">
                <h4>{_e(item.get("title", "典型案例"))}</h4>
                <span>{_n(item.get("count", 0))} 次</span>
              </div>
              <div class="chip-cloud">{_tags(meta_items) or '<span class="subtle">暂无补充标签。</span>'}</div>
              <div class="voice-body"><div class="quote">{_e(item.get("content") or "样例内容为空。")}</div></div>
            </article>
            """
        )
    return f'<div class="voice-grid">{"".join(cards)}</div>'


def _supporting_quotes(items: list[dict], limit: int = 3) -> str:
    blocks = []
    for item in items[:limit]:
        if not item.get("samples"):
            continue
        blocks.append(
            f"""
            <article class="voice-card" data-reveal="item">
              <div class="voice-head">
                <h4>{_e(item["key"])}</h4>
                <span>{_n(item["count"])} 次</span>
              </div>
              <div class="voice-body">
                {''.join(f'<div class="quote">{_e(sample.get("content_excerpt", ""))}</div>' for sample in item.get("samples", [])[:2])}
              </div>
            </article>
            """
        )
    return "".join(blocks)


def _compact_anomaly_cards(anomalies: list[dict]) -> str:
    if not anomalies:
        return '<div class="analysis-box" data-reveal="card"><strong>异动判断</strong><p>当前周期未识别到日环比超过 50% 且当日问题量不少于 5 件的明显异动。</p></div>'
    sorted_days = _sorted_anomaly_days(anomalies)[:3]
    rows = []
    for day in sorted_days:
        match_text = _matchday_summary(day) if _matchday(day) else "非赛事日"
        day_total = int(day.get("count", 0) or 0)
        rows.append(
            f"""
            <article class="signal-card signal-card-compact" data-reveal="item">
              <div class="signal-card-head">
                <strong>{_e(day["date"])}</strong>
                <span class="signal-chip">日环比 {_pct(day.get("day_over_day_growth", 0))}</span>
              </div>
              <p>问题量 {_n(day["count"])} 件；负向占比 {_pct(day.get("negative_ratio", 0))}；赛事日标注：{_e(match_text)}。</p>
              <p>主要一级问题：{_e(_tag_text(day.get("top_primary", []), 2, total=day_total))}；主要二级问题：{_e(_tag_text(day.get("top_secondary", []), 2, total=day_total))}；主要三级问题：{_e(_tag_text(day.get("top_tertiary", []), 3, total=day_total))}。</p>
              <p>业务热点：服务类型 {_e(_tag_text(day.get("top_service_type", []), 2, total=day_total))}；涉及业务/会员类型 {_e(_tag_text(day.get("top_member_cluster", []), 2, total=day_total))}。</p>
            </article>
            """
        )
    method = (
        "以上日期基于日聚合口径，日环比增长 ≥ 50% 且当日问题量 ≥ 5 件被识别为异动。"
        "按日环比降序排列，以下列出排名前三的异动节点。"
        "表内所有标签和业务维度占比均以该日问题量为分母；多标签字段可重复，合计可能超过 100%。"
    )
    return f'<div class="narrative-stack"><p>{_e(method)}</p></div><div class="signal-grid">{"".join(rows)}</div>'


def _trend_chart_summary(trend_view: dict[str, Any]) -> list[str]:
    days = trend_view.get("days", [])
    if not days:
        return ["当前筛选周期内没有可绘制的趋势图数据。"]

    peak = max(days, key=lambda item: item.get("count", 0))
    negative_peak = max(days, key=lambda item: item.get("negative_ratio", 0))
    matchdays = [day for day in days if _matchday(day)]
    non_matchdays = [day for day in days if not _matchday(day)]
    anomalies = trend_view.get("anomalies", [])

    lines = [
        f"折线图显示问题量峰值出现在 {peak['date']}，当日提及 {_n(peak['count'])} 件，主要问题集中在 {'、'.join(item['key'] for item in peak.get('top_tertiary', [])[:3]) or '无'}。",
        f"负向情绪占比最高日为 {negative_peak['date']}，占比 {_pct(negative_peak.get('negative_ratio', 0))}；该指标用于替代模板中的负向情绪指数。",
    ]

    if matchdays and non_matchdays:
        matchday_avg = sum(day.get("count", 0) for day in matchdays) / len(matchdays)
        non_matchday_avg = sum(day.get("count", 0) for day in non_matchdays) / len(non_matchdays)
        lines.append(
            f"赛事日日均问题量约为 {matchday_avg:.1f} 件，非赛事日日均约为 {non_matchday_avg:.1f} 件，赛事日的投诉波动整体高于非赛事日。"
        )

    if anomalies:
        strongest = max(anomalies, key=lambda item: item.get("day_over_day_growth", 0))
        lines.append(
            f"异动中增幅最高的节点为 {strongest['date']}，日环比 {_pct(strongest.get('day_over_day_growth', 0))}，需要结合赛事安排和处理动作复盘。"
        )

    return lines


def _trend_voice_items(trend_view: dict[str, Any], limit: int = 3) -> list[dict]:
    days = trend_view.get("days", [])
    if not days:
        return []

    anomaly_dates = {item["date"] for item in trend_view.get("anomalies", [])}
    peak = max(days, key=lambda item: item.get("count", 0), default=None)
    peak_date = peak.get("date") if peak else None

    matchday_samples = [day for day in days if _matchday(day) and day.get("samples")]
    matchday_samples.sort(
        key=lambda item: (
            item.get("date") == peak_date,
            item.get("date") in anomaly_dates,
            item.get("count", 0),
            item.get("negative_ratio", 0),
        ),
        reverse=True,
    )

    selected = []
    seen_dates: set[str] = set()
    for day in matchday_samples:
        if day["date"] in seen_dates:
            continue
        seen_dates.add(day["date"])
        selected.append(
            {
                "date": day["date"],
                "count": day.get("count", 0),
                "negative_ratio": day.get("negative_ratio", 0),
                "match_summary": _matchday_summary(day),
                "top_tertiary": day.get("top_tertiary", []),
                "samples": day.get("samples", [])[:2],
            }
        )
        if len(selected) >= limit:
            break
    return selected


def _trend_voice_summary(items: list[dict]) -> list[str]:
    if not items:
        return ["当前趋势窗口内未提取到带赛事日标注的样例原声。"]

    lead = max(items, key=lambda item: int(item.get("count", 0) or 0))
    lead_issues = "、".join(item.get("key", "") for item in lead.get("top_tertiary", [])[:3] if item.get("key")) or "无"
    lines = [
        f"赛事日样例中，{lead['date']} 的投诉最集中，共 {_n(lead['count'])} 件；相关原声主要围绕 {lead_issues} 展开。",
        "从赛事日原声看，用户更容易在比赛前后集中投诉退订、权益兑换、订购失败和覆盖范围等即时体验问题。",
    ]
    if any(item.get("negative_ratio", 0) > 0.3 for item in items):
        high = max(items, key=lambda item: item.get("negative_ratio", 0))
        lines.append(f"{high['date']} 的负向占比达到 {_pct(high.get('negative_ratio', 0))}，说明赛事节点附近更容易出现高情绪强度投诉。")
    return lines


def _trend_voice_cards(items: list[dict], narratives: dict[str, list[str]] | None = None) -> str:
    if not items:
        return '<div class="analysis-box" data-reveal="card"><strong>样例原声</strong><p>当前趋势窗口内未提取到带赛事日标注的样例原声。</p></div>'

    narratives = narratives or {}
    summary_lines = narratives.get("trend_voice_sample_summaries") or []
    cards = []
    for idx, item in enumerate(items):
        samples = item.get("samples", [])
        fallback_text = "；".join(
            _natural_sample_summary(sample.get("content_excerpt", ""), _key_text(item.get("top_tertiary", []), 1))
            for sample in samples[:2]
            if sample.get("content_excerpt")
        )
        summary_text = _narrative_line_at(summary_lines, idx) or fallback_text or "暂无样例。"
        issue_tags = _tags(item.get("top_tertiary", []), total=int(item.get("count", 0) or 0))
        cards.append(
            f"""
            <article class="voice-card" data-reveal="item">
              <div class="voice-head">
                <div>
                  <h4>{_e(item["date"])} 赛事日样例</h4>
                  <p class="voice-meta">{_e(item.get("match_summary") or '赛事日')}；问题量 {_n(item.get("count", 0))} 件；负向占比 {_pct(item.get("negative_ratio", 0))}。</p>
                </div>
                <span>{_n(item.get("count", 0))} 次</span>
              </div>
              <div class="chip-cloud">{issue_tags or '<span class="subtle">暂无主要问题标签。</span>'}</div>
              <div class="voice-body"><div class="quote">{_e(summary_text)}</div></div>
            </article>
            """
        )
    return f'<div class="voice-grid">{"".join(cards)}</div>'


def _legacy_overview_table(title: str, kicker: str, items: list[dict], total: int, summary: str) -> str:
    visible = [item for item in items if item.get("count", 0) > 0][:10]
    if not visible:
        body = '<p class="subtle">暂无可展示数据。</p>'
    else:
        rows = []
        for idx, item in enumerate(visible, start=1):
            rows.append(
                f"""
                <tr>
                  <td>{idx:02d}</td>
                  <td>{_e(item["key"])}</td>
                  <td>{_n(item["count"])}</td>
                  <td>{_pct(_safe_ratio(item["count"], total))}</td>
                </tr>
                """
            )
        body = f"""
        <div class="table-scroll">
          <table class="data-table level-table">
            <thead>
              <tr><th>排名</th><th>问题标签</th><th>提及量</th><th>占比</th></tr>
            </thead>
            <tbody>{''.join(rows)}</tbody>
          </table>
        </div>
        """

    return f"""
    <section class="chart-card" data-reveal="card">
      <div class="chart-header">
        <div>
          <span class="chart-kicker">{_e(kicker)}</span>
          <h3>{_e(title)}</h3>
        </div>
      </div>
      <p class="module-summary">{_e(summary)}</p>
      {body}
    </section>
    """


def _distribution_insights(result: dict) -> list[str]:
    labeled_total = result.get("total", 0)
    total = result.get("total_with_unlabeled", labeled_total)
    unlabeled_analysis = result.get("unlabeled_analysis", {})
    unlabeled_total = unlabeled_analysis.get("unlabeled_total", 0)
    primary = result.get("primary", [])
    secondary = result.get("secondary", [])
    tertiary = result.get("tertiary", [])
    insights = []
    if not total and not unlabeled_total:
        return ["当前筛选周期内未检索到可统计的服务数据。"]
    if not labeled_total:
        return ["当前筛选周期内没有可纳入主分布统计的已标注服务数据；未标注数据已单独展示。"]
    if primary:
        top = primary[0]
        insights.append(
            f"本周期共纳入 {total} 条用户投诉数据；一级问题中 {top['key']}（共{_n(top['count'])}条，占比{_pct(_safe_ratio(top['count'], total))}）最集中，标签分布基于已完成标注的服务数据统计。"
        )
    if secondary:
        top_secondary = secondary[0]
        insights.append(
            f"二级问题中 {top_secondary['key']}（共{_n(top_secondary['count'])}条，占比{_pct(_safe_ratio(top_secondary['count'], total))}）最集中。"
        )
    if tertiary:
        top5_count = _sum_counts(tertiary[:5])
        insights.append(
            f"三级问题 TOP5 累计提及 {_n(top5_count)} 条，占三级标签提及量的 {_pct(_safe_ratio(top5_count, total))}；首要痛点为 {tertiary[0]['key']}（共{_n(tertiary[0]['count'])}条，占比{_pct(_safe_ratio(tertiary[0]['count'], total))}）。"
        )
    insights.extend(_business_dimension_lines(result))
    return insights


def _trend_insights(result: dict, trend_view: dict[str, Any]) -> list[str]:
    daily = trend_view.get("days", [])
    anomalies = trend_view.get("anomalies", [])
    if not daily:
        return ["当前筛选周期内没有可绘制的每日趋势数据。"]
    peak = max(daily, key=lambda item: item["count"])
    neg_peak = max(daily, key=lambda item: item["negative_ratio"])
    peak_match = _matchday_summary(peak)
    neg_peak_match = _matchday_summary(neg_peak)
    insights = [
        (
            f"{peak['date']} 问题提及量达到峰值 {peak['count']} 件"
            f"{'，该日为' + peak_match if peak_match else ''}，主要问题为："
            f"{_tag_text(peak.get('top_tertiary', []), 3)}。"
        ),
        (
            f"{neg_peak['date']} 负向情绪占比最高，为 {_pct(neg_peak['negative_ratio'])}"
            f"{'，该日为' + neg_peak_match if neg_peak_match else ''}；"
            "当前以负向占比替代模板中的负向情绪指数。"
        ),
    ]
    insights.extend(_trend_matchday_business_lines(result, trend_view))
    if anomalies:
        first = _sorted_anomaly_days(anomalies)[0]
        match_note = _matchday_summary(first)
        insights.append(
            f"识别到 {len(anomalies)} 个明显异动日，增幅最高异动日为 {first['date']}"
            f"{'，该日为' + match_note if match_note else ''}，日环比 {_pct(first.get('day_over_day_growth', 0))}。"
        )
    else:
        insights.append("未发现日环比超过 50% 且当日问题量不少于 5 件的明显异动日，整体波动相对平稳。")
    if trend_view.get("used_focus_window"):
        insights.append(
            f"为保证折线图可读性，1.2 图表聚焦主分析时段 {trend_view['start']} 至 {trend_view['end']}；"
            f"此前零散活跃日共 {trend_view['trimmed_active_days']} 个、{trend_view['trimmed_count']} 件，未纳入折线图。"
        )
    return insights


def _unlabeled_dist_lines(result: dict) -> list[str]:
    unlabeled_analysis = result.get("unlabeled_analysis", {})
    unlabeled_total = unlabeled_analysis.get("unlabeled_total", 0)
    if not unlabeled_total:
        return []
    total_with_unlabeled = result.get("total_with_unlabeled", result.get("total", 0))
    unlabeled_pct = _pct(_safe_ratio(unlabeled_total, total_with_unlabeled))
    emotion = unlabeled_analysis.get("emotion", [])
    csp_name = unlabeled_analysis.get("csp_name", [])
    customer_key_appeal = unlabeled_analysis.get("customer_key_appeal", [])
    refund_demand = next((item["count"] for item in unlabeled_analysis.get("has_refund_demand", []) if item["key"] == "是"), 0)
    escalation = next((item["count"] for item in unlabeled_analysis.get("has_escalation", []) if item["key"] == "是"), 0)
    lines = [
        f"本次共纳入 {total_with_unlabeled} 条服务数据，其中 {unlabeled_total} 条（{unlabeled_pct}）一/二/三级标签未标注，已从问题分布统计中排除。",
    ]
    if emotion or customer_key_appeal or csp_name:
        lines.append(
            f"从未标注服务数据的内容结构看，情绪以 {_tag_text(emotion, 2)} 为主，诉求集中在 {_tag_text(customer_key_appeal, 2)}，主要渠道/终端线索为 {_tag_text(csp_name, 2)}。"
        )
    return lines[:4]


def _unlabeled_trend_lines(result: dict) -> list[str]:
    unlabeled_trend = result.get("unlabeled_trend_analysis", {})
    unlabeled_total = unlabeled_trend.get("unlabeled_total", 0)
    if not unlabeled_total:
        return []
    total_with_unlabeled = result.get("total_with_unlabeled", result.get("total", 0))
    unlabeled_pct = _pct(_safe_ratio(unlabeled_total, total_with_unlabeled))
    unlabeled_daily = unlabeled_trend.get("daily", [])
    unlabeled_peak = unlabeled_trend.get("peak_day")
    unlabeled_emotion_peak = unlabeled_trend.get("emotion_peak_day")
    lines = [
        f"本周期共 {unlabeled_total} 条一/二/三级标签未标注服务数据，占原始总量的 {unlabeled_pct}，未纳入上述趋势计算。",
    ]
    if unlabeled_daily:
        date_range = f"{unlabeled_daily[0]['date']} 至 {unlabeled_daily[-1]['date']}"
        if unlabeled_peak:
            lines.append(f"时间上覆盖 {date_range}；峰值出现在 {unlabeled_peak['date']}（{unlabeled_peak['count']} 件），建议核查当日是否存在批量活动咨询、权益问题或导入漏标。")
        else:
            lines.append(f"时间上覆盖 {date_range}，建议作为独立漏标趋势跟踪。")
    if unlabeled_emotion_peak:
        lines.append(f"情绪高峰出现在 {unlabeled_emotion_peak['date']}，负向情绪占比 {_pct(unlabeled_emotion_peak['negative_ratio'])}，可优先抽样校验该日未标注文本的真实问题类型。")
    if unlabeled_daily and len(unlabeled_daily) > 1:
        first_half = unlabeled_daily[:len(unlabeled_daily)//2]
        second_half = unlabeled_daily[len(unlabeled_daily)//2:]
        first_avg = sum(d['count'] for d in first_half) / len(first_half) if first_half else 0
        second_avg = sum(d['count'] for d in second_half) / len(second_half) if second_half else 0
        if second_avg > first_avg * 1.5:
            lines.append("趋势上后半周期明显抬升，提示后续导入或标注流程可能出现阶段性漏标。")
        elif first_avg > second_avg * 1.5:
            lines.append("趋势上前半周期更集中，后半周期有所回落，建议核对早期批次的标签抽取规则。")
    return lines[:4]


def _insight_list(items: list[str], dark: bool = False) -> str:
    cls = "insights insights-dark" if dark else "insights"
    return f'<ul class="{cls}">{"".join(f"<li>{item}</li>" for item in items)}</ul>'


def _unlabeled_card_html(lines: list[str], title: str = "未标注一二三级标签服务数据分析") -> str:
    if not lines:
        return ""
    html_lines = "".join(f"<li>{_e(line)}</li>" for line in lines)
    return f"""
    <div class="unlabeled-card" data-reveal="card">
      <div class="unlabeled-card-header">
        <span class="chart-kicker">UNLABELED</span>
        <h3>{_e(title)}</h3>
      </div>
      <ul class="insights">{html_lines}</ul>
    </div>
    """


def _scope_strip(analysis: str, display: str, calc: str, dark: bool = False) -> str:
    mode = " scope-strip-dark" if dark else ""
    return f"""
    <div class="scope-strip{mode}" data-reveal="card">
      <div><span>分析要点</span><p>{_e(analysis)}</p></div>
      <div><span>展示方式</span><p>{_e(display)}</p></div>
      <div><span>计算说明</span><p>{_e(calc)}</p></div>
    </div>
    """


def _section_focus_title(section_focus: str) -> str:
    if section_focus == "distribution":
        return "问题分布概览"
    if section_focus == "trend":
        return "趋势与异动"
    return "一、整体情况"


def _section_focus_label(section_focus: str) -> str:
    if section_focus == "distribution":
        return "DISTRIBUTION"
    if section_focus == "trend":
        return "TREND & ANOMALY"
    return "OVERALL SITUATION"


def _section_focus_description(section_focus: str) -> str:
    if section_focus == "distribution":
        return "当前聚焦 1.1 问题分布概览，以 Elasticsearch 聚合结果呈现问题总量、类型分布、TOP 痛点与原因线索。"
    if section_focus == "trend":
        return "当前聚焦 1.2 投诉趋势与异动表现，以 Elasticsearch 聚合结果呈现按日波动、负向情绪占比与异常节点。"
    return "围绕模板定义的“问题分布概览”和“投诉趋势与异动表现”，以 Elasticsearch 聚合结果为核心，输出可审阅、可复盘、可直接用于汇报的 HTML 报告。"


def _analysis_type_text(section_focus: str) -> str:
    if section_focus == "distribution":
        return "1.1 问题分布概览"
    if section_focus == "trend":
        return "1.2 投诉趋势与异动表现"
    return "一、整体情况（1.1 + 1.2）— 视频产品重点赛事用户洞察分析专题报告"


def _top_secondary_label(result: dict) -> str:
    secondary = result.get("secondary", [])
    if not secondary:
        return "无"
    return str(secondary[0].get("key", "无"))


def _negative_peak_day(trend_view: dict[str, Any]) -> dict[str, Any] | None:
    days = trend_view.get("days", [])
    return max(days, key=lambda item: item["negative_ratio"], default=None)


def _hero_signal(section_focus: str, total: int, peak_day: dict[str, Any] | None, anomalies: list[dict]) -> tuple[str, str, str]:
    if section_focus == "trend":
        if peak_day:
            return "PEAK DAY", _e(peak_day["date"][5:]), f"峰值问题量 {_n(peak_day['count'])} 件"
        return "PEAK DAY", "无", "当前无可用趋势峰值"
    if section_focus == "distribution":
        return "TOTAL FEEDBACK", _n(total), "已纳入本次分布分析"
    return "LIVE SIGNAL", _n(total), "已纳入本周期投诉"


def _hero_issue(section_focus: str, top_primary: dict | None, top_tertiary: dict | None, anomalies: list[dict]) -> tuple[str, str, str]:
    if section_focus == "trend":
        if anomalies:
            first = _sorted_anomaly_days(anomalies)[0]
            return "ANOMALY", _e(first["date"][5:]), f"最高增幅异动日，日环比 {_pct(first.get('day_over_day_growth', 0))}"
        return "ANOMALY", "无", "当前未识别到明显异动日"
    if section_focus == "distribution":
        primary_name = _e(top_primary["key"]) if top_primary else "无"
        return "TOP CATEGORY", primary_name, "当前最集中的一级问题类型"
    top_issue = _e(top_tertiary["key"]) if top_tertiary else "无"
    return "TOP ISSUE", top_issue, "当前最需要优先定位的痛点"


def _build_kpis(section_focus: str, result: dict, total: int, top_primary: dict | None, top_tertiary: dict | None, peak_day: dict[str, Any] | None, trend_view: dict[str, Any]) -> list[dict[str, str]]:
    if section_focus == "distribution":
        return [
            {"label": "投诉总量", "value": _n(total)},
            {"label": "一级问题最高项", "value": _e(top_primary["key"]) if top_primary else "无"},
            {"label": "三级 TOP 问题", "value": _e(top_tertiary["key"]) if top_tertiary else "无"},
            {"label": "核心二级问题", "value": _e(_top_secondary_label(result))},
        ]
    if section_focus == "trend":
        return [
            {"label": "投诉总量", "value": _n(total)},
            {"label": "趋势峰值日", "value": _e(peak_day["date"][5:]) if peak_day else "无"},
            {"label": "峰值问题量", "value": _n(peak_day["count"]) if peak_day else "无"},
            {"label": "异动天数", "value": _n(len(trend_view.get("anomalies", [])))},
        ]
    return [
        {"label": "投诉总量", "value": _n(total)},
        {"label": "一级问题最高项", "value": _e(top_primary["key"]) if top_primary else "无"},
        {"label": "三级 TOP 问题", "value": _e(top_tertiary["key"]) if top_tertiary else "无"},
        {"label": "趋势峰值日", "value": _e(peak_day["date"][5:]) if peak_day else "无"},
    ]


def _query_note_text(query: dict, section_focus: str) -> str:
    note = str(query.get("note") or "").strip()
    if not note:
        return f"当前分析类型：{_analysis_type_text(section_focus)}。"
    cleaned = note.replace("section_focus为distribution", "当前聚焦 1.1 问题分布概览")
    cleaned = cleaned.replace("section_focus为trend", "当前聚焦 1.2 投诉趋势与异动表现")
    cleaned = cleaned.replace("section_focus为full", "当前聚焦完整“一、整体情况”")
    return cleaned


def render_html_report(result: dict, output_path: Path) -> Path:
    result = sanitize_report_payload(result)
    top_primary = result["primary"][0] if result.get("primary") else None
    top_secondary = result["secondary"][0] if result.get("secondary") else None
    top_tertiary = result["tertiary"][0] if result.get("tertiary") else None
    trend_view = _build_trend_view(result.get("daily", []), result.get("filters", {}), result.get("anomalies", []))
    context = build_report_context(result, trend_view)
    period_start = context.period_start
    period_end = context.period_end
    query = context.query
    section_focus = context.section_focus
    peak_day = max(trend_view.get("days", []), key=lambda day: day["count"], default=None)
    total = context.total
    source_text = _source_files_text(result.get("source_files", []))
    schedule = _schedule_status(result)
    narratives = context.narratives
    trend_chart_summary = narratives.get("trend_chart_summary") or _trend_chart_summary(trend_view)
    trend_voice_items = _trend_voice_items(trend_view)
    trend_voice_summary = narratives.get("trend_voice_summary") or _trend_voice_summary(trend_voice_items)
    daily_detail_rows = trend_view.get("days", [])
    focus_title = _section_focus_title(section_focus)
    focus_label = _section_focus_label(section_focus)
    focus_description = _section_focus_description(section_focus)
    analysis_type = _analysis_type_text(section_focus)
    signal_label, signal_value, signal_desc = _hero_signal(section_focus, total, peak_day, trend_view.get("anomalies", []))
    issue_label, issue_value, issue_desc = _hero_issue(section_focus, top_primary, top_tertiary, trend_view.get("anomalies", []))
    kpis = _build_kpis(section_focus, result, total, top_primary, top_tertiary, peak_day, trend_view)

    analysis_line = f'<p class="subtle hero-meta">分析类型：{_e(analysis_type)}</p>'
    trend_window_line = (
        f'<p class="subtle hero-meta">趋势主分析时段：{_e(trend_view["start"])} 至 {_e(trend_view["end"])}</p>'
        if trend_view.get("used_focus_window") and section_focus in {"trend", "full"}
        else ""
    )
    trend_window_note = (
        trend_view.get("note") or "当前按完整查询周期展示每日趋势。"
        if section_focus in {"trend", "full"}
        else "当前报告未展示 1.2 趋势章节。"
    )
    schedule_method_text = _matchday_note(result, trend_view)
    avg_duration = result.get("avg_duration_minutes")
    avg_duration_text = f"{float(avg_duration):.1f} 分钟" if isinstance(avg_duration, (int, float)) and not math.isnan(float(avg_duration)) else "未覆盖"
    primary_summary = (
        f"一级问题以「{top_primary['key']}」最集中，提及 {_n(top_primary['count'])} 次，占比 {_pct(_safe_ratio(top_primary['count'], total))}。"
        if top_primary
        else "当前没有可展示的一级问题数据。"
    )
    secondary_summary = (
        f"二级问题中「{top_secondary['key']}」提及 {_n(top_secondary['count'])} 次，占比 {_pct(_safe_ratio(top_secondary['count'], total))}。"
        if top_secondary
        else "当前没有可展示的二级问题数据。"
    )
    tertiary_summary = (
        f"三级问题中「{top_tertiary['key']}」为核心痛点，提及 {_n(top_tertiary['count'])} 次，占比 {_pct(_safe_ratio(top_tertiary['count'], total))}。"
        if top_tertiary
        else "当前没有可展示的三级问题数据。"
    )

    distribution_section = f"""
    {_render_executive_summary_html(narratives.get("executive_summary", ""))}
    <section class="report-section" data-reveal="section" data-lazy="section">
      <div class="section-label"><span class="pulse-dot"></span><strong>SECTION 1.1</strong></div>
      <div class="section-heading">
        <div>
          <h2>1.1 问题分布概览</h2>
          <p>快速定位本周期最集中的用户痛点，判断哪一类问题需要优先投入资源解决。</p>
        </div>
      </div>
      <div class="analysis-box analysis-box-gradient" data-reveal="card">
        <div class="analysis-header">
          <span class="chart-kicker">INSIGHT</span>
          <h3>分析结论</h3>
        </div>
        {_narrative_stack(narratives.get("distribution_conclusion") or _distribution_insights(result))}
      </div>
      {_unlabeled_card_html(narratives.get("unlabeled_distribution_summary") or _unlabeled_dist_lines(result))}
      <div class="grid chart-grid">
        {_donut_chart(result.get("primary", []), "一级标签类型分布", "一级标签提及量")}
        {_donut_chart(result.get("secondary", []), "二级标签类型分布", "二级标签提及量")}
        {_donut_chart(result.get("tertiary", []), "三级标签类型分布", "三级标签提及量")}
        {_top_bar_chart(result.get("tertiary", []))}
      </div>
      <div class="section-stack chart-grid">
        {_overview_table("一级问题概览", "PRIMARY", result.get("primary", []), total, narratives.get("primary_overview") or [primary_summary])}
        {_overview_table("二级问题概览", "SECONDARY", result.get("secondary", []), total, narratives.get("secondary_overview") or [secondary_summary])}
        {_overview_table("三级问题概览", "TERTIARY", result.get("tertiary", []), total, narratives.get("tertiary_overview") or [tertiary_summary])}
      </div>
      {_primary_detail_breakdown_html(result, narratives, total)}
      {_province_analysis_section(result.get("province", []), result.get("province_refund", []), narratives)}
      {_refund_analysis_section(result.get("refund", []), result.get("refund_tertiary", []), result.get("escalation", []), narratives)}
      {_render_four_ops_html(result.get("four_ops_map", []), result.get("four_products_map", []), result.get("four_mapping_table", []))}
      {_render_typical_case_deep_dive_html(narratives.get("typical_case_deep_dive", []))}
      <section class="chart-card chart-grid-wide" data-reveal="card">
        <div class="chart-header">
          <div>
            <span class="chart-kicker">CAUSE & VOICE</span>
            <h3>三级问题原因线索、样例原声与典型案例</h3>
          </div>
        </div>
        {_render_tertiary_cause_detail_section(narratives.get("tertiary_cause_detail"))}
        {_merged_cause_voice_table(result, narratives)}
      </section>
    </section>
    """

    trend_section = f"""
    <section class="report-section" data-reveal="section" data-lazy="section">
      <div class="section-label"><span class="pulse-dot"></span><strong>SECTION 1.2</strong></div>
      <div class="section-heading">
        <div>
          <h2>1.2 投诉趋势与异动表现</h2>
          <p>按日识别问题爆发的关键时间节点，结合赛事/事件线索解释异常波动的潜在原因。</p>
        </div>
      </div>
      <div class="analysis-box analysis-box-gradient" data-reveal="card">
        <div class="analysis-header">
          <span class="chart-kicker">TREND INSIGHT</span>
          <h3>分析结论</h3>
        </div>
        {_narrative_stack(narratives.get("trend_conclusion") or _trend_insights(result, trend_view))}
      </div>
      {_trend_svg(trend_view.get("days", []), focus_note=trend_view.get("note"))}
      {_daily_detail_table_html(daily_detail_rows, trend_view.get("anomalies", []))}
      <section class="chart-card chart-grid-wide" data-reveal="card">
        <div class="chart-header">
          <div>
            <span class="chart-kicker">CHART SUMMARY</span>
            <h3>图表分析总结</h3>
          </div>
        </div>
        {_narrative_stack(trend_chart_summary)}
      </section>
      <section class="chart-card chart-grid-voice" data-reveal="card">
        <div class="chart-header">
          <div>
            <span class="chart-kicker">TREND VOICE</span>
            <h3>赛事日用户原声</h3>
          </div>
        </div>
        {_narrative_stack(trend_voice_summary)}
        {_trend_voice_cards(trend_voice_items, narratives)}
      </section>
      <section class="chart-card" data-reveal="card">
        <div class="chart-header">
          <div>
            <span class="chart-kicker">ANOMALY</span>
            <h3>异动节点</h3>
          </div>
        </div>
        {_narrative_stack(narratives.get("anomaly_summary"))}
        {_compact_anomaly_cards(trend_view.get("anomalies", []))}
      </section>
    </section>
    """

    if section_focus == "distribution":
        selected_sections = distribution_section
    elif section_focus == "trend":
        selected_sections = trend_section
    else:
        selected_sections = distribution_section + trend_section

    summary_section = _executive_summary_section(result, narratives, trend_view)

    style = """
  <style>
    :root {
      --background: #FAFAFA;
      --foreground: #0F172A;
      --muted: #F1F5F9;
      --muted-foreground: #64748B;
      --accent: #0052FF;
      --accent-secondary: #4D7CFF;
      --accent-strong: #1D4FFF;
      --accent-soft: rgba(0,82,255,0.08);
      --border: #E2E8F0;
      --card: #FFFFFF;
      --shadow: 0 12px 30px rgba(15, 23, 42, 0.08);
      --shadow-hover: 0 18px 42px rgba(15, 23, 42, 0.14);
      --radius: 8px;
    }
    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body, h1, h2, h3, h4, p, div, span, td, th, strong {
      writing-mode: horizontal-tb;
      text-orientation: mixed;
    }
    body {
      margin: 0;
      font-family: "Inter", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
      color: var(--foreground);
      background:
        radial-gradient(circle at top right, rgba(77,124,255,0.14), transparent 26%),
        radial-gradient(circle at top left, rgba(0,82,255,0.08), transparent 24%),
        var(--background);
      line-height: 1.65;
    }
    .page {
      max-width: 1160px;
      margin: 0 auto;
      padding: 36px 22px 72px;
    }
    .has-js [data-reveal] {
      opacity: 0;
      transform: translate3d(0, 30px, 0) scale(0.985);
      filter: blur(10px);
      transition:
        opacity .72s cubic-bezier(.16,1,.3,1),
        transform .72s cubic-bezier(.16,1,.3,1),
        filter .72s cubic-bezier(.16,1,.3,1);
      transition-delay: calc(var(--reveal-order, 0) * 55ms);
      will-change: opacity, transform, filter;
    }
    .has-js [data-reveal="section"] {
      transform: translate3d(0, 38px, 0);
      transition-duration: .82s;
    }
    .has-js [data-reveal="item"] {
      transform: translate3d(0, 22px, 0) scale(0.992);
      transition-duration: .62s;
    }
    .has-js [data-reveal].is-visible {
      opacity: 1;
      transform: translate3d(0, 0, 0) scale(1);
      filter: none;
    }
    [data-lazy="section"] {
      contain: layout paint style;
    }
    @supports (content-visibility: auto) {
      [data-lazy="section"] {
        content-visibility: auto;
        contain-intrinsic-size: 920px;
      }
      .section-dark[data-lazy="section"] {
        contain-intrinsic-size: 1180px;
      }
    }
    .hero {
      display: grid;
      grid-template-columns: 1.1fr 0.9fr;
      gap: 28px;
      align-items: stretch;
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 34px;
      overflow: hidden;
      position: relative;
      animation: fade-up .8s cubic-bezier(.16,1,.3,1) both;
    }
    .hero::before {
      content: "";
      position: absolute;
      inset: auto auto -120px -120px;
      width: 280px;
      height: 280px;
      background: radial-gradient(circle, rgba(0,82,255,0.12), transparent 70%);
      filter: blur(4px);
      pointer-events: none;
    }
    .hero::after {
      content: "";
      position: absolute;
      inset: auto 0 0 0;
      height: 4px;
      background: linear-gradient(90deg, var(--accent), var(--accent-secondary));
    }
    .hero-copy { position: relative; z-index: 1; }
    .section-label {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      padding: 8px 14px;
      border-radius: 999px;
      border: 1px solid rgba(0,82,255,0.26);
      background: rgba(0,82,255,0.06);
      color: var(--accent);
      font-family: "JetBrains Mono", Consolas, monospace;
      font-size: 12px;
      letter-spacing: 0.15em;
      text-transform: uppercase;
      white-space: nowrap;
    }
    .section-label-light {
      border-color: rgba(255,255,255,0.18);
      background: rgba(255,255,255,0.08);
      color: rgba(255,255,255,0.9);
    }
    .pulse-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: linear-gradient(135deg, var(--accent), var(--accent-secondary));
      box-shadow: 0 0 0 0 rgba(77,124,255,0.35);
      animation: pulse 2.4s ease-in-out infinite;
    }
    h1, h2 {
      font-family: "Calistoga", Georgia, "Times New Roman", "Microsoft YaHei", serif;
      margin: 0;
      font-weight: 400;
    }
    h1 {
      font-size: clamp(2.9rem, 6vw, 5.05rem);
      line-height: 1.05;
      margin-top: 18px;
      max-width: 9ch;
      position: relative;
    }
    h2 {
      font-size: clamp(2rem, 4vw, 3.25rem);
      line-height: 1.12;
    }
    h3 {
      margin: 0;
      font-size: 1.25rem;
      line-height: 1.3;
      font-weight: 600;
    }
    h4 {
      margin: 0;
      font-size: 1.05rem;
      line-height: 1.35;
      font-weight: 600;
    }
    .gradient-text {
      background: linear-gradient(90deg, var(--accent), var(--accent-secondary));
      -webkit-background-clip: text;
      background-clip: text;
      color: transparent;
    }
    .hero-copy .lead {
      margin: 18px 0 0;
      max-width: 700px;
      color: var(--muted-foreground);
      font-size: 1.05rem;
    }
    .subtle { color: var(--muted-foreground); }
    .hero-meta {
      margin: 12px 0 0;
      font-size: 0.95rem;
      max-width: 100%;
      word-break: break-word;
      overflow-wrap: anywhere;
    }
    .hero-visual {
      position: relative;
      min-height: 320px;
      border-radius: var(--radius);
      overflow: hidden;
      background:
        radial-gradient(circle, rgba(255,255,255,0.035) 1px, transparent 1px) 0 0 / 26px 26px,
        #0F172A;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.06);
      animation: fade-up .85s cubic-bezier(.16,1,.3,1) both .08s;
    }
    .hero-glow {
      position: absolute;
      inset: auto -10% -18% auto;
      width: 260px;
      height: 260px;
      background: radial-gradient(circle, rgba(77,124,255,0.34), transparent 70%);
      filter: blur(28px);
    }
    .hero-ring {
      position: absolute;
      width: 280px;
      height: 280px;
      left: 50%;
      top: 50%;
      transform: translate(-50%, -50%);
      border-radius: 50%;
      border: 1px dashed rgba(255,255,255,0.24);
      animation: spin 60s linear infinite;
    }
    .hero-orbit {
      position: absolute;
      width: 220px;
      height: 220px;
      left: 50%;
      top: 50%;
      transform: translate(-50%, -50%);
      border-radius: 50%;
      border: 1px solid rgba(255,255,255,0.08);
    }
    .hero-block {
      position: absolute;
      border-radius: 8px;
      background: linear-gradient(135deg, var(--accent), var(--accent-secondary));
      box-shadow: 0 10px 28px rgba(0,82,255,0.34);
    }
    .hero-block-a { width: 72px; height: 72px; top: 26px; right: 28px; }
    .hero-block-b { width: 22px; height: 22px; bottom: 26px; left: 28px; }
    .float-card {
      position: absolute;
      background: rgba(255,255,255,0.1);
      border: 1px solid rgba(255,255,255,0.12);
      backdrop-filter: blur(12px);
      border-radius: 8px;
      padding: 14px 16px;
      color: #FFFFFF;
      min-width: 170px;
      box-shadow: 0 16px 34px rgba(15,23,42,0.26);
    }
    .float-card strong { display: block; font-size: 1.75rem; line-height: 1; margin-top: 6px; }
    .float-card small { color: rgba(255,255,255,0.72); font-size: 0.8rem; }
    .float-card-1 { top: 38px; left: 30px; animation: float-a 5.2s ease-in-out infinite; }
    .float-card-2 { bottom: 40px; right: 34px; animation: float-b 4.6s ease-in-out infinite; }
    .hero-badge {
      display: inline-flex;
      gap: 8px;
      align-items: center;
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid rgba(255,255,255,0.16);
      background: rgba(255,255,255,0.08);
      font-size: 0.82rem;
    }
    .hero-badge .pulse-dot { transform: scale(.9); }
    .kpis {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 16px;
      margin: 28px 0 0;
    }
    .kpi {
      position: relative;
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 18px 18px 20px;
      box-shadow: var(--shadow);
      min-height: 132px;
      overflow: hidden;
      transition: transform .25s ease, box-shadow .25s ease, border-color .25s ease;
      animation: fade-up .8s cubic-bezier(.16,1,.3,1) both;
    }
    .kpi:nth-child(1){ animation-delay:.10s; }
    .kpi:nth-child(2){ animation-delay:.16s; }
    .kpi:nth-child(3){ animation-delay:.22s; }
    .kpi:nth-child(4){ animation-delay:.28s; }
    .kpi::after {
      content: "";
      position: absolute;
      inset: auto -18% -52% auto;
      width: 160px;
      height: 160px;
      background: radial-gradient(circle, rgba(0,82,255,0.12), transparent 68%);
    }
    .kpi:hover {
      transform: translateY(-4px);
      box-shadow: var(--shadow-hover);
      border-color: rgba(0,82,255,0.28);
    }
    .kpi .label {
      color: var(--muted-foreground);
      font-size: 0.82rem;
      margin-bottom: 10px;
    }
    .kpi .value {
      font-size: clamp(1.7rem, 3vw, 2.55rem);
      font-weight: 800;
      line-height: 1.1;
      word-break: break-word;
      overflow-wrap: anywhere;
    }
    .report-section {
      margin-top: 48px;
    }
    .section-dark {
      margin-top: 56px;
      padding: 34px;
      border-radius: var(--radius);
      background:
        radial-gradient(circle, rgba(255,255,255,0.03) 1px, transparent 1px) 0 0 / 28px 28px,
        radial-gradient(circle at top right, rgba(77,124,255,0.18), transparent 22%),
        #0F172A;
      position: relative;
      overflow: hidden;
      box-shadow: 0 22px 44px rgba(15,23,42,0.22);
    }
    .section-dark::before {
      content: "";
      position: absolute;
      inset: -10% auto auto -12%;
      width: 280px;
      height: 280px;
      background: radial-gradient(circle, rgba(77,124,255,0.22), transparent 70%);
      filter: blur(18px);
      pointer-events: none;
    }
    .section-heading {
      display: flex;
      justify-content: space-between;
      gap: 24px;
      align-items: end;
      margin: 16px 0 18px;
    }
    .section-heading p {
      margin: 10px 0 0;
      max-width: 760px;
      color: var(--muted-foreground);
      font-size: 1rem;
    }
    .section-heading-dark p { color: rgba(255,255,255,0.74); }
    .light-title { color: #FFFFFF; }
    .scope-strip {
      display: grid;
      grid-template-columns: 1.2fr 0.95fr 1.2fr;
      gap: 1px;
      background: var(--border);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      overflow: hidden;
    }
    .scope-strip > div {
      background: var(--card);
      padding: 16px;
    }
    .scope-strip span {
      display: inline-block;
      color: var(--accent);
      font-weight: 700;
      font-size: 0.8rem;
      margin-bottom: 6px;
    }
    .scope-strip p {
      margin: 0;
      color: var(--muted-foreground);
      font-size: 0.92rem;
    }
    .scope-strip-dark {
      background: rgba(255,255,255,0.08);
      border-color: rgba(255,255,255,0.1);
    }
    .scope-strip-dark > div { background: rgba(255,255,255,0.04); }
    .scope-strip-dark span { color: #8FB0FF; }
    .scope-strip-dark p { color: rgba(255,255,255,0.72); }
    .analysis-box {
      margin-top: 18px;
      padding: 20px 22px;
      border-radius: var(--radius);
      border: 1px solid var(--border);
      background: var(--card);
      box-shadow: var(--shadow);
      transition: transform .25s ease, box-shadow .25s ease, border-color .25s ease;
    }
    .analysis-box:hover {
      transform: translateY(-4px);
      box-shadow: var(--shadow-hover);
      border-color: rgba(0,82,255,0.22);
    }
    .analysis-box-gradient {
      background: linear-gradient(135deg, rgba(0,82,255,0.08), rgba(255,255,255,0.96));
      border-color: rgba(0,82,255,0.18);
    }
    .analysis-box-dark {
      background: rgba(255,255,255,0.05);
      border-color: rgba(255,255,255,0.12);
      box-shadow: none;
    }
    .unlabeled-card {
      margin-top: 18px;
      padding: 20px 22px;
      border-radius: var(--radius);
      border: 2px dashed #cbd5e1;
      border-left: 4px solid #f59e0b;
      background: #fffbeb;
      box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
    .unlabeled-card:hover {
      border-color: #f59e0b;
      box-shadow: 0 4px 16px rgba(245,158,11,0.12);
    }
    .unlabeled-card-header {
      display: flex;
      align-items: baseline;
      gap: 14px;
      margin-bottom: 10px;
      padding-bottom: 10px;
      border-bottom: 2px dashed #e2e8f0;
    }
    .unlabeled-card-header h3 {
      color: #92400e;
    }
    .unlabeled-card-header .chart-kicker {
      color: #d97706;
    }
    .analysis-header {
      display: flex;
      align-items: baseline;
      gap: 14px;
      margin-bottom: 10px;
    }
    .module-summary {
      margin: 0 0 14px;
      color: var(--muted-foreground);
      font-size: 0.96rem;
    }
    .narrative-stack {
      display: grid;
      gap: 10px;
      margin: 0 0 14px;
    }
    .narrative-stack p {
      margin: 0;
      color: var(--muted-foreground);
      font-size: 0.97rem;
      line-height: 1.72;
    }
    .narrative-stack-dark p {
      color: rgba(255,255,255,0.86);
    }
    .metric-pill-row {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: flex-start;
    }
    .metric-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-height: 34px;
      padding: 6px 12px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: rgba(0,82,255,0.04);
      color: var(--foreground);
      line-height: 1.4;
    }
    .metric-pill strong {
      font-size: 0.88rem;
      font-weight: 700;
    }
    .metric-pill span {
      color: var(--accent);
      font-size: 0.84rem;
      font-weight: 700;
      white-space: nowrap;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
      align-items: start;
    }
    .section-stack {
      display: grid;
      gap: 18px;
    }
    .chart-grid { margin-top: 18px; }
    .chart-grid-wide { margin-top: 18px; }
    .primary-detail-grid {
      grid-template-columns: 1fr;
    }
    .primary-detail-grid .chart-grid-wide {
      margin-top: 0;
    }
    .primary-detail-card > h4 {
      margin: 6px 0 10px;
      font-size: 0.96rem;
    }
    .tertiary-detail-list {
      display: grid;
      gap: 12px;
      margin: 16px 0;
    }
    .tertiary-detail {
      padding: 14px;
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: rgba(248,250,252,0.72);
    }
    .tertiary-detail h4 {
      margin: 0 0 8px;
      font-size: 0.98rem;
    }
    .chart-card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 20px;
      box-shadow: var(--shadow);
      transition: transform .25s ease, box-shadow .25s ease, border-color .25s ease;
    }
    .chart-card:hover {
      transform: translateY(-4px);
      box-shadow: var(--shadow-hover);
      border-color: rgba(0,82,255,0.22);
    }
    .chart-card-highlight {
      background: linear-gradient(135deg, rgba(0,82,255,0.06), rgba(255,255,255,1));
      border-color: rgba(0,82,255,0.18);
    }
    .chart-card-dark {
      margin-top: 18px;
      background: transparent;
      border-color: rgba(255,255,255,0.1);
      box-shadow: none;
      color: #FFFFFF;
      padding: 20px 0 0;
    }
    .chart-card-dark:hover {
      transform: none;
      box-shadow: none;
      border-color: rgba(255,255,255,0.1);
    }
    .chart-card-light { margin-top: 18px; }
    .chart-header {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 14px;
    }
    .chart-header-dark { padding: 0 0 8px; }
    .chart-kicker {
      display: inline-block;
      color: var(--accent);
      font-family: "JetBrains Mono", Consolas, monospace;
      font-size: 0.78rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      margin-bottom: 8px;
    }
    .chart-kicker-light { color: #9EB6FF; }
    .pie-layout {
      display: grid;
      grid-template-columns: 248px 1fr;
      gap: 16px;
      align-items: center;
    }
    .donut-chart {
      width: 232px;
      height: 232px;
      display: block;
      margin: 0 auto;
    }
    .donut-total {
      font-size: 1.95rem;
      font-weight: 800;
      fill: var(--foreground);
    }
    .donut-caption {
      font-size: 0.74rem;
      fill: var(--muted-foreground);
    }
    .legend-stack {
      display: grid;
      gap: 10px;
      min-width: 0;
    }
    .legend-row {
      display: grid;
      grid-template-columns: 12px minmax(0, 1fr) auto auto;
      gap: 10px;
      align-items: center;
      padding: 8px 10px;
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: rgba(255,255,255,0.84);
    }
    .legend-swatch {
      width: 10px;
      height: 10px;
      border-radius: 50%;
    }
    .legend-name {
      min-width: 0;
      word-break: normal;
      overflow-wrap: anywhere;
    }
    .legend-share { color: var(--muted-foreground); }
    .rank-chart {
      display: grid;
      gap: 14px;
      margin-top: 6px;
    }
    .rank-row {
      display: grid;
      grid-template-columns: 48px minmax(150px, 220px) 1fr 54px;
      gap: 12px;
      align-items: center;
    }
    .rank-index {
      width: 38px;
      height: 38px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      background: linear-gradient(135deg, rgba(0,82,255,0.12), rgba(77,124,255,0.22));
      color: var(--accent-strong);
      font-weight: 700;
      font-family: "JetBrains Mono", Consolas, monospace;
    }
    .rank-label {
      min-width: 0;
      font-weight: 600;
      word-break: keep-all;
      overflow-wrap: break-word;
    }
    .rank-track {
      height: 16px;
      background: var(--muted);
      border-radius: 999px;
      overflow: hidden;
      position: relative;
    }
    .rank-fill {
      width: var(--target-width);
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--accent), var(--accent-secondary));
      transform-origin: left center;
      transform: scaleX(0);
    }
    .rank-value {
      text-align: right;
      font-weight: 700;
      color: var(--muted-foreground);
      white-space: nowrap;
    }
    .bar-row {
      display: grid;
      grid-template-columns: minmax(110px, 140px) 1fr 42px;
      gap: 12px;
      align-items: center;
      margin: 10px 0;
    }
    .bar-label {
      min-width: 0;
      word-break: keep-all;
      overflow-wrap: break-word;
    }
    .bar-track {
      height: 16px;
      background: var(--muted);
      border-radius: 999px;
      overflow: hidden;
      position: relative;
    }
    .bar-fill {
      width: var(--target-width);
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--accent), var(--accent-secondary));
      transform-origin: left center;
      transform: scaleX(0);
    }
    .bar-fill.alt {
      background: linear-gradient(90deg, #F97316, #FDBA74);
    }
    .bar-value {
      text-align: right;
      font-weight: 700;
      color: var(--muted-foreground);
      white-space: nowrap;
    }
    .risk-stack {
      display: grid;
      gap: 12px;
    }
    .risk-row {
      display: grid;
      grid-template-columns: 96px 1fr;
      gap: 12px;
      align-items: start;
      padding: 12px;
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: rgba(255,255,255,0.85);
    }
    .risk-row > span {
      font-size: 0.9rem;
      font-weight: 700;
      color: var(--muted-foreground);
      padding-top: 4px;
    }
    .detail-grid, .voice-grid, .signal-grid {
      display: grid;
      gap: 14px;
    }
    .detail-card, .voice-card, .signal-card {
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: linear-gradient(135deg, rgba(0,82,255,0.03), rgba(255,255,255,0.98));
      padding: 16px;
      transition: transform .25s ease, box-shadow .25s ease, border-color .25s ease;
    }
    .detail-card:hover, .voice-card:hover, .signal-card:hover {
      transform: translateY(-4px);
      box-shadow: var(--shadow);
      border-color: rgba(0,82,255,0.22);
    }
    .detail-head, .voice-head, .signal-card-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: start;
      margin-bottom: 12px;
    }
    .detail-head p, .signal-card p, .voice-meta {
      margin: 6px 0 0;
      color: var(--muted-foreground);
      font-size: 0.92rem;
    }
    .detail-count, .voice-head span {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 44px;
      height: 32px;
      padding: 0 10px;
      border-radius: 999px;
      background: rgba(0,82,255,0.08);
      color: var(--accent);
      font-weight: 700;
      white-space: nowrap;
    }
    .voice-body { display: grid; gap: 8px; }
    .quote {
      position: relative;
      padding: 12px 14px 12px 16px;
      border-radius: var(--radius);
      border-left: 3px solid var(--accent);
      background: rgba(0,82,255,0.04);
      color: var(--muted-foreground);
      word-break: break-word;
      overflow-wrap: anywhere;
    }
    .chip-cloud {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: flex-start;
    }
    .tag {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      min-height: 34px;
      max-width: 100%;
      padding: 6px 10px;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: rgba(255,255,255,0.94);
      white-space: normal;
      word-break: break-word;
      overflow-wrap: anywhere;
      line-height: 1.45;
      box-shadow: 0 1px 2px rgba(15,23,42,0.04);
    }
    .tag strong {
      white-space: nowrap;
      color: var(--foreground);
    }
    .tag-text {
      min-width: 0;
      overflow-wrap: anywhere;
    }
    .insights {
      margin: 0;
      padding-left: 20px;
    }
    .insights li { margin: 8px 0; }
    .insights-dark li { color: rgba(255,255,255,0.88); }
    .trend-svg {
      width: 100%;
      height: auto;
      display: block;
      border-radius: var(--radius);
      margin-top: 6px;
    }
    .axis-tick {
      font-size: 12px;
      fill: var(--muted-foreground);
    }
    .axis-tick-dark {
      fill: rgba(255,255,255,0.68);
    }
    .axis-title {
      font-size: 13px;
      font-weight: 700;
    }
    .axis-title-dark {
      fill: rgba(255,255,255,0.92);
    }
    .event-label {
      font-size: 11px;
      font-weight: 700;
      fill: #9EB6FF;
    }
    .legend {
      display: flex;
      flex-wrap: wrap;
      gap: 16px;
      margin-top: 14px;
      color: var(--muted-foreground);
      font-size: 0.92rem;
    }
    .legend-light { color: rgba(255,255,255,0.82); }
    .trend-note {
      margin: 12px 0 2px;
      color: var(--muted-foreground);
      font-size: 0.9rem;
      line-height: 1.6;
    }
    .event-summary {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }
    .event-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-height: 32px;
      padding: 6px 10px;
      border-radius: 999px;
      border: 1px solid rgba(0,82,255,0.14);
      background: rgba(0,82,255,0.05);
      color: var(--muted-foreground);
      font-size: 0.84rem;
      line-height: 1.4;
    }
    .event-pill-strong {
      background: rgba(0,82,255,0.08);
      border-color: rgba(0,82,255,0.24);
    }
    .event-pill-peak {
      box-shadow: 0 0 0 1px rgba(0,82,255,0.16) inset;
    }
    .event-pill strong {
      color: var(--accent);
      white-space: nowrap;
    }
    .dot {
      display: inline-block;
      width: 10px;
      height: 10px;
      border-radius: 50%;
      margin-right: 6px;
      vertical-align: middle;
    }
    .dot.count { background: linear-gradient(135deg, #0052FF, #4D7CFF); }
    .dot.negative { background: linear-gradient(135deg, #F97316, #FDBA74); }
    .dot.event { background: #9EB6FF; }
    .table-scroll {
      overflow-x: auto;
      padding-bottom: 4px;
    }
    .data-table {
      width: 100%;
      border-collapse: collapse;
      min-width: 920px;
      font-size: 0.92rem;
    }
    .drilldown-table {
      min-width: 1280px;
    }
    .data-table th,
    .data-table td {
      padding: 12px 12px;
      border-bottom: 1px solid var(--border);
      text-align: left;
      vertical-align: top;
      line-height: 1.55;
      white-space: normal;
      word-break: keep-all;
      overflow-wrap: break-word;
    }
    .data-table th {
      font-size: 0.78rem;
      color: var(--muted-foreground);
      background: var(--muted);
      font-weight: 700;
    }
    .data-table tr:last-child td { border-bottom: 0; }
    .analysis-box strong { display: inline-block; margin-bottom: 6px; }
    .signal-chip {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      height: 30px;
      padding: 0 10px;
      border-radius: 999px;
      background: rgba(0,82,255,0.1);
      color: var(--accent);
      font-size: 0.82rem;
      font-weight: 700;
      white-space: nowrap;
    }
    .signal-meta {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-top: 12px;
    }
    .signal-meta span {
      display: inline-block;
      color: var(--muted-foreground);
      font-size: 0.76rem;
      margin-bottom: 4px;
      font-weight: 700;
    }
    .signal-meta p {
      margin: 0;
      font-size: 0.9rem;
      word-break: break-word;
      overflow-wrap: anywhere;
    }
    .signal-note {
      margin: 12px 0 0 !important;
      color: var(--muted-foreground);
      font-size: 0.84rem !important;
      line-height: 1.55;
    }
    .day-marker {
      display: grid;
      gap: 8px;
      min-width: 220px;
    }
    .day-marker-copy {
      display: grid;
      gap: 6px;
      min-width: 0;
    }
    .day-marker-copy strong {
      color: var(--foreground);
      font-size: 0.92rem;
      line-height: 1.45;
      word-break: break-word;
      overflow-wrap: anywhere;
    }
    .day-marker-subtle {
      color: var(--muted-foreground);
      font-size: 0.82rem;
      line-height: 1.5;
    }
    .match-pill {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 28px;
      width: fit-content;
      padding: 0 10px;
      border-radius: 999px;
      background: rgba(0,82,255,0.1);
      color: var(--accent);
      font-size: 0.78rem;
      font-weight: 700;
      white-space: nowrap;
    }
    .match-pill-muted {
      background: var(--muted);
      color: var(--muted-foreground);
    }
    .match-pill-dark {
      background: rgba(158,182,255,0.16);
      color: #C8D7FF;
    }
    .match-pill-muted-dark {
      background: rgba(255,255,255,0.08);
      color: rgba(255,255,255,0.76);
    }
    .footnote {
      margin-top: 46px;
    }
    .has-js [data-reveal].is-visible .rank-fill {
      animation: grow-x 1.05s cubic-bezier(.16,1,.3,1) both;
    }
    .has-js [data-reveal].is-visible .bar-fill {
      animation: grow-x 1s cubic-bezier(.16,1,.3,1) both;
    }
    html:not(.has-js) .rank-fill {
      animation: grow-x 1.05s cubic-bezier(.16,1,.3,1) both;
    }
    html:not(.has-js) .bar-fill {
      animation: grow-x 1s cubic-bezier(.16,1,.3,1) both;
    }
    @keyframes spin {
      from { transform: translate(-50%, -50%) rotate(0deg); }
      to { transform: translate(-50%, -50%) rotate(360deg); }
    }
    @keyframes pulse {
      0%, 100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(77,124,255,0.38); }
      50% { transform: scale(1.24); box-shadow: 0 0 0 8px rgba(77,124,255,0); }
    }
    @keyframes float-a {
      0%, 100% { transform: translateY(0px); }
      50% { transform: translateY(-10px); }
    }
    @keyframes float-b {
      0%, 100% { transform: translateY(0px); }
      50% { transform: translateY(10px); }
    }
    @keyframes grow-x {
      from { transform: scaleX(0); }
      to { transform: scaleX(1); }
    }
    @keyframes fade-up {
      from { opacity: 0; transform: translateY(26px); }
      to { opacity: 1; transform: translateY(0); }
    }
    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after { animation: none !important; transition: none !important; scroll-behavior: auto !important; }
      .has-js [data-reveal] {
        opacity: 1 !important;
        transform: none !important;
        filter: none !important;
      }
    }
    @media (max-width: 1100px) {
      .hero,
      .kpis,
      .grid,
      .pie-layout,
      .scope-strip,
      .signal-meta {
        grid-template-columns: 1fr;
      }
      .hero { padding: 28px; }
      .hero-visual { min-height: 280px; }
      .rank-row {
        grid-template-columns: 40px minmax(130px, 1fr) 1fr 48px;
      }
      .risk-row { grid-template-columns: 88px 1fr; }
    }
    @media (max-width: 760px) {
      .page { padding: 22px 14px 52px; }
      .hero,
      .section-dark {
        padding: 22px 18px;
      }
      .kpis { gap: 12px; }
      .kpi { min-height: 112px; }
      .section-heading { display: block; }
      .section-heading p { margin-top: 10px; }
      .chart-card, .analysis-box { padding: 16px; }
      .bar-row {
        grid-template-columns: minmax(88px, 110px) 1fr 34px;
        gap: 8px;
      }
      .rank-row {
        grid-template-columns: 34px minmax(104px, 1fr);
        gap: 10px;
      }
      .rank-track, .rank-value { grid-column: 2; }
      .rank-value { text-align: left; }
      .risk-row { grid-template-columns: 1fr; }
      .tag { width: 100%; justify-content: space-between; }
      .data-table { min-width: 760px; }
    }
  </style>
    """

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
   <title>一、整体情况 — 视频产品重点赛事用户洞察分析专题报告</title>
  <script>document.documentElement.classList.add("has-js");</script>
  {style}
</head>
<body>
  <main class="page">
    <section class="hero">
      <div class="hero-copy">
        <div class="section-label"><span class="pulse-dot"></span><strong>{_e(focus_label)}</strong></div>
         <h1>视频产品重点赛事<span class="gradient-text">{_e(focus_title)}</span></h1>
        <p class="lead">{_e(focus_description)}</p>
        <p class="subtle hero-meta">报告周期：{_e(period_start[:10]) if len(period_start) > 10 else _e(period_start)} 至 {_e(period_end[:10]) if len(period_end) > 10 else _e(period_end)}</p>
      </div>
      <div class="hero-visual">
        <div class="hero-glow"></div>
        <div class="hero-ring"></div>
        <div class="hero-orbit"></div>
        <div class="hero-block hero-block-a"></div>
        <div class="hero-block hero-block-b"></div>
        <div class="float-card float-card-1">
          <div class="hero-badge"><span class="pulse-dot"></span><span>{_e(signal_label)}</span></div>
          <strong>{_e(signal_value)}</strong>
          <small>{_e(signal_desc)}</small>
        </div>
        <div class="float-card float-card-2">
          <div class="hero-badge"><span class="pulse-dot"></span><span>{_e(issue_label)}</span></div>
          <strong>{_e(issue_value)}</strong>
          <small>{_e(issue_desc)}</small>
        </div>
      </div>
    </section>


    <section class="kpis">
      {"".join(f'<article class="kpi"><div class="label">{_e(item["label"])}</div><div class="value">{_e(item["value"])}</div></article>' for item in kpis)}
    </section>

    {selected_sections}
  </main>
  <script>
    (() => {{
      const prefersReducedMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const revealNodes = Array.from(document.querySelectorAll("[data-reveal]"));
      if (!revealNodes.length) {{
        return;
      }}
      const sectionRoots = revealNodes.filter((node) => node.dataset.reveal === "section");
      const observedNodes = sectionRoots.length
        ? sectionRoots
        : revealNodes.filter((node) => !node.closest('[data-reveal="section"]') || node.dataset.reveal === "section");
      const pending = new Set(observedNodes);

      const show = (node, immediate) => {{
        if (node.classList.contains("is-visible")) {{
          return;
        }}
        if (immediate) {{
          node.style.transitionDelay = "0ms";
        }}
        node.classList.add("is-visible");
      }};

      const revealBranch = (root, immediate) => {{
        show(root, immediate);
        const children = Array.from(root.querySelectorAll("[data-reveal]")).filter((node) => node !== root);
        children.forEach((node, index) => {{
          node.style.setProperty("--reveal-order", String(Math.min(index + 1, 8)));
          const activate = () => show(node, immediate);
          if (immediate) {{
            activate();
            return;
          }}
          window.setTimeout(activate, Math.min(index, 8) * 55);
        }});
      }};

      const isNearViewport = (node) => {{
        const rect = node.getBoundingClientRect();
        const enterTop = window.innerHeight * 0.96;
        const leaveBottom = -160;
        return rect.top <= enterTop && rect.bottom >= leaveBottom;
      }};

      const activateNode = (node, immediate) => {{
        if (!pending.has(node)) {{
          return;
        }}
        pending.delete(node);
        if (node.dataset.reveal === "section") {{
          revealBranch(node, immediate);
          return;
        }}
        show(node, immediate);
      }};

      const checkPending = () => {{
        pending.forEach((node) => {{
          if (isNearViewport(node)) {{
            activateNode(node, false);
          }}
        }});
        if (!pending.size) {{
          window.removeEventListener("scroll", checkPending, passiveOptions);
          window.removeEventListener("resize", checkPending);
        }}
      }};

      const passiveOptions = {{ passive: true }};

      if (prefersReducedMotion || !("IntersectionObserver" in window)) {{
        observedNodes.forEach((node) => {{
          activateNode(node, true);
        }});
        return;
      }}

      const observer = new IntersectionObserver(
        (entries) => {{
          entries.forEach((entry) => {{
            if (!entry.isIntersecting && !isNearViewport(entry.target)) {{
              return;
            }}
            activateNode(entry.target, false);
            observer.unobserve(entry.target);
          }});
        }},
        {{
          threshold: 0,
          rootMargin: "160px 0px -12% 0px",
        }},
      );

      observedNodes.forEach((node, index) => {{
        node.style.setProperty("--reveal-order", String(index % 4));
        if (isNearViewport(node)) {{
          activateNode(node, true);
        }} else {{
          observer.observe(node);
        }}
      }});

      if (pending.size) {{
        window.addEventListener("scroll", checkPending, passiveOptions);
        window.addEventListener("resize", checkPending);
        window.requestAnimationFrame(checkPending);
      }}
    }})();
  </script>
</body>
</html>
"""

    html = _sanitize_report_terms(enforce_style_contract(html))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path
