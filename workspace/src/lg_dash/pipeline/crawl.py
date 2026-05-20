from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from lg_dash.adapters.base import SourceAdapter
from lg_dash.adapters.coupang import CoupangAdapter
from lg_dash.adapters.danawa import DanawaAdapter
from lg_dash.adapters.fetcher import HttpFetcher
from lg_dash.adapters.manufacturer import ManufacturerAdapter
from lg_dash.adapters.youtube import YouTubeAdapter
from lg_dash.models import Brand, Category, CategoryId, RefreshStatus, SourceId
from lg_dash.storage import repo
from lg_dash.storage.db import connect, db_path, migrate, transaction


@dataclass
class CrawlResult:
    run_id: int
    products_processed: int


def _resolve_brand(conn, brand_id: str) -> Brand:
    for b in repo.list_brands(conn):
        if b.id == brand_id:
            return b
    raise ValueError(f"brand not found in DB: {brand_id} (run seed_brands first)")


def _resolve_category(conn, category_id: str) -> Category:
    for c in repo.list_categories(conn):
        if c.id.value == category_id:
            return c
    raise ValueError(f"category not found: {category_id}")


def run_crawl(
    *,
    adapter: SourceAdapter,
    brand_id: str,
    category_id: str,
    limit: int,
    db_path: Path,
) -> CrawlResult:
    conn = connect(db_path)
    try:
        brand = _resolve_brand(conn, brand_id)
        category = _resolve_category(conn, category_id)

        run_id = repo.start_refresh(
            conn, brands=[brand.id], categories=[category.id]
        )

        refs = adapter.discover(brand, category)[:limit]
        processed = 0
        try:
            for ref in refs:
                with transaction(conn):
                    product_id = repo.upsert_product(conn, ref)
                    repo.upsert_product_source_ref(conn, product_id, ref)
                    payload = adapter.fetch_specs(ref)
                    repo.save_spec_raw(conn, product_id, payload)
                    reviews = list(adapter.fetch_reviews(ref))
                    repo.save_raw_reviews(conn, product_id, reviews)
                processed += 1
            repo.finalize_refresh(
                conn,
                run_id,
                status=RefreshStatus.SUCCESS.value,
                items_processed=processed,
            )
        except Exception as exc:
            repo.finalize_refresh(
                conn,
                run_id,
                status=RefreshStatus.FAILED.value,
                items_processed=processed,
                error_text=repr(exc),
            )
            raise

        return CrawlResult(run_id=run_id, products_processed=processed)
    finally:
        conn.close()


_ADAPTER_FACTORIES = {
    SourceId.DANAWA.value: lambda fetcher: DanawaAdapter(fetcher=fetcher),
    SourceId.MANUFACTURER.value: lambda fetcher: ManufacturerAdapter(fetcher=fetcher),
    SourceId.COUPANG.value: lambda fetcher: CoupangAdapter(fetcher=fetcher),
    SourceId.YOUTUBE.value: lambda fetcher: YouTubeAdapter(fetcher=fetcher),
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crawl a source for a given brand+category and persist into SQLite"
    )
    parser.add_argument(
        "--source", required=True, choices=list(_ADAPTER_FACTORIES.keys())
    )
    parser.add_argument("--brand", required=True, help="brand id (e.g. lg, samsung)")
    parser.add_argument(
        "--category",
        required=True,
        choices=[c.value for c in CategoryId],
    )
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()

    fetcher = HttpFetcher()
    factory = _ADAPTER_FACTORIES[args.source]
    adapter: SourceAdapter = factory(fetcher)

    try:
        result = run_crawl(
            adapter=adapter,
            brand_id=args.brand,
            category_id=args.category,
            limit=args.limit,
            db_path=db_path(),
        )
    finally:
        fetcher.close()

    print(
        f"run_id={result.run_id} processed={result.products_processed} "
        f"source={args.source} brand={args.brand} category={args.category}"
    )


if __name__ == "__main__":
    main()
