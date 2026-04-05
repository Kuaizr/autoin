from __future__ import annotations

from pydantic import BaseModel, Field


class WindowProfile(BaseModel):
    """Static window matching hints for a desktop application."""

    app: str
    backend: str = "uia"
    process_candidates: list[str] = Field(default_factory=list)
    title_patterns: list[str] = Field(default_factory=list)
    default_capture_mode: str


WINDOW_PROFILES: dict[str, WindowProfile] = {
    "wechat": WindowProfile(
        app="wechat",
        process_candidates=["WeChat.exe"],
        title_patterns=["微信", "WeChat"],
        default_capture_mode="main_window",
    ),
    "xiaohongshu": WindowProfile(
        app="xiaohongshu",
        process_candidates=["XiaoHongShu.exe"],
        title_patterns=["小红书"],
        default_capture_mode="fullscreen",
    ),
    "douyin": WindowProfile(
        app="douyin",
        process_candidates=["Douyin.exe", "Chrome.exe", "msedge.exe"],
        title_patterns=["抖音", "Douyin"],
        default_capture_mode="focused_window",
    ),
    "xianyu": WindowProfile(
        app="xianyu",
        process_candidates=["Xianyu.exe", "Chrome.exe", "msedge.exe"],
        title_patterns=["闲鱼"],
        default_capture_mode="conversation_panel",
    ),
}


def get_window_profile(app: str) -> WindowProfile:
    return WINDOW_PROFILES.get(
        app,
        WindowProfile(
            app=app,
            process_candidates=[],
            title_patterns=[app],
            default_capture_mode="main_window",
        ),
    )
