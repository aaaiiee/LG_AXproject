#!/usr/bin/env bash
# lg_dash one-shot bootstrap: venv + deps + .env + DB migrate + seed.
# Idempotent — safe to re-run.
set -euo pipefail

# Move to workspace root (parent of scripts/)
cd "$(dirname "$0")/.."

echo "[1/6] Python 3.11+ check..."
PY_OK=$(python3 -c 'import sys; print("ok" if sys.version_info >= (3, 11) else "")')
if [ -z "$PY_OK" ]; then
  echo "  ❌ Python 3.11+ required. Found: $(python3 --version)"
  exit 1
fi
echo "  ✅ $(python3 --version)"

echo "[2/6] venv..."
if [ ! -d .venv ]; then
  python3 -m venv .venv
  echo "  ✅ created .venv"
else
  echo "  ✅ .venv exists"
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "[3/6] dependencies..."
pip install --upgrade pip --quiet
pip install -e . --quiet
echo "  ✅ installed (editable)"

echo "[4/6] .env..."
if [ ! -f .env ]; then
  cp .env.example .env
  echo "  ✅ copied .env.example → .env"
fi
if ! grep -q "^ANTHROPIC_API_KEY=.\+" .env; then
  echo "  ⚠️  .env: ANTHROPIC_API_KEY 미설정 — LLM 기능 사용 시 채우세요"
fi

echo "[5/6] storage dirs..."
mkdir -p storage/images storage/backups
echo "  ✅ storage/images, storage/backups"

echo "[6/6] DB migrate + brand seed..."
python -c "from lg_dash.storage.db import connect, db_path, migrate; migrate(connect(db_path()))"
python -m lg_dash.scripts.seed_brands >/dev/null
echo "  ✅ migrated + seeded"

echo ""
echo "✅ Bootstrap complete. Next steps:"
echo "   1) source .venv/bin/activate"
echo "   2) python -m lg_dash.pipeline.run --source danawa --brand lg --category washer --limit 3 --skip-llm"
echo "   3) streamlit run src/lg_dash/app/dashboard.py"
