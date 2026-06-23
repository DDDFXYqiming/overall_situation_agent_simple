from __future__ import annotations

import unittest
from types import SimpleNamespace

from overall_situation_agent.evidence import _build_evidence_from_buckets


class FakeElasticsearch:
    def __init__(self) -> None:
        self.msearch_calls: list[tuple[str, list[dict]]] = []
        self.search_calls: list[tuple[str, dict]] = []

    def msearch(self, index: str, bodies: list[dict]):
        self.msearch_calls.append((index, bodies))
        responses = []
        for body in bodies:
            term_filter = next(
                item["term"]
                for item in body["query"]["bool"]["filter"]
                if "term" in item and "tertiary_labels" in item["term"]
            )
            label = term_filter["tertiary_labels"]
            responses.append(SimpleNamespace(body={
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "content": f"{label} 用户要求处理",
                                "cs_reply": "客服已记录",
                                "customer_key_appeal": "要求退费",
                                "customer_keywords": "退费",
                                "cs_key_action": "解释规则",
                                "cs_keywords": "规则",
                                "service_time": "2026-03-01",
                                "scene_emotion": "负向",
                            }
                        }
                    ]
                },
                "aggregations": {
                    "appeal_agg": {"buckets": [{"key": "要求退费", "doc_count": 3}]},
                    "cs_action_agg": {"buckets": [{"key": "解释规则", "doc_count": 2}]},
                },
            }))
        return responses

    def search(self, index: str, body: dict):
        self.search_calls.append((index, body))
        raise AssertionError("sample collection should use msearch when available")


class EvidenceTests(unittest.TestCase):
    def test_evidence_sampling_uses_single_msearch_and_keeps_bucket_order(self) -> None:
        es = FakeElasticsearch()
        result = _build_evidence_from_buckets(
            es=es,  # type: ignore[arg-type]
            index_name="tickets",
            total_hits=100,
            buckets=[
                {"key": "退订困难/自动续费争议", "doc_count": 10},
                {"key": "奖励/优惠未到账", "doc_count": 8},
            ],
            start_date="2026-03-01",
            end_date="2026-03-31",
            all_tertiary_total=18,
        )

        self.assertEqual(len(es.msearch_calls), 1)
        self.assertEqual(es.msearch_calls[0][0], "tickets")
        self.assertEqual(len(es.msearch_calls[0][1]), 2)
        self.assertEqual(es.search_calls, [])
        self.assertEqual([item["key"] for item in result["labels"]], ["退订困难/自动续费争议", "奖励/优惠未到账"])
        self.assertEqual(result["labels"][0]["samples"][0]["customer_key_appeal"], "要求退费")


if __name__ == "__main__":
    unittest.main()
