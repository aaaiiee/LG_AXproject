from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from lg_dash.models import (
    Brand,
    Category,
    CategoryId,
    MatchedBy,
    ProductRef,
    RawReview,
    SourceId,
    SpecPayload,
)
from lg_dash.pipeline.normalize import NormalizedFact
from lg_dash.storage import repo
from lg_dash.storage.db import connect, migrate


@pytest.fixture
def conn(tmp_path: Path):
    c = connect(tmp_path / "db.sqlite")
    migrate(c)
    repo.upsert_brand(
        c,
        Brand(
            id="lg",
            display="LG전자",
            aliases=["LG"],
            manufacturer_site="https://www.lge.co.kr",
            search_keywords={"세탁기": "LG 트롬"},
        ),
    )
    repo.upsert_category(c, Category(id=CategoryId.WASHER, display="세탁기"))
    yield c
    c.close()


def _ref(external_id: str = "12345678") -> ProductRef:
    return ProductRef(
        source_id=SourceId.DANAWA,
        brand_id="lg",
        category_id=CategoryId.WASHER,
        external_id=external_id,
        url=f"https://prod.danawa.com/info/?pcode={external_id}",
        model_name="LG 트롬 워시콤보 WK24WS",
        model_code="WK24WS",
    )


class TestProductUpsert:
    def test_creates_product_first_time(self, conn) -> None:
        product_id = repo.upsert_product(conn, _ref())
        assert isinstance(product_id, int) and product_id > 0
        assert repo.count(conn, "product") == 1

    def test_returns_same_id_for_same_model_code(self, conn) -> None:
        a = repo.upsert_product(conn, _ref())
        b = repo.upsert_product(conn, _ref())
        assert a == b
        assert repo.count(conn, "product") == 1

    def test_different_model_codes_create_distinct_products(self, conn) -> None:
        ref1 = _ref("12345678")
        ref2 = _ref("87654321")
        ref2 = ref2.model_copy(update={"model_code": "F24VDD"})
        a = repo.upsert_product(conn, ref1)
        b = repo.upsert_product(conn, ref2)
        assert a != b
        assert repo.count(conn, "product") == 2


class TestProductSourceRef:
    def test_inserts_then_idempotent(self, conn) -> None:
        ref = _ref()
        product_id = repo.upsert_product(conn, ref)
        repo.upsert_product_source_ref(conn, product_id, ref)
        repo.upsert_product_source_ref(conn, product_id, ref)
        assert repo.count(conn, "product_source_ref") == 1

    def test_updates_url_on_conflict(self, conn) -> None:
        ref = _ref()
        product_id = repo.upsert_product(conn, ref)
        repo.upsert_product_source_ref(conn, product_id, ref)
        new_ref = ref.model_copy(update={"url": "https://prod.danawa.com/info/?pcode=12345678&v=2"})
        repo.upsert_product_source_ref(conn, product_id, new_ref)
        row = conn.execute(
            "SELECT url FROM product_source_ref WHERE product_id=? AND source_id=?",
            (product_id, ref.source_id.value),
        ).fetchone()
        assert row["url"].endswith("&v=2")


class TestSpecRaw:
    def test_save_spec_raw_stores_payload(self, conn) -> None:
        ref = _ref()
        product_id = repo.upsert_product(conn, ref)
        repo.upsert_product_source_ref(conn, product_id, ref)
        payload = SpecPayload(
            product_ref=ref,
            attributes={"세탁용량": "24kg", "탈수속도": "1400 RPM"},
            captured_at=datetime(2026, 5, 20, 10, 0),
        )
        repo.save_spec_raw(conn, product_id, payload)
        row = conn.execute(
            "SELECT payload_json FROM spec_raw WHERE product_id=? AND source_id=?",
            (product_id, ref.source_id.value),
        ).fetchone()
        assert row is not None
        data = json.loads(row["payload_json"])
        assert data["attributes"]["세탁용량"] == "24kg"


class TestRawReviews:
    def _review(self, ref: ProductRef, text: str = "세척력 좋습니다", rating: float = 5.0) -> RawReview:
        return RawReview(
            product_ref=ref,
            rating=rating,
            text=text,
            posted_at=datetime(2026, 5, 1),
        )

    def test_save_reviews_inserts_new(self, conn) -> None:
        ref = _ref()
        product_id = repo.upsert_product(conn, ref)
        repo.upsert_product_source_ref(conn, product_id, ref)
        inserted = repo.save_raw_reviews(conn, product_id, [self._review(ref)])
        assert inserted == 1
        assert repo.count(conn, "raw_review") == 1

    def test_save_reviews_dedupes_same_text(self, conn) -> None:
        ref = _ref()
        product_id = repo.upsert_product(conn, ref)
        repo.upsert_product_source_ref(conn, product_id, ref)
        review = self._review(ref)
        repo.save_raw_reviews(conn, product_id, [review])
        again = repo.save_raw_reviews(conn, product_id, [review])
        assert again == 0
        assert repo.count(conn, "raw_review") == 1

    def test_save_reviews_distinct_text_inserts_all(self, conn) -> None:
        ref = _ref()
        product_id = repo.upsert_product(conn, ref)
        repo.upsert_product_source_ref(conn, product_id, ref)
        items = [
            self._review(ref, "텍스트 A"),
            self._review(ref, "텍스트 B"),
            self._review(ref, "텍스트 C"),
        ]
        inserted = repo.save_raw_reviews(conn, product_id, items)
        assert inserted == 3


class TestSpecFacts:
    def _fact(
        self,
        canonical_key: str = "wash_capacity_kg",
        value_num: float = 24.0,
        unit: str = "kg",
        label: str = "세탁용량",
    ) -> NormalizedFact:
        return NormalizedFact(
            canonical_key=canonical_key,
            value_num=value_num,
            value_text=None,
            unit=unit,
            source_attr_label=label,
            confidence=1.0,
            matched_by=MatchedBy.RULE,
        )

    def test_save_inserts_one_row_per_fact(self, conn) -> None:
        ref = _ref()
        product_id = repo.upsert_product(conn, ref)
        facts = [
            self._fact("wash_capacity_kg", 24.0, "kg", "세탁용량"),
            self._fact("spin_rpm", 1400.0, "rpm", "탈수속도"),
        ]
        inserted = repo.save_spec_facts(
            conn,
            product_id,
            facts,
            source_id=SourceId.DANAWA,
            captured_at=datetime(2026, 5, 20, 10, 0),
        )
        assert inserted == 2
        assert repo.count(conn, "spec_fact") == 2

    def test_save_replaces_existing_for_same_product_and_source(self, conn) -> None:
        ref = _ref()
        product_id = repo.upsert_product(conn, ref)
        repo.save_spec_facts(
            conn,
            product_id,
            [self._fact("wash_capacity_kg", 24.0)],
            source_id=SourceId.DANAWA,
            captured_at=datetime(2026, 5, 20),
        )
        repo.save_spec_facts(
            conn,
            product_id,
            [
                self._fact("wash_capacity_kg", 25.0),
                self._fact("spin_rpm", 1400.0, "rpm", "탈수속도"),
            ],
            source_id=SourceId.DANAWA,
            captured_at=datetime(2026, 5, 21),
        )
        assert repo.count(conn, "spec_fact") == 2
        row = conn.execute(
            "SELECT value_num FROM spec_fact WHERE canonical_key='wash_capacity_kg'"
        ).fetchone()
        assert row["value_num"] == 25.0

    def test_save_preserves_other_source_facts(self, conn) -> None:
        ref = _ref()
        product_id = repo.upsert_product(conn, ref)
        repo.save_spec_facts(
            conn,
            product_id,
            [self._fact("wash_capacity_kg", 24.0)],
            source_id=SourceId.DANAWA,
            captured_at=datetime(2026, 5, 20),
        )
        repo.save_spec_facts(
            conn,
            product_id,
            [self._fact("wash_capacity_kg", 25.0)],
            source_id=SourceId.MANUFACTURER,
            captured_at=datetime(2026, 5, 20),
        )
        rows = conn.execute(
            "SELECT source_id, value_num FROM spec_fact "
            "WHERE canonical_key='wash_capacity_kg' ORDER BY source_id"
        ).fetchall()
        assert len(rows) == 2
        sources = {r["source_id"] for r in rows}
        assert sources == {"danawa", "manufacturer"}


class TestManualOverride:
    def test_save_creates_row(self, conn) -> None:
        product_id = repo.upsert_product(conn, _ref())
        repo.save_manual_override(
            conn,
            product_id=product_id,
            canonical_key="wash_capacity_kg",
            value_num=24.0,
            value_text=None,
            unit="kg",
            set_by="user",
        )
        assert repo.count(conn, "manual_override") == 1

    def test_save_upserts_on_same_key(self, conn) -> None:
        product_id = repo.upsert_product(conn, _ref())
        repo.save_manual_override(
            conn,
            product_id=product_id,
            canonical_key="wash_capacity_kg",
            value_num=24.0,
            value_text=None,
            unit="kg",
            set_by="user",
        )
        repo.save_manual_override(
            conn,
            product_id=product_id,
            canonical_key="wash_capacity_kg",
            value_num=25.0,
            value_text=None,
            unit="kg",
            set_by="user",
        )
        assert repo.count(conn, "manual_override") == 1
        row = conn.execute(
            "SELECT value_num FROM manual_override WHERE product_id=? AND canonical_key=?",
            (product_id, "wash_capacity_kg"),
        ).fetchone()
        assert row["value_num"] == 25.0

    def test_list_returns_overrides_for_product(self, conn) -> None:
        product_id = repo.upsert_product(conn, _ref())
        repo.save_manual_override(
            conn,
            product_id=product_id,
            canonical_key="wash_capacity_kg",
            value_num=24.0,
            value_text=None,
            unit="kg",
            set_by="user",
        )
        repo.save_manual_override(
            conn,
            product_id=product_id,
            canonical_key="spin_rpm",
            value_num=1400.0,
            value_text=None,
            unit="rpm",
            set_by="user",
        )
        rows = repo.list_manual_overrides(conn, product_id=product_id)
        assert len(rows) == 2
        keys = {r["canonical_key"] for r in rows}
        assert keys == {"wash_capacity_kg", "spin_rpm"}

    def test_delete_removes_override(self, conn) -> None:
        product_id = repo.upsert_product(conn, _ref())
        repo.save_manual_override(
            conn,
            product_id=product_id,
            canonical_key="wash_capacity_kg",
            value_num=24.0,
            value_text=None,
            unit="kg",
            set_by="user",
        )
        repo.delete_manual_override(
            conn, product_id=product_id, canonical_key="wash_capacity_kg"
        )
        assert repo.count(conn, "manual_override") == 0


class TestComparisonMatrix:
    def _seed_product(
        self,
        conn,
        *,
        model_code: str,
        model_name: str,
        facts: list[tuple[str, float | None, str | None, str]],
    ) -> int:
        ref = ProductRef(
            source_id=SourceId.DANAWA,
            brand_id="lg",
            category_id=CategoryId.WASHER,
            external_id=model_code,
            url=f"https://prod.danawa.com/info/?pcode={model_code}",
            model_name=model_name,
            model_code=model_code,
        )
        product_id = repo.upsert_product(conn, ref)
        repo.upsert_product_source_ref(conn, product_id, ref)
        fact_objs = [
            NormalizedFact(
                canonical_key=key,
                value_num=num,
                value_text=text,
                unit=unit,
                source_attr_label=key,
                confidence=1.0,
                matched_by=MatchedBy.RULE,
            )
            for (key, num, text, unit) in facts
        ]
        repo.save_spec_facts(
            conn,
            product_id,
            fact_objs,
            source_id=SourceId.DANAWA,
            captured_at=datetime(2026, 5, 20),
        )
        return product_id

    def test_empty_product_list_returns_empty(self, conn) -> None:
        m = repo.build_comparison_matrix(conn, [])
        assert m["products"] == []
        assert m["rows"] == []

    def test_single_product_returns_one_column(self, conn) -> None:
        pid = self._seed_product(
            conn,
            model_code="ALPHA",
            model_name="Alpha 24kg",
            facts=[("wash_capacity_kg", 24.0, None, "kg")],
        )
        m = repo.build_comparison_matrix(conn, [pid])
        assert len(m["products"]) == 1
        assert m["products"][0]["product_id"] == pid
        row = next(r for r in m["rows"] if r["canonical_key"] == "wash_capacity_kg")
        cells = {c["product_id"]: c for c in row["cells"]}
        assert cells[pid]["value_num"] == 24.0
        assert cells[pid]["rank"] == "neutral"

    def test_higher_is_better_ranks_max_as_best(self, conn) -> None:
        a = self._seed_product(
            conn,
            model_code="HIGH-A",
            model_name="A",
            facts=[("wash_capacity_kg", 24.0, None, "kg")],
        )
        b = self._seed_product(
            conn,
            model_code="HIGH-B",
            model_name="B",
            facts=[("wash_capacity_kg", 25.0, None, "kg")],
        )
        m = repo.build_comparison_matrix(conn, [a, b])
        row = next(r for r in m["rows"] if r["canonical_key"] == "wash_capacity_kg")
        cells = {c["product_id"]: c for c in row["cells"]}
        assert cells[a]["rank"] == "worst"
        assert cells[b]["rank"] == "best"

    def test_noise_db_lower_is_better(self, conn) -> None:
        a = self._seed_product(
            conn,
            model_code="QUIET",
            model_name="Quiet",
            facts=[("noise_db", 46.0, None, "dB")],
        )
        b = self._seed_product(
            conn,
            model_code="LOUD",
            model_name="Loud",
            facts=[("noise_db", 52.0, None, "dB")],
        )
        m = repo.build_comparison_matrix(conn, [a, b])
        row = next(r for r in m["rows"] if r["canonical_key"] == "noise_db")
        cells = {c["product_id"]: c for c in row["cells"]}
        assert cells[a]["rank"] == "best"
        assert cells[b]["rank"] == "worst"

    def test_price_lower_is_better(self, conn) -> None:
        cheap = self._seed_product(
            conn,
            model_code="CHEAP",
            model_name="Cheap",
            facts=[("price_krw", 990000.0, None, "krw")],
        )
        pricey = self._seed_product(
            conn,
            model_code="PRICEY",
            model_name="Pricey",
            facts=[("price_krw", 1690000.0, None, "krw")],
        )
        m = repo.build_comparison_matrix(conn, [cheap, pricey])
        row = next(r for r in m["rows"] if r["canonical_key"] == "price_krw")
        cells = {c["product_id"]: c for c in row["cells"]}
        assert cells[cheap]["rank"] == "best"
        assert cells[pricey]["rank"] == "worst"

    def test_missing_fact_marked_missing(self, conn) -> None:
        with_steam = self._seed_product(
            conn,
            model_code="STEAM",
            model_name="HasSteam",
            facts=[("steam", 1.0, "트루스팀", "bool")],
        )
        without = self._seed_product(
            conn,
            model_code="NO-STEAM",
            model_name="NoSteam",
            facts=[("wash_capacity_kg", 24.0, None, "kg")],
        )
        m = repo.build_comparison_matrix(conn, [with_steam, without])
        row = next(r for r in m["rows"] if r["canonical_key"] == "steam")
        cells = {c["product_id"]: c for c in row["cells"]}
        assert cells[with_steam]["rank"] == "best"
        assert cells[with_steam]["value_num"] == 1.0
        assert cells[without]["rank"] == "missing"
        assert cells[without]["value_num"] is None

    def test_all_equal_returns_neutral(self, conn) -> None:
        a = self._seed_product(
            conn,
            model_code="EQ-A",
            model_name="A",
            facts=[("wash_capacity_kg", 24.0, None, "kg")],
        )
        b = self._seed_product(
            conn,
            model_code="EQ-B",
            model_name="B",
            facts=[("wash_capacity_kg", 24.0, None, "kg")],
        )
        m = repo.build_comparison_matrix(conn, [a, b])
        row = next(r for r in m["rows"] if r["canonical_key"] == "wash_capacity_kg")
        for c in row["cells"]:
            assert c["rank"] == "neutral"

    def test_products_order_preserved(self, conn) -> None:
        a = self._seed_product(
            conn, model_code="OA", model_name="A",
            facts=[("wash_capacity_kg", 23.0, None, "kg")],
        )
        b = self._seed_product(
            conn, model_code="OB", model_name="B",
            facts=[("wash_capacity_kg", 24.0, None, "kg")],
        )
        c = self._seed_product(
            conn, model_code="OC", model_name="C",
            facts=[("wash_capacity_kg", 25.0, None, "kg")],
        )
        m = repo.build_comparison_matrix(conn, [c, a, b])
        assert [p["product_id"] for p in m["products"]] == [c, a, b]
        row = next(r for r in m["rows"] if r["canonical_key"] == "wash_capacity_kg")
        assert [cell["product_id"] for cell in row["cells"]] == [c, a, b]

    def test_review_summary_attached_per_product(self, conn) -> None:
        a = self._seed_product(
            conn, model_code="RS-A", model_name="A",
            facts=[("wash_capacity_kg", 24.0, None, "kg")],
        )

        class _Stub:
            pros = ["good"]
            cons = ["bad"]
            sentiment_tags = {"세척력": 0.7}
            overall_score = 0.4
            evidence_count = 5
            caveats: list[str] = []
            model_used = "mock"
            input_hash = "h" * 8

        repo.save_review_summary(conn, product_id=a, result=_Stub())
        m = repo.build_comparison_matrix(conn, [a])
        p = m["products"][0]
        assert p["overall_score"] == 0.4
        assert p["sentiment_tags"] == {"세척력": 0.7}


class TestRefreshLog:
    def test_start_and_finalize(self, conn) -> None:
        run_id = repo.start_refresh(
            conn, brands=["lg"], categories=[CategoryId.WASHER]
        )
        assert isinstance(run_id, int) and run_id > 0
        repo.finalize_refresh(conn, run_id, status="success", items_processed=3)
        row = conn.execute(
            "SELECT status, items_processed, finished_at FROM refresh_log WHERE run_id=?",
            (run_id,),
        ).fetchone()
        assert row["status"] == "success"
        assert row["items_processed"] == 3
        assert row["finished_at"] is not None


class TestCostPerRun:
    def test_aggregates_llm_calls_within_run_window(self, conn) -> None:
        run_id = repo.start_refresh(
            conn, brands=["lg"], categories=[CategoryId.WASHER]
        )
        for cost in (0.30, 0.50, 0.40):
            repo.save_llm_call_log(
                conn,
                product_id=None,
                purpose="review_summary",
                model="claude-haiku-4-5",
                input_tokens=100,
                output_tokens=50,
                cost_usd=cost,
                latency_ms=100,
                cache_hit=False,
            )
        repo.finalize_refresh(conn, run_id, status="success", items_processed=3)

        rows = repo.cost_per_run(conn)
        assert len(rows) == 1
        row = rows[0]
        assert row["run_id"] == run_id
        assert row["cost_usd"] == pytest.approx(1.20)
        assert row["calls"] == 3

    def test_in_progress_run_includes_calls_so_far(self, conn) -> None:
        run_id = repo.start_refresh(
            conn, brands=["lg"], categories=[CategoryId.WASHER]
        )
        repo.save_llm_call_log(
            conn,
            product_id=None,
            purpose="review_summary",
            model="claude-haiku-4-5",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.75,
            latency_ms=80,
            cache_hit=False,
        )

        rows = repo.cost_per_run(conn)
        assert len(rows) == 1
        assert rows[0]["run_id"] == run_id
        assert rows[0]["cost_usd"] == pytest.approx(0.75)
        assert rows[0]["finished_at"] is None
