from autoin.infrastructure.models import (
    ConversationRef,
    EventMetadata,
    EventType,
    MessagePayload,
    Platform,
    TaskKind,
    TaskPayload,
    UnifiedEvent,
)


def test_conversation_uid_is_platform_scoped() -> None:
    ref = ConversationRef(platform=Platform.DOUYIN, user_id="123")
    assert ref.uid == "douyin_123"


def test_unified_event_accepts_message_payload() -> None:
    event = UnifiedEvent(
        event_type=EventType.MESSAGE_BUFFERED,
        metadata=EventMetadata(producer="adapter.douyin-observer"),
        payload=MessagePayload(
            conversation=ConversationRef(platform=Platform.DOUYIN, user_id="u1"),
            messages=["hello"],
        ),
    )
    assert event.payload.messages == ["hello"]


def test_unified_event_accepts_task_payload() -> None:
    event = UnifiedEvent(
        event_type=EventType.TASK_CREATED,
        metadata=EventMetadata(producer="coordinator"),
        payload=TaskPayload(
            kind=TaskKind.UI_ACTION,
            sequence=1,
            dependencies=["task-0"],
            adapter="wechat.executor",
            action="send_group_message",
        ),
    )
    assert event.payload.adapter == "wechat.executor"
    assert event.payload.dependencies == ["task-0"]
