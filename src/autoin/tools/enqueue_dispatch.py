from __future__ import annotations

import argparse
import json
from typing import Any

from autoin.config import Settings, get_settings
from autoin.infrastructure import RedisBroker
from autoin.tools.wechat_smoke import build_wechat_dispatch_task


def enqueue_wechat_dispatch_task(
    source_platform: str,
    source_user_id: str,
    dispatch_target_uid: str,
    extracted_fields: dict[str, str],
    screenshot_ref: str | None = None,
    reason: str = "manual_enqueue_dispatch",
    *,
    broker: RedisBroker | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    resolved_settings = settings
    if resolved_settings is None and broker is None:
        resolved_settings = get_settings()
    selected_broker = broker or RedisBroker(resolved_settings)
    task = build_wechat_dispatch_task(
        source_platform=source_platform,
        source_user_id=source_user_id,
        dispatch_target_uid=dispatch_target_uid,
        extracted_fields=extracted_fields,
        screenshot_ref=screenshot_ref,
        reason=reason,
    )
    stream_id = selected_broker.enqueue_task(task)
    return {
        "stream_id": stream_id,
        "task_id": task.task_id,
        "adapter": task.adapter,
        "dispatch_target_uid": dispatch_target_uid,
        "task": task.model_dump(mode="json", exclude_none=True),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enqueue a WeChat dispatch task into Redis.")
    parser.add_argument("--source-platform", default="xiaohongshu", choices=["xiaohongshu", "xianyu", "douyin", "wechat"])
    parser.add_argument("--source-user-id", required=True)
    parser.add_argument("--dispatch-target-uid", required=True)
    parser.add_argument("--item-code")
    parser.add_argument("--address")
    parser.add_argument("--phone")
    parser.add_argument("--note")
    parser.add_argument("--screenshot-ref")
    parser.add_argument("--reason", default="manual_enqueue_dispatch")
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
    result = enqueue_wechat_dispatch_task(
        source_platform=args.source_platform,
        source_user_id=args.source_user_id,
        dispatch_target_uid=args.dispatch_target_uid,
        extracted_fields=_build_extracted_fields(args),
        screenshot_ref=args.screenshot_ref,
        reason=args.reason,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
