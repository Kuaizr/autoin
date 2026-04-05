# Architecture Review

## Distributed Topology Risks
- Lack of formal contract between Linux control plane and Windows adapters creates runtime discovery pain; recommend defining `AdapterManifest` with endpoint metadata and heartbeat schema.
- Redis normalized to single namespace; without capacity planning, Streams can grow unbounded—add retention policies and monitor `length` and `last-delivered-id`.
- UI lock expiration currently unspecified; any process crash leaves `SETNX` lock orphans. Need TTL-based lock with renewal heartbeat plus dead-man switch to release via `PEXPIRE`.

## Missing Infrastructure
- No observability plan for Redis bus traffic or lock contention—add Prometheus-compatible metrics (`redis_pubsub_messages_total`, `ui_lock_failures_total`) plus structured logging for `Unified_Event`.
- State machine lacks persistence/backfill; plan to checkpoint Stream offsets per module to avoid recompute after crash.
- No security controls for cross-network Redis access; require TLS + ACLs for Redis, and rotate password via Vault/secrets manager placeholder while allowing Windows clients to fetch via secure channel.

## Recommendations
- Introduce `EventCatalog` specification (type/producer/consumer/priority) so Brain/Checker agents can subscribe declaratively rather than hard-coding channel names.
- Bake in `MemoryCompactor` queue with backpressure feedback so Token budgets stay within model context — for example, push summaries through `compaction_request` stream when `context_tokens` exceeds threshold.
- Develop deployment validation script that checks cross-OS connectivity, ensures Redis TLS certs, and verifies `BaseAdapter` version compatibility before allowing adapters to claim UI lock.
