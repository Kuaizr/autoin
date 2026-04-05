from datetime import UTC, datetime

from autoin.adapters.runtime import ExecutorAdapter, ObserverAdapter, TaskWorker
from autoin.infrastructure.lock_manager import LockLease
from autoin.infrastructure.models import (
    ConversationRef,
    EventType,
    LockStatePayload,
    Platform,
    TaskKind,
    TaskPayload,
)


class StubBroker:
    def __init__(self) -> None:
        self.events = []
        self.tasks = []
        self.acked = []
        self.group_ensured = 0

    def publish(self, event):  # noqa: ANN001
        self.events.append(event)
        return "1-0"

    def ensure_consumer_group(self) -> None:
        self.group_ensured += 1

    def consume_tasks(self, consumer_name: str, count: int, block_ms: int):  # noqa: ANN001
        return list(self.tasks)

    def ack_task(self, stream_id: str) -> int:
        self.acked.append(stream_id)
        return 1


class StubLockManager:
    def __init__(self) -> None:
        self.acquired = []
        self.released = []

    def acquire(self, owner_id: str) -> LockLease:
        self.acquired.append(owner_id)
        return LockLease(
            key="autoin:lock:ui",
            owner_id=owner_id,
            token="token-1",
            expires_at=datetime.now(UTC),
        )

    def release(self, lease: LockLease) -> bool:
        self.released.append(lease.token)
        return True

    def snapshot(self, lease: LockLease, state: str):  # noqa: ANN001
        return LockStatePayload(
            lock_key=lease.key,
            owner_id=lease.owner_id,
            expires_at=lease.expires_at,
            state=state,
        )


def test_observer_publishes_buffered_message_event() -> None:
    broker = StubBroker()
    adapter = ObserverAdapter("douyin.observer", Platform.DOUYIN, broker)

    event = adapter.emit_messages(
        ConversationRef(platform=Platform.DOUYIN, user_id="u1"),
        ["hello", "world"],
    )

    assert event.event_type == EventType.MESSAGE_BUFFERED
    assert broker.events[-1].payload.messages == ["hello", "world"]


def test_executor_acquires_and_releases_lock_around_action() -> None:
    broker = StubBroker()
    lock_manager = StubLockManager()
    adapter = ExecutorAdapter("wechat.executor", Platform.WECHAT, broker, lock_manager)
    task = TaskPayload(kind=TaskKind.UI_ACTION, adapter="wechat.executor", action="send_group_message")

    event = adapter.execute_action(task)

    assert event.event_type == EventType.ACTION_COMPLETED
    assert lock_manager.acquired == ["wechat.executor"]
    assert lock_manager.released == ["token-1"]
    assert [published.event_type for published in broker.events] == [
        EventType.TASK_STATUS_CHANGED,
        EventType.LOCK_ACQUIRED,
        EventType.ACTION_COMPLETED,
        EventType.LOCK_RELEASED,
    ]


def test_task_worker_consumes_and_acks_executor_tasks() -> None:
    broker = StubBroker()
    lock_manager = StubLockManager()
    executor = ExecutorAdapter("wechat.executor", Platform.WECHAT, broker, lock_manager)
    broker.tasks = [
        ("1-0", TaskPayload(kind=TaskKind.UI_ACTION, adapter="wechat.executor", action="send_group_message"))
    ]
    worker = TaskWorker(broker, executor, consumer_name="worker-1")

    processed = worker.poll_once()

    assert processed == ["1-0"]
    assert broker.group_ensured == 1
    assert broker.acked == ["1-0"]


def test_executor_rolls_back_when_action_handler_fails() -> None:
    broker = StubBroker()
    lock_manager = StubLockManager()

    def failing_handler(task: TaskPayload) -> dict[str, object]:
        raise RuntimeError(f"action failed for {task.task_id}")

    adapter = ExecutorAdapter(
        "wechat.executor",
        Platform.WECHAT,
        broker,
        lock_manager,
        action_handler=failing_handler,
    )

    try:
        adapter.execute_action(
            TaskPayload(kind=TaskKind.UI_ACTION, adapter="wechat.executor", action="send_group_message")
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected the executor to propagate action failures.")

    assert adapter.rollback_invocations == 1
    assert EventType.ERROR_RAISED in [published.event_type for published in broker.events]


def test_task_worker_routes_failures_to_handler_and_acks() -> None:
    broker = StubBroker()
    lock_manager = StubLockManager()
    routed_failures = []

    def failing_handler(task: TaskPayload) -> dict[str, object]:
        raise RuntimeError("focus lost")

    def route_failure(task: TaskPayload, error_code: str, error_message: str, retryable: bool):
        routed_failures.append((task.task_id, error_code, error_message, retryable))
        return "retry-1", None

    executor = ExecutorAdapter(
        "wechat.executor",
        Platform.WECHAT,
        broker,
        lock_manager,
        action_handler=failing_handler,
    )
    broker.tasks = [
        ("1-0", TaskPayload(kind=TaskKind.UI_ACTION, adapter="wechat.executor", action="send_group_message"))
    ]
    worker = TaskWorker(
        broker,
        executor,
        consumer_name="worker-1",
        failure_handler=route_failure,
    )

    processed = worker.poll_once()

    assert processed == ["1-0"]
    assert broker.acked == ["1-0"]
    assert routed_failures[0][1:] == ("action_execution_failed", "focus lost", True)


def test_task_worker_routes_success_to_handler() -> None:
    broker = StubBroker()
    lock_manager = StubLockManager()
    succeeded = []

    def route_success(task: TaskPayload):
        succeeded.append(task.task_id)
        return []

    task = TaskPayload(
        task_id="task-1",
        plan_id="plan-1",
        kind=TaskKind.UI_ACTION,
        adapter="wechat.executor",
        action="send_group_message",
    )
    executor = ExecutorAdapter("wechat.executor", Platform.WECHAT, broker, lock_manager)
    broker.tasks = [("1-0", task)]
    worker = TaskWorker(
        broker,
        executor,
        consumer_name="worker-1",
        success_handler=route_success,
    )

    processed = worker.poll_once()

    assert processed == ["1-0"]
    assert succeeded == ["task-1"]
