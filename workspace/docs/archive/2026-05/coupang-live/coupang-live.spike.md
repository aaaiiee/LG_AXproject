# coupang-live Spike Findings

> **Spike date**: 2026-05-22
> **Duration**: ~30 min
> **Verdict**: Path A (crawl4ai 헤드리스) **NOT viable** out-of-the-box. Akamai 봇 방어가 너무 강력.

## What was tested

| # | Test | Method | Result |
|---|---|---|---|
| 1 | `robots.txt` 직접 fetch (LG_Dash UA) | `curl -A "LG_Dash/..." https://www.coupang.com/robots.txt` | HTTP **403** Access Denied (edgesuite) |
| 2 | `robots.txt` Chromium UA | `curl -A "Mozilla/...Chrome/131"` | HTTP **403** |
| 3 | `robots.txt` 기본 curl UA | (no UA override) | HTTP **403** |
| 4 | Search page Chromium UA HEAD | `curl -A "Chrome/131" ...search?q=...` | HTTP **403**, 387B |
| 5 | crawl4ai 헤드리스 Chromium (no wait) | `AsyncWebCrawler(headless=True, chromium)` + `delay_before_return_html=5s` | HTTP **200 OK**이지만 body는 `<title>Access Denied</title>` (Akamai 가짜 200) |

### Decisive evidence (test #5)

```html
<html><head>
<title>Access Denied</title>
</head><body>
<h1>Access Denied</h1>
You don't have permission to access "http://www.coupang.com/np/search?" on this server.
Reference #18.d23a6f3d.1779381235.4b2b3dee
https://errors.edgesuite.net/18.d23a6f3d.1779381235.4b2b3dee
</body></html>
```

→ Akamai이 status 200으로 fake response 반환. TLS fingerprint + headless 신호 둘 다 탐지.

## Why curl/httpx fails

- Coupang은 Akamai Bot Manager를 사용
- TLS JA3 fingerprint가 실제 브라우저와 다름 → 즉시 차단
- User-Agent 변경만으로는 우회 불가

## Why default crawl4ai fails

- crawl4ai의 Chromium은 `navigator.webdriver=true` 등 headless 신호 노출
- Akamai가 이 신호를 탐지해 200 status로 fake "Access Denied" 페이지 반환
- (status 코드가 200이라 단순 status 체크로는 차단을 못 감지 — body 검사 필수)

## Options remaining

| Option | Viability | Effort | Risk |
|---|:-:|:-:|---|
| **(1) crawl4ai + 고급 stealth** | 불확실 | 중~상 | `navigator.webdriver` 우회 + 마우스 jitter + 세션 쿠키 재사용. Coupang ToS 위반 가능성. 영구 해결은 어려움 (Akamai 업데이트마다 깨짐) |
| **(2) Coupang Partners API** | 가장 안정적 | 상 | 머천트 계약 + API 키 필요. 사내 도구에 비현실적 |
| **(3) Coupang 모바일 앱 API** | 보통 | 상 | 비공식 API reverse engineering. ToS 위반 명백. 사내 정책 충돌 가능 |
| **(4) Coupang 포기, 대체 소스 도입** | 명확 | 중 | Naver Shopping 리뷰 / 11번가 / G마켓 등. 새 어댑터 1개 = ~M3 1개 분량 |
| **(5) 무기한 deferred** | 즉시 가능 | 0 | 다나와는 robots.txt 차단, manufacturer는 적합화 안 됨, youtube만 남음 — 리뷰 커버리지 절대 부족 |

## Recommendation

**Option (4) — Coupang 포기, Naver Shopping (또는 11번가) 어댑터로 대체.**

근거:
- Path A는 anti-detection arms race로 지속 가능성 낮음
- Partners API는 계약 장벽
- Naver Shopping은 공식 검색 API + 일부 리뷰 노출 — 더 안정적
- lg_dash의 본질적 가치(리뷰 기반 의사결정)에는 "꼭 쿠팡이어야"라는 제약 없음

대안 후보:
1. **Naver Shopping** — `developers.naver.com/docs/serviceapi/search/shopping/shopping.md` 공식 API, 무료 25,000 요청/일
2. **11번가** — robots.txt 검토 필요, public API 없음
3. **G마켓 / 옥션** — 동일

## Suggested next plan

`/pdca plan naver-shopping` — Coupang 어댑터를 Naver Shopping 어댑터로 대체하는 별도 PDCA 사이클. 본 `coupang-live` plan은 archive로 보내거나 "Deferred - infrastructure blocker" 상태로 표기.

## Cost of spike

- Time: ~30 minutes
- Disk: Playwright Chromium 200MB+ (1회성)
- Memory: peak ~400MB during crawl4ai run
- Network: 5 HTTP requests to coupang.com, all 403 or 200-fake
- Tokens: included in session budget
