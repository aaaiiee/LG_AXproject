from __future__ import annotations

from pathlib import Path

import pytest

from lg_dash.adapters.danawa import DanawaAdapter
from lg_dash.models import Brand, Category, CategoryId
from lg_dash.pipeline.normalize import Normalizer, load_attr_dictionary
from lg_dash.pipeline.run import run_pipeline
from lg_dash.storage import repo
from lg_dash.storage.db import connect, migrate

from tests.adapters.file_fetcher import FileFetcher

ROOT = Path(__file__).parent.parent
DANAWA_FIXTURES = ROOT / "tests" / "fixtures" / "danawa"
CONFIG_DIR = ROOT / "config"


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
            search_keywords={"세탁기": "LG 트롬"},
        ),
    )
    repo.upsert_category(conn, Category(id=CategoryId.WASHER, display="세탁기"))
    conn.close()
    return db


@pytest.fixture(scope="module")
def normalizer() -> Normalizer:
    return Normalizer(load_attr_dictionary(CONFIG_DIR / "attr_dictionary.yaml"))


class TestRunPipeline:
    def test_chains_crawl_and_normalize_when_only_those_provided(
        self, seeded_db: Path, normalizer: Normalizer
    ) -> None:
        adapter = DanawaAdapter(fetcher=FileFetcher.for_danawa(DANAWA_FIXTURES))
        result = run_pipeline(
            adapter=adapter,
            normalizer=normalizer,
            brand_id="lg",
            category_id="washer",
            limit=3,
            db_path=seeded_db,
        )
        assert result["products_processed"] == 3
        assert result["spec_facts_total"] >= 8
        assert result["images_total"] == 0
        assert result["analyses_total"] == 0
