"""messages, threads, reactions, files, notifications from messages (spec 1.7–1.14, 1.19)."""

import uuid

from tests.conftest import ids, requires_db

pytestmark = requires_db


def png() -> bytes:
    from io import BytesIO

    from PIL import Image

    out = BytesIO()
    Image.new("RGB", (640, 480), "teal").save(out, "PNG")
    return out.getvalue()


def post(api, conv: str, body: str, **extra):
    return api.post(f"/conversations/{ids.conv(conv)}/messages",
                    json={"client_id": str(uuid.uuid4()), "body_md": body, **extra})


def test_send_is_idempotent_on_client_id(api_as) -> None:
    alice = api_as("alice")
    body = {"client_id": str(uuid.uuid4()), "body_md": "Shipping the hero image today"}
    first = alice.post(f"/conversations/{ids.conv('website')}/messages", json=body)
    retry = alice.post(f"/conversations/{ids.conv('website')}/messages", json=body)
    assert first.status_code == 201 and retry.status_code == 200
    assert first.json()["id"] == retry.json()["id"]
    assert first.json()["seq"] == alice.get(f"/conversations/{ids.conv('website')}").json()["last_seq"]


def test_only_members_post_and_slash_text_is_rejected(api_as) -> None:
    assert post(api_as("sofia"), "website", "hello").status_code == 403  # can read (public), not a member
    r = post(api_as("alice"), "website", "/task do it")
    assert r.status_code == 422


def test_paging_up_and_gap_fill(api_as) -> None:
    bob = api_as("bob")
    url = f"/conversations/{ids.conv('general')}/messages"
    latest = bob.get(url, params={"limit": 10}).json()
    assert len(latest["items"]) == 10 and latest["has_more"]
    seqs = [m["seq"] for m in latest["items"]]
    assert seqs == sorted(seqs)
    older = bob.get(url, params={"before_seq": seqs[0], "limit": 5}).json()
    assert [m["seq"] for m in older["items"]][-1] < seqs[0]
    gap = bob.get(url, params={"after_seq": seqs[4]}).json()
    assert [m["seq"] for m in gap["items"]] == seqs[5:] and not gap["has_more"]
    assert bob.get(f"/conversations/{ids.conv('hiring')}/messages").status_code == 403


def test_threads_count_replies_and_also_in_channel(api_as) -> None:
    alice, bob = api_as("alice"), api_as("bob")
    parent = post(alice, "website", "Thread about the footer").json()
    post(bob, "website", "Looks fine to me", parent_id=parent["id"])
    shared = post(bob, "website", "Pushed the fix", parent_id=parent["id"], also_in_channel=True).json()
    assert shared["also_in_channel"]
    thread = alice.get(f"/messages/{parent['id']}/thread").json()
    assert thread["parent"]["reply_count"] == 2 and [r["body_md"] for r in thread["replies"]] == [
        "Looks fine to me", "Pushed the fix"]
    assert thread["parent"]["reply_user_ids"] == [str(ids.user("bob"))]
    listed = [m["id"] for m in alice.get(f"/conversations/{ids.conv('website')}/messages").json()["items"]]
    assert shared["id"] in listed and thread["replies"][0]["id"] not in listed
    nested = post(bob, "website", "nested", parent_id=shared["id"])
    assert nested.status_code == 422


def test_edit_keeps_history_and_only_the_author_edits(api_as) -> None:
    alice = api_as("alice")
    m = post(alice, "website", "Draft copy").json()
    assert api_as("bob").patch(f"/messages/{m['id']}", json={"body_md": "hijack"}).status_code == 403
    edited = alice.patch(f"/messages/{m['id']}", json={"body_md": f"Final copy, {ids.mention('bob')} please check"})
    assert edited.json()["edited_at"] and edited.json()["mentions"][0]["user_id"] == str(ids.user("bob"))


def test_soft_delete_hides_the_body(api_as) -> None:
    alice = api_as("alice")
    m = post(alice, "website", "oops").json()
    assert api_as("bob").delete(f"/messages/{m['id']}").status_code == 403
    assert alice.delete(f"/messages/{m['id']}").status_code == 204
    gone = alice.get(f"/messages/{m['id']}").json()
    assert gone["deleted_at"] and gone["body_md"] == ""
    assert api_as("grace").delete(f"/messages/{ids.message('p2b')}").status_code == 204  # admin


def test_messages_read_point_in_time(api_as) -> None:
    ken = api_as("ken")
    assert ken.get(f"/messages/{ids.message('p20')}").status_code == 200
    assert api_as("bob").get(f"/messages/{ids.message('p19')}").status_code == 403  # #hiring
    assert api_as("bob").get(f"/messages/{uuid.uuid4()}").status_code == 404


def test_reactions_are_idempotent(api_as) -> None:
    alice, bob = api_as("alice"), api_as("bob")
    m = post(alice, "website", "Launch day 🚀").json()
    url = f"/messages/{m['id']}/reactions/🎉"
    assert bob.put(url).json() == [{"emoji": "🎉", "count": 1, "user_ids": [str(ids.user("bob"))]}]
    assert bob.put(url).json()[0]["count"] == 1
    assert alice.put(url).json()[0]["count"] == 2
    assert bob.delete(url).json()[0]["user_ids"] == [str(ids.user("alice"))]
    assert bob.delete(url).status_code == 200


def test_mentions_notify_and_muting_spares_only_direct_mentions(api_as) -> None:
    alice, bob, dana = api_as("alice"), api_as("bob"), api_as("dana")
    dana.patch(f"/conversations/{ids.conv('website')}/membership", json={"muted": True})
    m = post(alice, "website", f"{ids.mention('bob')} and @channel: launch moved").json()
    bob_notes = bob.get("/notifications", params={"unread_only": True}).json()
    assert bob_notes[0]["ref_id"] == m["id"] and bob_notes[0]["type"] == "mention"
    assert "Bob Tan" in bob_notes[0]["preview"]
    assert not any(n["ref_id"] == m["id"] for n in dana.get("/notifications").json())  # muted, not direct
    assert not any(n["ref_id"] == m["id"] for n in alice.get("/notifications").json())  # author


def test_dm_and_thread_reply_notifications(api_as) -> None:
    alice, bob = api_as("alice"), api_as("bob")
    dm = post(alice, "dm:alice:bob", "quick question").json()
    latest = bob.get("/notifications").json()[0]
    assert (latest["type"], latest["ref_id"]) == ("dm", dm["id"])
    parent = post(bob, "website", "Thread start").json()
    reply = post(alice, "website", "reply", parent_id=parent["id"]).json()
    assert bob.get("/notifications").json()[0]["ref_id"] == reply["id"]
    assert bob.get("/notifications").json()[0]["type"] == "thread_reply"


def test_notifications_mark_read(api_as) -> None:
    bob = api_as("bob")
    post(api_as("alice"), "dm:alice:bob", "ping")
    note = bob.get("/notifications", params={"unread_only": True}).json()[0]
    assert bob.post(f"/notifications/{note['id']}/read").status_code == 204
    assert all(n["id"] != note["id"] for n in bob.get("/notifications", params={"unread_only": True}).json())
    assert api_as("alice").post(f"/notifications/{note['id']}/read").status_code == 404
    assert bob.post("/notifications/read-all").status_code == 204
    assert bob.get("/notifications", params={"unread_only": True}).json() == []


def test_upload_attach_and_download_with_access_checks(api_as) -> None:
    mei, bob = api_as("mei"), api_as("mei"),
    mei, bob = api_as("mei"), api_as("bob")
    up = mei.post("/files", data={"conversation_id": str(ids.conv("payments"))},
                  files={"file": ("ledger.csv", b"a,b\n1,2\n", "text/csv")})
    assert up.status_code == 201 and up.json()["message_id"] is None and up.json()["size"] == 8
    file_id = up.json()["id"]
    assert bob.get(f"/files/{file_id}").status_code == 403  # unattached: uploader only
    m = post(mei, "payments", "ledger attached", file_ids=[file_id]).json()
    assert m["files"][0]["id"] == file_id
    got = mei.get(f"/files/{file_id}")
    assert got.status_code == 200 and got.content == b"a,b\n1,2\n"
    assert mei.get(f"/files/{file_id}/meta").json()["message_id"] == m["id"]
    assert bob.get(f"/files/{file_id}").status_code == 403  # private channel
    assert bob.get(f"/files/{file_id}/meta").status_code == 403
    reuse = post(mei, "payments", "again", file_ids=[file_id])
    assert reuse.status_code == 422


def test_images_get_thumbnails_and_snippets_previews(api_as) -> None:
    ivy = api_as("ivy")
    img = ivy.post("/files", data={"conversation_id": str(ids.conv("website"))},
                   files={"file": ("dot.png", png(), "image/png")}).json()
    assert img["kind"] == "image" and img["has_thumbnail"]
    assert ivy.get(f"/files/{img['id']}", params={"thumbnail": True}).headers["content-type"] == "image/png"
    snippet = ivy.post("/files", data={"conversation_id": str(ids.conv("website")), "kind": "snippet",
                                       "name": "query.sql", "language": "sql"},
                       files={"file": ("x", b"select 1;\nselect 2;\nselect 3;\n", "text/plain")}).json()
    prev = ivy.get(f"/files/{snippet['id']}/preview", params={"lines": 2}).json()
    assert prev == {"text": "select 1;\nselect 2;", "truncated": True, "language": "sql"}
    assert ivy.get(f"/files/{img['id']}/preview").status_code == 422
    assert ivy.post("/files", files={"file": ("x.txt", b"x", "text/plain")}).status_code == 422
    assert api_as("bob").post("/files", data={"conversation_id": str(ids.conv("hiring"))},
                              files={"file": ("x.txt", b"x", "text/plain")}).status_code == 403
