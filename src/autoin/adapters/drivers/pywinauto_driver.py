from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from sys import platform as sys_platform

from autoin.adapters.drivers.windows import DesktopDriver, DriverActionResult, WindowReference


class PywinautoUnavailableError(RuntimeError):
    pass


class PywinautoDriver(DesktopDriver):
    """Windows-only driver boundary for future pywinauto-backed automation."""

    def __init__(self, artifact_root: Path | None = None) -> None:
        if sys_platform != "win32":
            raise PywinautoUnavailableError("PywinautoDriver is only available on Windows.")
        try:
            import pywinauto  # noqa: F401
        except ImportError as exc:  # pragma: no cover - depends on host environment
            raise PywinautoUnavailableError(
                "pywinauto is not installed. Install with `uv sync --extra windows` on Windows."
            ) from exc
        self.artifact_root = artifact_root or Path("artifacts") / "windows"

    def resolve_window(self, app: str, target_uid: str | None) -> WindowReference:
        locator = target_uid or f"{app}_main_window"
        return WindowReference(
            app=app,
            target_uid=target_uid,
            backend="uia",
            locator=locator,
            locator_status="stubbed",
        )

    def build_capture_artifact_path(self, app: str, target_uid: str | None, mode: str) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        safe_target = (target_uid or "broadcast").replace("/", "_").replace("\\", "_")
        filename = f"{app}_{safe_target}_{mode}_{timestamp}.png"
        return self.artifact_root / app / mode / filename

    def send_message(self, app: str, target_uid: str | None, message: str) -> DriverActionResult:
        window = self.resolve_window(app, target_uid)
        return DriverActionResult(
            driver="pywinauto",
            operation="send_message",
            status="stubbed",
            app=app,
            target_uid=target_uid,
            message=message,
            window=window,
            metadata={"backend": window.backend},
        )

    def capture_window(self, app: str, target_uid: str | None, mode: str) -> DriverActionResult:
        window = self.resolve_window(app, target_uid)
        artifact_path = self.build_capture_artifact_path(app, target_uid, mode)
        artifact_dir = artifact_path.parent
        artifact_dir.mkdir(parents=True, exist_ok=True)
        return DriverActionResult(
            driver="pywinauto",
            operation="capture_window",
            status="stubbed",
            app=app,
            target_uid=target_uid,
            mode=mode,
            artifact_path=artifact_path,
            window=window,
            metadata={"artifact_dir": str(artifact_dir), "backend": window.backend},
        )

    def rollback_ui(self, app: str, target_uid: str | None = None) -> DriverActionResult:
        window = self.resolve_window(app, target_uid)
        return DriverActionResult(
            driver="pywinauto",
            operation="rollback_ui",
            status="stubbed",
            app=app,
            target_uid=target_uid,
            window=window,
            metadata={"strategy": ["esc", "close_interference_popup"], "backend": window.backend},
        )
