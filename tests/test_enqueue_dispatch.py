from autoin.tools.enqueue_dispatch import enqueue_wechat_dispatch_task, main


class StubBroker:
    def __init__(self) -> None:
        self.tasks = []

    def enqueue_task(self, task):  # noqa: ANN001
        self.tasks.append(task)
        return "1-0"


def test_enqueue_wechat_dispatch_task_returns_stream_and_task_payload() -> None:
    broker = StubBroker()

    result = enqueue_wechat_dispatch_task(
        source_platform="xiaohongshu",
        source_user_id="u1",
        dispatch_target_uid="文件传输助手",
        extracted_fields={"item_code": "A123", "address": "Shanghai"},
        reason="manual_enqueue_dispatch",
        broker=broker,
    )

    assert result["stream_id"] == "1-0"
    assert result["adapter"] == "wechat.executor"
    assert result["dispatch_target_uid"] == "文件传输助手"
    assert result["task"]["arguments"]["extracted_fields"] == {"item_code": "A123", "address": "Shanghai"}
    assert broker.tasks[0].action == "send_dispatch_message"


def test_enqueue_dispatch_main_prints_json(capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        "autoin.tools.enqueue_dispatch.enqueue_wechat_dispatch_task",
        lambda **kwargs: {
            "stream_id": "1-0",
            "task_id": "task-1",
            "adapter": "wechat.executor",
            "dispatch_target_uid": kwargs["dispatch_target_uid"],
            "task": {"arguments": {"item_code": "A123"}},
        },
    )

    exit_code = main(
        [
            "--source-user-id",
            "u1",
            "--dispatch-target-uid",
            "文件传输助手",
            "--item-code",
            "A123",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"stream_id": "1-0"' in captured.out
    assert '"dispatch_target_uid": "文件传输助手"' in captured.out
