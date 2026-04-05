from __future__ import annotations

import json
from collections.abc import Iterator

from redis import Redis

from autoin.config import Settings
from autoin.infrastructure.models import TaskPayload, UnifiedEvent


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
