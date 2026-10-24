#!/usr/bin/env sh
# Regenerates web/src/api/ from contracts/openapi.yaml. CI fails if this produces a diff.
set -e
cd "$(dirname "$0")/../web"
npx openapi-typescript ../contracts/openapi.yaml -o src/api/schema.ts
