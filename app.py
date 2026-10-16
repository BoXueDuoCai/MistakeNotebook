# ============================================================
# 应用主类 - 自适应布局与页面路由
# ============================================================
# 设计要点：
#   1. AppBar 图标用 on_surface 色 (亮暗模式都可见)
#   2. 字号统一略大 (标题 24, 正文 15)
#   3. 视图缓存：add/export/settings 保留表单状态
#   4. 字体设置应用：通过 theme 字段
# ============================================================

from typing import Dict, Optional

import flet as ft
from flet import (
    Page, Control, NavigationRail, NavigationRailDestination,
    NavigationBar, NavigationBarDestination, Column, Row, Container,
    Icon, Text, Icons, Colors, ThemeMode,
)

from config import APP_NAME, APP_SUBTITLE
from utils.theme import build_theme
from utils.dialog import pop_dialog, show_alert_dialog
from services.storage_service import SettingsService


class MistakeNotebookApp:
    """错题本应用主类"""

    NAV_ITEMS = [
        {"icon": Icons.HOME_OUTLINED, "selected_icon": Icons.HOME,
         "label": "首页", "key": "home"},
        {"icon": Icons.LIBRARY_BOOKS_OUTLINED, "selected_icon": Icons.LIBRARY_BOOKS,
         "label": "错题库", "key": "library"},
        {"icon": Icons.ADD_CIRCLE_OUTLINED, "selected_icon": Icons.ADD_CIRCLE,
         "label": "添加错题", "key": "add"},
        {"icon": Icons.FILE_DOWNLOAD_OUTLINED, "selected_icon": Icons.FILE_DOWNLOAD,
         "label": "导出试卷", "key": "export"},
        {"icon": Icons.SETTINGS_OUTLINED, "selected_icon": Icons.SETTINGS,
         "label": "设置", "key": "settings"},
    ]

    MOBILE_BREAKPOINT = 720
    CACHED_VIEWS = {"add", "export", "settings"}

    def __init__(self, page: Page):
        self.page = page
        self.settings = SettingsService.load()
        self.current_route = "home"
        self._view_instances: Dict[str, object] = {}
        self.content_area = Container(expand=True)
        self.nav_rail: Optional[NavigationRail] = None
        self.nav_bar: Optional[NavigationBar] = None
        self.app_bar_title = Text(APP_NAME, size=24, weight=ft.FontWeight.W_700)

    # -------------------- 应用构建 --------------------
    def build(self):
        self.page.title = APP_NAME
        try:
            # 仅在窗口尺寸未由平台提供时设置默认桌面尺寸 (移动端保持系统尺寸)
            if not self.page.window.width:
                self.page.window.width = 1280
            if not self.page.window.height:
                self.page.window.height = 800
            if not self.page.window.min_width:
                self.page.window.min_width = 480
            if not self.page.window.min_height:
                self.page.window.min_height = 600
            self.page.window.title = APP_NAME
        except Exception as e:
            print(f"[app] window 设置失败: {e}")

        self._apply_theme()
        self.page.on_resize = self._on_resize
        self._build_layout()
        self.navigate_to("home")

    def _apply_theme(self):
        """应用主题"""
        mode_str = self.settings.get("theme_mode", "system")
        if mode_str == "light":
            self.page.theme_mode = ThemeMode.LIGHT
        elif mode_str == "dark":
            self.page.theme_mode = ThemeMode.DARK
        else:
            self.page.theme_mode = ThemeMode.SYSTEM

        _ui_font = self.settings.get("ui_font_family", "Microsoft YaHei UI")
        self.page.theme = build_theme(dark=False, font_family=_ui_font)
        self.page.dark_theme = build_theme(dark=True, font_family=_ui_font)

        # 应用导出字体设置 (用于 export_service)
        # 通过全局 settings 传递，不直接影响 UI
        self.page.update()

    def _on_resize(self, e):
        try:
            self._rebuild_layout_for_width(self.page.window.width or 1280)
            self.page.update()
        except Exception as ex:
            print(f"[app] resize 失败: {ex}")

    def _build_layout(self):
        try:
            w = self.page.window.width or 1280
        except Exception:
            w = 1280
        self._rebuild_layout_for_width(w)

    def _rebuild_layout_for_width(self, width: float):
        """根据窗口宽度选择桌面/移动布局"""
        is_mobile = width < self.MOBILE_BREAKPOINT

        # AppBar - 关键：图标用 on_surface 保证亮暗都可见
        app_bar = ft.AppBar(
            leading=Container(
                content=Icon(Icons.SCHOOL_ROUNDED, size=30,
                             color=Colors.ON_SURFACE),   # 用 on_surface 而非 primary
                padding=ft.Padding.only(left=12),
            ),
            leading_width=56,
            title=self.app_bar_title,
            center_title=False,
            actions=[
                # 主题切换按钮 (高对比度)
                ft.IconButton(
                    icon=Icons.LIGHT_MODE if self.page.theme_mode == ThemeMode.DARK
                    else Icons.DARK_MODE,
                    tooltip="切换主题",
                    on_click=self._toggle_theme,
                    icon_color=Colors.ON_SURFACE,        # 关键：明确图标颜色
                    selected_icon_color=Colors.PRIMARY,
                ),
                # 关于按钮
                ft.IconButton(
                    icon=Icons.INFO_OUTLINE,
                    tooltip="关于",
                    on_click=self._show_about,
                    icon_color=Colors.ON_SURFACE,        # 关键：明确图标颜色
                ),
            ],
            bgcolor=Colors.SURFACE,
        )

        if is_mobile:
            self.nav_rail = None
            self.nav_bar = self._build_nav_bar()
            layout = Column(
                controls=[
                    app_bar,
                    Container(
                        content=self.content_area,
                        expand=True,
                        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                    ),
                    self.nav_bar,
                ],
                spacing=0,
                expand=True,
            )
        else:
            self.nav_bar = None
            self.nav_rail = self._build_nav_rail()
            layout = Row(
                controls=[
                    Container(
                        content=self.nav_rail,
                        width=220,
                        bgcolor=Colors.SURFACE,
                    ),
                    Container(
                        content=Column(
                            controls=[
                                app_bar,
                                Container(
                                    content=self.content_area,
                                    expand=True,
                                    padding=ft.Padding.symmetric(
                                        horizontal=24, vertical=16
                                    ),
                                ),
                            ],
                            spacing=0,
                            expand=True,
                        ),
                        expand=True,
                    ),
                ],
                spacing=0,
                expand=True,
            )

        self.page.controls.clear()
        self.page.add(layout)
        self.page.update()

    def _build_nav_rail(self) -> NavigationRail:
        destinations = [
            NavigationRailDestination(
                icon=ft.Icon(item["icon"]),
                selected_icon=ft.Icon(item["selected_icon"]),
                label=item["label"],
            )
            for item in self.NAV_ITEMS
        ]

        selected_idx = next(
            (i for i, item in enumerate(self.NAV_ITEMS)
             if item["key"] == self.current_route),
            0
        )

        return NavigationRail(
            selected_index=selected_idx,
            destinations=destinations,
            on_change=self._on_nav_rail_change,
            extended=False,
            min_width=80,
            min_extended_width=220,
            leading=Container(
                content=Column(
                    controls=[
                        Icon(Icons.AUTO_STORIES_ROUNDED, size=42,
                             color=Colors.PRIMARY),
                        Text(APP_NAME, size=14, weight=ft.FontWeight.W_700,
                             text_align=ft.TextAlign.CENTER),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=6,
                ),
                padding=ft.Padding.only(top=16, bottom=8, left=8, right=8),
            ),
            trailing=Container(
                content=Text(
                    f"v{self._version()}",
                    size=11,
                    color=Colors.ON_SURFACE_VARIANT,
                    text_align=ft.TextAlign.CENTER,
                ),
                padding=ft.Padding.only(bottom=12),
                alignment=ft.Alignment(0, 0),
            ),
            bgcolor=Colors.SURFACE,
        )

    def _version(self):
        from config import APP_VERSION
        return APP_VERSION

    def _build_nav_bar(self) -> NavigationBar:
        destinations = [
            NavigationBarDestination(
                icon=ft.Icon(item["icon"]),
                selected_icon=ft.Icon(item["selected_icon"]),
                label=item["label"],
            )
            for item in self.NAV_ITEMS
        ]

        selected_idx = next(
            (i for i, item in enumerate(self.NAV_ITEMS)
             if item["key"] == self.current_route),
            0
        )

        return NavigationBar(
            selected_index=selected_idx,
            destinations=destinations,
            on_change=self._on_nav_bar_change,
        )

    # -------------------- 导航事件 --------------------
    def _on_nav_rail_change(self, e):
        idx = e.control.selected_index
        if 0 <= idx < len(self.NAV_ITEMS):
            self.navigate_to(self.NAV_ITEMS[idx]["key"])

    def _on_nav_bar_change(self, e):
        idx = e.control.selected_index
        if 0 <= idx < len(self.NAV_ITEMS):
            self.navigate_to(self.NAV_ITEMS[idx]["key"])

    # -------------------- 视图路由 --------------------
    def navigate_to(self, route: str):
        self.current_route = route

        idx = next(
            (i for i, item in enumerate(self.NAV_ITEMS) if item["key"] == route),
            0
        )
        if self.nav_rail:
            self.nav_rail.selected_index = idx
        if self.nav_bar:
            self.nav_bar.selected_index = idx

        view = self._get_view(route)
        self.content_area.content = view
        self.page.update()

    def _get_view(self, route: str) -> Control:
        """获取视图 (缓存策略)"""
        if route == "home":
            from views.home_view import HomeView
            return HomeView(app=self).build()
        elif route == "library":
            from views.library_view import LibraryView
            return LibraryView(app=self).build()
        elif route == "add":
            if "add" not in self._view_instances:
                from views.add_mistake_view import AddMistakeView
                self._view_instances["add"] = AddMistakeView(app=self)
            return self._view_instances["add"].build()
        elif route == "export":
            if "export" not in self._view_instances:
                from views.export_view import ExportView
                self._view_instances["export"] = ExportView(app=self)
            return self._view_instances["export"].build()
        elif route == "settings":
            if "settings" not in self._view_instances:
                from views.settings_view import SettingsView
                self._view_instances["settings"] = SettingsView(app=self)
            return self._view_instances["settings"].build()
        else:
            return Container(
                content=Text(f"未知页面: {route}", size=16),
                alignment=ft.Alignment(0, 0),
                expand=True,
            )

    # -------------------- 全局操作 --------------------
    def _toggle_theme(self, e=None):
        """切换主题模式 (system 模式按平台亮度决定)"""
        current = self.page.theme_mode
        if current == ThemeMode.LIGHT:
            new_mode = "dark"
        elif current == ThemeMode.DARK:
            new_mode = "light"
        else:
            try:
                if self.page.platform_brightness == ft.Brightness.DARK:
                    new_mode = "light"
                else:
                    new_mode = "dark"
            except Exception:
                new_mode = "dark"

        self.settings["theme_mode"] = new_mode
        SettingsService.save(self.settings)
        self._apply_theme()

        if e and hasattr(e, "control"):
            e.control.icon = (Icons.LIGHT_MODE if new_mode == "dark"
                              else Icons.DARK_MODE)

        self._rebuild_layout_for_width(self.page.window.width or 1280)
        # 重建当前视图, 让输入框/公式颜色立即应用新主题
        try:
            self.refresh_current_view()
        except Exception:
            pass

    def _show_about(self, e=None):
        """显示关于对话框"""
        content = ft.Container(
            content=ft.Column(
                controls=[
                    Text(APP_SUBTITLE, size=15,
                         color=Colors.ON_SURFACE_VARIANT),
                    ft.Divider(),
                    Text("技术栈", size=16, weight=ft.FontWeight.W_600),
                    Text(
                        "• Flet 0.86+ (Material 3)\n"
                        "• Pillow (图像增强)\n"
                        "• matplotlib (LaTeX 渲染)\n"
                        "• pypandoc (Word 导出)\n"
                        "• pdfkit (PDF 导出)",
                        size=14, color=Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Divider(),
                    Text(f"版本：{self._version()}", size=14,
                         color=Colors.ON_SURFACE_VARIANT),
                ],
                spacing=8,
                tight=True,
            ),
            width=420,
        )
        show_alert_dialog(
            self.page, APP_NAME, content,
            actions=[ft.TextButton("关闭", on_click=lambda e: pop_dialog(self.page))],
        )

    # -------------------- 设置刷新 --------------------
    def refresh_settings(self):
        self.settings = SettingsService.load()
        self._apply_theme()
        self._view_instances.clear()

    def refresh_current_view(self):
        self.navigate_to(self.current_route)
