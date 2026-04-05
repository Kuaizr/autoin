from __future__ import annotations

from abc import ABC, abstractmethod


class DesktopDriver(ABC):
    """Cross-platform control-plane interface for Windows desktop actions."""

    @abstractmethod
    def send_message(self, app: str, target_uid: str | None, message: str) -> dict[str, object]:
        """Send a message to a target conversation."""

    @abstractmethod
    def capture_window(self, app: str, target_uid: str | None, mode: str) -> dict[str, object]:
        """Capture a window or region and return metadata."""


class MockWindowsDriver(DesktopDriver):
    """Non-Windows placeholder driver used until real automation is wired in."""

    def send_message(self, app: str, target_uid: str | None, message: str) -> dict[str, object]:
        return {
            "driver": "mock_windows",
            "app": app,
            "target_uid": target_uid,
            "message": message,
            "operation": "send_message",
        }

    def capture_window(self, app: str, target_uid: str | None, mode: str) -> dict[str, object]:
        return {
            "driver": "mock_windows",
            "app": app,
            "target_uid": target_uid,
            "mode": mode,
            "operation": "capture_window",
        }
