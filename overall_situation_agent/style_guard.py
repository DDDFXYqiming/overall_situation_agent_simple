from __future__ import annotations

from pathlib import Path

ALLOWED_COLORS = {
    "#1d252c",
    "#65717b",
    "#d7dde2",
    "#f7f9fb",
    "#006d77",
    "#c44536",
    "#ffffff",
    "#eef3f5",
    "#e9eef1",
}

REQUIRED_SELECTORS = [
    ".page",
    ".kpis",
    ".kpi",
    ".grid",
    ".bar-row",
    ".trend-svg",
    ".tag",
    ".quote",
]


class StyleGuardError(ValueError):
    pass


def enforce_style_contract(html: str) -> str:
    lower = html.lower()
    forbidden = ["<script src", "<link", "@import", "iframe", "position: fixed", "letter-spacing: -", "javascript:"]
    found = [token for token in forbidden if token in lower]
    if found:
        raise StyleGuardError(f"HTML 样式或结构包含不允许的内容：{', '.join(found)}")
    missing = [selector for selector in REQUIRED_SELECTORS if selector not in html]
    if missing:
        raise StyleGuardError(f"HTML 缺少固定样式选择器：{', '.join(missing)}")
    return html


def enforce_style_file(path: Path) -> None:
    html = path.read_text(encoding="utf-8")
    enforce_style_contract(html)
