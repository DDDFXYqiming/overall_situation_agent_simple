from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from overall_situation_agent.aggregations import normalize_unlabeled_analysis
from overall_situation_agent.markdown_renderer import render_markdown_report
from overall_situation_agent.report import render_html_report
from overall_situation_agent.sanitization import mask_sensitive_text, sanitize_report_payload

PHONE = "138" + "1234" + "5678"
EMAIL = "a" + "@" + "example.com"
ID_CARD = "110101" + "19900101" + "1234"
WORK_ORDER_ID = "GD-" + "20260301" + "0001"


class SanitizationTests(unittest.TestCase):
    def test_mask_sensitive_text_masks_personal_and_business_terms(self) -> None:
        product_name = "\u54aa\u5495\u89c6\u9891"
        event_name = "\u4e2d\u8d85\u8d5b\u4e8b"
        text = f"{product_name}{event_name}用户 phone={PHONE} email={EMAIL} id={ID_CARD}"

        masked = mask_sensitive_text(text)

        self.assertNotIn(product_name, masked)
        self.assertNotIn(event_name, masked)
        self.assertNotIn(PHONE, masked)
        self.assertNotIn(EMAIL, masked)
        self.assertNotIn(ID_CARD, masked)
        self.assertIn("视频产品重点赛事", masked)
        self.assertIn("138****5678", masked)

    def test_sanitize_report_payload_masks_identifier_fields_recursively(self) -> None:
        payload = {
            "gd_identity": WORK_ORDER_ID,
            "items": [{"phone_number": PHONE, "text": f"联系 {PHONE}"}],
        }

        sanitized = sanitize_report_payload(payload)

        self.assertEqual(sanitized["gd_identity"], "已脱敏")
        self.assertEqual(sanitized["items"][0]["phone_number"], "已脱敏")
        self.assertIn("138****5678", sanitized["items"][0]["text"])
        self.assertNotIn(PHONE, str(sanitized))

    def test_unlabeled_samples_are_masked_before_report_payload_use(self) -> None:
        response = {
            "hits": {"total": {"value": 1}},
            "aggregations": {
                "samples": {
                    "hits": {
                        "hits": [
                            {
                                "_source": {
                                    "gd_identity": WORK_ORDER_ID,
                                    "content": f"用户手机号{PHONE}，邮箱{EMAIL}",
                                    "cs_reply": f"已按工单{WORK_ORDER_ID}处理",
                                    "customer_key_appeal": f"要求联系{PHONE}",
                                }
                            }
                        ]
                    }
                },
                "emotion": {"buckets": []},
                "biz_member_cluster": {"buckets": []},
                "province": {"buckets": []},
                "service_type": {"buckets": []},
                "csp_name": {"buckets": []},
                "operation_action": {"buckets": []},
                "latent_need": {"buckets": []},
                "customer_key_appeal": {"buckets": []},
                "has_refund_demand": {"buckets": []},
                "has_escalation": {"buckets": []},
                "insight_dimension": {"buckets": []},
                "time_period": {"buckets": []},
            },
        }

        result = normalize_unlabeled_analysis(response)
        sample = result["samples"][0]

        self.assertEqual(sample["gd_identity"], "已脱敏")
        self.assertNotIn(PHONE, str(sample))
        self.assertNotIn(EMAIL, str(sample))
        self.assertIn("138****5678", sample["content_excerpt"])

    def test_renderers_mask_sensitive_text_at_output_boundary(self) -> None:
        result = {
            "query": {"section_focus": "distribution"},
            "filters": {},
            "period": {"min": "2026-03-01", "max": "2026-03-02"},
            "total": 1,
            "total_with_unlabeled": 1,
            "source_files": [],
            "schedule": {"status": "missing", "message": "未提供赛程文件", "days": {}},
            "primary": [{"key": "通用分类", "count": 1}],
            "secondary": [{"key": "通用子类", "count": 1}],
            "tertiary": [{"key": "通用问题", "count": 1}],
            "emotion": [],
            "service_type": [],
            "province": [],
            "province_refund": [],
            "refund": [],
            "refund_tertiary": [],
            "escalation": [],
            "four_ops_map": [],
            "four_products_map": [],
            "four_mapping_table": [],
            "top_tertiary_examples": [],
            "unlabeled_analysis": {"unlabeled_total": 0},
            "unlabeled_trend_analysis": {"unlabeled_total": 0},
            "anomalies": [],
            "daily": [],
            "narratives": {
                "executive_summary": f"\u54aa\u5495\u89c6\u9891\u4e2d\u8d85\u8d5b\u4e8b样例：联系{PHONE}，邮箱{EMAIL}。",
                "distribution_conclusion": [f"用户标识 USER-001，手机号{PHONE}。"],
            },
        }

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            md_path = render_markdown_report(result, base / "report.md")
            html_path = render_html_report(result, base / "report.html")
            rendered = md_path.read_text(encoding="utf-8") + html_path.read_text(encoding="utf-8")

        self.assertNotIn("\u54aa\u5495\u89c6\u9891", rendered)
        self.assertNotIn("\u4e2d\u8d85\u8d5b\u4e8b", rendered)
        self.assertNotIn(PHONE, rendered)
        self.assertNotIn(EMAIL, rendered)
        self.assertIn("视频产品重点赛事", rendered)
        self.assertIn("138****5678", rendered)

    def test_source_has_no_known_local_business_paths(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        source_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (repo / "overall_situation_agent").glob("*.py")
        )

        local_user = "\u0038\u0036\u0031\u0038\u0037"
        forbidden_terms = (
            "C:" + "\\Users\\" + local_user,
            "/mnt/c/" + "Users/" + local_user,
            "\u8425\u670d\u5de5\u4f5c\u8bb0\u5f55",
            "\u65b0\u6570\u636e20260508",
            "\u54aa\u5495\u89c6\u9891",
            "\u4e2d\u8d85\u8d5b\u4e8b",
        )
        for forbidden in forbidden_terms:
            self.assertNotIn(forbidden, source_text)


if __name__ == "__main__":
    unittest.main()
