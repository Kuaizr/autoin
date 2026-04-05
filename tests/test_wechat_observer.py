import json
from pathlib import Path

from autoin.adapters.drivers import WindowReference
from autoin.infrastructure.models import EventType
from autoin.tools.wechat_observer import (
    load_observer_state,
    main,
    normalize_visible_texts,
    observe_wechat_customer_message,
    run_wechat_observer_loop,
    select_latest_customer_message,
)


class StubBroker:
    def __init__(self) -> None:
        self.events = []

    def publish(self, event):  # noqa: ANN001
        self.events.append(event)
        return "1-0"


class StubDriver:
    def __init__(self, texts: list[str]) -> None:
        self.texts = texts

    def observe_wechat_conversation(self, target_uid: str | None = None) -> dict[str, object]:
        return {
            "window": WindowReference(
                app="wechat",
                target_uid=target_uid,
                backend="uia",
                locator="微信",
                locator_status="resolved",
            ),
            "texts": list(self.texts),
        }


def test_normalize_visible_texts_compacts_blanks_and_repeats() -> None:
    assert normalize_visible_texts(["", "  hello  ", "hello", "foo\nbar"]) == ["hello", "foo bar"]


def test_select_latest_customer_message_skips_noise() -> None:
    selected = select_latest_customer_message(
        ["微信", "kzr", "12:34", "我要下单这个产品，我的客户id是 abc123"],
        "kzr",
    )

    assert selected == "我要下单这个产品，我的客户id是 abc123"


def test_observe_wechat_customer_message_emits_once_per_new_message(tmp_path: Path) -> None:
    broker = StubBroker()
    state_file = tmp_path / "observer-state.json"

    first = observe_wechat_customer_message(
        "kzr",
        broker=broker,
        driver=StubDriver(["微信", "kzr", "我要下单这个产品，我的客户id是 abc123"]),
        state_file=state_file,
    )
    second = observe_wechat_customer_message(
        "kzr",
        broker=broker,
        driver=StubDriver(["微信", "kzr", "我要下单这个产品，我的客户id是 abc123"]),
        state_file=state_file,
    )

    assert first["status"] == "emitted"
    assert first["event_type"] == EventType.MESSAGE_BUFFERED
    assert second["status"] == "deduplicated"
    assert len(broker.events) == 1
    assert broker.events[0].payload.messages == ["我要下单这个产品，我的客户id是 abc123"]


def test_observe_wechat_customer_message_returns_idle_without_visible_message(tmp_path: Path) -> None:
    broker = StubBroker()

    result = observe_wechat_customer_message(
        "kzr",
        broker=broker,
        driver=StubDriver(["微信", "kzr", "12:34"]),
        state_file=tmp_path / "observer-state.json",
    )

    assert result["status"] == "idle"
    assert broker.events == []


def test_run_wechat_observer_loop_returns_poll_summary(tmp_path: Path) -> None:
    broker = StubBroker()

    result = run_wechat_observer_loop(
        "kzr",
        max_polls=1,
        broker=broker,
        driver=StubDriver(["微信", "kzr", "我要下单这个产品，我的客户id是 abc123"]),
        state_file=tmp_path / "observer-state.json",
    )

    assert result["polls"] == 1
    assert result["last_result"]["status"] == "emitted"


def test_load_observer_state_returns_empty_for_missing_file(tmp_path: Path) -> None:
    assert load_observer_state(tmp_path / "missing.json") == {}


def test_wechat_observer_main_prints_json(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        "autoin.tools.wechat_observer.observe_wechat_customer_message",
        lambda *args, **kwargs: {
            "status": "emitted",
            "event_id": "event-1",
            "event_type": "message_buffered",
            "conversation_uid": "wechat_kzr",
            "observed_message": "abc123",
            "emitted": True,
        },
    )

    exit_code = main(["--customer-user-id", "kzr", "--once", "--state-file", str(tmp_path / "observer-state.json")])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["conversation_uid"] == "wechat_kzr"
    assert payload["status"] == "emitted"
