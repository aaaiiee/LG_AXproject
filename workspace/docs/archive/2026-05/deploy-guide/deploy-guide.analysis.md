# deploy-guide Gap Analysis Report

> **Feature**: deploy-guide
> **Date**: 2026-05-22
> **Analyst**: bkit:gap-detector
> **Status**: Passed (Match Rate 97%)

## 분석 개요

| 항목 | 값 |
|---|---|
| **Design Doc** | [docs/02-design/features/deploy-guide.design.md](../02-design/features/deploy-guide.design.md) |
| **Plan Doc** | [docs/01-plan/features/deploy-guide.plan.md](../01-plan/features/deploy-guide.plan.md) |
| **Implementation** | 5 files (`.env.example`, `scripts/bootstrap.sh`, `RUNBOOK.md`, `DEPLOY.md`, `README.md`) |
| **Overall Match Rate** | **97%** (≥90% 통과) |
| **Verdict** | `/pdca report` 진행 권장 |

---

## Per-Category Verdict

| Category | Score | Status |
|---|:-:|:-:|
| Design Outline 일치 | 98% | OK |
| Plan FR Coverage (10/10) | 100% | OK |
| Security / DoD | 95% | OK |
| Implementation Order | 100% | OK |

---

## Per-Section Verdict (Design §3.1 ~ §3.5)

| § | 대상 파일 | 일치 항목 | 결과 |
|---|---|---|:-:|
| §3.1 README | `README.md` | Quick Start 5단계 / 외부 노출 차단 박스 / RUNBOOK·DEPLOY·완성보고서 링크 모두 존재. Stack 표·디렉터리 구조·env 변수 표는 outline을 초과해 보강 (+) | OK |
| §3.2 RUNBOOK | `docs/05-ops/RUNBOOK.md` | 일일 새로고침 / 백업 (일·주·cron) / 모니터링 4지표 / 트러블슈팅 5케이스(4.1~4.5) / 정상화 + 보안 체크 (+) | OK |
| §3.3 DEPLOY | `docs/05-ops/DEPLOY.md` | SSH 터널 (default) / nginx + IP allowlist + basic auth / 안티패턴 6항목(설계 3 초과 +) / 점검 체크리스트 (+) | OK |
| §3.4 .env.example | `workspace/.env.example` | 4 필수 변수 모두 존재 + `LLM_MODEL`, `LG_DASH_IMAGE_DIR`, `CRAWL_TIMEOUT_SECONDS` 추가 | OK* |
| §3.5 bootstrap.sh | `workspace/scripts/bootstrap.sh` | 6단계 모두 (Python 체크 → venv → install → .env → storage → migrate+seed). `[N/6]` 진행 로그 + idempotent 분기 (+) | OK |

\* outline에는 4개만 적혔으나 추가 3변수는 plan에서 직접 금지된 적 없음 — 문서화 보강 차원.

---

## Plan FR Coverage (FR-01 ~ FR-10)

| ID | Requirement | Evidence | Status |
|---|---|---|:-:|
| FR-01 | README 1문단 + Quick Start 5단계 | `README.md:1-7, 35-68` | Done |
| FR-02 | `.env.example` 변수 + 예시값 + 보안 주의 | `.env.example:1-12`, `README.md:129` (절대 commit 금지) | Done |
| FR-03 | bootstrap (venv + pip -e + migrate + seed) | `scripts/bootstrap.sh:1-54` (6 steps) | Done |
| FR-04 | 첫 크롤 walkthrough (`pipeline.run --skip-llm`) | `README.md:48-53`, `RUNBOOK.md:19-23` | Done |
| FR-05 | Streamlit 명령 + 포트 명시 | `README.md:63-66`, `DEPLOY.md:29-32` | Done |
| FR-06 | SSH 터널 + nginx 2가지 패턴 | `DEPLOY.md:20-85, 88-148` | Done |
| FR-07 | DB 백업 (일/주, 이미지 dir 옵션) | `RUNBOOK.md:36-69` | Done |
| FR-08 | LLM 비용 모니터링 ($1 경고) | `RUNBOOK.md:31-32, 77-83` | Done |
| FR-09 | 트러블슈팅 5케이스 | `RUNBOOK.md:86-130` (4.1~4.5 모두 매칭) | Done |
| FR-10 | 외부 공개 차단 경고 (README + DEPLOY) | `README.md:5-7`, `DEPLOY.md:8-16` | Done |

**Coverage**: 10/10 (100%)

---

## Security Check (Design §5.3)

| 항목 | 결과 |
|---|:-:|
| `.gitignore`에 `.env` | OK |
| `.gitignore`에 `.venv/` | OK |
| `.gitignore`에 `storage/db.sqlite*` | OK |
| `.gitignore`에 `storage/images/` | OK |
| README 외부 노출 차단 경고 | OK |
| DEPLOY 외부 노출 차단 경고 | OK |

---

## 이미 검증된 Smoke 결과 (sub-agent 사전 확인)

| 검증 | 결과 |
|---|:-:|
| `bash -n scripts/bootstrap.sh` syntax | ✓ |
| `bootstrap.sh` 재실행 idempotency | ✓ |
| `python -m lg_dash.pipeline.run --help` 모든 documented flag | ✓ |
| README 5개 doc 링크 resolve | ✓ |
| `pytest` 전체 통과 (169 tests) | ✓ |
| `.gitignore` 4 secrets 커버 | ✓ |

---

## Gap List (priority 순)

| # | Priority | Gap | 위치 | 권장 조치 |
|---|:-:|---|---|---|
| G1 | Low | `.env.example`에 `ANTHROPIC_API_KEY=sk-ant-...` placeholder가 채워져 있어 design §3.4 "빈 값" 명세와 다름. bootstrap.sh의 `grep "^ANTHROPIC_API_KEY=.\+"` 검증을 통과시켜 경고를 못 띄움 | `.env.example:1` | `ANTHROPIC_API_KEY=`로 비우기 (1 line 수정) |
| G2 | Low | §5.1 "fresh tmp dir from-scratch test"가 자동화돼 있지 않음. manual smoke로 ✓ 확인 완료 | Verification Plan §5.1 | 현 상태 수용. report 단계에 "manual 검증 완료" 명시 |
| G3 | Info | `.env.example`에 design outline 외 3변수 추가 (`LLM_MODEL`, `LG_DASH_IMAGE_DIR`, `CRAWL_TIMEOUT_SECONDS`) | `.env.example:2,5,8` | design doc §3.4에 반영 또는 .env.example에서 제거 |

---

## 추가 강점 (Design 초과 구현)

- `bootstrap.sh`: `[N/6]` 진행 로그 + check 이모지, design 대비 가독성 향상
- `DEPLOY.md`: 안티패턴 3개 → 6개로 확장 (DDNS+포트포워딩, public 클라우드 배포 등)
- `RUNBOOK.md` §6 보안 체크 (월 1회) — design에 없음, 운영 가치 +
- `README.md` Stack 표 + 디렉터리 구조 + 명령 요약 표 — single entry point 원칙 강화

---

## 권장 다음 단계

**`/pdca report deploy-guide`** — Match Rate 97% ≥ 90% 통과.

선택적 후속 조치 (작아 보고서 작성 전 즉시 처리 가능):
1. **G1 수정** (1 line): `.env.example`의 `ANTHROPIC_API_KEY=` 빈 값으로 변경 → bootstrap의 경고 메시지 동작 보장
2. **G3 흡수**: design §3.4에 추가 변수 반영 또는 .env.example 축소
