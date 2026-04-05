from autoin.adapters.platforms.wechat import WechatActionHandler, build_wechat_action_registry
from autoin.adapters.platforms.xiaohongshu import (
    XiaohongshuActionHandler,
    build_xiaohongshu_action_registry,
)

__all__ = [
    "WechatActionHandler",
    "XiaohongshuActionHandler",
    "build_wechat_action_registry",
    "build_xiaohongshu_action_registry",
]
