from __future__ import annotations

import inspect
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Callable, get_type_hints

import pytest

from lg_dash.adapters.base import SourceAdapter
from lg_dash.models import (
    Brand,
    Category,
    CategoryId,
    ProductRef,
    RawReview,
    SourceId,
    SpecPayload,
)

from lg_dash.adapters.coupang import CoupangAdapter
from lg_dash.adapters.danawa import DanawaAdapter
from lg_dash.adapters.manufacturer import ManufacturerAdapter
from lg_dash.adapters.youtube import YouTubeAdapter
from tests.adapters.file_fetcher import FileFetcher
from tests.adapters.fixture_adapter import FixtureAdapter

FIXTURE_ROOT = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_brand() -> Brand:
    return Brand(
        id="lg",
        display="LG전자",
        aliases=["LG"],
        manufacturer_site="https://www.lge.co.kr",
        search_keywords={"세탁기": "LG 트롬"},
    )


@pytest.fixture
def sample_category() -> Category:
    return Category(id=CategoryId.WASHER, display="세탁기")


def _adapter_factories() -> list[pytest.param]:
    return [
        pytest.param(
            lambda: FixtureAdapter(FIXTURE_ROOT / "fixture_source"),
            id="fixture",
        ),
        pytest.param(
            lambda: DanawaAdapter(
                fetcher=FileFetcher.for_danawa(FIXTURE_ROOT / "danawa")
            ),
            id="danawa",
        ),
        pytest.param(
            lambda: ManufacturerAdapter(
                fetcher=FileFetcher.for_manufacturer(FIXTURE_ROOT / "manufacturer")
            ),
            id="manufacturer",
        ),
        pytest.param(
            lambda: CoupangAdapter(
                fetcher=FileFetcher.for_coupang(FIXTURE_ROOT / "coupang")
            ),
            id="coupang",
        ),
        pytest.param(
            lambda: YouTubeAdapter(
                fetcher=FileFetcher.for_youtube(FIXTURE_ROOT / "youtube")
            ),
            id="youtube",
        ),
    ]


class TestProtocolDefinition:
    def test_is_runtime_checkable_protocol(self) -> None:
        assert getattr(SourceAdapter, "_is_protocol", False) is True
        assert getattr(SourceAdapter, "_is_runtime_protocol", False) is True

    def test_declares_source_id_attribute(self) -> None:
        hints = get_type_hints(SourceAdapter)
        assert "source_id" in hints
        assert hints["source_id"] is str

    def test_declares_required_methods(self) -> None:
        for name in ("discover", "fetch_specs", "fetch_reviews"):
            assert hasattr(SourceAdapter, name), f"missing method: {name}"

    def test_discover_signature(self) -> None:
        sig = inspect.signature(SourceAdapter.discover)
        params = list(sig.parameters)
        assert params[:3] == ["self", "brand", "category"]

    def test_fetch_specs_signature(self) -> None:
        sig = inspect.signature(SourceAdapter.fetch_specs)
        params = list(sig.parameters)
        assert params[:2] == ["self", "ref"]

    def test_fetch_reviews_signature(self) -> None:
        sig = inspect.signature(SourceAdapter.fetch_reviews)
        params = list(sig.parameters)
        assert params[:2] == ["self", "ref"]
        assert "since" in sig.parameters


@pytest.mark.parametrize("factory", _adapter_factories())
class TestAdapterContract:
    def test_satisfies_protocol(self, factory: Callable[[], SourceAdapter]) -> None:
        adapter = factory()
        assert isinstance(adapter, SourceAdapter)

    def test_source_id_is_known(self, factory: Callable[[], SourceAdapter]) -> None:
        adapter = factory()
        assert isinstance(adapter.source_id, str)
        assert adapter.source_id in {s.value for s in SourceId}

    def test_discover_returns_list_of_product_refs(
        self,
        factory: Callable[[], SourceAdapter],
        sample_brand: Brand,
        sample_category: Category,
    ) -> None:
        adapter = factory()
        refs = adapter.discover(sample_brand, sample_category)
        assert isinstance(refs, list)
        assert len(refs) >= 1
        for ref in refs:
            assert isinstance(ref, ProductRef)
            assert ref.source_id.value == adapter.source_id
            assert ref.brand_id == sample_brand.id
            assert ref.category_id == sample_category.id

    def test_discover_is_idempotent(
        self,
        factory: Callable[[], SourceAdapter],
        sample_brand: Brand,
        sample_category: Category,
    ) -> None:
        adapter = factory()
        first = adapter.discover(sample_brand, sample_category)
        second = adapter.discover(sample_brand, sample_category)
        assert [(r.external_id, r.model_name) for r in first] == [
            (r.external_id, r.model_name) for r in second
        ]

    def test_fetch_specs_returns_spec_payload(
        self,
        factory: Callable[[], SourceAdapter],
        sample_brand: Brand,
        sample_category: Category,
    ) -> None:
        adapter = factory()
        refs = adapter.discover(sample_brand, sample_category)
        payload = adapter.fetch_specs(refs[0])
        assert isinstance(payload, SpecPayload)
        assert payload.product_ref.external_id == refs[0].external_id
        assert payload.product_ref.source_id.value == adapter.source_id
        assert isinstance(payload.attributes, dict)
        assert isinstance(payload.captured_at, datetime)

    def test_fetch_reviews_returns_iterable_of_raw_review(
        self,
        factory: Callable[[], SourceAdapter],
        sample_brand: Brand,
        sample_category: Category,
    ) -> None:
        adapter = factory()
        refs = adapter.discover(sample_brand, sample_category)
        result = adapter.fetch_reviews(refs[0])
        assert isinstance(result, Iterable)
        for review in list(result):
            assert isinstance(review, RawReview)
            assert review.product_ref.source_id.value == adapter.source_id
            assert review.text.strip() != ""

    def test_fetch_reviews_since_filter(
        self,
        factory: Callable[[], SourceAdapter],
        sample_brand: Brand,
        sample_category: Category,
    ) -> None:
        adapter = factory()
        refs = adapter.discover(sample_brand, sample_category)
        cutoff = datetime(2099, 1, 1)
        result = list(adapter.fetch_reviews(refs[0], since=cutoff))
        assert result == []
