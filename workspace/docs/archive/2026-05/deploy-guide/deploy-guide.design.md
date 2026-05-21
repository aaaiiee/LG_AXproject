---
template: design
version: 1.2
feature: deploy-guide
project: lg_dash
date: 2026-05-22
author: aaaiiee
status: Draft
---

# deploy-guide Design Document

> **Summary**: README + RUNBOOK + DEPLOY + .env.example + bootstrap.sh 5종 산출물의 outline + 검증 방법.
>
> **Project**: lg_dash
> **Version**: 0.0.1
> **Author**: aaaiiee
> **Date**: 2026-05-22
> **Status**: Draft
> **Planning Doc**: [deploy-guide.plan.md](../../01-plan/features/deploy-guide.plan.md)

---

## 1. Overview

### 1.1 Design Goals

- 신규 팀원이 30분 내 첫 크롤 + Streamlit 구동 도달 가능한 단일 입구 (README) 제공
- 운영자가 백업·비용 모니터링·트러블슈팅을 한 문서(RUNBOOK)에서 해결
- 사내망 노출을 위한 2가지 패턴(SSH 터널 / nginx)을 DEPLOY에서 안전 default와 함께 제시
- 환경 변수 노출 사고 방지: `.env.example`만 commit, `.env`는 `.gitignore`

### 1.2 Design Principles

- **Single Entry Point**: README가 모든 문서의 허브 역할 (다른 문서로의 링크만 제공, 내용 중복 회피)
- **Copy-Pasteable**: 모든 명령은 그대로 복사해 실행 가능 (가공된 placeholder 금지)
- **Idempotent Bootstrap**: bootstrap.sh 재실행해도 깨지지 않음 (이미 있는 .venv/.env/DB는 보존)
- **Security by Default**: 외부 노출 방지가 default. nginx 예시는 IP allowlist + basic auth 포함
- **YAGNI**: Docker, CI/CD, 멀티유저 인증은 plan에서 명시적 제외

---

## 2. Architecture

### 2.1 Document Component Map

```
README.md (입구)
  │
  ├─ Quick Start → bootstrap.sh + first crawl + streamlit run
  ├─ "더 알아보기" 링크 ↓
  │
  ├──▶ docs/05-ops/RUNBOOK.md (일상 운영)
  │     · 일일/주간 백업 절차
  │     · LLM 비용 모니터링 (ops_view)
  │     · 트러블슈팅 5가지
  │
  ├──▶ docs/05-ops/DEPLOY.md (사내망 노출)
  │     · 패턴 A: SSH 터널 (default)
  │     · 패턴 B: nginx + basic auth + IP allowlist
  │     · 외부 노출 차단 경고 박스
  │
  └──▶ docs/04-report/lg_dash-completion-report.md (이미 존재, 참조만)
```

### 2.2 Bootstrap Flow

```
scripts/bootstrap.sh
  │
  ├─ check_python_3_11_or_higher
  ├─ create_venv_if_missing  → .venv/
  ├─ activate_venv
  ├─ pip_install_editable    → pip install -e .
  ├─ ensure_env_file         → cp .env.example .env (if missing) + WARN if API key empty
  ├─ ensure_storage_dirs     → mkdir storage/images
  ├─ initialize_db           → python -c "from lg_dash.storage.db import connect, migrate; conn=connect(); migrate(conn)"
  ├─ seed_brands_if_empty    → python -m lg_dash.scripts.seed_brands (idempotent)
  └─ print_next_steps        → "Run: streamlit run ..."
```

### 2.3 Dependencies (작성 시 참조하는 기존 파일)

| 작성 문서 | 참조 기존 자원 | 용도 |
|---|---|---|
| README | pyproject.toml, ref 보고서 | dep 목록, 스택 |
| README Quick Start | bootstrap.sh, pipeline/run.py | 명령 정확성 |
| RUNBOOK 백업 | storage/db.sqlite 경로, db_path() | 백업 대상 |
| RUNBOOK 모니터링 | ops_view.py | 어디서 무엇을 보는지 |
| RUNBOOK 트러블슈팅 | 라이브 스모크 findings (F1~F5) | 실제 발생 사례 |
| DEPLOY | streamlit 기본 포트 8501, HttpFetcher UA | nginx config 정확성 |

---

## 3. Document Outlines

### 3.1 README.md outline (≤200 lines)

```
# lg_dash — 국내 생활가전 비교 대시보드

## What
1문단: 4 소스 크롤 → 정규화 → LLM 요약 → Streamlit 대시보드. 사내 한정.

## Stack
Python 3.11 + Streamlit + SQLite + Anthropic Claude Haiku 4.5

## Quick Start (5단계)
1. ./scripts/bootstrap.sh
2. .env에 ANTHROPIC_API_KEY 채우기
3. python -m lg_dash.pipeline.run --source danawa --brand lg --category washer --limit 3 --skip-llm
4. python -m lg_dash.pipeline.llm_analyze --all   # (선택, LLM 분석)
5. streamlit run src/lg_dash/app/dashboard.py

## ⚠️ 외부 노출 차단
사내망에서만 사용. 외부 노출 시 저작권 + API 비용 리스크. 사내망 노출 방법은 docs/05-ops/DEPLOY.md.

## 더 알아보기
- 운영: docs/05-ops/RUNBOOK.md
- 사내망 노출: docs/05-ops/DEPLOY.md
- 설계 배경: docs/04-report/lg_dash-completion-report.md
```

### 3.2 RUNBOOK.md outline

```
# 운영 Runbook

## 1. 매일 새로고침
- ops 탭 → "선택 새로고침" 또는 CLI: pipeline.run --limit 3
- 비용 점검: ops 탭의 "Run별 비용" 표, $1 초과 경고 확인

## 2. 백업
- 일일: cp -p storage/db.sqlite storage/backups/db.$(date +%F).sqlite
- 주간: tar -czf storage/backups/images.$(date +%F).tar.gz storage/images/
- cron 예시 (사내 호스트):
  0 2 * * * cd /path/to/workspace && ./scripts/backup.sh

## 3. 모니터링 체크리스트
- ops 탭 "신뢰도" — confidence<0.7 비율 ≤30% 유지
- "Run별 비용" — $1 초과 run 있으면 범위 축소 검토
- "최근 새로고침 이력" — status=failed 있으면 error_text 확인

## 4. 트러블슈팅 (라이브 검증으로 확인된 케이스)
4.1 `no such table: manual_override`
    → 구DB. python -c "from lg_dash.storage.db import connect, migrate; migrate(connect())" 실행
4.2 ANTHROPIC_API_KEY 누락
    → .env에 채우거나 --skip-llm으로 실행
4.3 다나와 robots.txt 위반 (rate limit)
    → HttpFetcher는 search.danawa.com에 10s 지연 강제. 외부 fetcher 사용 금지
4.4 다나와 카테고리 미스분류 (워셔에 드라이어 섞임)
    → 알려진 한계. 수동으로 product 행 삭제 또는 manual override
4.5 이미지 다운로드 실패
    → product_image.status='failed' 행 확인. 원본 URL 만료 가능. 재크롤 시도

## 5. 정상화 절차
- DB 손상: 가장 최근 백업 복원 cp -p backups/db.YYYY-MM-DD.sqlite storage/db.sqlite
- WAL 파일 정리: sqlite3 storage/db.sqlite "PRAGMA wal_checkpoint(TRUNCATE);"
```

### 3.3 DEPLOY.md outline

```
# 사내망 노출 가이드

⚠️ 외부 공개 금지 — 저작권(이미지) + API 비용(LLM) 노출 위험

## 패턴 A: SSH 터널 (default, 권장)
대상: 본인 + 신뢰 팀원 소수
방법:
  호스트에서: streamlit run src/lg_dash/app/dashboard.py --server.address 127.0.0.1
  클라이언트: ssh -L 8501:127.0.0.1:8501 user@host
  브라우저: http://localhost:8501
장점: 추가 인프라 0, 외부 노출 0
단점: 사용자마다 SSH 권한 필요

## 패턴 B: nginx reverse proxy + IP allowlist + basic auth (옵션)
대상: 사내 동일 서브넷 5+ 사용자
nginx config 예시:
  server {
    listen 80;
    server_name lg-dash.internal;
    allow 10.0.0.0/8;
    deny all;
    auth_basic "lg_dash";
    auth_basic_user_file /etc/nginx/.htpasswd;
    location / {
      proxy_pass http://127.0.0.1:8501;
      proxy_set_header Host $host;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection "upgrade";
    }
  }
htpasswd 생성: htpasswd -c /etc/nginx/.htpasswd teamuser

## ❌ 안티패턴
- streamlit run --server.address 0.0.0.0 (외부 노출 위험)
- Cloudflare Tunnel 등 외부 라우팅 (저작권 + 비용 노출)
- ngrok (테스트도 금지)
```

### 3.4 .env.example outline

```
# Anthropic API (LLM 요약 + fallback 매칭)
# 필수. 빈 값이면 pipeline.run --skip-llm 사용 가능
ANTHROPIC_API_KEY=

# SQLite 경로 (기본값 사용 권장)
LG_DASH_DB_PATH=storage/db.sqlite

# HTTP fetcher 식별자 (사내 정책 따라 조정)
CRAWL_USER_AGENT=LG_Dash/0.0.1 (+internal-use)

# 호스트별 기본 최소 지연 (초). search.danawa.com=10s는 코드에 하드코딩
CRAWL_RATE_LIMIT_PER_HOST=1.0
```

### 3.5 scripts/bootstrap.sh outline

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# 1. Python 3.11+ 확인
python3 --version | grep -E "3\.(1[1-9]|[2-9][0-9])" || { echo "Python 3.11+ required"; exit 1; }

# 2. venv
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate

# 3. install
pip install --upgrade pip --quiet
pip install -e . --quiet

# 4. .env
[ -f .env ] || cp .env.example .env
grep -q "^ANTHROPIC_API_KEY=." .env || echo "⚠️  .env: ANTHROPIC_API_KEY 미설정 — LLM 기능 사용 시 채우세요"

# 5. storage
mkdir -p storage/images storage/backups

# 6. DB migrate + seed
python -c "from lg_dash.storage.db import connect, db_path, migrate; migrate(connect(db_path()))"
python -m lg_dash.scripts.seed_brands

echo "✅ Bootstrap 완료. 다음:"
echo "   1) source .venv/bin/activate"
echo "   2) python -m lg_dash.pipeline.run --source danawa --brand lg --category washer --limit 3 --skip-llm"
echo "   3) streamlit run src/lg_dash/app/dashboard.py"
```

---

## 4. Implementation Order

| # | File | Lines (est) | Why this order |
|---|------|-----|----|
| 1 | `.env.example` | ~15 | 다른 모든 문서가 참조. 변수 이름 fix 먼저. |
| 2 | `scripts/bootstrap.sh` | ~30 | README가 첫 명령으로 호출하므로 미리 작성. |
| 3 | `docs/05-ops/RUNBOOK.md` | ~150 | 트러블슈팅 + 백업 — 운영의 핵심. |
| 4 | `docs/05-ops/DEPLOY.md` | ~120 | nginx config + SSH 터널 + 안티패턴. |
| 5 | `README.md` | ~180 | 모든 문서가 작성된 뒤 마지막으로 hub 역할로 작성. |

각 파일 작성 후 즉시 다음 검증:
- bootstrap.sh: fresh tmp dir에서 한 번 실행해 끝까지 통과 확인
- README 명령들: 위 순서대로 1회 실행해 모든 단계 동작 검증
- DEPLOY nginx: syntax-check만 (`nginx -t -c ...`), 실제 배포는 사내 환경 의존

---

## 5. Verification Plan

### 5.1 Manual smoke (Definition of Done)

신규 환경 시뮬레이션:
```bash
cd /tmp/lg-dash-smoke
git clone <repo> .  # or rsync
./scripts/bootstrap.sh
# .env 편집해 ANTHROPIC_API_KEY 입력
python -m lg_dash.pipeline.run --source danawa --brand lg --category washer --limit 1 --skip-llm
sqlite3 storage/db.sqlite "SELECT COUNT(*) FROM product;"  # >= 1
streamlit run src/lg_dash/app/dashboard.py &
curl -s http://localhost:8501 | grep -q "lg_dash"  # 또는 수동 접속
```

### 5.2 Doc-code 정합성 체크

각 README/RUNBOOK 명령을 fresh shell에서 순차 실행 → 통과하지 못한 명령 즉시 수정.

### 5.3 보안 체크

- `.gitignore`에 `.env`, `.venv/`, `storage/db.sqlite*`, `storage/images/` 포함 확인
- `git ls-files` 결과에 `.env` 없음 확인
- README + DEPLOY 양쪽에 외부 노출 차단 경고 포함 확인

---

## 6. Out of Scope (재확인)

| 항목 | 이유 |
|---|---|
| Docker / Compose | 단일 호스트 + venv로 충분. 추가 학습 비용 회피 |
| CI/CD 파이프라인 | 사내 단일 호스트, 자동 배포 불필요 |
| 자동 스케줄링 (cron 외) | 원 plan: "온디맨드만" |
| 멀티유저 인증 | 원 plan: "사내 신뢰 환경 가정" |
| 외부 공개·SaaS화 | 원 plan: "외부 공개 X" |
| Kubernetes / 고가용성 | Starter 레벨, 단일 호스트 |

---

## 7. Risks (Plan 대비 갱신)

| Risk | Mitigation 추가 명시 |
|---|---|
| 문서 drift | Verification Plan §5.2를 DoD 필수 항목으로 — fresh shell smoke 통과 시에만 PDCA 완료 |
| API 키 노출 | bootstrap.sh가 `.env` 검증 + `.gitignore` 사전 등록 |
| nginx 미설정으로 외부 노출 | DEPLOY에 IP allowlist `allow 10.0.0.0/8; deny all;` 강제 + 안티패턴 섹션 |
| 다나와 robots.txt 위반 | HttpFetcher 코드 보장 (이미 구현됨). RUNBOOK §4.3 명시 |

---

## 8. Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-22 | Initial draft (5 산출물 outline + 검증 계획) | aaaiiee |
