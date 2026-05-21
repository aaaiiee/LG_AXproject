---
template: plan
version: 1.2
feature: deploy-guide
project: lg_dash
date: 2026-05-22
author: aaaiiee
status: Draft
---

# deploy-guide Planning Document

> **Summary**: lg_dash 대시보드를 사내망에서 안전하게 구동하기 위한 README + 운영 runbook + 환경 구성 가이드 작성.
>
> **Project**: lg_dash (Korean home appliance comparison dashboard)
> **Version**: 0.0.1
> **Author**: aaaiiee
> **Date**: 2026-05-22
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | lg_dash 코드는 완성됐지만 팀원이 자력으로 셋업·구동·운영하기 위한 단일 문서가 없음. 환경 변수, DB 마이그레이션, Streamlit 사내망 노출 방식 등이 산재해 있어 시행착오 비용 발생. |
| **Solution** | README + ops runbook + 첫 실행 walkthrough 3개 문서를 작성해 셋업·운영·트러블슈팅을 한 곳에서 다룬다. 사내망 한정 노출 패턴(SSH 터널 또는 nginx)을 명시한다. |
| **Function/UX Effect** | 신규 팀원이 30분 내 첫 크롤+대시보드 구동까지 도달. 운영자가 LLM 비용 초과·DB 백업·인덱싱 문제를 runbook 한 번에 처리. |
| **Core Value** | 1인이 만든 도구가 팀 자산으로 전환되는 운영 기반 확보. 외부 공개 차단으로 저작권 리스크 회피. |

---

## 1. Overview

### 1.1 Purpose

lg_dash (M0~M8 완료, 169/169 테스트 통과)를 본인 외 팀원이 자력 구동·운영할 수 있도록 문서화한다.

### 1.2 Background

- 현재 코드는 동작하지만 setup 절차가 머릿속에만 있음
- 사내망 한정 노출 정책이 README에 명시돼야 저작권·보안 리스크 회피
- LLM 비용·DB 크기·이미지 디스크 사용량 모니터링 가이드 필요
- 다음 사이클(쿠팡 라이브 적합화 등) 진입 전 기반 작업

### 1.3 Related Documents

- 원본 설계: `/Users/aaaiiee/.claude/plans/frolicking-drifting-plum.md`
- 완성 보고서: `docs/04-report/lg_dash-completion-report.md`
- 라이브 검증 결과 (M8 + 라이브 스모크): 위 보고서 §3.5

---

## 2. Scope

### 2.1 In Scope

- [ ] **README.md** — 프로젝트 한눈에 보기 + 빠른 시작 5단계
- [ ] **docs/05-ops/RUNBOOK.md** — 일상 운영 (백업/모니터링/트러블슈팅)
- [ ] **docs/05-ops/DEPLOY.md** — 사내망 노출 패턴 (SSH 터널 + nginx reverse proxy)
- [ ] **.env.example** — 환경 변수 템플릿 (`ANTHROPIC_API_KEY`, `LG_DASH_DB_PATH`, `CRAWL_USER_AGENT`, `CRAWL_RATE_LIMIT_PER_HOST`)
- [ ] **scripts/bootstrap.sh** — 신규 환경 초기화 자동화 (venv + pip + migrate + seed)

### 2.2 Out of Scope

- 자동 스케줄링 (cron/airflow) — plan 원문에 "온디맨드만" 명시
- Docker 컨테이너화 — Python venv 직접 사용으로 충분
- CI/CD 파이프라인 — 사내 단일 호스트 가정
- 외부 공개·배포 — plan 원문에 "외부 공개 X" 명시
- 멀티-테넌트/사용자 인증 — plan 원문에 "사내 신뢰 환경 가정" 명시

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | README에 프로젝트 1문단 설명 + 빠른 시작 5단계 | High | Pending |
| FR-02 | `.env.example` 모든 환경 변수 + 예시값 + 보안 주의 | High | Pending |
| FR-03 | bootstrap 스크립트 (venv + `pip install -e .` + `migrate` + `seed_brands`) | High | Pending |
| FR-04 | 첫 크롤 walkthrough: `python -m lg_dash.pipeline.run --source danawa --brand lg --category washer --limit 3 --skip-llm` 권장 | High | Pending |
| FR-05 | Streamlit 구동 명령 + 로컬 포트 (`streamlit run src/lg_dash/app/dashboard.py`) | High | Pending |
| FR-06 | 사내망 노출 2가지 패턴: (a) SSH 터널 `ssh -L 8501:localhost:8501 host`, (b) nginx reverse proxy + basic auth | High | Pending |
| FR-07 | DB 백업 (`storage/db.sqlite` 일/주 단위 cp + 이미지 dir 옵션) | Medium | Pending |
| FR-08 | LLM 비용 모니터링 (ops_view의 `Run별 비용` 표 + $1 경고) | Medium | Pending |
| FR-09 | 트러블슈팅 5가지: `no such table: manual_override`, robots.txt 차단, ANTHROPIC_API_KEY 누락, 이미지 fetch 실패, 다나와 카테고리 미스분류 | Medium | Pending |
| FR-10 | 외부 공개 차단 경고 (README + DEPLOY 양쪽에 명시) | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Onboarding 시간 | 신규 팀원 30분 내 첫 크롤 완료 | 동료 1명에게 README만 주고 실제 측정 |
| 문서 신선도 | 코드와 일치 (실제 명령이 그대로 동작) | 가이드 명령을 fresh tmp env에서 1회 끝까지 실행 |
| 저작권/보안 | 외부망 노출 차단 명시 | README + DEPLOY에 강조 박스로 표기 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] README.md 작성 (≤200 lines, 빠른 시작 5단계)
- [ ] RUNBOOK.md 작성 (백업/모니터링/트러블슈팅)
- [ ] DEPLOY.md 작성 (사내망 패턴 2가지)
- [ ] .env.example + bootstrap.sh 실행 검증
- [ ] 모든 명령이 README 그대로 fresh shell에서 동작 (manual smoke)

### 4.2 Quality Criteria

- [ ] 169 tests 여전히 통과 (코드 변경 시)
- [ ] bootstrap.sh가 idempotent (재실행 시 깨지지 않음)
- [ ] DEPLOY 가이드가 외부 노출 차단 패턴을 default로 제시

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 문서가 코드와 어긋남 (drift) | Medium | High | fresh shell smoke를 DoD에 포함, gap-detector로 재검증 |
| ANTHROPIC_API_KEY 노출 | High | Medium | `.env.example`만 commit, `.gitignore`에 `.env` 등록 확인 |
| 외부 노출 실수 | High | Low | DEPLOY에 강조 박스 + nginx config에 IP allowlist 예시 |
| 다나와 rate limit 위반 | Medium | Low | `CRAWL_RATE_LIMIT_PER_HOST` env + runbook에 robots.txt 준수 명시 |
| 사내망 환경 다양성 (방화벽/포트) | Low | Medium | SSH 터널을 first-class로 안내, nginx는 secondary |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Selected |
|-------|-----------------|:--------:|
| **Starter** | 단일 호스트, 사내 한정, 정적/단순 운영 | ☑ |
| **Dynamic** | 멀티 사용자, 외부 노출 | ☐ |
| **Enterprise** | 고가용성, k8s, 마이크로서비스 | ☐ |

→ Starter 레벨 적합. Streamlit 단일 호스트 + SQLite + 사내망.

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 호스팅 | Vercel / Streamlit Cloud / 사내 단일 호스트 | 사내 단일 호스트 | 저작권 + 데이터 보안 |
| 노출 패턴 | Public / Cloudflare Tunnel / SSH 터널 / nginx + VPN | SSH 터널 (default) + nginx (옵션) | 사내망 한정 + 운영 단순성 |
| 환경 격리 | conda / venv / poetry / docker | `python -m venv` (현재 사용 중) | 단일 호스트 + 추가 도구 불필요 |
| 비밀 관리 | .env / vault / 1Password | `.env` 파일 + `.gitignore` | 단일 사용자 환경 |
| 백업 전략 | rsync to NAS / cron + cp / 수동 | cron + `cp -p storage/db.sqlite` | 단순성 우선 |
| LLM 비용 알림 | 이메일 / Slack / ops_view UI 배너 | ops_view UI 배너 ($1 초과 경고, P1.1로 구현 완료) | 사용자가 정기적으로 보는 곳 |

### 6.3 Repository Structure (deploy-related)

```
workspace/
├─ README.md                    ← 신규 (전체 입구)
├─ .env.example                 ← 신규
├─ .gitignore                   ← 확인 (.env, .venv, storage/db.sqlite, storage/images/)
├─ scripts/
│  └─ bootstrap.sh              ← 신규 (one-shot 초기화)
├─ docs/
│  ├─ 01-plan/features/
│  │  └─ deploy-guide.plan.md   ← 본 문서
│  ├─ 02-design/features/
│  │  └─ deploy-guide.design.md ← 다음 단계
│  ├─ 04-report/
│  │  └─ lg_dash-completion-report.md  (이미 존재)
│  └─ 05-ops/                   ← 신규
│     ├─ RUNBOOK.md
│     └─ DEPLOY.md
└─ ... (기존 src/, tests/, config/, storage/)
```

---

## 7. Convention Prerequisites

### 7.1 Existing Project Conventions

- [x] `pyproject.toml` 존재 (의존성 + 빌드)
- [x] Python 3.11+ 명시
- [x] ruff 설정 존재 (line-length=100)
- [x] pytest 설정 존재
- [ ] `.env.example` 없음 → FR-02로 추가
- [ ] README.md 없음 → FR-01로 추가
- [ ] CLAUDE.md 프로젝트 컨벤션 섹션 없음 (필요 시 추후)

### 7.2 Environment Variables Needed

| Variable | Purpose | Default | To Be Documented |
|----------|---------|---------|:----------------:|
| `ANTHROPIC_API_KEY` | LLM 호출 (review summary + fallback matching) | (none, required) | ☑ |
| `LG_DASH_DB_PATH` | SQLite DB 경로 | `storage/db.sqlite` | ☑ |
| `CRAWL_USER_AGENT` | HTTP 요청 User-Agent | `LG_Dash/0.0.1 (+internal-use)` | ☑ |
| `CRAWL_RATE_LIMIT_PER_HOST` | 기본 host별 최소 지연 (초) | `1.0` | ☑ |

### 7.3 Pipeline Integration

본 feature는 9-phase Development Pipeline 외부 작업 (문서 중심). Phase 1·2 적용 불필요.

---

## 8. Next Steps

1. [ ] `/pdca design deploy-guide` — Design 문서로 README/RUNBOOK/DEPLOY 각 섹션 outline 확정
2. [ ] `/pdca do deploy-guide` — 5개 파일 작성 + smoke
3. [ ] `/pdca analyze deploy-guide` — gap-detector로 검증
4. [ ] `/pdca report deploy-guide` — 완료 보고서

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-22 | Initial draft | aaaiiee |
