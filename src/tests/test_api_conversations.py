"""conversations, members, read cursors (spec 1.5, 1.6, 1.16, 3.5)."""

from tests.conftest import ids, requires_db

pytestmark = requires_db


def test_sidebar_lists_department_then_channels_then_dms(api_as) -> None:
    rows = api_as("alice").get("/conversations").json()
    kinds = [r["kind"] for r in rows]
    assert kinds == sorted(kinds, key=["department", "channel", "dm"].index)
    assert rows[0]["name"] == "marketing" and all(r["membership"] for r in rows)
    dm = next(r for r in rows if r["kind"] == "dm")
    assert dm["name"] is None and dm["dm_peer"]["name"]


def test_browse_lists_public_channels(api_as) -> None:
    names = {r["name"] for r in api_as("sofia").get("/conversations", params={"scope": "browse"}).json()}
    assert {"website", "general", "random"} <= names and "hiring" not in names and "payments-launch" not in names


def test_get_conversation_checks_access(api_as) -> None:
    bob = api_as("bob")
    assert bob.get(f"/conversations/{ids.conv('website')}").json()["member_count"] == 8
    assert bob.get(f"/conversations/{ids.conv('hiring')}").status_code == 403
    assert bob.get("/conversations/00000000-0000-0000-0000-000000000000").status_code == 404


def test_create_channel_with_members(api_as) -> None:
    r = api_as("bob").post("/conversations", json={"kind": "channel", "name": "launch-party", "is_public": False,
                                                   "member_ids": [str(ids.user("dana"))]})
    assert r.status_code == 201
    body = r.json()
    assert body["member_count"] == 2 and body["membership"]["role"] == "owner" and not body["is_public"]
    assert api_as("bob").post("/conversations", json={"kind": "channel"}).status_code == 422


def test_dm_find_or_create(api_as) -> None:
    bob = api_as("bob")
    first = bob.post("/conversations", json={"kind": "dm", "member_ids": [str(ids.user("yusuf"))]})
    assert first.status_code == 201
    again = api_as("yusuf").post("/conversations", json={"kind": "dm", "member_ids": [str(ids.user("bob"))]})
    assert again.status_code == 200 and again.json()["id"] == first.json()["id"]
    existing = bob.post("/conversations", json={"kind": "dm", "member_ids": [str(ids.user("alice"))]})
    assert existing.status_code == 200 and existing.json()["id"] == str(ids.conv("dm:alice:bob"))
    assert bob.post("/conversations", json={"kind": "dm", "member_ids": []}).status_code == 422


def test_owner_edits_and_archives(api_as) -> None:
    alice, bob = api_as("alice"), api_as("bob")  # alice created #website
    assert bob.patch(f"/conversations/{ids.conv('website')}", json={"description": "x"}).status_code == 403
    r = alice.patch(f"/conversations/{ids.conv('website')}", json={"description": "Site and landing pages"})
    assert r.json()["description"] == "Site and landing pages"
    archived = alice.post(f"/conversations/{ids.conv('website')}/archive")
    assert archived.status_code == 200 and archived.json()["archived_at"]
    post = alice.post(f"/conversations/{ids.conv('website')}/messages", json={"client_id": str(ids.task("x")),
                                                                             "body_md": "hi"})
    assert post.status_code == 409


def test_cannot_edit_or_archive_a_dm(api_as) -> None:
    alice = api_as("alice")
    assert alice.patch(f"/conversations/{ids.conv('dm:alice:bob')}", json={"name": "x"}).status_code == 409
    assert alice.post(f"/conversations/{ids.conv('dm:alice:bob')}/archive").status_code == 409


def test_join_and_leave(api_as) -> None:
    sofia = api_as("sofia")
    joined = sofia.post(f"/conversations/{ids.conv('website')}/join")
    assert joined.status_code == 200 and joined.json()["user"]["name"] == "Sofia Lindqvist"
    assert sofia.post(f"/conversations/{ids.conv('website')}/join").status_code == 200  # idempotent
    assert api_as("bob").post(f"/conversations/{ids.conv('hiring')}/join").status_code == 403
    assert sofia.post(f"/conversations/{ids.conv('website')}/leave").status_code == 204
    assert sofia.post(f"/conversations/{ids.conv('website')}/leave").status_code == 403


def test_department_channels_and_dms_cannot_be_left(api_as) -> None:
    bob = api_as("bob")
    r = bob.post(f"/conversations/{ids.conv('engineering')}/leave")
    assert r.status_code == 409 and r.json()["code"] == "cannot_leave"
    assert bob.post(f"/conversations/{ids.conv('dm:alice:bob')}/leave").status_code == 409


def test_members_invite_and_remove(api_as) -> None:
    alice, bob = api_as("alice"), api_as("bob")
    website = ids.conv("website")
    current = alice.get(f"/conversations/{website}/members").json()
    former = alice.get(f"/conversations/{website}/members", params={"include_former": True}).json()
    assert len(current) == 8 and len(former) == 9
    assert any(m["left_at"] for m in former)
    after = bob.post(f"/conversations/{website}/members", json={"user_ids": [str(ids.user("ethan"))]}).json()
    assert str(ids.user("ethan")) in {m["user"]["id"] for m in after}
    assert bob.delete(f"/conversations/{website}/members/{ids.user('ethan')}").status_code == 403  # not owner
    assert alice.delete(f"/conversations/{website}/members/{ids.user('ethan')}").status_code == 204
    assert api_as("dana").post(f"/conversations/{ids.conv('payments')}/members",
                               json={"user_ids": [str(ids.user("bob"))]}).status_code == 403


def test_dm_ai_opt_in_toggles_ai_active(api_as) -> None:
    bob = api_as("bob")
    dm = ids.conv("dm:alice:bob")
    assert bob.get(f"/conversations/{dm}").json()["ai_active"] is False
    r = bob.patch(f"/conversations/{dm}/membership", json={"ai_opt_in": True, "muted": True})
    assert r.json()["ai_opt_in"] and r.json()["muted"]
    assert bob.get(f"/conversations/{dm}").json()["ai_active"] is True
    assert bob.patch(f"/conversations/{ids.conv('hiring')}/membership", json={"muted": True}).status_code == 403


def test_read_cursor_moves_forward_only_and_clears_unread(api_as) -> None:
    alice = api_as("alice")
    random_id = ids.conv("random")
    convo = alice.get(f"/conversations/{random_id}").json()
    assert convo["unread_count"] > 0
    r = alice.put(f"/conversations/{random_id}/read", json={"last_read_seq": convo["last_seq"]})
    assert r.json()["last_read_seq"] == convo["last_seq"]
    assert alice.get(f"/conversations/{random_id}").json()["unread_count"] == 0
    back = alice.put(f"/conversations/{random_id}/read", json={"last_read_seq": 1})
    assert back.json()["last_read_seq"] == convo["last_seq"]
    cursors = {c["conversation_id"]: c["last_read_seq"] for c in alice.get("/me/read-cursors").json()}
    assert cursors[str(random_id)] == convo["last_seq"]
    assert alice.put(f"/conversations/{ids.conv('hiring')}/read", json={"last_read_seq": 1}).status_code == 403


def test_mention_count_counts_unread_mentions(api_as) -> None:
    alice, bob = api_as("alice"), api_as("bob")
    website = ids.conv("website")
    seq = bob.get(f"/conversations/{website}").json()["last_seq"]
    bob.put(f"/conversations/{website}/read", json={"last_read_seq": seq})
    alice.post(f"/conversations/{website}/messages",
               json={"client_id": str(ids.task("m1")), "body_md": f"{ids.mention('bob')} ping"})
    alice.post(f"/conversations/{website}/messages", json={"client_id": str(ids.task("m2")), "body_md": "no ping"})
    convo = bob.get(f"/conversations/{website}").json()
    assert convo["unread_count"] == 2 and convo["mention_count"] == 1
