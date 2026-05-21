---
template: plan
version: 1.2
feature: coupang-live
project: lg_dash
date: 2026-05-22
author: aaaiiee
status: Draft
---

# coupang-live Planning Document

> **Summary**: 쿠팡 라이브 사이트 적합화. 현재 `CoupangAdapter`는 synthetic HTML 픽스처에서만 동작 — 실제 쿠팡(SPA, JS 렌더링)에 대해 종단간 크롤 가능하게 한다.
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
| **Problem** | 현재 `CoupangAdapter`는 BeautifulSoup만 사용해 synthetic 픽스처에서만 동작. 라이브 쿠팡은 SPA + 동적 JS 렌더링이라 첫 HTML 응답에는 제품 데이터가 비어 있어 0건이 잡힘. 다나와에서 못 가져오는 리뷰 소스가 빠져 lg_dash의 리뷰 커버리지가 부족함. |
| **Solution** | crawl4ai (이미 설치 완료)를 Coupang 전용 헤드리스 fetcher로 도입. 1~2시간 research spike로 라이브 1 페이지 가져오기 가능성 확인 → 가능 시 본 구현. 안 되면 fallback 옵션(모바일 endpoint, 또는 deferred) 결정. |
| **Function/UX Effect** | 쿠팡에서 제품 검색·스펙·리뷰가 실제 데이터로 수집 → review_summary 품질 향상 (리뷰 ≥80건/제품). 운영자가 다나와+쿠팡 두 소스의 리뷰를 비교 가능. |
| **Core Value** | 리뷰 기반 의사결정의 신뢰도 확보. 현재 다나와 robots.txt 차단으로 리뷰 0건인 상태에서 쿠팡이 1차 리뷰 소스가 되어 LLM 요약이 의미 있는 결과 산출. |

---

## 1. Overview

### 1.1 Purpose

쿠팡 실제 사이트에서 제품 discover/spec/review를 종단간 수집할 수 있도록 `CoupangAdapter`를 라이브 SPA에 맞춰 적합화한다.

### 1.2 Background

- 현재 `CoupangAdapter` (workspace/src/lg_dash/adapters/coupang.py, 122 lines)는 `BeautifulSoup` 단일 파싱
- synthetic 픽스처 (`tests/fixtures/coupang/{search,product_*}.html`)로는 통과
- 라이브 쿠팡은 SPA — 첫 HTML 응답에는 `<div id="root">` 정도만 있고 제품 list는 JS 실행 후 채워짐
- 다나와는 robots.txt로 리뷰 AJAX 차단 → 리뷰 소스 부재 상황. 쿠팡이 리뷰 1차 소스가 되어야 LLM 분석이 가치를 가짐
- `crawl4ai>=0.4`는 이미 pyproject.toml + .venv에 설치됨 (현재 사용 안 함)

### 1.3 Related Documents

- lg_dash 완성 보고서: [docs/04-report/lg_dash-completion-report.md](../../04-report/lg_dash-completion-report.md)
- deploy-guide archive (참고): [docs/archive/2026-05/deploy-guide/](../../archive/2026-05/deploy-guide/)
- 현재 Coupang adapter: `src/lg_dash/adapters/coupang.py`

---

## 2. Scope

### 2.1 In Scope

- [ ] **Research spike (1~2h)**: 라이브 쿠팡 1 페이지에서 crawl4ai로 제품 데이터 추출 가능성 확인. 결과를 design phase로 가져감.
- [ ] **Fetcher 추상화 확장**: 기존 `HtmlFetcher` Protocol 유지 + `Crawl4aiFetcher` (또는 `BrowserFetcher`) 신규 구현. 어댑터는 fetcher만 교체.
- [ ] **CoupangAdapter 적합화**: 라이브 마크업에 맞춘 셀렉터 (search list, product detail, reviews). dual-format (synthetic + 라이브) 유지.
- [ ] **라이브 픽스처 1세트 캡처**: 회귀 방지용 (다나와 패턴 답습 — `tests/fixtures/coupang_live/`).
- [ ] **테스트**: synthetic 테스트는 그대로 유지 + 라이브 픽스처 기반 회귀 테스트 추가.
- [ ] **Rate limiting**: 쿠팡 IP 차단 회피 — `www.coupang.com=2s` 이미 존재, 헤드리스 환경에서도 동일 적용.
- [ ] **추가 robots.txt 검토**: `https://www.coupang.com/robots.txt`에 search/product 경로 허용 여부.

### 2.2 Out of Scope

- 쿠팡 Partners API 연동 (별도 머천트 계약 필요)
- 다른 소스 어댑터 (manufacturer, youtube) 라이브 적합화 — 별도 feature
- 헤드리스 브라우저의 일반화 (다나와 등 다른 어댑터로 확장 — 별도 feature)
- 카테고리 미스분류 fix (별개 `category-filter` feature)
- 쿠팡 자체 리뷰 dedup·번역 등 가공 (`pipeline.llm_analyze`가 이미 처리)
- 쿠팡 가격 변동 시계열 (현 plan: "현 시점 가격만")

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | Spike: `crawl4ai`로 search.coupang.com 1 페이지에서 제품 list 추출 PoC | High | Pending |
| FR-02 | Spike: 제품 detail 1건에서 스펙 + 리뷰 5건 추출 PoC | High | Pending |
| FR-03 | `BrowserFetcher` (Crawl4ai 기반) — `HtmlFetcher` Protocol 충족 | High | Pending |
| FR-04 | `CoupangAdapter` 라이브 마크업 대응 (`discover` / `fetch_specs` / `fetch_reviews`) | High | Pending |
| FR-05 | Synthetic + 라이브 dual-format 어댑터 (다나와 패턴 답습) | High | Pending |
| FR-06 | 라이브 픽스처 캡처 + 회귀 테스트 (`tests/test_coupang_live_shape.py`) | High | Pending |
| FR-07 | Rate limit 준수 — 헤드리스 환경에서 `www.coupang.com=2s` 적용 | Medium | Pending |
| FR-08 | CLI 사용법 문서화 — RUNBOOK §4에 쿠팡 라이브 트러블슈팅 추가 | Medium | Pending |
| FR-09 | 비용·메모리 측정 — 헤드리스 1 페이지당 ~몇 MB 메모리, ~몇 초 | Low | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement |
|----------|----------|-------------|
| Performance | 1 제품 종단간 ≤30s (search + detail + 5 reviews) | manual time |
| Stability | 회귀 테스트 통과율 100% (라이브 사이트 변경 검출) | pytest |
| Compliance | robots.txt 준수, rate limit 2s 이상 유지 | 코드 보장 |
| Memory | 헤드리스 브라우저 RSS ≤500MB peak | `/usr/bin/time -v` 또는 `psutil` |
| Detection 회피 | 1000회 누적 호출 후 IP 차단/CAPTCHA 없음 | 운영 시 관찰 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] Spike 결과 문서화 (design.md에 포함) — 어떤 path가 viable인가
- [ ] `BrowserFetcher` 구현 + 단위 테스트 (mocked browser)
- [ ] `CoupangAdapter` 라이브 모드 지원 + dual-format
- [ ] 라이브 픽스처 1세트 캡처 (`tests/fixtures/coupang_live/`)
- [ ] 회귀 테스트 `test_coupang_live_shape.py` 통과
- [ ] 라이브 종단간 스모크: `pipeline.run --source coupang --brand lg --category washer --limit 1 --skip-llm` 성공
- [ ] product 1행 + spec_raw + raw_review ≥5건 적재 확인
- [ ] 전체 pytest 회귀 0 (169+ tests still green)

### 4.2 Quality Criteria

- [ ] confidence<0.7 spec_fact 비율 ≤30% (lg_dash 기존 기준)
- [ ] 메모리 RSS ≤500MB
- [ ] zero new ruff lint warnings

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **쿠팡이 헤드리스 봇 탐지로 차단** | High | High | Spike에서 가장 먼저 확인. 차단 시 (a) User-Agent + viewport 조정, (b) 세션 쿠키 재사용, (c) 최후 — 모바일 endpoint로 우회 |
| 헤드리스 브라우저 메모리 폭증 | Medium | Medium | crawl4ai에 페이지별 close + 단일 브라우저 인스턴스 재사용. 메모리 모니터링 추가 |
| 쿠팡 셀렉터가 자주 변함 | Medium | High | dual-format 패턴 + 라이브 픽스처 회귀 테스트로 즉시 감지 |
| 1 제품 30s 초과 | Low | Medium | search list만 lazy + detail은 on-demand. `--limit` 작게 운영 |
| Spike에서 viable path 0 | High | Low | Plan 완료 후 design 단계에서 결정 — viable 없으면 Coupang Partners API 전환 검토 (별도 feature) |
| CI/local 환경 차이 (Playwright 의존성) | Medium | Medium | `pyproject.toml`에서 crawl4ai 의존성 명시. 로컬에서 `playwright install chromium` 1회 필요할 수 있음 — bootstrap에 추가 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Selected |
|-------|:--------:|
| Starter (단일 호스트, 사내 한정) | ☑ |
| Dynamic | ☐ |
| Enterprise | ☐ |

→ lg_dash 본체와 동일 Starter 레벨. 추가 인프라 없음.

### 6.2 Solution Paths (design 단계에서 선택)

| Path | 요약 | Pros | Cons |
|---|---|---|---|
| **A. crawl4ai 헤드리스** (추천) | crawl4ai 라이브러리로 Chromium 헤드리스 실행 | 이미 설치됨, JS 렌더링 완전 지원 | 메모리 비용 + 봇 탐지 위험 |
| B. 모바일 endpoint | `m.coupang.com` 또는 mAPI 호출 | 가벼움, JSON 응답 가능성 | 비공식, 자주 깨짐, 리뷰는 별도 API 필요 |
| C. Partners API | 공식 API + 머천트 계약 | 안정적, ToS 위반 0 | 사내 도구에 머천트 계약 비현실적 |

**Design phase 결정**: spike (FR-01, FR-02) 결과로 A vs B 선택. A가 viable이면 A 진행 (default).

### 6.3 Key Architectural Decisions

| Decision | Selected | Rationale |
|----------|----------|-----------|
| Fetcher 추상화 | 기존 `HtmlFetcher` Protocol 유지 + `BrowserFetcher` 신규 구현 | 다나와는 그대로, 쿠팡만 브라우저 사용 |
| 브라우저 풀 | 단일 인스턴스 재사용 (per-process) | 메모리 + 시작 시간 절감 |
| 셀렉터 전략 | data-attribute 우선 → CSS class fallback | 다나와 dual-format 패턴 답습 |
| 픽스처 캡처 | `tests/fixtures/coupang_live/` 1 search + 1 product | 다나와와 동일 구조 |
| robots.txt 검증 | spike에 포함 | 차단 경로는 무조건 제외 |

### 6.4 Folder Structure

```
workspace/
├─ src/lg_dash/adapters/
│   ├─ coupang.py                ← 적합화 대상 (dual-format)
│   └─ fetcher.py                ← BrowserFetcher 추가
└─ tests/
    ├─ fixtures/coupang_live/    ← 신규
    │   ├─ search_lg_washer.html
    │   └─ product_<pcode>.html
    └─ test_coupang_live_shape.py ← 신규
```

---

## 7. Convention Prerequisites

### 7.1 Existing Project Conventions

- [x] `pyproject.toml` 의존성 — `crawl4ai>=0.4` 이미 명시
- [x] Python 3.11+
- [x] ruff line-length=100
- [x] pytest fixture 패턴 (다나와 라이브에서 답습)

### 7.2 Conventions to Define/Verify

| Category | Current State | To Define |
|----------|---------------|-----------|
| Browser fetcher 종료 시점 | undefined | context manager `with BrowserFetcher() as fetcher:` 패턴 |
| 라이브 픽스처 갱신 주기 | undefined | 셀렉터 깨짐 발생 시 갱신 (수동), 분기 1회 점검 권장 |

### 7.3 Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `CRAWL4AI_HEADLESS` | 헤드리스 모드 on/off (debug 시 false) | `true` |
| `CRAWL4AI_BROWSER` | 브라우저 선택 (chromium/firefox/webkit) | `chromium` |

`.env.example`에 추가 후 `bootstrap.sh`가 `playwright install chromium`을 자동 실행하도록 보강.

---

## 8. Next Steps

1. [ ] `/pdca design coupang-live` — spike 결과 기록 + Path 선택 + selector outline 확정
2. [ ] Design 안에서 spike 실행 (1~2h, 또는 Do 첫 task로 분리)
3. [ ] `/pdca do coupang-live` — 본 구현 (BrowserFetcher → CoupangAdapter → 픽스처 → 회귀 테스트)
4. [ ] `/pdca analyze coupang-live` — gap-detector로 검증
5. [ ] `/pdca report coupang-live`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-22 | Initial draft (3 paths + research spike 필수) | aaaiiee |
