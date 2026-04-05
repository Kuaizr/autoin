from __future__ import annotations

from pathlib import Path
from sys import platform as sys_platform

from autoin.adapters.drivers.windows import DesktopDriver


class PywinautoUnavailableError(RuntimeError):
    pass


class PywinautoDriver(DesktopDriver):
    """Windows-only driver boundary for future pywinauto-backed automation."""

    def __init__(self) -> None:
        if sys_platform != "win32":
            raise PywinautoUnavailableError("PywinautoDriver is only available on Windows.")
        try:
            import pywinauto  # noqa: F401
        except ImportError as exc:  # pragma: no cover - depends on host environment
            raise PywinautoUnavailableError(
                "pywinauto is not installed. Install with `uv sync --extra windows` on Windows."
            ) from exc

    def send_message(self, app: str, target_uid: str | None, message: str) -> dict[str, object]:
        return {
            "driver": "pywinauto",
            "app": app,
            "target_uid": target_uid,
            "message": message,
            "operation": "send_message",
            "status": "stub",
        }

    def capture_window(self, app: str, target_uid: str | None, mode: str) -> dict[str, object]:
        artifact_dir = Path("artifacts") / "snapshots"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        return {
            "driver": "pywinauto",
            "app": app,
            "target_uid": target_uid,
            "mode": mode,
            "operation": "capture_window",
            "artifact_dir": str(artifact_dir),
            "status": "stub",
        }
