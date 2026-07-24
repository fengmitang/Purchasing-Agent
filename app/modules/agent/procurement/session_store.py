import json
from typing import Protocol

try:
    import redis.asyncio as redis
except ModuleNotFoundError:  # 允许仅使用内存 Store 的单元测试运行
    redis = None

from app.modules.agent.procurement.schemas import ProcurementSessionState


class ProcurementSessionStoreProtocol(Protocol):
    async def get(
        self, organization_id: int, user_id: str, conv_id: str
    ) -> ProcurementSessionState | None: ...

    async def save(
        self,
        organization_id: int,
        user_id: str,
        conv_id: str,
        state: ProcurementSessionState,
    ) -> None: ...

    async def clear(self, organization_id: int, user_id: str, conv_id: str) -> None: ...


class RedisProcurementSessionStore:
    def __init__(self, redis_url: str, ttl_seconds: int = 604800) -> None:
        if redis is None:
            raise RuntimeError("未安装 redis 依赖，无法使用持久化采购会话状态。")
        self._redis = redis.from_url(redis_url, decode_responses=True)
        self._ttl_seconds = ttl_seconds

    async def get(
        self, organization_id: int, user_id: str, conv_id: str
    ) -> ProcurementSessionState | None:
        raw = await self._redis.get(self._key(organization_id, user_id, conv_id))
        if not raw:
            return None
        return ProcurementSessionState.model_validate(json.loads(raw))

    async def save(
        self,
        organization_id: int,
        user_id: str,
        conv_id: str,
        state: ProcurementSessionState,
    ) -> None:
        await self._redis.setex(
            self._key(organization_id, user_id, conv_id),
            self._ttl_seconds,
            state.model_dump_json(),
        )

    async def clear(self, organization_id: int, user_id: str, conv_id: str) -> None:
        await self._redis.delete(self._key(organization_id, user_id, conv_id))

    async def close(self) -> None:
        await self._redis.aclose()

    @staticmethod
    def _key(organization_id: int, user_id: str, conv_id: str) -> str:
        safe_user = user_id.replace(":", "_")[:128]
        safe_conv = conv_id.replace(":", "_")[:128]
        return f"procurement:session:{organization_id}:{safe_user}:{safe_conv}"


class InMemoryProcurementSessionStore:
    """仅用于单元测试和本地无 Redis 联调。"""

    def __init__(self) -> None:
        self._states: dict[tuple[int, str, str], ProcurementSessionState] = {}

    async def get(
        self, organization_id: int, user_id: str, conv_id: str
    ) -> ProcurementSessionState | None:
        state = self._states.get((organization_id, user_id, conv_id))
        return state.model_copy(deep=True) if state is not None else None

    async def save(
        self,
        organization_id: int,
        user_id: str,
        conv_id: str,
        state: ProcurementSessionState,
    ) -> None:
        self._states[(organization_id, user_id, conv_id)] = state.model_copy(deep=True)

    async def clear(self, organization_id: int, user_id: str, conv_id: str) -> None:
        self._states.pop((organization_id, user_id, conv_id), None)
