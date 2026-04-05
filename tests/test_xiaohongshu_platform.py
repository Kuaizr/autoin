from autoin.adapters import build_xiaohongshu_action_registry
from autoin.infrastructure.models import ConversationRef, Platform, TaskKind, TaskPayload


def test_xiaohongshu_action_registry_builds_check_handler() -> None:
    registry = build_xiaohongshu_action_registry()
    task = TaskPayload(
        kind=TaskKind.CHECK,
        adapter="xiaohongshu.executor",
        target=ConversationRef(platform=Platform.XIAOHONGSHU, user_id="u1"),
        action="capture_and_validate_order",
    )

    result = registry.dispatch(task)

    assert result["platform"] == "xiaohongshu"
    assert result["action"] == "capture_and_validate_order"
    assert result["requires_latest_snapshot"] is True


def test_xiaohongshu_action_registry_builds_reply_handler() -> None:
    registry = build_xiaohongshu_action_registry()
    task = TaskPayload(
        kind=TaskKind.REPLY,
        adapter="xiaohongshu.executor",
        target=ConversationRef(platform=Platform.XIAOHONGSHU, user_id="u2"),
        action="send_auto_reply",
        arguments={"message": "你好，已收到"},
    )

    result = registry.dispatch(task)

    assert result["platform"] == "xiaohongshu"
    assert result["message"] == "你好，已收到"
