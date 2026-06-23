from __future__ import annotations

import json
import unittest

from overall_situation_agent.llm_client import LLMResponse
from overall_situation_agent.narrative_builder import (
    _build_executive_summary,
    _build_tertiary_cause_detail_llm,
    _build_trend_voice_summary_fallback,
)


class FakeLLM:
    enabled = True
    report_enabled = True
    report_timeout = 60
    report_max_tokens = 4000

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    def chat(self, messages, **kwargs):
        self.prompts.append(messages[-1]["content"])
        if not self.responses:
            raise AssertionError("unexpected extra LLM call")
        return LLMResponse(content=self.responses.pop(0), used_fallback=False)


def _response(user_voice: str) -> str:
    return json.dumps(
        {
            "content_summary": "用户集中反映退订入口、续费提醒和退费规则解释不清，咨询时希望尽快获得明确处理结果。",
            "cs_reply_summary": "客服主要围绕规则解释、操作引导和诉求记录进行回应，处理口径偏流程说明。",
            "root_cause": "根因在于会员续费提醒和退订路径说明不足，用户对后续处理预期不稳定。",
            "user_voice_natural": user_voice,
        },
        ensure_ascii=False,
    )


def _evidence() -> list[dict]:
    return [
        {
            "key": "退订困难/自动续费争议",
            "count": 10,
            "share": 1.0,
            "samples": [
                {
                    "content_excerpt": "用户咨询会员退订和退费规则。",
                    "cs_reply_excerpt": "客服解释会员规则并记录诉求。",
                }
            ],
            "appeal_agg": [{"key": "退订退费", "count": 10}],
            "cs_action_agg": [{"key": "解释规则", "count": 10}],
        }
    ]


class NarrativeBuilderTests(unittest.TestCase):
    def test_user_voice_in_range_is_accepted_without_retry(self) -> None:
        voice = "诉" * 120
        llm = FakeLLM([_response(voice)])

        details = _build_tertiary_cause_detail_llm(_evidence(), llm)  # type: ignore[arg-type]

        self.assertEqual(len(llm.prompts), 1)
        self.assertEqual(details[0]["user_voice_natural"], voice)

    def test_user_voice_out_of_range_retries_then_accepts_valid_result(self) -> None:
        short_voice = "短" * 80
        valid_voice = "诉" * 120
        llm = FakeLLM([_response(short_voice), _response(valid_voice)])

        details = _build_tertiary_cause_detail_llm(_evidence(), llm)  # type: ignore[arg-type]

        self.assertEqual(len(llm.prompts), 2)
        self.assertIn("100-150字", llm.prompts[1])
        self.assertEqual(details[0]["user_voice_natural"], valid_voice)

    def test_user_voice_still_out_of_range_after_retry_is_kept_complete(self) -> None:
        short_voice = "短" * 80
        long_voice = "长" * 170
        llm = FakeLLM([_response(short_voice), _response(long_voice)])

        details = _build_tertiary_cause_detail_llm(_evidence(), llm)  # type: ignore[arg-type]

        self.assertEqual(len(llm.prompts), 2)
        self.assertEqual(details[0]["user_voice_natural"], long_voice)

    def test_trend_voice_summary_uses_highest_count_matchday(self) -> None:
        summary = _build_trend_voice_summary_fallback([
            {"date": "2026-03-06", "count": 126, "top_tertiary": [{"key": "退订困难/自动续费争议"}]},
            {"date": "2026-03-07", "count": 304, "top_tertiary": [{"key": "权益无法兑换/使用"}]},
            {"date": "2026-03-14", "count": 242, "top_tertiary": [{"key": "直播无法回看"}]},
        ])

        self.assertIn("2026-03-07", summary[0])
        self.assertNotIn("2026-03-06 的投诉最集中", summary[0])

    def test_executive_summary_retries_and_sanitizes_retention_friction_advice(self) -> None:
        banned = "二、三大痛点\n退订流程不畅。\n\n四、行动建议\n增加退订操作的二次确认弹窗，并通过短信告知用户。"
        llm = FakeLLM([banned, banned])
        result = {
            "total_with_unlabeled": 10,
            "total": 10,
            "period": {"min": "2026-03-01", "max": "2026-03-31"},
            "service_type": [{"key": "投诉", "count": 10}],
            "primary": [{"key": "业务体验", "count": 10}],
            "tertiary": [{"key": "退订困难/自动续费争议", "count": 10}],
            "schedule": {},
            "daily": [],
            "province": [],
        }

        summary = _build_executive_summary(result, llm)  # type: ignore[arg-type]

        self.assertEqual(len(llm.prompts), 2)
        self.assertNotIn("退订操作的二次确认弹窗", summary)
        self.assertIn("自动扣费前增加确认提示", summary)


if __name__ == "__main__":
    unittest.main()
