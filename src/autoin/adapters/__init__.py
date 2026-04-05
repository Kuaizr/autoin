from autoin.adapters.actions import ActionRegistry, UnknownActionError, build_default_action_registry
from autoin.adapters.base import BaseAdapter
from autoin.adapters.directory import AdapterDirectory, UnsupportedAdapterActionError
from autoin.adapters.drivers import (
    DesktopAutomationError,
    DesktopDriver,
    DriverActionResult,
    MockWindowsDriver,
    PywinautoDriver,
    PywinautoUnavailableError,
    WindowProfile,
    WindowReference,
    get_window_profile,
)
from autoin.adapters.factory import build_executor_adapter, build_platform_action_registry, build_windows_driver
from autoin.adapters.platforms import (
    DouyinActionHandler,
    WechatActionHandler,
    XiaohongshuActionHandler,
    XianyuActionHandler,
    build_douyin_action_registry,
    build_wechat_action_registry,
    build_xiaohongshu_action_registry,
    build_xianyu_action_registry,
)
from autoin.adapters.runtime import ExecutorAdapter, FailureHandler, ObserverAdapter, SuccessHandler, TaskWorker

__all__ = [
    "ActionRegistry",
    "AdapterDirectory",
    "BaseAdapter",
    "DesktopAutomationError",
    "DesktopDriver",
    "DriverActionResult",
    "ExecutorAdapter",
    "FailureHandler",
    "MockWindowsDriver",
    "ObserverAdapter",
    "PywinautoDriver",
    "PywinautoUnavailableError",
    "SuccessHandler",
    "TaskWorker",
    "UnknownActionError",
    "UnsupportedAdapterActionError",
    "build_executor_adapter",
    "build_default_action_registry",
    "build_platform_action_registry",
    "build_windows_driver",
    "DouyinActionHandler",
    "WechatActionHandler",
    "WindowProfile",
    "WindowReference",
    "XiaohongshuActionHandler",
    "XianyuActionHandler",
    "build_douyin_action_registry",
    "build_wechat_action_registry",
    "build_xiaohongshu_action_registry",
    "build_xianyu_action_registry",
    "get_window_profile",
]
