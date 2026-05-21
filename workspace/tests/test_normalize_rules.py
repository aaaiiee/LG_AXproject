from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from lg_dash.models import (
    CategoryId,
    MatchedBy,
    ProductRef,
    SourceId,
    SpecPayload,
)
from lg_dash.pipeline.normalize import (
    NormalizedFact,
    Normalizer,
    load_attr_dictionary,
)

CONFIG_DIR = Path(__file__).parent.parent / "config"


@pytest.fixture(scope="module")
def normalizer() -> Normalizer:
    defs = load_attr_dictionary(CONFIG_DIR / "attr_dictionary.yaml")
    return Normalizer(defs)


def _payload(attrs: dict[str, str]) -> SpecPayload:
    ref = ProductRef(
        source_id=SourceId.DANAWA,
        brand_id="lg",
        category_id=CategoryId.WASHER,
        external_id="00000000",
        url="https://prod.danawa.com/info/?pcode=00000000",
        model_name="TestModel",
        model_code=None,
    )
    return SpecPayload(
        product_ref=ref,
        attributes=attrs,
        captured_at=datetime(2026, 5, 20, 10, 0),
    )


def _find(facts: list[NormalizedFact], key: str) -> NormalizedFact | None:
    for f in facts:
        if f.canonical_key == key:
            return f
    return None


class TestRuleMatching:
    @pytest.mark.parametrize(
        "label,raw,expected_key,expected_num,expected_unit",
        [
            ("세탁용량", "24kg", "wash_capacity_kg", 24.0, "kg"),
            ("1회 세탁량", "25 KG", "wash_capacity_kg", 25.0, "kg"),
            ("세탁 용량", "21.5kg", "wash_capacity_kg", 21.5, "kg"),
            ("탈수속도", "1400 RPM", "spin_rpm", 1400.0, "rpm"),
            ("회전수", "1200rpm", "spin_rpm", 1200.0, "rpm"),
            ("소음", "48 dB", "noise_db", 48.0, "dB"),
            ("작동소음", "50dB", "noise_db", 50.0, "dB"),
            ("에너지소비효율등급", "1등급", "energy_grade", 1.0, "class"),
            ("에너지등급", "2등급", "energy_grade", 2.0, "class"),
            ("에너지", "1등급", "energy_grade", 1.0, "class"),
            ("소비전력", "2,200W", "power_consumption_w", 2200.0, "W"),
            ("가격", "1,290,000원", "price_krw", 1290000.0, "krw"),
            ("출시가", "1,100,000원", "price_krw", 1100000.0, "krw"),
        ],
    )
    def test_extracts_number_value_via_regex(
        self,
        normalizer: Normalizer,
        label: str,
        raw: str,
        expected_key: str,
        expected_num: float,
        expected_unit: str,
    ) -> None:
        facts = normalizer.normalize(_payload({label: raw}), CategoryId.WASHER)
        fact = _find(facts, expected_key)
        assert fact is not None, f"no fact for {expected_key}"
        assert fact.value_num == pytest.approx(expected_num)
        assert fact.unit == expected_unit
        assert fact.matched_by == MatchedBy.RULE
        assert fact.confidence == pytest.approx(1.0)
        assert fact.source_attr_label == label

    def test_dimensions_kept_as_text(self, normalizer: Normalizer) -> None:
        facts = normalizer.normalize(
            _payload({"외형치수": "600 x 850 x 600 mm"}), CategoryId.WASHER
        )
        fact = _find(facts, "dimensions_whd_mm")
        assert fact is not None
        assert fact.value_text == "600 x 850 x 600 mm"
        assert fact.unit == "mm"
        assert fact.matched_by == MatchedBy.RULE

    @pytest.mark.parametrize(
        "label,raw,expected_key",
        [
            ("스팀", "트루스팀", "steam"),
            ("스팀", "살균스팀", "steam"),
            ("WiFi", "ThinQ", "wifi_smart"),
            ("와이파이", "지원", "wifi_smart"),
        ],
    )
    def test_bool_attribute_set_to_true_when_label_matches(
        self,
        normalizer: Normalizer,
        label: str,
        raw: str,
        expected_key: str,
    ) -> None:
        facts = normalizer.normalize(_payload({label: raw}), CategoryId.WASHER)
        fact = _find(facts, expected_key)
        assert fact is not None
        assert fact.value_num == 1.0
        assert fact.value_text == raw
        assert fact.unit == "bool"
        assert fact.matched_by == MatchedBy.RULE


class TestFuzzyMatching:
    def test_label_with_extra_whitespace_matches_via_fuzzy(
        self, normalizer: Normalizer
    ) -> None:
        facts = normalizer.normalize(
            _payload({"에너지 등급": "1등급"}), CategoryId.WASHER
        )
        fact = _find(facts, "energy_grade")
        assert fact is not None
        assert fact.matched_by in {MatchedBy.RULE, MatchedBy.FUZZY}
        if fact.matched_by == MatchedBy.FUZZY:
            assert 0.7 <= fact.confidence < 1.0

    def test_unknown_label_far_from_any_synonym_is_skipped(
        self, normalizer: Normalizer
    ) -> None:
        facts = normalizer.normalize(
            _payload({"완전무관한속성이름": "값"}), CategoryId.WASHER
        )
        assert all(f.source_attr_label != "완전무관한속성이름" for f in facts)


class TestCategoryFiltering:
    def test_dry_capacity_excluded_for_washer(self, normalizer: Normalizer) -> None:
        facts = normalizer.normalize(
            _payload({"건조용량": "12kg"}), CategoryId.WASHER
        )
        assert _find(facts, "dry_capacity_kg") is None

    def test_dry_capacity_included_for_dryer(self, normalizer: Normalizer) -> None:
        facts = normalizer.normalize(
            _payload({"건조용량": "12kg"}), CategoryId.DRYER
        )
        fact = _find(facts, "dry_capacity_kg")
        assert fact is not None
        assert fact.value_num == 12.0

    def test_spin_rpm_excluded_for_dryer(self, normalizer: Normalizer) -> None:
        facts = normalizer.normalize(
            _payload({"탈수속도": "1400 RPM"}), CategoryId.DRYER
        )
        assert _find(facts, "spin_rpm") is None

    def test_short_label_건조_matches_dry_capacity_for_dryer(
        self, normalizer: Normalizer
    ) -> None:
        facts = normalizer.normalize(_payload({"건조": "18kg"}), CategoryId.DRYER)
        fact = _find(facts, "dry_capacity_kg")
        assert fact is not None
        assert fact.value_num == 18.0
        assert fact.matched_by == MatchedBy.RULE


class TestBatchNormalization:
    def test_full_danawa_spec_payload_yields_high_confidence_majority(
        self, normalizer: Normalizer
    ) -> None:
        attrs = {
            "세탁용량": "24kg",
            "탈수속도": "1400 RPM",
            "에너지소비효율등급": "1등급",
            "소비전력": "2,200W",
            "소음": "48 dB",
            "외형치수": "600 x 850 x 600 mm",
            "스팀": "트루스팀",
            "WiFi": "ThinQ",
            "가격": "1,290,000원",
        }
        facts = normalizer.normalize(_payload(attrs), CategoryId.WASHER)
        assert len(facts) >= 8
        high_conf = [f for f in facts if f.confidence >= 0.7]
        ratio = len(high_conf) / len(facts)
        assert ratio >= 0.8
