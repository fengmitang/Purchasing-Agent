import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from copy import deepcopy
from typing import Any, Protocol

from app.modules.agent.chat_schemas import ChatHistoryMessage, ChatMessageStatus
from app.modules.agent.procurement.schemas import ProcurementSessionState

try:
    import redis.asyncio as redis_async
except ModuleNotFoundError:  # pragma: no cover - optional production dependency
    redis_async = None


class ChatStoreUnavailable(RuntimeError):
    pass


class ConversationBusy(RuntimeError):
    pass


class AgentChatStoreProtocol(Protocol):
    @asynccontextmanager
    async def lock(self, conversation_key: str) -> AsyncIterator[None]: ...

    async def get_state(self, conversation_key: str) -> ProcurementSessionState | None: ...
    async def save_state(self, conversation_key: str, state: ProcurementSessionState) -> None: ...
    async def append_message(self, conversation_key: str, message: ChatHistoryMessage) -> None: ...
    async def set_message_status(
        self, conversation_key: str, message_id: str, status: ChatMessageStatus
    ) -> None: ...
    async def list_messages(self, conversation_key: str) -> list[ChatHistoryMessage]: ...
    async def clear(self, conversation_key: str) -> None: ...
    async def get_idempotency(
        self, conversation_key: str, key: str
    ) -> tuple[str, dict[str, Any]] | None: ...
    async def save_idempotency(
        self, conversation_key: str, key: str, request_hash: str, response: dict[str, Any]
    ) -> None: ...


class InMemoryAgentChatStore:
    def __init__(self, *, max_messages: int = 100) -> None:
        self._max_messages = max_messages
        self._messages: dict[str, list[ChatHistoryMessage]] = {}
        self._states: dict[str, ProcurementSessionState] = {}
        self._idempotency: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    @asynccontextmanager
    async def lock(self, conversation_key: str) -> AsyncIterator[None]:
        lock = self._locks.setdefault(conversation_key, asyncio.Lock())
        async with lock:
            yield

    async def get_state(self, conversation_key: str) -> ProcurementSessionState | None:
        state = self._states.get(conversation_key)
        return state.model_copy(deep=True) if state else None

    async def save_state(self, conversation_key: str, state: ProcurementSessionState) -> None:
        self._states[conversation_key] = state.model_copy(deep=True)

    async def append_message(self, conversation_key: str, message: ChatHistoryMessage) -> None:
        messages = self._messages.setdefault(conversation_key, [])
        messages.append(message.model_copy(deep=True))
        del messages[: max(0, len(messages) - self._max_messages)]

    async def set_message_status(
        self, conversation_key: str, message_id: str, status: ChatMessageStatus
    ) -> None:
        for message in self._messages.get(conversation_key, []):
            if message.message_id == message_id:
                message.status = status
                return

    async def list_messages(self, conversation_key: str) -> list[ChatHistoryMessage]:
        return [
            message.model_copy(deep=True) for message in self._messages.get(conversation_key, [])
        ]

    async def clear(self, conversation_key: str) -> None:
        self._messages.pop(conversation_key, None)
        self._states.pop(conversation_key, None)

    async def get_idempotency(
        self, conversation_key: str, key: str
    ) -> tuple[str, dict[str, Any]] | None:
        record = self._idempotency.get((conversation_key, key))
        return (record[0], deepcopy(record[1])) if record else None

    async def save_idempotency(
        self, conversation_key: str, key: str, request_hash: str, response: dict[str, Any]
    ) -> None:
        self._idempotency[(conversation_key, key)] = (request_hash, deepcopy(response))


class RedisAgentChatStore:
    def __init__(
        self,
        redis_url: str,
        *,
        ttl_seconds: int = 604_800,
        max_messages: int = 100,
        lock_timeout_seconds: int = 60,
        lock_wait_seconds: int = 20,
    ) -> None:
        if redis_async is None:
            raise ChatStoreUnavailable("Redis support requires the optional redis dependency")
        self._redis = redis_async.from_url(redis_url, decode_responses=True)
        self._ttl = ttl_seconds
        self._max_messages = max_messages
        self._lock_timeout = lock_timeout_seconds
        self._lock_wait = lock_wait_seconds

    @asynccontextmanager
    async def lock(self, conversation_key: str) -> AsyncIterator[None]:
        lock = self._redis.lock(
            f"agent:lock:{conversation_key}",
            timeout=self._lock_timeout,
            blocking_timeout=self._lock_wait,
        )
        try:
            acquired = await lock.acquire()
        except Exception as exc:
            raise ChatStoreUnavailable("Redis lock is unavailable") from exc
        if not acquired:
            raise ConversationBusy(conversation_key)
        try:
            yield
        finally:
            with suppress(Exception):
                await lock.release()

    async def get_state(self, conversation_key: str) -> ProcurementSessionState | None:
        try:
            raw = await self._redis.get(self._state_key(conversation_key))
        except Exception as exc:
            raise ChatStoreUnavailable("Redis session state is unavailable") from exc
        return ProcurementSessionState.model_validate_json(raw) if raw else None

    async def save_state(self, conversation_key: str, state: ProcurementSessionState) -> None:
        try:
            await self._redis.setex(
                self._state_key(conversation_key), self._ttl, state.model_dump_json()
            )
        except Exception as exc:
            raise ChatStoreUnavailable("Redis session state is unavailable") from exc

    async def append_message(self, conversation_key: str, message: ChatHistoryMessage) -> None:
        key = self._messages_key(conversation_key)
        try:
            pipe = self._redis.pipeline()
            pipe.rpush(key, message.model_dump_json())
            pipe.ltrim(key, -self._max_messages, -1)
            pipe.expire(key, self._ttl)
            await pipe.execute()
        except Exception as exc:
            raise ChatStoreUnavailable("Redis chat history is unavailable") from exc

    async def set_message_status(
        self, conversation_key: str, message_id: str, status: ChatMessageStatus
    ) -> None:
        messages = await self.list_messages(conversation_key)
        for message in messages:
            if message.message_id == message_id:
                message.status = status
        key = self._messages_key(conversation_key)
        try:
            pipe = self._redis.pipeline()
            pipe.delete(key)
            if messages:
                pipe.rpush(key, *(message.model_dump_json() for message in messages))
                pipe.expire(key, self._ttl)
            await pipe.execute()
        except Exception as exc:
            raise ChatStoreUnavailable("Redis chat history is unavailable") from exc

    async def list_messages(self, conversation_key: str) -> list[ChatHistoryMessage]:
        try:
            rows = await self._redis.lrange(self._messages_key(conversation_key), 0, -1)
        except Exception as exc:
            raise ChatStoreUnavailable("Redis chat history is unavailable") from exc
        return [ChatHistoryMessage.model_validate_json(row) for row in rows]

    async def clear(self, conversation_key: str) -> None:
        try:
            await self._redis.delete(
                self._messages_key(conversation_key), self._state_key(conversation_key)
            )
        except Exception as exc:
            raise ChatStoreUnavailable("Redis chat session is unavailable") from exc

    async def get_idempotency(
        self, conversation_key: str, key: str
    ) -> tuple[str, dict[str, Any]] | None:
        try:
            raw = await self._redis.get(self._idempotency_key(conversation_key, key))
        except Exception as exc:
            raise ChatStoreUnavailable("Redis idempotency store is unavailable") from exc
        if not raw:
            return None
        payload = json.loads(raw)
        return str(payload["request_hash"]), dict(payload["response"])

    async def save_idempotency(
        self, conversation_key: str, key: str, request_hash: str, response: dict[str, Any]
    ) -> None:
        payload = json.dumps(
            {"request_hash": request_hash, "response": response},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        try:
            await self._redis.setex(
                self._idempotency_key(conversation_key, key), self._ttl, payload
            )
        except Exception as exc:
            raise ChatStoreUnavailable("Redis idempotency store is unavailable") from exc

    async def close(self) -> None:
        await self._redis.aclose()

    @staticmethod
    def _messages_key(key: str) -> str:
        return f"agent:messages:{key}"

    @staticmethod
    def _state_key(key: str) -> str:
        return f"agent:state:{key}"

    @staticmethod
    def _idempotency_key(key: str, idempotency_key: str) -> str:
        return f"agent:idempotency:{key}:{idempotency_key}"
