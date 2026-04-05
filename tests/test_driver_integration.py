from autoin.adapters import build_platform_action_registry
from autoin.adapters.drivers import DesktopDriver, DriverActionResult
from autoin.infrastructure.models import ConversationRef, Platform, TaskKind, TaskPayload


class RecordingDriver(DesktopDriver):
    def __init__(self) -> None:
        self.calls = []

    def send_message(self, app: str, target_uid: str | None, message: str) -> DriverActionResult:
        self.calls.append(("send_message", app, target_uid, message))
        return DriverActionResult(
            driver="recording",
            operation="send_message",
            status="ok",
            app=app,
            target_uid=target_uid,
            message=message,
        )

    def capture_window(self, app: str, target_uid: str | None, mode: str) -> DriverActionResult:
        self.calls.append(("capture_window", app, target_uid, mode))
        return DriverActionResult(
            driver="recording",
            operation="capture_window",
            status="ok",
            app=app,
            target_uid=target_uid,
            mode=mode,
        )

    def rollback_ui(self, app: str, target_uid: str | None = None) -> DriverActionResult:
        self.calls.append(("rollback_ui", app, target_uid))
        return DriverActionResult(
            driver="recording",
            operation="rollback_ui",
            status="ok",
            app=app,
            target_uid=target_uid,
        )


def test_platform_registry_uses_driver_for_wechat_send() -> None:
    driver = RecordingDriver()
    registry = build_platform_action_registry(Platform.WECHAT, driver=driver)
    task = TaskPayload(
        kind=TaskKind.UI_ACTION,
        adapter="wechat.executor",
        target=ConversationRef(platform=Platform.XIAOHONGSHU, user_id="u1"),
        action="send_dispatch_message",
        arguments={"source_platform": Platform.XIAOHONGSHU},
    )

    result = registry.dispatch(task)

    assert result["driver"] == "recording"
    assert driver.calls == [
        (
            "send_message",
            "wechat",
            "xiaohongshu_u1",
            "[AUTO DISPATCH]\nsource_platform: xiaohongshu",
        )
    ]


def test_platform_registry_uses_driver_for_source_capture() -> None:
    driver = RecordingDriver()
    registry = build_platform_action_registry(Platform.DOUYIN, driver=driver)
    task = TaskPayload(
        kind=TaskKind.CHECK,
        adapter="douyin.executor",
        target=ConversationRef(platform=Platform.DOUYIN, user_id="u2"),
        action="capture_and_validate_order",
    )

    result = registry.dispatch(task)

    assert result["driver"] == "recording"
    assert driver.calls == [("capture_window", "douyin", "douyin_u2", "focused_window")]
