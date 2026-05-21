---
template: plan
version: 1.2
feature: naver-shopping
project: lg_dash
date: 2026-05-22
author: aaaiiee
status: Draft
---

# naver-shopping Planning Document

> **Summary**: 차단된 Coupang 어댑터를 대체하기 위해 Naver Shopping 공식 API를 사용하는 신규 어댑터 도입. 제품 discovery + 메타데이터 + (가능 시) 리뷰 커버리지 확보.
>
> **Project**: lg_dash
> **Version**: 0.0.1
> **Author**: aaaiiee
> **Date**: 2026-05-22
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | Coupang Akamai 봇 방어로 라이브 크롤 불가 (coupang-live spike에서 확인됨). 다나와는 리뷰 AJAX 차단. 결과적으로 lg_dash의 리뷰 소스가 YouTube 한 곳뿐 — LLM 요약 품질을 위한 다양성 부족. |
| **Solution** | Naver Shopping 검색 API (developers.naver.com, 25k 요청/일 무료, 공식)를 사용하는 `NaverShoppingAdapter` 신설. JSON 응답이라 HTML 파싱·헤드리스 브라우저 불필요. 리뷰는 별도 spike로 가능성 확인. |
| **Function/UX Effect** | 추가 1 소스에서 LG/삼성/위니아 가전 제품 메타데이터 + 가격 안정적 수집. YouTube와 함께 리뷰 다양성 확보 (가능 시 Naver 블로그 리뷰까지). 비교 뷰의 "출처별 가격" 컬럼이 의미 있어짐. |
| **Core Value** | 외부 차단·ToS 충돌 없는 공식 데이터 파이프라인. Coupang 제외에 따른 가치 손실 회복. 25k 요청/일은 ~100 제품 운영 비용에 충분 (제품당 1 search + 1 detail = 200 calls/refresh). |

---

## 1. Overview

### 1.1 Purpose

Coupang을 대체할 안정적인 한국 쇼핑·리뷰 소스로 Naver Shopping을 도입하고, lg_dash의 리뷰 다양성을 회복한다.

### 1.2 Background

- **coupang-live**가 Akamai 차단으로 archive됨 (deferred 상태, infra blocker)
- 현재 lg_dash 소스 현황:
  - manufacturer: 라이브 적합화 미실시 (catalog HTML만 fetcher)
  - danawa: 라이브 ✓ but **리뷰 AJAX 차단**
  - coupang: 라이브 ✗ (Akamai)
  - youtube: 라이브 적합화 미실시 (구현체는 있음)
- 리뷰 적재량: 다나와 0, 쿠팡 0, manufacturer 0, youtube 미검증 → 사실상 0
- review_summary가 작동하려면 리뷰 ≥20건 필요 (`pipeline.llm_analyze.MIN_REVIEW_LEN`)
- Naver Shopping API는 무료·공식이라 가장 낮은 위험-보상 비율

### 1.3 Related Documents

- coupang-live spike: [docs/archive/2026-05/coupang-live/coupang-live.spike.md](../../archive/2026-05/coupang-live/coupang-live.spike.md)
- lg_dash 완성 보고서: [docs/04-report/lg_dash-completion-report.md](../../04-report/lg_dash-completion-report.md)
- Naver API docs: https://developers.naver.com/docs/serviceapi/search/shopping/shopping.md

---

## 2. Scope

### 2.1 In Scope

- [ ] **Naver API 등록 + 키 발급** (수동, 사용자) — `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET`
- [ ] **`SourceId.NAVER` 추가** + 모델 enum 확장
- [ ] **migrations/0003_naver.sql** — `SourceId` enum 값 확장에 따른 schema_migrations 항목 (만약 enum CHECK 제약 있다면)
- [ ] **`NaverShoppingAdapter`** — `SourceAdapter` Protocol 충족 (`discover` / `fetch_specs` / `fetch_reviews`)
- [ ] **JSON 응답 파서** — title/lprice/hprice/mallName/brand/maker/category 추출
- [ ] **HTML clean** — Naver API title은 `<b>` 태그 포함하므로 unescape 필요
- [ ] **`config/brands.yaml`** — search_keywords가 Naver 검색에 맞는지 점검
- [ ] **테스트**: synthetic JSON 픽스처 + 라이브 회귀 테스트 (`tests/test_naver_shopping_adapter.py`)
- [ ] **Spike (별도 1h)** — Naver Shopping 제품 상세 페이지에서 리뷰 추출 가능성 검토. blocked 시 fetch_reviews는 빈 iterator 반환 + 다음 단계로 위임
- [ ] **pipeline.run 확장** — `--source naver` 지원
- [ ] **README + RUNBOOK 업데이트** — Naver API 키 설정 + 일일 25k 한도 모니터링

### 2.2 Out of Scope

- Naver 블로그 리뷰 크롤링 (별도 feature `naver-blog-reviews` 검토)
- Naver Smart Store SellerCenter API (머천트만)
- Coupang 재시도 (deferred 상태 유지)
- 가격 변동 시계열
- 다른 어댑터(manufacturer, youtube) 라이브 적합화

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | Naver API 키 → `.env.example` 추가 (`NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`) | High | Pending |
| FR-02 | `SourceId.NAVER` 모델 enum 추가 | High | Pending |
| FR-03 | `NaverShoppingAdapter.discover(brand, category)` — 검색 결과에서 ProductRef 추출 | High | Pending |
| FR-04 | `NaverShoppingAdapter.fetch_specs(ref)` — 제품 메타 + 카테고리 + 가격을 SpecPayload로 | High | Pending |
| FR-05 | `NaverShoppingAdapter.fetch_reviews(ref, since=None)` — 리뷰 spike 결과에 따라 구현 또는 빈 iter | Medium | Pending |
| FR-06 | 합성 픽스처 (JSON) + 라이브 회귀 테스트 | High | Pending |
| FR-07 | `attr_dictionary.yaml`에 Naver 응답 라벨 시놋 보강 (`brand`/`maker`/`category4` 등) | Medium | Pending |
| FR-08 | Rate limit: Naver API는 초당 10건 제한 → fetcher에 명시 (혹은 운영 가이드) | Medium | Pending |
| FR-09 | `pipeline.run` CLI에 `--source naver` 추가 + `_ADAPTER_FACTORIES`에 등록 | High | Pending |
| FR-10 | RUNBOOK §4에 트러블슈팅: 401 (키 누락), 429 (한도 초과), 200 + 빈 결과 | Medium | Pending |
| FR-11 | Naver title `<b>` HTML escape 제거 | Low | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement |
|----------|----------|-------------|
| Performance | 1 제품 메타 fetch ≤2s (network bound) | timing log |
| Reliability | 401/429 시 명확한 에러 + retry 정책 | unit test |
| Quota | 일일 25,000 요청 한도 < 50% 사용 (안전 마진) | ops_view |
| Test coverage | NaverShoppingAdapter 단위·통합 테스트 ≥5건 | pytest |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] `.env.example`에 Naver 키 추가 + README/RUNBOOK 문서화
- [ ] `NaverShoppingAdapter` 구현 + Protocol 충족
- [ ] 합성 JSON 픽스처 1세트 (검색 + 제품 detail-or-equivalent)
- [ ] 라이브 회귀 테스트 통과 (실제 API 호출 1회)
- [ ] `pipeline.run --source naver --brand lg --category washer --limit 3 --skip-llm` 종단간 성공
- [ ] product 3행 + spec_raw 3건 적재 확인
- [ ] 전체 pytest 회귀 0 (169+ tests still green)
- [ ] 리뷰 spike 결과 문서화 (가능 vs 차단 + 차후 액션)

### 4.2 Quality Criteria

- [ ] confidence<0.7 spec_fact 비율 ≤30% (lg_dash 기존 기준)
- [ ] Naver API 일일 사용량 모니터링 UI (ops_view) — 선택, 우선순위 낮음
- [ ] zero new ruff lint warnings

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Naver API 응답에 리뷰 미포함 | High | High | spike로 미리 확인. 빈 iter 반환 + 별도 `naver-blog-reviews` feature로 분리 |
| Naver shopping product detail 페이지도 Akamai 등 봇 방어 | Medium | Medium | search API JSON만 사용, detail 페이지 크롤 안 함 (불필요) |
| 일일 25k 한도 초과 (~100 제품 × 200 refresh/day = 20k OK) | Low | Low | ops_view에 누적 API 호출 카운터 추가 (선택) |
| Naver title의 `<b>` 태그가 normalize 망침 | Low | Low | `html.unescape` + `re.sub(r"<[^>]+>", "", ...)` |
| Naver 카테고리 분류가 LG_Dash 카테고리(washer/dryer/top_loader)와 안 맞음 | Medium | Medium | `category1` ~ `category4` 매핑 dict 추가 (config) |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Selected |
|-------|:--------:|
| Starter | ☑ |
| Dynamic | ☐ |
| Enterprise | ☐ |

→ lg_dash 본체와 동일.

### 6.2 Key Architectural Decisions

| Decision | Selected | Rationale |
|----------|----------|-----------|
| Fetcher 종류 | httpx (현재 `HtmlFetcher`) + 응답 타입을 JSON으로 처리 | 헤드리스 브라우저 불필요 (공식 API) |
| 인증 | HTTP headers `X-Naver-Client-Id` + `X-Naver-Client-Secret` | API spec 그대로 |
| 응답 파싱 | JSON 직접 (Pydantic 모델로 검증 권장) | HTML보다 안정적 |
| 리뷰 처리 | spike 결과에 따라 분기 — 빈 iter 또는 별도 feature | YAGNI |
| 카테고리 매핑 | `config/naver_category_map.yaml` (신규) | Naver 4단 → LG_Dash 카테고리 1단 |

### 6.3 Folder Structure

```
workspace/
├─ src/lg_dash/
│   ├─ adapters/
│   │   ├─ naver_shopping.py    ← 신규
│   │   └─ fetcher.py            ← JsonFetcher protocol 추가 검토
│   └─ models.py                 ← SourceId.NAVER 추가
├─ config/
│   └─ naver_category_map.yaml   ← 신규 (옵션)
├─ tests/
│   ├─ fixtures/naver_shopping/  ← 신규
│   │   ├─ search_lg_washer.json
│   │   └─ search_samsung_dryer.json
│   └─ test_naver_shopping_adapter.py ← 신규
```

---

## 7. Convention Prerequisites

### 7.1 Existing Project Conventions

- [x] `httpx` 이미 사용 중 (fetcher.py)
- [x] Adapter Protocol 패턴 (`SourceAdapter`)
- [x] dual-format 패턴 (합성 + 라이브)
- [x] `.env.example` + RUNBOOK 패턴 (deploy-guide 완료)

### 7.2 New Conventions

| Item | Decision |
|------|----------|
| Naver 카테고리 매핑 | `config/naver_category_map.yaml` (없으면 fallback `category1`) |
| API 응답 캐싱 | 미적용 (현 시점 운영 빈도가 낮아 불필요) |
| 401/429 에러 처리 | 즉시 raise + RUNBOOK §4 안내 |

### 7.3 Environment Variables Needed

| Variable | Purpose | Default | To Document |
|----------|---------|---------|:-----------:|
| `NAVER_CLIENT_ID` | Naver Shopping API client ID | (none, required for naver source) | ☑ |
| `NAVER_CLIENT_SECRET` | Naver Shopping API secret | (none) | ☑ |

---

## 8. Next Steps

1. [ ] `/pdca design naver-shopping` — JSON 응답 스키마 + adapter outline + 리뷰 spike 계획 확정
2. [ ] (Design 내) 리뷰 spike 1h — Naver 제품 detail 페이지 또는 별 API 가능성 확인
3. [ ] `/pdca do naver-shopping` — adapter 구현 + 픽스처 + 회귀 테스트
4. [ ] `/pdca analyze naver-shopping`
5. [ ] `/pdca report naver-shopping`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-22 | Initial draft (coupang-live spike 결과 후 대체 사이클로 시작) | aaaiiee |
