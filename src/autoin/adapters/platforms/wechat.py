from __future__ import annotations

from abc import ABC, abstractmethod

from autoin.adapters.actions import ActionRegistry
from autoin.adapters.drivers import DesktopDriver, MockWindowsDriver
from autoin.infrastructure.models import TaskPayload


def render_dispatch_message(arguments: dict[str, object]) -> str:
    source_platform = str(arguments.get("source_platform", "unknown"))
    extracted_fields = arguments.get("extracted_fields", {})
    screenshot_ref = str(arguments.get("screenshot_ref", "")).strip()
    reason = str(arguments.get("reason", "")).strip()
    if not isinstance(extracted_fields, dict):
        extracted_fields = {}

    lines = [
        "[AUTO DISPATCH]",
        f"source_platform: {source_platform}",
    ]
    for key in sorted(extracted_fields):
        value = extracted_fields[key]
        lines.append(f"{key}: {value}")
    if screenshot_ref:
        lines.append(f"screenshot_ref: {screenshot_ref}")
    if reason:
        lines.append(f"reason: {reason}")
    return "\n".join(lines)


def resolve_dispatch_target_uid(task: TaskPayload) -> str | None:
    override = task.arguments.get("dispatch_target_uid")
    if override is not None:
        return str(override)
    if task.target is None:
        return None
    return task.target.uid


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
        target_uid = resolve_dispatch_target_uid(task)
        message = render_dispatch_message(task.arguments)
        result = self.driver.send_message(
            app="wechat",
            target_uid=target_uid,
            message=message,
        )
        return {
            **result.model_dump(mode="json", exclude_none=True),
            "platform": "wechat",
            "action": self.action_name,
            "source_platform": str(task.arguments.get("source_platform", "")),
            "dispatch_target_uid": target_uid,
            "message_template": "dispatch_v2_structured",
            "message": message,
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
