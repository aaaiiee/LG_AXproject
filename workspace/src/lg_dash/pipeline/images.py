from __future__ import annotations

import argparse
import io
import json
import sqlite3
from pathlib import Path

from PIL import Image

from lg_dash.adapters.fetcher import HttpImageFetcher, ImageFetcher
from lg_dash.models import SourceId
from lg_dash.storage import repo
from lg_dash.storage.db import connect, db_path

__all__ = ["download_product_images", "normalize_product_images"]


_SOURCE_PRIORITY = [
    SourceId.MANUFACTURER,
    SourceId.DANAWA,
    SourceId.COUPANG,
    SourceId.YOUTUBE,
]


def _save_webp(raw: bytes, target: Path, max_width: int) -> tuple[int, int, int]:
    img = Image.open(io.BytesIO(raw))
    if img.mode != "RGB":
        img = img.convert("RGB")
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
    target.parent.mkdir(parents=True, exist_ok=True)
    img.save(target, format="WEBP", quality=85)
    return img.width, img.height, target.stat().st_size


def download_product_images(
    conn: sqlite3.Connection,
    *,
    product_id: int,
    source_id: SourceId,
    image_urls: list[str],
    fetcher: ImageFetcher,
    image_dir: Path,
    max_width: int = 1200,
) -> int:
    inserted = 0
    for idx, url in enumerate(image_urls):
        target = image_dir / str(product_id) / f"{idx}.webp"
        try:
            raw = fetcher.fetch_bytes(url)
            width, height, size = _save_webp(raw, target, max_width)
        except Exception:
            repo.save_product_image(
                conn,
                product_id=product_id,
                source_id=source_id,
                idx=idx,
                original_url=url,
                is_primary=False,
                status="failed",
            )
            continue
        repo.save_product_image(
            conn,
            product_id=product_id,
            source_id=source_id,
            idx=idx,
            original_url=url,
            local_path=str(target),
            width=width,
            height=height,
            bytes_len=size,
            is_primary=(idx == 0),
            status="ok",
        )
        inserted += 1
    return inserted


def normalize_product_images(
    conn: sqlite3.Connection,
    *,
    product_id: int,
    fetcher: ImageFetcher,
    image_dir: Path,
    max_width: int = 1200,
) -> tuple[SourceId, int] | None:
    rows = conn.execute(
        """
        SELECT source_id, payload_json
        FROM spec_raw
        WHERE product_id = ?
        """,
        (product_id,),
    ).fetchall()
    by_source: dict[str, list[str]] = {}
    for r in rows:
        payload = json.loads(r["payload_json"])
        urls = payload.get("image_urls") or []
        if urls:
            by_source[r["source_id"]] = urls
    for src in _SOURCE_PRIORITY:
        if src.value in by_source:
            inserted = download_product_images(
                conn,
                product_id=product_id,
                source_id=src,
                image_urls=by_source[src.value],
                fetcher=fetcher,
                image_dir=image_dir,
                max_width=max_width,
            )
            return (src, inserted)
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download product images per source priority, resize to WebP"
    )
    parser.add_argument("--product-id", type=int, help="single product id")
    parser.add_argument("--all", action="store_true", help="all products in DB")
    parser.add_argument(
        "--image-dir",
        type=Path,
        default=Path("storage/images"),
        help="local image storage directory",
    )
    parser.add_argument("--max-width", type=int, default=1200)
    args = parser.parse_args()
    if not (args.all or args.product_id):
        parser.error("either --product-id or --all is required")

    fetcher = HttpImageFetcher()
    conn = connect(db_path())
    try:
        if args.all:
            ids = [r["id"] for r in conn.execute("SELECT id FROM product ORDER BY id")]
        else:
            ids = [args.product_id]
        for pid in ids:
            result = normalize_product_images(
                conn,
                product_id=pid,
                fetcher=fetcher,
                image_dir=args.image_dir,
                max_width=args.max_width,
            )
            if result is None:
                print(f"product_id={pid} no_image_urls_in_spec_raw")
            else:
                src, n = result
                print(f"product_id={pid} source={src.value} downloaded={n}")
    finally:
        conn.close()
        fetcher.close()


if __name__ == "__main__":
    main()
