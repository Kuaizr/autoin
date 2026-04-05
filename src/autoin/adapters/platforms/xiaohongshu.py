from __future__ import annotations

from abc import ABC, abstractmethod

from autoin.adapters.actions import ActionRegistry
from autoin.infrastructure.models import TaskPayload


class XiaohongshuActionHandler(ABC):
    """Platform action object boundary for the Windows Xiaohongshu executor."""

    action_name: str

    @abstractmethod
    def run(self, task: TaskPayload) -> dict[str, object]:
        """Run a logical action and return structured execution metadata."""


class CaptureAndValidateOrderHandler(XiaohongshuActionHandler):
    action_name = "capture_and_validate_order"

    def run(self, task: TaskPayload) -> dict[str, object]:
        return {
            "platform": "xiaohongshu",
            "action": self.action_name,
            "target_uid": task.target.uid if task.target else None,
            "capture_mode": "fullscreen",
            "requires_latest_snapshot": True,
        }


class SendAutoReplyHandler(XiaohongshuActionHandler):
    action_name = "send_auto_reply"

    def run(self, task: TaskPayload) -> dict[str, object]:
        return {
            "platform": "xiaohongshu",
            "action": self.action_name,
            "target_uid": task.target.uid if task.target else None,
            "message": task.arguments.get("message", "auto_reply"),
        }


def build_xiaohongshu_action_registry() -> ActionRegistry:
    registry = ActionRegistry()
    handlers: list[XiaohongshuActionHandler] = [
        CaptureAndValidateOrderHandler(),
        SendAutoReplyHandler(),
    ]
    for handler in handlers:
        registry.register(handler.action_name, handler.run)
    return registry
