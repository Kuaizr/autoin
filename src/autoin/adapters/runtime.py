from __future__ import annotations

from collections.abc import Callable
from socket import gethostname

from autoin.adapters.base import BaseAdapter
from autoin.infrastructure.broker import RedisBroker
from autoin.infrastructure.lock_manager import LockAcquisitionError, RedisLockManager
from autoin.infrastructure.models import (
    AdapterHeartbeatPayload,
    ConversationRef,
    ErrorPayload,
    EventMetadata,
    EventType,
    MessagePayload,
    Platform,
    TaskPayload,
    TaskStatus,
    UnifiedEvent,
)

FailureHandler = Callable[[TaskPayload, str, str, bool], tuple[str, UnifiedEvent]]
SuccessHandler = Callable[[TaskPayload], list[str] | None]


class ObserverAdapter(BaseAdapter):
    """Passive adapter that buffers externally observed messages into events."""

    role = "observer"

    def __init__(self, adapter_name: str, platform_name: Platform, broker: RedisBroker) -> None:
        self.adapter_name = adapter_name
        self.platform_name = platform_name
        self.broker = broker

    def start_listening(self) -> None:
        self.broker.publish(self._heartbeat_event())

    def emit_messages(
        self,
        conversation: ConversationRef,
        messages: list[str],
        screenshot_ref: str | None = None,
    ) -> UnifiedEvent:
        event = UnifiedEvent(
            event_type=EventType.MESSAGE_BUFFERED,
            metadata=EventMetadata(producer=self.adapter_name),
            payload=MessagePayload(
                conversation=conversation,
                messages=messages,
                screenshot_ref=screenshot_ref,
            ),
        )
        self.broker.publish(event)
        return event

    def execute_action(self, task: TaskPayload) -> UnifiedEvent:
        raise NotImplementedError("Observer adapters do not execute foreground actions.")

    def rollback_last_action(self) -> None:
        return None

    def _heartbeat_event(self) -> UnifiedEvent:
        return UnifiedEvent(
            event_type=EventType.ADAPTER_HEARTBEAT,
            metadata=EventMetadata(producer=self.adapter_name),
            payload=AdapterHeartbeatPayload(
                adapter=self.adapter_name,
                platform=self.platform_name,
                role=self.role,
                host=gethostname(),
                capabilities=["observe_messages", "capture_background_snapshot"],
            ),
        )


class ExecutorAdapter(BaseAdapter):
    """Foreground adapter that performs UI actions under the global UI lock."""

    role = "executor"

    def __init__(
        self,
        adapter_name: str,
        platform_name: Platform,
        broker: RedisBroker,
        lock_manager: RedisLockManager,
        action_handler: Callable[[TaskPayload], dict[str, object]] | None = None,
    ) -> None:
        self.adapter_name = adapter_name
        self.platform_name = platform_name
        self.broker = broker
        self.lock_manager = lock_manager
        self.action_handler = action_handler or self._default_action_handler
        self.rollback_invocations = 0

    def start_listening(self) -> None:
        self.broker.publish(self._heartbeat_event())

    def execute_action(self, task: TaskPayload) -> UnifiedEvent:
        lease = None
        running_task = task.model_copy(update={"status": TaskStatus.RUNNING, "lock_owner": self.adapter_name})
        self.broker.publish(
            UnifiedEvent(
                event_type=EventType.TASK_STATUS_CHANGED,
                metadata=EventMetadata(producer=self.adapter_name),
                payload=running_task,
            )
        )

        try:
            if task.requires_ui_lock:
                lease = self.lock_manager.acquire(self.adapter_name)
                self.broker.publish(
                    UnifiedEvent(
                        event_type=EventType.LOCK_ACQUIRED,
                        metadata=EventMetadata(producer=self.adapter_name, causation_id=task.task_id),
                        payload=self.lock_manager.snapshot(lease, "acquired"),
                    )
                )

            result = self.action_handler(task)
            completed_task = running_task.model_copy(update={"status": TaskStatus.SUCCEEDED})
            event = UnifiedEvent(
                event_type=EventType.ACTION_COMPLETED,
                metadata=EventMetadata(producer=self.adapter_name, causation_id=task.task_id),
                payload=completed_task,
            )
            self.broker.publish(event)
            return event
        except LockAcquisitionError as exc:
            self.rollback_last_action()
            error_event = UnifiedEvent(
                event_type=EventType.ERROR_RAISED,
                metadata=EventMetadata(producer=self.adapter_name, causation_id=task.task_id),
                payload=ErrorPayload(
                    code="ui_lock_unavailable",
                    message=str(exc),
                    retryable=True,
                    details={"task_id": task.task_id, "adapter": self.adapter_name},
                ),
            )
            self.broker.publish(error_event)
            raise
        except Exception as exc:
            self.rollback_last_action()
            failed_task = running_task.model_copy(update={"status": TaskStatus.FAILED})
            self.broker.publish(
                UnifiedEvent(
                    event_type=EventType.TASK_STATUS_CHANGED,
                    metadata=EventMetadata(producer=self.adapter_name, causation_id=task.task_id),
                    payload=failed_task,
                )
            )
            error_event = UnifiedEvent(
                event_type=EventType.ERROR_RAISED,
                metadata=EventMetadata(producer=self.adapter_name, causation_id=task.task_id),
                payload=ErrorPayload(
                    code="action_execution_failed",
                    message=str(exc),
                    retryable=True,
                    details={"task_id": task.task_id, "adapter": self.adapter_name},
                ),
            )
            self.broker.publish(error_event)
            raise
        finally:
            if lease is not None:
                self.lock_manager.release(lease)
                self.broker.publish(
                    UnifiedEvent(
                        event_type=EventType.LOCK_RELEASED,
                        metadata=EventMetadata(producer=self.adapter_name, causation_id=task.task_id),
                        payload=self.lock_manager.snapshot(lease, "released"),
                    )
                )

    def rollback_last_action(self) -> None:
        self.rollback_invocations += 1

    @staticmethod
    def _default_action_handler(task: TaskPayload) -> dict[str, object]:
        return {"task_id": task.task_id, "action": task.action}

    def _heartbeat_event(self) -> UnifiedEvent:
        return UnifiedEvent(
            event_type=EventType.ADAPTER_HEARTBEAT,
            metadata=EventMetadata(producer=self.adapter_name),
            payload=AdapterHeartbeatPayload(
                adapter=self.adapter_name,
                platform=self.platform_name,
                role=self.role,
                host=gethostname(),
                capabilities=["execute_ui_action", "rollback_popup"],
            ),
        )


class TaskWorker:
    """Consumes task stream entries and dispatches them to the executor adapter."""

    def __init__(
        self,
        broker: RedisBroker,
        executor: ExecutorAdapter,
        consumer_name: str,
        failure_handler: FailureHandler | None = None,
        success_handler: SuccessHandler | None = None,
    ) -> None:
        self.broker = broker
        self.executor = executor
        self.consumer_name = consumer_name
        self.failure_handler = failure_handler
        self.success_handler = success_handler

    def poll_once(self, count: int = 10, block_ms: int = 1000) -> list[str]:
        self.broker.ensure_consumer_group()
        processed: list[str] = []
        for stream_id, task in self.broker.consume_tasks(
            consumer_name=self.consumer_name,
            count=count,
            block_ms=block_ms,
        ):
            try:
                self.executor.execute_action(task)
                self._handle_success(task)
            except LockAcquisitionError as exc:
                self._handle_failure(task, "ui_lock_unavailable", str(exc), retryable=True)
            except Exception as exc:
                self._handle_failure(task, "action_execution_failed", str(exc), retryable=True)
            self.broker.ack_task(stream_id)
            processed.append(stream_id)
        return processed

    def poll_many(self, batches: int, count: int = 10, block_ms: int = 1000) -> list[str]:
        processed: list[str] = []
        for _ in range(batches):
            processed.extend(self.poll_once(count=count, block_ms=block_ms))
        return processed

    def recover_pending(self, idle_ms: int = 0) -> list[str]:
        processed: list[str] = []
        for stream_id, task in self.broker.pending_tasks(
            consumer_name=self.consumer_name,
            idle_ms=idle_ms,
        ):
            try:
                self.executor.execute_action(task)
                self._handle_success(task)
            except LockAcquisitionError as exc:
                self._handle_failure(task, "ui_lock_unavailable", str(exc), retryable=True)
            except Exception as exc:
                self._handle_failure(task, "action_execution_failed", str(exc), retryable=True)
            self.broker.ack_task(stream_id)
            processed.append(stream_id)
        return processed

    def resume(self, pending_idle_ms: int = 0, poll_count: int = 10, poll_block_ms: int = 1000) -> dict[str, list[str]]:
        return {
            "recovered": self.recover_pending(idle_ms=pending_idle_ms),
            "polled": self.poll_once(count=poll_count, block_ms=poll_block_ms),
        }

    def _handle_failure(
        self,
        task: TaskPayload,
        error_code: str,
        error_message: str,
        retryable: bool,
    ) -> tuple[str, UnifiedEvent] | None:
        if self.failure_handler is None:
            return None
        return self.failure_handler(task, error_code, error_message, retryable)

    def _handle_success(self, task: TaskPayload) -> list[str] | None:
        if self.success_handler is None:
            return None
        return self.success_handler(task)
