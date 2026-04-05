from __future__ import annotations

from collections.abc import Callable

from autoin.infrastructure.models import TaskPayload

ActionHandler = Callable[[TaskPayload], dict[str, object]]


class UnknownActionError(KeyError):
    pass


class ActionRegistry:
    """Maps logical task.action values to executor callables."""

    def __init__(self) -> None:
        self._handlers: dict[str, ActionHandler] = {}

    def register(self, action_name: str, handler: ActionHandler) -> None:
        self._handlers[action_name] = handler

    def dispatch(self, task: TaskPayload) -> dict[str, object]:
        try:
            handler = self._handlers[task.action]
        except KeyError as exc:
            raise UnknownActionError(f"Unknown action: {task.action}") from exc
        return handler(task)

    def has_action(self, action_name: str) -> bool:
        return action_name in self._handlers

    def list_actions(self) -> list[str]:
        return sorted(self._handlers)


def build_default_action_registry() -> ActionRegistry:
    registry = ActionRegistry()

    registry.register(
        "send_auto_reply",
        lambda task: {
            "action": task.action,
            "target_uid": task.target.uid if task.target else None,
            "message": task.arguments.get("message", "auto_reply"),
        },
    )
    registry.register(
        "capture_and_validate_order",
        lambda task: {
            "action": task.action,
            "target_uid": task.target.uid if task.target else None,
            "requires_screenshot": True,
        },
    )
    registry.register(
        "check",
        lambda task: {
            "action": task.action,
            "target_uid": task.target.uid if task.target else None,
            "requires_screenshot": True,
        },
    )
    registry.register(
        "send_dispatch_message",
        lambda task: {
            "action": task.action,
            "target_uid": task.target.uid if task.target else None,
            "source_platform": str(task.arguments.get("source_platform", "")),
        },
    )
    return registry
