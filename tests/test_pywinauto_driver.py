from pathlib import Path

from autoin.adapters import MockWindowsDriver, build_windows_driver
from autoin.adapters.drivers import DriverActionResult, PywinautoUnavailableError
from autoin.adapters.drivers.pywinauto_driver import PywinautoDriver


def test_build_windows_driver_defaults_to_mock() -> None:
    driver = build_windows_driver(prefer_pywinauto=False)
    assert isinstance(driver, MockWindowsDriver)


def test_build_windows_driver_falls_back_when_pywinauto_unavailable() -> None:
    driver = build_windows_driver(prefer_pywinauto=True)
    assert isinstance(driver, MockWindowsDriver)


def test_pywinauto_driver_raises_on_non_windows_hosts() -> None:
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

    window = driver.resolve_window(app="douyin", target_uid="douyin_u2")

    assert window.app == "douyin"
    assert window.target_uid == "douyin_u2"
    assert window.locator_status == "stubbed"
