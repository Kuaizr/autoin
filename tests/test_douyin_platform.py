from autoin.adapters import build_douyin_action_registry
from autoin.infrastructure.models import ConversationRef, Platform, TaskKind, TaskPayload


def test_douyin_action_registry_builds_check_handler() -> None:
    registry = build_douyin_action_registry()
    task = TaskPayload(
        kind=TaskKind.CHECK,
        adapter="douyin.executor",
        target=ConversationRef(platform=Platform.DOUYIN, user_id="u1"),
        action="capture_and_validate_order",
    )

    result = registry.dispatch(task)

    assert result["platform"] == "douyin"
    assert result["capture_mode"] == "focused_window"


def test_douyin_action_registry_builds_reply_handler() -> None:
    registry = build_douyin_action_registry()
    task = TaskPayload(
        kind=TaskKind.REPLY,
        adapter="douyin.executor",
        target=ConversationRef(platform=Platform.DOUYIN, user_id="u2"),
        action="send_auto_reply",
        arguments={"message": "已收到"},
    )

    result = registry.dispatch(task)

    assert result["platform"] == "douyin"
    assert result["message"] == "已收到"
