#!/usr/bin/env sh
# Regenerates api/schemas/contract.py from contracts/openapi.yaml. CI fails if this produces a diff.
set -e
cd "$(dirname "$0")/.."
uv run datamodel-codegen \
  --input contracts/openapi.yaml --input-file-type openapi \
  --output api/schemas/contract.py \
  --output-model-type pydantic_v2.BaseModel \
  --target-python-version 3.12 \
  --use-annotated --use-standard-collections --use-union-operator \
  --field-constraints --use-double-quotes --collapse-root-models \
  --enum-field-as-literal all \
  --disable-timestamp --formatters black isort
