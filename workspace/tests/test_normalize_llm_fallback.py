from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from lg_dash.llm.client import LlmResponse
from lg_dash.models import CategoryId, MatchedBy, ProductRef, SourceId, SpecPayload
from lg_dash.pipeline.normalize import Normalizer, load_attr_dictionary

CONFIG_DIR = Path(__file__).parent.parent / "config"


class MockLlmClient:
    model: str = "mock-haiku"

    def __init__(self, responses: list[str] | str) -> None:
        if isinstance(responses, str):
            responses = [responses]
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete(self, *, system: str, user: str) -> LlmResponse:
        self.calls.append((system, user))
        if not self._responses:
            raise RuntimeError("no mock responses left")
        return LlmResponse(
            text=self._responses.pop(0),
            input_tokens=500,
            output_tokens=80,
            latency_ms=50,
            cache_hit=False,
        )


@pytest.fixture(scope="module")
def attr_defs():
    return load_attr_dictionary(CONFIG_DIR / "attr_dictionary.yaml")


def _payload(attrs: dict[str, str]) -> SpecPayload:
    return SpecPayload(
        product_ref=ProductRef(
            source_id=SourceId.DANAWA,
            brand_id="lg",
            category_id=CategoryId.WASHER,
            external_id="00000000",
            url="https://example.test",
            model_name="TestModel",
        ),
        attributes=attrs,
        captured_at=datetime(2026, 5, 20),
    )


class TestLlmFallbackMatching:
    def test_unmatched_label_resolved_to_canonical_key(self, attr_defs) -> None:
        client = MockLlmClient(json.dumps({"세탁능력": "wash_capacity_kg"}))
        normalizer = Normalizer(attr_defs=attr_defs, llm_client=client)
        facts = normalizer.normalize(
            _payload({"세탁능력": "24kg"}), CategoryId.WASHER
        )
        fact = next(
            (f for f in facts if f.canonical_key == "wash_capacity_kg"), None
        )
        assert fact is not None
        assert fact.value_num == 24.0
        assert fact.matched_by == MatchedBy.LLM
        assert 0.5 <= fact.confidence < 1.0

    def test_no_llm_client_means_no_fallback(self, attr_defs) -> None:
        normalizer = Normalizer(attr_defs=attr_defs)
        facts = normalizer.normalize(
            _payload({"세탁능력": "24kg"}), CategoryId.WASHER
        )
        assert not any(f.matched_by == MatchedBy.LLM for f in facts)

    def test_llm_returns_null_yields_no_fact(self, attr_defs) -> None:
        client = MockLlmClient(json.dumps({"전혀모르는라벨": None}))
        normalizer = Normalizer(attr_defs=attr_defs, llm_client=client)
        facts = normalizer.normalize(
            _payload({"전혀모르는라벨": "값123"}), CategoryId.WASHER
        )
        assert not any(f.source_attr_label == "전혀모르는라벨" for f in facts)

    def test_rule_matched_labels_skip_llm(self, attr_defs) -> None:
        client = MockLlmClient(json.dumps({}))
        normalizer = Normalizer(attr_defs=attr_defs, llm_client=client)
        normalizer.normalize(
            _payload({"세탁용량": "24kg", "탈수속도": "1400 RPM"}),
            CategoryId.WASHER,
        )
        assert len(client.calls) == 0

    def test_llm_called_only_once_for_batch_of_unmatched(self, attr_defs) -> None:
        client = MockLlmClient(
            json.dumps({"라벨A": "wash_capacity_kg", "라벨B": "spin_rpm"})
        )
        normalizer = Normalizer(attr_defs=attr_defs, llm_client=client)
        normalizer.normalize(
            _payload({"라벨A": "24kg", "라벨B": "1400 RPM"}),
            CategoryId.WASHER,
        )
        assert len(client.calls) == 1
