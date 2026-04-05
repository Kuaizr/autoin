from autoin.adapters import build_xianyu_action_registry
from autoin.infrastructure.models import ConversationRef, Platform, TaskKind, TaskPayload


def test_xianyu_action_registry_builds_check_handler() -> None:
    registry = build_xianyu_action_registry()
    task = TaskPayload(
        kind=TaskKind.CHECK,
        adapter="xianyu.executor",
        target=ConversationRef(platform=Platform.XIANYU, user_id="u1"),
        action="capture_and_validate_order",
    )

    result = registry.dispatch(task)

    assert result["platform"] == "xianyu"
    assert result["capture_mode"] == "conversation_panel"


def test_xianyu_action_registry_builds_reply_handler() -> None:
    registry = build_xianyu_action_registry()
    task = TaskPayload(
        kind=TaskKind.REPLY,
        adapter="xianyu.executor",
        target=ConversationRef(platform=Platform.XIANYU, user_id="u2"),
        action="send_auto_reply",
        arguments={"message": "这边已收到"},
    )

    result = registry.dispatch(task)

    assert result["platform"] == "xianyu"
    assert result["message"] == "这边已收到"
