from __future__ import annotations

import argparse
import json
from typing import Any

from autoin.config import Settings, get_settings
from autoin.coordinator import Coordinator
from autoin.gateway import GatewayPipeline, MemoryCompactor, MessageDebouncer
from autoin.infrastructure import EventType, RedisBroker, TaskPlanState, UnifiedEvent


def emit_control_plane_log(event: str, payload: dict[str, Any]) -> None:
    print(json.dumps({"event": event, **payload}, ensure_ascii=False), flush=True)


class ControlPlaneService:
    """Long-running Linux control-plane loop over the Redis event stream."""

    def __init__(
        self,
        broker: RedisBroker,
        settings: Settings,
        producer_name: str = "control_plane",
    ) -> None:
        self.broker = broker
        self.settings = settings
        self.producer_name = producer_name
        self.coordinator = Coordinator(broker, producer_name=f"{producer_name}.coordinator")
        self.debouncer = MessageDebouncer(broker, producer_name=f"{producer_name}.debouncer")
        self.compactor = MemoryCompactor(broker, settings, producer_name=f"{producer_name}.memory")
        self.pipeline = GatewayPipeline(
            self.debouncer,
            self.compactor,
            self.coordinator,
            producer_name=f"{producer_name}.pipeline",
        )

    def process_event(self, event: UnifiedEvent) -> dict[str, Any]:
        if event.event_type == EventType.MESSAGE_BUFFERED:
            payload = event.payload
            for index, message in enumerate(payload.messages):
                self.debouncer.add_message(
                    payload.conversation,
                    message,
                    observed_at=payload.observed_at,
                    screenshot_ref=payload.screenshot_ref if index == len(payload.messages) - 1 else None,
                    debounce_window_seconds=payload.debounce_window_seconds,
                )
            return {
                "handled": True,
                "event_type": event.event_type,
                "action": "debounce_buffered_message",
                "conversation_uid": payload.conversation.uid,
            }

        if event.event_type == EventType.MESSAGE_DEBOUNCED:
            payload = event.payload
            compaction_event = self.compactor.publish_compaction(
                conversation=payload.conversation,
                full_history=payload.messages,
                latest_screenshot_ref=payload.screenshot_ref,
            )
            return {
                "handled": True,
                "event_type": event.event_type,
                "action": "publish_memory_compaction",
                "conversation_uid": payload.conversation.uid,
                "compaction_event_id": compaction_event.event_id,
            }

        if event.event_type == EventType.MEMORY_COMPACTED:
            routed_event, stream_ids = self.pipeline.route_and_plan(event)
            return {
                "handled": True,
                "event_type": event.event_type,
                "action": "route_and_plan",
                "intent": routed_event.payload.intent,
                "stream_ids": stream_ids,
            }

        if event.event_type == EventType.ACTION_COMPLETED:
            released = self.coordinator.handle_task_success(event.payload)
            return {
                "handled": True,
                "event_type": event.event_type,
                "action": "release_dependent_tasks",
                "released_stream_ids": released,
            }

        if event.event_type == EventType.SNAPSHOT_CAPTURED:
            plan_id = self._find_plan_id_for_check_task(event.payload.check_task_id)
            released = self.coordinator.handle_snapshot_capture(plan_id, event.payload) if plan_id else []
            return {
                "handled": plan_id is not None,
                "event_type": event.event_type,
                "action": "handle_snapshot_capture",
                "plan_id": plan_id,
                "released_stream_ids": released,
            }

        return {
            "handled": False,
            "event_type": event.event_type,
            "action": "ignored",
        }

    def run_once(
        self,
        *,
        last_stream_id: str = "0-0",
        count: int = 10,
        block_ms: int = 1000,
        emit_logs: bool = False,
    ) -> dict[str, Any]:
        entries = self.broker.read_stream(last_stream_id=last_stream_id, count=count, block_ms=block_ms)
        processed: list[dict[str, Any]] = []
        current_stream_id = last_stream_id
        for stream_id, event in entries:
            current_stream_id = stream_id
            summary = self.process_event(event)
            processed.append(
                {
                    "stream_id": stream_id,
                    "event_id": event.event_id,
                    **summary,
                }
            )
            if emit_logs:
                emit_control_plane_log("control_plane_event_processed", processed[-1])
        flushed_events = self.pipeline.flush_and_compact()
        for flushed_event in flushed_events:
            processed.append(
                {
                    "stream_id": current_stream_id,
                    "event_id": flushed_event.event_id,
                    "handled": True,
                    "event_type": flushed_event.event_type,
                    "action": "flush_debounce_and_publish_compaction",
                }
            )
            if emit_logs:
                emit_control_plane_log("control_plane_event_processed", processed[-1])
        return {
            "last_stream_id": current_stream_id,
            "processed_count": len(processed),
            "processed": processed,
        }

    def run_loop(
        self,
        *,
        last_stream_id: str = "0-0",
        count: int = 10,
        block_ms: int = 1000,
        max_batches: int | None = None,
        emit_logs: bool = False,
    ) -> dict[str, Any]:
        processed_batches: list[dict[str, Any]] = []
        current_stream_id = last_stream_id
        batches = 0
        if emit_logs:
            emit_control_plane_log(
                "control_plane_started",
                {
                    "last_stream_id": last_stream_id,
                    "count": count,
                    "block_ms": block_ms,
                    "max_batches": max_batches,
                },
            )
        while True:
            batch = self.run_once(
                last_stream_id=current_stream_id,
                count=count,
                block_ms=block_ms,
                emit_logs=emit_logs,
            )
            current_stream_id = batch["last_stream_id"]
            processed_batches.append(batch)
            batches += 1
            if max_batches is not None and batches >= max_batches:
                break
        return {
            "batches": batches,
            "last_stream_id": current_stream_id,
            "processed_count": sum(batch["processed_count"] for batch in processed_batches),
            "batch_summaries": processed_batches,
        }

    def _find_plan_id_for_check_task(self, check_task_id: str) -> str | None:
        for state in self.broker.list_plan_states():
            if any(task.task_id == check_task_id for task in state.plan.tasks):
                return state.plan.plan_id
        return None


def build_control_plane_service(
    *,
    broker: RedisBroker | None = None,
    settings: Settings | None = None,
) -> ControlPlaneService:
    resolved_settings = settings or get_settings()
    selected_broker = broker or RedisBroker(resolved_settings)
    return ControlPlaneService(selected_broker, resolved_settings)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Linux control-plane loop over the Redis event stream.")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--block-ms", type=int, default=1000)
    parser.add_argument("--last-stream-id", default="0-0")
    parser.add_argument("--max-batches", type=int, default=None)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    service = build_control_plane_service()
    if args.once:
        result = service.run_once(
            last_stream_id=args.last_stream_id,
            count=args.count,
            block_ms=args.block_ms,
            emit_logs=not args.quiet,
        )
    else:
        result = service.run_loop(
            last_stream_id=args.last_stream_id,
            count=args.count,
            block_ms=args.block_ms,
            max_batches=args.max_batches,
            emit_logs=not args.quiet,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
