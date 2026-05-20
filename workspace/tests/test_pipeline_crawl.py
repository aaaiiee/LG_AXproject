from __future__ import annotations

from pathlib import Path

import pytest

from lg_dash.adapters.danawa import DanawaAdapter
from lg_dash.models import Brand, Category, CategoryId
from lg_dash.pipeline.crawl import run_crawl
from lg_dash.storage import repo
from lg_dash.storage.db import connect, migrate

from tests.adapters.file_fetcher import FileFetcher

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "danawa"


@pytest.fixture
def seeded_db(tmp_path: Path) -> Path:
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
            search_keywords={
                "세탁기": "LG 트롬",
                "건조기": "LG 트롬 건조기",
                "통돌이": "LG 통돌이 세탁기",
            },
        ),
    )
    repo.upsert_category(conn, Category(id=CategoryId.WASHER, display="세탁기"))
    conn.close()
    return db


@pytest.fixture
def adapter_factory():
    def _build():
        return DanawaAdapter(fetcher=FileFetcher.for_danawa(FIXTURE_DIR))
    return _build


class TestRunCrawl:
    def test_persists_three_products_specs_and_reviews(
        self, seeded_db: Path, adapter_factory
    ) -> None:
        result = run_crawl(
            adapter=adapter_factory(),
            brand_id="lg",
            category_id="washer",
            limit=3,
            db_path=seeded_db,
        )

        assert result.products_processed == 3

        conn = connect(seeded_db)
        try:
            assert repo.count(conn, "product") == 3
            assert repo.count(conn, "product_source_ref") == 3
            assert repo.count(conn, "spec_raw") == 3
            assert repo.count(conn, "raw_review") == 7
        finally:
            conn.close()

    def test_marks_refresh_log_success(
        self, seeded_db: Path, adapter_factory
    ) -> None:
        result = run_crawl(
            adapter=adapter_factory(),
            brand_id="lg",
            category_id="washer",
            limit=3,
            db_path=seeded_db,
        )

        conn = connect(seeded_db)
        try:
            row = conn.execute(
                "SELECT status, items_processed, finished_at FROM refresh_log WHERE run_id=?",
                (result.run_id,),
            ).fetchone()
            assert row["status"] == "success"
            assert row["items_processed"] == 3
            assert row["finished_at"] is not None
        finally:
            conn.close()

    def test_idempotent_rerun_does_not_duplicate(
        self, seeded_db: Path, adapter_factory
    ) -> None:
        run_crawl(
            adapter=adapter_factory(),
            brand_id="lg",
            category_id="washer",
            limit=3,
            db_path=seeded_db,
        )
        run_crawl(
            adapter=adapter_factory(),
            brand_id="lg",
            category_id="washer",
            limit=3,
            db_path=seeded_db,
        )
        conn = connect(seeded_db)
        try:
            assert repo.count(conn, "product") == 3
            assert repo.count(conn, "product_source_ref") == 3
            assert repo.count(conn, "raw_review") == 7
        finally:
            conn.close()

    def test_respects_limit(self, seeded_db: Path, adapter_factory) -> None:
        result = run_crawl(
            adapter=adapter_factory(),
            brand_id="lg",
            category_id="washer",
            limit=1,
            db_path=seeded_db,
        )
        assert result.products_processed == 1
        conn = connect(seeded_db)
        try:
            assert repo.count(conn, "product") == 1
        finally:
            conn.close()
