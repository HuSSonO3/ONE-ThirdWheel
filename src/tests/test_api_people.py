"""auth, users, departments, dashboards (spec 1.1–1.4, 2.1, 2.4)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.models import ConversationMember, UserClosure
from tests.conftest import ids, requires_db

pytestmark = requires_db


def test_health(api_as) -> None:
    assert api_as(None).get("/health").json() == {"status": "ok"}


def test_login_logout_and_me(api_as) -> None:
    anon = api_as(None)
    assert anon.get("/auth/me").status_code == 401
    bad = anon.post("/auth/login", json={"email": "alice.moreau@example.com", "password": "nope"})
    assert bad.status_code == 401 and bad.json()["code"] == "unauthenticated"
    alice = api_as("alice")
    me = alice.get("/auth/me").json()
    assert (me["name"], me["department_name"], me["manager_name"]) == ("Alice Moreau", "Marketing", "Hannah Weber")
    assert alice.post("/auth/logout").status_code == 204
    assert alice.get("/auth/me").status_code == 401


def test_login_is_case_insensitive_on_email(api_as) -> None:
    r = api_as(None).post("/auth/login", json={"email": "ALICE.MOREAU@example.com", "password": "password123"})
    assert r.status_code == 200


def test_validation_errors_use_the_error_shape(api_as) -> None:
    r = api_as(None).post("/auth/login", json={"email": "not-an-email"})
    assert r.status_code == 422 and r.json()["code"] == "validation_error" and r.json()["details"]


def test_user_directory_and_profile(api_as) -> None:
    bob = api_as("bob")
    found = bob.get("/users", params={"q": "da"}).json()
    assert [u["name"] for u in found] == ["Dana Kim"]
    profile = bob.get(f"/users/{ids.user('omar')}").json()
    assert len(profile["direct_reports"]) == 9 and profile["manager_name"] == "Maya Chen"
    assert bob.get(f"/users/{ids.user('bob')[:-1]}0").status_code in (404, 422)


def test_users_edit_their_own_profile_only(api_as) -> None:
    bob = api_as("bob")
    r = bob.patch(f"/users/{ids.user('bob')}", json={"job_title": "Senior Frontend Engineer"})
    assert r.status_code == 200 and r.json()["job_title"] == "Senior Frontend Engineer"
    assert bob.patch(f"/users/{ids.user('dana')}", json={"name": "X"}).status_code == 403
    assert bob.patch(f"/users/{ids.user('bob')}", json={"role": "admin"}).json()["code"] == "admin_required"


def test_admin_creates_a_user_into_a_department(api_as, session: Session) -> None:
    grace = api_as("grace")
    body = {"email": "new.hire@example.com", "password": "longenough", "name": "New Hire",
            "department_id": str(ids.department("Design")), "manager_id": str(ids.user("carol"))}
    assert api_as("bob").post("/users", json=body).status_code == 403
    r = grace.post("/users", json=body)
    assert r.status_code == 201
    new_id = r.json()["id"]
    assert grace.post("/users", json=body).json()["code"] == "email_taken"
    ancestors = set(session.scalars(select(UserClosure.ancestor_id).where(UserClosure.descendant_id == new_id)))
    assert {ids.user("carol"), ids.user("maya")} <= {str(a) for a in ancestors}
    assert session.scalar(select(ConversationMember).where(
        ConversationMember.conversation_id == ids.conv("design"), ConversationMember.user_id == new_id))
    assert api_as(None).post("/auth/login", json={"email": "new.hire@example.com",
                                                  "password": "longenough"}).status_code == 200


def test_manager_cycles_are_rejected(api_as) -> None:
    grace = api_as("grace")
    r = grace.patch(f"/users/{ids.user('omar')}", json={"manager_id": str(ids.user("bob"))})
    assert r.status_code == 409 and r.json()["code"] == "manager_cycle"
    assert grace.patch(f"/users/{ids.user('omar')}", json={"manager_id": str(ids.user("omar"))}).status_code == 409


def test_moving_a_manager_moves_the_subtree(api_as) -> None:
    grace = api_as("grace")
    assert grace.patch(f"/users/{ids.user('dana')}", json={"manager_id": str(ids.user("bob"))}).status_code == 200
    subs = {u["id"] for u in api_as("bob").get("/me/subordinates").json()}
    assert subs == {str(ids.user("dana"))}


def test_changing_department_moves_department_channel_membership(api_as) -> None:
    grace = api_as("grace")
    r = grace.patch(f"/users/{ids.user('ivy')}", json={"department_id": str(ids.department("Marketing"))})
    assert r.status_code == 200 and r.json()["department_name"] == "Marketing"
    ivy = api_as("ivy")
    kinds = {(c["kind"], c["name"]) for c in ivy.get("/conversations").json()}
    assert ("department", "marketing") in kinds and ("department", "design") not in kinds


def test_deactivated_users_are_logged_out(api_as) -> None:
    bob = api_as("bob")
    assert api_as("grace").patch(f"/users/{ids.user('bob')}", json={"active": False}).status_code == 200
    assert bob.get("/auth/me").status_code == 401


def test_subordinates_nearest_first(api_as) -> None:
    subs = api_as("maya").get("/me/subordinates").json()
    assert len(subs) == 29 and subs[0]["name"] in {"Carol Diaz", "Hannah Weber", "Omar Haddad", "Rafael Gomez",
                                                   "Sofia Lindqvist"}
    assert api_as("bob").get("/me/subordinates").json() == []


def test_dashboard_is_open_to_self_and_superiors_only(api_as) -> None:
    bob_id = ids.user("bob")
    assert {t["title"] for t in api_as("bob").get(f"/users/{bob_id}/tasks").json()} >= {
        "Fix the signup button 500 on the pricing page"}
    assert api_as("omar").get(f"/users/{bob_id}/tasks").status_code == 200
    assert api_as("maya").get(f"/users/{bob_id}/tasks", params={"status": ["in_progress"]}).json()[0]["status"] \
        == "in_progress"
    assert api_as("dana").get(f"/users/{bob_id}/tasks").status_code == 403


def test_departments(api_as) -> None:
    bob = api_as("bob")
    depts = bob.get("/departments").json()
    assert {d["name"]: d["member_count"] for d in depts}["Engineering"] == 10
    detail = bob.get(f"/departments/{ids.department('Finance')}").json()
    assert {m["name"] for m in detail["members"]} == {"Sofia Lindqvist", "Ahmed Saleh", "Mei Wong", "Jonas Berg"}

    grace = api_as("grace")
    assert bob.post("/departments", json={"name": "Legal"}).status_code == 403
    legal = grace.post("/departments", json={"name": "Legal"})
    assert legal.status_code == 201 and legal.json()["member_count"] == 0
    assert grace.post("/departments", json={"name": "legal"}).status_code == 409
    renamed = grace.patch(f"/departments/{legal.json()['id']}", json={"name": "Legal & Compliance"})
    assert renamed.json()["name"] == "Legal & Compliance"
