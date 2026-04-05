from __future__ import annotations

from abc import ABC, abstractmethod

from autoin.adapters.actions import ActionRegistry
from autoin.adapters.drivers import DesktopDriver, MockWindowsDriver
from autoin.infrastructure.models import TaskPayload


class XiaohongshuActionHandler(ABC):
    """Platform action object boundary for the Windows Xiaohongshu executor."""

    action_name: str

    @abstractmethod
    def run(self, task: TaskPayload) -> dict[str, object]:
        """Run a logical action and return structured execution metadata."""


class CaptureAndValidateOrderHandler(XiaohongshuActionHandler):
    action_name = "capture_and_validate_order"

    def __init__(self, driver: DesktopDriver | None = None) -> None:
        self.driver = driver or MockWindowsDriver()

    def run(self, task: TaskPayload) -> dict[str, object]:
        result = self.driver.capture_window(
            app="xiaohongshu",
            target_uid=task.target.uid if task.target else None,
            mode="fullscreen",
        )
        return {
            **result.model_dump(mode="json", exclude_none=True),
            "platform": "xiaohongshu",
            "action": self.action_name,
            "capture_mode": "fullscreen",
            "requires_latest_snapshot": True,
        }


class SendAutoReplyHandler(XiaohongshuActionHandler):
    action_name = "send_auto_reply"

    def __init__(self, driver: DesktopDriver | None = None) -> None:
        self.driver = driver or MockWindowsDriver()

    def run(self, task: TaskPayload) -> dict[str, object]:
        message = str(task.arguments.get("message", "auto_reply"))
        result = self.driver.send_message(
            app="xiaohongshu",
            target_uid=task.target.uid if task.target else None,
            message=message,
        )
        return {
            **result.model_dump(mode="json", exclude_none=True),
            "platform": "xiaohongshu",
            "action": self.action_name,
            "message": message,
        }


def build_xiaohongshu_action_registry(driver: DesktopDriver | None = None) -> ActionRegistry:
    registry = ActionRegistry()
    handlers: list[XiaohongshuActionHandler] = [
        CaptureAndValidateOrderHandler(driver=driver),
        SendAutoReplyHandler(driver=driver),
    ]
    for handler in handlers:
        registry.register(handler.action_name, handler.run)
    return registry
