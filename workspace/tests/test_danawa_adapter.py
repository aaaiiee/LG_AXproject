from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from lg_dash.adapters.danawa import DanawaAdapter
from lg_dash.adapters.fetcher import HtmlFetcher
from lg_dash.models import Brand, Category, CategoryId, ProductRef, SourceId

from tests.adapters.file_fetcher import FileFetcher

DANAWA_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "danawa"


@pytest.fixture
def lg_brand() -> Brand:
    return Brand(
        id="lg",
        display="LG전자",
        aliases=["LG"],
        manufacturer_site="https://www.lge.co.kr",
        search_keywords={
            "세탁기": "LG 트롬",
            "건조기": "LG 트롬 건조기",
            "통돌이": "LG 통돌이 세탁기",
        },
    )


@pytest.fixture
def washer() -> Category:
    return Category(id=CategoryId.WASHER, display="세탁기")


@pytest.fixture
def fetcher() -> HtmlFetcher:
    return FileFetcher.for_danawa(DANAWA_FIXTURE_DIR)


@pytest.fixture
def adapter(fetcher: HtmlFetcher) -> DanawaAdapter:
    return DanawaAdapter(fetcher=fetcher)


class TestUrlBuilders:
    def test_search_url_uses_brand_search_keyword(
        self, adapter: DanawaAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        url = adapter.search_url(lg_brand, washer)
        assert url.startswith("https://search.danawa.com/dsearch.php")
        assert "query=" in url
        assert "LG" in url or "%4C%47" in url or "LG+%ED%8A%B8%EB%A1%AC" in url or "트롬" in url

    def test_product_url_uses_pcode(self, adapter: DanawaAdapter) -> None:
        url = adapter.product_url("12345678")
        assert url == "https://prod.danawa.com/info/?pcode=12345678"


class TestDiscover:
    def test_discover_parses_search_results(
        self, adapter: DanawaAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        refs = adapter.discover(lg_brand, washer)
        assert len(refs) == 3
        first = refs[0]
        assert first.source_id == SourceId.DANAWA
        assert first.brand_id == "lg"
        assert first.category_id == CategoryId.WASHER
        assert first.external_id.isdigit()
        assert first.url.startswith("https://prod.danawa.com/info/?pcode=")
        assert first.model_name.strip() != ""

    def test_discover_extracts_model_name_and_code(
        self, adapter: DanawaAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        refs = adapter.discover(lg_brand, washer)
        model_names = [r.model_name for r in refs]
        assert any("워시콤보" in m for m in model_names)
        assert any("트롬" in m for m in model_names)


class TestFetchSpecs:
    def test_fetch_specs_extracts_attributes_dict(
        self, adapter: DanawaAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        refs = adapter.discover(lg_brand, washer)
        target = next(r for r in refs if r.external_id == "12345678")
        payload = adapter.fetch_specs(target)
        attrs = payload.attributes
        assert attrs["세탁용량"] == "24kg"
        assert attrs["탈수속도"] == "1400 RPM"
        assert attrs["에너지소비효율등급"] == "1등급"
        assert isinstance(payload.captured_at, datetime)


class TestFetchReviews:
    def test_fetch_reviews_extracts_text_and_rating(
        self, adapter: DanawaAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        refs = adapter.discover(lg_brand, washer)
        target = next(r for r in refs if r.external_id == "12345678")
        reviews = list(adapter.fetch_reviews(target))
        assert len(reviews) >= 2
        ratings = [r.rating for r in reviews if r.rating is not None]
        assert all(0 <= r <= 5 for r in ratings)
        texts = [r.text for r in reviews]
        assert any("세척력" in t for t in texts)

    def test_fetch_reviews_posted_at_parsed(
        self, adapter: DanawaAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        refs = adapter.discover(lg_brand, washer)
        target = next(r for r in refs if r.external_id == "12345678")
        reviews = list(adapter.fetch_reviews(target))
        with_dates = [r for r in reviews if r.posted_at is not None]
        assert len(with_dates) >= 1
        assert all(isinstance(r.posted_at, datetime) for r in with_dates)

    def test_fetch_reviews_since_filter_excludes_older(
        self, adapter: DanawaAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        refs = adapter.discover(lg_brand, washer)
        target = next(r for r in refs if r.external_id == "12345678")
        cutoff = datetime(2026, 5, 10)
        recent = list(adapter.fetch_reviews(target, since=cutoff))
        assert all(
            r.posted_at is None or r.posted_at >= cutoff for r in recent
        )
