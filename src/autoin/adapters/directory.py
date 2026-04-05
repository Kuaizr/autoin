from __future__ import annotations

from datetime import UTC, datetime, timedelta

from autoin.config import Settings, get_settings
from autoin.infrastructure.broker import RedisBroker
from autoin.infrastructure.models import (
    AdapterHeartbeatPayload,
    AdapterManifestPayload,
    AdapterStatusPayload,
    EventMetadata,
    EventType,
    TaskPayload,
    UnifiedEvent,
)


class UnsupportedAdapterActionError(ValueError):
    pass


class AdapterDirectory:
    """Tracks adapter manifests and validates task/action compatibility."""

    def __init__(
        self,
        broker: RedisBroker,
        producer_name: str = "adapter.directory",
        settings: Settings | None = None,
    ) -> None:
        self.broker = broker
        self.producer_name = producer_name
        self.settings = settings or get_settings()
        self._manifests: dict[str, AdapterManifestPayload] = {}
        self._last_seen_at: dict[str, datetime] = {}

    def register(self, manifest: AdapterManifestPayload) -> UnifiedEvent:
        self._manifests[manifest.adapter] = manifest
        event = UnifiedEvent(
            event_type=EventType.ADAPTER_REGISTERED,
            metadata=EventMetadata(producer=self.producer_name),
            payload=manifest,
        )
        self.broker.publish(event)
        return event

    def get_manifest(self, adapter_name: str) -> AdapterManifestPayload | None:
        return self._manifests.get(adapter_name)

    def validate_task(self, task: TaskPayload) -> None:
        manifest = self.get_manifest(task.adapter)
        if manifest is None:
            raise UnsupportedAdapterActionError(f"Adapter not registered: {task.adapter}")
        if not self.is_online(task.adapter):
            raise UnsupportedAdapterActionError(f"Adapter offline: {task.adapter}")
        if task.action not in manifest.supported_actions:
            raise UnsupportedAdapterActionError(
                f"Adapter {task.adapter} does not support action {task.action}"
            )

    def mark_heartbeat(self, heartbeat: AdapterHeartbeatPayload) -> UnifiedEvent:
        self._last_seen_at[heartbeat.adapter] = heartbeat.observed_at
        event = UnifiedEvent(
            event_type=EventType.ADAPTER_HEARTBEAT,
            metadata=EventMetadata(producer=self.producer_name),
            payload=heartbeat,
        )
        self.broker.publish(event)
        return event

    def last_seen_at(self, adapter_name: str) -> datetime | None:
        return self._last_seen_at.get(adapter_name)

    def is_online(self, adapter_name: str, now: datetime | None = None) -> bool:
        last_seen = self.last_seen_at(adapter_name)
        if last_seen is None:
            return False
        reference = now or datetime.now(UTC)
        ttl = timedelta(milliseconds=self.settings.adapter_heartbeat_ttl_ms)
        return reference - last_seen <= ttl

    def status(self, adapter_name: str, now: datetime | None = None) -> AdapterStatusPayload:
        last_seen = self.last_seen_at(adapter_name)
        online = self.is_online(adapter_name, now=now)
        reason = "heartbeat_fresh" if online else "heartbeat_missing_or_expired"
        return AdapterStatusPayload(
            adapter=adapter_name,
            online=online,
            last_seen_at=last_seen,
            reason=reason,
        )

    def list_adapters(self) -> list[str]:
        return sorted(self._manifests)
