from __future__ import annotations

import argparse
import json
from typing import Any

from autoin.adapters import build_executor_adapter
from autoin.config import Settings, get_settings
from autoin.infrastructure import ConversationRef, Platform, RedisBroker, RedisLockManager, TaskKind, TaskPayload


def build_wechat_dispatch_task(
    source_platform: str,
    source_user_id: str,
    dispatch_target_uid: str,
    extracted_fields: dict[str, str],
    screenshot_ref: str | None = None,
    reason: str = "manual_smoke_test",
) -> TaskPayload:
    return TaskPayload(
        kind=TaskKind.UI_ACTION,
        adapter="wechat.executor",
        target=ConversationRef(platform=Platform(source_platform), user_id=source_user_id),
        action="send_dispatch_message",
        arguments={
            "source_platform": Platform(source_platform),
            "dispatch_target_uid": dispatch_target_uid,
            "extracted_fields": extracted_fields,
            "screenshot_ref": screenshot_ref,
            "reason": reason,
        },
    )


def run_wechat_dispatch_smoke(
    source_platform: str,
    source_user_id: str,
    dispatch_target_uid: str,
    extracted_fields: dict[str, str],
    screenshot_ref: str | None = None,
    reason: str = "manual_smoke_test",
    prefer_pywinauto: bool = True,
    *,
    broker: RedisBroker | None = None,
    lock_manager: RedisLockManager | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    task = build_wechat_dispatch_task(
        source_platform=source_platform,
        source_user_id=source_user_id,
        dispatch_target_uid=dispatch_target_uid,
        extracted_fields=extracted_fields,
        screenshot_ref=screenshot_ref,
        reason=reason,
    )
    resolved_settings = settings
    if resolved_settings is None and (broker is None or lock_manager is None):
        resolved_settings = get_settings()
    selected_broker = broker or RedisBroker(resolved_settings)
    selected_lock_manager = lock_manager or RedisLockManager(resolved_settings)
    executor = build_executor_adapter(
        adapter_name="wechat.executor",
        platform_name=Platform.WECHAT,
        broker=selected_broker,
        lock_manager=selected_lock_manager,
        prefer_pywinauto=prefer_pywinauto,
    )
    event = executor.execute_action(task)
    return {
        "event_type": event.event_type,
        "task_status": event.payload.status,
        "action_result": executor.last_action_result,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a direct WeChat dispatch smoke test.")
    parser.add_argument("--source-platform", default="xiaohongshu", choices=[item.value for item in Platform if item != Platform.SYSTEM])
    parser.add_argument("--source-user-id", required=True)
    parser.add_argument("--dispatch-target-uid", required=True, help="WeChat group or conversation label used by the executor.")
    parser.add_argument("--item-code")
    parser.add_argument("--address")
    parser.add_argument("--phone")
    parser.add_argument("--note")
    parser.add_argument("--screenshot-ref")
    parser.add_argument("--reason", default="manual_smoke_test")
    parser.add_argument("--mock-driver", action="store_true", help="Use the cross-platform mock driver instead of pywinauto.")
    return parser.parse_args(argv)


def _build_extracted_fields(args: argparse.Namespace) -> dict[str, str]:
    extracted_fields: dict[str, str] = {}
    for field_name in ("item_code", "address", "phone", "note"):
        value = getattr(args, field_name)
        if value:
            extracted_fields[field_name] = value
    return extracted_fields


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_wechat_dispatch_smoke(
        source_platform=args.source_platform,
        source_user_id=args.source_user_id,
        dispatch_target_uid=args.dispatch_target_uid,
        extracted_fields=_build_extracted_fields(args),
        screenshot_ref=args.screenshot_ref,
        reason=args.reason,
        prefer_pywinauto=not args.mock_driver,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
