from datetime import UTC, datetime, timedelta

from autoin.config import Settings
from autoin.infrastructure.models import (
    CheckerDecisionPayload,
    ConversationRef,
    EventMetadata,
    EventType,
    MemoryCompactionPayload,
    MessagePayload,
    Platform,
    SnapshotCapturedPayload,
    TaskKind,
    TaskPayload,
    UnifiedEvent,
)
from autoin.tools.control_plane import ControlPlaneService, emit_control_plane_log, main, resolve_start_stream_id


class StubBroker:
    def __init__(self) -> None:
        self.events = []
        self.tasks = []
        self.plan_states = {}
        self.stream_entries = []

    def publish(self, event):  # noqa: ANN001
        self.events.append(event)
        return f"{len(self.events)}-0"

    def enqueue_task(self, task):  # noqa: ANN001
        self.tasks.append(task)
        return f"{len(self.tasks)}-0"

    def save_plan_state(self, state):  # noqa: ANN001
        self.plan_states[state.plan.plan_id] = state

    def load_plan_state(self, plan_id: str):
        return self.plan_states.get(plan_id)

    def delete_plan_state(self, plan_id: str) -> int:
        existed = plan_id in self.plan_states
        self.plan_states.pop(plan_id, None)
        return int(existed)

    def list_plan_states(self):
        return list(self.plan_states.values())

    def read_stream(self, last_stream_id: str = "0-0", count: int = 10, block_ms: int = 1000):  # noqa: ARG002
        return list(self.stream_entries[:count])

    def latest_event_stream_id(self) -> str:
        return "99-0"


def build_service(broker: StubBroker) -> ControlPlaneService:
    return ControlPlaneService(broker, Settings(redis_host="redis.internal.example.com"))


def test_control_plane_processes_debounced_message_into_compaction() -> None:
    broker = StubBroker()
    service = build_service(broker)
    event = UnifiedEvent(
        event_type=EventType.MESSAGE_DEBOUNCED,
        metadata=EventMetadata(producer="test"),
        payload=MessagePayload(
            conversation=ConversationRef(platform=Platform.XIAOHONGSHU, user_id="u1"),
            messages=["我想下单", "地址在上海"],
        ),
    )

    result = service.process_event(event)

    assert result["handled"] is True
    assert result["action"] == "publish_memory_compaction"
    assert broker.events[-1].event_type == EventType.MEMORY_COMPACTED


def test_control_plane_routes_compacted_event_into_tasks() -> None:
    broker = StubBroker()
    service = build_service(broker)
    event = UnifiedEvent(
        event_type=EventType.MEMORY_COMPACTED,
        metadata=EventMetadata(producer="test"),
        payload=MemoryCompactionPayload(
            conversation=ConversationRef(platform=Platform.XIAOHONGSHU, user_id="u2"),
            compressed_summary="",
            recent_messages=["我想下单", "地址在上海", "电话13800138000"],
            latest_screenshot_ref="shot-1",
            source_message_count=3,
        ),
    )

    result = service.process_event(event)

    assert result["handled"] is True
    assert result["action"] == "route_and_plan"
    assert broker.tasks[0].action == "capture_and_validate_order"


def test_control_plane_extracts_wechat_customer_id_and_dispatch_target() -> None:
    broker = StubBroker()
    service = build_service(broker)
    event = UnifiedEvent(
        event_type=EventType.MEMORY_COMPACTED,
        metadata=EventMetadata(producer="test"),
        payload=MemoryCompactionPayload(
            conversation=ConversationRef(platform=Platform.WECHAT, user_id="kzr"),
            compressed_summary="",
            recent_messages=["我要下单这个产品，我的客户id是 abc123"],
            latest_screenshot_ref=None,
            source_message_count=1,
        ),
    )

    result = service.process_event(event)

    assert result["handled"] is True
    assert result["action"] == "route_and_plan"
    latest_state = list(broker.plan_states.values())[-1]
    assert len(latest_state.plan.tasks) == 1
    assert latest_state.plan.tasks[0].arguments["dispatch_target_uid"] == "文件传输助手"
    assert latest_state.plan.tasks[0].arguments["extracted_fields"] == {"customer_id": "abc123"}
    assert broker.tasks[0].action == "send_dispatch_message"


def test_control_plane_releases_followup_tasks_after_action_completed() -> None:
    broker = StubBroker()
    service = build_service(broker)
    first = TaskPayload(
        task_id="task-1",
        kind=TaskKind.CHECK,
        adapter="xiaohongshu.executor",
        action="capture_and_validate_order",
        sequence=1,
    )
    second = TaskPayload(
        task_id="task-2",
        kind=TaskKind.UI_ACTION,
        adapter="wechat.executor",
        action="send_dispatch_message",
        sequence=2,
        dependencies=["task-1"],
    )
    plan = service.coordinator.create_plan("corr-1", [first, second])
    state, _ = service.coordinator.dispatch_plan(plan)
    completed_task = state.plan.tasks[0]
    event = UnifiedEvent(
        event_type=EventType.ACTION_COMPLETED,
        metadata=EventMetadata(producer="wechat.executor"),
        payload=completed_task,
    )

    result = service.process_event(event)

    assert result["released_stream_ids"] == ["2-0"]
    assert broker.tasks[-1].task_id == "task-2"


def test_control_plane_handles_snapshot_capture_via_plan_lookup() -> None:
    broker = StubBroker()
    service = build_service(broker)
    check_task = TaskPayload(
        task_id="task-check",
        kind=TaskKind.CHECK,
        adapter="xiaohongshu.executor",
        target=ConversationRef(platform=Platform.XIAOHONGSHU, user_id="u3"),
        action="capture_and_validate_order",
        sequence=1,
    )
    dispatch_task = TaskPayload(
        task_id="task-dispatch",
        kind=TaskKind.UI_ACTION,
        adapter="wechat.executor",
        target=ConversationRef(platform=Platform.XIAOHONGSHU, user_id="u3"),
        action="send_dispatch_message",
        sequence=2,
        dependencies=["task-check"],
    )
    plan = service.coordinator.create_plan("corr-2", [check_task, dispatch_task])
    service.coordinator.dispatch_plan(plan)
    capture = UnifiedEvent(
        event_type=EventType.SNAPSHOT_CAPTURED,
        metadata=EventMetadata(producer="xiaohongshu.observer"),
        payload=SnapshotCapturedPayload(
            conversation=ConversationRef(platform=Platform.XIAOHONGSHU, user_id="u3"),
            check_task_id="task-check",
            adapter="xiaohongshu.executor",
            screenshot_ref="shot-3",
            extracted_fields={"address": "Shanghai", "item_code": "A123"},
        ),
    )

    result = service.process_event(capture)

    assert result["handled"] is True
    assert result["released_stream_ids"] == ["2-0"]


def test_control_plane_run_once_processes_stream_entries() -> None:
    broker = StubBroker()
    service = build_service(broker)
    broker.stream_entries = [
        (
            "1-0",
            UnifiedEvent(
                event_type=EventType.MESSAGE_DEBOUNCED,
                metadata=EventMetadata(producer="test"),
                payload=MessagePayload(
                    conversation=ConversationRef(platform=Platform.XIAOHONGSHU, user_id="u1"),
                    messages=["我想下单", "地址在上海"],
                ),
            ),
        )
    ]

    result = service.run_once(emit_logs=False)

    assert result["last_stream_id"] == "1-0"
    assert result["processed_count"] == 1
    assert result["processed"][0]["action"] == "publish_memory_compaction"


def test_control_plane_run_once_flushes_buffered_messages_after_debounce() -> None:
    broker = StubBroker()
    service = build_service(broker)
    broker.stream_entries = [
        (
            "1-0",
            UnifiedEvent(
                event_type=EventType.MESSAGE_BUFFERED,
                metadata=EventMetadata(producer="wechat.observer"),
                payload=MessagePayload(
                    conversation=ConversationRef(platform=Platform.WECHAT, user_id="kzr"),
                    messages=["我要下单这个产品，我的客户id是 abc123"],
                    observed_at=datetime.now(UTC) - timedelta(seconds=2),
                    debounce_window_seconds=1,
                ),
            ),
        )
    ]

    result = service.run_once(emit_logs=False)

    assert result["processed_count"] == 2
    assert result["processed"][0]["action"] == "debounce_buffered_message"
    assert result["processed"][1]["action"] == "flush_debounce_and_publish_compaction"


def test_emit_control_plane_log_prints_json(capsys) -> None:
    emit_control_plane_log("control_plane_started", {"count": 1})
    captured = capsys.readouterr()

    assert captured.out.strip() == '{"event": "control_plane_started", "count": 1}'


def test_resolve_start_stream_id_defaults_to_latest_event_id() -> None:
    broker = StubBroker()
    service = build_service(broker)

    assert resolve_start_stream_id(service, "latest") == "99-0"
    assert resolve_start_stream_id(service, "12-0") == "12-0"


def test_control_plane_main_supports_quiet_once(capsys, monkeypatch) -> None:
    class StubBroker:
        def latest_event_stream_id(self) -> str:
            return "99-0"

    class StubService:
        broker = StubBroker()

        def run_once(self, **kwargs):  # noqa: ANN003, ANN201
            return {"last_stream_id": "1-0", "processed_count": 0, "processed": []}

        def run_loop(self, **kwargs):  # noqa: ANN003, ANN201
            return {"batches": 1, "last_stream_id": "1-0", "processed_count": 0, "batch_summaries": []}

    monkeypatch.setattr("autoin.tools.control_plane.build_control_plane_service", lambda: StubService())

    exit_code = main(["--once", "--quiet"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"processed_count": 0' in captured.out
