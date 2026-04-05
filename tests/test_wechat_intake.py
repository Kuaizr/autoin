from autoin.infrastructure.models import EventType
from autoin.tools.wechat_intake import emit_wechat_customer_message, main


class StubBroker:
    def __init__(self) -> None:
        self.events = []

    def publish(self, event):  # noqa: ANN001
        self.events.append(event)
        return "1-0"


def test_emit_wechat_customer_message_publishes_buffered_event() -> None:
    broker = StubBroker()

    result = emit_wechat_customer_message(
        customer_user_id="kzr",
        messages=["我要下单这个产品，我的客户id是 abc123"],
        broker=broker,
    )

    assert result["event_type"] == EventType.MESSAGE_BUFFERED
    assert result["conversation_uid"] == "wechat_kzr"
    assert broker.events[-1].payload.messages == ["我要下单这个产品，我的客户id是 abc123"]


def test_wechat_intake_main_prints_json(capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        "autoin.tools.wechat_intake.emit_wechat_customer_message",
        lambda **kwargs: {
            "event_id": "event-1",
            "event_type": "message_buffered",
            "conversation_uid": "wechat_kzr",
            "message_count": 1,
            "messages": kwargs["messages"],
            "observed_at": "2026-01-01T00:00:00+00:00",
        },
    )

    exit_code = main(["--customer-user-id", "kzr", "--message", "我要下单这个产品，我的客户id是 abc123"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"conversation_uid": "wechat_kzr"' in captured.out
    assert '"message_count": 1' in captured.out
