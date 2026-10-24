#!/usr/bin/env bash
# Replit deployment build: Python deps + production frontend bundle.
set -euo pipefail
cd "$(dirname "$0")/.."
pip install --quiet uv
(cd src && uv sync --frozen --no-dev)
(cd src/web && npm ci && npm run build)
