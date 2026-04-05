from datetime import UTC, datetime, timedelta

from autoin.config import Settings
from autoin.coordinator import Coordinator
from autoin.gateway import GatewayPipeline, MemoryCompactor, MessageDebouncer
from autoin.infrastructure.models import ConversationRef, EventType, Platform


class StubBroker:
    def __init__(self) -> None:
        self.events = []
        self.tasks = []
        self.plan_states = {}

    def publish(self, event):  # noqa: ANN001
        self.events.append(event)
        return f"{len(self.events)}-0"

    def enqueue_task(self, task):  # noqa: ANN001
        self.tasks.append(task)
        return f"{len(self.events) + len(self.tasks)}-0"

    def save_plan_state(self, state):  # noqa: ANN001
        self.plan_states[state.plan.plan_id] = state

    def load_plan_state(self, plan_id: str):
        return self.plan_states.get(plan_id)

    def delete_plan_state(self, plan_id: str) -> int:
        existed = plan_id in self.plan_states
        self.plan_states.pop(plan_id, None)
        return int(existed)


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


def test_gateway_pipeline_can_build_and_dispatch_plan_from_compacted_event() -> None:
    broker = StubBroker()
    compactor = MemoryCompactor(broker, Settings(redis_host="redis.internal.example.com"))
    coordinator = Coordinator(broker)
    pipeline = GatewayPipeline(MessageDebouncer(broker), compactor, coordinator)
    conversation = ConversationRef(platform=Platform.XIAOHONGSHU, user_id="u3")
    compacted_event = compactor.publish_compaction(
        conversation=conversation,
        full_history=["我想下单", "地址在上海", "货号A123"],
        latest_screenshot_ref="shot-2",
    )

    routed, stream_ids = pipeline.route_and_plan(compacted_event)

    assert routed.payload.intent == "dispatch"
    assert stream_ids == ["5-0"]
    assert broker.events[-1].event_type == EventType.TASK_CREATED
    assert broker.tasks[0].action == "capture_and_validate_order"
