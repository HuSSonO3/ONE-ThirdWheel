"""tasks, projects and AI suggestions (spec 2.2–2.4, 2.7, 3.2, 3.3)."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.orm import Session

from api.models import AiProposal
from api.services.suggestions import ServiceBackend
from tests.conftest import ids, requires_db

pytestmark = requires_db


def titles(rows: list[dict]) -> set[str]:
    return {r["title"] for r in rows}


def test_department_tab_shows_every_members_tasks(api_as) -> None:
    rows = api_as("chloe").get(f"/conversations/{ids.conv('engineering')}/tasks").json()
    assert "Fix the signup button 500 on the pricing page" in titles(rows)  # spawned in #website, Bob is Eng
    assert {r["assignee"]["department_id"] for r in rows} == {str(ids.department("Engineering"))}


def test_other_tabs_show_only_tasks_spawned_there(api_as) -> None:
    rows = api_as("alice").get(f"/conversations/{ids.conv('website')}/tasks").json()
    assert {r["source_conversation"]["name"] for r in rows} == {"website"}
    assert "Run a Lighthouse audit on the new landing page" in titles(rows)
    marketing = api_as("alice").get(f"/conversations/{ids.conv('marketing')}/tasks").json()
    assert "Fix the signup button 500 on the pricing page" not in titles(marketing)


def test_task_filters(api_as) -> None:
    omar = api_as("omar")
    url = f"/conversations/{ids.conv('engineering')}/tasks"
    assert {r["project"] for r in omar.get(url, params={"project": "infra"}).json()} == {"infra"}
    only_bob = omar.get(url, params={"assignee": str(ids.user("bob"))}).json()
    assert {r["assignee"]["name"] for r in only_bob} == {"Bob Tan"}
    done = omar.get(url, params={"status": ["done"]}).json()
    assert done and {r["status"] for r in done} == {"done"}
    assert "infra" in omar.get("/projects").json()


def test_create_task_enforces_the_assignment_rule(api_as) -> None:
    ivy = api_as("ivy")
    url = f"/conversations/{ids.conv('website')}/tasks"
    r = ivy.post(url, json={"title": "Update GA4 tag", "assignee_id": str(ids.user("ethan"))})
    assert r.status_code == 403 and r.json()["code"] == "assignee_not_member"
    ok = ivy.post(url, json={"title": "Review the hero copy", "assignee_id": str(ids.user("alice")),
                             "project": "website", "source_message_ids": [str(ids.message("f3m"))]})
    assert ok.status_code == 201 and ok.json()["source_message_ids"] == [str(ids.message("f3m"))]
    assert not ok.json()["created_by_ai"]
    bad_source = ivy.post(url, json={"title": "x", "assignee_id": str(ids.user("alice")),
                                     "source_message_ids": [str(ids.message("p19"))]})
    assert bad_source.status_code == 422
    outsider = api_as("sofia").post(url, json={"title": "x", "assignee_id": str(ids.user("bob"))})
    assert outsider.status_code == 403 and outsider.json()["code"] == "not_a_member"


def test_direct_manager_exception_copies_the_source_text(api_as) -> None:
    r = api_as("omar").post(f"/conversations/{ids.conv('website')}/tasks", json={
        "title": "Check the GA4 tag", "assignee_id": str(ids.user("ethan")),
        "source_message_ids": [str(ids.message("p3"))]})
    assert r.status_code == 201
    assert "GA4 tag is outdated" in r.json()["description_md"]
    ethan = api_as("ethan")
    assert ethan.get(f"/tasks/{r.json()['id']}").status_code == 200
    embed = ethan.get("/embeds", params={"url": f"/c/{ids.conv('website')}/m/{ids.message('p3')}"}).json()
    assert embed["type"] == "message"  # #website is public; the stub case is covered in test_api_misc


def test_update_task_status_history_and_reassignment(api_as) -> None:
    bob = api_as("bob")
    task = ids.task("t1")
    r = bob.patch(f"/tasks/{task}", json={"status": "done"})
    assert r.json()["status"] == "done" and r.json()["completed_at"]
    reopened = bob.patch(f"/tasks/{task}", json={"status": "open"}).json()
    assert reopened["completed_at"] is None
    history = bob.get(f"/tasks/{task}/history").json()
    assert [(h["field"], h["old_value"], h["new_value"]) for h in history][-2:] == [
        ("status", "in_progress", "done"), ("status", "done", "open")]
    denied = bob.patch(f"/tasks/{task}", json={"assignee_id": str(ids.user("ethan"))})
    assert denied.status_code == 403
    moved = bob.patch(f"/tasks/{task}", json={"assignee_id": str(ids.user("dana"))})
    assert moved.json()["assignee"]["name"] == "Dana Kim"
    assert bob.patch(f"/tasks/{task}", json={"title": None}).status_code == 422


def test_tasks_are_only_visible_through_can_see(api_as) -> None:
    assert api_as("ivy").get(f"/tasks/{ids.task('h3')}").status_code == 403
    assert api_as("ivy").get(f"/tasks/{ids.task('h3')}/history").status_code == 403
    assert api_as("ivy").patch(f"/tasks/{ids.task('h3')}", json={"status": "done"}).status_code == 403
    assert api_as("maya").get(f"/tasks/{ids.task('h3')}").status_code == 200  # superior
    assert api_as("ivy").get(f"/tasks/{uuid.uuid4()}").status_code == 404
    assert "payments" not in api_as("ivy").get("/projects").json()


# ---------------------------------------------------------------- suggestions

def test_conversation_suggestions_are_members_only(api_as) -> None:
    rows = api_as("alice").get(f"/conversations/{ids.conv('website')}/suggestions").json()
    assert {r["id"] for r in rows} >= {str(ids.suggestion("s5")), str(ids.suggestion("s7"))}
    pending = api_as("alice").get(f"/conversations/{ids.conv('website')}/suggestions",
                                  params={"status": "pending"}).json()
    assert {r["status"] for r in pending} == {"pending"}
    assert api_as("sofia").get(f"/conversations/{ids.conv('website')}/suggestions").status_code == 403


def test_can_accept_reflects_the_assignment_rule(api_as) -> None:
    def card(user: str, key: str) -> dict:
        rows = api_as(user).get(f"/conversations/{ids.conv('website')}/suggestions").json()
        return next(r for r in rows if r["id"] == str(ids.suggestion(key)))

    assert card("alice", "s5")["can_accept"] is False  # Ethan isn't in #website
    assert card("omar", "s5")["can_accept"] is True  # but he's Omar's direct report
    assert card("alice", "s5")["payload"]["assignee_is_member"] is False


def test_my_suggestions_only_where_i_am_a_member(api_as) -> None:
    assert {r["id"] for r in api_as("mei").get("/me/suggestions").json()} == {str(ids.suggestion("s6"))}
    assert api_as("ethan").get("/me/suggestions").json() == []  # s5 proposes Ethan, who isn't in #website


def test_accept_creates_the_task_as_proposed(api_as) -> None:
    sofia = api_as("sofia")
    r = sofia.post(f"/suggestions/{ids.suggestion('s6')}/accept")
    assert r.status_code == 200
    body = r.json()
    assert body["suggestion"]["status"] == "accepted" and body["suggestion"]["decided_by"] == str(ids.user("sofia"))
    task = body["task"]
    assert task["created_by_ai"] and task["created_by"] == str(ids.user("sofia"))
    assert task["assignee"]["name"] == "Mei Wong" and task["project"] == "payments"
    assert task["source_message_ids"] == [str(ids.message("p8"))]
    again = sofia.post(f"/suggestions/{ids.suggestion('s6')}/accept")
    assert again.status_code == 409 and again.json()["code"] == "already_decided"


def test_accept_is_blocked_by_the_assignment_rule(api_as) -> None:
    r = api_as("alice").post(f"/suggestions/{ids.suggestion('s5')}/accept")
    assert r.status_code == 403 and r.json()["code"] == "assignee_not_member"
    assert api_as("omar").post(f"/suggestions/{ids.suggestion('s5')}/accept").status_code == 200


def test_non_members_cannot_decide(api_as) -> None:
    assert api_as("bob").post(f"/suggestions/{ids.suggestion('s6')}/reject").status_code == 403


def test_modify_and_reject(api_as) -> None:
    leo = api_as("leo")
    r = leo.post(f"/suggestions/{ids.suggestion('s7')}/modify",
                 json={"title": "Empty state mock for the dashboard", "assignee_id": str(ids.user("noah"))})
    assert r.json()["suggestion"]["status"] == "modified"
    assert r.json()["task"]["assignee"]["name"] == "Noah Park"
    assert r.json()["task"]["source_message_ids"] == [str(ids.message("p9"))]
    dana = api_as("dana")
    rejected = dana.post(f"/suggestions/{ids.suggestion('s8')}/reject").json()
    assert rejected["suggestion"]["status"] == "rejected" and rejected["task"] is None
    status_change = api_as("bob").post(f"/suggestions/{ids.suggestion('s11')}/modify",
                                       json={"title": "x", "assignee_id": str(ids.user("bob"))})
    assert status_change.status_code == 422


def test_status_change_suggestion_applies_the_status(api_as) -> None:
    r = api_as("bob").post(f"/suggestions/{ids.suggestion('s11')}/accept").json()
    assert r["task"]["id"] == str(ids.task("t1")) and r["task"]["status"] == "done"


def test_service_backend_creates_proposals_and_expiry_is_lazy(api_as, session: Session) -> None:
    backend = ServiceBackend(session)
    payload = {"title": "Ship the newsletter", "description_md": "", "assignee_id": str(ids.user("alice")),
               "assignee_is_member": True, "project": None, "due_at": None,
               "source_message_ids": [str(ids.message("p21"))]}
    new_id = backend.create_proposal(run_id=None, conversation_id=uuid.UUID(ids.conv("marketing")), kind="task",
                                     payload=payload, confidence=0.7)
    session.commit()
    alice = api_as("alice")
    assert str(new_id) in {r["id"] for r in alice.get("/me/suggestions").json()}
    assert any(n["ref_id"] == str(new_id) for n in alice.get("/notifications").json())

    session.execute(update(AiProposal).where(AiProposal.id == new_id)
                    .values(expires_at=datetime.now(UTC) - timedelta(minutes=1)))
    session.commit()
    rows = alice.get(f"/conversations/{ids.conv('marketing')}/suggestions").json()
    assert next(r for r in rows if r["id"] == str(new_id))["status"] == "expired"
    assert alice.post(f"/suggestions/{new_id}/accept").status_code == 409
