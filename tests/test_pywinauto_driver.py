from autoin.adapters import MockWindowsDriver, build_windows_driver
from autoin.adapters.drivers import PywinautoUnavailableError
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
