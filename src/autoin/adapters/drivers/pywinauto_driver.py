from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import subprocess
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
        self.enable_live_wechat = True

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
        from ctypes import wintypes  # pragma: no cover - Windows-only runtime

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        GMEM_MOVEABLE = 0x0002
        CF_UNICODETEXT = 13

        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.EmptyClipboard.argtypes = []
        user32.EmptyClipboard.restype = wintypes.BOOL
        user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        user32.SetClipboardData.restype = wintypes.HANDLE
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = wintypes.BOOL

        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = wintypes.LPVOID
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.restype = wintypes.BOOL
        kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalFree.restype = wintypes.HGLOBAL

        if not user32.OpenClipboard(None):
            raise DesktopAutomationError("clipboard_open_failed", "Failed to open Windows clipboard.", app="wechat")
        handle = None
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
            if not buffer:
                kernel32.GlobalFree(handle)
                raise DesktopAutomationError(
                    "clipboard_lock_failed",
                    "Failed to lock clipboard buffer.",
                    app="wechat",
                )
            ctypes.memmove(buffer, data, len(data))
            kernel32.GlobalUnlock(handle)
            if not user32.SetClipboardData(CF_UNICODETEXT, handle):
                kernel32.GlobalFree(handle)
                raise DesktopAutomationError(
                    "clipboard_set_failed",
                    "Failed to populate clipboard text.",
                    app="wechat",
                )
            handle = None
        finally:
            user32.CloseClipboard()
            if handle:
                kernel32.GlobalFree(handle)

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

    @staticmethod
    def _send_wechat_keys(keys: str) -> None:
        from pywinauto.keyboard import send_keys  # pragma: no cover - Windows-only runtime

        send_keys(keys)

    @staticmethod
    def _focus_wechat_editor(window) -> None:  # noqa: ANN001
        rectangle = window.rectangle()
        width = rectangle.width()
        height = rectangle.height()
        x = max(120, width // 2)
        y = max(120, height - 90)
        window.click_input(coords=(x, y))
        time.sleep(0.2)

    def _open_wechat_search_and_select_target(self, target_uid: str) -> None:
        self._send_wechat_keys("^f")
        time.sleep(0.2)
        self._set_windows_clipboard_text(target_uid)
        self._send_wechat_keys("^v")
        time.sleep(0.2)
        self._send_wechat_keys("{ENTER}")
        time.sleep(0.6)

    def _send_wechat_message_once(self, target_uid: str | None, message: str) -> tuple[WindowReference, list[str]]:
        operation_log: list[str] = []
        window = self._find_live_window("wechat")
        operation_log.append("window_resolved")
        self._focus_window(window)
        operation_log.append("window_focused")
        if target_uid:
            self._open_wechat_search_and_select_target(target_uid)
            operation_log.append("search_target_selected")
            self._focus_wechat_editor(window)
            operation_log.append("editor_focused_by_click")
        else:
            self._focus_wechat_editor(window)
            operation_log.append("editor_focused_by_click")
        self._set_windows_clipboard_text(message)
        operation_log.append("message_copied")
        self._send_wechat_keys("^v")
        time.sleep(0.2)
        operation_log.append("message_pasted")
        self._send_wechat_keys("{ENTER}")
        operation_log.append("message_sent")
        return WindowReference(
            app="wechat",
            target_uid=target_uid,
            backend=get_window_profile("wechat").backend,
            locator=window.window_text() or "wechat_window",
            locator_status="resolved",
        ), operation_log

    def _send_wechat_message(self, target_uid: str | None, message: str) -> tuple[WindowReference, dict[str, object]]:
        attempts: list[dict[str, object]] = []
        last_error: DesktopAutomationError | None = None
        for attempt in (1, 2):
            try:
                window, operation_log = self._send_wechat_message_once(target_uid, message)
                attempts.append(
                    {
                        "attempt": attempt,
                        "status": "sent",
                        "operation_log": operation_log,
                    }
                )
                return window, {
                    "delivery": "live_wechat",
                    "delivery_attempts": attempts,
                }
            except DesktopAutomationError as exc:
                attempts.append(
                    {
                        "attempt": attempt,
                        "status": "failed",
                        "error_code": exc.code,
                        "error_message": str(exc),
                    }
                )
                last_error = exc
                if attempt == 1:
                    time.sleep(0.4)
                    continue
                raise
        assert last_error is not None
        raise last_error

    @staticmethod
    def _safe_collect_control_texts(control) -> list[str]:  # noqa: ANN001
        texts: list[str] = []
        for accessor in ("window_text", "texts", "legacy_properties"):
            try:
                value = getattr(control, accessor)()
            except Exception:
                continue
            if isinstance(value, str):
                candidate_values = [value]
            elif isinstance(value, dict):
                candidate_values = [str(item) for item in value.values()]
            else:
                candidate_values = [str(item) for item in value if item]
            for candidate in candidate_values:
                cleaned = candidate.strip()
                if not cleaned:
                    continue
                if texts and texts[-1] == cleaned:
                    continue
                texts.append(cleaned)
        return texts

    @classmethod
    def _read_visible_text_controls(cls, window) -> list[str]:  # noqa: ANN001
        texts: list[str] = []
        control_types = {"Text", "Edit", "ListItem", "Document", "Pane", "Button"}
        controls = [window]
        try:
            controls.extend(window.descendants())
        except Exception:
            pass
        for control in controls:
            try:
                if hasattr(control, "is_visible") and not control.is_visible():
                    continue
            except Exception:
                continue
            try:
                element_info = getattr(control, "element_info", None)
                control_type = getattr(element_info, "control_type", None)
            except Exception:
                control_type = None
            if control_type and control_type not in control_types:
                continue
            for text in cls._safe_collect_control_texts(control):
                if texts and texts[-1] == text:
                    continue
                texts.append(text)
        return texts

    def observe_wechat_conversation(self, target_uid: str | None = None) -> dict[str, object]:
        window = self._find_live_window("wechat")
        texts = self._read_visible_text_controls(window)
        return {
            "driver": "pywinauto",
            "app": "wechat",
            "target_uid": target_uid,
            "window": WindowReference(
                app="wechat",
                target_uid=target_uid,
                backend=get_window_profile("wechat").backend,
                locator=window.window_text() or "wechat_window",
                locator_status="resolved",
            ),
            "texts": texts,
        }

    @classmethod
    def _collect_uia_debug_nodes(cls, window, max_nodes: int = 200) -> list[dict[str, object]]:  # noqa: ANN001
        nodes: list[dict[str, object]] = []
        queue: list[tuple[object, int]] = [(window, 0)]
        while queue and len(nodes) < max_nodes:
            control, depth = queue.pop(0)
            try:
                element_info = getattr(control, "element_info", None)
                control_type = getattr(element_info, "control_type", None)
                class_name = getattr(element_info, "class_name", None)
                automation_id = getattr(element_info, "automation_id", None)
                name = getattr(element_info, "name", None)
            except Exception:
                control_type = None
                class_name = None
                automation_id = None
                name = None
            texts = cls._safe_collect_control_texts(control)
            nodes.append(
                {
                    "depth": depth,
                    "control_type": control_type,
                    "class_name": class_name,
                    "automation_id": automation_id,
                    "name": name,
                    "texts": texts,
                }
            )
            try:
                children = list(control.children())
            except Exception:
                children = []
            for child in children:
                queue.append((child, depth + 1))
        return nodes

    def dump_wechat_uia_tree(self, max_nodes: int = 200) -> dict[str, object]:
        window = self._find_live_window("wechat")
        return {
            "driver": "pywinauto",
            "app": "wechat",
            "window": WindowReference(
                app="wechat",
                target_uid=None,
                backend=get_window_profile("wechat").backend,
                locator=window.window_text() or "wechat_window",
                locator_status="resolved",
            ),
            "nodes": self._collect_uia_debug_nodes(window, max_nodes=max_nodes),
        }

    def build_capture_artifact_path(self, app: str, target_uid: str | None, mode: str) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        safe_target = (target_uid or "broadcast").replace("/", "_").replace("\\", "_")
        filename = f"{app}_{safe_target}_{mode}_{timestamp}.png"
        return self.artifact_root / app / mode / filename

    def capture_live_wechat_chat_region(self, target_uid: str | None = None) -> dict[str, object]:
        window = self._find_live_window("wechat")
        artifact_path = self.build_capture_artifact_path("wechat", target_uid, "chat_region")
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        image = window.capture_as_image()
        if image is None:
            raise DesktopAutomationError(
                "capture_image_unavailable",
                "WeChat screenshot capture is unavailable. Install Pillow with `uv sync --extra windows` on Windows.",
                app="wechat",
                target_uid=target_uid,
            )
        width, height = image.size
        crop_box = (
            int(width * 0.28),
            int(height * 0.10),
            int(width * 0.98),
            int(height * 0.82),
        )
        cropped = image.crop(crop_box)
        cropped.save(artifact_path)
        return {
            "driver": "pywinauto",
            "app": "wechat",
            "target_uid": target_uid,
            "artifact_path": artifact_path,
            "crop_box": crop_box,
            "window": WindowReference(
                app="wechat",
                target_uid=target_uid,
                backend=get_window_profile("wechat").backend,
                locator=window.window_text() or "wechat_window",
                locator_status="resolved",
            ),
        }

    def capture_live_wechat_ocr_probes(self, target_uid: str | None = None) -> list[dict[str, object]]:
        window = self._find_live_window("wechat")
        image = window.capture_as_image()
        if image is None:
            raise DesktopAutomationError(
                "capture_image_unavailable",
                "WeChat screenshot capture is unavailable. Install Pillow with `uv sync --extra windows` on Windows.",
                app="wechat",
                target_uid=target_uid,
            )
        width, height = image.size
        profiles = [
            ("full_window", (0, 0, width, height)),
            ("right_panel", (int(width * 0.24), 0, width, height)),
            ("chat_region", (int(width * 0.28), int(height * 0.10), int(width * 0.98), int(height * 0.82))),
            ("chat_dense", (int(width * 0.34), int(height * 0.12), int(width * 0.94), int(height * 0.72))),
            ("latest_messages", (int(width * 0.34), int(height * 0.16), int(width * 0.94), int(height * 0.56))),
        ]
        probes: list[dict[str, object]] = []
        for mode, crop_box in profiles:
            artifact_path = self.build_capture_artifact_path("wechat", target_uid, mode)
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            cropped = image.crop(crop_box)
            cropped.save(artifact_path)
            probes.append(
                {
                    "mode": mode,
                    "artifact_path": artifact_path,
                    "crop_box": crop_box,
                    "window": WindowReference(
                        app="wechat",
                        target_uid=target_uid,
                        backend=get_window_profile("wechat").backend,
                        locator=window.window_text() or "wechat_window",
                        locator_status="resolved",
                    ),
                }
            )
        return probes

    @staticmethod
    def run_tesseract_ocr(
        image_path: Path,
        *,
        tesseract_cmd: str = "tesseract",
        languages: str = "chi_sim+eng",
        psm: int = 6,
    ) -> str:
        completed = subprocess.run(
            [
                tesseract_cmd,
                str(image_path),
                "stdout",
                "-l",
                languages,
                "--psm",
                str(psm),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout

    def send_message(self, app: str, target_uid: str | None, message: str) -> DriverActionResult:
        if app == "wechat" and getattr(self, "enable_live_wechat", False):  # pragma: no branch - simple switch
            window, metadata = self._send_wechat_message(target_uid, message)
            return DriverActionResult(
                driver="pywinauto",
                operation="send_message",
                status="sent",
                app=app,
                target_uid=target_uid,
                message=message,
                window=window,
                metadata={"backend": window.backend, **metadata},
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
        if (
            app == "wechat"
            and sys_platform == "win32"
            and getattr(self, "enable_live_wechat", False)
        ):  # pragma: no branch - Windows-only side effect
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
            status=(
                "sent"
                if app == "wechat" and sys_platform == "win32" and getattr(self, "enable_live_wechat", False)
                else "stubbed"
            ),
            app=app,
            target_uid=target_uid,
            window=window,
            metadata={"strategy": ["esc", "close_interference_popup"], "backend": window.backend},
        )
