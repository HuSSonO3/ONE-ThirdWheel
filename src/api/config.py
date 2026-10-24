import os
from datetime import timedelta
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://chat:chat@localhost:5432/chat")
FILES_DIR = Path(os.environ.get("FILES_DIR", SRC / ".data" / "files"))
SESSION_TTL = timedelta(days=int(os.environ.get("SESSION_TTL_DAYS", "14")))
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
SUGGESTION_TTL = timedelta(days=int(os.environ.get("SUGGESTION_TTL_DAYS", "7")))
CONTRACT = SRC / "contracts" / "openapi.yaml"
