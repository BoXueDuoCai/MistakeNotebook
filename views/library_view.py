# ============================================================
# 错题库与变式训练页
# ============================================================
# 功能：
#   1. 左侧列表 (搜索框 + 学科筛选)
#   2. 右侧详情：原图缩略图 + 题干 + 解析 (LaTeX 渲染)
#   3. 生成 AI 解析与变式题 (核心 AI 功能在此)
#   4. 变式挑战：作答 + AI 批改
#   5. 顶部"添加错题"按钮 (跳转到添加页)
# ============================================================

import time
import flet as ft
from flet import (
    Container, Column, Row, Text, ElevatedButton, OutlinedButton,
    Icons, Colors, Card, Icon,
    MainAxisAlignment, CrossAxisAlignment, FontWeight, Image,
    AlertDialog, ControlEvent, Control, Dropdown, TextField,
    Divider, ProgressBar, TextButton,
)

from utils.theme import surface_input_color
from services.storage_service import SettingsService, MistakeStorageService
from services.llm_service import create_llm_service
from utils.dialog import show_dialog, pop_dialog, show_snackbar, show_confirm_dialog
from utils.file_loader import image_to_base64, get_mime_type
from models.mistake import Mistake, Variant, SUBJECTS, SUBJECT_ICONS


class LibraryView:
    """错题库视图"""

    def __init__(self, app):
        self.app = app
        self.page = app.page
        self.settings = SettingsService.load()

        # 当前选中的错题
        self.current_mistake: Mistake = None
        self.current_variants: list = []

        # 控件
        self.filter_dropdown: Dropdown = None
        self.search_input: TextField = None
        self.mistake_list_view: ft.ListView = None
        self.detail_panel: Container = None
        self.loading_bar: ProgressBar = ProgressBar(visible=False, color=Colors.PRIMARY)
        self.variants_panel: Container = Container()

        # busy 标志
        self._generating = False
        # 看门狗: 生成/批改超时自动复位 (防卡死)
        from utils.run_guard import Watchdog
        self._gen_watchdog = Watchdog(self._reset_generating, timeout=120, name="生成解析")
        self._grade_watchdog = Watchdog(self._reset_grading, timeout=120, name="AI 批改")

        # 流式输出面板 (状态存于 _stream_buf, 控件在渲染时创建)
        self._stream_visible = False
        self._stream_phase = ""
        self._stream_buf = {"text": "", "reasoning": "", "last_push": 0.0}
        self._stream_status_ref = None
        self._stream_text_ref = None
        self._grading = False

        # 搜索关键词缓存
        self._search_keyword = ""
        self._filter_subject = "全部"

    def build(self):
        self.settings = SettingsService.load()
        all_mistakes = MistakeStorageService.load_all()

        # 头部 (含"添加错题"按钮)
        header = Container(
            content=Row(
                controls=[
                    Column(
                        controls=[
                            Text("错题库", size=30, weight=FontWeight.W_700),
                            Text(f"共 {len(all_mistakes)} 道错题",
                                 size=15, color=Colors.ON_SURFACE_VARIANT),
                        ],
                        spacing=4,
                    ),
                    ElevatedButton(
                        "添加错题",
                        icon=Icons.ADD_CIRCLE_OUTLINE,
                        on_click=lambda e: self.app.navigate_to("add"),
                        style=ft.ButtonStyle(
                            bgcolor=Colors.PRIMARY_CONTAINER,
                            color=Colors.ON_PRIMARY_CONTAINER,
                        ),
                    ),
                ],
                alignment=MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.only(bottom=16),
        )

        main_layout = ft.ResponsiveRow(
            controls=[
                ft.Column(
                    controls=[self._build_list_panel(all_mistakes)],
                    col={"xs": 12, "md": 4, "lg": 4},
                ),
                ft.Column(
                    controls=[self._build_detail_panel()],
                    col={"xs": 12, "md": 8, "lg": 8},
                ),
            ],
            spacing=16,
            expand=True,
        )

        return Container(
            content=ft.ListView(
                controls=[header, main_layout],
                spacing=16,
                expand=True,
            ),
            expand=True,
        )

    # -------------------- 筛选 + 搜索 --------------------
    def _build_list_panel(self, mistakes: list) -> Card:
        """构建左侧错题列表 (含搜索框 + 筛选)"""
        # 搜索框
        self.search_input = TextField(filled=True, fill_color=surface_input_color(self.page), 
            label="搜索 (题干/知识点/学科)",
            prefix_icon=Icons.SEARCH,
            on_change=self._on_search_change,
            hint_text="输入关键词",
        )

        # 学科筛选
        options = [ft.dropdown.Option(key="全部", text="全部学科")]
        for s in SUBJECTS:
            options.append(ft.dropdown.Option(key=s, text=s))

        self.filter_dropdown = Dropdown(filled=True, fill_color=surface_input_color(self.page), 
            value="全部",
            options=options,
            on_select=self._on_filter_change,
            dense=True,
        )

        # 列表项
        if not mistakes:
            items = [Container(
                content=Column(
                    controls=[
                        Icon(Icons.LIBRARY_BOOKS_OUTLINED, size=56,
                             color=Colors.OUTLINE),
                        Text("暂无错题", size=16,
                             color=Colors.ON_SURFACE_VARIANT),
                        Text("点击右上角「添加错题」开始录入",
                             size=13, color=Colors.OUTLINE),
                    ],
                    horizontal_alignment=CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
                alignment=ft.Alignment(0, 0),
                padding=ft.Padding.all(40),
            )]
        else:
            items = [self._build_list_item(m) for m in mistakes]

        self.mistake_list_view = ft.ListView(
            controls=items,
            spacing=8,
            expand=True,
            padding=ft.Padding.all(8),
        )
        return Card(
            elevation=0.5,
            content=Container(
                content=Column(
                    controls=[
                        self.search_input,
                        self.filter_dropdown,
                        Divider(),
                        Container(
                            content=self.mistake_list_view,
                            height=520,
                        ),
                    ],
                    spacing=8,
                ),
                padding=ft.Padding.all(12),
            ),
        )

    def _on_search_change(self, e: ControlEvent):
        """搜索关键词变化"""
        self._search_keyword = (e.control.value or "").strip().lower()
        self._apply_filter_and_refresh()

    def _on_filter_change(self, e: ControlEvent):
        """学科筛选变化"""
        self._filter_subject = e.control.value or "全部"
        self._apply_filter_and_refresh()

    def _apply_filter_and_refresh(self):
        """应用搜索和筛选，刷新列表"""
        all_mistakes = MistakeStorageService.load_all()
        filtered = []
        for m in all_mistakes:
            # 学科筛选
            if self._filter_subject != "全部" and m.subject != self._filter_subject:
                continue
            # 关键词搜索
            if self._search_keyword:
                keyword = self._search_keyword
                in_question = keyword in (m.original_question or "").lower()
                in_tag = keyword in (m.knowledge_tag or "").lower()
                in_subject = keyword in (m.subject or "").lower()
                in_error = keyword in (m.error_analysis or "").lower()
                if not (in_question or in_tag or in_subject or in_error):
                    continue
            filtered.append(m)

        self.mistake_list_view.controls.clear()
        if not filtered:
            self.mistake_list_view.controls.append(
                Container(
                    content=Column(
                        controls=[
                            Icon(Icons.SEARCH_OFF, size=48, color=Colors.OUTLINE),
                            Text("未找到匹配的错题", size=14,
                                 color=Colors.ON_SURFACE_VARIANT),
                        ],
                        horizontal_alignment=CrossAxisAlignment.CENTER,
                        spacing=8,
                    ),
                    alignment=ft.Alignment(0, 0),
                    padding=ft.Padding.all(40),
                )
            )
        else:
            for m in filtered:
                self.mistake_list_view.controls.append(self._build_list_item(m))
        self.page.update()

    def _build_list_item(self, mistake: Mistake) -> Control:
        subject = mistake.subject or "未分类"
        icon_name = SUBJECT_ICONS.get(subject, "HELP_OUTLINE")
        icon_attr = getattr(ft.Icons, icon_name, ft.Icons.HELP_OUTLINE)

        question_text = mistake.original_question or "(无题干)"
        # LaTeX 转为可读文本预览
        from services.latex_service import latex_to_plain_text
        preview = latex_to_plain_text(question_text)
        if len(preview) > 40:
            preview = preview[:40] + "..."

        # 选中状态：用主色边框+背景高亮
        is_selected = (self.current_mistake and mistake.id == self.current_mistake.id)
        if mistake.is_mastered:
            bg = Colors.TERTIARY_CONTAINER
            text_color = Colors.ON_TERTIARY_CONTAINER
        elif is_selected:
            bg = Colors.PRIMARY_CONTAINER
            text_color = Colors.ON_PRIMARY_CONTAINER
        else:
            bg = Colors.SURFACE
            text_color = Colors.ON_SURFACE

        # 解析状态标记
        has_solution = bool(mistake.standard_solution)
        solution_badge = " ✓ 已解析" if has_solution else " ⏳ 待生成解析"

        # 边框 (选中时显示主色边框)
        border = None
        if is_selected:
            border = ft.Border.all(2, Colors.PRIMARY)

        return Container(
            content=Row(
                controls=[
                    Icon(icon_attr, color=Colors.PRIMARY, size=22),
                    Container(
                        content=Column(
                            controls=[
                                Text(preview, size=14, color=text_color,
                                     max_lines=1,
                                     overflow=ft.TextOverflow.ELLIPSIS,
                                     weight=FontWeight.W_500),
                                Text(
                                    f"{subject} · {mistake.knowledge_tag or '未分类'}{solution_badge}"
                                    + (" · ✓" if mistake.is_mastered else ""),
                                    size=12, color=Colors.ON_SURFACE_VARIANT,
                                ),
                            ],
                            spacing=2,
                        ),
                        expand=True,
                    ),
                    # 选中指示器
                    *([Icon(Icons.CHEVRON_RIGHT, color=Colors.PRIMARY, size=20)]
                      if is_selected else []),
                ],
                spacing=10,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            border_radius=10,
            bgcolor=bg,
            border=border,
            ink=True,
            on_click=lambda e, m=mistake: self._on_select_mistake(m),
        )

    def _on_select_mistake(self, mistake: Mistake):
        self.current_mistake = mistake
        self.current_variants = mistake.variants.copy() if mistake.variants else []
        # 重新渲染列表 (高亮选中项)
        all_mistakes = MistakeStorageService.load_all()
        subject = self.filter_dropdown.value if self.filter_dropdown else "全部"
        if subject and subject != "全部":
            all_mistakes = [m for m in all_mistakes if m.subject == subject]
        # 应用搜索过滤
        if self._search_keyword:
            all_mistakes = [m for m in all_mistakes if (
                self._search_keyword in (m.original_question or "").lower() or
                self._search_keyword in (m.knowledge_tag or "").lower() or
                self._search_keyword in (m.subject or "").lower() or
                self._search_keyword in (m.error_analysis or "").lower()
            )]
        self.mistake_list_view.controls.clear()
        for m in all_mistakes:
            self.mistake_list_view.controls.append(self._build_list_item(m))
        # 渲染详情
        self._render_detail_panel()
        self.page.update()

    # -------------------- 右侧详情 --------------------
    def _build_detail_panel(self) -> Card:
        self.detail_panel = Container(
            content=self._build_detail_placeholder(),
            expand=True,
        )
        return Card(
            elevation=0.5,
            content=Container(
                content=self.detail_panel,
                padding=ft.Padding.all(8),
                height=680,
            ),
        )

    def _build_detail_placeholder(self) -> Container:
        return Container(
            content=Column(
                controls=[
                    Icon(Icons.LIBRARY_BOOKS_OUTLINED, size=72,
                         color=Colors.OUTLINE),
                    Text("选择左侧错题查看详情", size=18,
                         color=Colors.ON_SURFACE_VARIANT),
                    Text("支持查看原图、生成 AI 解析与变式挑战",
                         size=14, color=Colors.OUTLINE),
                ],
                horizontal_alignment=CrossAxisAlignment.CENTER,
                spacing=10,
            ),
            alignment=ft.Alignment(0, 0),
            padding=ft.Padding.all(60),
            expand=True,
        )

    def _render_detail_panel(self):
        """渲染详情面板"""
        if not self.current_mistake:
            self.detail_panel.content = self._build_detail_placeholder()
            return

        m = self.current_mistake
        # LaTeX 混排渲染 (文本与公式同行显示)
        from utils.latex_widgets import build_latex_content, is_dark_mode

        def build_latex_widget(text: str, size: int = 15) -> Control:
            return build_latex_content(text, size, dark=is_dark_mode(self.page))

        # 图片缩略图 (限宽居中, 避免面板留大片空白) - 单击可预览 (issue #9)
        img_path = m.enhanced_image or m.original_image
        image_widget = Container()
        if img_path:
            b64 = image_to_base64(img_path)
            if b64:
                # 包一层 InkWell + Tooltip, 单击弹出大图预览 (可缩放/拖拽)
                from utils.image_preview_dialog import show_image_preview_dialog
                thumb = Container(
                    content=Image(
                        src=f"data:{get_mime_type(img_path)};base64," + b64,
                        fit=ft.BoxFit.CONTAIN,
                        width=300, height=200,
                        border_radius=12,
                    ),
                    padding=ft.Padding.all(8),
                    bgcolor=Colors.SURFACE_CONTAINER_HIGHEST,
                    border_radius=12,
                    width=320,
                    alignment=ft.Alignment(0, 0),
                    ink=True,
                    on_click=lambda e, p=img_path: show_image_preview_dialog(
                        self.page, p, title="错题图片预览"),
                    tooltip="单击放大预览 (滚轮缩放 / 拖拽移动 / 双击复位)",
                )
                image_widget = Row(
                    [thumb],
                    alignment=MainAxisAlignment.START,
                )

        tags_row = Row(
            controls=[
                Container(
                    content=Text(m.subject or "未分类",
                                 size=14, weight=FontWeight.W_600),
                    padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                    bgcolor=Colors.PRIMARY_CONTAINER,
                    border_radius=12,
                ),
                Container(
                    content=Text(m.knowledge_tag or "未分类", size=13),
                    padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                    bgcolor=Colors.SECONDARY_CONTAINER,
                    border_radius=12,
                ),
                *([
                    Container(
                        content=Text("已掌握", size=12),
                        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                        bgcolor=Colors.TERTIARY_CONTAINER,
                        border_radius=12,
                    )
                ] if m.is_mastered else []),
                *([
                    Container(
                        content=Row([
                            Icon(Icons.CHECK_CIRCLE, size=14, color=Colors.TERTIARY),
                            Text("已生成解析", size=12, color=Colors.TERTIARY),
                        ], spacing=4),
                        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                        bgcolor=Colors.TERTIARY_CONTAINER,
                        border_radius=12,
                    )
                ] if m.standard_solution else [
                    Container(
                        content=Row([
                            Icon(Icons.PENDING, size=14, color=Colors.SECONDARY),
                            Text("待生成解析", size=12, color=Colors.SECONDARY),
                        ], spacing=4),
                        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                        bgcolor=Colors.SECONDARY_CONTAINER,
                        border_radius=12,
                    )
                ]),
            ],
            spacing=8,
            wrap=True,
        )

        info_controls = [
            tags_row,
            Divider(),
            # Loading + 流式面板置顶: 点击生成后立即在顶部看到实时状态
            self.loading_bar,
            self._build_stream_container(),
            image_widget,
            Row([
                Icon(Icons.QUESTION_MARK, color=Colors.PRIMARY, size=20),
                Text("题目", size=17, weight=FontWeight.W_600),
            ], spacing=6),
            build_latex_widget(m.original_question, size=15),
        ]

        if m.error_analysis:
            info_controls.extend([
                Row([
                    Icon(Icons.ERROR_OUTLINE, color=Colors.ERROR, size=20),
                    Text("错因分析", size=17, weight=FontWeight.W_600),
                ], spacing=6),
                build_latex_widget(m.error_analysis, size=15),
            ])

        if m.standard_solution:
            info_controls.extend([
                Row([
                    Icon(Icons.MENU_BOOK, color=Colors.PRIMARY, size=20),
                    Text("标准解析", size=17, weight=FontWeight.W_600),
                ], spacing=6),
                build_latex_widget(m.standard_solution, size=15),
            ])

        # 变式挑战区
        info_controls.extend([
            Divider(),
            Row([
                Icon(Icons.EXTENSION, color=Colors.TERTIARY, size=22),
                Text("AI 解析与变式训练", size=20, weight=FontWeight.W_600),
            ], spacing=8),
            Row([
                ElevatedButton(
                    "📝 生成解析",
                    icon=Icons.MENU_BOOK,
                    on_click=self._on_generate_solution,
                    disabled=self._generating,
                    style=ft.ButtonStyle(
                        bgcolor=Colors.PRIMARY_CONTAINER,
                        color=Colors.ON_PRIMARY_CONTAINER,
                    ),
                ),
                ElevatedButton(
                    "✨ 生成变式题",
                    icon=Icons.EXTENSION,
                    on_click=self._on_generate_variants,
                    disabled=self._generating or not bool(m.standard_solution),
                    style=ft.ButtonStyle(
                        bgcolor=Colors.TERTIARY_CONTAINER,
                        color=Colors.ON_TERTIARY_CONTAINER,
                    ),
                ),
                OutlinedButton(
                    "清空变式",
                    icon=Icons.DELETE_OUTLINE,
                    on_click=self._on_clear_variants,
                ),
                OutlinedButton(
                    "删除此题",
                    icon=Icons.DELETE_FOREVER,
                    on_click=self._on_delete_mistake,
                ),
            ], spacing=8, wrap=True),
            self._build_variants_panel(),
        ])

        self.detail_panel.content = Column(
            controls=info_controls,
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def _build_variants_panel(self) -> Container:
        if not self.current_variants:
            self.variants_panel.content = Text(
                "尚无变式题，点击「生成变式题」开始挑战",
                size=14, color=Colors.ON_SURFACE_VARIANT,
            )
            return self.variants_panel

        cards = []
        for i, v in enumerate(self.current_variants):
            cards.append(self._build_variant_challenge_card(i + 1, v))

        self.variants_panel.content = Column(
            controls=cards,
            spacing=12,
        )
        return self.variants_panel

    def _build_variant_challenge_card(self, idx: int, variant: Variant) -> Card:
        # LaTeX 混排渲染 (文本与公式同行显示)
        from utils.latex_widgets import build_latex_content, is_dark_mode

        def build_latex_widget(text: str, size: int = 15) -> Control:
            return build_latex_content(text, size, dark=is_dark_mode(self.page))

        question_section = Column([
            Row([
                Icon(Icons.EXTENSION_OUTLINED, color=Colors.TERTIARY, size=20),
                Text(f"变式 {idx}", weight=FontWeight.W_600,
                     color=Colors.TERTIARY, size=16),
            ], spacing=6),
            build_latex_widget(variant.question, size=15),
        ], spacing=6)

        answer_input = TextField(filled=True, fill_color=surface_input_color(self.page), 
            label="你的作答",
            multiline=True,
            min_lines=2,
            max_lines=4,
            value=variant.user_answer,
        )
        answer_input.data = variant

        feedback_section = Container()
        if variant.ai_feedback:
            is_correct = variant.is_correct
            feedback_section = Container(
                content=Column([
                    Row([
                        Icon(Icons.CHECK_CIRCLE if is_correct else Icons.CANCEL,
                             color=Colors.TERTIARY if is_correct else Colors.ERROR,
                             size=22),
                        Text("AI 批改反馈", weight=FontWeight.W_600, size=16,
                             color=Colors.TERTIARY if is_correct else Colors.ERROR),
                    ], spacing=6),
                    Text(variant.ai_feedback, size=14, selectable=True),
                ], spacing=6),
                padding=ft.Padding.all(12),
                bgcolor=Colors.TERTIARY_CONTAINER if is_correct else Colors.ERROR_CONTAINER,
                border_radius=10,
            )

        solution_section = Container()
        if variant.solution:
            solution_section = Container(
                content=Column([
                    Text("参考解析", size=14, weight=FontWeight.W_500,
                         color=Colors.ON_SURFACE_VARIANT),
                    build_latex_widget(variant.solution, size=14),
                ], spacing=4),
                padding=ft.Padding.all(10),
                bgcolor=Colors.SURFACE_CONTAINER_HIGHEST,
                border_radius=8,
            )

        return Card(
            elevation=0.5,
            content=Container(
                content=Column([
                    question_section,
                    answer_input,
                    Row([
                        ElevatedButton(
                            "AI 批改",
                            icon=Icons.GRADING,
                            on_click=lambda e, inp=answer_input, v=variant:
                            self._on_grade_variant(v, inp.value or ""),
                        ),
                        OutlinedButton(
                            "查看解析",
                            icon=Icons.MENU_BOOK_OUTLINED,
                            on_click=lambda e, sol=variant.solution:
                            self._show_solution_dialog(sol),
                        ),
                    ], spacing=8),
                    feedback_section,
                    solution_section,
                ], spacing=10),
                padding=ft.Padding.all(14),
            ),
        )

    # -------------------- 生成 AI 解析与变式题 --------------------
    # -------------------- 流式输出 (实时显示 AI 生成过程) --------------------
    def _stream_status_value(self) -> str:
        """当前状态标题"""
        buf = self._stream_buf
        reasoning = buf.get("reasoning", "") or ""
        text = buf.get("text", "") or ""
        if reasoning and not text:
            return "🧠 AI 正在思考..."
        if text:
            return f"✍️ {self._stream_phase or 'AI 正在生成...'}"
        return self._stream_phase or "AI 处理中..."

    def _stream_text_value(self) -> str:
        """当前流式正文 (尾部)"""
        buf = self._stream_buf
        reasoning = buf.get("reasoning", "") or ""
        text = buf.get("text", "") or ""
        if reasoning and not text:
            return reasoning[-200:]
        if text:
            return text[-280:]
        return ""

    def _build_stream_container(self) -> Container:
        """每次渲染重建流式面板 (避免控件重复挂载; 状态存于 _stream_buf)"""
        self._stream_status_ref = Text(self._stream_status_value(), size=12,
                                       color=Colors.SECONDARY,
                                       weight=FontWeight.W_600)
        self._stream_text_ref = Text(self._stream_text_value(), size=12,
                                     color=Colors.ON_SURFACE_VARIANT,
                                     selectable=True)
        return Container(
            content=Column([self._stream_status_ref, self._stream_text_ref], spacing=2),
            padding=ft.Padding.all(10),
            bgcolor=Colors.SURFACE_CONTAINER_HIGHEST,
            border_radius=8,
            visible=self._stream_visible,
        )

    def _set_stream_phase(self, phase: str):
        """更新阶段提示"""
        self._stream_phase = phase
        try:
            self.page.run_thread(self._update_stream_ui)
        except Exception:
            pass

    def _push_stream(self, text: str, reasoning: str):
        """流式回调 (节流后刷新 UI): 展示思维链与生成内容"""
        import time as _time
        buf = self._stream_buf
        buf["text"] += text
        buf["reasoning"] += reasoning
        now = _time.time()
        if now - buf["last_push"] < 0.12:   # 节流 ~8fps, 避免 UI 卡顿
            return
        buf["last_push"] = now
        try:
            self.page.run_thread(self._update_stream_ui)
        except Exception:
            pass

    def _update_stream_ui(self):
        """刷新流式面板 (可从任意线程安全调用)"""
        try:
            self._stream_visible = True
            if getattr(self, "_stream_status_ref", None) is not None:
                self._stream_status_ref.value = self._stream_status_value()
            if getattr(self, "_stream_text_ref", None) is not None:
                self._stream_text_ref.value = self._stream_text_value()
            self.page.update()
        except Exception:
            pass

    def _hide_stream(self):
        """完成/失败时隐藏流式面板"""
        try:
            self._stream_visible = False
            self._stream_buf = {"text": "", "reasoning": "", "last_push": 0.0}
            if getattr(self, "_stream_status_ref", None) is not None:
                self._stream_status_ref.value = self._stream_status_value()
            if getattr(self, "_stream_text_ref", None) is not None:
                self._stream_text_ref.value = self._stream_text_value()
            self.page.update()
        except Exception:
            pass

    # -------------------- 生成解析 (仅解析, 不含变式) --------------------
    def _on_generate_solution(self, e: ControlEvent):
        """生成标准解析 (不含变式题)"""
        if self._generating:
            return
        if not self.current_mistake:
            show_snackbar(self.page, "请先选择一道错题", is_error=True)
            return
        if not self.settings.get("api_key"):
            show_snackbar(self.page, "请先配置 API Key", is_error=True)
            return

        m = self.current_mistake
        self._generating = True
        self.loading_bar.visible = True
        self.page.update()
        self._gen_watchdog.arm()

        def _on_delta(text, reasoning):
            self._push_stream(text, reasoning)

        def _do_generate():
            try:
                self.settings = SettingsService.load()
                llm = create_llm_service(self.settings, purpose="solution")

                image_path = m.enhanced_image or m.original_image
                # 带图片时使用视觉模型 (文本模型可能不支持识图, 如 deepseek)
                purpose = "ocr" if image_path else "solution"
                llm = create_llm_service(self.settings, purpose=purpose)
                self._set_stream_phase("📝 正在生成标准解析...")
                result = llm.analyze_mistake_stream(
                    image_path=image_path if image_path else None,
                    question_text=m.original_question,
                    error_thinking=m.error_thinking,
                    on_delta=_on_delta,
                )
                # 只更新解析相关字段, 不动 variants
                if not m.subject:
                    m.subject = result.get("subject", "")
                if not m.knowledge_tag:
                    m.knowledge_tag = result.get("knowledge_tag", "")
                if not m.original_question:
                    m.original_question = result.get("original_question", "")
                m.image_desc = result.get("image_desc", "")
                m.error_analysis = result.get("error_analysis", "")
                m.standard_solution = result.get("standard_solution", "")
                MistakeStorageService.update(m)

                def _on_success():
                    try:
                        self.loading_bar.visible = False
                        self._generating = False
                        self._gen_watchdog.disarm()
                        self._hide_stream()
                        self._render_detail_panel()
                        self._apply_filter_and_refresh()
                        self.page.update()
                        show_snackbar(self.page, "✓ 解析已生成")
                    except Exception:
                        self._generating = False
                self.page.run_thread(_on_success)
            except BaseException as ex:
                def _on_error(err=ex):
                    self.loading_bar.visible = False
                    self._generating = False
                    self._gen_watchdog.disarm()
                    self._hide_stream()
                    self.page.update()
                    show_snackbar(self.page, f"生成解析失败: {err}", is_error=True)
                self.page.run_thread(_on_error)

        self.page.run_thread(_do_generate)

    # -------------------- 生成变式 (仅变式) --------------------
    def _on_generate_variants(self, e: ControlEvent):
        """仅生成变式题 (需已有解析)"""
        if self._generating:
            return
        if not self.current_mistake:
            show_snackbar(self.page, "请先选择一道错题", is_error=True)
            return
        if not self.settings.get("api_key"):
            show_snackbar(self.page, "请先配置 API Key", is_error=True)
            return
        m = self.current_mistake
        if not m.standard_solution:
            show_snackbar(self.page, "请先生成解析", is_error=True)
            return

        self._generating = True
        self.loading_bar.visible = True
        self.page.update()
        self._gen_watchdog.arm()

        def _on_delta(text, reasoning):
            self._push_stream(text, reasoning)

        def _do_generate():
            try:
                self.settings = SettingsService.load()
                llm = create_llm_service(self.settings, purpose="variants")

                self._set_stream_phase("✨ 正在生成变式题...")
                variants_data = llm.generate_variants(
                    question=m.original_question,
                    solution=m.standard_solution,
                    knowledge_tag=m.knowledge_tag,
                    num_variants=2,
                )
                self.current_variants = [
                    Variant(question=v.get("question", ""),
                            solution=v.get("solution", ""))
                    for v in variants_data
                ]
                m.variants = self.current_variants
                MistakeStorageService.update(m)

                def _on_success():
                    try:
                        self.loading_bar.visible = False
                        self._generating = False
                        self._gen_watchdog.disarm()
                        self._hide_stream()
                        self._render_detail_panel()
                        self.page.update()
                        show_snackbar(self.page,
                            f"✓ 已生成 {len(self.current_variants)} 道变式题")
                    except Exception:
                        self._generating = False
                self.page.run_thread(_on_success)
            except BaseException as ex:
                def _on_error(err=ex):
                    self.loading_bar.visible = False
                    self._generating = False
                    self._gen_watchdog.disarm()
                    self._hide_stream()
                    self.page.update()
                    show_snackbar(self.page, f"生成变式失败: {err}", is_error=True)
                self.page.run_thread(_on_error)

        self.page.run_thread(_do_generate)

    # -------------------- 兼容: 一键生成全部 (保留旧入口) --------------------
    def _on_generate_full(self, e: ControlEvent):
        """一键生成解析 + 变式 (兼容旧调用)"""
        if self._generating:
            return
        if not self.current_mistake:
            show_snackbar(self.page, "请先选择一道错题", is_error=True)
            return
        if not self.settings.get("api_key"):
            show_snackbar(self.page, "请先配置 API Key", is_error=True)
            return

        m = self.current_mistake
        self._generating = True
        self.loading_bar.visible = True
        self.page.update()
        self._gen_watchdog.arm()

        def _on_delta(text, reasoning):
            self._push_stream(text, reasoning)

        def _do_generate():
            try:
                self.settings = SettingsService.load()
                if m.standard_solution:
                    # 已有解析 -> 只生成变式
                    llm = create_llm_service(self.settings, purpose="variants")
                    self._set_stream_phase("✨ 正在生成变式题...")
                    variants_data = llm.generate_variants(
                        question=m.original_question,
                        solution=m.standard_solution,
                        knowledge_tag=m.knowledge_tag,
                        num_variants=2,
                    )
                    self.current_variants = [
                        Variant(question=v.get("question", ""),
                                solution=v.get("solution", ""))
                        for v in variants_data
                    ]
                    m.variants = self.current_variants
                    MistakeStorageService.update(m)
                else:
                    # 无解析 -> 完整分析 (解析 + 变式)
                    image_path = m.enhanced_image or m.original_image
                    purpose = "ocr" if image_path else "solution"
                    llm = create_llm_service(self.settings, purpose=purpose)
                    self._set_stream_phase("📝 正在生成解析与变式...")
                    result = llm.analyze_mistake_stream(
                        image_path=image_path if image_path else None,
                        question_text=m.original_question,
                        error_thinking=m.error_thinking,
                        on_delta=_on_delta,
                    )
                    if not m.subject:
                        m.subject = result.get("subject", "")
                    if not m.knowledge_tag:
                        m.knowledge_tag = result.get("knowledge_tag", "")
                    if not m.original_question:
                        m.original_question = result.get("original_question", "")
                    m.image_desc = result.get("image_desc", "")
                    m.error_analysis = result.get("error_analysis", "")
                    m.standard_solution = result.get("standard_solution", "")
                    self.current_variants = [
                        Variant(question=v.get("question", ""),
                                solution=v.get("solution", ""))
                        for v in result.get("variants", [])
                    ]
                    m.variants = self.current_variants
                    MistakeStorageService.update(m)

                def _on_success():
                    try:
                        self.loading_bar.visible = False
                        self._generating = False
                        self._gen_watchdog.disarm()
                        self._hide_stream()
                        self._render_detail_panel()
                        self._apply_filter_and_refresh()
                        self.page.update()
                        show_snackbar(self.page,
                            f"✓ 已生成解析与 {len(self.current_variants)} 道变式题")
                    except Exception:
                        self._generating = False
                self.page.run_thread(_on_success)
            except BaseException as ex:
                def _on_error(err=ex):
                    self.loading_bar.visible = False
                    self._generating = False
                    self._gen_watchdog.disarm()
                    self._hide_stream()
                    self.page.update()
                    show_snackbar(self.page, f"生成失败: {err}", is_error=True)
                self.page.run_thread(_on_error)

        self.page.run_thread(_do_generate)

    def _reset_generating(self):
        """兜底: 强制结束生成状态"""
        self._generating = False
        try:
            self.loading_bar.visible = False
            self.page.update()
        except Exception:
            pass

    def _on_clear_variants(self, e: ControlEvent):
        if not self.current_mistake:
            return
        self.current_variants = []
        self.current_mistake.variants = []
        MistakeStorageService.update(self.current_mistake)
        self._render_detail_panel()
        self.page.update()

    def _on_delete_mistake(self, e: ControlEvent):
        if not self.current_mistake:
            return

        mistake_id = self.current_mistake.id

        def do_delete():
            MistakeStorageService.delete(mistake_id)
            self.current_mistake = None
            self.current_variants = []
            self.detail_panel.content = self._build_detail_placeholder()
            self._apply_filter_and_refresh()
            show_snackbar(self.page, "✓ 已删除")

        show_confirm_dialog(
            self.page,
            title="确认删除？",
            message="此操作不可恢复，错题及其变式题、图片文件都将被删除",
            on_confirm=do_delete,
            confirm_text="确认删除",
            cancel_text="取消",
            is_danger=True,
        )

    def _on_grade_variant(self, variant: Variant, user_answer: str):
        """AI 批改变式题"""
        if self._grading:
            return
        if not user_answer.strip():
            show_snackbar(self.page, "请先作答", is_error=True)
            return

        if not self.settings.get("api_key"):
            show_snackbar(self.page, "请先配置 API Key", is_error=True)
            return

        self._grading = True
        self._grade_watchdog.arm()
        show_snackbar(self.page, "正在批改...")
        self._stream_buf = {"text": "", "reasoning": "", "last_push": 0.0}
        self._set_stream_phase("📝 AI 正在批改你的作答...")

        def _grade_stream_cb(text, reasoning):
            self._push_stream(text, reasoning)

        def _do_grade():
            try:
                self.settings = SettingsService.load()
                llm = create_llm_service(self.settings)
                result = llm.grade_answer_stream(
                    question=variant.question,
                    standard_solution=variant.solution,
                    user_answer=user_answer,
                    on_delta=_grade_stream_cb,
                )
                variant.user_answer = user_answer
                variant.is_correct = result.get("is_correct", False)
                variant.ai_feedback = result.get("feedback", "")
                variant.answered_at = time.strftime("%Y-%m-%dT%H:%M:%S")

                if self.current_mistake:
                    MistakeStorageService.update(self.current_mistake)

                def _on_success():
                    try:
                        self._grading = False
                        self._grade_watchdog.disarm()
                        self._hide_stream()
                        self._render_detail_panel()
                        self.page.update()
                        score = result.get("score", 0)
                        correct = "正确" if variant.is_correct else "需改进"
                        show_snackbar(self.page, f"✓ 批改完成 ({correct}，{score}分)")
                    except Exception:
                        self._grading = False
                self.page.run_thread(_on_success)
            except Exception as ex:
                def _on_error(err=ex):
                    self._grading = False
                    self._grade_watchdog.disarm()
                    self._hide_stream()
                    show_snackbar(self.page, f"批改失败: {err}", is_error=True)
                self.page.run_thread(_on_error)

        self.page.run_thread(_do_grade)

    def _reset_grading(self):
        """兜底: 强制结束批改状态"""
        self._grading = False
        try:
            self.page.update()
        except Exception:
            pass

    def _show_solution_dialog(self, solution: str):
        # LaTeX 混排渲染 (文本与公式同行显示)
        from utils.latex_widgets import build_latex_content, is_dark_mode

        def build_latex_widget(text: str, size: int = 15) -> Control:
            return build_latex_content(text, size, dark=is_dark_mode(self.page))

        dlg = AlertDialog(
            modal=True,
            title=Text("参考解析", size=20),
            content=Container(
                content=build_latex_widget(solution),
                width=min(600, (self.page.window.width or 1280) - 64),
                height=min(400, (self.page.window.height or 800) - 200),
                padding=ft.Padding.all(16),
            ),
            actions=[
                TextButton("关闭", on_click=lambda e: pop_dialog(self.page)),
            ],
        )
        show_dialog(self.page, dlg)
