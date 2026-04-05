from autoin.adapters import build_wechat_action_registry
from autoin.adapters.platforms.wechat import render_dispatch_message
from autoin.infrastructure.models import ConversationRef, Platform, TaskKind, TaskPayload


def test_wechat_action_registry_builds_platform_handlers() -> None:
    registry = build_wechat_action_registry()
    task = TaskPayload(
        kind=TaskKind.UI_ACTION,
        adapter="wechat.executor",
        target=ConversationRef(platform=Platform.XIAOHONGSHU, user_id="u1"),
        action="send_dispatch_message",
        arguments={
            "source_platform": Platform.XIAOHONGSHU,
            "extracted_fields": {"item_code": "A123", "address": "Shanghai"},
            "screenshot_ref": "shot-1",
        },
    )

    result = registry.dispatch(task)

    assert result["platform"] == "wechat"
    assert result["action"] == "send_dispatch_message"
    assert result["message_template"] == "dispatch_v2_structured"
    assert result["dispatch_target_uid"] == "xiaohongshu_u1"
    assert "item_code: A123" in result["message"]
    assert "address: Shanghai" in result["message"]


def test_render_dispatch_message_keeps_stable_field_order() -> None:
    message = render_dispatch_message(
        {
            "source_platform": Platform.DOUYIN,
            "extracted_fields": {"phone": "13800138000", "address": "Shanghai", "item_code": "A123"},
            "reason": "checker_fields_present",
        }
    )

    assert message.splitlines() == [
        "[AUTO DISPATCH]",
        "source_platform: douyin",
        "address: Shanghai",
        "item_code: A123",
        "phone: 13800138000",
        "reason: checker_fields_present",
    ]


def test_render_dispatch_message_appends_gaming_broker_instruction() -> None:
    message = render_dispatch_message(
        {
            "source_platform": Platform.WECHAT,
            "extracted_fields": {"customer_id": "abc123"},
            "dispatch_target_uid": "文件传输助手",
            "reason": "wechat_gaming_broker_v1",
        }
    )

    assert "customer_id: abc123" in message
    assert "instruction: 请联系客户并处理代打订单" in message


def test_wechat_dispatch_handler_prefers_explicit_group_target() -> None:
    registry = build_wechat_action_registry()
    task = TaskPayload(
        kind=TaskKind.UI_ACTION,
        adapter="wechat.executor",
        target=ConversationRef(platform=Platform.XIAOHONGSHU, user_id="u1"),
        action="send_dispatch_message",
        arguments={
            "source_platform": Platform.XIAOHONGSHU,
            "dispatch_target_uid": "wechat_dispatch_group",
        },
    )

    result = registry.dispatch(task)

    assert result["dispatch_target_uid"] == "wechat_dispatch_group"


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
