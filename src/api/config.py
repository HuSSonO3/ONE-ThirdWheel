import os
from datetime import timedelta
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://chat:chat@localhost:5432/chat")
# Hosts such as Replit hand out plain postgres:// URLs; SQLAlchemy needs the psycopg driver named.
for _prefix in ("postgres://", "postgresql://"):
    if DATABASE_URL.startswith(_prefix):
        DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL.removeprefix(_prefix)
FILES_DIR = Path(os.environ.get("FILES_DIR", SRC / ".data" / "files"))
SESSION_TTL = timedelta(days=int(os.environ.get("SESSION_TTL_DAYS", "14")))
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
SUGGESTION_TTL = timedelta(days=int(os.environ.get("SUGGESTION_TTL_DAYS", "7")))
# Run the AI worker inside the API process so proposals are pushed over WebSocket live.
AI_WORKER_ENABLED = os.environ.get("AI_WORKER_ENABLED", "false").lower() == "true"
AI_DEBOUNCE_SECONDS = float(os.environ.get("AI_DEBOUNCE_SECONDS", "5"))
AI_POLL_SECONDS = float(os.environ.get("AI_POLL_SECONDS", "2"))
WEB_DIST = Path(os.environ.get("WEB_DIST", SRC / "web" / "dist"))
CONTRACT = SRC / "contracts" / "openapi.yaml"
# Browser origins allowed to open the WebSocket (cross-site WebSocket hijacking guard).
ALLOWED_ORIGINS = {o.strip() for o in os.environ.get(
    "ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()}
