from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from lg_dash.llm.client import LlmClient, LlmResponse
from lg_dash.models import (
    Brand,
    Category,
    CategoryId,
    ProductRef,
    RawReview,
    SourceId,
)
from lg_dash.pipeline.llm_analyze import (
    AnalysisResult,
    Analyzer,
    analyze_and_persist,
    load_sentiment_tags,
)
from lg_dash.storage import repo
from lg_dash.storage.db import connect, migrate

CONFIG_DIR = Path(__file__).parent.parent / "config"


class MockLlmClient:
    model: str = "mock-haiku"

    def __init__(
        self,
        responses: list[str] | str,
        *,
        input_tokens: int = 1500,
        output_tokens: int = 250,
    ) -> None:
        if isinstance(responses, str):
            responses = [responses]
        self._responses = list(responses)
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.calls: list[tuple[str, str]] = []

    def complete(self, *, system: str, user: str) -> LlmResponse:
        self.calls.append((system, user))
        if not self._responses:
            raise RuntimeError("no mock responses left")
        return LlmResponse(
            text=self._responses.pop(0),
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            latency_ms=42,
            cache_hit=False,
        )


def _valid_response_json(evidence: int = 3) -> str:
    return json.dumps(
        {
            "pros": ["세척력 좋음", "디자인 만족", "스팀 살균 우수"],
            "cons": ["탈수 시 소음", "AS 대기 시간"],
            "sentiment_tags": {
                "세척력": 0.7,
                "소음": -0.4,
                "디자인": 0.6,
                "AS": -0.2,
            },
            "overall_score": 0.35,
            "evidence_count": evidence,
            "caveats": [],
        },
        ensure_ascii=False,
    )


def _ref(product_id: int = 1) -> ProductRef:
    return ProductRef(
        source_id=SourceId.DANAWA,
        brand_id="lg",
        category_id=CategoryId.WASHER,
        external_id=str(product_id),
        url=f"https://prod.danawa.com/info/?pcode={product_id}",
        model_name="LG 트롬 워시콤보 WK24WS",
        model_code="WK24WS",
    )


def _review(text: str, *, rating: float = 4.0, source: SourceId = SourceId.DANAWA) -> RawReview:
    return RawReview(
        product_ref=_ref(),
        rating=rating,
        text=text,
        posted_at=datetime(2026, 5, 1),
    )


@pytest.fixture(scope="module")
def sentiment_tags():
    return load_sentiment_tags(CONFIG_DIR / "sentiment_tags.yaml")


def _make_analyzer(client: MockLlmClient, sentiment_tags, max_reviews: int = 80) -> Analyzer:
    return Analyzer(
        llm_client=client,
        sentiment_tags=sentiment_tags,
        max_reviews=max_reviews,
    )


class TestLlmClientProtocol:
    def test_runtime_checkable(self) -> None:
        assert getattr(LlmClient, "_is_runtime_protocol", False) is True

    def test_mock_satisfies_protocol(self) -> None:
        client = MockLlmClient([_valid_response_json()])
        assert isinstance(client, LlmClient)


class TestReviewFiltering:
    def test_short_reviews_excluded(self, sentiment_tags) -> None:
        client = MockLlmClient([_valid_response_json()])
        analyzer = _make_analyzer(client, sentiment_tags)
        reviews = [
            _review("최고"),
            _review("좋아요"),
            _review("정말 만족스럽고 세척력 우수합니다. 추천!"),
            _review("스팀 기능 마음에 들고 디자인이 깔끔해서 좋네요"),
        ]
        filtered = analyzer.filter_reviews(reviews)
        assert len(filtered) == 2
        for r in filtered:
            assert len(r.text) >= 20

    def test_duplicate_text_removed(self, sentiment_tags) -> None:
        client = MockLlmClient([_valid_response_json()])
        analyzer = _make_analyzer(client, sentiment_tags)
        same = "세척력 좋고 디자인도 만족합니다. 가격 대비 만족."
        reviews = [_review(same), _review(same), _review("탈수 소음이 약간 큰 편이지만 만족합니다.")]
        filtered = analyzer.filter_reviews(reviews)
        assert len(filtered) == 2


class TestSampling:
    def test_caps_at_max_reviews(self, sentiment_tags) -> None:
        client = MockLlmClient([_valid_response_json()])
        analyzer = _make_analyzer(client, sentiment_tags, max_reviews=5)
        reviews = [
            _review(f"리뷰 번호 {i} 세척력 좋고 디자인 만족 좋습니다") for i in range(20)
        ]
        sampled = analyzer.sample_reviews(analyzer.filter_reviews(reviews))
        assert len(sampled) == 5


class TestAnalyze:
    def test_returns_analysis_result_with_valid_json(self, sentiment_tags) -> None:
        client = MockLlmClient([_valid_response_json()])
        analyzer = _make_analyzer(client, sentiment_tags)
        reviews = [
            _review("세척력 정말 좋습니다 강력 추천합니다 대만족이에요"),
            _review("탈수 소음이 약간 큰 편이지만 옷이 잘 빨립니다"),
            _review("디자인이 인테리어와 잘 어울리고 스팀 살균 만족"),
        ]
        result = analyzer.analyze(
            model_name="LG 트롬 워시콤보 WK24WS",
            brand_display="LG전자",
            category=CategoryId.WASHER,
            reviews=reviews,
        )
        assert isinstance(result, AnalysisResult)
        assert len(result.pros) >= 1
        assert len(result.cons) >= 1
        assert -1.0 <= result.overall_score <= 1.0
        assert result.model_used == "mock-haiku"
        assert result.input_tokens == 1500
        assert result.output_tokens == 250
        assert result.cost_usd > 0

    def test_invalid_json_triggers_retry(self, sentiment_tags) -> None:
        client = MockLlmClient(["not valid json", _valid_response_json()])
        analyzer = _make_analyzer(client, sentiment_tags)
        reviews = [_review("세척력 정말 좋습니다 강력 추천합니다")]
        result = analyzer.analyze(
            model_name="LG 트롬",
            brand_display="LG전자",
            category=CategoryId.WASHER,
            reviews=reviews,
        )
        assert isinstance(result, AnalysisResult)
        assert len(client.calls) == 2

    def test_invalid_json_after_retry_raises(self, sentiment_tags) -> None:
        client = MockLlmClient(["bad", "still bad"])
        analyzer = _make_analyzer(client, sentiment_tags)
        with pytest.raises(ValueError):
            analyzer.analyze(
                model_name="LG 트롬",
                brand_display="LG전자",
                category=CategoryId.WASHER,
                reviews=[_review("세척력 정말 좋습니다 강력 추천합니다")],
            )

    def test_input_hash_is_deterministic(self, sentiment_tags) -> None:
        reviews = [_review("세척력 좋고 디자인 만족합니다 정말 추천드립니다")]
        c1 = MockLlmClient([_valid_response_json()])
        a1 = _make_analyzer(c1, sentiment_tags)
        r1 = a1.analyze(
            model_name="LG 트롬",
            brand_display="LG전자",
            category=CategoryId.WASHER,
            reviews=reviews,
        )
        c2 = MockLlmClient([_valid_response_json()])
        a2 = _make_analyzer(c2, sentiment_tags)
        r2 = a2.analyze(
            model_name="LG 트롬",
            brand_display="LG전자",
            category=CategoryId.WASHER,
            reviews=reviews,
        )
        assert r1.input_hash == r2.input_hash


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
    ref = _ref()
    product_id = repo.upsert_product(conn, ref)
    repo.upsert_product_source_ref(conn, product_id, ref)
    reviews = [
        _review("세척력 정말 좋고 스팀 살균이 확실히 됩니다 대만족"),
        _review("탈수 시 소음이 큰 편이지만 옷은 잘 빨립니다"),
        _review("디자인 만족하고 AS 빠른 대응 좋습니다"),
    ]
    repo.save_raw_reviews(conn, product_id, reviews)
    conn.close()
    return db


class TestAnalyzeAndPersist:
    def test_saves_review_summary_row(
        self, seeded_db: Path, sentiment_tags
    ) -> None:
        client = MockLlmClient([_valid_response_json(evidence=3)])
        analyzer = _make_analyzer(client, sentiment_tags)
        conn = connect(seeded_db)
        try:
            result = analyze_and_persist(conn, product_id=1, analyzer=analyzer)
            assert result is not None
            row = conn.execute(
                "SELECT pros_json, sentiment_tags_json, overall_score, status, "
                "model_used, input_hash FROM review_summary WHERE product_id=1"
            ).fetchone()
            assert row is not None
            assert row["status"] == "ok"
            assert row["model_used"] == "mock-haiku"
            assert row["overall_score"] == pytest.approx(0.35)
            pros = json.loads(row["pros_json"])
            tags = json.loads(row["sentiment_tags_json"])
            assert "세척력 좋음" in pros
            assert tags["세척력"] == pytest.approx(0.7)
        finally:
            conn.close()

    def test_records_llm_call_log(
        self, seeded_db: Path, sentiment_tags
    ) -> None:
        client = MockLlmClient([_valid_response_json()])
        analyzer = _make_analyzer(client, sentiment_tags)
        conn = connect(seeded_db)
        try:
            analyze_and_persist(conn, product_id=1, analyzer=analyzer)
            rows = conn.execute(
                "SELECT model, input_tokens, output_tokens, cost_usd, cache_hit "
                "FROM llm_call_log ORDER BY id"
            ).fetchall()
            assert len(rows) == 1
            assert rows[0]["model"] == "mock-haiku"
            assert rows[0]["input_tokens"] == 1500
            assert rows[0]["output_tokens"] == 250
            assert rows[0]["cost_usd"] > 0
            assert rows[0]["cache_hit"] == 0
        finally:
            conn.close()

    def test_rerun_with_same_input_hash_is_cache_hit(
        self, seeded_db: Path, sentiment_tags
    ) -> None:
        client = MockLlmClient([_valid_response_json()])
        analyzer = _make_analyzer(client, sentiment_tags)
        conn = connect(seeded_db)
        try:
            analyze_and_persist(conn, product_id=1, analyzer=analyzer)
            assert len(client.calls) == 1
            analyze_and_persist(conn, product_id=1, analyzer=analyzer)
            assert len(client.calls) == 1
            rows = conn.execute("SELECT cache_hit FROM llm_call_log ORDER BY id").fetchall()
            assert len(rows) == 2
            assert rows[1]["cache_hit"] == 1
        finally:
            conn.close()
