from types import SimpleNamespace

import pytest

from app.modules.agent.model import (
    AnthropicToolCallingModel,
    OpenAICompatibleToolCallingModel,
)


class AsyncCreate:
    def __init__(self, response) -> None:
        self.response = response
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


@pytest.mark.asyncio
async def test_openai_provider_maps_text_and_function_calls() -> None:
    message = SimpleNamespace(
        content="我会先读取草稿。",
        tool_calls=[
            SimpleNamespace(
                id="call-1",
                function=SimpleNamespace(
                    name="get_requirement_detail", arguments='{"requirement_id": 7}'
                ),
            )
        ],
    )
    create = AsyncCreate(SimpleNamespace(choices=[SimpleNamespace(message=message)]))
    client = SimpleNamespace(chat=SimpleNamespace(completions=create))
    model = OpenAICompatibleToolCallingModel(client, "test-model", max_retries=0)

    result = await model.complete(
        system="system",
        messages=[{"role": "user", "content": "查看草稿"}],
        tools=[
            {
                "name": "get_requirement_detail",
                "description": "读取草稿",
                "input_schema": {"type": "object", "properties": {}},
            }
        ],
    )

    assert result.text == "我会先读取草稿。"
    assert result.tool_calls[0].arguments == {"requirement_id": 7}
    assert create.kwargs["tools"][0]["function"]["parameters"]["type"] == "object"
    assert create.kwargs["messages"][0] == {"role": "system", "content": "system"}


@pytest.mark.asyncio
async def test_openai_provider_converts_internal_tool_result_history() -> None:
    message = SimpleNamespace(content="完成", tool_calls=[])
    create = AsyncCreate(SimpleNamespace(choices=[SimpleNamespace(message=message)]))
    client = SimpleNamespace(chat=SimpleNamespace(completions=create))
    model = OpenAICompatibleToolCallingModel(client, "test-model", max_retries=0)

    await model.complete(
        system="system",
        messages=[
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "call-1",
                        "name": "get_requirement_detail",
                        "input": {"requirement_id": 7},
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "call-1",
                        "content": '{"success": true}',
                    }
                ],
            },
        ],
        tools=[],
    )

    assistant = create.kwargs["messages"][1]
    tool_result = create.kwargs["messages"][2]
    assert assistant["tool_calls"][0]["function"]["arguments"] == '{"requirement_id": 7}'
    assert tool_result == {
        "role": "tool",
        "tool_call_id": "call-1",
        "content": '{"success": true}',
    }


@pytest.mark.asyncio
async def test_anthropic_provider_maps_text_and_tool_use_blocks() -> None:
    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="正在处理。"),
            SimpleNamespace(
                type="tool_use",
                id="tool-1",
                name="create_requirement_draft",
                input={"product_name": "服务器"},
            ),
        ]
    )
    create = AsyncCreate(response)
    client = SimpleNamespace(messages=create)
    model = AnthropicToolCallingModel(client, "test-model", max_retries=0)

    result = await model.complete(
        system="system",
        messages=[{"role": "user", "content": "采购服务器"}],
        tools=[],
    )

    assert result.text == "正在处理。"
    assert result.tool_calls[0].name == "create_requirement_draft"
    assert result.tool_calls[0].arguments == {"product_name": "服务器"}
