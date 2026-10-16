# ============================================================
# FilePicker 辅助工具 (Flet 0.86 正确用法)
# ============================================================
# 官方文档 (https://flet.dev/docs/services/filepicker):
#   files = await ft.FilePicker().pick_files(allow_multiple=True)
#
# 关键点：
#   1. FilePicker 是 Service 控件，**不需要** page.overlay.append
#   2. 每次直接 new 一个实例并调用方法即可
#   3. handler 必须是 async (因为 pick_files 是 coroutine)
#   4. 不要复用实例 (会导致 Session closed)
# ============================================================

import flet as ft
from typing import Optional


async def pick_files_async(page: ft.Page,
                            dialog_title: str = "选择文件",
                            allowed_extensions: Optional[list] = None,
                            allow_multiple: bool = False,
                            file_type: ft.FilePickerFileType = ft.FilePickerFileType.IMAGE):
    """
    异步选择文件 (Flet 0.86 官方推荐用法)
    每次创建新 FilePicker 实例，调用 pick_files
    :return: list[FilePickerFile] 或 None
    """
    try:
        fp = ft.FilePicker()
        files = await fp.pick_files(
            dialog_title=dialog_title,
            allow_multiple=allow_multiple,
            allowed_extensions=allowed_extensions,
            file_type=file_type,
        )
        return files
    except Exception as e:
        print(f"[file_picker_helper] pick_files 失败: {e}")
        return None


async def get_directory_path_async(page: ft.Page,
                                    dialog_title: str = "选择目录",
                                    initial_directory: str = ""):
    """
    异步选择目录 (Flet 0.86 官方推荐用法)
    :return: 目录路径字符串 或 None
    """
    try:
        fp = ft.FilePicker()
        path = await fp.get_directory_path(
            dialog_title=dialog_title,
            initial_directory=initial_directory or None,
        )
        return path
    except Exception as e:
        print(f"[file_picker_helper] get_directory_path 失败: {e}")
        return None


async def save_file_async(page: ft.Page,
                           dialog_title: str = "保存文件",
                           file_name: str = "",
                           initial_directory: str = "",
                           allowed_extensions: Optional[list] = None):
    """
    异步保存文件对话框 (Flet 0.86.5: save_file 原生支持 initial_directory)
    :return: 文件路径字符串 或 None
    """
    try:
        fp = ft.FilePicker()
        path = await fp.save_file(
            dialog_title=dialog_title,
            file_name=file_name,
            initial_directory=initial_directory or None,
            allowed_extensions=allowed_extensions,
        )
        return path
    except Exception as e:
        print(f"[file_picker_helper] save_file 失败: {e}")
        return None
