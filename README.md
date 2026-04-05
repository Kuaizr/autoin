# autoin

Phase 1 infrastructure skeleton for a distributed Linux control plane and Windows execution plane automation system.

## Python Environment

This repository uses `uv` for Python environment and dependency management.

```bash
uv sync --extra dev
uv run pytest -q
```

## WeChat Smoke Test

On a Windows execution node with WeChat Desktop already logged in:

```bash
uv sync --extra dev --extra windows
uv run python -m autoin.tools.wechat_smoke \
  --source-user-id u1 \
  --dispatch-target-uid wechat_dispatch_group \
  --item-code A123 \
  --address Shanghai \
  --phone 13800138000
```

Use `--mock-driver` if you only want to verify the task and rendering path without touching the desktop UI.

## WeChat Worker

On the Windows execution node, run a WeChat executor worker that consumes Redis tasks:

```bash
uv run python -m autoin.tools.wechat_worker --once --mock-driver
```

For a real Windows worker using `pywinauto`, keep WeChat Desktop open and run:

```bash
uv run python -m autoin.tools.wechat_worker
```

Use `--max-batches 1` if you want a finite run while testing task delivery from Redis.

## Enqueue Dispatch Task

On the Linux control plane, enqueue a WeChat dispatch task into Redis:

```bash
uv run python -m autoin.tools.enqueue_dispatch \
  --source-user-id u1 \
  --dispatch-target-uid 文件传输助手 \
  --item-code TEST-REDIS-001 \
  --address Shanghai \
  --phone 13800138000
```

This is the simplest way to hand a real dispatch task to the Windows `wechat_worker`.

## Control Plane

On the Linux control plane, run the event-stream loop that turns debounced messages into plans and follow-up tasks:

```bash
uv run python -m autoin.tools.control_plane
```

For a bounded debug run:

```bash
uv run python -m autoin.tools.control_plane --max-batches 1
```

Use `--once --quiet` if you only want the final JSON summary for a single polling batch.
