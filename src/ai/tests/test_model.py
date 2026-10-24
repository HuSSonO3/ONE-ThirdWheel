import io
import json
from urllib.error import HTTPError

import pytest

from ai import model as module
from ai.model import NativeModel


def test_native_tool_call_request_and_malformed_arguments(monkeypatch):
    calls = []

    def response(request, timeout):
        data = json.loads(request.data)
        assert data["tool_choice"] == "required" and data["tools"]
        assert data["messages"][0]["role"] == "system"
        calls.append(data)
        return io.BytesIO(json.dumps({"choices": [{"message": {"tool_calls": [
            {"function": {"name": "no_action", "arguments": '{"reason":"Nothing"}'}},
            {"function": {"name": "propose_task", "arguments": "not json"}},
        ]}}]}).encode())

    monkeypatch.setattr(module, "urlopen", response)
    result = NativeModel(api_key="test-only-placeholder").choose("chat", [{"type": "function"}])
    assert result[0].arguments == {"reason": "Nothing"} and result[1].arguments is None
    assert len(calls) == 1


def test_transient_retries_but_not_auth_failure(monkeypatch):
    attempts = []

    def response(request, timeout):
        attempts.append(1)
        raise HTTPError(request.full_url, 429, "rate limited", {}, None)

    monkeypatch.setattr(module, "urlopen", response)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="model_unavailable"):
        NativeModel(api_key="test-only-placeholder").choose("chat", [])
    assert len(attempts) == 3

    def denied(request, timeout):
        raise HTTPError(request.full_url, 401, "unauthorized", {}, None)

    monkeypatch.setattr(module, "urlopen", denied)
    with pytest.raises(RuntimeError, match="model_http_401"):
        NativeModel(api_key="test-only-placeholder").choose("chat", [])


def test_missing_credentials_fail_explicitly(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        NativeModel()
