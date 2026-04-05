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
