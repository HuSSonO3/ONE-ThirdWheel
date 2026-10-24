#!/usr/bin/env bash
# Replit deployment run: migrate, seed demo data into an empty database, serve API + frontend on one port.
set -euo pipefail
cd "$(dirname "$0")/../src"
export AI_WORKER_ENABLED="${AI_WORKER_ENABLED:-true}"
export AI_TOOL_CHOICE="${AI_TOOL_CHOICE:-auto}"
export COOKIE_SECURE="${COOKIE_SECURE:-true}"
PY=.venv/bin/python
$PY -m alembic upgrade head
if [ "${SEED_IF_EMPTY:-true}" = "true" ]; then
  $PY - <<'PY' && $PY scripts/seed.py
import sys
from sqlalchemy import func, select
from api.db import session_factory
from api.models import User
with session_factory() as db:
    sys.exit(0 if db.scalar(select(func.count()).select_from(User)) == 0 else 1)
PY
fi
exec $PY -m uvicorn api.main:app --host 0.0.0.0 --port "${PORT:-8000}"
