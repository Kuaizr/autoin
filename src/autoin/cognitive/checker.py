from __future__ import annotations

from autoin.infrastructure.models import CheckerDecisionPayload, SnapshotCapturedPayload, TaskPayload


class CheckerAgent:
    """Rule-based checker stub for screenshot/order validation."""

    def validate_dispatch_task(
        self,
        task: TaskPayload,
        screenshot_ref: str | None = None,
        extracted_fields: dict[str, str] | None = None,
    ) -> CheckerDecisionPayload:
        fields = extracted_fields or {}
        required = ("address", "item_code")
        approved = task.kind.name == "CHECK" and all(fields.get(key) for key in required)
        reason = "checker_fields_present" if approved else "checker_missing_required_fields"
        if task.target is None:
            raise ValueError("Checker validation requires a task target conversation.")
        return CheckerDecisionPayload(
            conversation=task.target,
            check_task_id=task.task_id,
            approved=approved,
            reason=reason,
            screenshot_ref=screenshot_ref,
            extracted_fields=fields,
        )

    def validate_snapshot_capture(
        self,
        task: TaskPayload,
        capture: SnapshotCapturedPayload,
    ) -> CheckerDecisionPayload:
        return self.validate_dispatch_task(
            task=task,
            screenshot_ref=capture.screenshot_ref,
            extracted_fields=capture.extracted_fields,
        )
