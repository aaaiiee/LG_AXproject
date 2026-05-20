from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from lg_dash.llm.client import AnthropicClient, LlmClient, calculate_cost
from lg_dash.models import (
    CategoryId,
    RawReview,
    SentimentTagDefinition,
    SourceId,
)
from lg_dash.storage import repo
from lg_dash.storage.db import connect, db_path

__all__ = [
    "AnalysisResult",
    "Analyzer",
    "analyze_and_persist",
    "load_sentiment_tags",
]


MIN_REVIEW_LEN = 20


@dataclass
class AnalysisResult:
    pros: list[str]
    cons: list[str]
    sentiment_tags: dict[str, float]
    overall_score: float
    evidence_count: int
    caveats: list[str]
    input_hash: str
    model_used: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cache_hit: bool
    cost_usd: float


def load_sentiment_tags(path: Path) -> list[SentimentTagDefinition]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [SentimentTagDefinition(**item) for item in data["tags"]]


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _extract_json(text: str) -> dict:
    text = text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is None:
        raise ValueError("no JSON object found in LLM response")
    return json.loads(match.group(0))


SYSTEM_TEMPLATE = """당신은 한국 생활가전 제품 리뷰 분석가입니다.
주어진 리뷰들을 분석해 구매 결정에 도움이 되는 형식으로 요약하세요.

규칙:
- 출력은 JSON만 (마크다운 코드 펜스 없이).
- pros/cons는 각 3~7개, 사용자 표현을 살리되 간결하게.
- sentiment_tags는 아래 어휘 안에서만 사용 (이 카테고리에 적용 가능한 태그):
  {tag_vocabulary}
- 점수 범위: 각 태그 -1.0 ~ +1.0, overall_score -1.0 ~ +1.0.
- 광고성·중복 의심 시 caveats에 명시.

응답 스키마:
{{
  "pros": ["..."],
  "cons": ["..."],
  "sentiment_tags": {{"세척력": 0.7, ...}},
  "overall_score": 0.0,
  "evidence_count": <리뷰 개수>,
  "caveats": []
}}"""

USER_TEMPLATE = """제품: {brand} {model_name}
카테고리: {category}

리뷰:
{reviews_json}"""


class Analyzer:
    def __init__(
        self,
        *,
        llm_client: LlmClient,
        sentiment_tags: list[SentimentTagDefinition],
        max_reviews: int = 80,
        max_retries: int = 1,
    ) -> None:
        self.llm_client = llm_client
        self.sentiment_tags = sentiment_tags
        self.max_reviews = max_reviews
        self.max_retries = max_retries

    def filter_reviews(self, reviews: Iterable[RawReview]) -> list[RawReview]:
        seen: set[str] = set()
        result: list[RawReview] = []
        for r in reviews:
            text = r.text.strip()
            if len(text) < MIN_REVIEW_LEN:
                continue
            h = _text_hash(text)
            if h in seen:
                continue
            seen.add(h)
            result.append(r)
        return result

    def sample_reviews(self, reviews: list[RawReview]) -> list[RawReview]:
        if len(reviews) <= self.max_reviews:
            return reviews
        return reviews[: self.max_reviews]

    def analyze(
        self,
        *,
        model_name: str,
        brand_display: str,
        category: CategoryId,
        reviews: list[RawReview],
    ) -> AnalysisResult:
        filtered = self.filter_reviews(reviews)
        sampled = self.sample_reviews(filtered)
        if not sampled:
            raise ValueError("no reviews after filtering")

        system_prompt = self._render_system(category)
        user_prompt = self._render_user(brand_display, model_name, category, sampled)
        input_hash = self._input_hash(model_name, sampled)

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            response = self.llm_client.complete(system=system_prompt, user=user_prompt)
            try:
                data = _extract_json(response.text)
            except (ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                continue
            self._validate(data)
            return AnalysisResult(
                pros=list(data["pros"]),
                cons=list(data["cons"]),
                sentiment_tags=self._filter_tags(data["sentiment_tags"], category),
                overall_score=float(data["overall_score"]),
                evidence_count=int(data.get("evidence_count", len(sampled))),
                caveats=list(data.get("caveats", [])),
                input_hash=input_hash,
                model_used=self.llm_client.model,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                latency_ms=response.latency_ms,
                cache_hit=response.cache_hit,
                cost_usd=calculate_cost(
                    self.llm_client.model, response.input_tokens, response.output_tokens
                ),
            )
        raise ValueError(f"LLM response did not parse after retries: {last_error}")

    def _render_system(self, category: CategoryId) -> str:
        tag_vocab = ", ".join(
            t.display_ko for t in self.sentiment_tags if category in t.applies_to
        )
        return SYSTEM_TEMPLATE.format(tag_vocabulary=tag_vocab)

    def _render_user(
        self,
        brand_display: str,
        model_name: str,
        category: CategoryId,
        reviews: list[RawReview],
    ) -> str:
        review_data = [
            {
                "source": r.product_ref.source_id.value,
                "rating": r.rating,
                "text": r.text,
            }
            for r in reviews
        ]
        return USER_TEMPLATE.format(
            brand=brand_display,
            model_name=model_name,
            category=category.value,
            reviews_json=json.dumps(review_data, ensure_ascii=False, indent=2),
        )

    def _input_hash(self, model_name: str, reviews: list[RawReview]) -> str:
        hashes = sorted(_text_hash(r.text) for r in reviews)
        payload = f"{self.llm_client.model}|{model_name}|" + "|".join(hashes)
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    def _validate(self, data: dict) -> None:
        for key in ("pros", "cons", "sentiment_tags", "overall_score"):
            if key not in data:
                raise ValueError(f"missing required key: {key}")
        if not isinstance(data["pros"], list) or not isinstance(data["cons"], list):
            raise ValueError("pros/cons must be lists")
        if not isinstance(data["sentiment_tags"], dict):
            raise ValueError("sentiment_tags must be a dict")
        score = float(data["overall_score"])
        if not -1.0 <= score <= 1.0:
            raise ValueError("overall_score out of range")

    def _filter_tags(
        self, tags: dict[str, float], category: CategoryId
    ) -> dict[str, float]:
        allowed = {t.display_ko for t in self.sentiment_tags if category in t.applies_to}
        return {k: float(v) for k, v in tags.items() if k in allowed}


def _select_product_context(conn: sqlite3.Connection, product_id: int):
    row = conn.execute(
        """
        SELECT p.brand_id, p.category_id, p.model_name,
               b.display AS brand_display
        FROM product p JOIN brand b ON p.brand_id = b.id
        WHERE p.id = ?
        """,
        (product_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"product not found: {product_id}")
    return row


def _select_reviews(conn: sqlite3.Connection, product_id: int) -> list[RawReview]:
    rows = conn.execute(
        """
        SELECT product_id, source_id, author_hash, rating, text, posted_at,
               url, language
        FROM raw_review WHERE product_id = ?
        """,
        (product_id,),
    ).fetchall()
    result: list[RawReview] = []
    product_ctx = conn.execute(
        "SELECT brand_id, category_id FROM product WHERE id = ?", (product_id,)
    ).fetchone()
    for r in rows:
        ref = _stub_ref(
            source_id=SourceId(r["source_id"]),
            brand_id=product_ctx["brand_id"],
            category_id=CategoryId(product_ctx["category_id"]),
        )
        posted_at = (
            datetime.fromisoformat(r["posted_at"]) if r["posted_at"] else None
        )
        result.append(
            RawReview(
                product_ref=ref,
                author_hash=r["author_hash"],
                rating=r["rating"],
                text=r["text"],
                posted_at=posted_at,
                url=r["url"],
                language=r["language"],
            )
        )
    return result


def _stub_ref(*, source_id: SourceId, brand_id: str, category_id: CategoryId):
    from lg_dash.models import ProductRef

    return ProductRef(
        source_id=source_id,
        brand_id=brand_id,
        category_id=category_id,
        external_id="",
        url="",
        model_name="",
    )


def _existing_input_hash(conn: sqlite3.Connection, product_id: int) -> str | None:
    row = conn.execute(
        "SELECT input_hash FROM review_summary WHERE product_id = ? AND status='ok'",
        (product_id,),
    ).fetchone()
    return row["input_hash"] if row else None


def analyze_and_persist(
    conn: sqlite3.Connection, *, product_id: int, analyzer: Analyzer
) -> AnalysisResult | None:
    ctx = _select_product_context(conn, product_id)
    reviews = _select_reviews(conn, product_id)
    if not reviews:
        return None

    filtered = analyzer.filter_reviews(reviews)
    sampled = analyzer.sample_reviews(filtered)
    if not sampled:
        return None
    candidate_hash = analyzer._input_hash(ctx["model_name"], sampled)
    cached_hash = _existing_input_hash(conn, product_id)
    if cached_hash == candidate_hash:
        repo.save_llm_call_log(
            conn,
            product_id=product_id,
            purpose="review_summary",
            model=analyzer.llm_client.model,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            latency_ms=0,
            cache_hit=True,
        )
        return None

    result = analyzer.analyze(
        model_name=ctx["model_name"],
        brand_display=ctx["brand_display"],
        category=CategoryId(ctx["category_id"]),
        reviews=reviews,
    )
    repo.save_review_summary(conn, product_id=product_id, result=result)
    repo.save_llm_call_log(
        conn,
        product_id=product_id,
        purpose="review_summary",
        model=result.model_used,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
        cache_hit=result.cache_hit,
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LLM-based review summary + sentiment analysis"
    )
    parser.add_argument("--product-id", type=int)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--config-dir", type=Path, default=Path("config"))
    args = parser.parse_args()
    if not (args.all or args.product_id):
        parser.error("either --product-id or --all is required")

    client = AnthropicClient()
    analyzer = Analyzer(
        llm_client=client,
        sentiment_tags=load_sentiment_tags(args.config_dir / "sentiment_tags.yaml"),
    )
    conn = connect(db_path())
    try:
        if args.all:
            ids = [r["id"] for r in conn.execute("SELECT id FROM product ORDER BY id")]
        else:
            ids = [args.product_id]
        for pid in ids:
            result = analyze_and_persist(conn, product_id=pid, analyzer=analyzer)
            if result is None:
                print(f"product_id={pid} skipped (cache_hit or no_reviews)")
            else:
                print(
                    f"product_id={pid} pros={len(result.pros)} cons={len(result.cons)} "
                    f"score={result.overall_score:.2f} cost=${result.cost_usd:.4f}"
                )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
