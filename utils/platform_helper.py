# ============================================================
# 平台检测 + 跨平台分享/打开工具
# ============================================================
# 说明：
#   - 桌面端 (Windows/macOS/Linux): 文件保存到本地, 通过 UrlLauncher.launch_url
#     打开文件夹/文件 (使用 file:/// 协议或 folder 协议)
#   - 移动端 (iOS/Android): 文件保存到 app 沙盒或共享目录, 通过 Share.share_files
#     调起系统分享面板 (微信/QQ/邮件/AirDrop 等)
#   - Web 端: 触发浏览器下载 (用 AnchorElement + download 属性)
# ============================================================

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, Union

import flet as ft


def is_mobile(page: ft.Page) -> bool:
    """是否移动端 (iOS/Android)"""
    try:
        return bool(page.platform and page.platform.is_mobile())
    except Exception:
        return False


def is_desktop(page: ft.Page) -> bool:
    """是否桌面端 (Windows/macOS/Linux)"""
    try:
        return bool(page.platform and page.platform.is_desktop())
    except Exception:
        # 后备: sys.platform 判断
        return sys.platform in ("win32", "darwin", "linux")


def is_web(page: ft.Page) -> bool:
    """是否 Web 端"""
    try:
        return bool(page.web)
    except Exception:
        return False


def is_windows() -> bool:
    """当前 Python 进程是否在 Windows 上 (用于路径分隔符等)"""
    return sys.platform == "win32"


def is_android() -> bool:
    """当前 Python 进程是否在 Android 上"""
    # 与 config._is_android() 保持一致
    return (
        "P4A_BOOTSTRAP" in os.environ
        or "ANDROID_ARGUMENT" in os.environ
        or "ANDROID_PRIVATE" in os.environ
        or getattr(sys, "android_api_level", None) is not None
    )


def to_file_uri(path: Union[str, Path]) -> str:
    """
    把本地路径转成 file:// URI (供浏览器/UrlLauncher 使用)
    - Windows: file:///C:/Users/...  (3 个斜杠)
    - Unix:    file:///home/...
    """
    p = str(path).replace("\\", "/")
    if not p.startswith("/"):
        p = "/" + p
    return f"file://{p}"


def get_default_export_dir() -> str:
    """
    获取默认导出目录
    - 桌面: ~/Desktop 或 ~/Documents 或 ~
    - 移动: app 沙盒内的 export/ 目录 (config.EXPORT_DIR)
    """
    if is_android():
        try:
            from config import EXPORT_DIR
            return str(EXPORT_DIR)
        except Exception:
            pass
    home = Path.home()
    candidates = [home / "Desktop", home / "桌面", home / "Documents", home]
    for c in candidates:
        try:
            if c.exists():
                return str(c)
        except Exception:
            continue
    return str(home)


def show_in_folder(page: ft.Page, file_path: Union[str, Path]):
    """
    在系统文件管理器中定位到指定文件 (桌面端)
    - Windows: explorer.exe /select,"<path>"
    - macOS:   open -R "<path>"
    - Linux:   xdg-open "<parent_dir>"
    - Android: 不支持, 自动调用 share_file_async 让用户分享
    """
    p = str(file_path)
    parent = os.path.dirname(p) or "."
    if is_android():
        # Android 无文件管理器统一入口, 走分享面板
        try:
            import asyncio
            page.run_task(share_file_async, page, p, title="已导出文件")
        except Exception:
            pass
        return
    try:
        if is_windows():
            import subprocess
            subprocess.Popen(["explorer.exe", "/select,", p], close_fds=True)
        elif sys.platform == "darwin":
            import subprocess
            subprocess.Popen(["open", "-R", p], close_fds=True)
        else:
            import subprocess
            subprocess.Popen(["xdg-open", parent], close_fds=True)
    except Exception as e:
        print(f"[platform_helper] show_in_folder 失败: {e}")
        # 退而求其次: 用浏览器打开父目录
        try:
            import asyncio
            from flet.controls.services.url_launcher import UrlLauncher, LaunchMode

            async def _open():
                await UrlLauncher().launch_url(
                    to_file_uri(parent),
                    mode=LaunchMode.EXTERNAL_APPLICATION,
                )
            page.run_task(_open)
        except Exception:
            pass


async def share_file_async(page: ft.Page, file_path: Union[str, Path],
                           title: str = "分享文件",
                           subject: Optional[str] = None,
                           text: Optional[str] = None) -> bool:
    """
    调起系统分享面板分享单个文件 (移动端可用, 调起微信/QQ/AirDrop 等)
    :return: True=已发起分享, False=平台不支持
    """
    p = str(file_path)
    if not os.path.exists(p):
        print(f"[platform_helper] 分享失败: 文件不存在 {p}")
        return False
    try:
        from flet.controls.services.share import Share, ShareFile
        share = Share()
        await share.share_files(
            files=[ShareFile.from_path(p)],
            title=title,
            subject=subject,
            text=text,
        )
        return True
    except Exception as e:
        print(f"[platform_helper] share_files 失败: {e}")
        return False


def open_file_with_system(file_path: Union[str, Path]) -> bool:
    """
    用系统默认程序打开本地文件 (桌面端)
    - Windows: os.startfile
    - macOS:   open
    - Linux:   xdg-open
    - Android: 不支持, 返回 False 让上层走分享面板
    返回 True=已发起, False=失败
    """
    p = str(file_path)
    if not os.path.exists(p):
        print(f"[platform_helper] open_file_with_system: 文件不存在 {p}")
        return False
    if is_android():
        # Android 无"用默认程序打开"通用入口
        return False
    try:
        if is_windows():
            os.startfile(p)  # type: ignore[attr-defined]
            return True
        elif sys.platform == "darwin":
            import subprocess
            subprocess.Popen(["open", p], close_fds=True)
            return True
        else:
            import subprocess
            subprocess.Popen(["xdg-open", p], close_fds=True)
            return True
    except Exception as e:
        print(f"[platform_helper] open_file_with_system 失败: {e}")
        return False


async def open_in_app_webview_async(page: ft.Page, url: str,
                                     title: Optional[str] = None) -> bool:
    """
    在 app 内 WebView 中打开 URL (移动端推荐)
    注意: IN_APP_WEB_VIEW 模式仅支持 http(s) URL;
    若传入 file:// URL 会改用系统默认浏览器打开
    :return: True=已发起, False=平台不支持
    """
    if url.startswith("file://"):
        path = url[len("file://"):]
        if is_windows() and path.startswith("/") and len(path) > 2 and path[2] == ":":
            path = path[1:].replace("/", "\\")
        if is_android():
            # Android 不能用 file:// 给 webview, 退回分享
            return await share_file_async(page, path, title=title or "已导出文件")
        return open_file_with_system(path)

    try:
        from flet.controls.services.url_launcher import (
            UrlLauncher, LaunchMode, WebViewConfiguration,
        )
        await UrlLauncher().launch_url(
            url,
            mode=LaunchMode.IN_APP_WEB_VIEW,
            web_view_configuration=WebViewConfiguration(enable_javascript=True),
        )
        return True
    except Exception as e:
        print(f"[platform_helper] in-app webview 失败: {e}")
        try:
            from flet.controls.services.url_launcher import UrlLauncher, LaunchMode
            await UrlLauncher().launch_url(
                url, mode=LaunchMode.EXTERNAL_APPLICATION,
            )
            return True
        except Exception as e2:
            print(f"[platform_helper] fallback launch_url 失败: {e2}")
            return False


async def share_or_open_async(page: ft.Page, file_path: Union[str, Path],
                               title: str = "已导出文件",
                               open_in_browser: bool = False) -> bool:
    """
    智能分享/打开:
    - 移动端: 调起系统分享面板
    - 桌面端: 在文件管理器中定位文件 (或浏览器打开)
    - Web 端: 退回 file:// 打开
    :param open_in_browser: True 则桌面端尝试用浏览器打开 HTML
    """
    p = str(file_path)
    if is_mobile(page):
        return await share_file_async(page, p, title=title)
    elif is_web(page):
        return await share_file_async(page, p, title=title)
    else:
        # 桌面端
        if open_in_browser:
            if open_file_with_system(p):
                return True
            show_in_folder(page, p)
            return True
        else:
            show_in_folder(page, p)
            return True
