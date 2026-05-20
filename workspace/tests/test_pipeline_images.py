from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from lg_dash.adapters.fetcher import ImageFetcher
from lg_dash.models import Brand, Category, CategoryId, ProductRef, SourceId
from lg_dash.pipeline.images import download_product_images
from lg_dash.storage import repo
from lg_dash.storage.db import connect, migrate


def _png_bytes(width: int = 800, height: int = 600, color: str = "red") -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class StaticImageFetcher:
    def __init__(self, mapping: dict[str, bytes]) -> None:
        self._mapping = mapping
        self.calls: list[str] = []

    def fetch_bytes(self, url: str) -> bytes:
        self.calls.append(url)
        if url not in self._mapping:
            raise FileNotFoundError(url)
        return self._mapping[url]


@pytest.fixture
def db_with_product(tmp_path: Path) -> tuple[Path, int]:
    db = tmp_path / "db.sqlite"
    conn = connect(db)
    migrate(conn)
    repo.upsert_brand(
        conn,
        Brand(
            id="lg",
            display="LG전자",
            aliases=["LG"],
            manufacturer_site="https://www.lge.co.kr",
            search_keywords={"세탁기": "LG 트롬"},
        ),
    )
    repo.upsert_category(conn, Category(id=CategoryId.WASHER, display="세탁기"))
    ref = ProductRef(
        source_id=SourceId.MANUFACTURER,
        brand_id="lg",
        category_id=CategoryId.WASHER,
        external_id="WT-LGA-001",
        url="https://www.lge.co.kr/product/WT-LGA-001",
        model_name="LG 트롬 워시콤보 24kg",
        model_code="WT-LGA-001",
    )
    product_id = repo.upsert_product(conn, ref)
    repo.upsert_product_source_ref(conn, product_id, ref)
    conn.close()
    return db, product_id


class TestImageFetcherProtocol:
    def test_is_runtime_checkable(self) -> None:
        assert getattr(ImageFetcher, "_is_runtime_protocol", False) is True

    def test_static_fetcher_satisfies_protocol(self) -> None:
        fetcher = StaticImageFetcher({"http://x/a.png": b"data"})
        assert isinstance(fetcher, ImageFetcher)


class TestDownloadProductImages:
    def test_creates_webp_files_on_disk(
        self, db_with_product, tmp_path: Path
    ) -> None:
        db, product_id = db_with_product
        urls = [
            "https://example.test/img/a.png",
            "https://example.test/img/b.png",
        ]
        fetcher = StaticImageFetcher(
            {urls[0]: _png_bytes(400, 300, "red"), urls[1]: _png_bytes(600, 450, "blue")}
        )
        image_dir = tmp_path / "images"

        conn = connect(db)
        try:
            inserted = download_product_images(
                conn,
                product_id=product_id,
                source_id=SourceId.MANUFACTURER,
                image_urls=urls,
                fetcher=fetcher,
                image_dir=image_dir,
            )
        finally:
            conn.close()

        assert inserted == 2
        product_image_dir = image_dir / str(product_id)
        files = sorted(product_image_dir.glob("*.webp"))
        assert len(files) == 2

    def test_persists_db_rows_with_primary_flag(
        self, db_with_product, tmp_path: Path
    ) -> None:
        db, product_id = db_with_product
        urls = [
            "https://example.test/img/a.png",
            "https://example.test/img/b.png",
        ]
        fetcher = StaticImageFetcher({u: _png_bytes() for u in urls})
        conn = connect(db)
        try:
            download_product_images(
                conn,
                product_id=product_id,
                source_id=SourceId.MANUFACTURER,
                image_urls=urls,
                fetcher=fetcher,
                image_dir=tmp_path / "images",
            )
            rows = conn.execute(
                "SELECT idx, source_id, is_primary, status, local_path "
                "FROM product_image WHERE product_id=? ORDER BY idx",
                (product_id,),
            ).fetchall()
        finally:
            conn.close()
        assert len(rows) == 2
        assert rows[0]["idx"] == 0
        assert rows[0]["is_primary"] == 1
        assert rows[0]["source_id"] == "manufacturer"
        assert rows[0]["status"] == "ok"
        assert rows[0]["local_path"].endswith(".webp")
        assert rows[1]["is_primary"] == 0

    def test_resizes_large_image_to_max_width(
        self, db_with_product, tmp_path: Path
    ) -> None:
        db, product_id = db_with_product
        url = "https://example.test/img/big.png"
        fetcher = StaticImageFetcher({url: _png_bytes(2400, 1800)})
        image_dir = tmp_path / "images"
        conn = connect(db)
        try:
            download_product_images(
                conn,
                product_id=product_id,
                source_id=SourceId.MANUFACTURER,
                image_urls=[url],
                fetcher=fetcher,
                image_dir=image_dir,
                max_width=300,
            )
            row = conn.execute(
                "SELECT local_path, width FROM product_image WHERE product_id=?",
                (product_id,),
            ).fetchone()
        finally:
            conn.close()
        assert row["width"] <= 300
        with Image.open(row["local_path"]) as saved:
            assert saved.width <= 300

    def test_rerun_is_idempotent(
        self, db_with_product, tmp_path: Path
    ) -> None:
        db, product_id = db_with_product
        urls = ["https://example.test/img/a.png", "https://example.test/img/b.png"]
        fetcher = StaticImageFetcher({u: _png_bytes() for u in urls})
        image_dir = tmp_path / "images"
        conn = connect(db)
        try:
            download_product_images(
                conn, product_id=product_id, source_id=SourceId.MANUFACTURER,
                image_urls=urls, fetcher=fetcher, image_dir=image_dir,
            )
            download_product_images(
                conn, product_id=product_id, source_id=SourceId.MANUFACTURER,
                image_urls=urls, fetcher=fetcher, image_dir=image_dir,
            )
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM product_image WHERE product_id=?",
                (product_id,),
            ).fetchone()["n"]
        finally:
            conn.close()
        assert count == 2

    def test_failed_download_recorded_as_status_failed(
        self, db_with_product, tmp_path: Path
    ) -> None:
        db, product_id = db_with_product
        ok = "https://example.test/img/ok.png"
        bad = "https://example.test/img/missing.png"
        fetcher = StaticImageFetcher({ok: _png_bytes()})
        conn = connect(db)
        try:
            download_product_images(
                conn,
                product_id=product_id,
                source_id=SourceId.MANUFACTURER,
                image_urls=[ok, bad],
                fetcher=fetcher,
                image_dir=tmp_path / "images",
            )
            rows = conn.execute(
                "SELECT idx, status FROM product_image WHERE product_id=? ORDER BY idx",
                (product_id,),
            ).fetchall()
        finally:
            conn.close()
        assert rows[0]["status"] == "ok"
        assert rows[1]["status"] == "failed"
