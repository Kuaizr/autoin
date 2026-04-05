from autoin.coordinator import Coordinator, TaskDependencyError
from autoin.infrastructure.models import TaskKind, TaskPayload, TaskStatus


class StubBroker:
    def __init__(self) -> None:
        self.events = []
        self.tasks = []
        self.dead_letters = []

    def publish(self, event):  # noqa: ANN001
        self.events.append(event)
        return "1-0"

    def enqueue_task(self, task):  # noqa: ANN001
        self.tasks.append(task)
        return f"{len(self.tasks)}-0"

    def move_to_dead_letter(self, task, reason: str, error_code: str):  # noqa: ANN001
        self.dead_letters.append((task, reason, error_code))
        return f"dead-{len(self.dead_letters)}"


def test_create_plan_requires_dependencies_to_appear_earlier() -> None:
    broker = StubBroker()
    coordinator = Coordinator(broker)
    child = TaskPayload(
        task_id="child",
        kind=TaskKind.UI_ACTION,
        adapter="wechat.executor",
        action="send",
        sequence=1,
        dependencies=["parent"],
    )
    parent = TaskPayload(
        task_id="parent",
        kind=TaskKind.CHECK,
        adapter="wechat.executor",
        action="check",
        sequence=2,
    )

    try:
        coordinator.create_plan("corr-1", [parent, child])
    except TaskDependencyError:
        pass
    else:
        raise AssertionError("Expected dependency ordering validation to fail.")


def test_dispatch_plan_enqueues_all_tasks_in_order() -> None:
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
        action="send",
        sequence=2,
        dependencies=["task-1"],
    )

    plan = coordinator.create_plan("corr-2", [second, first])
    stream_ids = coordinator.dispatch_plan(plan)

    assert stream_ids == ["1-0", "2-0"]
    assert [task.task_id for task in broker.tasks] == ["task-1", "task-2"]
    assert len(broker.events) == 2


def test_route_task_failure_requeues_before_dead_letter() -> None:
    broker = StubBroker()
    coordinator = Coordinator(broker)
    task = TaskPayload(
        task_id="task-1",
        kind=TaskKind.UI_ACTION,
        adapter="wechat.executor",
        action="send",
        retry_count=0,
        max_retries=1,
    )

    stream_id, _ = coordinator.route_task_failure(task, "focus_lost", "Focus lost", retryable=True)

    assert stream_id == "1-0"
    assert broker.tasks[0].retry_count == 1
    assert broker.dead_letters == []

    failed_stream_id, _ = coordinator.route_task_failure(
        broker.tasks[0],
        "focus_lost",
        "Focus lost again",
        retryable=True,
    )
    assert failed_stream_id == "dead-1"
    assert broker.dead_letters[0][0].status == TaskStatus.FAILED
