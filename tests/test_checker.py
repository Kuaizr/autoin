from autoin.cognitive import CheckerAgent
from autoin.infrastructure.models import ConversationRef, Platform, TaskKind, TaskPayload


def test_checker_agent_approves_when_required_fields_exist() -> None:
    checker = CheckerAgent()
    task = TaskPayload(
        task_id="check-1",
        kind=TaskKind.CHECK,
        adapter="xiaohongshu.executor",
        target=ConversationRef(platform=Platform.XIAOHONGSHU, user_id="u1"),
        action="capture_and_validate_order",
    )

    decision = checker.validate_dispatch_task(
        task,
        screenshot_ref="shot-1",
        extracted_fields={"address": "Shanghai", "item_code": "A123"},
    )

    assert decision.approved is True
    assert decision.reason == "checker_fields_present"


def test_checker_agent_rejects_when_required_fields_are_missing() -> None:
    checker = CheckerAgent()
    task = TaskPayload(
        task_id="check-2",
        kind=TaskKind.CHECK,
        adapter="xiaohongshu.executor",
        target=ConversationRef(platform=Platform.XIAOHONGSHU, user_id="u2"),
        action="capture_and_validate_order",
    )

    decision = checker.validate_dispatch_task(
        task,
        screenshot_ref="shot-2",
        extracted_fields={"address": "Shanghai"},
    )

    assert decision.approved is False
    assert decision.reason == "checker_missing_required_fields"


def test_checker_agent_approves_wechat_customer_id_dispatch() -> None:
    checker = CheckerAgent()
    task = TaskPayload(
        task_id="check-3",
        kind=TaskKind.CHECK,
        adapter="wechat.executor",
        target=ConversationRef(platform=Platform.WECHAT, user_id="kzr"),
        action="capture_and_validate_order",
    )

    decision = checker.validate_dispatch_task(
        task,
        screenshot_ref="shot-3",
        extracted_fields={"customer_id": "abc123"},
    )

    assert decision.approved is True
    assert decision.reason == "checker_fields_present"
