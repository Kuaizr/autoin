from __future__ import annotations

from collections.abc import Iterable

from autoin.infrastructure.broker import RedisBroker
from autoin.infrastructure.models import (
    ErrorPayload,
    EventMetadata,
    EventType,
    TaskPayload,
    TaskPlan,
    TaskPlanState,
    TaskStatus,
    UnifiedEvent,
)


class TaskDependencyError(ValueError):
    pass


class Coordinator:
    """Serial task planner and dispatcher for the Linux control plane."""

    def __init__(self, broker: RedisBroker, producer_name: str = "coordinator") -> None:
        self.broker = broker
        self.producer_name = producer_name

    def create_plan(self, correlation_id: str, tasks: Iterable[TaskPayload]) -> TaskPlan:
        planned_tasks = sorted(tasks, key=lambda item: item.sequence)
        if not planned_tasks:
            raise ValueError("Task plan must include at least one task.")
        self._validate_dependencies(planned_tasks)
        plan = TaskPlan(correlation_id=correlation_id, tasks=planned_tasks)
        updated_tasks = [task.model_copy(update={"plan_id": plan.plan_id}) for task in plan.tasks]
        return plan.model_copy(update={"tasks": updated_tasks})

    def initialize_plan_state(self, plan: TaskPlan) -> TaskPlanState:
        state = TaskPlanState(plan=plan)
        self.broker.save_plan_state(state)
        return state

    def dispatch_plan(self, plan: TaskPlan) -> tuple[TaskPlanState, list[str]]:
        state = self.initialize_plan_state(plan)
        stream_ids = self.release_ready_tasks(state)
        return state, stream_ids

    def release_ready_tasks(self, state: TaskPlanState) -> list[str]:
        if state.blocked:
            return []

        stream_ids: list[str] = []
        completed = set(state.completed_task_ids)
        released = set(state.released_task_ids)

        for task in state.plan.tasks:
            if task.task_id in released:
                continue
            if any(dependency not in completed for dependency in task.dependencies):
                continue
            created_event = UnifiedEvent(
                event_type=EventType.TASK_CREATED,
                metadata=EventMetadata(
                    producer=self.producer_name,
                    correlation_id=state.plan.correlation_id,
                ),
                payload=task,
            )
            self.broker.publish(created_event)
            stream_ids.append(self.broker.enqueue_task(task))
            state.released_task_ids.append(task.task_id)
        self.broker.save_plan_state(state)
        return stream_ids

    def complete_task(self, state: TaskPlanState, task: TaskPayload) -> list[str]:
        if task.task_id not in state.completed_task_ids:
            state.completed_task_ids.append(task.task_id)
        self.broker.save_plan_state(state)
        return self.release_ready_tasks(state)

    def fail_task(self, state: TaskPlanState, task: TaskPayload) -> None:
        if task.task_id not in state.failed_task_ids:
            state.failed_task_ids.append(task.task_id)
        state.blocked = True
        self.broker.save_plan_state(state)

    def get_plan_state(self, plan_id: str) -> TaskPlanState | None:
        return self.broker.load_plan_state(plan_id)

    def recover_active_plans(self) -> list[TaskPlanState]:
        return self.broker.list_plan_states()

    def resume_all(self) -> dict[str, list[str]]:
        resumed: dict[str, list[str]] = {}
        for state in self.recover_active_plans():
            resumed[state.plan.plan_id] = self.release_ready_tasks(state)
        return resumed

    def finalize_plan(self, state: TaskPlanState) -> bool:
        all_tasks_done = len(state.completed_task_ids) == len(state.plan.tasks)
        if not all_tasks_done or state.blocked:
            return False
        self.broker.delete_plan_state(state.plan.plan_id)
        return True

    def handle_task_success(self, task: TaskPayload) -> list[str]:
        if not task.plan_id:
            return []
        state = self.get_plan_state(task.plan_id)
        if state is None:
            return []
        released_stream_ids = self.complete_task(state, task)
        self.finalize_plan(state)
        return released_stream_ids

    def mark_task_status(
        self,
        task: TaskPayload,
        status: TaskStatus,
        causation_id: str | None = None,
    ) -> UnifiedEvent:
        updated_task = task.model_copy(update={"status": status})
        event = UnifiedEvent(
            event_type=EventType.TASK_STATUS_CHANGED,
            metadata=EventMetadata(
                producer=self.producer_name,
                causation_id=causation_id,
            ),
            payload=updated_task,
        )
        self.broker.publish(event)
        return event

    def route_task_failure(
        self,
        task: TaskPayload,
        error_code: str,
        error_message: str,
        retryable: bool = True,
    ) -> tuple[str, UnifiedEvent]:
        if retryable and task.retry_count < task.max_retries:
            retried_task = task.model_copy(
                update={
                    "retry_count": task.retry_count + 1,
                    "status": TaskStatus.PENDING,
                }
            )
            stream_id = self.broker.enqueue_task(retried_task)
            event = UnifiedEvent(
                event_type=EventType.ERROR_RAISED,
                metadata=EventMetadata(producer=self.producer_name),
                payload=ErrorPayload(
                    code=error_code,
                    message=error_message,
                    retryable=True,
                    details={
                        "task_id": task.task_id,
                        "retry_count": retried_task.retry_count,
                    },
                ),
            )
            self.broker.publish(event)
            return stream_id, event

        failed_task = task.model_copy(update={"status": TaskStatus.FAILED})
        if retryable is False:
            # irreversible failures should allow callers to block further dependent release
            pass
        stream_id = self.broker.move_to_dead_letter(
            failed_task,
            reason=error_message,
            error_code=error_code,
        )
        event = UnifiedEvent(
            event_type=EventType.ERROR_RAISED,
            metadata=EventMetadata(producer=self.producer_name),
            payload=ErrorPayload(
                code=error_code,
                message=error_message,
                retryable=False,
                details={"task_id": task.task_id},
            ),
        )
        self.broker.publish(event)
        return stream_id, event

    @staticmethod
    def _validate_dependencies(tasks: list[TaskPayload]) -> None:
        seen_task_ids: set[str] = set()
        seen_sequences: set[int] = set()
        for task in tasks:
            if task.sequence in seen_sequences:
                raise TaskDependencyError(f"Duplicate task sequence detected: {task.sequence}")
            if any(dependency not in seen_task_ids for dependency in task.dependencies):
                raise TaskDependencyError(
                    f"Task {task.task_id} depends on tasks that have not been planned earlier."
                )
            seen_sequences.add(task.sequence)
            seen_task_ids.add(task.task_id)
