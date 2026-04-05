from autoin.adapters import AdapterDirectory, UnsupportedAdapterActionError
from autoin.infrastructure.models import AdapterManifestPayload, Platform, TaskKind, TaskPayload


class StubBroker:
    def __init__(self) -> None:
        self.events = []

    def publish(self, event):  # noqa: ANN001
        self.events.append(event)
        return "1-0"


def test_adapter_directory_registers_manifest_and_validates_task() -> None:
    broker = StubBroker()
    directory = AdapterDirectory(broker)
    manifest = AdapterManifestPayload(
        adapter="wechat.executor",
        platform=Platform.WECHAT,
        role="executor",
        supported_actions=["send_dispatch_message"],
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
    directory = AdapterDirectory(broker)
    directory.register(
        AdapterManifestPayload(
            adapter="wechat.executor",
            platform=Platform.WECHAT,
            role="executor",
            supported_actions=["send_dispatch_message"],
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
