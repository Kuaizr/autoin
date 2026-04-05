from autoin.adapters import build_wechat_action_registry
from autoin.infrastructure.models import ConversationRef, Platform, TaskKind, TaskPayload


def test_wechat_action_registry_builds_platform_handlers() -> None:
    registry = build_wechat_action_registry()
    task = TaskPayload(
        kind=TaskKind.UI_ACTION,
        adapter="wechat.executor",
        target=ConversationRef(platform=Platform.XIAOHONGSHU, user_id="u1"),
        action="send_dispatch_message",
        arguments={"source_platform": Platform.XIAOHONGSHU},
    )

    result = registry.dispatch(task)

    assert result["platform"] == "wechat"
    assert result["action"] == "send_dispatch_message"
    assert result["message_template"] == "dispatch_v1"


def test_wechat_action_registry_supports_auto_reply_handler() -> None:
    registry = build_wechat_action_registry()
    task = TaskPayload(
        kind=TaskKind.REPLY,
        adapter="wechat.executor",
        target=ConversationRef(platform=Platform.DOUYIN, user_id="u2"),
        action="send_auto_reply",
        arguments={"message": "收到，稍后处理"},
    )

    result = registry.dispatch(task)

    assert result["platform"] == "wechat"
    assert result["message"] == "收到，稍后处理"
