# 운영 Runbook

> 일상 운영 (백업, 모니터링, 트러블슈팅) 가이드. 사내 한정.
> 신규 설치는 [README](../../README.md) 참조.

---

## 1. 일상 새로고침

### 1.1 UI에서
1. Streamlit 대시보드 (`streamlit run src/lg_dash/app/dashboard.py`) 접속
2. ⚙️ 운영 탭 → "최근 새로고침 이력" 확인 (최근 status가 `success`인지)
3. (TBD) 목록 탭에서 카테고리 선택 → "선택 새로고침" 버튼 *(UI 구현 시점에 따라 미존재 가능)*

### 1.2 CLI에서 (권장)
```bash
source .venv/bin/activate

# 가장 빠른 종단간 실행 (crawl + normalize, LLM 생략)
python -m lg_dash.pipeline.run \
  --source danawa --brand lg --category washer \
  --limit 3 --skip-llm

# LLM 분석 포함 (비용 발생)
python -m lg_dash.pipeline.run \
  --source danawa --brand lg --category washer \
  --limit 3
```

### 1.3 새로고침 직후 점검
운영 탭 → `Run별 비용` 표 → 마지막 행의 `cost_usd`가 $1를 넘으면 ⚠️ 경고 배지 표시.
초과 시: 범위 축소 (limit ↓) 또는 `--skip-llm` 사용.

---

## 2. 백업

### 2.1 일일 — DB 파일
```bash
mkdir -p storage/backups
cp -p storage/db.sqlite storage/backups/db.$(date +%F).sqlite
```

WAL 모드라 `db.sqlite-wal` / `db.sqlite-shm`도 있지만, 백업 직전에 checkpoint 후 main 파일만 떠도 안전:
```bash
sqlite3 storage/db.sqlite "PRAGMA wal_checkpoint(TRUNCATE);"
cp -p storage/db.sqlite storage/backups/db.$(date +%F).sqlite
```

### 2.2 주간 — 이미지
```bash
tar -czf storage/backups/images.$(date +%F).tar.gz storage/images/
```

### 2.3 (선택) cron 등록 — 사내 호스트 한정
```cron
# /etc/cron.d/lg_dash-backup (root 또는 dedicated user)
0 2 * * * cd /opt/lg_dash/workspace && \
  sqlite3 storage/db.sqlite "PRAGMA wal_checkpoint(TRUNCATE);" && \
  cp -p storage/db.sqlite storage/backups/db.$(date +\%F).sqlite

0 3 * * 0 cd /opt/lg_dash/workspace && \
  tar -czf storage/backups/images.$(date +\%F).tar.gz storage/images/
```

### 2.4 보존 정책 (권장)
- 일일 백업: 14일
- 주간 백업: 8주
- 정리 스크립트는 별도로 작성 (예: `find storage/backups -name 'db.*.sqlite' -mtime +14 -delete`)

---

## 3. 모니터링 체크리스트 (주 1회)

운영 탭 → 다음 4가지 확인:

| 지표 | 임계치 | 대응 |
|---|---|---|
| **개요 > 정규화 스펙** | 제품 수 × ≥6 | 적으면 attr_dictionary 시놋 보강 또는 라이브 어댑터 점검 |
| **신뢰도 > <0.5 / 0.5~0.7 합** | ≤30% | 초과 시 manual override 또는 시놋 추가 |
| **Run별 비용** | 단일 run ≤$1 | 초과 시 LLM 폴백 범위 축소 또는 `--skip-llm` |
| **최근 새로고침 이력** | status=success | failed 발생 시 error_text 확인 |

---

## 4. 트러블슈팅

라이브 검증과 일상 운영에서 실제 발생한 케이스.

### 4.1 `sqlite3.OperationalError: no such table: manual_override`
**원인**: 구 버전(0.0.0 ~ M7) DB에서 M8 migration 0002가 적용되지 않음.
**대응**:
```bash
source .venv/bin/activate
python -c "from lg_dash.storage.db import connect, db_path, migrate; migrate(connect(db_path()))"
```
또는 `pipeline.normalize`/`pipeline.run`을 한 번 실행하면 자동 migrate됨 (M8 fix).

### 4.2 `ANTHROPIC_API_KEY` 누락 / 빈 값
**원인**: `.env`에 키 미설정.
**증상**: `anthropic.AuthenticationError` 또는 `llm_analyze` 단계에서 401.
**대응**:
- 임시 회피: `pipeline.run --skip-llm`, `pipeline.crawl + pipeline.normalize`까지만 사용
- 정식 대응: `.env`의 `ANTHROPIC_API_KEY=`에 실제 키 채우기

### 4.3 다나와 robots.txt rate limit 위반 / 403
**원인**: `search.danawa.com` Crawl-delay: 10s 미준수.
**보장**: `src/lg_dash/adapters/fetcher.py` `HttpFetcher`에 host별 최소 지연 하드코딩 (search.danawa.com=10s, prod.danawa.com=2s).
**대응**: 외부 fetcher (직접 httpx/requests 호출 등)로 우회 금지. 항상 `HttpFetcher` 경유.

### 4.4 다나와 카테고리 미스분류 (워셔 검색에 건조기 섞임)
**원인**: Danawa 검색 결과가 카테고리 무관하게 반환됨. discover-side 필터링 미구현 (의도적 deferred, deploy-guide 범위 외).
**증상**: `product` 테이블에 category_id=`washer`인데 model_code가 RH18WTSN(드라이어) 같은 항목 존재.
**대응**:
```sql
-- 잘못 분류된 product 삭제 (예: pcode 76550339)
DELETE FROM product WHERE id = 2;
-- 또는 manual override로 카테고리 강제 (현재 UI 미지원, SQL 직접)
```

### 4.5 이미지 다운로드 실패 (`product_image.status='failed'`)
**원인**: 원본 URL 만료, 호스트 차단, 또는 Content-Type 불일치.
**대응**:
```bash
# 실패 행 확인
sqlite3 storage/db.sqlite "SELECT product_id, source_id, original_url FROM product_image WHERE status='failed';"

# 해당 제품 재크롤 (이미지 우선순위에 따라 다른 소스 시도)
python -m lg_dash.pipeline.images --product-id <id>
```

---

## 5. 비상 복구

### 5.1 DB 손상 / 의심
```bash
# 무결성 체크
sqlite3 storage/db.sqlite "PRAGMA integrity_check;"

# 손상 시 최근 백업 복원
cp -p storage/backups/db.YYYY-MM-DD.sqlite storage/db.sqlite
rm -f storage/db.sqlite-wal storage/db.sqlite-shm
```

### 5.2 WAL 파일 비대화 (수 GB)
```bash
sqlite3 storage/db.sqlite "PRAGMA wal_checkpoint(TRUNCATE);"
```

### 5.3 이미지 디렉터리 디스크 압박
```bash
du -sh storage/images
# 큰 제품 식별
du -sh storage/images/*/ | sort -h | tail -10
# 만료/실패 이미지 삭제 + DB 행 정리는 별도 작업
```

### 5.4 Streamlit 데드락 / 응답 없음
```bash
pkill -f "streamlit run"
streamlit run src/lg_dash/app/dashboard.py
```

---

## 6. 보안 체크 (월 1회)

- [ ] `git status` — `.env`가 staged/tracked 아닌지 확인
- [ ] `git log -- .env` — 과거 커밋에 `.env` 노출 이력 없는지 확인
- [ ] `.gitignore`에 `.env`, `storage/db.sqlite*`, `storage/images/` 포함 확인
- [ ] Streamlit 서버 노출 범위 확인 — `netstat -an | grep 8501` (0.0.0.0 바인딩 금지, 127.0.0.1만)
- [ ] nginx 사용 시 IP allowlist + basic auth 동작 확인 ([DEPLOY](DEPLOY.md) §B)

---

## 7. 참고

- 설계 문서: [docs/02-design/features/deploy-guide.design.md](../02-design/features/deploy-guide.design.md)
- 완성 보고서: [docs/04-report/lg_dash-completion-report.md](../04-report/lg_dash-completion-report.md)
- 사내망 노출: [DEPLOY.md](DEPLOY.md)
