import io
import json
from email.message import Message
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
        raise HTTPError(request.full_url, 429, "rate limited", Message(), None)

    monkeypatch.setattr(module, "urlopen", response)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="model_unavailable"):
        NativeModel(api_key="test-only-placeholder").choose("chat", [])
    assert len(attempts) == 3

    def denied(request, timeout):
        raise HTTPError(request.full_url, 401, "unauthorized", Message(), None)

    monkeypatch.setattr(module, "urlopen", denied)
    with pytest.raises(RuntimeError, match="model_http_401"):
        NativeModel(api_key="test-only-placeholder").choose("chat", [])


def test_missing_credentials_fail_explicitly(monkeypatch):
    clear_ai_env(monkeypatch)
    with pytest.raises(ValueError, match="RUNPOD_API_KEY"):
        NativeModel()


def clear_ai_env(monkeypatch):
    for key in ("AI_API_KEY", "RUNPOD_API_KEY", "OPENAI_API_KEY", "RUNPOD_ENDPOINT_ID", "AI_BASE_URL",
                "AI_MODEL", "AI_TOOL_CHOICE", "AI_TIMEOUT_SECONDS"):
        monkeypatch.delenv(key, raising=False)


def test_runpod_configuration_from_env_file(tmp_path, monkeypatch):
    clear_ai_env(monkeypatch)
    env = tmp_path / ".env"
    env.write_text("# comment\nRUNPOD_API_KEY='placeholder'\nRUNPOD_ENDPOINT_ID=abc123\nAI_MODEL=served-model\n")
    monkeypatch.setenv("AI_MODEL", "already-set")
    module.load_env(env)
    native = NativeModel()
    assert native.url == "https://api.runpod.ai/v2/abc123/openai/v1"
    assert native.key == "placeholder" and native.model == "already-set"
    assert native.timeout == 180


def test_runpod_requires_served_model_name(monkeypatch):
    clear_ai_env(monkeypatch)
    monkeypatch.setenv("RUNPOD_API_KEY", "placeholder")
    monkeypatch.setenv("RUNPOD_ENDPOINT_ID", "abc123")
    with pytest.raises(ValueError, match="AI_MODEL"):
        NativeModel()


def test_auto_tool_choice_maps_plain_reply_to_no_action(monkeypatch):
    clear_ai_env(monkeypatch)
    sent = []

    def respond(request, timeout):
        sent.append(json.loads(request.data))
        return io.BytesIO(json.dumps({"choices": [{"message": {"content": "nothing to do"}}]}).encode())

    monkeypatch.setattr(module, "urlopen", respond)
    calls = NativeModel(api_key="placeholder", base_url="https://example.test/v1", model="m",
                        tool_choice="auto").choose("chat", [])
    assert calls[0].name == "no_action" and sent[0]["tool_choice"] == "auto"
