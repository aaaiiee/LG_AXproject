from __future__ import annotations

from pathlib import Path

import pytest

from lg_dash.adapters.danawa import DanawaAdapter
from lg_dash.models import Brand, Category, CategoryId, SourceId

from tests.adapters.file_fetcher import FileFetcher

LIVE_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "danawa_live"

_EXPECTED_PCODES = {"76550339", "99477830", "19550933", "106702373", "98778002"}


@pytest.fixture
def lg_brand() -> Brand:
    return Brand(
        id="lg",
        display="LG전자",
        aliases=["LG"],
        manufacturer_site="https://www.lge.co.kr",
        search_keywords={"세탁기": "LG 트롬"},
    )


@pytest.fixture
def washer() -> Category:
    return Category(id=CategoryId.WASHER, display="세탁기")


@pytest.fixture
def adapter() -> DanawaAdapter:
    return DanawaAdapter(fetcher=FileFetcher.for_danawa_live(LIVE_FIXTURE_DIR))


class TestRealDanawaShape:
    def test_discover_extracts_pcode_from_li_id(
        self, adapter: DanawaAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        refs = adapter.discover(lg_brand, washer)
        assert len(refs) == 5
        found = {r.external_id for r in refs}
        assert found == _EXPECTED_PCODES

    def test_discover_extracts_model_name_from_prod_name_anchor(
        self, adapter: DanawaAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        refs = adapter.discover(lg_brand, washer)
        names = [r.model_name for r in refs]
        assert any("FH25ES" in n for n in names)
        assert any("FX25EF" in n for n in names)
        assert any("RH18WTSN" in n for n in names)
        for n in names:
            assert n.strip() != ""

    def test_discover_extracts_model_code_from_name(
        self, adapter: DanawaAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        refs = adapter.discover(lg_brand, washer)
        codes = {r.model_code for r in refs}
        assert "FH25ES" in codes
        assert "FX25EF" in codes
        assert "RH18WTSN" in codes

    def test_discover_ref_url_matches_pcode(
        self, adapter: DanawaAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        refs = adapter.discover(lg_brand, washer)
        for ref in refs:
            assert f"pcode={ref.external_id}" in ref.url
            assert ref.source_id == SourceId.DANAWA


def _target_ref(adapter: DanawaAdapter, lg_brand: Brand, washer: Category):
    refs = adapter.discover(lg_brand, washer)
    return next(r for r in refs if r.external_id == "76550339")


class TestRealDanawaProductSpecs:
    def test_fetch_specs_extracts_wash_capacity(
        self, adapter: DanawaAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        target = _target_ref(adapter, lg_brand, washer)
        attrs = adapter.fetch_specs(target).attributes
        wash = next(
            (v for k, v in attrs.items() if "세탁" in k and "건조" not in k),
            None,
        )
        assert wash is not None
        assert "25" in wash and "kg" in wash.lower()

    def test_fetch_specs_extracts_dry_capacity(
        self, adapter: DanawaAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        target = _target_ref(adapter, lg_brand, washer)
        attrs = adapter.fetch_specs(target).attributes
        dry = next((v for k, v in attrs.items() if "건조" in k), None)
        assert dry is not None
        assert "15" in dry and "kg" in dry.lower()

    def test_fetch_specs_extracts_energy_grade(
        self, adapter: DanawaAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        target = _target_ref(adapter, lg_brand, washer)
        attrs = adapter.fetch_specs(target).attributes
        energy = next((v for k, v in attrs.items() if "에너지" in k), None)
        assert energy is not None
        assert "1등급" in energy

    def test_fetch_specs_detects_steam(
        self, adapter: DanawaAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        target = _target_ref(adapter, lg_brand, washer)
        attrs = adapter.fetch_specs(target).attributes
        assert any(
            "스팀" in k or "스팀" in (v or "")
            for k, v in attrs.items()
        )

    def test_fetch_specs_detects_smart_remote(
        self, adapter: DanawaAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        target = _target_ref(adapter, lg_brand, washer)
        attrs = adapter.fetch_specs(target).attributes
        keywords = {"WiFi", "와이파이", "ThinQ", "씽큐", "원격제어", "스마트"}
        assert any(
            any(kw in k or kw in (v or "") for kw in keywords)
            for k, v in attrs.items()
        )

    def test_fetch_specs_extracts_dimensions(
        self, adapter: DanawaAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        target = _target_ref(adapter, lg_brand, washer)
        attrs = adapter.fetch_specs(target).attributes
        dims = next(
            (v for k, v in attrs.items() if "크기" in k or "치수" in k),
            None,
        )
        assert dims is not None
        assert "700" in dims and "990" in dims and "830" in dims
