from app.modules.agent.tools.base import AgentTool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, AgentTool] = {}

    def register(self, tool: AgentTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"工具已注册：{tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> AgentTool | None:
        return self._tools.get(name)

    def names(self) -> set[str]:
        return set(self._tools)

    def schemas(self, visible_names: set[str]) -> list[dict]:
        return [tool.llm_schema() for name, tool in self._tools.items() if name in visible_names]
