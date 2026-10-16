# ============================================================
# 主入口 - 基于生成式 AI 的个性化错题本与变式训练系统
# ============================================================
# 说明：
#   本文件是 Flet 应用的入口
#   - 自适应布局 (桌面 NavigationRail / 移动 NavigationBar)
#   - Material 3 主题 (科技紫蓝主色调)
#   - 亮色/暗色模式切换
#   - 5 个主页面 (首页复习 / 错题库 / 添加错题 / 导出试卷 / 设置)
# ============================================================

import sys
import os

# 确保项目根目录在 sys.path 中 (便于绝对导入)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import flet as ft
from flet import Page

# 导入应用主类
from app import MistakeNotebookApp


def main(page: Page):
    """Flet 应用入口"""
    # 启动日志: 记录代码版本与启动时间 (用于确认运行的是哪份代码)
    try:
        from utils.run_guard import debug_log
        from config import APP_VERSION
        debug_log(f"[boot] 应用启动 v{APP_VERSION} (pid={os.getpid()})")
    except Exception:
        pass

    app = MistakeNotebookApp(page)
    app.build()

    def _on_error(e):
        """全局错误兜底: 显示错误而不是静默卡住"""
        try:
            import traceback
            traceback.print_exc()
            msg = str(getattr(e, "data", None) or e)[:200]
            page.show_dialog(
                ft.SnackBar(
                    content=ft.Text(f"发生错误: {msg}", color=ft.Colors.ON_SURFACE),
                    bgcolor=ft.Colors.ERROR_CONTAINER,
                )
            )
        except Exception:
            pass

    page.on_error = _on_error



if __name__ == "__main__":
    # 启动 Flet 应用
    # 桌面端：会弹出窗口
    # 移动端：可通过 flet pack 打包
    # 注: Flet 0.86+ 推荐使用 ft.run() 替代 ft.app()
    #      ft.run 的第一个参数是位置参数 (main), 不是 target=
    try:
        ft.run(main)
    except (AttributeError, TypeError):
        # 兼容旧版 Flet (0.86 之前): ft.app(target=...) 作为函数存在时才使用
        _legacy_app = getattr(ft, "app", None)
        if callable(_legacy_app):
            _legacy_app(target=main)
        else:
            raise

    # 如需指定 web 模式 (浏览器):
    # ft.run(main, view=ft.AppView.WEB_BROWSER, port=8080)
