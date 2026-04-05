from __future__ import annotations

from abc import ABC, abstractmethod

from autoin.adapters.actions import ActionRegistry
from autoin.infrastructure.models import TaskPayload


class WechatActionHandler(ABC):
    """Platform action object boundary for the Windows WeChat executor."""

    action_name: str

    @abstractmethod
    def run(self, task: TaskPayload) -> dict[str, object]:
        """Run a logical action and return structured execution metadata."""


class SendDispatchMessageHandler(WechatActionHandler):
    action_name = "send_dispatch_message"

    def run(self, task: TaskPayload) -> dict[str, object]:
        return {
            "platform": "wechat",
            "action": self.action_name,
            "target_uid": task.target.uid if task.target else None,
            "source_platform": str(task.arguments.get("source_platform", "")),
            "message_template": "dispatch_v1",
        }


class SendAutoReplyHandler(WechatActionHandler):
    action_name = "send_auto_reply"

    def run(self, task: TaskPayload) -> dict[str, object]:
        return {
            "platform": "wechat",
            "action": self.action_name,
            "target_uid": task.target.uid if task.target else None,
            "message": task.arguments.get("message", "auto_reply"),
        }


def build_wechat_action_registry() -> ActionRegistry:
    registry = ActionRegistry()
    handlers: list[WechatActionHandler] = [
        SendDispatchMessageHandler(),
        SendAutoReplyHandler(),
    ]
    for handler in handlers:
        registry.register(handler.action_name, handler.run)
    return registry
