from __future__ import annotations

from autoin.config import Settings
from autoin.infrastructure.broker import RedisBroker
from autoin.infrastructure.models import (
    ConversationRef,
    EventMetadata,
    EventType,
    MemoryCompactionPayload,
    UnifiedEvent,
)


class MemoryCompactor:
    """Produces a fixed-shape memory package for downstream cognitive agents."""

    def __init__(self, broker: RedisBroker, settings: Settings, producer_name: str = "gateway.memory") -> None:
        self.broker = broker
        self.settings = settings
        self.producer_name = producer_name

    def compact(
        self,
        conversation: ConversationRef,
        full_history: list[str],
        latest_screenshot_ref: str | None = None,
    ) -> MemoryCompactionPayload:
        recent_messages = full_history[-self.settings.memory_recent_turns :]
        older_messages = full_history[: -self.settings.memory_recent_turns] if len(full_history) > self.settings.memory_recent_turns else []
        summary = self._summarize(older_messages)
        return MemoryCompactionPayload(
            conversation=conversation,
            compressed_summary=summary,
            recent_messages=recent_messages,
            latest_screenshot_ref=latest_screenshot_ref,
            source_message_count=len(full_history),
        )

    def publish_compaction(
        self,
        conversation: ConversationRef,
        full_history: list[str],
        latest_screenshot_ref: str | None = None,
    ) -> UnifiedEvent:
        payload = self.compact(
            conversation=conversation,
            full_history=full_history,
            latest_screenshot_ref=latest_screenshot_ref,
        )
        event = UnifiedEvent(
            event_type=EventType.MEMORY_COMPACTED,
            metadata=EventMetadata(producer=self.producer_name),
            payload=payload,
        )
        self.broker.publish(event)
        return event

    def _summarize(self, messages: list[str]) -> str:
        if not messages:
            return ""
        summary = " | ".join(messages)
        return summary[: self.settings.memory_summary_max_chars]
