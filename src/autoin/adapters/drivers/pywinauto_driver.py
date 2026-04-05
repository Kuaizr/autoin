from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from sys import platform as sys_platform
import re
import time

from autoin.adapters.drivers.catalog import get_window_profile
from autoin.adapters.drivers.windows import (
    DesktopAutomationError,
    DesktopDriver,
    DriverActionResult,
    WindowReference,
)


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
        profile = get_window_profile(app)
        locator = target_uid or "|".join(profile.title_patterns) or f"{app}_main_window"
        return WindowReference(
            app=app,
            target_uid=target_uid,
            backend=profile.backend,
            locator=locator,
            locator_status="stubbed",
        )

    @staticmethod
    def _set_windows_clipboard_text(text: str) -> None:
        import ctypes  # pragma: no cover - Windows-only runtime

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        GMEM_MOVEABLE = 0x0002
        CF_UNICODETEXT = 13

        if not user32.OpenClipboard(None):
            raise DesktopAutomationError("clipboard_open_failed", "Failed to open Windows clipboard.", app="wechat")
        try:
            user32.EmptyClipboard()
            data = text.encode("utf-16-le") + b"\x00\x00"
            handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            if not handle:
                raise DesktopAutomationError(
                    "clipboard_alloc_failed",
                    "Failed to allocate clipboard buffer.",
                    app="wechat",
                )
            buffer = kernel32.GlobalLock(handle)
            ctypes.memmove(buffer, data, len(data))
            kernel32.GlobalUnlock(handle)
            if not user32.SetClipboardData(CF_UNICODETEXT, handle):
                raise DesktopAutomationError(
                    "clipboard_set_failed",
                    "Failed to populate clipboard text.",
                    app="wechat",
                )
        finally:
            user32.CloseClipboard()

    def _find_live_window(self, app: str):  # noqa: ANN202
        from pywinauto import Desktop  # pragma: no cover - Windows-only runtime

        profile = get_window_profile(app)
        title_pattern = "|".join(re.escape(title) for title in profile.title_patterns if title)
        title_regex = re.compile(title_pattern, re.IGNORECASE) if title_pattern else None
        for window in Desktop(backend=profile.backend).windows():
            title = window.window_text()
            if not title:
                continue
            if title_regex and not title_regex.search(title):
                continue
            if not window.is_visible():
                continue
            return window
        raise DesktopAutomationError(
            "window_not_found",
            f"Could not find a visible {app} desktop window.",
            app=app,
        )

    @staticmethod
    def _focus_window(window) -> None:  # noqa: ANN001
        try:  # pragma: no cover - Windows-only runtime
            if window.is_minimized():
                window.restore()
        except Exception:
            pass
        window.set_focus()
        time.sleep(0.2)

    def _send_wechat_message(self, target_uid: str | None, message: str) -> WindowReference:
        from pywinauto.keyboard import send_keys  # pragma: no cover - Windows-only runtime

        window = self._find_live_window("wechat")
        self._focus_window(window)
        if target_uid:
            send_keys("^f")
            time.sleep(0.2)
            self._set_windows_clipboard_text(target_uid)
            send_keys("^v")
            time.sleep(0.2)
            send_keys("{ENTER}")
            time.sleep(0.4)
        self._set_windows_clipboard_text(message)
        send_keys("^v")
        time.sleep(0.2)
        send_keys("{ENTER}")
        return WindowReference(
            app="wechat",
            target_uid=target_uid,
            backend=get_window_profile("wechat").backend,
            locator=window.window_text() or "wechat_window",
            locator_status="resolved",
        )

    def build_capture_artifact_path(self, app: str, target_uid: str | None, mode: str) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        safe_target = (target_uid or "broadcast").replace("/", "_").replace("\\", "_")
        filename = f"{app}_{safe_target}_{mode}_{timestamp}.png"
        return self.artifact_root / app / mode / filename

    def send_message(self, app: str, target_uid: str | None, message: str) -> DriverActionResult:
        if app == "wechat":  # pragma: no branch - simple platform switch
            window = self._send_wechat_message(target_uid, message)
            return DriverActionResult(
                driver="pywinauto",
                operation="send_message",
                status="sent",
                app=app,
                target_uid=target_uid,
                message=message,
                window=window,
                metadata={"backend": window.backend, "delivery": "live_wechat"},
            )
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
        if app == "wechat" and sys_platform == "win32":  # pragma: no branch - Windows-only side effect
            from pywinauto.keyboard import send_keys  # pragma: no cover - Windows-only runtime

            live_window = self._find_live_window(app)
            self._focus_window(live_window)
            send_keys("{ESC}")
            window = WindowReference(
                app=app,
                target_uid=target_uid,
                backend=get_window_profile(app).backend,
                locator=live_window.window_text() or window.locator,
                locator_status="resolved",
            )
        return DriverActionResult(
            driver="pywinauto",
            operation="rollback_ui",
            status="sent" if app == "wechat" and sys_platform == "win32" else "stubbed",
            app=app,
            target_uid=target_uid,
            window=window,
            metadata={"strategy": ["esc", "close_interference_popup"], "backend": window.backend},
        )
