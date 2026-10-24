"""Schema behaviour that only Postgres can show: closure triggers, constraints, seeded data."""

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from tests.conftest import requires_db

pytestmark = requires_db
FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def add_user(db: Connection, name: str, manager: uuid.UUID | None = None) -> uuid.UUID:
    uid = uuid.uuid4()
    db.execute(
        text("INSERT INTO users (id, email, password_hash, name, manager_id) VALUES (:id, :e, 'x', :n, :m)"),
        {"id": uid, "e": f"{uid}@test", "n": name, "m": manager},
    )
    return uid


def closure(db: Connection, ids: dict[str, uuid.UUID]) -> set[tuple[str, str, int]]:
    names = {v: k for k, v in ids.items()}
    rows = db.execute(
        text("SELECT ancestor_id, descendant_id, depth FROM user_closure WHERE descendant_id = ANY(:ids)"),
        {"ids": list(ids.values())},
    )
    return {(names[a], names[d], depth) for a, d, depth in rows}


def test_closure_follows_inserts_and_manager_moves(db: Connection) -> None:
    ids = {"a": add_user(db, "A")}
    ids["b"] = add_user(db, "B", ids["a"])
    ids["c"] = add_user(db, "C", ids["b"])
    ids["d"] = add_user(db, "D")
    assert closure(db, ids) == {
        ("a", "a", 0), ("b", "b", 0), ("c", "c", 0), ("d", "d", 0),
        ("a", "b", 1), ("b", "c", 1), ("a", "c", 2),
    }

    # Moving B under D moves B's whole subtree.
    db.execute(text("UPDATE users SET manager_id = :d WHERE id = :b"), ids)
    assert closure(db, ids) == {
        ("a", "a", 0), ("b", "b", 0), ("c", "c", 0), ("d", "d", 0),
        ("d", "b", 1), ("b", "c", 1), ("d", "c", 2),
    }

    # Detaching B makes it a root.
    db.execute(text("UPDATE users SET manager_id = NULL WHERE id = :b"), ids)
    assert ("d", "c", 2) not in closure(db, ids)
    assert ("b", "c", 1) in closure(db, ids)


def test_closure_rejects_cycles(db: Connection) -> None:
    a = add_user(db, "A")
    b = add_user(db, "B", a)
    with pytest.raises(IntegrityError, match="manager cycle"), db.begin_nested():
        db.execute(text("UPDATE users SET manager_id = :b WHERE id = :a"), {"a": a, "b": b})


def test_one_dm_per_pair(db: Connection) -> None:
    db.execute(text("INSERT INTO conversations (kind, member_key) VALUES ('dm', 'x:y')"))
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(text("INSERT INTO conversations (kind, member_key) VALUES ('dm', 'x:y')"))


def test_ai_principal_exists(db: Connection) -> None:
    scopes = db.execute(text("SELECT scopes FROM ai_agent WHERE name = 'assistant'")).scalar_one()
    assert set(scopes) == {"conversations:read", "suggestions:create", "suggestions:status"}
    assert db.execute(text("SELECT count(*) FROM event_consumers WHERE name = 'ai'")).scalar_one() == 1


def test_seeded_database_matches_fixtures(db: Connection) -> None:
    if not db.execute(text("SELECT count(*) FROM users")).scalar_one():
        pytest.skip("database not seeded (run scripts/seed.py)")
    for table, name in [("users", "users"), ("conversations", "conversations"), ("messages", "messages"),
                        ("tasks", "tasks"), ("ai_proposals", "suggestions")]:
        expected = len(json.loads((FIXTURES / f"{name}.json").read_text()))
        assert db.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == expected, table
    # One message.created event per message, in time order.
    assert db.execute(text("SELECT count(*) FROM events WHERE type = 'message.created'")).scalar_one() == len(
        json.loads((FIXTURES / "messages.json").read_text()))
    assert db.execute(text(
        "SELECT bool_and(created_at >= prev) FROM (SELECT created_at, "
        "lag(created_at, 1, '-infinity') OVER (ORDER BY id) AS prev FROM events) x"
    )).scalar_one()
