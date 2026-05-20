from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

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

_CATALOG_PATHS: dict[str, dict[str, str]] = {
    "lg": {
        "washer": "/washing-machines",
        "dryer": "/dryers",
        "top_loader": "/top-load-washing-machines",
    },
    "samsung": {
        "washer": "/washers-and-dryers/washers",
        "dryer": "/washers-and-dryers/dryers",
        "top_loader": "/washers-and-dryers/top-load-washers",
    },
    "winia": {
        "washer": "/products/washer",
        "dryer": "/products/dryer",
        "top_loader": "/products/top-loader",
    },
}


class ManufacturerAdapter:
    source_id: str = SourceId.MANUFACTURER.value

    def __init__(self, fetcher: HtmlFetcher) -> None:
        self.fetcher = fetcher

    def catalog_url(self, brand: Brand, category: Category) -> str:
        paths = _CATALOG_PATHS.get(brand.id)
        if paths is None:
            raise ValueError(f"unsupported manufacturer brand: {brand.id}")
        path = paths.get(category.id.value)
        if path is None:
            raise ValueError(f"no catalog path for {brand.id}/{category.id.value}")
        return f"{brand.manufacturer_site.rstrip('/')}{path}"

    def discover(self, brand: Brand, category: Category) -> list[ProductRef]:
        html = self.fetcher.fetch(self.catalog_url(brand, category))
        soup = BeautifulSoup(html, "lxml")
        refs: list[ProductRef] = []
        for card in soup.select("article.product_card"):
            model_code = card.get("data-model")
            link = card.select_one("a")
            name_el = card.select_one(".name")
            if not model_code or not link or not name_el:
                continue
            href = link.get("href") or ""
            url = href if href.startswith("http") else f"{brand.manufacturer_site.rstrip('/')}{href}"
            refs.append(
                ProductRef(
                    source_id=SourceId.MANUFACTURER,
                    brand_id=brand.id,
                    category_id=category.id,
                    external_id=str(model_code),
                    url=url,
                    model_name=name_el.get_text(strip=True),
                    model_code=str(model_code),
                )
            )
        return refs

    def fetch_specs(self, ref: ProductRef) -> SpecPayload:
        html = self.fetcher.fetch(ref.url)
        soup = BeautifulSoup(html, "lxml")
        attributes: dict[str, str] = {}
        for row in soup.select(".spec_grid .row"):
            label_el = row.select_one(".label")
            value_el = row.select_one(".value")
            if label_el and value_el:
                attributes[label_el.get_text(strip=True)] = value_el.get_text(strip=True)
        image_urls: list[str] = []
        for img in soup.select(".gallery img"):
            src = img.get("src")
            if src:
                image_urls.append(str(src))
        return SpecPayload(
            product_ref=ref,
            attributes=attributes,
            captured_at=datetime.now(),
            image_urls=image_urls,
        )

    def fetch_reviews(
        self, ref: ProductRef, since: datetime | None = None
    ) -> Iterator[RawReview]:
        return iter(())
