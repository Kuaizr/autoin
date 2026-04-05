from datetime import UTC, datetime, timedelta

from autoin.config import Settings
from autoin.coordinator import Coordinator
from autoin.gateway import GatewayPipeline, MemoryCompactor, MessageDebouncer
from autoin.infrastructure.models import ConversationRef, EventType, Platform


class StubBroker:
    def __init__(self) -> None:
        self.events = []

    def publish(self, event):  # noqa: ANN001
        self.events.append(event)
        return f"{len(self.events)}-0"


def test_gateway_pipeline_flushes_debounce_into_memory_compaction() -> None:
    broker = StubBroker()
    debouncer = MessageDebouncer(broker)
    compactor = MemoryCompactor(broker, Settings(redis_host="redis.internal.example.com"))
    coordinator = Coordinator(broker)
    pipeline = GatewayPipeline(debouncer, compactor, coordinator)
    conversation = ConversationRef(platform=Platform.DOUYIN, user_id="u1")
    base_time = datetime.now(UTC)

    debouncer.add_message(conversation, "我想下单", observed_at=base_time)
    debouncer.add_message(conversation, "地址在上海", observed_at=base_time + timedelta(seconds=1))

    compacted = pipeline.flush_and_compact()

    assert compacted == []

    compacted = debouncer.flush_due(base_time + timedelta(seconds=12))
    assert compacted[0].event_type == EventType.MESSAGE_DEBOUNCED


def test_gateway_pipeline_routes_compacted_event_to_intake_decision() -> None:
    broker = StubBroker()
    compactor = MemoryCompactor(broker, Settings(redis_host="redis.internal.example.com"))
    coordinator = Coordinator(broker)
    pipeline = GatewayPipeline(MessageDebouncer(broker), compactor, coordinator)
    conversation = ConversationRef(platform=Platform.XIAOHONGSHU, user_id="u2")
    compacted_event = compactor.publish_compaction(
        conversation=conversation,
        full_history=["我想下单", "地址在上海", "电话13800000000"],
        latest_screenshot_ref="shot-1",
    )

    routed = pipeline.route_compacted_event(compacted_event)

    assert routed.event_type == EventType.ACTION_REQUESTED
    assert routed.payload.intent == "dispatch"
    assert broker.events[-1].payload.suggested_tasks
