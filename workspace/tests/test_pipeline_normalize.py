from __future__ import annotations

from pathlib import Path

import pytest

from lg_dash.adapters.danawa import DanawaAdapter
from lg_dash.models import Brand, Category, CategoryId
from lg_dash.pipeline.crawl import run_crawl
from lg_dash.pipeline.normalize import (
    Normalizer,
    load_attr_dictionary,
    normalize_and_persist,
)
from lg_dash.storage import repo
from lg_dash.storage.db import connect, migrate

from tests.adapters.file_fetcher import FileFetcher

ROOT = Path(__file__).parent.parent
DANAWA_FIXTURES = ROOT / "tests" / "fixtures" / "danawa"
CONFIG_DIR = ROOT / "config"


@pytest.fixture
def crawled_db(tmp_path: Path) -> Path:
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
    conn.close()
    adapter = DanawaAdapter(fetcher=FileFetcher.for_danawa(DANAWA_FIXTURES))
    run_crawl(
        adapter=adapter,
        brand_id="lg",
        category_id="washer",
        limit=3,
        db_path=db,
    )
    return db


@pytest.fixture(scope="module")
def normalizer() -> Normalizer:
    return Normalizer(load_attr_dictionary(CONFIG_DIR / "attr_dictionary.yaml"))


class TestNormalizeAndPersist:
    def test_persists_spec_facts_for_one_product(
        self, crawled_db: Path, normalizer: Normalizer
    ) -> None:
        conn = connect(crawled_db)
        try:
            summary = normalize_and_persist(
                conn, product_id=1, normalizer=normalizer
            )
            assert summary["danawa"] >= 8
            assert repo.count(conn, "spec_fact") >= 8
        finally:
            conn.close()

    def test_high_confidence_ratio_above_80_percent(
        self, crawled_db: Path, normalizer: Normalizer
    ) -> None:
        conn = connect(crawled_db)
        try:
            normalize_and_persist(conn, product_id=1, normalizer=normalizer)
            rows = conn.execute(
                "SELECT confidence FROM spec_fact WHERE product_id = 1"
            ).fetchall()
            assert len(rows) > 0
            high = [r for r in rows if r["confidence"] >= 0.7]
            assert len(high) / len(rows) >= 0.8
        finally:
            conn.close()

    def test_rerun_replaces_facts_not_duplicates(
        self, crawled_db: Path, normalizer: Normalizer
    ) -> None:
        conn = connect(crawled_db)
        try:
            normalize_and_persist(conn, product_id=1, normalizer=normalizer)
            first_count = repo.count(conn, "spec_fact")
            normalize_and_persist(conn, product_id=1, normalizer=normalizer)
            second_count = repo.count(conn, "spec_fact")
            assert first_count == second_count
        finally:
            conn.close()

    def test_all_three_products_normalized(
        self, crawled_db: Path, normalizer: Normalizer
    ) -> None:
        conn = connect(crawled_db)
        try:
            for pid in (1, 2, 3):
                normalize_and_persist(conn, product_id=pid, normalizer=normalizer)
            total_facts = repo.count(conn, "spec_fact")
            assert total_facts >= 24
            distinct_products = conn.execute(
                "SELECT COUNT(DISTINCT product_id) AS n FROM spec_fact"
            ).fetchone()["n"]
            assert distinct_products == 3
        finally:
            conn.close()


class TestNormalizeRespectsManualOverride:
    def test_override_replaces_auto_fact(
        self, crawled_db: Path, normalizer: Normalizer
    ) -> None:
        conn = connect(crawled_db)
        try:
            normalize_and_persist(conn, product_id=1, normalizer=normalizer)
            before = conn.execute(
                "SELECT value_num FROM spec_fact "
                "WHERE product_id=1 AND canonical_key='wash_capacity_kg'"
            ).fetchone()
            assert before is not None
            assert before["value_num"] == 24.0

            repo.save_manual_override(
                conn,
                product_id=1,
                canonical_key="wash_capacity_kg",
                value_num=99.0,
                value_text=None,
                unit="kg",
                set_by="qa-tester",
            )

            normalize_and_persist(conn, product_id=1, normalizer=normalizer)

            after = conn.execute(
                "SELECT value_num, matched_by, source_id, confidence "
                "FROM spec_fact "
                "WHERE product_id=1 AND canonical_key='wash_capacity_kg'"
            ).fetchone()
            assert after["value_num"] == 99.0
            assert after["matched_by"] == "manual"
            assert after["confidence"] == 1.0
        finally:
            conn.close()

    def test_override_for_unmatched_key_creates_new_fact(
        self, crawled_db: Path, normalizer: Normalizer
    ) -> None:
        conn = connect(crawled_db)
        try:
            normalize_and_persist(conn, product_id=1, normalizer=normalizer)
            before = conn.execute(
                "SELECT COUNT(*) AS n FROM spec_fact "
                "WHERE product_id=1 AND canonical_key='dry_capacity_kg'"
            ).fetchone()["n"]
            assert before == 0

            repo.save_manual_override(
                conn,
                product_id=1,
                canonical_key="dry_capacity_kg",
                value_num=12.0,
                value_text=None,
                unit="kg",
                set_by="user",
            )
            normalize_and_persist(conn, product_id=1, normalizer=normalizer)

            row = conn.execute(
                "SELECT value_num, matched_by FROM spec_fact "
                "WHERE product_id=1 AND canonical_key='dry_capacity_kg'"
            ).fetchone()
            assert row is not None
            assert row["value_num"] == 12.0
            assert row["matched_by"] == "manual"
        finally:
            conn.close()

    def test_no_override_leaves_auto_fact_intact(
        self, crawled_db: Path, normalizer: Normalizer
    ) -> None:
        conn = connect(crawled_db)
        try:
            normalize_and_persist(conn, product_id=1, normalizer=normalizer)
            row = conn.execute(
                "SELECT matched_by FROM spec_fact "
                "WHERE product_id=1 AND canonical_key='wash_capacity_kg'"
            ).fetchone()
            assert row["matched_by"] == "rule"
        finally:
            conn.close()
