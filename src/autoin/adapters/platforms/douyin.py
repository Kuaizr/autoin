from __future__ import annotations

from abc import ABC, abstractmethod

from autoin.adapters.actions import ActionRegistry
from autoin.infrastructure.models import TaskPayload


class DouyinActionHandler(ABC):
    """Platform action object boundary for the Windows Douyin executor."""

    action_name: str

    @abstractmethod
    def run(self, task: TaskPayload) -> dict[str, object]:
        """Run a logical action and return structured execution metadata."""


class CaptureAndValidateOrderHandler(DouyinActionHandler):
    action_name = "capture_and_validate_order"

    def run(self, task: TaskPayload) -> dict[str, object]:
        return {
            "platform": "douyin",
            "action": self.action_name,
            "target_uid": task.target.uid if task.target else None,
            "capture_mode": "focused_window",
            "requires_latest_snapshot": True,
        }


class SendAutoReplyHandler(DouyinActionHandler):
    action_name = "send_auto_reply"

    def run(self, task: TaskPayload) -> dict[str, object]:
        return {
            "platform": "douyin",
            "action": self.action_name,
            "target_uid": task.target.uid if task.target else None,
            "message": task.arguments.get("message", "auto_reply"),
        }


def build_douyin_action_registry() -> ActionRegistry:
    registry = ActionRegistry()
    handlers: list[DouyinActionHandler] = [
        CaptureAndValidateOrderHandler(),
        SendAutoReplyHandler(),
    ]
    for handler in handlers:
        registry.register(handler.action_name, handler.run)
    return registry
