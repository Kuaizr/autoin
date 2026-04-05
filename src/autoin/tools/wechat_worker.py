from __future__ import annotations

import argparse
import json
import socket
from typing import Any

from autoin.adapters import TaskWorker, build_executor_adapter
from autoin.config import Settings, get_settings
from autoin.infrastructure import Platform, RedisBroker, RedisLockManager


def default_consumer_name() -> str:
    hostname = socket.gethostname()
    return f"wechat-worker-{hostname}"


def _build_worker_snapshot(consumer_name: str, executor: Any, processed_stream_ids: list[str], **extra: Any) -> dict[str, Any]:
    return {
        "consumer_name": consumer_name,
        "processed_stream_ids": processed_stream_ids,
        "processed_count": len(processed_stream_ids),
        "last_action_result": executor.last_action_result if processed_stream_ids else None,
        "last_rollback_result": executor.last_rollback_result if processed_stream_ids else None,
        **extra,
    }


def emit_worker_log(event: str, payload: dict[str, Any]) -> None:
    print(
        json.dumps(
            {
                "event": event,
                **payload,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


def build_wechat_worker(
    consumer_name: str,
    *,
    prefer_pywinauto: bool = True,
    broker: RedisBroker | None = None,
    lock_manager: RedisLockManager | None = None,
    settings: Settings | None = None,
) -> tuple[TaskWorker, Any]:
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
    worker = TaskWorker(
        broker=selected_broker,
        executor=executor,
        consumer_name=consumer_name,
    )
    return worker, executor


def run_wechat_worker_once(
    consumer_name: str,
    *,
    prefer_pywinauto: bool = True,
    count: int = 10,
    block_ms: int = 1000,
    broker: RedisBroker | None = None,
    lock_manager: RedisLockManager | None = None,
    settings: Settings | None = None,
    emit_logs: bool = False,
) -> dict[str, Any]:
    worker, executor = build_wechat_worker(
        consumer_name=consumer_name,
        prefer_pywinauto=prefer_pywinauto,
        broker=broker,
        lock_manager=lock_manager,
        settings=settings,
    )
    executor.start_listening()
    if emit_logs:
        emit_worker_log(
            "worker_started",
            {
                "consumer_name": consumer_name,
                "mode": "once",
                "count": count,
                "block_ms": block_ms,
                "driver_mode": "pywinauto" if prefer_pywinauto else "mock_windows",
            },
        )
    processed = worker.poll_once(count=count, block_ms=block_ms)
    snapshot = _build_worker_snapshot(consumer_name, executor, processed)
    if emit_logs:
        emit_worker_log("worker_batch_processed", snapshot)
    return snapshot


def run_wechat_worker_loop(
    consumer_name: str,
    *,
    prefer_pywinauto: bool = True,
    count: int = 10,
    block_ms: int = 1000,
    max_batches: int | None = None,
    broker: RedisBroker | None = None,
    lock_manager: RedisLockManager | None = None,
    settings: Settings | None = None,
    emit_logs: bool = False,
) -> dict[str, Any]:
    worker, executor = build_wechat_worker(
        consumer_name=consumer_name,
        prefer_pywinauto=prefer_pywinauto,
        broker=broker,
        lock_manager=lock_manager,
        settings=settings,
    )
    executor.start_listening()
    if emit_logs:
        emit_worker_log(
            "worker_started",
            {
                "consumer_name": consumer_name,
                "mode": "loop",
                "count": count,
                "block_ms": block_ms,
                "max_batches": max_batches,
                "driver_mode": "pywinauto" if prefer_pywinauto else "mock_windows",
            },
        )
    processed_stream_ids: list[str] = []
    batch_summaries: list[dict[str, Any]] = []
    batches = 0
    while True:
        batch_processed = worker.poll_once(count=count, block_ms=block_ms)
        processed_stream_ids.extend(batch_processed)
        batches += 1
        batch_summaries.append(
            {
                "batch": batches,
                "processed_stream_ids": batch_processed,
                "processed_count": len(batch_processed),
                "last_action_result": executor.last_action_result if batch_processed else None,
                "last_rollback_result": executor.last_rollback_result if batch_processed else None,
            }
        )
        if emit_logs:
            emit_worker_log("worker_batch_processed", batch_summaries[-1])
        if max_batches is not None and batches >= max_batches:
            break
    return _build_worker_snapshot(
        consumer_name,
        executor,
        processed_stream_ids,
        batches=batches,
        batch_summaries=batch_summaries,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Windows WeChat executor task worker.")
    parser.add_argument("--consumer-name", default=default_consumer_name())
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--block-ms", type=int, default=1000)
    parser.add_argument("--max-batches", type=int, default=None, help="Stop after N poll batches. Omit for an endless worker loop.")
    parser.add_argument("--once", action="store_true", help="Run a single poll batch and exit.")
    parser.add_argument("--mock-driver", action="store_true", help="Use the mock Windows driver instead of pywinauto.")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-batch worker logs and only print the final JSON summary.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.once:
        result = run_wechat_worker_once(
            consumer_name=args.consumer_name,
            prefer_pywinauto=not args.mock_driver,
            count=args.count,
            block_ms=args.block_ms,
            emit_logs=not args.quiet,
        )
    else:
        result = run_wechat_worker_loop(
            consumer_name=args.consumer_name,
            prefer_pywinauto=not args.mock_driver,
            count=args.count,
            block_ms=args.block_ms,
            max_batches=args.max_batches,
            emit_logs=not args.quiet,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
