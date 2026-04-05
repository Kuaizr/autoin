from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from autoin.infrastructure.broker import RedisBroker
from autoin.infrastructure.models import ConversationRef, EventMetadata, EventType, MessagePayload, UnifiedEvent


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class BufferedConversation:
    conversation: ConversationRef
    messages: list[str] = field(default_factory=list)
    screenshot_ref: str | None = None
    deadline_at: datetime = field(default_factory=utc_now)
    debounce_window_seconds: int = 10


class MessageDebouncer:
    """Buffers messages by UID and emits a single debounced event when the timer expires."""

    def __init__(self, broker: RedisBroker, producer_name: str = "gateway.debouncer") -> None:
        self.broker = broker
        self.producer_name = producer_name
        self.buffers: dict[str, BufferedConversation] = {}

    def add_message(
        self,
        conversation: ConversationRef,
        message: str,
        observed_at: datetime | None = None,
        screenshot_ref: str | None = None,
        debounce_window_seconds: int = 10,
    ) -> None:
        observed = observed_at or utc_now()
        uid = conversation.uid
        buffer = self.buffers.get(uid)
        if buffer is None:
            self.buffers[uid] = BufferedConversation(
                conversation=conversation,
                messages=[message],
                screenshot_ref=screenshot_ref,
                deadline_at=observed + timedelta(seconds=debounce_window_seconds),
                debounce_window_seconds=debounce_window_seconds,
            )
            return

        buffer.messages.append(message)
        if screenshot_ref is not None:
            buffer.screenshot_ref = screenshot_ref
        buffer.deadline_at = observed + timedelta(seconds=buffer.debounce_window_seconds)

    def flush_due(self, now: datetime | None = None) -> list[UnifiedEvent]:
        current_time = now or utc_now()
        due_uids = [uid for uid, buffer in self.buffers.items() if buffer.deadline_at <= current_time]
        events: list[UnifiedEvent] = []
        for uid in due_uids:
            buffer = self.buffers.pop(uid)
            event = UnifiedEvent(
                event_type=EventType.MESSAGE_DEBOUNCED,
                metadata=EventMetadata(producer=self.producer_name),
                payload=MessagePayload(
                    conversation=buffer.conversation,
                    messages=buffer.messages,
                    debounce_window_seconds=buffer.debounce_window_seconds,
                    screenshot_ref=buffer.screenshot_ref,
                ),
            )
            self.broker.publish(event)
            events.append(event)
        return events

    def pending_uids(self) -> list[str]:
        return list(self.buffers.keys())
