from datetime import UTC, datetime, timedelta

from autoin.adapters import AdapterDirectory, UnsupportedAdapterActionError
from autoin.config import Settings
from autoin.infrastructure.models import (
    AdapterHeartbeatPayload,
    AdapterManifestPayload,
    Platform,
    TaskKind,
    TaskPayload,
)


class StubBroker:
    def __init__(self) -> None:
        self.events = []

    def publish(self, event):  # noqa: ANN001
        self.events.append(event)
        return "1-0"


def test_adapter_directory_registers_manifest_and_validates_task() -> None:
    broker = StubBroker()
    settings = Settings(redis_host="redis.internal.example.com", adapter_heartbeat_ttl_ms=30000)
    directory = AdapterDirectory(broker, settings=settings)
    manifest = AdapterManifestPayload(
        adapter="wechat.executor",
        platform=Platform.WECHAT,
        role="executor",
        supported_actions=["send_dispatch_message"],
    )
    directory.mark_heartbeat(
        AdapterHeartbeatPayload(
            adapter="wechat.executor",
            platform=Platform.WECHAT,
            role="executor",
            observed_at=datetime.now(UTC),
        )
    )

    event = directory.register(manifest)
    directory.validate_task(
        TaskPayload(
            kind=TaskKind.UI_ACTION,
            adapter="wechat.executor",
            action="send_dispatch_message",
        )
    )

    assert event.event_type == "adapter_registered"
    assert directory.list_adapters() == ["wechat.executor"]


def test_adapter_directory_rejects_unknown_action() -> None:
    broker = StubBroker()
    settings = Settings(redis_host="redis.internal.example.com", adapter_heartbeat_ttl_ms=30000)
    directory = AdapterDirectory(broker, settings=settings)
    directory.register(
        AdapterManifestPayload(
            adapter="wechat.executor",
            platform=Platform.WECHAT,
            role="executor",
            supported_actions=["send_dispatch_message"],
        )
    )
    directory.mark_heartbeat(
        AdapterHeartbeatPayload(
            adapter="wechat.executor",
            platform=Platform.WECHAT,
            role="executor",
            observed_at=datetime.now(UTC),
        )
    )

    try:
        directory.validate_task(
            TaskPayload(
                kind=TaskKind.UI_ACTION,
                adapter="wechat.executor",
                action="send_auto_reply",
            )
        )
    except UnsupportedAdapterActionError:
        pass
    else:
        raise AssertionError("Expected unsupported action validation to fail.")


def test_adapter_directory_reports_offline_when_heartbeat_expires() -> None:
    broker = StubBroker()
    settings = Settings(redis_host="redis.internal.example.com", adapter_heartbeat_ttl_ms=1000)
    directory = AdapterDirectory(broker, settings=settings)
    directory.register(
        AdapterManifestPayload(
            adapter="wechat.executor",
            platform=Platform.WECHAT,
            role="executor",
            supported_actions=["send_dispatch_message"],
        )
    )
    heartbeat_time = datetime.now(UTC)
    directory.mark_heartbeat(
        AdapterHeartbeatPayload(
            adapter="wechat.executor",
            platform=Platform.WECHAT,
            role="executor",
            observed_at=heartbeat_time,
        )
    )

    assert directory.is_online("wechat.executor", now=heartbeat_time + timedelta(milliseconds=500)) is True
    status = directory.status("wechat.executor", now=heartbeat_time + timedelta(milliseconds=1500))

    assert status.online is False
    assert status.reason == "heartbeat_missing_or_expired"
