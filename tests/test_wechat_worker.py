from datetime import UTC, datetime

from autoin.infrastructure.lock_manager import LockLease
from autoin.infrastructure.models import ConversationRef, Platform, TaskKind, TaskPayload
from autoin.tools.wechat_worker import (
    default_consumer_name,
    main,
    run_wechat_worker_loop,
    run_wechat_worker_once,
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


def build_dispatch_task() -> TaskPayload:
    return TaskPayload(
        kind=TaskKind.UI_ACTION,
        adapter="wechat.executor",
        target=ConversationRef(platform=Platform.XIAOHONGSHU, user_id="u1"),
        action="send_dispatch_message",
        arguments={
            "source_platform": Platform.XIAOHONGSHU,
            "dispatch_target_uid": "AUTOIN_SMOKE_TEST",
            "extracted_fields": {"item_code": "A123"},
            "reason": "worker_test",
        },
    )


def test_run_wechat_worker_once_processes_single_batch() -> None:
    broker = StubBroker()
    broker.tasks = [("1-0", build_dispatch_task())]

    result = run_wechat_worker_once(
        consumer_name="worker-1",
        prefer_pywinauto=False,
        count=1,
        block_ms=1,
        broker=broker,
        lock_manager=StubLockManager(),
    )

    assert result["consumer_name"] == "worker-1"
    assert result["processed_stream_ids"] == ["1-0"]
    assert result["last_action_result"] is not None
    assert result["last_action_result"]["driver"] == "mock_windows"
    assert broker.group_ensured == 1
    assert broker.acked == ["1-0"]


def test_run_wechat_worker_loop_stops_after_max_batches() -> None:
    broker = StubBroker()
    broker.tasks = [("1-0", build_dispatch_task())]

    result = run_wechat_worker_loop(
        consumer_name="worker-1",
        prefer_pywinauto=False,
        count=1,
        block_ms=1,
        max_batches=2,
        broker=broker,
        lock_manager=StubLockManager(),
    )

    assert result["batches"] == 2
    assert result["processed_stream_ids"] == ["1-0", "1-0"]


def test_default_consumer_name_uses_hostname() -> None:
    assert default_consumer_name().startswith("wechat-worker-")


def test_wechat_worker_main_supports_mock_driver(capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        "autoin.tools.wechat_worker.run_wechat_worker_once",
        lambda **kwargs: {
            "consumer_name": kwargs["consumer_name"],
            "processed_stream_ids": ["1-0"],
            "last_action_result": {"driver": "mock_windows"},
            "last_rollback_result": None,
        },
    )

    exit_code = main(["--once", "--consumer-name", "worker-1", "--mock-driver"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"consumer_name": "worker-1"' in captured.out
    assert '"processed_stream_ids": [' in captured.out
