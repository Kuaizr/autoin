from __future__ import annotations

import json
from collections.abc import Iterator
from fnmatch import fnmatch

from redis import Redis

from autoin.config import Settings
from autoin.infrastructure.models import TaskPayload, TaskPlanState, UnifiedEvent


class RedisBroker:
    """Redis-backed event bus using both Streams and Pub/Sub."""

    def __init__(self, settings: Settings, client: Redis | None = None) -> None:
        self.settings = settings
        self.client = client or Redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )

    def publish(self, event: UnifiedEvent) -> str:
        event_json = event.model_dump_json()
        self.client.publish(self.settings.redis_pubsub_channel, event_json)
        stream_id = self.client.xadd(
            self.settings.redis_stream_key,
            {"event": event_json, "event_type": event.event_type},
        )
        return str(stream_id)

    def read_stream(
        self,
        last_stream_id: str = "0-0",
        count: int = 10,
        block_ms: int = 1000,
    ) -> list[tuple[str, UnifiedEvent]]:
        entries = self.client.xread(
            {self.settings.redis_stream_key: last_stream_id},
            count=count,
            block=block_ms,
        )
        return self._decode_stream_entries(entries)

    def enqueue_task(self, task: TaskPayload) -> str:
        task_json = task.model_dump_json()
        return str(
            self.client.xadd(
                self.settings.redis_task_stream_key,
                {
                    "task": task_json,
                    "task_kind": task.kind,
                    "adapter": task.adapter,
                },
            )
        )

    def move_to_dead_letter(self, task: TaskPayload, reason: str, error_code: str) -> str:
        task_json = task.model_dump_json()
        return str(
            self.client.xadd(
                self.settings.redis_dead_letter_stream_key,
                {
                    "task": task_json,
                    "reason": reason,
                    "error_code": error_code,
                    "task_kind": task.kind,
                    "adapter": task.adapter,
                },
            )
        )

    def save_plan_state(self, state: TaskPlanState) -> None:
        self.client.set(self.plan_state_key(state.plan.plan_id), state.model_dump_json())

    def load_plan_state(self, plan_id: str) -> TaskPlanState | None:
        raw_state = self.client.get(self.plan_state_key(plan_id))
        if raw_state is None:
            return None
        return TaskPlanState.model_validate_json(raw_state)

    def delete_plan_state(self, plan_id: str) -> int:
        return int(self.client.delete(self.plan_state_key(plan_id)))

    def plan_state_key(self, plan_id: str) -> str:
        return f"{self.settings.redis_plan_state_prefix}:{plan_id}"

    def list_plan_states(self) -> list[TaskPlanState]:
        pattern = f"{self.settings.redis_plan_state_prefix}:*"
        states: list[TaskPlanState] = []
        for key in self.client.scan_iter(match=pattern):
            raw_state = self.client.get(key)
            if raw_state is None:
                continue
            states.append(TaskPlanState.model_validate_json(raw_state))
        return states

    def ensure_consumer_group(self, group_name: str | None = None) -> None:
        group = group_name or self.settings.redis_consumer_group
        try:
            self.client.xgroup_create(
                self.settings.redis_task_stream_key,
                group,
                id="0-0",
                mkstream=True,
            )
        except Exception as exc:  # redis raises a generic ResponseError for BUSYGROUP
            if "BUSYGROUP" not in str(exc):
                raise

    def consume_tasks(
        self,
        consumer_name: str,
        group_name: str | None = None,
        count: int = 10,
        block_ms: int = 1000,
    ) -> list[tuple[str, TaskPayload]]:
        group = group_name or self.settings.redis_consumer_group
        entries = self.client.xreadgroup(
            group,
            consumer_name,
            {self.settings.redis_task_stream_key: ">"},
            count=count,
            block=block_ms,
        )
        tasks: list[tuple[str, TaskPayload]] = []
        for _, stream_entries in entries:
            for stream_id, fields in stream_entries:
                raw_task = fields.get("task")
                if not raw_task:
                    continue
                tasks.append((str(stream_id), TaskPayload.model_validate_json(raw_task)))
        return tasks

    def ack_task(self, stream_id: str, group_name: str | None = None) -> int:
        group = group_name or self.settings.redis_consumer_group
        return int(
            self.client.xack(
                self.settings.redis_task_stream_key,
                group,
                stream_id,
            )
        )

    def pending_tasks(
        self,
        consumer_name: str | None = None,
        group_name: str | None = None,
        idle_ms: int = 0,
    ) -> list[tuple[str, TaskPayload]]:
        group = group_name or self.settings.redis_consumer_group
        pending = self.client.xpending_range(
            self.settings.redis_task_stream_key,
            group,
            min="-",
            max="+",
            count=100,
            consumername=consumer_name,
            idle=idle_ms,
        )
        entries: list[tuple[str, TaskPayload]] = []
        for item in pending:
            stream_id = str(item["message_id"])
            claimed = self.client.xrange(self.settings.redis_task_stream_key, min=stream_id, max=stream_id, count=1)
            if not claimed:
                continue
            _, fields = claimed[0]
            raw_task = fields.get("task")
            if not raw_task:
                continue
            entries.append((stream_id, TaskPayload.model_validate_json(raw_task)))
        return entries

    def claim_stale_tasks(
        self,
        consumer_name: str,
        min_idle_ms: int,
        group_name: str | None = None,
        count: int = 100,
    ) -> list[tuple[str, TaskPayload]]:
        group = group_name or self.settings.redis_consumer_group
        next_id, claimed, deleted = self.client.xautoclaim(
            self.settings.redis_task_stream_key,
            group,
            consumer_name,
            min_idle_ms,
            start_id="0-0",
            count=count,
        )
        del next_id, deleted
        tasks: list[tuple[str, TaskPayload]] = []
        for stream_id, fields in claimed:
            raw_task = fields.get("task")
            if not raw_task:
                continue
            tasks.append((str(stream_id), TaskPayload.model_validate_json(raw_task)))
        return tasks

    def subscribe(self) -> Iterator[UnifiedEvent]:
        pubsub = self.client.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(self.settings.redis_pubsub_channel)
        for message in pubsub.listen():
            data = message.get("data")
            if not isinstance(data, str):
                continue
            yield UnifiedEvent.model_validate_json(data)

    @staticmethod
    def _decode_stream_entries(
        entries: list[tuple[str, list[tuple[str, dict[str, str]]]]],
    ) -> list[tuple[str, UnifiedEvent]]:
        events: list[tuple[str, UnifiedEvent]] = []
        for _, stream_entries in entries:
            for stream_id, fields in stream_entries:
                raw_event = fields.get("event")
                if not raw_event:
                    continue
                events.append((str(stream_id), UnifiedEvent.model_validate_json(raw_event)))
        return events

    @staticmethod
    def dumps(event: UnifiedEvent) -> str:
        return json.dumps(event.model_dump(mode="json"))
