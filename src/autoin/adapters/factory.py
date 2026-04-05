from __future__ import annotations

from autoin.adapters.actions import ActionRegistry, build_default_action_registry
from autoin.adapters.drivers import (
    DesktopDriver,
    MockWindowsDriver,
    PywinautoDriver,
    PywinautoUnavailableError,
)
from autoin.adapters.platforms import (
    build_douyin_action_registry,
    build_wechat_action_registry,
    build_xiaohongshu_action_registry,
    build_xianyu_action_registry,
)
from autoin.adapters.runtime import ExecutorAdapter
from autoin.infrastructure.broker import RedisBroker
from autoin.infrastructure.lock_manager import RedisLockManager
from autoin.infrastructure.models import Platform


def build_windows_driver(prefer_pywinauto: bool = False) -> DesktopDriver:
    if prefer_pywinauto:
        try:
            return PywinautoDriver()
        except PywinautoUnavailableError:
            return MockWindowsDriver()
    return MockWindowsDriver()


def build_platform_action_registry(platform: Platform, driver: DesktopDriver | None = None) -> ActionRegistry:
    selected_driver = driver or build_windows_driver(prefer_pywinauto=False)
    if platform == Platform.WECHAT:
        return build_wechat_action_registry(driver=selected_driver)
    if platform == Platform.XIAOHONGSHU:
        return build_xiaohongshu_action_registry(driver=selected_driver)
    if platform == Platform.DOUYIN:
        return build_douyin_action_registry(driver=selected_driver)
    if platform == Platform.XIANYU:
        return build_xianyu_action_registry(driver=selected_driver)
    return build_default_action_registry()


def build_executor_adapter(
    adapter_name: str,
    platform_name: Platform,
    broker: RedisBroker,
    lock_manager: RedisLockManager,
    driver: DesktopDriver | None = None,
    prefer_pywinauto: bool = False,
) -> ExecutorAdapter:
    selected_driver = driver or build_windows_driver(prefer_pywinauto=prefer_pywinauto)
    return ExecutorAdapter(
        adapter_name=adapter_name,
        platform_name=platform_name,
        broker=broker,
        lock_manager=lock_manager,
        action_registry=build_platform_action_registry(
            platform_name,
            driver=selected_driver,
        ),
        rollback_handler=lambda: selected_driver.rollback_ui(platform_name.value),
    )
