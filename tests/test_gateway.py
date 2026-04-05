from datetime import UTC, datetime, timedelta

from autoin.config import Settings
from autoin.gateway import MemoryCompactor, MessageDebouncer
from autoin.infrastructure.models import ConversationRef, EventType, Platform


class StubBroker:
    def __init__(self) -> None:
        self.events = []

    def publish(self, event):  # noqa: ANN001
        self.events.append(event)
        return "1-0"


def test_message_debouncer_groups_messages_by_uid_until_deadline() -> None:
    broker = StubBroker()
    debouncer = MessageDebouncer(broker)
    conversation = ConversationRef(platform=Platform.DOUYIN, user_id="u1")
    base_time = datetime.now(UTC)

    debouncer.add_message(conversation, "hello", observed_at=base_time, debounce_window_seconds=10)
    debouncer.add_message(
        conversation,
        "world",
        observed_at=base_time + timedelta(seconds=3),
        screenshot_ref="shot-2",
        debounce_window_seconds=10,
    )

    assert debouncer.flush_due(base_time + timedelta(seconds=12)) == []

    events = debouncer.flush_due(base_time + timedelta(seconds=14))

    assert len(events) == 1
    assert events[0].event_type == EventType.MESSAGE_DEBOUNCED
    assert events[0].payload.messages == ["hello", "world"]
    assert events[0].payload.screenshot_ref == "shot-2"


def test_memory_compactor_keeps_recent_turns_and_summarizes_older_history() -> None:
    broker = StubBroker()
    settings = Settings(
        redis_host="redis.internal.example.com",
        memory_recent_turns=3,
        memory_summary_max_chars=100,
    )
    compactor = MemoryCompactor(broker, settings)
    conversation = ConversationRef(platform=Platform.XIAOHONGSHU, user_id="u2")

    payload = compactor.compact(
        conversation=conversation,
        full_history=["m1", "m2", "m3", "m4", "m5"],
        latest_screenshot_ref="shot-5",
    )

    assert payload.recent_messages == ["m3", "m4", "m5"]
    assert payload.compressed_summary == "m1 | m2"
    assert payload.latest_screenshot_ref == "shot-5"


def test_memory_compactor_publishes_fixed_shape_event() -> None:
    broker = StubBroker()
    settings = Settings(redis_host="redis.internal.example.com")
    compactor = MemoryCompactor(broker, settings)
    conversation = ConversationRef(platform=Platform.XIANYU, user_id="u3")

    event = compactor.publish_compaction(
        conversation=conversation,
        full_history=["a", "b", "c", "d", "e", "f"],
        latest_screenshot_ref="shot-6",
    )

    assert event.event_type == EventType.MEMORY_COMPACTED
    assert event.payload.recent_messages == ["b", "c", "d", "e", "f"]
    assert broker.events[-1].payload.source_message_count == 6
