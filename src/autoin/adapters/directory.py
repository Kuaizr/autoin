from __future__ import annotations

from autoin.infrastructure.broker import RedisBroker
from autoin.infrastructure.models import AdapterManifestPayload, EventMetadata, EventType, TaskPayload, UnifiedEvent


class UnsupportedAdapterActionError(ValueError):
    pass


class AdapterDirectory:
    """Tracks adapter manifests and validates task/action compatibility."""

    def __init__(self, broker: RedisBroker, producer_name: str = "adapter.directory") -> None:
        self.broker = broker
        self.producer_name = producer_name
        self._manifests: dict[str, AdapterManifestPayload] = {}

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
        if task.action not in manifest.supported_actions:
            raise UnsupportedAdapterActionError(
                f"Adapter {task.adapter} does not support action {task.action}"
            )

    def list_adapters(self) -> list[str]:
        return sorted(self._manifests)
