import json
from io import BytesIO
from urllib.error import HTTPError

import pytest

from app.cli import chat
from app.cli.chat import AgentApiClient, AgentCliError, run_chat


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return self._body


def test_send_message_uses_utf8_and_generates_identifiers(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse(
            {
                "data": {
                    "content": "已创建采购草稿",
                    "intent": "create_requirement",
                    "scene": "PROCUREMENT_REQUIREMENT",
                    "stage": "WAITING_FOR_CLARIFICATION",
                }
            }
        )

    monkeypatch.setattr(chat, "urlopen", fake_urlopen)
    client = AgentApiClient(user_code="DEV-E0001", timeout_seconds=12)

    result = client.send_message("cli-test", "采购两台服务器")

    request = captured["request"]
    body = json.loads(request.data.decode("utf-8"))
    assert result["content"] == "已创建采购草稿"
    assert body["content"] == "采购两台服务器"
    assert body["conversation_id"] == "cli-test"
    assert len(body["client_message_id"]) == 32
    assert request.get_header("X-user-code") == "DEV-E0001"
    assert request.get_header("Idempotency-key")
    assert captured["timeout"] == 12


def test_history_and_reset_use_expected_http_contract(monkeypatch) -> None:
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        if request.method == "GET":
            return FakeResponse(
                {
                    "data": [
                        {
                            "role": "USER",
                            "content": "你好",
                            "status": "COMPLETED",
                        }
                    ]
                }
            )
        return FakeResponse({"data": {"conversation_id": "conv-1", "cleared": True}})

    monkeypatch.setattr(chat, "urlopen", fake_urlopen)
    client = AgentApiClient()

    assert client.history("conv-1")[0]["content"] == "你好"
    assert client.reset("conv-1")["cleared"] is True
    assert requests[0].method == "GET"
    assert requests[0].full_url.endswith("/messages?page=1&page_size=100")
    assert requests[1].method == "DELETE"
    assert requests[1].get_header("Idempotency-key")


def test_http_error_is_rendered_without_traceback(monkeypatch) -> None:
    error_body = json.dumps(
        {"error": {"code": "AGENT_UNAVAILABLE", "message": "服务暂时不可用"}}
    ).encode()

    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, 503, "error", {}, BytesIO(error_body))

    monkeypatch.setattr(chat, "urlopen", fake_urlopen)

    with pytest.raises(AgentCliError, match="AGENT_UNAVAILABLE"):
        AgentApiClient().send_message("conv-1", "你好")


def test_interactive_commands_keep_and_replace_conversations() -> None:
    class StubClient:
        def __init__(self) -> None:
            self.sent = []
            self.reset_ids = []

        def send_message(self, conversation_id, content):
            self.sent.append((conversation_id, content))
            return {
                "content": "收到",
                "intent": "unknown",
                "scene": "GENERAL_QUERY",
                "stage": "INTENT_RECOGNITION",
            }

        def history(self, conversation_id):
            return [{"role": "USER", "content": "历史消息", "status": "COMPLETED"}]

        def reset(self, conversation_id):
            self.reset_ids.append(conversation_id)
            return {"conversation_id": conversation_id, "cleared": True}

    inputs = iter(["你好", "/history", "/reset", "/new", "新消息", "/exit"])
    output = []
    client = StubClient()

    run_chat(
        client,  # type: ignore[arg-type]
        conversation_id="original",
        input_fn=lambda _: next(inputs),
        write=output.append,
    )

    assert client.sent[0] == ("original", "你好")
    assert client.reset_ids == ["original"]
    assert client.sent[1][0] != "original"
    assert any("[COMPLETED] 你> 历史消息" in line for line in output)
    assert any("MySQL 采购事实未删除" in line for line in output)


def test_utf8_configuration_reconfigures_available_streams() -> None:
    class Stream:
        def __init__(self) -> None:
            self.calls = []

        def reconfigure(self, **kwargs):
            self.calls.append(kwargs)

    streams = [Stream(), Stream()]
    chat._configure_utf8(streams)  # type: ignore[arg-type]
    assert all(stream.calls == [{"encoding": "utf-8", "errors": "replace"}] for stream in streams)


def test_parser_uses_timeout_long_enough_for_two_model_stages() -> None:
    args = chat.build_parser().parse_args([])
    assert args.timeout == 90.0
