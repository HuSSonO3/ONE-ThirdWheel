from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api import ai_host, config, errors
from api.routers import admin, conversations, messages, people, work, ws


@asynccontextmanager
async def lifespan(_: FastAPI):
    worker = ai_host.start()
    yield
    if worker:
        worker[1].set()


app = FastAPI(title="Company Chat API", lifespan=lifespan)
errors.install(app)
for module in (people, conversations, messages, work, admin, ws):
    app.include_router(module.router)

# The served OpenAPI document is the contract itself, not FastAPI's derivation of the code.
_contract = yaml.safe_load(config.CONTRACT.read_text())
app.openapi = lambda: _contract  # type: ignore[method-assign]


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


# Single-service deployments (Replit): serve the built frontend from the API so the session
# cookie and WebSocket stay same-origin. Registered last, so API routes always win.
if config.WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=config.WEB_DIST, html=True), name="web")
