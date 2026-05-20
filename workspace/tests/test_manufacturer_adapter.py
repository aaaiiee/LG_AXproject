from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from lg_dash.adapters.manufacturer import ManufacturerAdapter
from lg_dash.models import Brand, Category, CategoryId, SourceId

from tests.adapters.file_fetcher import FileFetcher

MANUFACTURER_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "manufacturer"


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
def samsung_brand() -> Brand:
    return Brand(
        id="samsung",
        display="삼성전자",
        aliases=["Samsung"],
        manufacturer_site="https://www.samsung.com/sec",
        search_keywords={"세탁기": "삼성 그랑데"},
    )


@pytest.fixture
def winia_brand() -> Brand:
    return Brand(
        id="winia",
        display="위니아",
        aliases=["WINIA"],
        manufacturer_site="https://www.winia.com",
        search_keywords={"세탁기": "위니아 드럼세탁기"},
    )


@pytest.fixture
def washer() -> Category:
    return Category(id=CategoryId.WASHER, display="세탁기")


@pytest.fixture
def adapter() -> ManufacturerAdapter:
    return ManufacturerAdapter(
        fetcher=FileFetcher.for_manufacturer(MANUFACTURER_FIXTURE_DIR)
    )


class TestCatalogUrl:
    def test_lg_catalog_url_uses_brand_site(
        self, adapter: ManufacturerAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        url = adapter.catalog_url(lg_brand, washer)
        assert url.startswith(lg_brand.manufacturer_site)
        assert "washing" in url or "washer" in url or "세탁" in url

    def test_each_brand_yields_distinct_catalog_urls(
        self,
        adapter: ManufacturerAdapter,
        lg_brand: Brand,
        samsung_brand: Brand,
        winia_brand: Brand,
        washer: Category,
    ) -> None:
        urls = {
            adapter.catalog_url(lg_brand, washer),
            adapter.catalog_url(samsung_brand, washer),
            adapter.catalog_url(winia_brand, washer),
        }
        assert len(urls) == 3


class TestDiscover:
    def test_lg_discover_returns_products(
        self, adapter: ManufacturerAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        refs = adapter.discover(lg_brand, washer)
        assert len(refs) == 3
        for ref in refs:
            assert ref.source_id == SourceId.MANUFACTURER
            assert ref.brand_id == "lg"
            assert ref.category_id == CategoryId.WASHER
            assert ref.url.startswith(lg_brand.manufacturer_site)
            assert ref.model_code is not None and ref.model_code.startswith("WT-LGA-")

    def test_samsung_discover_uses_samsung_fixture(
        self, adapter: ManufacturerAdapter, samsung_brand: Brand, washer: Category
    ) -> None:
        refs = adapter.discover(samsung_brand, washer)
        assert len(refs) >= 1
        assert all(r.brand_id == "samsung" for r in refs)
        assert all("samsung" in r.url for r in refs)

    def test_winia_discover_uses_winia_fixture(
        self, adapter: ManufacturerAdapter, winia_brand: Brand, washer: Category
    ) -> None:
        refs = adapter.discover(winia_brand, washer)
        assert len(refs) >= 1
        assert all(r.brand_id == "winia" for r in refs)
        assert all("winia" in r.url for r in refs)


class TestFetchSpecs:
    def test_extracts_spec_grid_attributes(
        self, adapter: ManufacturerAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        refs = adapter.discover(lg_brand, washer)
        target = refs[0]
        payload = adapter.fetch_specs(target)
        attrs = payload.attributes
        assert attrs["세탁용량"] == "24kg"
        assert attrs["탈수속도"] == "1400 RPM"
        assert isinstance(payload.captured_at, datetime)
        assert payload.product_ref.external_id == target.external_id


class TestFetchReviews:
    def test_manufacturer_reviews_are_empty(
        self, adapter: ManufacturerAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        refs = adapter.discover(lg_brand, washer)
        result = list(adapter.fetch_reviews(refs[0]))
        assert result == []


class TestImageExtraction:
    def test_fetch_specs_includes_image_urls(
        self, adapter: ManufacturerAdapter, lg_brand: Brand, washer: Category
    ) -> None:
        refs = adapter.discover(lg_brand, washer)
        payload = adapter.fetch_specs(refs[0])
        assert len(payload.image_urls) >= 1
        for url in payload.image_urls:
            assert url.startswith("http") or url.startswith("/")
