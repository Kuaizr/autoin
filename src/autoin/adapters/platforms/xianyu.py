from __future__ import annotations

from abc import ABC, abstractmethod

from autoin.adapters.actions import ActionRegistry
from autoin.adapters.drivers import DesktopDriver, MockWindowsDriver
from autoin.infrastructure.models import TaskPayload


class XianyuActionHandler(ABC):
    """Platform action object boundary for the Windows Xianyu executor."""

    action_name: str

    @abstractmethod
    def run(self, task: TaskPayload) -> dict[str, object]:
        """Run a logical action and return structured execution metadata."""


class CaptureAndValidateOrderHandler(XianyuActionHandler):
    action_name = "capture_and_validate_order"

    def __init__(self, driver: DesktopDriver | None = None) -> None:
        self.driver = driver or MockWindowsDriver()

    def run(self, task: TaskPayload) -> dict[str, object]:
        result = self.driver.capture_window(
            app="xianyu",
            target_uid=task.target.uid if task.target else None,
            mode="conversation_panel",
        )
        return {
            "platform": "xianyu",
            "action": self.action_name,
            "capture_mode": "conversation_panel",
            "requires_latest_snapshot": True,
            **result,
        }


class SendAutoReplyHandler(XianyuActionHandler):
    action_name = "send_auto_reply"

    def __init__(self, driver: DesktopDriver | None = None) -> None:
        self.driver = driver or MockWindowsDriver()

    def run(self, task: TaskPayload) -> dict[str, object]:
        message = str(task.arguments.get("message", "auto_reply"))
        result = self.driver.send_message(
            app="xianyu",
            target_uid=task.target.uid if task.target else None,
            message=message,
        )
        return {
            "platform": "xianyu",
            "action": self.action_name,
            "message": message,
            **result,
        }


def build_xianyu_action_registry(driver: DesktopDriver | None = None) -> ActionRegistry:
    registry = ActionRegistry()
    handlers: list[XianyuActionHandler] = [
        CaptureAndValidateOrderHandler(driver=driver),
        SendAutoReplyHandler(driver=driver),
    ]
    for handler in handlers:
        registry.register(handler.action_name, handler.run)
    return registry
