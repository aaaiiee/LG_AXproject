# lg_dash — 국내 생활가전 비교 대시보드

> 세탁기 / 건조기 / 통돌이 — 제조사 공식 + 다나와 + 쿠팡 + 유튜브 4개 소스를 크롤하여 스펙·리뷰를 정규화하고 Streamlit으로 비교/탐색하는 사내용 대시보드.

## ⚠️ 사내망 한정

이 도구는 **사내 의사결정 지원용**이며 외부 공개를 가정하지 않습니다. 저작권(이미지/스펙/리뷰) 및 LLM API 비용 노출 위험이 있어 외부 URL로 라우팅하지 마세요. 사내망 노출 패턴은 [docs/05-ops/DEPLOY.md](docs/05-ops/DEPLOY.md) 참조.

---

## What

- **수집**: 4 소스 어댑터 (`manufacturer / danawa / coupang / youtube`)에서 스펙·이미지·리뷰 크롤
- **정규화**: 사전 기반 rule → fuzzy → LLM 폴백 3단계 매칭, confidence + matched_by 추적
- **요약**: Anthropic Claude Haiku 4.5로 리뷰 pros/cons + 감성 태그 + overall_score
- **대시보드**: Streamlit 4탭 (목록·카드 / 비교 / 상세 / 운영)
- **운영**: refresh_log + llm_call_log, $1/run 비용 경고, 수동 오버라이드 편집

---

## Stack

| Layer | Tech |
|---|---|
| Language | Python 3.11+ |
| Storage | SQLite (WAL mode) |
| Crawler | httpx + BeautifulSoup |
| Matching | rapidfuzz (fuzzy) + Anthropic Claude (LLM fallback) |
| LLM | Anthropic Claude Haiku 4.5 + prompt caching |
| Dashboard | Streamlit + Plotly Scatterpolar |
| Tests | pytest (169 tests) |

---

## Quick Start (5단계)

### 1. 환경 부트스트랩
```bash
./scripts/bootstrap.sh
```
venv 생성 + 의존성 설치 + .env 복사 + DB migrate + brand seed. **재실행해도 안전**.

### 2. API 키 설정
`.env` 파일을 열어 `ANTHROPIC_API_KEY=` 자리에 실제 키 입력.
LLM 기능을 안 쓰면 비워둬도 됩니다 (아래 명령에 `--skip-llm` 추가).

### 3. 첫 크롤 + 정규화
```bash
source .venv/bin/activate
python -m lg_dash.pipeline.run \
  --source danawa --brand lg --category washer \
  --limit 3 --skip-llm
```
다나와에서 LG 세탁기 3개를 크롤하고 SQLite에 정규화된 스펙으로 저장합니다.

### 4. (선택) LLM 분석
```bash
python -m lg_dash.pipeline.llm_analyze --all
```
저장된 리뷰를 요약하고 감성 태그를 추출합니다. 제품당 약 $0.005.

### 5. 대시보드 실행
```bash
streamlit run src/lg_dash/app/dashboard.py --server.address 127.0.0.1
```
브라우저로 <http://localhost:8501> 접속.

> 외부에서 접근하려면 **SSH 터널** 또는 **nginx + IP allowlist** 사용. [DEPLOY](docs/05-ops/DEPLOY.md) 참조. `0.0.0.0` 바인딩은 절대 금지.

---

## 디렉터리 구조

```
workspace/
├─ README.md                          ← 본 문서 (입구)
├─ pyproject.toml                     ← 의존성
├─ .env.example                       ← 환경 변수 템플릿
├─ scripts/
│  └─ bootstrap.sh                    ← one-shot 초기화
├─ src/lg_dash/
│  ├─ adapters/        ← 4 소스 어댑터 (Protocol 기반)
│  ├─ pipeline/        ← crawl → normalize → images → llm_analyze → run (오케스트레이터)
│  ├─ storage/         ← SQLite + migrations
│  ├─ llm/             ← Anthropic 클라이언트 + 프롬프트
│  ├─ scripts/         ← seed_brands 등
│  └─ app/             ← Streamlit 4탭
├─ tests/                              ← 169 tests
├─ config/
│  ├─ brands.yaml                     ← LG, Samsung, Winia
│  ├─ categories.yaml                 ← 세탁기 / 건조기 / 통돌이
│  ├─ attr_dictionary.yaml            ← 11 canonical_keys + 시놋
│  └─ sentiment_tags.yaml             ← 감성 태그 어휘
├─ storage/                            ← (gitignored)
│  ├─ db.sqlite                       ← SQLite DB
│  ├─ images/                         ← 다운로드된 이미지
│  └─ backups/                        ← 백업
└─ docs/
   ├─ 01-plan/features/               ← PDCA Plan 문서
   ├─ 02-design/features/             ← PDCA Design 문서
   ├─ 04-report/                      ← PDCA 완성 보고서
   └─ 05-ops/                         ← 운영 가이드
      ├─ RUNBOOK.md                   ← 일상 운영, 백업, 트러블슈팅
      └─ DEPLOY.md                    ← 사내망 노출 패턴
```

---

## 주요 명령

| 작업 | 명령 |
|---|---|
| 종단간 (crawl+normalize+images+LLM) | `python -m lg_dash.pipeline.run --source danawa --brand lg --category washer --limit 3` |
| 종단간 (LLM 생략) | `... --skip-llm` |
| 종단간 (이미지 생략) | `... --skip-images` |
| 크롤만 | `python -m lg_dash.pipeline.crawl --source danawa --brand lg --category washer --limit 3` |
| 정규화만 | `python -m lg_dash.pipeline.normalize --all` |
| 이미지만 | `python -m lg_dash.pipeline.images --all` |
| LLM 분석만 | `python -m lg_dash.pipeline.llm_analyze --all` |
| 테스트 | `pytest` (169 tests) |
| 린트 | `ruff check src tests` |

지원 카테고리: `washer`, `dryer`, `top_loader` · 지원 브랜드 (seed 시점): `lg`, `samsung`, `winia` · 지원 소스: `manufacturer`, `danawa`, `coupang`, `youtube`

---

## 환경 변수

`.env` 파일 (`.gitignore`에 등록, 절대 commit 금지):

| 변수 | 필수 | 기본값 | 설명 |
|---|:---:|---|---|
| `ANTHROPIC_API_KEY` | LLM 사용 시 | (empty) | Anthropic API 키. 미설정 시 `--skip-llm` 사용 |
| `LLM_MODEL` | ❌ | `claude-haiku-4-5` | LLM 모델 ID |
| `LG_DASH_DB_PATH` | ❌ | `storage/db.sqlite` | SQLite 경로 |
| `CRAWL_USER_AGENT` | ❌ | `LG_Dash/0.0.1 (+internal-use)` | HTTP User-Agent |
| `CRAWL_RATE_LIMIT_PER_HOST` | ❌ | `1.0` | 기본 호스트별 최소 지연(초) |

host별 하드코딩 지연 (코드): `search.danawa.com=10s` (robots.txt), `prod.danawa.com=2s`, `www.coupang.com=2s`, `www.youtube.com=2s`.

---

## 더 알아보기

- 일상 운영 (백업·모니터링·트러블슈팅): **[docs/05-ops/RUNBOOK.md](docs/05-ops/RUNBOOK.md)**
- 사내망 노출 (SSH 터널 / nginx): **[docs/05-ops/DEPLOY.md](docs/05-ops/DEPLOY.md)**
- 설계 배경 + 완성 보고: [docs/04-report/lg_dash-completion-report.md](docs/04-report/lg_dash-completion-report.md)
- deploy-guide PDCA 아카이브: [docs/archive/2026-05/deploy-guide/](docs/archive/2026-05/deploy-guide/) (plan + design + analysis + report)

---

## 라이선스

내부 사용 전용. 외부 배포·재공개 금지. 수집 데이터의 원저작권은 각 출처에 있음.
