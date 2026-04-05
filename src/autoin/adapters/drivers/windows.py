from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel, Field


class WindowReference(BaseModel):
    """Structured locator result for a desktop window target."""

    app: str
    target_uid: str | None = None
    backend: str = "uia"
    locator: str
    locator_status: str


class DriverActionResult(BaseModel):
    """Stable contract returned by Windows executor drivers."""

    driver: str
    operation: str
    status: str
    app: str
    target_uid: str | None = None
    mode: str | None = None
    message: str | None = None
    artifact_path: Path | None = None
    window: WindowReference | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class DesktopAutomationError(RuntimeError):
    """Structured runtime error for desktop automation failures."""

    def __init__(self, code: str, message: str, *, app: str, target_uid: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.app = app
        self.target_uid = target_uid


class DesktopDriver(ABC):
    """Cross-platform control-plane interface for Windows desktop actions."""

    @abstractmethod
    def send_message(self, app: str, target_uid: str | None, message: str) -> DriverActionResult:
        """Send a message to a target conversation."""

    @abstractmethod
    def capture_window(self, app: str, target_uid: str | None, mode: str) -> DriverActionResult:
        """Capture a window or region and return metadata."""

    @abstractmethod
    def rollback_ui(self, app: str, target_uid: str | None = None) -> DriverActionResult:
        """Best-effort recovery, such as sending ESC or closing a blocking popup."""


class MockWindowsDriver(DesktopDriver):
    """Non-Windows placeholder driver used until real automation is wired in."""

    def send_message(self, app: str, target_uid: str | None, message: str) -> DriverActionResult:
        return DriverActionResult(
            driver="mock_windows",
            operation="send_message",
            status="mocked",
            app=app,
            target_uid=target_uid,
            message=message,
            window=WindowReference(
                app=app,
                target_uid=target_uid,
                locator=target_uid or f"{app}_default",
                locator_status="mocked",
            ),
        )

    def capture_window(self, app: str, target_uid: str | None, mode: str) -> DriverActionResult:
        return DriverActionResult(
            driver="mock_windows",
            operation="capture_window",
            status="mocked",
            app=app,
            target_uid=target_uid,
            mode=mode,
            window=WindowReference(
                app=app,
                target_uid=target_uid,
                locator=target_uid or f"{app}_default",
                locator_status="mocked",
            ),
        )

    def rollback_ui(self, app: str, target_uid: str | None = None) -> DriverActionResult:
        return DriverActionResult(
            driver="mock_windows",
            operation="rollback_ui",
            status="mocked",
            app=app,
            target_uid=target_uid,
            window=WindowReference(
                app=app,
                target_uid=target_uid,
                locator=target_uid or f"{app}_default",
                locator_status="mocked",
            ),
            metadata={"strategy": ["esc", "dismiss_popup"]},
        )
