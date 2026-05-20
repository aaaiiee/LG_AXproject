from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from lg_dash.adapters.coupang import CoupangAdapter
from lg_dash.models import Brand, Category, CategoryId, SourceId

from tests.adapters.file_fetcher import FileFetcher

COUPANG_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "coupang"


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
def adapter() -> CoupangAdapter:
    return CoupangAdapter(fetcher=FileFetcher.for_coupang(COUPANG_FIXTURE_DIR))


class TestUrlBuilders:
    def test_search_url_uses_brand_search_keyword(
        self, adapter: CoupangAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        url = adapter.search_url(lg_brand, washer)
        assert url.startswith("https://www.coupang.com/np/search")
        assert "q=" in url

    def test_product_url_uses_product_id(self, adapter: CoupangAdapter) -> None:
        assert (
            adapter.product_url("2000001")
            == "https://www.coupang.com/vp/products/2000001"
        )


class TestDiscover:
    def test_discover_parses_search_results(
        self, adapter: CoupangAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        refs = adapter.discover(lg_brand, washer)
        assert len(refs) == 2
        first = refs[0]
        assert first.source_id == SourceId.COUPANG
        assert first.brand_id == "lg"
        assert first.category_id == CategoryId.WASHER
        assert first.external_id.isdigit()
        assert first.url.startswith("https://www.coupang.com/vp/products/")


class TestFetchSpecs:
    def test_specs_extracted(
        self, adapter: CoupangAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        refs = adapter.discover(lg_brand, washer)
        payload = adapter.fetch_specs(refs[0])
        assert isinstance(payload, type(payload))
        assert payload.attributes.get("세탁용량") == "24kg"
        assert isinstance(payload.captured_at, datetime)


class TestFetchReviews:
    def test_reviews_with_rating_and_text(
        self, adapter: CoupangAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        refs = adapter.discover(lg_brand, washer)
        reviews = list(adapter.fetch_reviews(refs[0]))
        assert len(reviews) >= 2
        assert all(r.text.strip() for r in reviews)
        ratings = [r.rating for r in reviews if r.rating is not None]
        assert all(0 <= r <= 5 for r in ratings)

    def test_since_filter_drops_older_reviews(
        self, adapter: CoupangAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        refs = adapter.discover(lg_brand, washer)
        cutoff = datetime(2026, 5, 10)
        recent = list(adapter.fetch_reviews(refs[0], since=cutoff))
        for r in recent:
            assert r.posted_at is None or r.posted_at >= cutoff
