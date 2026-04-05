from __future__ import annotations

from autoin.infrastructure.models import (
    BrainPlanPayload,
    IntakeDecisionPayload,
    Platform,
    TaskKind,
    TaskPayload,
    TaskPlan,
)


class BrainAgent:
    """Rule-based planning stub for reply and dispatch flows."""

    def __init__(self, source_executor_suffix: str = ".executor", dispatch_adapter: str = "wechat.executor") -> None:
        self.source_executor_suffix = source_executor_suffix
        self.dispatch_adapter = dispatch_adapter

    def build_tasks(self, decision: IntakeDecisionPayload) -> list[TaskPayload]:
        source_adapter = f"{decision.conversation.platform}{self.source_executor_suffix}"
        if decision.intent == "reply":
            return [
                TaskPayload(
                    kind=TaskKind.REPLY,
                    sequence=1,
                    adapter=source_adapter,
                    target=decision.conversation,
                    action="send_auto_reply",
                    arguments={"reason": decision.reason},
                )
            ]

        check_task = TaskPayload(
            kind=TaskKind.CHECK,
            sequence=1,
            adapter=source_adapter,
            target=decision.conversation,
            action="capture_and_validate_order",
            arguments={
                "reason": decision.reason,
                "extracted_fields": dict(decision.extracted_fields),
                "dispatch_target_uid": decision.dispatch_target_uid,
            },
        )
        dispatch_task = TaskPayload(
            kind=TaskKind.UI_ACTION,
            sequence=2,
            adapter=self.dispatch_adapter,
            target=decision.conversation,
            action="send_dispatch_message",
            dependencies=[check_task.task_id],
            arguments={
                "source_platform": decision.conversation.platform,
                "dispatch_target_uid": decision.dispatch_target_uid,
                "extracted_fields": dict(decision.extracted_fields),
                "reason": decision.reason,
            },
        )
        return [check_task, dispatch_task]

    def build_plan_payload(self, decision: IntakeDecisionPayload, plan: TaskPlan) -> BrainPlanPayload:
        return BrainPlanPayload(
            conversation=decision.conversation,
            intent=decision.intent,
            plan_id=plan.plan_id,
            task_ids=[task.task_id for task in plan.tasks],
            rationale=decision.reason,
        )
