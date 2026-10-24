"""Test harness.

DB tests run against the seeded database (scripts/seed.py) inside one transaction per test that is
always rolled back. Every HTTP response made through `api_as` is validated against
contracts/openapi.yaml for its operation and status code, so each API test is also a conformance
test, and the operations exercised are recorded for tests/test_zz_conformance.py.
"""

import os
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from sqlalchemy import Connection, create_engine
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_fixtures as fx  # noqa: E402  (fixture ids: fx.U, fx.C, fx.uid)

requires_db = pytest.mark.skipif("DATABASE_URL" not in os.environ, reason="needs DATABASE_URL (migrated Postgres)")
PASSWORD = "password123"
EXERCISED: set[str] = set()


# ---------------------------------------------------------------- contract validation

class Contract:
    METHODS = ("get", "post", "put", "patch", "delete")

    def __init__(self, path: Path):
        self.spec = yaml.safe_load(path.read_text())
        self.registry = Registry().with_resource("urn:contract", Resource(self.spec, specification=DRAFT202012))
        self.routes = []
        for template, ops in self.spec["paths"].items():
            pattern = re.compile("^" + re.sub(r"\{[^/]+\}", "[^/]+", template) + "$")
            for method in self.METHODS:
                if method in ops:
                    self.routes.append((template.count("{"), method, pattern, template, ops[method]))
        self.routes.sort(key=lambda r: r[0])  # static segments win over parameters
        self.operation_ids = {r[4]["operationId"] for r in self.routes}

    def check(self, method: str, url: str, status: int, body: Any) -> None:
        path = urlsplit(url).path
        match = next((r for r in self.routes if r[1] == method.lower() and r[2].match(path)), None)
        assert match, f"{method} {path} is not in the contract"
        _, _, _, template, op = match
        EXERCISED.add(op["operationId"])
        response = op["responses"].get(str(status))
        assert response is not None, f"{op['operationId']} returned undocumented status {status}: {body}"
        pointer = f"#/paths/{template.replace('~', '~0').replace('/', '~1')}/{method.lower()}/responses/{status}"
        if "$ref" in response:
            pointer, response = response["$ref"], self._resolve(response["$ref"])
        if "application/json" not in response.get("content", {}):
            return
        schema = {"$ref": f"urn:contract{pointer}/content/application~1json/schema"}
        errors = sorted(Draft202012Validator(schema, registry=self.registry, format_checker=FormatChecker())
                        .iter_errors(body), key=lambda e: list(e.path))
        assert not errors, f"{op['operationId']} {status} breaks the contract: " + "; ".join(
            f"{'/'.join(map(str, e.path))}: {e.message[:200]}" for e in errors[:5])

    def _resolve(self, ref: str) -> dict:
        node: Any = self.spec
        for part in ref.removeprefix("#/").split("/"):
            node = node[part]
        return node


CONTRACT = Contract(ROOT / "contracts" / "openapi.yaml")


# ---------------------------------------------------------------- database

@pytest.fixture
def db() -> Iterator[Connection]:
    """A raw connection inside a transaction that is always rolled back (schema tests)."""
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        tx = conn.begin()
        try:
            yield conn
        finally:
            tx.rollback()
    engine.dispose()


@pytest.fixture
def app_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[sessionmaker[Session]]:
    """Point the app at one connection whose outer transaction is rolled back after the test."""
    from api import db as db_module
    from api import realtime
    from api.routers import ws

    engine = create_engine(os.environ["DATABASE_URL"])
    conn = engine.connect()
    tx = conn.begin()
    factory = sessionmaker(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    monkeypatch.setattr(db_module, "session_factory", factory)
    monkeypatch.setattr(realtime, "PRESENCE_GRACE_S", 0.2)
    realtime.hub._conns.clear()
    realtime.hub._grace.clear()
    ws._last_typing.clear()
    try:
        yield factory
    finally:
        tx.rollback()
        conn.close()
        engine.dispose()


# ---------------------------------------------------------------- HTTP clients

class Api:
    """A logged-in user. Every response is checked against the contract."""

    def __init__(self, client, token: str | None, key: str | None = None):
        self.client, self.token, self.key = client, token, key
        self.id = fx.U.get(key) if key else None

    @property
    def headers(self) -> dict[str, str]:
        return {"Cookie": f"session={self.token}"} if self.token else {}

    def request(self, method: str, url: str, **kwargs: Any):
        headers = {**self.headers, **kwargs.pop("headers", {})}
        response = self.client.request(method, url, headers=headers, **kwargs)
        self.client.cookies.clear()
        is_json = response.headers.get("content-type", "").startswith("application/json")
        CONTRACT.check(method, url, response.status_code, response.json() if is_json else None)
        return response

    def get(self, url: str, **kw: Any):
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw: Any):
        return self.request("POST", url, **kw)

    def put(self, url: str, **kw: Any):
        return self.request("PUT", url, **kw)

    def patch(self, url: str, **kw: Any):
        return self.request("PATCH", url, **kw)

    def delete(self, url: str, **kw: Any):
        return self.request("DELETE", url, **kw)

    def ws(self):
        return self.client.websocket_connect("/ws", headers=self.headers)


@pytest.fixture
def client(app_db: sessionmaker[Session]):
    from fastapi.testclient import TestClient

    from api.main import app

    with TestClient(app) as c:
        yield c


def email(key: str) -> str:
    return next(f"{name.lower().replace(' ', '.')}@example.com" for k, name, *_ in fx.PEOPLE if k == key)


@pytest.fixture
def api_as(client):
    """`api_as("alice")` logs in a fixture user; `api_as(None)` is anonymous."""
    sessions: dict[str | None, Api] = {}

    def login(key: str | None) -> Api:
        if key not in sessions:
            if key is None:
                sessions[key] = Api(client, None)
            else:
                anon = Api(client, None)
                r = anon.post("/auth/login", json={"email": email(key), "password": PASSWORD})
                assert r.status_code == 200, r.text
                sessions[key] = Api(client, r.cookies.get("session") or _cookie(r), key)
        return sessions[key]

    return login


def _cookie(response) -> str:
    header = response.headers.get("set-cookie", "")
    return header.split("session=", 1)[1].split(";", 1)[0]


@pytest.fixture
def session(app_db: sessionmaker[Session]) -> Iterator[Session]:
    """An ORM session on the test connection, for calling services and access functions directly."""
    s = app_db()
    try:
        yield s
    finally:
        s.close()


# ---------------------------------------------------------------- fixture ids

class Ids:
    """Fixture ids as strings (what JSON carries)."""

    user = staticmethod(lambda key: fx.U[key])
    conv = staticmethod(lambda key: fx.C[key])
    department = staticmethod(lambda name: fx.D[name])
    message = staticmethod(lambda key: fx.uid("message", key))
    task = staticmethod(lambda key: fx.uid("task", key))
    suggestion = staticmethod(lambda key: fx.uid("suggestion", key))
    mention = staticmethod(fx.mention)


ids = Ids()
