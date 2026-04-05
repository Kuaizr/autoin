from __future__ import annotations

from collections.abc import Iterable

from autoin.infrastructure.broker import RedisBroker
from autoin.infrastructure.models import (
    ErrorPayload,
    EventMetadata,
    EventType,
    TaskPayload,
    TaskPlan,
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
        return TaskPlan(correlation_id=correlation_id, tasks=planned_tasks)

    def dispatch_plan(self, plan: TaskPlan) -> list[str]:
        stream_ids: list[str] = []
        for task in plan.tasks:
            created_event = UnifiedEvent(
                event_type=EventType.TASK_CREATED,
                metadata=EventMetadata(
                    producer=self.producer_name,
                    correlation_id=plan.correlation_id,
                ),
                payload=task,
            )
            self.broker.publish(created_event)
            stream_ids.append(self.broker.enqueue_task(task))
        return stream_ids

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
