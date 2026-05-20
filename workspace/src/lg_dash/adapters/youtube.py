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

BASE_SEARCH = "https://www.youtube.com/results"
BASE_VIDEO = "https://www.youtube.com/watch"

_DATE_FMTS = ("%Y-%m-%d", "%Y.%m.%d")


class YouTubeAdapter:
    source_id: str = SourceId.YOUTUBE.value

    def __init__(self, fetcher: HtmlFetcher) -> None:
        self.fetcher = fetcher

    def search_url(self, brand: Brand, category: Category) -> str:
        keyword = brand.search_keywords.get(category.display, brand.display)
        return f"{BASE_SEARCH}?search_query={quote_plus(keyword)}"

    def video_url(self, video_id: str) -> str:
        return f"{BASE_VIDEO}?v={video_id}"

    def discover(self, brand: Brand, category: Category) -> list[ProductRef]:
        html = self.fetcher.fetch(self.search_url(brand, category))
        soup = BeautifulSoup(html, "lxml")
        refs: list[ProductRef] = []
        for item in soup.select("div.video"):
            video_id = item.get("data-id")
            title_el = item.select_one(".title")
            if not video_id or not title_el:
                continue
            refs.append(
                ProductRef(
                    source_id=SourceId.YOUTUBE,
                    brand_id=brand.id,
                    category_id=category.id,
                    external_id=str(video_id),
                    url=self.video_url(str(video_id)),
                    model_name=title_el.get_text(strip=True),
                    model_code=None,
                )
            )
        return refs

    def fetch_specs(self, ref: ProductRef) -> SpecPayload:
        return SpecPayload(
            product_ref=ref,
            attributes={},
            captured_at=datetime.now(),
        )

    def fetch_reviews(
        self, ref: ProductRef, since: datetime | None = None
    ) -> Iterator[RawReview]:
        html = self.fetcher.fetch(ref.url)
        soup = BeautifulSoup(html, "lxml")
        for item in soup.select(".comment"):
            text_el = item.select_one(".text")
            if text_el is None:
                continue
            text = text_el.get_text(strip=True)
            if not text:
                continue
            posted_at = self._parse_date(item)
            if since is not None and posted_at is not None and posted_at < since:
                continue
            author_el = item.select_one(".author")
            author = author_el.get_text(strip=True) if author_el else None
            yield RawReview(
                product_ref=ref,
                author_hash=author,
                rating=None,
                text=text,
                posted_at=posted_at,
            )

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
