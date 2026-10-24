"""The contract files agree with each other and with the code."""

import json
import subprocess
import sys
from pathlib import Path

import yaml
from openapi_spec_validator import validate

from ai.tools.base import DEFAULT_SCOPES, Scope, ToolResult
from api.models import AiProposal, AiToolCall, Task
from api.models.ai import PROPOSAL_STATUSES, TOOL_CALL_STATUSES
from api.models.tasks import PRIORITIES, STATUSES

ROOT = Path(__file__).resolve().parent.parent
SPEC = yaml.safe_load((ROOT / "contracts/openapi.yaml").read_text())
SCHEMAS = SPEC["components"]["schemas"]
METHODS = {"get", "post", "put", "patch", "delete"}


def test_openapi_is_valid() -> None:
    validate(SPEC)


def test_every_operation_has_a_unique_id() -> None:
    ids = [op.get("operationId") for path in SPEC["paths"].values() for m, op in path.items() if m in METHODS]
    assert all(ids)
    assert len(ids) == len(set(ids))


def test_enums_match_the_schema() -> None:
    assert SCHEMAS["TaskStatus"]["enum"] == list(STATUSES)
    assert SCHEMAS["TaskPriority"]["enum"] == list(PRIORITIES)
    assert SCHEMAS["SuggestionStatus"]["enum"] == list(PROPOSAL_STATUSES)
    assert SCHEMAS["ToolCallStatus"]["enum"] == list(TOOL_CALL_STATUSES)
    assert set(SCHEMAS["Scope"]["enum"]) == {s.value for s in Scope}
    assert set(Scope) >= DEFAULT_SCOPES


def test_tool_result_statuses_match_ai_tool_calls() -> None:
    assert set(ToolResult.__annotations__["status"].__args__) == set(TOOL_CALL_STATUSES)
    assert AiToolCall.__table__.c.status is not None and AiProposal.__table__.c.kind is not None
    assert Task.__table__.c.source_conversation_id is not None


def test_fixtures_are_current() -> None:
    result = subprocess.run([sys.executable, str(ROOT / "scripts/build_fixtures.py"), "--check"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_expected_cases_point_at_fixture_messages() -> None:
    messages = {m["id"] for m in json.loads((ROOT / "fixtures/messages.json").read_text())}
    expected = json.loads((ROOT / "fixtures/expected.json").read_text())
    assert expected["cases"]
    assert all(c["message_id"] in messages for c in expected["cases"])
