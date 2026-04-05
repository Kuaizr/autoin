from __future__ import annotations

from autoin.coordinator import Coordinator
from autoin.gateway.debounce import MessageDebouncer
from autoin.gateway.memory import MemoryCompactor
from autoin.infrastructure.models import (
    EventMetadata,
    EventType,
    IntakeDecisionPayload,
    MemoryCompactionPayload,
    TaskKind,
    UnifiedEvent,
)


class GatewayPipeline:
    """Connects debounced inbound messages, memory compaction, and coordinator intake."""

    def __init__(
        self,
        debouncer: MessageDebouncer,
        compactor: MemoryCompactor,
        coordinator: Coordinator,
        producer_name: str = "gateway.pipeline",
    ) -> None:
        self.debouncer = debouncer
        self.compactor = compactor
        self.coordinator = coordinator
        self.producer_name = producer_name

    def flush_and_compact(self) -> list[UnifiedEvent]:
        debounced_events = self.debouncer.flush_due()
        compacted_events: list[UnifiedEvent] = []
        for event in debounced_events:
            payload = event.payload
            compaction_event = self.compactor.publish_compaction(
                conversation=payload.conversation,
                full_history=payload.messages,
                latest_screenshot_ref=payload.screenshot_ref,
            )
            compacted_events.append(compaction_event)
        return compacted_events

    def route_compacted_event(self, event: UnifiedEvent) -> UnifiedEvent:
        payload = event.payload
        decision = self.coordinator.handle_memory_compaction(payload)
        routed_event = UnifiedEvent(
            event_type=EventType.ACTION_REQUESTED,
            metadata=EventMetadata(
                producer=self.producer_name,
                correlation_id=event.metadata.correlation_id,
                causation_id=event.event_id,
            ),
            payload=decision,
        )
        self.coordinator.broker.publish(routed_event)
        return routed_event

    def route_and_plan(self, event: UnifiedEvent) -> tuple[UnifiedEvent, list[str]]:
        routed_event = self.route_compacted_event(event)
        plan, _, stream_ids, _ = self.coordinator.build_and_dispatch_plan(
            routed_event.payload,
            correlation_id=routed_event.metadata.correlation_id,
        )
        return routed_event, stream_ids
