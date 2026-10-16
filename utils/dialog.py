# ============================================================
# 对话框工具 - 统一 show_dialog / pop_dialog / snackbar
# + 后台线程执行工具 (修复 run_task 协程问题)
# ============================================================
# Flet 0.86 API:
#   - page.show_dialog(dlg) 显示 DialogControl
#   - page.pop_dialog() 弹出当前对话框
#   - page.run_thread(sync_fn) 在后台线程执行同步函数 (不需协程)
#   - page.run_task(async_fn) 在事件循环执行协程 (必须 async def)
#
# 关键修复：
#   - run_ui_update(page, fn): 在主线程执行同步 UI 更新
#     (替代之前错误的 page.run_task(sync_fn) 调用)
# ============================================================

import flet as ft
from typing import Optional, Callable


def show_dialog(page: ft.Page, dlg: ft.DialogControl) -> None:
    """显示对话框 (AlertDialog / SnackBar 均可)"""
    page.show_dialog(dlg)


def pop_dialog(page: ft.Page) -> Optional[ft.DialogControl]:
    """关闭最上层对话框"""
    return page.pop_dialog()


def show_snackbar(page: ft.Page, msg: str,
                  is_error: bool = False,
                  duration: int = 3000) -> None:
    """显示 SnackBar 提示"""
    snack = ft.SnackBar(
        content=ft.Text(msg, color=ft.Colors.ON_SURFACE),
        bgcolor=(ft.Colors.ERROR_CONTAINER if is_error
                 else ft.Colors.PRIMARY_CONTAINER),
        duration=duration,
    )
    page.show_dialog(snack)


def show_alert_dialog(page: ft.Page, title: str, content,
                      actions: Optional[list] = None,
                      on_close=None) -> ft.AlertDialog:
    """快捷创建并显示 AlertDialog"""
    if isinstance(content, str):
        content = ft.Text(content)

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text(title, weight=ft.FontWeight.W_600),
        content=content if isinstance(content, ft.Control) else ft.Container(content=content),
        actions=actions or [ft.TextButton("关闭", on_click=lambda e: pop_dialog(page))],
        actions_alignment=ft.MainAxisAlignment.END,
        on_dismiss=on_close,
    )
    page.show_dialog(dlg)
    return dlg


def show_confirm_dialog(page: ft.Page, title: str, message: str,
                         on_confirm, confirm_text: str = "确认",
                         cancel_text: str = "取消",
                         is_danger: bool = False) -> ft.AlertDialog:
    """确认对话框 (回调式)"""
    def do_confirm(e):
        pop_dialog(page)
        if callable(on_confirm):
            on_confirm()

    def do_cancel(e):
        pop_dialog(page)

    confirm_btn = ft.TextButton(
        confirm_text,
        on_click=do_confirm,
        style=ft.ButtonStyle(
            color=ft.Colors.ERROR if is_danger else ft.Colors.PRIMARY,
        ),
    )
    cancel_btn = ft.TextButton(cancel_text, on_click=do_cancel)

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text(title, weight=ft.FontWeight.W_600),
        content=ft.Text(message),
        actions=[cancel_btn, confirm_btn],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dlg)
    return dlg


# -------------------- 后台执行 + UI 更新工具 --------------------
def run_in_background(page: ft.Page, task_fn: Callable,
                       on_success: Optional[Callable] = None,
                       on_error: Optional[Callable] = None):
    """
    在后台线程执行同步任务，完成后在主线程更新 UI
    - task_fn: 同步函数 (在后台线程执行，如 LLM 调用、文件导出)
    - on_success(result): 主线程回调，参数为 task_fn 的返回值
    - on_error(error): 主线程回调，参数为 Exception

    注意：on_success/on_error 必须是同步函数 (因为 run_thread 会调用它们)
    """
    def _worker():
        try:
            result = task_fn()
            if on_success:
                # 在主线程执行回调 (用 run_thread 在主线程执行同步函数)
                page.run_thread(lambda: on_success(result))
        except Exception as ex:
            print(f"[background] 任务失败: {ex}")
            if on_error:
                page.run_thread(lambda e=ex: on_error(e))

    page.run_thread(_worker)


def run_ui_callback(page: ft.Page, callback: Callable, *args, **kwargs):
    """
    在主线程执行同步 UI 更新回调 (替代错误的 page.run_task(sync_fn))
    """
    def _run():
        callback(*args, **kwargs)
    page.run_thread(_run)
