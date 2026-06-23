from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from overall_situation_agent.markdown_renderer import render_markdown_report
from overall_situation_agent.markdown_renderer import _anomaly_table, _trend_voice_markdown
from overall_situation_agent.report import render_html_report
from overall_situation_agent.report import _compact_anomaly_cards


LONG_USER_VOICE = (
    "用户表示购买会员后仍不清楚退订入口、自动续费规则和退费条件，认为页面提示与客服解释之间存在落差，"
    "希望一次性说明能否退订、何时生效、是否退费以及后续如何查询处理结果，避免反复咨询和等待。"
)


def _minimal_result() -> dict:
    tertiary_label = "退订困难/自动续费争议"
    return {
        "query": {"section_focus": "full"},
        "filters": {},
        "period": {"min": "2026-03-01", "max": "2026-03-02"},
        "total": 10,
        "total_with_unlabeled": 10,
        "source_files": [],
        "schedule": {"status": "missing", "message": "未提供赛程文件，1.2 未标注赛事日。", "days": {}},
        "primary": [{"key": "业务体验", "count": 10}],
        "secondary": [{"key": "订购退订", "count": 10}],
        "tertiary": [{"key": tertiary_label, "count": 10}],
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
        "daily": [
            {
                "date": "2026-03-01",
                "count": 4,
                "negative_ratio": 0.25,
                "top_primary": [{"key": "业务体验", "count": 4}],
                "top_secondary": [{"key": "订购退订", "count": 4}],
                "top_tertiary": [{"key": tertiary_label, "count": 4}],
            },
            {
                "date": "2026-03-02",
                "count": 6,
                "negative_ratio": 0.3,
                "top_primary": [{"key": "业务体验", "count": 6}],
                "top_secondary": [{"key": "订购退订", "count": 6}],
                "top_tertiary": [{"key": tertiary_label, "count": 6}],
            },
        ],
        "narratives": {
            "executive_summary": "二、三大问题\n退订链路问题集中。\n\n四、行动建议\n优化退订规则说明。",
            "distribution_conclusion": ["业务体验问题集中在退订链路。"],
            "primary_overview": ["一级问题以业务体验为主。"],
            "secondary_overview": ["二级问题以订购退订为主。"],
            "tertiary_overview": ["三级问题以退订困难为主。"],
            "primary_summaries": [
                {
                    "label": "业务体验",
                    "summary": "分析小结：业务体验类问题共10条，占总量100.0%；同节表格Top3为退订困难/自动续费争议（10条，100.0%）。用户主要围绕退订路径、自动续费认知和退费规则提出疑问，说明订购后的解释链路需要更清晰。",
                }
            ],
            "primary_overall_evaluation": [
                "业务体验是当前整体情况中最需要优先处理的一级标签。",
                "后续应围绕退订说明、续费提醒和客服处理闭环保持统一口径。",
            ],
            "tertiary_cause_detail": [
                {
                    "label": tertiary_label,
                    "count": 10,
                    "share": "100.0%",
                    "user_voice_natural": LONG_USER_VOICE,
                    "content_summary": "用户集中反映退订入口不清楚、自动续费感知弱。",
                    "cs_reply_summary": "客服多以解释规则、记录诉求和引导操作为主。",
                    "customer_appeal_summary": "用户诉求集中在退订和退费。",
                    "customer_keywords_summary": "关键词集中在退订、自动续费、退费。",
                    "cs_action_summary": "客服处理动作集中在解释规则和引导操作。",
                    "cs_keywords_summary": "客服关键词集中在规则、退订、记录。",
                    "root_cause": "根因在于续费规则提示和退订路径说明不足。",
                }
            ],
            "trend_conclusion": ["3月2日问题量高于3月1日。"],
            "trend_chart_summary": ["趋势整体平稳，小幅上升。"],
            "trend_voice_summary": ["当前没有赛事日样例原声。"],
            "anomaly_summary": ["未发现明显异动节点。"],
            "unlabeled_distribution_summary": [],
            "unlabeled_trend_summary": [],
            "typical_case_deep_dive": [],
        },
    }


class ReportRenderingTests(unittest.TestCase):
    def test_markdown_and_native_html_share_required_report_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            md_path = render_markdown_report(_minimal_result(), base / "report.md")
            html_path = render_html_report(_minimal_result(), base / "report.html")

            markdown = md_path.read_text(encoding="utf-8")
            html = html_path.read_text(encoding="utf-8")

        for text in ("用户核心诉求分布", "退订困难/自动续费争议", "一级标签综合评价", "每日明细数据"):
            self.assertIn(text, markdown)
            self.assertIn(text, html)
        self.assertIn(LONG_USER_VOICE, markdown)
        self.assertIn(LONG_USER_VOICE, html)
        self.assertNotIn(LONG_USER_VOICE[:97] + "...", markdown)
        self.assertNotIn(LONG_USER_VOICE[:97] + "...", html)
        self.assertNotIn("markdown.css", html)
        self.assertNotIn("markdown-body", html)

    def test_daily_detail_renders_all_days_for_chart_data(self) -> None:
        result = _minimal_result()
        result["period"] = {"min": "2026-03-01", "max": "2026-03-31"}
        result["daily"] = [
            {
                "date": f"2026-03-{day:02d}",
                "count": day,
                "negative_ratio": 0.1,
                "top_primary": [{"key": "业务体验", "count": day}],
                "top_secondary": [{"key": "订购退订", "count": day}],
                "top_tertiary": [{"key": "退订困难/自动续费争议", "count": day}],
            }
            for day in range(1, 32)
        ]

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            md_path = render_markdown_report(result, base / "report.md")
            html_path = render_html_report(result, base / "report.html")
            markdown = md_path.read_text(encoding="utf-8")
            html = html_path.read_text(encoding="utf-8")

        for day in range(1, 32):
            self.assertIn(f"| 2026-03-{day:02d} |", markdown)
            self.assertIn(f"<td>2026-03-{day:02d}</td>", html)

    def test_trend_voice_top3_share_uses_day_total_denominator(self) -> None:
        trend_view = {
            "days": [
                {
                    "date": "2026-03-07",
                    "count": 304,
                    "negative_ratio": 0.625,
                    "is_matchday": True,
                    "matchday": {"match_summary": "赛事日"},
                    "top_tertiary": [
                        {"key": "退订困难/自动续费争议", "count": 105},
                        {"key": "权益无法兑换/使用", "count": 98},
                        {"key": "多端体验差异", "count": 53},
                    ],
                    "samples": [{"content_excerpt": "用户投诉权益无法观看。"}],
                }
            ],
            "anomalies": [],
        }

        markdown = _trend_voice_markdown(trend_view, {})

        self.assertIn("退订困难/自动续费争议（共105条，占比34.5%）", markdown)
        self.assertIn("权益无法兑换/使用（共98条，占比32.2%）", markdown)
        self.assertIn("多端体验差异（共53条，占比17.4%）", markdown)
        self.assertNotIn("占比41.0%", markdown)

    def test_anomaly_table_uses_day_total_denominator_and_explains_scope(self) -> None:
        anomaly = {
            "date": "2026-03-14",
            "count": 242,
            "day_over_day_growth": 2.781,
            "negative_ratio": 0.558,
            "top_primary": [{"key": "业务体验", "count": 138}],
            "top_secondary": [{"key": "权益使用", "count": 85}],
            "top_tertiary": [{"key": "权益无法兑换/使用", "count": 50}],
            "top_service_type": [{"key": "投诉", "count": 193}],
            "top_member_cluster": [{"key": "其他", "count": 74}],
        }

        markdown = _anomaly_table([anomaly])
        html = _compact_anomaly_cards([anomaly])

        self.assertIn("均以该日问题量为分母", markdown)
        self.assertIn("权益无法兑换/使用（共50条，占比20.7%）", markdown)
        self.assertIn("投诉（共193条，占比79.8%）", markdown)
        self.assertIn("均以该日问题量为分母", html)
        self.assertIn("权益无法兑换/使用（共50条，占比20.7%）", html)
        self.assertIn("投诉（共193条，占比79.8%）", html)


if __name__ == "__main__":
    unittest.main()
