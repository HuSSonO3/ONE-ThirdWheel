import yaml
from fastapi import FastAPI

from api import config, errors
from api.routers import admin, conversations, messages, people, work, ws

app = FastAPI(title="Company Chat API")
errors.install(app)
for module in (people, conversations, messages, work, admin, ws):
    app.include_router(module.router)

# The served OpenAPI document is the contract itself, not FastAPI's derivation of the code.
_contract = yaml.safe_load(config.CONTRACT.read_text())
app.openapi = lambda: _contract  # type: ignore[method-assign]


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}
