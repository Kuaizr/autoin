from datetime import UTC, datetime

from autoin.adapters import build_executor_adapter, build_platform_action_registry
from autoin.infrastructure.lock_manager import LockLease
from autoin.infrastructure.models import ConversationRef, Platform, TaskKind, TaskPayload


class StubBroker:
    def __init__(self) -> None:
        self.events = []

    def publish(self, event):  # noqa: ANN001
        self.events.append(event)
        return "1-0"


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

    def snapshot(self, lease: LockLease, state: str):  # noqa: ANN001
        return {
            "lock_key": lease.key,
            "owner_id": lease.owner_id,
            "expires_at": lease.expires_at,
            "state": state,
        }


def test_build_platform_action_registry_selects_wechat_handlers() -> None:
    registry = build_platform_action_registry(Platform.WECHAT)
    assert registry.has_action("send_dispatch_message") is True


def test_build_executor_adapter_uses_platform_registry() -> None:
    broker = StubBroker()
    adapter = build_executor_adapter(
        adapter_name="xiaohongshu.executor",
        platform_name=Platform.XIAOHONGSHU,
        broker=broker,
        lock_manager=StubLockManager(),
    )
    task = TaskPayload(
        kind=TaskKind.CHECK,
        adapter="xiaohongshu.executor",
        target=ConversationRef(platform=Platform.XIAOHONGSHU, user_id="u1"),
        action="capture_and_validate_order",
    )

    event = adapter.execute_action(task)

    assert event.payload.status == "succeeded"


def test_build_executor_adapter_wires_driver_rollback_handler() -> None:
    broker = StubBroker()
    adapter = build_executor_adapter(
        adapter_name="wechat.executor",
        platform_name=Platform.WECHAT,
        broker=broker,
        lock_manager=StubLockManager(),
    )

    adapter.rollback_last_action()

    assert adapter.last_rollback_result is not None
    assert adapter.last_rollback_result["operation"] == "rollback_ui"
    assert adapter.last_rollback_result["app"] == "wechat"
