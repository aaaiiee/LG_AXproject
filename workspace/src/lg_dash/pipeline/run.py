from __future__ import annotations

import argparse
from pathlib import Path

from lg_dash.adapters.base import SourceAdapter
from lg_dash.adapters.coupang import CoupangAdapter
from lg_dash.adapters.danawa import DanawaAdapter
from lg_dash.adapters.fetcher import HttpFetcher, HttpImageFetcher, ImageFetcher
from lg_dash.adapters.manufacturer import ManufacturerAdapter
from lg_dash.adapters.youtube import YouTubeAdapter
from lg_dash.models import CategoryId, SourceId
from lg_dash.pipeline.crawl import run_crawl
from lg_dash.pipeline.images import normalize_product_images
from lg_dash.pipeline.llm_analyze import Analyzer, analyze_and_persist, load_sentiment_tags
from lg_dash.pipeline.normalize import Normalizer, load_attr_dictionary, normalize_and_persist
from lg_dash.llm.client import AnthropicClient
from lg_dash.storage.db import connect, db_path, migrate

__all__ = ["run_pipeline"]


_ADAPTER_FACTORIES = {
    SourceId.DANAWA.value: lambda fetcher: DanawaAdapter(fetcher=fetcher),
    SourceId.MANUFACTURER.value: lambda fetcher: ManufacturerAdapter(fetcher=fetcher),
    SourceId.COUPANG.value: lambda fetcher: CoupangAdapter(fetcher=fetcher),
    SourceId.YOUTUBE.value: lambda fetcher: YouTubeAdapter(fetcher=fetcher),
}


def run_pipeline(
    *,
    adapter: SourceAdapter,
    normalizer: Normalizer,
    brand_id: str,
    category_id: str,
    limit: int,
    db_path: Path,
    image_fetcher: ImageFetcher | None = None,
    image_dir: Path | None = None,
    analyzer: Analyzer | None = None,
) -> dict[str, int]:
    crawl_result = run_crawl(
        adapter=adapter,
        brand_id=brand_id,
        category_id=category_id,
        limit=limit,
        db_path=db_path,
    )

    spec_facts_total = 0
    images_total = 0
    analyses_total = 0

    conn = connect(db_path)
    try:
        migrate(conn)
        product_ids = [
            r["id"] for r in conn.execute("SELECT id FROM product ORDER BY id")
        ]
        for pid in product_ids:
            summary = normalize_and_persist(conn, product_id=pid, normalizer=normalizer)
            spec_facts_total += sum(summary.values())

            if image_fetcher is not None and image_dir is not None:
                result = normalize_product_images(
                    conn,
                    product_id=pid,
                    fetcher=image_fetcher,
                    image_dir=image_dir,
                )
                if result is not None:
                    _, n = result
                    images_total += n

            if analyzer is not None:
                analysis = analyze_and_persist(
                    conn, product_id=pid, analyzer=analyzer
                )
                if analysis is not None:
                    analyses_total += 1
    finally:
        conn.close()

    return {
        "run_id": crawl_result.run_id,
        "products_processed": crawl_result.products_processed,
        "spec_facts_total": spec_facts_total,
        "images_total": images_total,
        "analyses_total": analyses_total,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="End-to-end pipeline: crawl → normalize → [images] → [llm]"
    )
    parser.add_argument(
        "--source", required=True, choices=list(_ADAPTER_FACTORIES.keys())
    )
    parser.add_argument("--brand", required=True)
    parser.add_argument(
        "--category", required=True, choices=[c.value for c in CategoryId]
    )
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument(
        "--config-dir", type=Path, default=Path("config")
    )
    parser.add_argument("--skip-images", action="store_true")
    parser.add_argument("--skip-llm", action="store_true")
    parser.add_argument(
        "--image-dir", type=Path, default=Path("storage/images")
    )
    args = parser.parse_args()

    fetcher = HttpFetcher()
    image_fetcher = None if args.skip_images else HttpImageFetcher()
    adapter = _ADAPTER_FACTORIES[args.source](fetcher)
    normalizer = Normalizer(
        load_attr_dictionary(args.config_dir / "attr_dictionary.yaml")
    )
    analyzer = None
    if not args.skip_llm:
        analyzer = Analyzer(
            llm_client=AnthropicClient(),
            sentiment_tags=load_sentiment_tags(args.config_dir / "sentiment_tags.yaml"),
        )

    try:
        result = run_pipeline(
            adapter=adapter,
            normalizer=normalizer,
            brand_id=args.brand,
            category_id=args.category,
            limit=args.limit,
            db_path=db_path(),
            image_fetcher=image_fetcher,
            image_dir=args.image_dir if image_fetcher else None,
            analyzer=analyzer,
        )
    finally:
        fetcher.close()
        if image_fetcher is not None:
            image_fetcher.close()

    print(
        f"run_id={result['run_id']} products={result['products_processed']} "
        f"facts={result['spec_facts_total']} images={result['images_total']} "
        f"analyses={result['analyses_total']}"
    )


if __name__ == "__main__":
    main()
