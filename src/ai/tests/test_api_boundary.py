"""Opt-in AI boundary check against an unchanged, seeded API running in Docker.

Set AI_DOCKER_TEST_API_URL and DATABASE_URL to the same disposable test deployment.
Never point this test at a real/shared company database: it accepts one suggestion.
"""

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import httpx
import pytest

from tests.conftest import ids

pytestmark = pytest.mark.skipif(
    not os.environ.get("AI_DOCKER_TEST_API_URL") or not os.environ.get("DATABASE_URL"),
    reason="requires a disposable seeded Docker API and its DATABASE_URL",
)


def test_recorded_worker_configuration_uses_live_api_services(tmp_path):
    with httpx.Client(base_url=os.environ["AI_DOCKER_TEST_API_URL"], timeout=10) as api:
        assert api.get("/health").json() == {"status": "ok"}
        assert api.post("/auth/login", json={"email": "alice.moreau@example.com",
                                            "password": "password123"}).status_code == 200
        conv_id = str(ids.conv("website"))
        test_id = uuid.uuid4().hex
        task_url = f"/conversations/{conv_id}/tasks"
        original_count = len(api.get(task_url).json())
        message = api.post(f"/conversations/{conv_id}/messages", json={
            "client_id": str(uuid.uuid4()),
            "body_md": f"{ids.mention('bob')} please review the AI boundary test {test_id}.",
        })
        assert message.status_code == 201
        message_id = message.json()["id"]
        recordings = tmp_path / "responses.json"
        recordings.write_text(json.dumps({message_id: [{"name": "propose_task", "arguments": {
            "title": f"Review AI boundary test {test_id}", "description_md": "AI-only integration verification.",
            "source_message_ids": [message_id], "suggested_assignee": "Bob Tan", "confidence": .95,
        }}]}))
        command = subprocess.run(
            [sys.executable, "-m", "ai.worker", "--source", "postgres", "--model", "recorded",
             "--responses", str(recordings), "--once", "--debounce", "0"],
            cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=30,
        )
        assert command.returncode == 0, "AI CLI failed; inspect ai_runs in the disposable test database."
        assert len(api.get(task_url).json()) == original_count
        proposals = api.get(f"/conversations/{conv_id}/suggestions", params={"status": "pending"})
        assert proposals.status_code == 200
        proposal = next(p for p in proposals.json() if p["payload"].get("source_message_ids") == [message_id])
        assert proposal["payload"]["assignee_id"] == str(ids.user("bob"))
        accepted = api.post(f"/suggestions/{proposal['id']}/accept")
        assert accepted.status_code == 200
        assert accepted.json()["task"]["created_by_ai"]
        assert len(api.get(task_url).json()) == original_count + 1
