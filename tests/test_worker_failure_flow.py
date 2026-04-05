from datetime import UTC, datetime

from autoin.adapters.runtime import ExecutorAdapter, TaskWorker
from autoin.coordinator import Coordinator
from autoin.infrastructure.lock_manager import LockLease
from autoin.infrastructure.models import LockStatePayload, Platform, TaskKind, TaskPayload


class StubBroker:
    def __init__(self) -> None:
        self.events = []
        self.tasks = []
        self.acked = []
        self.dead_letters = []
        self.group_ensured = 0
        self.plan_states = {}

    def publish(self, event):  # noqa: ANN001
        self.events.append(event)
        return "1-0"

    def ensure_consumer_group(self) -> None:
        self.group_ensured += 1

    def consume_tasks(self, consumer_name: str, count: int, block_ms: int):  # noqa: ANN001
        return list(self.tasks)

    def enqueue_task(self, task):  # noqa: ANN001
        self.tasks.append(("retry", task))
        return "retry-1"

    def ack_task(self, stream_id: str) -> int:
        self.acked.append(stream_id)
        return 1

    def move_to_dead_letter(self, task, reason: str, error_code: str):  # noqa: ANN001
        self.dead_letters.append((task, reason, error_code))
        return "dead-1"

    def save_plan_state(self, state):  # noqa: ANN001
        self.plan_states[state.plan.plan_id] = state

    def load_plan_state(self, plan_id: str):
        return self.plan_states.get(plan_id)

    def delete_plan_state(self, plan_id: str) -> int:
        existed = plan_id in self.plan_states
        self.plan_states.pop(plan_id, None)
        return int(existed)


class StubLockManager:
    def acquire(self, owner_id: str) -> LockLease:
        return LockLease(
            key="autoin:lock:ui",
            owner_id=owner_id,
            token="token-1",
            expires_at=datetime.now(UTC),
        )

    def release(self, lease: LockLease) -> bool:
        return True

    def snapshot(self, lease: LockLease, state: str) -> LockStatePayload:
        return LockStatePayload(
            lock_key=lease.key,
            owner_id=lease.owner_id,
            expires_at=lease.expires_at,
            state=state,
        )


def test_worker_requeues_failed_task_via_coordinator_handler() -> None:
    broker = StubBroker()
    coordinator = Coordinator(broker)

    def failing_handler(task: TaskPayload) -> dict[str, object]:
        raise RuntimeError("focus lost")

    executor = ExecutorAdapter(
        "wechat.executor",
        Platform.WECHAT,
        broker,
        StubLockManager(),
        action_handler=failing_handler,
    )
    original_task = TaskPayload(
        task_id="task-1",
        kind=TaskKind.UI_ACTION,
        adapter="wechat.executor",
        action="send_group_message",
        retry_count=0,
        max_retries=1,
    )
    broker.tasks = [("1-0", original_task)]

    worker = TaskWorker(
        broker,
        executor,
        consumer_name="worker-1",
        failure_handler=coordinator.route_task_failure,
    )

    processed = worker.poll_once()

    assert processed == ["1-0"]
    assert broker.acked == ["1-0"]
    assert broker.tasks[-1][1].retry_count == 1
    assert broker.dead_letters == []


def test_worker_success_releases_dependent_tasks_via_coordinator_handler() -> None:
    broker = StubBroker()
    coordinator = Coordinator(broker)

    first = TaskPayload(
        task_id="task-1",
        kind=TaskKind.CHECK,
        adapter="wechat.executor",
        action="check",
        sequence=1,
    )
    second = TaskPayload(
        task_id="task-2",
        kind=TaskKind.UI_ACTION,
        adapter="wechat.executor",
        action="send_group_message",
        sequence=2,
        dependencies=["task-1"],
    )
    plan = coordinator.create_plan("corr-6", [first, second])
    state, _ = coordinator.dispatch_plan(plan)

    executor = ExecutorAdapter(
        "wechat.executor",
        Platform.WECHAT,
        broker,
        StubLockManager(),
    )
    broker.tasks = [("1-0", state.plan.tasks[0])]

    worker = TaskWorker(
        broker,
        executor,
        consumer_name="worker-1",
        success_handler=coordinator.handle_task_success,
    )

    processed = worker.poll_once()

    assert processed == ["1-0"]
    assert broker.acked == ["1-0"]
    assert broker.tasks[-1][1].task_id == "task-2"
