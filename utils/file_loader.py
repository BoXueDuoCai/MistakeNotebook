# ============================================================
# 文件加载工具 - 处理 Flet 0.86 中本地图片加载
# ============================================================
# 关键问题：
#   Flet 0.86 中 Image.src 仅支持：
#     1. http/https URL
#     2. assets 目录下相对路径
#   不支持本地磁盘绝对路径 (如 /home/user/xxx.png 或 C:\xxx.png)
#   也不支持 ?t= 查询串
#
# 解决方案：本地图片 → base64 → Image.src_base64
# ============================================================

import base64
import os
from pathlib import Path
from typing import Optional, Union

import flet as ft


def image_to_base64(image_path: Union[str, Path]) -> Optional[str]:
    """
    将本地图片文件转为 base64 字符串
    :param image_path: 图片路径 (str 或 pathlib.Path 均可)
    :return: base64 字符串 (不含 data: 前缀)，失败返回 None
    """
    # 容错：Flet FilePicker 在桌面端会返回 WindowsPath/PosixPath 对象,
    # 直接传给字符串函数 (如 .lower()) 会触发 AttributeError
    if image_path is None:
        return None
    if not isinstance(image_path, str):
        image_path = str(image_path)
    if not os.path.exists(image_path):
        return None
    try:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except (IOError, OSError) as e:
        print(f"[file_loader] 读取图片失败 {image_path}: {e}")
        return None


def get_mime_type(image_path: Union[str, Path]) -> str:
    """根据扩展名推断 MIME (兼容 str / pathlib.Path)"""
    if not image_path:
        return "image/png"
    # 关键修复: 先转 str 再 lower, 避免 'WindowsPath' object has no attribute 'lower'
    s = str(image_path).lower()
    ext = s.split(".")[-1] if "." in s else ""
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "webp": "image/webp",
        "bmp": "image/bmp",
    }.get(ext, "image/png")


def build_image_src(image_path: str) -> Optional[str]:
    """
    构建适合 Flet Image.src_base64 的字符串
    :return: base64 编码字符串
    """
    return image_to_base64(image_path)


def build_image_src_with_mime(image_path: str) -> Optional[str]:
    """
    构建 data URL 形式 (部分控件可能需要)
    """
    b64 = image_to_base64(image_path)
    if not b64:
        return None
    mime = get_mime_type(image_path)
    return f"data:{mime};base64,{b64}"


def create_image_control(image_path: str,
                         width: Optional[int] = None,
                         height: Optional[int] = None,
                         fit: ft.BoxFit = ft.BoxFit.CONTAIN,
                         border_radius: Optional[int] = None,
                         visible: bool = True) -> Optional[ft.Image]:
    """
    从本地图片路径创建 Flet Image 控件
    Flet 0.86 中 Image.src 接受 data URL (base64)
    """
    src = build_image_src_with_mime(image_path)
    if not src:
        return None
    return ft.Image(
        src=src,
        fit=fit,
        width=width,
        height=height,
        border_radius=border_radius,
        visible=visible,
        gapless_playback=True,
    )


def build_image_src_for_flet(image_path: str) -> Optional[str]:
    """
    构建可直接传给 Image.src 的字符串 (data URL 形式)
    用于动态更新已有 Image 控件的 src 属性
    """
    return build_image_src_with_mime(image_path)


def sanitize_filename(name: str, replacement: str = "_") -> str:
    """
    文件名消毒：替换非法字符
    防止 Windows/Mac/Linux 文件名限制
    """
    if not name:
        return "untitled"
    # Windows: \ / : * ? " < > |
    # Mac/Linux: / 和 null
    illegal = r'\/:*?"<>|'
    for ch in illegal:
        name = name.replace(ch, replacement)
    # 去除首尾空格和点
    name = name.strip().strip(".")
    # 限制长度
    if len(name) > 200:
        name = name[:200]
    return name or "untitled"
