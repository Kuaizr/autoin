from __future__ import annotations

from autoin.adapters.actions import ActionRegistry, build_default_action_registry
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


def build_platform_action_registry(platform: Platform) -> ActionRegistry:
    if platform == Platform.WECHAT:
        return build_wechat_action_registry()
    if platform == Platform.XIAOHONGSHU:
        return build_xiaohongshu_action_registry()
    if platform == Platform.DOUYIN:
        return build_douyin_action_registry()
    if platform == Platform.XIANYU:
        return build_xianyu_action_registry()
    return build_default_action_registry()


def build_executor_adapter(
    adapter_name: str,
    platform_name: Platform,
    broker: RedisBroker,
    lock_manager: RedisLockManager,
) -> ExecutorAdapter:
    return ExecutorAdapter(
        adapter_name=adapter_name,
        platform_name=platform_name,
        broker=broker,
        lock_manager=lock_manager,
        action_registry=build_platform_action_registry(platform_name),
    )
