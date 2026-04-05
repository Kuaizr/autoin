from pathlib import Path
from sys import platform as sys_platform

from autoin.adapters import MockWindowsDriver, build_windows_driver
from autoin.adapters.drivers import DriverActionResult, PywinautoUnavailableError, get_window_profile
from autoin.adapters.drivers.pywinauto_driver import PywinautoDriver


def test_build_windows_driver_defaults_to_mock() -> None:
    driver = build_windows_driver(prefer_pywinauto=False)
    assert isinstance(driver, MockWindowsDriver)


def test_build_windows_driver_falls_back_when_pywinauto_unavailable() -> None:
    driver = build_windows_driver(prefer_pywinauto=True)
    if sys_platform == "win32":
        assert isinstance(driver, PywinautoDriver | MockWindowsDriver)
    else:
        assert isinstance(driver, MockWindowsDriver)


def test_pywinauto_driver_raises_on_non_windows_hosts() -> None:
    if sys_platform == "win32":
        driver = PywinautoDriver()
        assert isinstance(driver, PywinautoDriver)
    else:
        try:
            PywinautoDriver()
        except PywinautoUnavailableError:
            pass
        else:
            raise AssertionError("Expected PywinautoDriver to reject non-Windows hosts in this environment.")


def test_mock_windows_driver_returns_structured_result() -> None:
    driver = MockWindowsDriver()

    result = driver.capture_window(app="wechat", target_uid="wechat_u1", mode="focused_window")

    assert isinstance(result, DriverActionResult)
    assert result.status == "mocked"
    assert result.window is not None
    assert result.window.locator == "wechat_u1"


def test_pywinauto_driver_builds_artifact_path_from_contract() -> None:
    driver = object.__new__(PywinautoDriver)
    driver.artifact_root = Path("artifacts") / "windows"
    driver.enable_live_wechat = False

    artifact_path = driver.build_capture_artifact_path(
        app="xiaohongshu",
        target_uid="xiaohongshu/u1",
        mode="fullscreen",
    )

    assert artifact_path.parent == Path("artifacts") / "windows" / "xiaohongshu" / "fullscreen"
    assert artifact_path.name.startswith("xiaohongshu_xiaohongshu_u1_fullscreen_")
    assert artifact_path.suffix == ".png"


def test_pywinauto_driver_returns_stubbed_window_resolution() -> None:
    driver = object.__new__(PywinautoDriver)
    driver.artifact_root = Path("artifacts") / "windows"
    driver.enable_live_wechat = False

    window = driver.resolve_window(app="douyin", target_uid="douyin_u2")

    assert window.app == "douyin"
    assert window.target_uid == "douyin_u2"
    assert window.locator_status == "stubbed"
    assert window.backend == "uia"


def test_pywinauto_driver_exposes_stubbed_rollback_contract() -> None:
    driver = object.__new__(PywinautoDriver)
    driver.artifact_root = Path("artifacts") / "windows"
    driver.enable_live_wechat = False

    result = driver.rollback_ui(app="wechat", target_uid="wechat_u3")

    assert result.operation == "rollback_ui"
    assert result.status == "stubbed"
    assert result.metadata["strategy"] == ["esc", "close_interference_popup"]


def test_open_wechat_search_and_select_target_exits_search_mode(monkeypatch) -> None:
    driver = object.__new__(PywinautoDriver)
    driver.artifact_root = Path("artifacts") / "windows"
    driver.enable_live_wechat = False
    calls: list[str] = []
    clipboard_values: list[str] = []

    monkeypatch.setattr(driver, "_send_wechat_keys", lambda keys: calls.append(keys))
    monkeypatch.setattr(driver, "_set_windows_clipboard_text", lambda text: clipboard_values.append(text))
    monkeypatch.setattr("autoin.adapters.drivers.pywinauto_driver.time.sleep", lambda _: None)

    driver._open_wechat_search_and_select_target("文件传输助手")

    assert clipboard_values == ["文件传输助手"]
    assert calls == ["^f", "^v", "{ENTER}", "{ESC}"]


def test_window_profile_catalog_exposes_platform_hints() -> None:
    profile = get_window_profile("wechat")

    assert profile.process_candidates == ["WeChat.exe"]
    assert "微信" in profile.title_patterns
    assert profile.default_capture_mode == "main_window"


def test_unknown_window_profile_falls_back_to_generic_contract() -> None:
    profile = get_window_profile("custom_app")

    assert profile.app == "custom_app"
    assert profile.title_patterns == ["custom_app"]
    assert profile.default_capture_mode == "main_window"
