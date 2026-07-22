import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class AgentToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class AgentModelResponse:
    text: str = ""
    tool_calls: list[AgentToolCall] = field(default_factory=list)
    assistant_content: list[dict[str, Any]] = field(default_factory=list)


class AgentModelProtocol(Protocol):
    async def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AgentModelResponse: ...


class AnthropicToolCallingModel:
    """隔离Anthropic兼容响应格式，业务Agent只依赖统一模型结果。"""

    def __init__(
        self,
        client: Any,
        model: str,
        *,
        max_tokens: int = 1800,
        temperature: float = 0.1,
        timeout_seconds: float = 15.0,
        max_retries: int = 1,
    ) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries

    async def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AgentModelResponse:
        async def invoke():
            return await self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                system=system,
                messages=messages,
                tools=tools,
            )

        response = await _invoke_with_retries(
            invoke, timeout_seconds=self._timeout_seconds, max_retries=self._max_retries
        )

        text_parts: list[str] = []
        tool_calls: list[AgentToolCall] = []
        assistant_content: list[dict[str, Any]] = []
        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text = str(getattr(block, "text", ""))
                text_parts.append(text)
                assistant_content.append({"type": "text", "text": text})
            elif block_type == "tool_use":
                tool_call = AgentToolCall(
                    id=str(block.id),
                    name=str(block.name),
                    arguments=dict(getattr(block, "input", {}) or {}),
                )
                tool_calls.append(tool_call)
                assistant_content.append(
                    {
                        "type": "tool_use",
                        "id": tool_call.id,
                        "name": tool_call.name,
                        "input": tool_call.arguments,
                    }
                )

        return AgentModelResponse(
            text="\n".join(part for part in text_parts if part).strip(),
            tool_calls=tool_calls,
            assistant_content=assistant_content,
        )


class OpenAICompatibleToolCallingModel:
    """Adapt an OpenAI-compatible chat completion client to AgentModelProtocol."""

    def __init__(
        self,
        client: Any,
        model: str,
        *,
        max_tokens: int = 1800,
        temperature: float = 0.1,
        timeout_seconds: float = 15.0,
        max_retries: int = 1,
    ) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries

    async def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AgentModelResponse:
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {}),
                },
            }
            for tool in tools
        ]

        async def invoke():
            kwargs: dict[str, Any] = {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system},
                    *_to_openai_messages(messages),
                ],
                "max_tokens": self._max_tokens,
                "temperature": self._temperature,
            }
            if openai_tools:
                kwargs["tools"] = openai_tools
            return await self._client.chat.completions.create(**kwargs)

        response = await _invoke_with_retries(
            invoke, timeout_seconds=self._timeout_seconds, max_retries=self._max_retries
        )
        message = response.choices[0].message
        text = str(message.content or "").strip()
        tool_calls: list[AgentToolCall] = []
        assistant_content: list[dict[str, Any]] = []
        if text:
            assistant_content.append({"type": "text", "text": text})
        for call in message.tool_calls or []:
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except (TypeError, ValueError):
                arguments = {}
            tool_call = AgentToolCall(
                id=str(call.id),
                name=str(call.function.name),
                arguments=arguments if isinstance(arguments, dict) else {},
            )
            tool_calls.append(tool_call)
            assistant_content.append(
                {
                    "type": "tool_use",
                    "id": tool_call.id,
                    "name": tool_call.name,
                    "input": tool_call.arguments,
                }
            )
        return AgentModelResponse(
            text=text,
            tool_calls=tool_calls,
            assistant_content=assistant_content,
        )


async def _invoke_with_retries(invoke, *, timeout_seconds: float, max_retries: int):
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            async with asyncio.timeout(timeout_seconds):
                return await invoke()
        except Exception as exc:
            last_error = exc
            if attempt >= max_retries:
                raise
            await asyncio.sleep(0.2 * (attempt + 1))
    raise RuntimeError("model invocation failed") from last_error


def _to_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if not isinstance(content, list):
            converted.append({"role": role, "content": content})
            continue

        if role == "assistant":
            text_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            for block in content:
                if block.get("type") == "text":
                    text_parts.append(str(block.get("text", "")))
                elif block.get("type") == "tool_use":
                    tool_calls.append(
                        {
                            "id": str(block.get("id", "")),
                            "type": "function",
                            "function": {
                                "name": str(block.get("name", "")),
                                "arguments": json.dumps(block.get("input", {}), ensure_ascii=False),
                            },
                        }
                    )
            converted_message: dict[str, Any] = {
                "role": "assistant",
                "content": "\n".join(filter(None, text_parts)) or None,
            }
            if tool_calls:
                converted_message["tool_calls"] = tool_calls
            converted.append(converted_message)
            continue

        if role == "user" and all(block.get("type") == "tool_result" for block in content):
            converted.extend(
                {
                    "role": "tool",
                    "tool_call_id": str(block.get("tool_use_id", "")),
                    "content": str(block.get("content", "")),
                }
                for block in content
            )
            continue

        text = "\n".join(
            str(block.get("text", "")) for block in content if block.get("type") == "text"
        )
        converted.append({"role": role, "content": text})
    return converted
