# ============================================================
# 图片预览对话框 (可放大缩小 / 弹出新窗口 / 可拖拽)
# ============================================================
# 功能 (issue #9):
#   - 单击图片缩略图弹出全屏预览对话框
#   - 支持滚轮缩放 / 按钮缩放 / 双指捏合 (移动端)
#   - 支持拖拽移动图片
#   - 桌面端额外提供 "在新窗口打开" 按钮 (UrlLauncher)
#   - 使用 Flet 0.86 的 InteractiveViewer (内置手势支持, 移动端友好)
# ============================================================
from typing import Optional, Union
from pathlib import Path
import flet as ft
from flet import (
    Container, Column, Row, Text, Icon, Icons, Colors, FontWeight,
    MainAxisAlignment, CrossAxisAlignment, AlertDialog, OutlinedButton,
    Image, Slider, ControlEvent,
)
from utils.file_loader import image_to_base64, get_mime_type
from utils.dialog import show_dialog, pop_dialog


def show_image_preview_dialog(page: ft.Page, image_path: Union[str, Path],
                              title: str = "图片预览"):
    """
    弹出图片预览对话框 (用 InteractiveViewer 实现缩放+拖拽)
    - 桌面端可通过"在新窗口打开"按钮单独打开图片窗口
    """
    # 容错: 转 str (兼容 WindowsPath)
    if image_path is None:
        return
    img_path_str = str(image_path)

    b64 = image_to_base64(img_path_str)
    if not b64:
        from utils.dialog import show_snackbar
        show_snackbar(page, f"图片读取失败: {img_path_str}", is_error=True)
        return

    mime = get_mime_type(img_path_str)
    src = f"data:{mime};base64," + b64

    # 视图大小: 取窗口尺寸的 80% 或 800x600
    try:
        win_w = page.window.width or 1280
        win_h = page.window.height or 800
    except Exception:
        win_w, win_h = 1280, 800

    box_w = max(360, min(int(win_w * 0.8), 1100))
    box_h = max(320, min(int(win_h * 0.75), 720))
    img_h = box_h - 70  # 留出底部工具栏空间

    # InteractiveViewer 提供内置缩放/拖拽手势
    # min_scale/max_scale 设置缩放上下限; boundary_margin 让图片可以拖出视口
    viewer = ft.InteractiveViewer(
        min_scale=0.2,
        max_scale=8.0,
        boundary_margin=float("inf"),  # 允许拖出边界
        interaction_end_friction_coefficient=0.001,  # 立即停止惯性, >0 绕过flet校验
        clip_behavior=ft.ClipBehavior.NONE,
        content=Image(
            src=src,
            fit=ft.BoxFit.CONTAIN,
            width=box_w,
            height=img_h,
            gapless_playback=True,
        ),
    )

    # 程序控制缩放 (按钮 +/-)
    state = {"scale": 1.0}

    async def _reset(e=None):
        # InteractiveViewer 有异步 reset() 方法 (恢复初始 transform)
        try:
            await viewer.reset()
        except Exception as ex:
            print(f"[image_preview] reset 失败: {ex}")
        state["scale"] = 1.0

    # 在新窗口打开 (桌面端; 移动端用 launch_url file://)
    async def open_in_new_window(e=None):
        try:
            from utils.platform_helper import share_or_open_async
            await share_or_open_async(
                page, img_path_str, title="图片预览",
                open_in_browser=True,
            )
        except Exception as ex:
            from utils.dialog import show_snackbar
            show_snackbar(page, f"打开失败: {ex}", is_error=True)

    actions_row = Row(
        controls=[
            # OutlinedButton("复位", icon=Icons.CENTER_FOCUS_STRONG,
            #               on_click=lambda e: page.run_task(_reset)),
            # OutlinedButton("在新窗口打开", icon=Icons.OPEN_IN_NEW,
            #               on_click=lambda e: page.run_task(open_in_new_window)),
            # Container(expand=True),
            # Text("💡 滚轮缩放 / 双指捏合 / 拖拽移动",
            #      size=12, color=Colors.ON_SURFACE_VARIANT),
        ],
        spacing=8,
        alignment=MainAxisAlignment.SPACE_BETWEEN,
        # wrap=True,
    )

    dlg = AlertDialog(
        modal=True,
        title=Row([
            Icon(Icons.IMAGE, color=Colors.PRIMARY, size=22),
            Text(title, weight=FontWeight.W_600, size=18),
            Container(expand=True),
        ], spacing=8),
        content=Container(
            content=Column([
                Container(
                    content=viewer,
                    width=box_w,
                    height=img_h,
                    bgcolor=Colors.SURFACE_CONTAINER_HIGHEST,
                    border_radius=8,
                    padding=ft.Padding.all(4),
                ),
                actions_row,
            ], spacing=6, tight=True),
            width=box_w,
            padding=ft.Padding.all(4),
        ),
        actions=[
            ft.TextButton("关闭", on_click=lambda e: pop_dialog(page)),
        ],
        actions_alignment=MainAxisAlignment.END,
    )
    show_dialog(page, dlg)


# # ============================================================
# # 图片预览对话框 (可放大缩小 / 弹出新窗口 / 可拖拽)
# # ============================================================
# # 功能 (issue #9):
# #   - 单击图片缩略图弹出全屏预览对话框
# #   - 支持滚轮缩放 / 按钮缩放 / 双指捏合 (移动端)
# #   - 支持拖拽移动图片
# #   - 桌面端额外提供 "在新窗口打开" 按钮 (UrlLauncher)
# #   - 使用 Flet 0.86 的 InteractiveViewer (内置手势支持, 移动端友好)
# # ============================================================

# from typing import Optional, Union
# import flet as ft
# from flet import (
#     Container, Column, Row, Text, Icon, Icons, Colors, FontWeight,
#     MainAxisAlignment, CrossAxisAlignment, AlertDialog, OutlinedButton,
#     Image, Slider, ControlEvent,
# )
# from utils.file_loader import image_to_base64, get_mime_type
# from utils.dialog import show_dialog, pop_dialog


# def show_image_preview_dialog(page: ft.Page, image_path: Union[str, "ft.Path"],
#                               title: str = "图片预览"):
#     """
#     弹出图片预览对话框 (用 InteractiveViewer 实现缩放+拖拽)
#     - 桌面端可通过"在新窗口打开"按钮单独打开图片窗口
#     """
#     # 容错: 转 str (兼容 WindowsPath)
#     if image_path is not None and not isinstance(image_path, str):
#         image_path = str(image_path)

#     b64 = image_to_base64(image_path)
#     if not b64:
#         from utils.dialog import show_snackbar
#         show_snackbar(page, f"图片读取失败: {image_path}", is_error=True)
#         return

#     mime = get_mime_type(image_path)
#     src = f"data:{mime};base64," + b64

#     # 视图大小: 取窗口尺寸的 80% 或 800x600
#     try:
#         win_w = page.window.width or 1280
#         win_h = page.window.height or 800
#     except Exception:
#         win_w, win_h = 1280, 800
#     box_w = max(360, min(int(win_w * 0.8), 1100))
#     box_h = max(320, min(int(win_h * 0.75), 720))
#     img_h = box_h - 70  # 留出底部工具栏空间

#     # InteractiveViewer 提供内置缩放/拖拽手势
#     # min_scale/max_scale 设置缩放上下限; boundary_margin 让图片可以拖出视口
#     viewer = ft.InteractiveViewer(
#         min_scale=0.2,
#         max_scale=8.0,
#         boundary_margin=float("inf"),  # 允许拖出边界
#         interaction_end_friction_coefficient=0,  # 立即停止惯性
#         clip_behavior=ft.ClipBehavior.NONE,
#         content=Image(
#             src=src,
#             fit=ft.BoxFit.CONTAIN,
#             width=box_w,
#             height=img_h,
#             gapless_playback=True,
#         ),
#     )

#     # 程序控制缩放 (按钮 +/-)
#     state = {"scale": 1.0}

#     async def _reset(e=None):
#         # InteractiveViewer 有异步 reset() 方法 (恢复初始 transform)
#         try:
#             await viewer.reset()
#         except Exception as ex:
#             print(f"[image_preview] reset 失败: {ex}")
#         state["scale"] = 1.0

#     # 在新窗口打开 (桌面端; 移动端用 launch_url file://)
#     async def open_in_new_window(e=None):
#         try:
#             from utils.platform_helper import share_or_open_async
#             await share_or_open_async(
#                 page, image_path, title="图片预览",
#                 open_in_browser=True,
#             )
#         except Exception as ex:
#             from utils.dialog import show_snackbar
#             show_snackbar(page, f"打开失败: {ex}", is_error=True)

#     actions_row = Row(
#         controls=[
#             OutlinedButton("复位", icon=Icons.CENTER_FOCUS_STRONG,
#                             on_click=lambda e: page.run_task(_reset)),
#             OutlinedButton("在新窗口打开", icon=Icons.OPEN_IN_NEW,
#                             on_click=lambda e: page.run_task(open_in_new_window)),
#             Container(expand=True),
#             Text("💡 滚轮缩放 / 双指捏合 / 拖拽移动",
#                  size=12, color=Colors.ON_SURFACE_VARIANT),
#         ],
#         spacing=8,
#         alignment=MainAxisAlignment.SPACE_BETWEEN,
#         wrap=True,
#     )

#     dlg = AlertDialog(
#         modal=True,
#         title=Row([
#             Icon(Icons.IMAGE, color=Colors.PRIMARY, size=22),
#             Text(title, weight=FontWeight.W_600, size=18),
#             Container(expand=True),
#         ], spacing=8),
#         content=Container(
#             content=Column([
#                 Container(
#                     content=viewer,
#                     width=box_w,
#                     height=img_h,
#                     bgcolor=Colors.SURFACE_CONTAINER_HIGHEST,
#                     border_radius=8,
#                     padding=ft.Padding.all(4),
#                 ),
#                 actions_row,
#             ], spacing=6, tight=True),
#             width=box_w,
#             padding=ft.Padding.all(4),
#         ),
#         actions=[
#             ft.TextButton("关闭", on_click=lambda e: pop_dialog(page)),
#         ],
#         actions_alignment=MainAxisAlignment.END,
#     )
#     show_dialog(page, dlg)
