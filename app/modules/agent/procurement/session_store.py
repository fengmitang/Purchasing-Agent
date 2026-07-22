import json
from typing import Protocol

try:
    import redis
except ModuleNotFoundError:  # 允许仅使用内存 Store 的单元测试运行
    redis = None

from app.modules.agent.procurement.schemas import ProcurementSessionState


class ProcurementSessionStoreProtocol(Protocol):
    def get(self, user_id: str, conv_id: str) -> ProcurementSessionState | None: ...

    def save(self, user_id: str, conv_id: str, state: ProcurementSessionState) -> None: ...


class RedisProcurementSessionStore:
    def __init__(self, redis_url: str, ttl_seconds: int = 604800) -> None:
        if redis is None:
            raise RuntimeError("未安装 redis 依赖，无法使用持久化采购会话状态。")
        self._redis = redis.from_url(redis_url, decode_responses=True)
        self._ttl_seconds = ttl_seconds

    def get(self, user_id: str, conv_id: str) -> ProcurementSessionState | None:
        raw = self._redis.get(self._key(user_id, conv_id))
        if not raw:
            return None
        return ProcurementSessionState.model_validate(json.loads(raw))

    def save(self, user_id: str, conv_id: str, state: ProcurementSessionState) -> None:
        self._redis.setex(
            self._key(user_id, conv_id),
            self._ttl_seconds,
            state.model_dump_json(),
        )

    @staticmethod
    def _key(user_id: str, conv_id: str) -> str:
        safe_user = user_id.replace(":", "_")[:128]
        safe_conv = conv_id.replace(":", "_")[:128]
        return f"procurement:session:{safe_user}:{safe_conv}"


class InMemoryProcurementSessionStore:
    """仅用于单元测试和本地无 Redis 联调。"""

    def __init__(self) -> None:
        self._states: dict[tuple[str, str], ProcurementSessionState] = {}

    def get(self, user_id: str, conv_id: str) -> ProcurementSessionState | None:
        return self._states.get((user_id, conv_id))

    def save(self, user_id: str, conv_id: str, state: ProcurementSessionState) -> None:
        self._states[(user_id, conv_id)] = state
