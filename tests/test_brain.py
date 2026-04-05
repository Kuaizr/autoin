from autoin.cognitive import BrainAgent
from autoin.infrastructure.models import ConversationRef, IntakeDecisionPayload, Platform, TaskKind


def test_brain_agent_builds_reply_plan_as_single_source_task() -> None:
    brain = BrainAgent()
    decision = IntakeDecisionPayload(
        conversation=ConversationRef(platform=Platform.DOUYIN, user_id="u1"),
        intent="reply",
        reason="keyword_router_v1",
        suggested_tasks=[TaskKind.REPLY],
    )

    tasks = brain.build_tasks(decision)

    assert len(tasks) == 1
    assert tasks[0].kind == TaskKind.REPLY
    assert tasks[0].adapter == "douyin.executor"


def test_brain_agent_builds_dispatch_check_then_wechat_dispatch() -> None:
    brain = BrainAgent()
    decision = IntakeDecisionPayload(
        conversation=ConversationRef(platform=Platform.XIAOHONGSHU, user_id="u2"),
        intent="dispatch",
        reason="keyword_router_v1",
        suggested_tasks=[TaskKind.CHECK, TaskKind.UI_ACTION],
    )

    tasks = brain.build_tasks(decision)

    assert [task.kind for task in tasks] == [TaskKind.CHECK, TaskKind.UI_ACTION]
    assert tasks[0].adapter == "xiaohongshu.executor"
    assert tasks[1].adapter == "wechat.executor"
    assert tasks[1].dependencies == [tasks[0].task_id]


def test_brain_agent_carries_dispatch_target_and_customer_fields() -> None:
    brain = BrainAgent()
    decision = IntakeDecisionPayload(
        conversation=ConversationRef(platform=Platform.WECHAT, user_id="kzr"),
        intent="dispatch",
        reason="wechat_gaming_broker_v1",
        suggested_tasks=[TaskKind.CHECK, TaskKind.UI_ACTION],
        extracted_fields={"customer_id": "abc123"},
        dispatch_target_uid="文件传输助手",
    )

    tasks = brain.build_tasks(decision)

    assert tasks[1].arguments["dispatch_target_uid"] == "文件传输助手"
    assert tasks[1].arguments["extracted_fields"] == {"customer_id": "abc123"}
