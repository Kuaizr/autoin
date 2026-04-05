from __future__ import annotations

from autoin.infrastructure.models import TaskPayload


class CheckerAgent:
    """Placeholder checker contract for screenshot/order validation."""

    def validate_dispatch_task(self, task: TaskPayload) -> bool:
        return task.kind.name in {"CHECK", "UI_ACTION"}
