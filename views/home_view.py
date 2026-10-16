# ============================================================
# 首页 - 今日复习
# ============================================================
# 设计要点：
#   1. 头部布局调整：问候 + 日期 → 今日待复习 → 灰色小副标题
#   2. 亮色模式：日期/数量用 ON_PRIMARY (白)
#   3. 暗色模式：用深色背景 + 浅色文字
#   4. 整张页面可滚动
# ============================================================

from datetime import datetime
import flet as ft
from flet import (
    Container, Column, Row, Text, ElevatedButton, OutlinedButton,
    Icons, Colors, Card, Icon,
    MainAxisAlignment, CrossAxisAlignment, FontWeight, Image,
    Control, TextButton,
)

from services.storage_service import SettingsService
from services.review_service import ReviewService
from utils.dialog import show_dialog, pop_dialog, show_snackbar
from utils.file_loader import image_to_base64, get_mime_type
from models.mistake import Mistake, SUBJECT_ICONS


class HomeView:
    """首页 - 今日复习视图"""

    def __init__(self, app):
        self.app = app
        self.page = app.page
        self.settings = SettingsService.load()
        self.review_service = ReviewService(
            intervals=self.settings.get("review_intervals",
                                         [1, 2, 4, 7, 15, 30])
        )

    def build(self):
        today_mistakes = self.review_service.get_today_review_list()
        stats = self.review_service.get_stats()

        # 头部卡片 (问候 + 今日待复习合并为一张)
        header = self._build_header(stats, today_mistakes)
        # 统计卡片行
        stats_row = self._build_stats_row(stats)
        # 复习列表 (灰色副标题在此)
        review_section = self._build_review_section(today_mistakes)

        # 整个页面用 ListView 滚动
        scroll_view = ft.ListView(
            controls=[header, stats_row, review_section],
            spacing=20,
            expand=True,
        )

        return Container(
            content=scroll_view,
            expand=True,
        )

    # -------------------- 头部 (问候 + 今日待复习) --------------------
    def _build_header(self, stats: dict, today_mistakes: list) -> Container:
        today = datetime.now()
        greeting = "早上好"
        if 12 <= today.hour < 18:
            greeting = "下午好"
        elif today.hour >= 18:
            greeting = "晚上好"

        today_count = len(today_mistakes)

        # 今日待复习标题 (放在问候下方，紧贴问候)
        if today_count > 0:
            review_title = f"今日待复习：{today_count} 道"
        else:
            review_title = "今日无待复习"

        # 日期字符串 (放在最右侧或紧贴标题)
        date_str = today.strftime("%Y 年 %m 月 %d 日")

        # 头部卡片内容：垂直排列
        # 第一行：问候 + 日期 (日期在右)
        # 第二行：今日待复习标题 (大号)
        # 第三行：副标题/鼓励语 (灰色小字)
        header_content = Column(
            controls=[
                # 第一行：问候 + 日期
                Row(
                    controls=[
                        Text(f"{greeting}，同学！",
                             size=26, weight=FontWeight.W_700,
                             color=Colors.ON_PRIMARY),
                        # 日期 (放在右侧，白色或亮色)
                        Container(
                            content=Row(
                                controls=[
                                    Icon(Icons.CALENDAR_TODAY,
                                         color=Colors.ON_PRIMARY, size=16),
                                    Text(date_str, size=13,
                                         color=Colors.ON_PRIMARY),
                                ],
                                spacing=6,
                            ),
                            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                            bgcolor=Colors.PRIMARY,
                            border_radius=12,
                        ),
                    ],
                    alignment=MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=CrossAxisAlignment.CENTER,
                ),
                # 第二行：今日待复习大标题
                Row(
                    controls=[
                        Icon(Icons.TODAY, color=Colors.ON_PRIMARY_CONTAINER, size=24),
                        Text(review_title, size=20, weight=FontWeight.W_600,
                             color=Colors.ON_PRIMARY_CONTAINER),
                    ],
                    spacing=8,
                ),
                # 第三行：灰色副标题
                Text(
                    "继续坚持，每一道错题都是进步的阶梯" if today_count > 0
                    else "今天没有待复习的错题，继续保持！",
                    size=13, color=Colors.ON_PRIMARY_CONTAINER,
                ),
            ],
            spacing=8,
        )

        # 头部卡片 (用渐变背景)
        return Container(
            content=Row(
                controls=[
                    Container(
                        content=header_content,
                        expand=True,
                    ),
                    # 装饰大图标
                    Container(
                        content=Icon(Icons.AUTO_STORIES_ROUNDED,
                                     size=80, color=Colors.PRIMARY_CONTAINER),
                        padding=ft.Padding.only(right=20),
                    ),
                ],
                alignment=MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.all(24),
            border_radius=20,
            gradient=ft.LinearGradient(
                begin=ft.Alignment(-1, -1),
                end=ft.Alignment(1, 1),
                colors=[Colors.PRIMARY, Colors.PRIMARY_CONTAINER],
                stops=[0.3, 1.0],
            ),
        )

    # -------------------- 统计行 --------------------
    def _build_stats_row(self, stats: dict) -> Row:
        total = stats.get("total", 0)
        mastered = stats.get("mastered", 0)
        pending = stats.get("pending", 0)

        cards = [
            self._build_stat_card("错题总数", str(total),
                                   Icons.LIBRARY_BOOKS_OUTLINED,
                                   Colors.PRIMARY, Colors.PRIMARY_CONTAINER),
            self._build_stat_card("已掌握", str(mastered),
                                   Icons.CHECK_CIRCLE_OUTLINE,
                                   Colors.TERTIARY, Colors.TERTIARY_CONTAINER),
            self._build_stat_card("待复习", str(pending),
                                   Icons.SCHEDULE,
                                   Colors.SECONDARY, Colors.SECONDARY_CONTAINER),
        ]
        return ft.ResponsiveRow(
            controls=cards,
            spacing=12,
            run_spacing=12,
        )

    def _build_stat_card(self, title: str, value: str,
                         icon: str, color, bg) -> Container:
        return Container(
            content=Column(
                controls=[
                    Row(
                        controls=[
                            Icon(icon, color=color, size=24),
                            Text(title, size=14,
                                 color=Colors.ON_SURFACE_VARIANT,
                                 weight=FontWeight.W_500),
                        ],
                        spacing=6,
                    ),
                    Text(value, size=36, weight=FontWeight.W_700, color=color),
                ],
                spacing=6,
            ),
            padding=ft.Padding.all(16),
            bgcolor=bg,
            border_radius=14,
            col={"xs": 12, "md": 4},
        )

    # -------------------- 复习列表 --------------------
    def _build_review_section(self, today_mistakes: list) -> Container:
        if not today_mistakes:
            empty = Container(
                content=Column(
                    controls=[
                        Icon(Icons.CELEBRATION_OUTLINED, size=72,
                             color=Colors.OUTLINE),
                        Text("今日复习已清空", size=20,
                             weight=FontWeight.W_500),
                        Text("继续保持，争取早日掌握所有错题！",
                             size=14, color=Colors.ON_SURFACE_VARIANT),
                    ],
                    horizontal_alignment=CrossAxisAlignment.CENTER,
                    spacing=12,
                ),
                alignment=ft.Alignment.CENTER,
                padding=ft.Padding.all(60),
                bgcolor=Colors.SURFACE,
                border_radius=16,
            )
            content = Column(controls=[empty], spacing=12)
        else:
            cards = [self._build_mistake_card(m) for m in today_mistakes]
            content = Column(
                controls=cards,
                spacing=12,
            )

        return Container(content=content)

    def _build_mistake_card(self, mistake: Mistake) -> Control:
        """构建单道错题卡片 (Container 包装支持 on_click)"""
        subject = mistake.subject or "其他"
        icon_name = SUBJECT_ICONS.get(subject, "HELP_OUTLINE")
        icon_attr = getattr(ft.Icons, icon_name, ft.Icons.HELP_OUTLINE)

        # 题干预览 (LaTeX 转为可读文本)
        from services.latex_service import latex_to_plain_text
        question_text = latex_to_plain_text(mistake.original_question or "(无题干)")
        if len(question_text) > 100:
            question_text = question_text[:100] + "..."

        tag_text = mistake.knowledge_tag or "未分类"
        stage_info = self.review_service.get_stage_info(mistake)
        stage_label = stage_info["label"]

        # 标签行
        tags_row = Row(
            controls=[
                Container(
                    content=Row(
                        controls=[
                            Icon(icon_attr, size=18, color=Colors.PRIMARY),
                            Text(subject, size=14, weight=FontWeight.W_600),
                        ],
                        spacing=6,
                    ),
                    padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                    bgcolor=Colors.PRIMARY_CONTAINER,
                    border_radius=16,
                ),
                Container(
                    content=Text(tag_text, size=12,
                                 color=Colors.ON_SECONDARY_CONTAINER),
                    padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                    bgcolor=Colors.SECONDARY_CONTAINER,
                    border_radius=12,
                ),
                Container(
                    content=Text(stage_label, size=12,
                                 color=Colors.ON_TERTIARY_CONTAINER),
                    padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                    bgcolor=Colors.TERTIARY_CONTAINER,
                    border_radius=12,
                ),
                *([
                    Container(
                        content=Row(
                            controls=[
                                Icon(Icons.CHECK_CIRCLE, size=14, color=Colors.TERTIARY),
                                Text("已掌握", size=12, color=Colors.TERTIARY),
                            ],
                            spacing=4,
                        ),
                        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                        bgcolor=Colors.TERTIARY_CONTAINER,
                        border_radius=12,
                    )
                ] if mistake.is_mastered else []),
            ],
            spacing=8,
            wrap=True,
        )

        actions_row = Row(
            controls=[
                OutlinedButton(
                    "查看详情",
                    icon=Icons.VISIBILITY_OUTLINED,
                    on_click=lambda e, m=mistake: self._show_detail(m),
                ),
                ElevatedButton(
                    "继续复习",
                    icon=Icons.REFRESH,
                    on_click=lambda e, m=mistake: self._mark_continue(m),
                ),
                ElevatedButton(
                    "已掌握",
                    icon=Icons.CHECK,
                    on_click=lambda e, m=mistake: self._mark_mastered(m),
                    style=ft.ButtonStyle(
                        bgcolor=Colors.TERTIARY_CONTAINER,
                        color=Colors.ON_TERTIARY_CONTAINER,
                    ),
                ),
            ],
            spacing=8,
            wrap=True,
        )

        return Container(
            content=Card(
                elevation=0.5,
                content=Container(
                    content=Column(
                        controls=[
                            tags_row,
                            Text(question_text, size=15,
                                 max_lines=3, overflow=ft.TextOverflow.ELLIPSIS,
                                 selectable=True),
                            actions_row,
                        ],
                        spacing=10,
                    ),
                    padding=ft.Padding.all(16),
                ),
            ),
            ink=True,
            on_click=lambda e, m=mistake: self._show_detail(m),
        )

    # -------------------- 详情弹窗 --------------------
    def _show_detail(self, mistake: Mistake):
        # LaTeX 混排渲染 (文本与公式同行显示)
        from utils.latex_widgets import build_latex_content, is_dark_mode

        def build_latex_widget(text: str, size: int = 15) -> Control:
            return build_latex_content(text, size, dark=is_dark_mode(self.page))

        # 图片显示 (限宽居中)
        img_path = mistake.enhanced_image or mistake.original_image
        image_widget = Container()
        if img_path:
            b64 = image_to_base64(img_path)
            if b64:
                image_widget = Container(
                    content=Image(
                        src=f"data:{get_mime_type(img_path)};base64," + b64,
                        fit=ft.BoxFit.CONTAIN,
                        width=400, height=280,
                        border_radius=12,
                    ),
                    padding=ft.Padding.all(8),
                    bgcolor=Colors.SURFACE_CONTAINER_HIGHEST,
                    border_radius=12,
                    width=420,
                    alignment=ft.Alignment(0, 0),
                )
                image_widget = Row(
                    [image_widget],
                    alignment=MainAxisAlignment.START,
                )

        content_col = Column(
            controls=[
                Row(
                    controls=[
                        Container(
                            content=Text(mistake.subject or "未分类",
                                         size=14, weight=FontWeight.W_600),
                            padding=ft.Padding.symmetric(horizontal=12, vertical=6),
                            bgcolor=Colors.PRIMARY_CONTAINER,
                            border_radius=16,
                        ),
                        Container(
                            content=Text(mistake.knowledge_tag or "无标签",
                                         size=13),
                            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                            bgcolor=Colors.SECONDARY_CONTAINER,
                            border_radius=12,
                        ),
                    ],
                    spacing=8,
                ),
                ft.Divider(),
                image_widget,
                Text("题目", size=16, weight=FontWeight.W_600),
                build_latex_widget(mistake.original_question),
                ft.Divider(),
                Text("错因分析", size=16, weight=FontWeight.W_600),
                build_latex_widget(mistake.error_analysis),
                ft.Divider(),
                Text("标准解析", size=16, weight=FontWeight.W_600),
                build_latex_widget(mistake.standard_solution),
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
        )

        dlg = ft.AlertDialog(
            modal=True,
            title=Text(f"错题详情 - {mistake.subject or '未分类'}", size=20),
            content=Container(content=content_col,
                              width=min(900, (self.page.window.width or 1280) - 64),
                              height=min(600, (self.page.window.height or 800) - 160),
                              padding=ft.Padding.all(8)),
            actions=[
                ElevatedButton(
                    "已掌握",
                    icon=Icons.CHECK,
                    on_click=lambda e: self._dialog_mark_mastered(mistake, dlg),
                ),
                ElevatedButton(
                    "继续复习",
                    icon=Icons.REFRESH,
                    on_click=lambda e: self._dialog_mark_continue(mistake, dlg),
                ),
                TextButton("关闭", on_click=lambda e: pop_dialog(self.page)),
            ],
            actions_alignment=MainAxisAlignment.END,
        )
        show_dialog(self.page, dlg)

    # -------------------- 复习操作 --------------------
    def _mark_mastered(self, mistake: Mistake):
        try:
            self.review_service.mark_mastered(mistake.id)
            show_snackbar(self.page, "✓ 已标记为已掌握")
            self.app.refresh_current_view()
        except Exception as ex:
            show_snackbar(self.page, f"操作失败: {ex}", is_error=True)

    def _mark_continue(self, mistake: Mistake):
        try:
            self.review_service.mark_continue(mistake.id)
            show_snackbar(self.page, "✓ 已进入下一复习阶段")
            self.app.refresh_current_view()
        except Exception as ex:
            show_snackbar(self.page, f"操作失败: {ex}", is_error=True)

    def _dialog_mark_mastered(self, mistake: Mistake, dlg):
        pop_dialog(self.page)
        self._mark_mastered(mistake)

    def _dialog_mark_continue(self, mistake: Mistake, dlg):
        pop_dialog(self.page)
        self._mark_continue(mistake)
