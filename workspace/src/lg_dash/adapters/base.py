from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol, runtime_checkable

from lg_dash.models import Brand, Category, ProductRef, RawReview, SpecPayload


@runtime_checkable
class SourceAdapter(Protocol):
    source_id: str

    def discover(self, brand: Brand, category: Category) -> list[ProductRef]: ...

    def fetch_specs(self, ref: ProductRef) -> SpecPayload: ...

    def fetch_reviews(
        self, ref: ProductRef, since: datetime | None = None
    ) -> Iterable[RawReview]: ...
