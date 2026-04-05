from autoin.adapters.runtime import ObserverAdapter
from autoin.cognitive import CheckerAgent
from autoin.coordinator import Coordinator
from autoin.infrastructure.models import (
    ConversationRef,
    EventType,
    Platform,
    SnapshotRequestPayload,
    TaskKind,
    TaskPayload,
)


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
        return f"{len(self.tasks)}-0"

    def save_plan_state(self, state):  # noqa: ANN001
        self.plan_states[state.plan.plan_id] = state

    def load_plan_state(self, plan_id: str):
        return self.plan_states.get(plan_id)

    def delete_plan_state(self, plan_id: str) -> int:
        existed = plan_id in self.plan_states
        self.plan_states.pop(plan_id, None)
        return int(existed)


def test_coordinator_emits_snapshot_request_for_check_task() -> None:
    broker = StubBroker()
    coordinator = Coordinator(broker)
    task = TaskPayload(
        task_id="check-1",
        kind=TaskKind.CHECK,
        adapter="xiaohongshu.executor",
        target=ConversationRef(platform=Platform.XIAOHONGSHU, user_id="u1"),
        action="capture_and_validate_order",
    )

    event = coordinator.request_snapshot_for_check(task)

    assert event.event_type == EventType.SNAPSHOT_REQUESTED
    assert event.payload.check_task_id == "check-1"
    assert broker.events[-1].payload.adapter == "xiaohongshu.executor"


def test_observer_adapter_publishes_snapshot_captured_event() -> None:
    broker = StubBroker()
    observer = ObserverAdapter("xiaohongshu.observer", Platform.XIAOHONGSHU, broker)
    request = SnapshotRequestPayload(
        conversation=ConversationRef(platform=Platform.XIAOHONGSHU, user_id="u2"),
        check_task_id="check-2",
        adapter="xiaohongshu.executor",
        reason="checker_requires_latest_snapshot",
    )

    event = observer.capture_snapshot(
        request=request,
        screenshot_ref="shot-2",
        extracted_fields={"address": "Shanghai", "item_code": "A123"},
    )

    assert event.event_type == EventType.SNAPSHOT_CAPTURED
    assert event.payload.screenshot_ref == "shot-2"
    assert broker.events[-1].payload.extracted_fields["item_code"] == "A123"


def test_snapshot_capture_can_unlock_dispatch_via_checker() -> None:
    broker = StubBroker()
    coordinator = Coordinator(broker, checker=CheckerAgent())
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
    plan = coordinator.create_plan("corr-snap", [check_task, dispatch_task])
    state, _ = coordinator.dispatch_plan(plan)
    capture_event = ObserverAdapter("xiaohongshu.observer", Platform.XIAOHONGSHU, broker).capture_snapshot(
        request=SnapshotRequestPayload(
            conversation=state.plan.tasks[0].target,
            check_task_id=state.plan.tasks[0].task_id,
            adapter="xiaohongshu.executor",
            reason="checker_requires_latest_snapshot",
        ),
        screenshot_ref="shot-3",
        extracted_fields={"address": "Shanghai", "item_code": "A123"},
    )

    released = coordinator.handle_snapshot_capture(plan.plan_id, capture_event.payload)

    assert released == ["2-0"]
    assert state.completed_task_ids == [state.plan.tasks[0].task_id]
