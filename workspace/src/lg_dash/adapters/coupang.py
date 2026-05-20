from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from lg_dash.adapters.fetcher import HtmlFetcher
from lg_dash.models import (
    Brand,
    Category,
    ProductRef,
    RawReview,
    SourceId,
    SpecPayload,
)

BASE_SEARCH = "https://www.coupang.com/np/search"
BASE_PRODUCT = "https://www.coupang.com/vp/products"

_DATE_FMTS = ("%Y-%m-%d", "%Y.%m.%d")


class CoupangAdapter:
    source_id: str = SourceId.COUPANG.value

    def __init__(self, fetcher: HtmlFetcher) -> None:
        self.fetcher = fetcher

    def search_url(self, brand: Brand, category: Category) -> str:
        keyword = brand.search_keywords.get(category.display, brand.display)
        return f"{BASE_SEARCH}?q={quote_plus(keyword)}"

    def product_url(self, product_id: str) -> str:
        return f"{BASE_PRODUCT}/{product_id}"

    def discover(self, brand: Brand, category: Category) -> list[ProductRef]:
        html = self.fetcher.fetch(self.search_url(brand, category))
        soup = BeautifulSoup(html, "lxml")
        refs: list[ProductRef] = []
        for item in soup.select("li.search-product"):
            product_id = item.get("data-product-id")
            name_el = item.select_one(".name")
            if not product_id or not name_el:
                continue
            refs.append(
                ProductRef(
                    source_id=SourceId.COUPANG,
                    brand_id=brand.id,
                    category_id=category.id,
                    external_id=str(product_id),
                    url=self.product_url(str(product_id)),
                    model_name=name_el.get_text(strip=True),
                    model_code=None,
                )
            )
        return refs

    def fetch_specs(self, ref: ProductRef) -> SpecPayload:
        html = self.fetcher.fetch(ref.url)
        soup = BeautifulSoup(html, "lxml")
        attributes: dict[str, str] = {}
        for row in soup.select("table.product-spec-table tr"):
            th = row.select_one("th")
            td = row.select_one("td")
            if th and td:
                attributes[th.get_text(strip=True)] = td.get_text(strip=True)
        return SpecPayload(
            product_ref=ref,
            attributes=attributes,
            captured_at=datetime.now(),
        )

    def fetch_reviews(
        self, ref: ProductRef, since: datetime | None = None
    ) -> Iterator[RawReview]:
        html = self.fetcher.fetch(ref.url)
        soup = BeautifulSoup(html, "lxml")
        for item in soup.select("article.review"):
            content_el = item.select_one(".review-content")
            if content_el is None:
                continue
            text = content_el.get_text(strip=True)
            if not text:
                continue
            rating = self._parse_rating(item)
            posted_at = self._parse_date(item)
            if since is not None and posted_at is not None and posted_at < since:
                continue
            yield RawReview(
                product_ref=ref,
                rating=rating,
                text=text,
                posted_at=posted_at,
            )

    @staticmethod
    def _parse_rating(item) -> float | None:
        attr = item.get("data-rating")
        if attr is None:
            rating_el = item.select_one(".rating")
            if rating_el is None:
                return None
            attr = rating_el.get_text(strip=True)
        try:
            return float(attr)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_date(item) -> datetime | None:
        date_el = item.select_one(".date")
        if date_el is None:
            return None
        raw = date_el.get_text(strip=True)
        for fmt in _DATE_FMTS:
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue
        return None
