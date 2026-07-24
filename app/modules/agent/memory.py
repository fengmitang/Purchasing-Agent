from dataclasses import dataclass, field
from typing import Protocol

from app.shared.identity import CurrentUser


@dataclass(frozen=True)
class MemoryItem:
    content: str
    source: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class KnowledgeItem:
    content: str
    source: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


class MemoryProvider(Protocol):
    async def recall(
        self, *, actor: CurrentUser, conversation_id: str, query: str, limit: int
    ) -> list[MemoryItem]: ...


class KnowledgeProvider(Protocol):
    async def search(
        self, *, actor: CurrentUser, query: str, limit: int
    ) -> list[KnowledgeItem]: ...


class EmptyMemoryProvider:
    async def recall(self, **kwargs) -> list[MemoryItem]:
        return []


class EmptyKnowledgeProvider:
    async def search(self, **kwargs) -> list[KnowledgeItem]:
        return []
