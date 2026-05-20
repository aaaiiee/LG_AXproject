from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from lg_dash.adapters.youtube import YouTubeAdapter
from lg_dash.models import Brand, Category, CategoryId, SourceId

from tests.adapters.file_fetcher import FileFetcher

YOUTUBE_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "youtube"


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
def adapter() -> YouTubeAdapter:
    return YouTubeAdapter(fetcher=FileFetcher.for_youtube(YOUTUBE_FIXTURE_DIR))


class TestUrlBuilders:
    def test_search_url_uses_brand_keyword(
        self, adapter: YouTubeAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        url = adapter.search_url(lg_brand, washer)
        assert url.startswith("https://www.youtube.com/results")
        assert "search_query=" in url

    def test_video_url_uses_video_id(self, adapter: YouTubeAdapter) -> None:
        assert (
            adapter.video_url("abc12345xyz")
            == "https://www.youtube.com/watch?v=abc12345xyz"
        )


class TestDiscover:
    def test_discover_returns_video_refs(
        self, adapter: YouTubeAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        refs = adapter.discover(lg_brand, washer)
        assert len(refs) == 2
        first = refs[0]
        assert first.source_id == SourceId.YOUTUBE
        assert first.brand_id == "lg"
        assert first.category_id == CategoryId.WASHER
        assert first.url.startswith("https://www.youtube.com/watch?v=")
        assert "트롬" in first.model_name or "LG" in first.model_name


class TestFetchSpecs:
    def test_returns_empty_attributes(
        self, adapter: YouTubeAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        refs = adapter.discover(lg_brand, washer)
        payload = adapter.fetch_specs(refs[0])
        assert payload.attributes == {}
        assert isinstance(payload.captured_at, datetime)
        assert payload.product_ref.source_id == SourceId.YOUTUBE


class TestFetchReviews:
    def test_returns_comments_as_reviews(
        self, adapter: YouTubeAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        refs = adapter.discover(lg_brand, washer)
        reviews = list(adapter.fetch_reviews(refs[0]))
        assert len(reviews) >= 2
        for r in reviews:
            assert r.text.strip() != ""
            assert r.product_ref.source_id == SourceId.YOUTUBE
            assert r.rating is None

    def test_since_filter_drops_older_comments(
        self, adapter: YouTubeAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        refs = adapter.discover(lg_brand, washer)
        cutoff = datetime(2026, 5, 5)
        recent = list(adapter.fetch_reviews(refs[0], since=cutoff))
        for r in recent:
            assert r.posted_at is None or r.posted_at >= cutoff
