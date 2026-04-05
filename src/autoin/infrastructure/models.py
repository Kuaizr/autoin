from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class EventType(StrEnum):
    MESSAGE_BUFFERED = "message_buffered"
    MESSAGE_DEBOUNCED = "message_debounced"
    TASK_CREATED = "task_created"
    TASK_STATUS_CHANGED = "task_status_changed"
    ACTION_REQUESTED = "action_requested"
    ACTION_COMPLETED = "action_completed"
    ADAPTER_HEARTBEAT = "adapter_heartbeat"
    MEMORY_COMPACTED = "memory_compacted"
    SNAPSHOT_REQUESTED = "snapshot_requested"
    SNAPSHOT_CAPTURED = "snapshot_captured"
    LOCK_ACQUIRED = "lock_acquired"
    LOCK_RELEASED = "lock_released"
    ERROR_RAISED = "error_raised"


class TaskKind(StrEnum):
    REPLY = "reply"
    DISPATCH = "dispatch"
    CHECK = "check"
    UI_ACTION = "ui_action"
    ROLLBACK = "rollback"


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Platform(StrEnum):
    XIAOHONGSHU = "xiaohongshu"
    XIANYU = "xianyu"
    DOUYIN = "douyin"
    WECHAT = "wechat"
    SYSTEM = "system"


class EventMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    correlation_id: str = Field(default_factory=lambda: str(uuid4()))
    causation_id: str | None = None
    producer: str = Field(..., description="Service or adapter instance name.")
    schema_version: str = Field(default="1.0")
    emitted_at: datetime = Field(default_factory=utc_now)


class ConversationRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: Platform
    user_id: str
    session_id: str | None = None

    @property
    def uid(self) -> str:
        return f"{self.platform}_{self.user_id}"


class MessagePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation: ConversationRef
    messages: list[str] = Field(min_length=1)
    observed_at: datetime = Field(default_factory=utc_now)
    debounce_window_seconds: int = Field(default=10, ge=1)
    screenshot_ref: str | None = Field(default=None, description="Object storage key or local cache key.")


class MemoryCompactionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation: ConversationRef
    compressed_summary: str
    recent_messages: list[str] = Field(default_factory=list)
    latest_screenshot_ref: str | None = None
    source_message_count: int = Field(default=0, ge=0)
    compacted_at: datetime = Field(default_factory=utc_now)


class IntakeDecisionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation: ConversationRef
    intent: Literal["reply", "dispatch"]
    reason: str
    suggested_tasks: list[TaskKind] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utc_now)


class TaskPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(default_factory=lambda: str(uuid4()))
    plan_id: str | None = None
    parent_task_id: str | None = None
    kind: TaskKind
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    sequence: int = Field(default=0, ge=0)
    dependencies: list[str] = Field(default_factory=list)
    adapter: str
    target: ConversationRef | None = None
    action: str = Field(..., description="Logical action name rather than platform-specific selector.")
    arguments: dict[str, Any] = Field(default_factory=dict)
    requires_ui_lock: bool = True
    lock_owner: str | None = None
    max_retries: int = Field(default=3, ge=0)
    retry_count: int = Field(default=0, ge=0)
    idempotency_key: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=utc_now)
    deadline_at: datetime | None = None


class TaskPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(default_factory=lambda: str(uuid4()))
    correlation_id: str
    tasks: list[TaskPayload] = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)


class TaskPlanState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: TaskPlan
    released_task_ids: list[str] = Field(default_factory=list)
    completed_task_ids: list[str] = Field(default_factory=list)
    failed_task_ids: list[str] = Field(default_factory=list)
    blocked: bool = False


class LockStatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lock_key: str
    owner_id: str
    expires_at: datetime
    state: Literal["acquired", "released", "expired"]


class ErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class AdapterHeartbeatPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter: str
    platform: Platform
    role: Literal["observer", "executor"]
    version: str = "0.1.0"
    host: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    observed_at: datetime = Field(default_factory=utc_now)


class UnifiedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: EventType
    metadata: EventMetadata
    payload: (
        MessagePayload
        | IntakeDecisionPayload
        | MemoryCompactionPayload
        | TaskPayload
        | LockStatePayload
        | ErrorPayload
        | AdapterHeartbeatPayload
    )
