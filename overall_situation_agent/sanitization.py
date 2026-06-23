from __future__ import annotations

import copy
import re
from typing import Any

SENSITIVE_IDENTIFIER_FIELDS = frozenset({
    "phone_number",
    "user_identity",
    "session_id",
    "gd_identity",
})

BUSINESS_TERM_REPLACEMENTS = {
    "\u54aa\u5495\u89c6\u9891": "视频产品",
    "\u54aa\u5495": "视频产品",
    "\u4e2d\u8d85\u8d5b\u4e8b": "重点赛事",
    "\u8425\u670d\u5de5\u4f5c\u8bb0\u5f55": "业务工作记录",
}

_PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_ID_CARD_RE = re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)")
_EMAIL_RE = re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9.-])")
_LONG_NUMERIC_ID_RE = re.compile(r"(?<!\d)\d{10,}(?!\d)")


def _mask_phone(match: re.Match[str]) -> str:
    value = match.group(0)
    return f"{value[:3]}****{value[-4:]}"


def mask_identifier(value: Any) -> str:
    """Mask an identifier field before it can reach report output."""
    if value is None:
        return ""
    text = str(value).strip()
    return "已脱敏" if text else ""


def mask_sensitive_text(value: Any) -> str:
    """Mask PII/business-specific terms inside free text."""
    if value is None:
        return ""
    text = str(value)
    for raw, replacement in BUSINESS_TERM_REPLACEMENTS.items():
        text = text.replace(raw, replacement)
    text = _PHONE_RE.sub(_mask_phone, text)
    text = _ID_CARD_RE.sub("身份证号已脱敏", text)
    text = _EMAIL_RE.sub("邮箱已脱敏", text)
    text = _LONG_NUMERIC_ID_RE.sub("编号已脱敏", text)
    return text


def sanitize_report_payload(value: Any, *, parent_key: str | None = None) -> Any:
    """Deep-copy a report payload with sensitive fields/text masked."""
    if isinstance(value, dict):
        sanitized: dict[Any, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text in SENSITIVE_IDENTIFIER_FIELDS:
                sanitized[key] = mask_identifier(item)
            else:
                sanitized[key] = sanitize_report_payload(item, parent_key=key_text)
        return sanitized
    if isinstance(value, list):
        return [sanitize_report_payload(item, parent_key=parent_key) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_report_payload(item, parent_key=parent_key) for item in value)
    if isinstance(value, str):
        return mask_sensitive_text(value)
    return copy.deepcopy(value)
