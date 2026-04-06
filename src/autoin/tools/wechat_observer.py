from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from autoin.adapters import DesktopAutomationError, ObserverAdapter, PywinautoDriver
from autoin.config import Settings, get_settings
from autoin.infrastructure import ConversationRef, Platform, RedisBroker

NOISE_TEXTS = {
    "微信",
    "Weixin",
    "聊天信息",
    "表情",
    "表情(E)",
    "更多功能",
    "更多功能(M)",
    "搜索",
    "搜索：联系人、群聊、企业",
    "输入",
}
TIMESTAMP_PATTERN = re.compile(r"^(昨天|前天|\d{1,2}:\d{2}|\d{4}/\d{1,2}/\d{1,2}.*)$")
NUMERIC_NOISE_PATTERN = re.compile(r"^\d+$")
DEFAULT_STATE_FILE = Path(".autoin") / "wechat_observer_state.json"


class WechatFerryUnavailableError(RuntimeError):
    pass


def load_wcf_client(debug: bool = False) -> Any:
    try:
        from wcferry import Wcf  # type: ignore
    except ImportError as exc:
        raise WechatFerryUnavailableError(
            "wcferry is not installed. Install it on Windows with `uv sync --extra windows`."
        ) from exc
    return Wcf(debug=debug)


class WcferryObserverClient:
    def __init__(self, client: Any | None = None, *, debug: bool = False) -> None:
        self.client = client or load_wcf_client(debug=debug)
        if not self.client.is_login():
            raise WechatFerryUnavailableError("WeChatFerry is connected but WeChat Desktop is not logged in.")
        if not self.client.is_receiving_msg():
            self.client.enable_receiving_msg()

    def receive_message(self) -> dict[str, object]:
        message = self.client.get_msg()
        if message is None:
            return {"status": "idle"}
        sender = getattr(message, "sender", None)
        roomid = getattr(message, "roomid", None)
        content = getattr(message, "content", None)
        msg_type = getattr(message, "type", None)
        is_self = bool(message.from_self()) if hasattr(message, "from_self") else False
        is_group = bool(message.from_group()) if hasattr(message, "from_group") else False
        return {
            "status": "received",
            "sender": sender,
            "roomid": roomid,
            "content": content,
            "message_type": msg_type,
            "is_self": is_self,
            "is_group": is_group,
        }


def normalize_visible_texts(texts: list[str]) -> list[str]:
    normalized: list[str] = []
    for text in texts:
        cleaned = " ".join(text.split())
        if not cleaned:
            continue
        if normalized and normalized[-1] == cleaned:
            continue
        normalized.append(cleaned)
    return normalized


def is_noise_text(text: str, customer_user_id: str) -> bool:
    return (
        text in NOISE_TEXTS
        or text == customer_user_id
        or bool(TIMESTAMP_PATTERN.match(text))
        or bool(NUMERIC_NOISE_PATTERN.match(text))
    )


def select_latest_customer_message(texts: list[str], customer_user_id: str) -> str | None:
    for text in reversed(normalize_visible_texts(texts)):
        if is_noise_text(text, customer_user_id):
            continue
        return text
    return None


def extract_ocr_lines(ocr_text: str) -> list[str]:
    return normalize_visible_texts([line for line in ocr_text.splitlines() if line.strip()])


def run_ocr_fallback_probes(
    driver: Any,
    customer_user_id: str,
    *,
    tesseract_cmd: str,
) -> tuple[str | None, list[str], list[dict[str, object]], str | None, str | None]:
    debug_probes: list[dict[str, object]] = []
    last_artifact_path: str | None = None
    for probe in driver.capture_live_wechat_ocr_probes(target_uid=customer_user_id):
        artifact_path = Path(probe["artifact_path"])
        last_artifact_path = str(artifact_path)
        try:
            ocr_text = driver.run_tesseract_ocr(artifact_path, tesseract_cmd=tesseract_cmd)
            ocr_lines = extract_ocr_lines(ocr_text)
            debug_probes.append(
                {
                    "mode": probe["mode"],
                    "artifact_path": str(artifact_path),
                    "crop_box": probe["crop_box"],
                    "ocr_lines": ocr_lines,
                }
            )
        except FileNotFoundError as exc:
            debug_probes.append(
                {
                    "mode": probe["mode"],
                    "artifact_path": str(artifact_path),
                    "crop_box": probe["crop_box"],
                    "ocr_lines": [],
                    "error": f"tesseract_not_found: {exc}",
                }
            )
            return None, [], debug_probes, last_artifact_path, f"tesseract_not_found: {exc}"
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            debug_probes.append(
                {
                    "mode": probe["mode"],
                    "artifact_path": str(artifact_path),
                    "crop_box": probe["crop_box"],
                    "ocr_lines": [],
                    "error": f"tesseract_failed: {stderr or exc}",
                }
            )
            return None, [], debug_probes, last_artifact_path, f"tesseract_failed: {stderr or exc}"
        latest_message = select_latest_customer_message(ocr_lines, customer_user_id)
        if latest_message is not None:
            return latest_message, ocr_lines, debug_probes, last_artifact_path, None
    return None, [], debug_probes, last_artifact_path, None


def load_observer_state(state_file: Path) -> dict[str, dict[str, str]]:
    if not state_file.exists():
        return {}
    return json.loads(state_file.read_text(encoding="utf-8"))


def save_observer_state(state_file: Path, state: dict[str, dict[str, str]]) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _state_key(conversation: ConversationRef, latest_message: str) -> str:
    return f"{conversation.uid}:{latest_message}"


def _build_wcferry_observation(
    *,
    customer_user_id: str,
    allow_any_sender: bool,
    wcf_client: Any | None,
) -> dict[str, Any]:
    observer = wcf_client if isinstance(wcf_client, WcferryObserverClient) else WcferryObserverClient(wcf_client)
    received = observer.receive_message()
    if received["status"] != "received":
        return {
            "conversation": ConversationRef(platform=Platform.WECHAT, user_id=customer_user_id),
            "latest_message": None,
            "debug": {"backend": "wcferry", "received": received},
        }

    sender = received.get("sender")
    content = received.get("content")
    if not isinstance(content, str) or not content.strip():
        return {
            "conversation": ConversationRef(platform=Platform.WECHAT, user_id=str(sender or customer_user_id)),
            "latest_message": None,
            "debug": {"backend": "wcferry", "received": received, "skip_reason": "empty_content"},
        }
    if received.get("is_self"):
        return {
            "conversation": ConversationRef(platform=Platform.WECHAT, user_id=str(sender or customer_user_id)),
            "latest_message": None,
            "debug": {"backend": "wcferry", "received": received, "skip_reason": "self_message"},
        }
    if not allow_any_sender and sender != customer_user_id:
        return {
            "conversation": ConversationRef(platform=Platform.WECHAT, user_id=str(sender or customer_user_id)),
            "latest_message": None,
            "debug": {"backend": "wcferry", "received": received, "skip_reason": "sender_mismatch"},
        }
    conversation_user_id = str(sender or customer_user_id)
    return {
        "conversation": ConversationRef(platform=Platform.WECHAT, user_id=conversation_user_id),
        "latest_message": content.strip(),
        "debug": {"backend": "wcferry", "received": received},
    }


def _build_pywinauto_observation(
    *,
    customer_user_id: str,
    selected_driver: Any,
    enable_ocr_fallback: bool,
    tesseract_cmd: str,
) -> dict[str, Any]:
    observation = selected_driver.observe_wechat_conversation(target_uid=customer_user_id)
    latest_message = select_latest_customer_message(observation.get("texts", []), customer_user_id)
    ocr_lines: list[str] = []
    artifact_path = None
    ocr_probe_results: list[dict[str, object]] = []
    ocr_error: str | None = None
    if latest_message is None and enable_ocr_fallback:
        try:
            latest_message, ocr_lines, ocr_probe_results, artifact_path, ocr_error = run_ocr_fallback_probes(
                selected_driver,
                customer_user_id,
                tesseract_cmd=tesseract_cmd,
            )
        except DesktopAutomationError as exc:
            ocr_lines = []
            ocr_probe_results = []
            ocr_error = f"{exc.code}: {exc}"
    return {
        "conversation": ConversationRef(platform=Platform.WECHAT, user_id=customer_user_id),
        "latest_message": latest_message,
        "debug": {
            "backend": "pywinauto",
            "window": observation.get("window"),
            "visible_texts": observation.get("texts", []),
            "ocr_lines": ocr_lines,
            "ocr_artifact_path": str(artifact_path) if artifact_path else None,
            "ocr_probe_results": ocr_probe_results,
            "ocr_error": ocr_error,
        },
    }


def observe_wechat_customer_message(
    customer_user_id: str,
    *,
    broker: RedisBroker | None = None,
    settings: Settings | None = None,
    driver: Any | None = None,
    wcf_client: Any | None = None,
    state_file: Path = DEFAULT_STATE_FILE,
    include_debug_texts: bool = False,
    enable_ocr_fallback: bool = False,
    tesseract_cmd: str = "tesseract",
    backend: str = "auto",
    allow_any_sender: bool = False,
) -> dict[str, Any]:
    resolved_settings = settings
    if resolved_settings is None and broker is None:
        resolved_settings = get_settings()
    selected_broker = broker or RedisBroker(resolved_settings)
    observer = ObserverAdapter("wechat.observer", Platform.WECHAT, selected_broker)
    selected_backend = backend
    selected_driver = driver
    observation: dict[str, Any]
    if selected_backend in {"auto", "wcferry"}:
        try:
            observation = _build_wcferry_observation(
                customer_user_id=customer_user_id,
                allow_any_sender=allow_any_sender,
                wcf_client=wcf_client,
            )
            selected_backend = "wcferry"
        except WechatFerryUnavailableError:
            if backend == "wcferry":
                raise
            selected_backend = "pywinauto"
        else:
            conversation = observation["conversation"]
            latest_message = observation["latest_message"]
            state = load_observer_state(state_file)
            previous_message = state.get(conversation.uid, {}).get("last_message")
            if latest_message is None:
                result = {
                    "status": "idle",
                    "conversation_uid": conversation.uid,
                    "observed_message": None,
                    "emitted": False,
                    "backend": selected_backend,
                }
                if include_debug_texts:
                    result.update(observation["debug"])
                return result
            if latest_message == previous_message:
                result = {
                    "status": "deduplicated",
                    "conversation_uid": conversation.uid,
                    "observed_message": latest_message,
                    "emitted": False,
                    "backend": selected_backend,
                }
                if include_debug_texts:
                    result.update(observation["debug"])
                return result
            event = observer.emit_messages(conversation=conversation, messages=[latest_message])
            state[conversation.uid] = {"last_message": latest_message}
            save_observer_state(state_file, state)
            result = {
                "status": "emitted",
                "event_id": event.event_id,
                "event_type": event.event_type,
                "conversation_uid": conversation.uid,
                "observed_message": latest_message,
                "emitted": True,
                "backend": selected_backend,
            }
            if include_debug_texts:
                result.update(observation["debug"])
            return result

    selected_driver = selected_driver or PywinautoDriver()
    observation = _build_pywinauto_observation(
        customer_user_id=customer_user_id,
        selected_driver=selected_driver,
        enable_ocr_fallback=enable_ocr_fallback,
        tesseract_cmd=tesseract_cmd,
    )
    conversation = observation["conversation"]
    latest_message = observation["latest_message"]
    state = load_observer_state(state_file)
    previous_message = state.get(conversation.uid, {}).get("last_message")

    if latest_message is None:
        result = {
            "status": "idle",
            "conversation_uid": conversation.uid,
            "observed_message": None,
            "emitted": False,
            "backend": selected_backend,
        }
        if include_debug_texts:
            result.update(observation["debug"])
        return result

    if latest_message == previous_message:
        result = {
            "status": "deduplicated",
            "conversation_uid": conversation.uid,
            "observed_message": latest_message,
            "emitted": False,
            "backend": selected_backend,
        }
        if include_debug_texts:
            result.update(observation["debug"])
        return result

    event = observer.emit_messages(conversation=conversation, messages=[latest_message])
    state[conversation.uid] = {"last_message": latest_message}
    save_observer_state(state_file, state)
    result = {
        "status": "emitted",
        "event_id": event.event_id,
        "event_type": event.event_type,
        "conversation_uid": conversation.uid,
        "observed_message": latest_message,
        "emitted": True,
        "backend": selected_backend,
    }
    if include_debug_texts:
        result.update(observation["debug"])
    return result


def run_wechat_observer_loop(
    customer_user_id: str,
    *,
    poll_interval_seconds: float = 2.0,
    max_polls: int | None = None,
    broker: RedisBroker | None = None,
    settings: Settings | None = None,
    driver: Any | None = None,
    wcf_client: Any | None = None,
    state_file: Path = DEFAULT_STATE_FILE,
    emit_logs: bool = False,
    include_debug_texts: bool = False,
    enable_ocr_fallback: bool = False,
    tesseract_cmd: str = "tesseract",
    backend: str = "auto",
    allow_any_sender: bool = False,
) -> dict[str, Any]:
    polls = 0
    snapshots: list[dict[str, Any]] = []
    while True:
        snapshot = observe_wechat_customer_message(
            customer_user_id,
            broker=broker,
            settings=settings,
            driver=driver,
            wcf_client=wcf_client,
            state_file=state_file,
            include_debug_texts=include_debug_texts,
            enable_ocr_fallback=enable_ocr_fallback,
            tesseract_cmd=tesseract_cmd,
            backend=backend,
            allow_any_sender=allow_any_sender,
        )
        snapshots.append(snapshot)
        polls += 1
        if emit_logs:
            print(
                json.dumps(
                    {"event": "observer_poll_completed", "poll": polls, **snapshot},
                    ensure_ascii=False,
                    default=str,
                ),
                flush=True,
            )
        if max_polls is not None and polls >= max_polls:
            break
        time.sleep(poll_interval_seconds)
    return {
        "customer_user_id": customer_user_id,
        "polls": polls,
        "last_result": snapshots[-1] if snapshots else None,
        "results": snapshots,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Observe the current Windows WeChat conversation and publish new inbound text.")
    parser.add_argument("--customer-user-id", required=True)
    parser.add_argument("--poll-interval-seconds", type=float, default=2.0)
    parser.add_argument("--max-polls", type=int, default=None, help="Run N polling iterations and exit. Omit for an endless loop.")
    parser.add_argument("--state-file", default=str(DEFAULT_STATE_FILE))
    parser.add_argument("--once", action="store_true", help="Observe once and exit.")
    parser.add_argument("--backend", choices=["auto", "wcferry", "pywinauto"], default="auto")
    parser.add_argument("--allow-any-sender", action="store_true", help="For WeChatFerry mode, accept inbound text from any non-self sender instead of matching --customer-user-id exactly.")
    parser.add_argument("--debug-visible-texts", action="store_true", help="Include extracted visible texts in observer output for Windows UI debugging.")
    parser.add_argument("--ocr-fallback", action="store_true", help="Fallback to Tesseract OCR on a cropped WeChat chat screenshot when UIA text extraction fails.")
    parser.add_argument("--tesseract-cmd", default="tesseract")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-poll logs and only print the final JSON summary.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    state_file = Path(args.state_file)
    if args.once:
        result = observe_wechat_customer_message(
            args.customer_user_id,
            state_file=state_file,
            include_debug_texts=args.debug_visible_texts,
            enable_ocr_fallback=args.ocr_fallback,
            tesseract_cmd=args.tesseract_cmd,
            backend=args.backend,
            allow_any_sender=args.allow_any_sender,
        )
    else:
        result = run_wechat_observer_loop(
            args.customer_user_id,
            poll_interval_seconds=args.poll_interval_seconds,
            max_polls=args.max_polls,
            state_file=state_file,
            emit_logs=not args.quiet,
            include_debug_texts=args.debug_visible_texts,
            enable_ocr_fallback=args.ocr_fallback,
            tesseract_cmd=args.tesseract_cmd,
            backend=args.backend,
            allow_any_sender=args.allow_any_sender,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
