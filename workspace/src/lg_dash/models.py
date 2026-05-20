from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SourceId(StrEnum):
    MANUFACTURER = "manufacturer"
    DANAWA = "danawa"
    COUPANG = "coupang"
    YOUTUBE = "youtube"
    MANUAL = "manual"


class CategoryId(StrEnum):
    WASHER = "washer"
    DRYER = "dryer"
    TOP_LOADER = "top_loader"


class MatchedBy(StrEnum):
    RULE = "rule"
    FUZZY = "fuzzy"
    LLM = "llm"
    MANUAL = "manual"


class RefreshStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class Brand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    display: str
    aliases: list[str] = Field(default_factory=list)
    manufacturer_site: str
    search_keywords: dict[str, str] = Field(default_factory=dict)


class Category(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: CategoryId
    display: str
    aliases: list[str] = Field(default_factory=list)


class AttrDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_key: str
    display_ko: str
    unit: str
    data_type: str
    applies_to: list[CategoryId]
    synonyms: list[str] = Field(default_factory=list)
    value_pattern: str | None = None
    enum_map: dict[str, int] | None = None


class SentimentTagDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    display_ko: str
    applies_to: list[CategoryId]


class ProductRef(BaseModel):
    source_id: SourceId
    brand_id: str
    category_id: CategoryId
    external_id: str
    url: str
    model_name: str
    model_code: str | None = None


class SpecPayload(BaseModel):
    product_ref: ProductRef
    attributes: dict[str, Any]
    captured_at: datetime
    image_urls: list[str] = Field(default_factory=list)


class RawReview(BaseModel):
    product_ref: ProductRef
    author_hash: str | None = None
    rating: float | None = None
    text: str
    posted_at: datetime | None = None
    url: str | None = None
    language: str = "ko"


class Product(BaseModel):
    id: int
    brand_id: str
    category_id: CategoryId
    model_name: str
    model_code: str | None = None
    first_seen_at: datetime
    last_refreshed_at: datetime | None = None
    is_active: bool = True


class SpecFact(BaseModel):
    product_id: int
    canonical_key: str
    value_num: float | None = None
    value_text: str | None = None
    unit: str
    source_id: SourceId
    source_attr_label: str | None = None
    confidence: float
    matched_by: MatchedBy
    captured_at: datetime


class ReviewSummary(BaseModel):
    product_id: int
    pros: list[str]
    cons: list[str]
    sentiment_tags: dict[str, float]
    overall_score: float
    evidence_count: int
    caveats: list[str] = Field(default_factory=list)
    generated_at: datetime
    model_used: str
    input_hash: str


class ProductImage(BaseModel):
    id: int | None = None
    product_id: int
    source_id: SourceId
    idx: int
    original_url: str
    local_path: str | None = None
    width: int | None = None
    height: int | None = None
    bytes: int | None = None
    is_primary: bool = False
    fetched_at: datetime | None = None
    status: str = "ok"


class RefreshLog(BaseModel):
    run_id: int | None = None
    started_at: datetime
    finished_at: datetime | None = None
    scope_brands: list[str] = Field(default_factory=list)
    scope_categories: list[CategoryId] = Field(default_factory=list)
    scope_product_ids: list[int] = Field(default_factory=list)
    status: RefreshStatus = RefreshStatus.PENDING
    items_processed: int = 0
    error_text: str | None = None


@dataclass
class NormalizedFact:
    canonical_key: str
    value_num: float | None
    value_text: str | None
    unit: str
    source_attr_label: str
    confidence: float
    matched_by: MatchedBy


class LlmCallLog(BaseModel):
    id: int | None = None
    product_id: int | None = None
    purpose: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    cache_hit: bool = False
    created_at: datetime
