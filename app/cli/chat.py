"""Interactive HTTP client for the procurement Agent chat API."""

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Any, TextIO
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_USER_CODE = "DEV-E0001"
DEFAULT_ROLES = "EMPLOYEE"
DEFAULT_TIMEOUT_SECONDS = 90.0


class AgentCliError(RuntimeError):
    """A safe error returned to the interactive CLI user."""


class AgentApiClient:
    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        user_code: str = DEFAULT_USER_CODE,
        roles: str = DEFAULT_ROLES,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._user_code = user_code
        self._roles = roles
        self._timeout_seconds = timeout_seconds

    def send_message(self, conversation_id: str, content: str) -> dict[str, Any]:
        payload = self._request(
            "POST",
            "/api/v1/agent/messages",
            body={
                "conversation_id": conversation_id,
                "client_message_id": uuid4().hex,
                "content": content,
            },
            idempotency_key=uuid4().hex,
        )
        return _object(payload.get("data"), "聊天接口返回了无效数据")

    def history(self, conversation_id: str) -> list[dict[str, Any]]:
        query = urlencode({"page": 1, "page_size": 100})
        payload = self._request(
            "GET",
            f"/api/v1/agent/conversations/{quote(conversation_id, safe='')}/messages?{query}",
        )
        data = payload.get("data")
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise AgentCliError("历史接口返回了无效数据")
        return data

    def reset(self, conversation_id: str) -> dict[str, Any]:
        payload = self._request(
            "DELETE",
            f"/api/v1/agent/conversations/{quote(conversation_id, safe='')}",
            idempotency_key=uuid4().hex,
        )
        return _object(payload.get("data"), "重置接口返回了无效数据")

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "X-User-Code": self._user_code,
            "X-User-Roles": self._roles,
        }
        encoded_body = None
        if body is not None:
            encoded_body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key

        request = Request(
            f"{self._base_url}{path}",
            data=encoded_body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                raw = response.read()
        except HTTPError as exc:
            raise AgentCliError(_http_error_message(exc)) from None
        except URLError as exc:
            raise AgentCliError("无法连接 Agent API，请确认服务已在指定地址启动") from exc
        except TimeoutError as exc:
            raise AgentCliError("Agent API 请求超时") from exc

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AgentCliError("Agent API 返回了无效 JSON") from exc
        return _object(payload, "Agent API 返回了无效响应")


def run_chat(
    client: AgentApiClient,
    *,
    conversation_id: str | None = None,
    input_fn: Callable[[str], str] = input,
    write: Callable[[str], None] = print,
) -> None:
    current_conversation = conversation_id or _new_conversation_id()
    write("采购 Agent CLI")
    write(f"会话：{current_conversation}")
    write("命令：/new /history /reset /exit")

    while True:
        try:
            message = input_fn("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            write("\n已退出。")
            return

        if not message:
            continue
        if message == "/exit":
            write("已退出。")
            return
        if message == "/new":
            current_conversation = _new_conversation_id()
            write(f"已创建新会话：{current_conversation}")
            continue
        if message == "/history":
            _show_history(client, current_conversation, write)
            continue
        if message == "/reset":
            _reset_conversation(client, current_conversation, write)
            continue
        if message.startswith("/"):
            write("未知命令。可用命令：/new /history /reset /exit")
            continue

        try:
            result = client.send_message(current_conversation, message)
        except AgentCliError as exc:
            write(f"请求失败：{exc}")
            continue
        write(f"Agent> {result.get('content', '')}")
        write(
            "状态> "
            f"意图={result.get('intent', '-')} "
            f"场景={result.get('scene', '-')} "
            f"阶段={result.get('stage', '-')}"
        )
        requirement = result.get("active_requirement")
        if isinstance(requirement, dict):
            write(
                "采购草稿> "
                f"{requirement.get('requirement_no', '-')} "
                f"状态={requirement.get('status', '-')}"
            )


def _show_history(
    client: AgentApiClient,
    conversation_id: str,
    write: Callable[[str], None],
) -> None:
    try:
        messages = client.history(conversation_id)
    except AgentCliError as exc:
        write(f"读取历史失败：{exc}")
        return
    if not messages:
        write("当前会话没有历史消息。")
        return
    for message in messages:
        role = "你" if message.get("role") == "USER" else "Agent"
        status = message.get("status", "-")
        write(f"[{status}] {role}> {message.get('content', '')}")


def _reset_conversation(
    client: AgentApiClient,
    conversation_id: str,
    write: Callable[[str], None],
) -> None:
    try:
        client.reset(conversation_id)
    except AgentCliError as exc:
        write(f"重置失败：{exc}")
        return
    write("当前会话的短期历史和 Agent 状态已清除；MySQL 采购事实未删除。")


def _http_error_message(error: HTTPError) -> str:
    try:
        payload = json.loads(error.read().decode("utf-8"))
        details = payload.get("error", {})
        code = details.get("code", f"HTTP_{error.code}")
        message = details.get("message", "请求失败")
        return f"{code}: {message}"
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
        return f"HTTP_{error.code}: 请求失败"


def _object(value: object, error_message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AgentCliError(error_message)
    return value


def _new_conversation_id() -> str:
    return f"cli-{uuid4().hex[:16]}"


def _configure_utf8(streams: Sequence[TextIO] = (sys.stdin, sys.stdout, sys.stderr)) -> None:
    for stream in streams:
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="采购 Agent 交互式命令行客户端")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Agent API 根地址")
    parser.add_argument("--user-code", default=DEFAULT_USER_CODE, help="内部员工号")
    parser.add_argument("--roles", default=DEFAULT_ROLES, help="逗号分隔的角色")
    parser.add_argument("--conversation-id", help="复用指定会话 ID")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="请求超时秒数",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    _configure_utf8()
    args = build_parser().parse_args(argv)
    if args.timeout <= 0:
        build_parser().error("--timeout 必须大于 0")
    client = AgentApiClient(
        base_url=args.base_url,
        user_code=args.user_code,
        roles=args.roles,
        timeout_seconds=args.timeout,
    )
    run_chat(client, conversation_id=args.conversation_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
