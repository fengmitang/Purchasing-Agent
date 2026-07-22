import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger("agent.trace")


@dataclass
class AgentTraceEvent:
    event: str
    elapsed_ms: float
    attributes: dict[str, Any] = field(default_factory=dict)


class AgentTrace:
    """请求级轻量Trace；不记录Authorization、完整消息或采购字段值。"""

    def __init__(self, request_id: str, conv_id: str, user_id: str) -> None:
        self.request_id = request_id
        self.conv_id = conv_id
        self.user_id = user_id
        self._started_at = time.monotonic()
        self.events: list[AgentTraceEvent] = []
        self.emit("agent.started")

    def emit(self, event: str, **attributes: Any) -> None:
        record = AgentTraceEvent(
            event=event,
            elapsed_ms=round((time.monotonic() - self._started_at) * 1000, 2),
            attributes=attributes,
        )
        self.events.append(record)
        logger.info(
            json.dumps(
                {
                    "trace_id": self.request_id,
                    "request_id": self.request_id,
                    "conv_id": self.conv_id,
                    "user_id": self.user_id,
                    **asdict(record),
                },
                ensure_ascii=False,
                default=str,
            )
        )

    def export(self) -> list[dict[str, Any]]:
        return [asdict(event) for event in self.events]
