---
template: design
version: 1.2
feature: naver-shopping
project: lg_dash
date: 2026-05-22
author: aaaiiee
status: Draft
---

# naver-shopping Design Document

> **Summary**: `NaverShoppingAdapter` 신설을 위한 구체 설계. JSON 응답 매핑, 인증·rate limit·에러 처리, dual-format 테스트 전략, 리뷰의 명시적 out-of-scope.
>
> **Project**: lg_dash
> **Version**: 0.0.1
> **Author**: aaaiiee
> **Date**: 2026-05-22
> **Status**: Draft
> **Planning Doc**: [naver-shopping.plan.md](../../01-plan/features/naver-shopping.plan.md)

---

## 1. Overview

### 1.1 Design Goals

- 공식 Naver Shopping API (`https://openapi.naver.com/v1/search/shop.json`)를 사용해 안정적·합법적 데이터 수집
- 기존 `SourceAdapter` Protocol 재사용 — 변경 없이 4번째 소스 어댑터로 plug-in
- 리뷰 한계 명시화: 본 어댑터는 product discovery + 메타데이터 전담. 리뷰는 별도 사이클 (`naver-blog-reviews` 후보) 또는 YouTube에 위임
- JSON 응답이라 HTML 파싱 불필요 → 가벼움 + 안정성 ↑

### 1.2 Design Principles

- **HTML 파싱 0**: API JSON 직접 사용 (`bs4`, `crawl4ai` 의존 없음)
- **계약 명시**: Pydantic 모델로 API 응답을 검증 → 스키마 변경 즉시 감지
- **Honest scope**: 리뷰 미제공 사실을 `fetch_reviews`가 빈 iter로 반환 + 주석에 명시
- **Dual-format 패턴**: 합성 JSON 픽스처 (CI) + 라이브 회귀 테스트 1세트 (수동 갱신)

---

## 2. Architecture

### 2.1 Component Diagram

```
┌──────────────────┐    HTTPS+headers   ┌────────────────────────┐
│ NaverShopping    │ ─────────────────▶ │ openapi.naver.com      │
│   Adapter        │ ◀───── JSON ────── │ /v1/search/shop.json   │
└──────────────────┘                    └────────────────────────┘
        │                                          ▲
        │ ProductRef / SpecPayload                 │ X-Naver-Client-Id
        ▼                                          │ X-Naver-Client-Secret
┌──────────────────┐
│ pipeline.crawl   │
│ → repo.*         │
└──────────────────┘
```

### 2.2 Data Flow

```
discover(brand, category)
  └─▶ search_keywords[category]: str (e.g., "LG 세탁기")
        └─▶ GET shop.json?query=...&display=N
              └─▶ items[] → ProductRef[]  (link → URL, productId → external_id)

fetch_specs(ref)
  └─▶ GET shop.json?query=<brand+model>&display=1  (또는 ref.url HEAD에서 ID 재추출)
        └─▶ items[0] → SpecPayload(attributes={brand, maker, lprice, hprice, category4, mallName}, image_urls=[image])

fetch_reviews(ref)
  └─▶ return iter([])  # explicit: Naver Shopping search API does not expose reviews
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `NaverShoppingAdapter` | `HtmlFetcher` (or new `JsonFetcher`) | HTTP transport with headers |
| `NaverShoppingAdapter` | `httpx` (이미 사용 중) | JSON 호출 |
| `NaverShoppingAdapter` | `lg_dash.models` | `ProductRef`, `SpecPayload`, `SourceId.NAVER` |
| `pipeline.run` / `crawl` CLI | `_ADAPTER_FACTORIES` | `--source naver` 라우팅 |

---

## 3. Data Model

### 3.1 Naver Shopping API Response (concrete sample)

```json
{
  "lastBuildDate": "Fri, 22 May 2026 10:00:00 +0900",
  "total": 1234,
  "start": 1,
  "display": 10,
  "items": [
    {
      "title": "<b>LG</b>전자 트롬 오브제컬렉션 워시콤보 FH25ES",
      "link": "https://search.shopping.naver.com/catalog/12345678",
      "image": "https://shopping-phinf.pstatic.net/main_1234567/12345678.jpg",
      "lprice": "1500000",
      "hprice": "1800000",
      "mallName": "네이버",
      "productId": "12345678",
      "productType": "1",
      "brand": "LG전자",
      "maker": "LG전자",
      "category1": "디지털/가전",
      "category2": "생활가전",
      "category3": "세탁기",
      "category4": "드럼세탁기"
    }
  ]
}
```

### 3.2 Pydantic models (신규 — `src/lg_dash/adapters/naver_schemas.py`)

```python
from pydantic import BaseModel

class NaverShopItem(BaseModel):
    title: str         # <b> 포함, unescape 필요
    link: str
    image: str
    lprice: str        # API는 문자열로 반환
    hprice: str        # 일부는 "0" (단일 가격)
    mallName: str
    productId: str
    productType: str   # "1"=일반, "2"=가격비교 등
    brand: str
    maker: str
    category1: str
    category2: str
    category3: str
    category4: str

class NaverShopResponse(BaseModel):
    total: int
    start: int
    display: int
    items: list[NaverShopItem]
```

### 3.3 Mapping: NaverShopItem → ProductRef + SpecPayload

| Naver field | ProductRef field | SpecPayload attribute | canonical_key | Note |
|---|---|---|---|---|
| `productId` | `external_id` | — | — | unique |
| `link` | `url` | — | — | |
| `title` (cleaned) | `model_name` | — | — | `<b>` 태그 제거 |
| `brand` | `brand_id` (mapped) | — | — | "LG전자"→`lg`, "삼성전자"→`samsung`, "위니아"→`winia` |
| `category3` / `category4` | `category_id` (mapped) | — | — | `config/naver_category_map.yaml` |
| `lprice` | — | `price` | `price_krw` | int 변환 (이미 시놋 "출시가" 매핑됨) |
| `hprice` | — | `price_max` (선택) | — | hprice=="0"이면 무시 |
| `image` | — | — | (image_urls[0]) | `SpecPayload.image_urls` |
| `mallName` | — | `mall` | — | 정보용 (canonical 매핑 불필요) |
| `maker` | — | `maker` | — | brand와 다를 수 있음 |
| `productType` | — | — | — | 무시 (운영 시 필터링 용도) |

### 3.4 Category map (`config/naver_category_map.yaml`)

```yaml
mappings:
  washer:
    - 디지털/가전 > 생활가전 > 세탁기 > 드럼세탁기
    - 디지털/가전 > 생활가전 > 세탁기 > 세탁기
  dryer:
    - 디지털/가전 > 생활가전 > 건조기
  top_loader:
    - 디지털/가전 > 생활가전 > 세탁기 > 일반세탁기
    - 디지털/가전 > 생활가전 > 세탁기 > 통돌이
fallback: unknown  # 위 match 없을 때 ProductRef.category_id 강제 X, 호출자가 필터링
```

---

## 4. API Specification

### 4.1 Auth + Rate Limit

| Item | Value |
|---|---|
| Endpoint | `https://openapi.naver.com/v1/search/shop.json` |
| Method | `GET` |
| Headers | `X-Naver-Client-Id`, `X-Naver-Client-Secret` |
| Query params | `query` (UTF-8 URL-encoded), `display` (1-100), `start` (1-1000), `sort` (sim/date/asc/dsc) |
| Rate limit | 10 QPS, 25,000 requests/day (free tier) |
| Error codes | 401 invalid auth, 403 quota exceeded, 429 too many requests, 500 server error |

### 4.2 Retry Policy

| Status | Behavior |
|---|---|
| 200 OK | Parse + return |
| 401 / 403 | Raise immediately (config error, no retry) |
| 429 | Sleep 1s then retry once. If still 429: raise + log to refresh_log |
| 5xx | Sleep 2s then retry once |
| Network timeout | httpx default + retry once |

### 4.3 Fetcher 확장 결정

**Option A** (선택): 기존 `HtmlFetcher.fetch(url) -> str` 사용 + adapter가 JSON 파싱.
- Pros: 변경 없음, rate limit infra (`_HOST_MIN_DELAY`) 재사용
- Cons: 의미적 불일치 (HTML이 아닌 JSON 반환)

**Option B** (대안): `JsonFetcher` Protocol 신설.
- Pros: 타입 명확
- Cons: 다른 어댑터까지 영향, 큰 변경

→ **Option A 채택**. JSON도 결국 `str` body. fetcher.py에 `openapi.naver.com=0.1s` 추가 (10 QPS = 100ms 간격).

---

## 5. Test Plan

### 5.1 Test Scope

| Type | Target | Tool |
|---|---|---|
| Unit (synthetic) | `NaverShopItem` Pydantic validation | pytest |
| Unit (synthetic) | `NaverShoppingAdapter._parse_response` | pytest + JSON fixture |
| Unit (synthetic) | title `<b>` 제거 + html.unescape | parametrize |
| Unit (synthetic) | brand mapping (LG전자→lg) | parametrize |
| Unit (synthetic) | category mapping (4단→lg_dash 1단) | parametrize |
| Integration (mocked) | discover→fetch_specs end-to-end with FileFetcher | pytest |
| Integration (live, optional) | 1 actual API call with real key | manual + opt-in env flag |
| Contract | `NaverShoppingAdapter` satisfies `SourceAdapter` Protocol | existing test |
| Regression | live fixture vs current parser | `test_naver_shopping_live_shape.py` |

### 5.2 Synthetic fixtures

```
tests/fixtures/naver_shopping/
├─ search_lg_washer.json          ← 10 items (LG 세탁기)
├─ search_samsung_dryer.json      ← 10 items (삼성 건조기)
└─ search_empty.json              ← total=0 edge case
```

각 fixture는 실제 API 응답을 anonymize (가격·productId만 변경)한 사본.

### 5.3 Live regression test

`tests/test_naver_shopping_live_shape.py` — `NAVER_CLIENT_ID`가 env에 있을 때만 실행:

```python
@pytest.mark.skipif(not os.environ.get("NAVER_CLIENT_ID"), reason="no API key")
def test_live_search_lg_washer_returns_at_least_5_items():
    ...
```

CI에서는 자동 skip, 로컬·운영 호스트에서만 동작.

---

## 6. Error Handling

### 6.1 Error Code Definition

| Code | Cause | Handling |
|---|---|---|
| 401 | `NAVER_CLIENT_ID/SECRET` 누락 또는 invalid | Raise `AuthenticationError`, RUNBOOK §4 안내 |
| 403 | 일일 quota 초과 | Raise `QuotaExceededError`, refresh_log.status=failed |
| 429 | Rate limit 위반 | 1회 retry. 재실패 시 raise |
| 5xx | Naver 서버 장애 | 1회 retry. 재실패 시 partial success로 마무리 |
| ValidationError | JSON 스키마 불일치 (Naver 변경) | Raise + 셀렉터(?) 갱신 가이드 RUNBOOK 참조 |

### 6.2 Trouble cases for RUNBOOK §4

- 4.6 Naver API `401 Unauthorized` — `.env` 확인
- 4.7 Naver API `403/429` — 일일 한도 초과 또는 burst. ops_view에서 호출 누적 확인
- 4.8 Naver title `<b>` 태그가 model_name에 남음 — `html.unescape + re.sub` 동작 확인

---

## 7. Security Considerations

- [ ] `NAVER_CLIENT_SECRET`은 `.env`에만 (`.gitignore` 적용 확인)
- [ ] 요청 로그에 secret 포함 금지 (`HttpFetcher` 헤더 redact 검토)
- [ ] API 응답에 PII 없음 — anonymize 불필요
- [ ] Rate limit 외부 누출 방지: `openapi.naver.com=100ms` 강제

---

## 8. Implementation Order

| # | File | Lines (est) | Why this order |
|---|------|---|----|
| 1 | `src/lg_dash/models.py` | +2 | `SourceId.NAVER` 추가 — 나머지 모듈이 import |
| 2 | `src/lg_dash/adapters/naver_schemas.py` | ~40 | Pydantic 모델 — adapter가 import |
| 3 | `config/naver_category_map.yaml` | ~15 | adapter가 read |
| 4 | `tests/fixtures/naver_shopping/*.json` | (data) | adapter test의 입력 |
| 5 | `tests/test_naver_shopping_adapter.py` | ~120 | **TDD: RED → GREEN** |
| 6 | `src/lg_dash/adapters/naver_shopping.py` | ~150 | adapter 본체 |
| 7 | `src/lg_dash/adapters/fetcher.py` | +1 (line) | `_HOST_MIN_DELAY["openapi.naver.com"] = 0.1` |
| 8 | `src/lg_dash/pipeline/crawl.py` + `pipeline/run.py` | +2 (lines each) | `_ADAPTER_FACTORIES` 등록 |
| 9 | `.env.example` | +3 lines | Naver 키 + 가이드 코멘트 |
| 10 | `docs/05-ops/RUNBOOK.md` | +30 lines | §4.6~§4.8 트러블슈팅 |

각 file 작성 직후 검증:
- 1~3: import error 없음 확인
- 4~6: TDD cycle (RED → GREEN)
- 7~8: `python -m lg_dash.pipeline.crawl --source naver --help`로 등록 확인
- 9~10: 문서 링크 resolve 확인

---

## 9. Verification Plan

### 9.1 Manual smoke (DoD)

```bash
# 사전: .env에 NAVER_CLIENT_ID, NAVER_CLIENT_SECRET 채움
source .venv/bin/activate

# 1. 단위 테스트 (synthetic, 빠름)
pytest tests/test_naver_shopping_adapter.py -v

# 2. 라이브 회귀 (real API, 5~10s)
pytest tests/test_naver_shopping_live_shape.py -v

# 3. 종단간 파이프라인
python -m lg_dash.pipeline.run --source naver --brand lg --category washer --limit 3 --skip-llm

# 4. DB 확인
sqlite3 storage/db.sqlite \
  "SELECT id, brand_id, category_id, substr(model_name,1,40) FROM product WHERE id IN (SELECT max(id) FROM product GROUP BY brand_id) LIMIT 3;"
sqlite3 storage/db.sqlite \
  "SELECT canonical_key, value_num, source_attr_label FROM spec_fact WHERE product_id = (SELECT max(id) FROM product);"

# 5. 회귀 0
pytest  # 169 + 신규 = 175+ tests, 모두 green
```

### 9.2 Cost check

1 refresh (3 products) = 4 API calls 정도 (search 1 + per-product 3) → 1일 100 refresh = 400 calls, 한도의 1.6%.

### 9.3 Doc-code 정합성

- README 환경 변수 표에 `NAVER_CLIENT_ID/SECRET` 추가 확인
- RUNBOOK §4 트러블슈팅 명령 그대로 동작

---

## 10. Out of Scope (재확인)

| 항목 | 이유 |
|---|---|
| **Reviews from Naver Shopping** | API 응답에 없음. 별도 feature `naver-blog-reviews` 후보로 분리 |
| **Naver 블로그 크롤** | 별도 사이클 |
| **Coupang 재시도** | spike에서 차단 확인됨, deferred 유지 |
| **Naver Smart Store 머천트 API** | 사내 도구에 비현실적 |
| **가격 추이 시계열** | lg_dash 원 plan: "현 시점 가격만" |
| **자동 스케줄링** | 온디맨드만 |

---

## 11. Risks Updated (Plan §5 대비)

| Risk | 변경 |
|---|---|
| Naver API 응답에 리뷰 미포함 | **확정** — 본 design에서 `fetch_reviews`를 빈 iter로 명시 |
| Naver 카테고리 매핑 불일치 | `config/naver_category_map.yaml`로 해결, fallback=unknown |
| `<b>` 태그 → model_name 망침 | `html.unescape + re.sub` (test §5.1 parametrize) |
| 401 (키 누락) | bootstrap.sh가 `.env` 검증 + RUNBOOK §4.6 |
| 429/403 (한도 초과) | ops_view에 일일 호출 누적 (옵션, 우선순위 낮음) |

---

## 12. Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-22 | Initial draft (concrete API spec + Pydantic models + 리뷰 out-of-scope 명시) | aaaiiee |
