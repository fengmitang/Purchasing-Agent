from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from app.modules.agent.context import AgentContext


class ToolExecutionResult(BaseModel):
    success: bool
    code: str = "OK"
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    terminal: bool = False


class AgentTool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    input_model: ClassVar[type[BaseModel]]
    is_write: ClassVar[bool] = False

    def llm_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_model.model_json_schema(),
        }

    @abstractmethod
    async def execute(
        self,
        context: AgentContext,
        arguments: BaseModel,
    ) -> ToolExecutionResult:
        raise NotImplementedError
