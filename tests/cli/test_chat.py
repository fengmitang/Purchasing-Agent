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


class FakeOpener:
    def __init__(self, callback) -> None:
        self._callback = callback

    def open(self, request, timeout):
        return self._callback(request, timeout)


def test_send_message_uses_utf8_and_generates_identifiers() -> None:
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

    client = AgentApiClient(
        dev_user_code="DEV-E0001",
        use_dev_headers=True,
        timeout_seconds=12,
        opener=FakeOpener(fake_urlopen),  # type: ignore[arg-type]
    )

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


def test_login_then_agent_request_uses_cookie_opener_without_dev_headers() -> None:
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        if request.full_url.endswith("/api/v1/auth/login"):
            return FakeResponse(
                {
                    "data": {
                        "user": {
                            "employee_no": "DEV-E0001",
                            "name": "测试员工",
                            "building_ids": [1],
                        }
                    }
                }
            )
        return FakeResponse(
            {
                "data": {
                    "content": "草稿已创建",
                    "intent": "create_requirement",
                    "scene": "PROCUREMENT_REQUIREMENT",
                    "stage": "COLLECTING_INFORMATION",
                }
            }
        )

    client = AgentApiClient(opener=FakeOpener(fake_urlopen))  # type: ignore[arg-type]
    user = client.login("DEV-E0001", "secret-password")
    client.send_message("conv-1", "采购服务器")

    login_body = json.loads(requests[0].data.decode("utf-8"))
    assert user["building_ids"] == [1]
    assert login_body == {"identifier": "DEV-E0001", "password": "secret-password"}
    assert requests[1].get_header("X-user-code") is None
    assert requests[1].get_header("X-user-roles") is None


def test_history_and_reset_use_expected_http_contract() -> None:
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

    client = AgentApiClient(opener=FakeOpener(fake_urlopen))  # type: ignore[arg-type]

    assert client.history("conv-1")[0]["content"] == "你好"
    assert client.reset("conv-1")["cleared"] is True
    assert requests[0].method == "GET"
    assert requests[0].full_url.endswith("/messages?page=1&page_size=100")
    assert requests[1].method == "DELETE"
    assert requests[1].get_header("Idempotency-key")


def test_http_error_is_rendered_without_traceback() -> None:
    error_body = json.dumps(
        {"error": {"code": "AGENT_UNAVAILABLE", "message": "服务暂时不可用"}}
    ).encode()

    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, 503, "error", {}, BytesIO(error_body))

    with pytest.raises(AgentCliError, match="AGENT_UNAVAILABLE"):
        AgentApiClient(opener=FakeOpener(fake_urlopen)).send_message(  # type: ignore[arg-type]
            "conv-1", "你好"
        )


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
    assert args.identifier == "DEV-E0001"
    assert args.dev_headers is False
