from autoin.adapters import ActionRegistry, UnknownActionError, build_default_action_registry
from autoin.infrastructure.models import ConversationRef, Platform, TaskKind, TaskPayload


def test_default_action_registry_handles_known_actions() -> None:
    registry = build_default_action_registry()
    task = TaskPayload(
        kind=TaskKind.REPLY,
        adapter="douyin.executor",
        target=ConversationRef(platform=Platform.DOUYIN, user_id="u1"),
        action="send_auto_reply",
        arguments={"message": "hello"},
    )

    result = registry.dispatch(task)

    assert result["action"] == "send_auto_reply"
    assert result["target_uid"] == "douyin_u1"
    assert result["message"] == "hello"


def test_action_registry_raises_for_unknown_actions() -> None:
    registry = ActionRegistry()
    task = TaskPayload(
        kind=TaskKind.UI_ACTION,
        adapter="wechat.executor",
        action="missing_action",
    )

    try:
        registry.dispatch(task)
    except UnknownActionError:
        pass
    else:
        raise AssertionError("Expected dispatch to fail for unregistered actions.")
