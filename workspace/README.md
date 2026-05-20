# lg_dash — 국내 생활가전 비교 대시보드

세탁기 / 건조기 / 통돌이 — 제조사 공식 + 다나와 + 쿠팡/원프라우 + 유튜브/블로그
4개 소스를 수집해 LLM으로 요약·감성 태그·정규화된 스펙 매칭을 수행하는
Notion 스타일 사내 비교 대시보드.

전체 구현 계획: `~/.claude/plans/frolicking-drifting-plum.md`

## 사용 범위 고지 (Internal Use Only)

이 도구는 **사내/팀 내부 의사결정 지원 목적**으로만 사용한다.

- 수집·캐싱한 이미지·텍스트는 외부 공개·재배포·상업적 이용을 금한다.
- 각 소스의 robots.txt 및 이용약관을 존중한다.
- Streamlit 서버는 사내망(localhost 또는 VPN) 한정으로 운영한다.
- 저작권·초상권·개인정보 침해 우려가 있는 데이터는 즉시 제거한다.

## 요구 사항

- Python 3.11+
- (선택) uv 또는 venv

## 설정

```bash
cd workspace
python3 -m venv .venv
.venv/bin/python -m pip install -e .
cp .env.example .env  # ANTHROPIC_API_KEY 등을 채운다
```

## M0 검증

```bash
PYTHONPATH=src .venv/bin/python -m lg_dash.scripts.seed_brands --config-dir config
```

기대 출력:

```
Applied migrations: 0001_init
Seeded 3 brand(s), 3 categorie(s).
  brand:   lg         LG전자
  brand:   samsung    삼성전자
  brand:   winia      위니아
  category: dryer       건조기
  category: top_loader  통돌이
  category: washer      세탁기
```

확인:

```bash
sqlite3 storage/db.sqlite ".tables"
sqlite3 storage/db.sqlite "SELECT id, display FROM brand;"
```

## 디렉터리 구조

```
workspace/
├─ config/                # brands, categories, attr_dictionary, sentiment_tags (YAML)
├─ src/lg_dash/
│   ├─ models.py          # Pydantic 모델
│   ├─ adapters/          # SourceAdapter 구현 (M1~M3)
│   ├─ pipeline/          # crawl/normalize/images/llm_analyze (M1~M5)
│   ├─ storage/           # SQLite db, migrations, repo
│   ├─ llm/               # Anthropic 클라이언트 + 프롬프트 (M5)
│   ├─ app/               # Streamlit UI (M6~M7)
│   └─ scripts/           # seed_brands 등
├─ tests/                 # 어댑터 계약, 정규화 룰, LLM 스키마
└─ storage/               # 런타임 산출물 (gitignore: db.sqlite, images/)
```

## 마일스톤

| M | 산출물 | 상태 |
|---|---|---|
| M0 | 부트스트랩 — pyproject, 마이그레이션, models, repo, seed | ✅ |
| M1 | 다나와 어댑터 종단간 | 대기 |
| M2 | 스펙 정규화 (룰/퍼지) | 대기 |
| M3 | 나머지 3개 어댑터 (manufacturer/coupang/youtube) | 대기 |
| M4 | 이미지 수집 | 대기 |
| M5 | LLM 분석 (요약+감성태그) | 대기 |
| M6 | Streamlit MVP (목록/카드 + 상세) | 대기 |
| M7 | 비교 뷰 + 운영 뷰 | 대기 |
| M8 | LLM 폴백 매칭 + 수동 오버라이드 | 대기 |
