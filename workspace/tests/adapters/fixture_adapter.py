from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from lg_dash.models import (
    Brand,
    Category,
    ProductRef,
    RawReview,
    SourceId,
    SpecPayload,
)


class FixtureAdapter:
    source_id: str = SourceId.MANUFACTURER.value

    def __init__(self, fixture_dir: Path):
        self.fixture_dir = fixture_dir

    def discover(self, brand: Brand, category: Category) -> list[ProductRef]:
        products_file = self.fixture_dir / "products.json"
        raw = json.loads(products_file.read_text(encoding="utf-8"))
        return [
            ProductRef(
                source_id=SourceId(self.source_id),
                brand_id=brand.id,
                category_id=category.id,
                external_id=item["external_id"],
                url=item["url"],
                model_name=item["model_name"],
                model_code=item.get("model_code"),
            )
            for item in raw
        ]

    def fetch_specs(self, ref: ProductRef) -> SpecPayload:
        spec_file = self.fixture_dir / "specs" / f"{ref.external_id}.json"
        raw = json.loads(spec_file.read_text(encoding="utf-8"))
        return SpecPayload(
            product_ref=ref,
            attributes=raw["attributes"],
            captured_at=datetime.fromisoformat(raw["captured_at"]),
        )

    def fetch_reviews(
        self, ref: ProductRef, since: datetime | None = None
    ) -> Iterator[RawReview]:
        review_file = self.fixture_dir / "reviews" / f"{ref.external_id}.json"
        raw = json.loads(review_file.read_text(encoding="utf-8"))
        for item in raw:
            posted_at = (
                datetime.fromisoformat(item["posted_at"]) if item.get("posted_at") else None
            )
            if since is not None and posted_at is not None and posted_at < since:
                continue
            yield RawReview(
                product_ref=ref,
                author_hash=item.get("author_hash"),
                rating=item.get("rating"),
                text=item["text"],
                posted_at=posted_at,
                url=item.get("url"),
                language=item.get("language", "ko"),
            )
