from __future__ import annotations

from abc import ABC, abstractmethod

from autoin.adapters.actions import ActionRegistry
from autoin.adapters.drivers import DesktopDriver, MockWindowsDriver
from autoin.infrastructure.models import TaskPayload


class WechatActionHandler(ABC):
    """Platform action object boundary for the Windows WeChat executor."""

    action_name: str

    @abstractmethod
    def run(self, task: TaskPayload) -> dict[str, object]:
        """Run a logical action and return structured execution metadata."""


class SendDispatchMessageHandler(WechatActionHandler):
    action_name = "send_dispatch_message"

    def __init__(self, driver: DesktopDriver | None = None) -> None:
        self.driver = driver or MockWindowsDriver()

    def run(self, task: TaskPayload) -> dict[str, object]:
        result = self.driver.send_message(
            app="wechat",
            target_uid=task.target.uid if task.target else None,
            message="dispatch_v1",
        )
        return {
            **result.model_dump(mode="json", exclude_none=True),
            "platform": "wechat",
            "action": self.action_name,
            "source_platform": str(task.arguments.get("source_platform", "")),
            "message_template": "dispatch_v1",
        }


class SendAutoReplyHandler(WechatActionHandler):
    action_name = "send_auto_reply"

    def __init__(self, driver: DesktopDriver | None = None) -> None:
        self.driver = driver or MockWindowsDriver()

    def run(self, task: TaskPayload) -> dict[str, object]:
        message = str(task.arguments.get("message", "auto_reply"))
        result = self.driver.send_message(
            app="wechat",
            target_uid=task.target.uid if task.target else None,
            message=message,
        )
        return {
            **result.model_dump(mode="json", exclude_none=True),
            "platform": "wechat",
            "action": self.action_name,
            "message": message,
        }


def build_wechat_action_registry(driver: DesktopDriver | None = None) -> ActionRegistry:
    registry = ActionRegistry()
    handlers: list[WechatActionHandler] = [
        SendDispatchMessageHandler(driver=driver),
        SendAutoReplyHandler(driver=driver),
    ]
    for handler in handlers:
        registry.register(handler.action_name, handler.run)
    return registry
