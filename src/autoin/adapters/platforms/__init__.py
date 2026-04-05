from autoin.adapters.platforms.douyin import DouyinActionHandler, build_douyin_action_registry
from autoin.adapters.platforms.wechat import WechatActionHandler, build_wechat_action_registry
from autoin.adapters.platforms.xiaohongshu import (
    XiaohongshuActionHandler,
    build_xiaohongshu_action_registry,
)
from autoin.adapters.platforms.xianyu import XianyuActionHandler, build_xianyu_action_registry

__all__ = [
    "DouyinActionHandler",
    "WechatActionHandler",
    "XiaohongshuActionHandler",
    "XianyuActionHandler",
    "build_douyin_action_registry",
    "build_wechat_action_registry",
    "build_xiaohongshu_action_registry",
    "build_xianyu_action_registry",
]
