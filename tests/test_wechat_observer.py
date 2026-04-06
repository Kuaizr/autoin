import json
from pathlib import Path

from autoin.adapters.drivers import WindowReference
from autoin.infrastructure.models import EventType
from autoin.tools.wechat_observer import (
    WechatFerryUnavailableError,
    WcferryObserverClient,
    extract_ocr_lines,
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

    def capture_live_wechat_chat_region(self, target_uid: str | None = None) -> dict[str, object]:
        return {
            "artifact_path": Path("artifacts") / "windows" / "wechat" / "chat_region" / "probe.png",
            "window": WindowReference(
                app="wechat",
                target_uid=target_uid,
                backend="uia",
                locator="微信",
                locator_status="resolved",
            ),
        }

    def capture_live_wechat_ocr_probes(self, target_uid: str | None = None) -> list[dict[str, object]]:
        return [
            {
                "mode": "full_window",
                "artifact_path": Path("artifacts") / "windows" / "wechat" / "full_window" / "probe.png",
                "crop_box": (0, 0, 100, 100),
                "window": WindowReference(
                    app="wechat",
                    target_uid=target_uid,
                    backend="uia",
                    locator="微信",
                    locator_status="resolved",
                ),
            },
            {
                "mode": "chat_region",
                "artifact_path": Path("artifacts") / "windows" / "wechat" / "chat_region" / "probe.png",
                "crop_box": (10, 10, 90, 90),
                "window": WindowReference(
                    app="wechat",
                    target_uid=target_uid,
                    backend="uia",
                    locator="微信",
                    locator_status="resolved",
                ),
            },
        ]

    def run_tesseract_ocr(self, image_path: Path, *, tesseract_cmd: str = "tesseract", languages: str = "chi_sim+eng", psm: int = 6) -> str:
        del image_path, tesseract_cmd, languages, psm
        return ""


class StubWcfMessage:
    def __init__(
        self,
        *,
        sender: str = "wxid_kzr",
        content: str = "我要下单这个产品，我的客户id是 abc123",
        roomid: str = "",
        msg_type: int = 1,
        is_self: bool = False,
        is_group: bool = False,
    ) -> None:
        self.sender = sender
        self.content = content
        self.roomid = roomid
        self.type = msg_type
        self._is_self = is_self
        self._is_group = is_group

    def from_self(self) -> bool:
        return self._is_self

    def from_group(self) -> bool:
        return self._is_group


class StubWcfClient:
    def __init__(self, message: StubWcfMessage | None = None, *, receiving: bool = False, logged_in: bool = True) -> None:
        self.message = message
        self.receiving = receiving
        self.logged_in = logged_in
        self.enable_calls = 0

    def is_login(self) -> bool:
        return self.logged_in

    def is_receiving_msg(self) -> bool:
        return self.receiving

    def enable_receiving_msg(self) -> None:
        self.enable_calls += 1
        self.receiving = True

    def get_msg(self):  # noqa: ANN202
        return self.message


def test_normalize_visible_texts_compacts_blanks_and_repeats() -> None:
    assert normalize_visible_texts(["", "  hello  ", "hello", "foo\nbar"]) == ["hello", "foo bar"]


def test_select_latest_customer_message_skips_noise() -> None:
    selected = select_latest_customer_message(
        ["微信", "kzr", "12:34", "我要下单这个产品，我的客户id是 abc123"],
        "kzr",
    )

    assert selected == "我要下单这个产品，我的客户id是 abc123"


def test_extract_ocr_lines_splits_non_empty_lines() -> None:
    assert extract_ocr_lines("abc123\n\n文件传输助手\n") == ["abc123", "文件传输助手"]


def test_wcferry_observer_client_enables_receiving_mode() -> None:
    client = StubWcfClient(receiving=False)

    observer = WcferryObserverClient(client)

    assert observer.client is client
    assert client.enable_calls == 1


def test_wcferry_observer_client_requires_logged_in_wechat() -> None:
    try:
        WcferryObserverClient(StubWcfClient(logged_in=False))
    except WechatFerryUnavailableError as exc:
        assert "not logged in" in str(exc)
    else:
        raise AssertionError("Expected WcferryObserverClient to reject logged-out clients.")


def test_observe_wechat_customer_message_emits_once_per_new_message(tmp_path: Path) -> None:
    broker = StubBroker()
    state_file = tmp_path / "observer-state.json"

    first = observe_wechat_customer_message(
        "kzr",
        broker=broker,
        driver=StubDriver(["微信", "kzr", "我要下单这个产品，我的客户id是 abc123"]),
        state_file=state_file,
        backend="pywinauto",
    )
    second = observe_wechat_customer_message(
        "kzr",
        broker=broker,
        driver=StubDriver(["微信", "kzr", "我要下单这个产品，我的客户id是 abc123"]),
        state_file=state_file,
        backend="pywinauto",
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
        backend="pywinauto",
    )

    assert result["status"] == "idle"
    assert broker.events == []


def test_observe_wechat_customer_message_can_include_debug_texts(tmp_path: Path) -> None:
    broker = StubBroker()

    result = observe_wechat_customer_message(
        "kzr",
        broker=broker,
        driver=StubDriver(["微信", "kzr", "我要下单这个产品，我的客户id是 abc123"]),
        state_file=tmp_path / "observer-state.json",
        include_debug_texts=True,
        backend="pywinauto",
    )

    assert result["status"] == "emitted"
    assert result["visible_texts"] == ["微信", "kzr", "我要下单这个产品，我的客户id是 abc123"]
    assert result["backend"] == "pywinauto"


def test_observe_wechat_customer_message_can_fallback_to_ocr(tmp_path: Path) -> None:
    broker = StubBroker()
    driver = StubDriver(["Weixin", "0", "1048576"])
    driver.run_tesseract_ocr = lambda image_path, **kwargs: (
        ""
        if "full_window" in str(image_path)
        else "我要下单这个产品，我的客户id是 abc123"
    )

    result = observe_wechat_customer_message(
        "kzr",
        broker=broker,
        driver=driver,
        state_file=tmp_path / "observer-state.json",
        enable_ocr_fallback=True,
        include_debug_texts=True,
        backend="pywinauto",
    )

    assert result["status"] == "emitted"
    assert result["observed_message"] == "我要下单这个产品，我的客户id是 abc123"
    assert result["ocr_lines"] == ["我要下单这个产品，我的客户id是 abc123"]
    assert result["ocr_probe_results"][0]["mode"] == "full_window"
    assert result["ocr_probe_results"][1]["mode"] == "chat_region"
    assert result["ocr_error"] is None


def test_observe_wechat_customer_message_reports_missing_tesseract(tmp_path: Path) -> None:
    broker = StubBroker()
    driver = StubDriver(["Weixin", "0", "1048576"])

    def raise_missing(*args, **kwargs):  # noqa: ANN001
        raise FileNotFoundError("tesseract")

    driver.run_tesseract_ocr = raise_missing

    result = observe_wechat_customer_message(
        "kzr",
        broker=broker,
        driver=driver,
        state_file=tmp_path / "observer-state.json",
        enable_ocr_fallback=True,
        include_debug_texts=True,
        backend="pywinauto",
    )

    assert result["status"] == "idle"
    assert result["ocr_error"] is not None
    assert "tesseract_not_found" in result["ocr_error"]
    assert result["ocr_probe_results"][0]["error"].startswith("tesseract_not_found")


def test_run_wechat_observer_loop_returns_poll_summary(tmp_path: Path) -> None:
    broker = StubBroker()

    result = run_wechat_observer_loop(
        "kzr",
        max_polls=1,
        broker=broker,
        driver=StubDriver(["微信", "kzr", "我要下单这个产品，我的客户id是 abc123"]),
        state_file=tmp_path / "observer-state.json",
        backend="pywinauto",
    )

    assert result["polls"] == 1
    assert result["last_result"]["status"] == "emitted"


def test_run_wechat_observer_loop_emits_json_safe_logs(tmp_path: Path, capsys) -> None:
    broker = StubBroker()

    result = run_wechat_observer_loop(
        "kzr",
        max_polls=1,
        broker=broker,
        driver=StubDriver(["微信", "kzr", "我要下单这个产品，我的客户id是 abc123"]),
        state_file=tmp_path / "observer-state.json",
        emit_logs=True,
        include_debug_texts=True,
        backend="pywinauto",
    )
    captured = capsys.readouterr()

    assert result["polls"] == 1
    assert '"event": "observer_poll_completed"' in captured.out
    assert '"window":' in captured.out
    assert "locator='微信'" in captured.out


def test_observe_wechat_customer_message_prefers_wcferry_auto_backend(tmp_path: Path) -> None:
    broker = StubBroker()
    client = StubWcfClient(message=StubWcfMessage(sender="wxid_kzr"))

    result = observe_wechat_customer_message(
        "wxid_kzr",
        broker=broker,
        wcf_client=client,
        state_file=tmp_path / "observer-state.json",
        include_debug_texts=True,
        backend="auto",
    )

    assert result["status"] == "emitted"
    assert result["backend"] == "wcferry"
    assert result["observed_message"] == "我要下单这个产品，我的客户id是 abc123"
    assert result["received"]["sender"] == "wxid_kzr"


def test_observe_wechat_customer_message_wcferry_can_accept_any_sender(tmp_path: Path) -> None:
    broker = StubBroker()
    client = StubWcfClient(message=StubWcfMessage(sender="wxid_unknown"))

    result = observe_wechat_customer_message(
        "kzr",
        broker=broker,
        wcf_client=client,
        state_file=tmp_path / "observer-state.json",
        include_debug_texts=True,
        backend="wcferry",
        allow_any_sender=True,
    )

    assert result["status"] == "emitted"
    assert result["conversation_uid"] == "wechat_wxid_unknown"


def test_observe_wechat_customer_message_wcferry_skips_sender_mismatch(tmp_path: Path) -> None:
    broker = StubBroker()
    client = StubWcfClient(message=StubWcfMessage(sender="wxid_unknown"))

    result = observe_wechat_customer_message(
        "kzr",
        broker=broker,
        wcf_client=client,
        state_file=tmp_path / "observer-state.json",
        include_debug_texts=True,
        backend="wcferry",
    )

    assert result["status"] == "idle"
    assert result["skip_reason"] == "sender_mismatch"


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
