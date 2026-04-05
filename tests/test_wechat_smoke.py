from autoin.tools.wechat_smoke import (
    build_wechat_dispatch_task,
    main,
    run_wechat_dispatch_smoke,
)


class StubBroker:
    def __init__(self) -> None:
        self.events = []

    def publish(self, event):  # noqa: ANN001
        self.events.append(event)
        return "1-0"


class StubLockManager:
    def acquire(self, owner_id: str):  # noqa: ANN001
        from datetime import UTC, datetime

        from autoin.infrastructure.lock_manager import LockLease

        return LockLease(
            key="autoin:lock:ui",
            owner_id=owner_id,
            token="token-1",
            expires_at=datetime.now(UTC),
        )

    def release(self, lease):  # noqa: ANN001
        return True

    def snapshot(self, lease, state):  # noqa: ANN001
        return {"lock_key": lease.key, "owner_id": lease.owner_id, "expires_at": lease.expires_at, "state": state}


def test_build_wechat_dispatch_task_populates_structured_arguments() -> None:
    task = build_wechat_dispatch_task(
        source_platform="xiaohongshu",
        source_user_id="u1",
        dispatch_target_uid="wechat_dispatch_group",
        extracted_fields={"item_code": "A123"},
        screenshot_ref="shot-1",
        reason="manual_smoke_test",
    )

    assert task.action == "send_dispatch_message"
    assert task.arguments["dispatch_target_uid"] == "wechat_dispatch_group"
    assert task.arguments["extracted_fields"] == {"item_code": "A123"}


def test_run_wechat_dispatch_smoke_returns_last_action_result() -> None:
    result = run_wechat_dispatch_smoke(
        source_platform="xiaohongshu",
        source_user_id="u1",
        dispatch_target_uid="wechat_dispatch_group",
        extracted_fields={"item_code": "A123", "address": "Shanghai"},
        screenshot_ref="shot-1",
        prefer_pywinauto=False,
        broker=StubBroker(),
        lock_manager=StubLockManager(),
    )

    assert result["task_status"] == "succeeded"
    assert result["action_result"] is not None
    assert result["action_result"]["driver"] == "mock_windows"
    assert result["action_result"]["dispatch_target_uid"] == "wechat_dispatch_group"


def test_wechat_smoke_main_supports_mock_driver(capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        "autoin.tools.wechat_smoke.run_wechat_dispatch_smoke",
        lambda **kwargs: {
            "event_type": "action_completed",
            "task_status": "succeeded",
            "action_result": {
                "dispatch_target_uid": kwargs["dispatch_target_uid"],
                "driver": "mock_windows",
            },
        },
    )

    exit_code = main(
        [
            "--source-user-id",
            "u1",
            "--dispatch-target-uid",
            "wechat_dispatch_group",
            "--item-code",
            "A123",
            "--mock-driver",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"task_status": "succeeded"' in captured.out
    assert '"dispatch_target_uid": "wechat_dispatch_group"' in captured.out
