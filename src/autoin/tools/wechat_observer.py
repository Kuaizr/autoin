from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

from autoin.adapters import ObserverAdapter, PywinautoDriver
from autoin.config import Settings, get_settings
from autoin.infrastructure import ConversationRef, Platform, RedisBroker

NOISE_TEXTS = {
    "微信",
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
DEFAULT_STATE_FILE = Path(".autoin") / "wechat_observer_state.json"


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
    return text in NOISE_TEXTS or text == customer_user_id or bool(TIMESTAMP_PATTERN.match(text))


def select_latest_customer_message(texts: list[str], customer_user_id: str) -> str | None:
    for text in reversed(normalize_visible_texts(texts)):
        if is_noise_text(text, customer_user_id):
            continue
        return text
    return None


def load_observer_state(state_file: Path) -> dict[str, dict[str, str]]:
    if not state_file.exists():
        return {}
    return json.loads(state_file.read_text(encoding="utf-8"))


def save_observer_state(state_file: Path, state: dict[str, dict[str, str]]) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def observe_wechat_customer_message(
    customer_user_id: str,
    *,
    broker: RedisBroker | None = None,
    settings: Settings | None = None,
    driver: Any | None = None,
    state_file: Path = DEFAULT_STATE_FILE,
) -> dict[str, Any]:
    resolved_settings = settings
    if resolved_settings is None and broker is None:
        resolved_settings = get_settings()
    selected_broker = broker or RedisBroker(resolved_settings)
    selected_driver = driver or PywinautoDriver()
    observer = ObserverAdapter("wechat.observer", Platform.WECHAT, selected_broker)
    observation = selected_driver.observe_wechat_conversation(target_uid=customer_user_id)
    latest_message = select_latest_customer_message(observation.get("texts", []), customer_user_id)
    conversation = ConversationRef(platform=Platform.WECHAT, user_id=customer_user_id)
    state = load_observer_state(state_file)
    previous_message = state.get(conversation.uid, {}).get("last_message")

    if latest_message is None:
        return {
            "status": "idle",
            "conversation_uid": conversation.uid,
            "observed_message": None,
            "emitted": False,
            "window": observation.get("window"),
        }

    if latest_message == previous_message:
        return {
            "status": "deduplicated",
            "conversation_uid": conversation.uid,
            "observed_message": latest_message,
            "emitted": False,
            "window": observation.get("window"),
        }

    event = observer.emit_messages(conversation=conversation, messages=[latest_message])
    state[conversation.uid] = {"last_message": latest_message}
    save_observer_state(state_file, state)
    return {
        "status": "emitted",
        "event_id": event.event_id,
        "event_type": event.event_type,
        "conversation_uid": conversation.uid,
        "observed_message": latest_message,
        "emitted": True,
        "window": observation.get("window"),
    }


def run_wechat_observer_loop(
    customer_user_id: str,
    *,
    poll_interval_seconds: float = 2.0,
    max_polls: int | None = None,
    broker: RedisBroker | None = None,
    settings: Settings | None = None,
    driver: Any | None = None,
    state_file: Path = DEFAULT_STATE_FILE,
    emit_logs: bool = False,
) -> dict[str, Any]:
    polls = 0
    snapshots: list[dict[str, Any]] = []
    while True:
        snapshot = observe_wechat_customer_message(
            customer_user_id,
            broker=broker,
            settings=settings,
            driver=driver,
            state_file=state_file,
        )
        snapshots.append(snapshot)
        polls += 1
        if emit_logs:
            print(json.dumps({"event": "observer_poll_completed", "poll": polls, **snapshot}, ensure_ascii=False), flush=True)
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
    parser.add_argument("--quiet", action="store_true", help="Suppress per-poll logs and only print the final JSON summary.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    state_file = Path(args.state_file)
    if args.once:
        result = observe_wechat_customer_message(
            args.customer_user_id,
            state_file=state_file,
        )
    else:
        result = run_wechat_observer_loop(
            args.customer_user_id,
            poll_interval_seconds=args.poll_interval_seconds,
            max_polls=args.max_polls,
            state_file=state_file,
            emit_logs=not args.quiet,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
