# Phase 1 Plan

## Scope
Deliverables cover Module 1 (Infrastructure) for the Linux control plane plus the Redis bus that links to Windows adapters. Focus is defining contracts, schemas, and foundational services before any cognitive or adapter-specific logic.

## Interfaces & Data Models
- `UnifiedEventModel` (Pydantic): fields `event_id`, `source_adapter`, `uid`, `type`, `payload`, `timestamp`, `metadata`. Enforces consistent metadata for debounce logic and replay recovery.
- `TaskPayloadModel` (Pydantic): fields `task_id`, `sequence`, `action`, `payload`, `dependencies`, `lock_id`. Supports Coordinator-issued TODO lists with dependency checks.
- Redis streams:
  * `stream:events:{adapter}` accepts serialized `UnifiedEventModel`.
  * `stream:tasks` stores `TaskPayloadModel`; Controller consumes with `READGROUP` per coordinator instance.
- Lock manager API:
  * `acquire_ui_lock(adapter_id, timeout_ms)` returns `lock_token`.
  * `refresh_ui_lock(lock_token)` extends TTL.
  * `release_ui_lock(lock_token)` handles normal release.
  * Failures logged to `ui_lock_failures_total`.
- Config template `config.yaml` exposes `redis.host`, `redis.port`, `redis.password`, `redis.tls_enabled`, `redis.ca_path` so Windows adapters can connect cross-network. `localhost` must never be hard-coded.

## Milestones
1. Define schema package (`models/`), including serialization helpers and example payloads for test harnessing. Document Redis key conventions.
2. Implement `redis_bus.py` wrapper around `aioredis` or `redis-py` async client, covering publish/subscribe, stream enqueueing, and consumer group management.
3. Build `lock_manager.py` that uses `SETNX` + `PEXPIRE`, stores lock metadata in `hash`, and emits telemetry for contention/timeout events.

## Sub-Agent Assignments
- `schema-agent`: owns Pydantic models, validation utils, and sample payloads described above. Delivers `models/__init__.py` and accompanying README with serialization/deserialization guidance.
- `bus-agent`: implements `RedisBus` class with `publish_event`, `enqueue_task`, `consume_tasks`, and exposes tracing hooks that the Coordinator can use for debouncing and state machine transitions.
- `lock-agent`: creates distributed UI mutex API plus helper for adapters to perform rollback when lock acquisition fails or expires. Also responsible for documenting lock usage patterns and TTL configuration.

## Validation Strategy
- Add simple smoke scripts that instantiate `RedisBus`, push a `UnifiedEventModel`, and ensure a consumer group can read and ack from `stream:tasks`.
- Simulate UI lock contention by running two agents with conflicting `adapter_id` values to prove TTL-driven release works and failure metrics emit as expected.
