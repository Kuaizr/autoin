from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from typing import Any

from autoin.adapters.runtime import ObserverAdapter
from autoin.config import Settings, get_settings
from autoin.infrastructure import ConversationRef, Platform, RedisBroker


def emit_wechat_customer_message(
    customer_user_id: str,
    messages: list[str],
    *,
    screenshot_ref: str | None = None,
    broker: RedisBroker | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    resolved_settings = settings
    if resolved_settings is None and broker is None:
        resolved_settings = get_settings()
    selected_broker = broker or RedisBroker(resolved_settings)
    observer = ObserverAdapter("wechat.observer", Platform.WECHAT, selected_broker)
    event = observer.emit_messages(
        conversation=ConversationRef(platform=Platform.WECHAT, user_id=customer_user_id),
        messages=messages,
        screenshot_ref=screenshot_ref,
    )
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "conversation_uid": event.payload.conversation.uid,
        "message_count": len(messages),
        "messages": list(messages),
        "observed_at": datetime.now(UTC).isoformat(),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish a simulated inbound WeChat customer message into Redis.")
    parser.add_argument("--customer-user-id", required=True)
    parser.add_argument("--message", action="append", required=True, help="Repeat this flag to publish multiple inbound messages.")
    parser.add_argument("--screenshot-ref")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = emit_wechat_customer_message(
        customer_user_id=args.customer_user_id,
        messages=args.message,
        screenshot_ref=args.screenshot_ref,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
