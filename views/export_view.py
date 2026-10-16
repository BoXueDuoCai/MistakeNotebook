# ============================================================
# 试卷导出页
# ============================================================
# 功能：
#   1. 复选框列表展示所有错题 (含导入时间)
#   2. 按导入时间范围筛选 + 多选科目/知识点筛选 (issue #5)
#   3. 预览区 (HTML 嵌入实时渲染, 字号略小) (issue #5)
#   4. 导出 Word / PDF / HTML (含进度百分比) (issue #6)
#   5. 询问无解析错题是否调用 AI 生成
#   6. 字体设置
#   7. 跨平台: 桌面端打开文件管理器, 移动端调起系统分享面板 (issue #8)
# ============================================================

import asyncio
import os
import tempfile
from datetime import datetime
from typing import Tuple, Set

import flet as ft
from flet import (
    Container, Column, Row, Text, ElevatedButton, OutlinedButton,
    Icons, Colors, Card, Icon,
    MainAxisAlignment, CrossAxisAlignment, FontWeight, Checkbox, Switch,
    AlertDialog, ControlEvent, Control,
    Markdown, MarkdownExtensionSet, Divider, ProgressBar,
    TextField, TextButton,
)

from utils.theme import surface_input_color
from utils.platform_helper import (
    is_mobile, is_desktop, is_web, share_or_open_async, to_file_uri,
    get_default_export_dir,
)
from config import EXPORT_DIR, CACHE_DIR
from services.storage_service import SettingsService, MistakeStorageService
from services.export_service import (
    mistakes_to_markdown, markdown_to_preview, mistakes_to_html,
    export_to_docx, export_to_pdf, export_to_html,
    check_pandoc_installed, check_wkhtmltopdf_installed,
    get_wkhtmltopdf_path, get_pandoc_path,
)
from services.llm_service import create_llm_service
from utils.dialog import show_dialog, pop_dialog, show_snackbar
from utils.file_loader import sanitize_filename
from models.mistake import Mistake, SUBJECTS


class ExportView:
    """试卷导出页视图"""

    def __init__(self, app):
        self.app = app
        self.page = app.page
        self.settings = SettingsService.load()

        self.selected_ids: Set[str] = set()
        self.checkbox_list: Column = None
        self.selected_count_text: Text = None
        self.preview_panel: Container = None
        self.select_all_switch: Switch = None
        self.title_input: TextField = None
        self.include_solutions_switch: Switch = None
        self.loading_bar: ProgressBar = None
        self.progress_text: Text = None
        self.all_mistakes = []
        self._exporting = False

        # 字体设置控件
        self.font_cjk_input: TextField = None
        self.font_latin_input: TextField = None
        self.font_size_input: TextField = None
        self.line_spacing_input: TextField = None

        # 时间筛选
        self.date_start_input: TextField = None
        self.date_end_input: TextField = None

        # 科目/知识点多选筛选 (issue #5)
        self.filter_subjects: Set[str] = set()           # 选中的学科
        self.filter_tags: Set[str] = set()               # 选中的知识点
        self._subject_filter_popup = None
        self._tag_filter_popup = None
        self.subject_filter_btn: OutlinedButton = None
        self.tag_filter_btn: OutlinedButton = None
        self.filter_summary_text: Text = None

    def build(self):
        self.settings = SettingsService.load()
        self.all_mistakes = MistakeStorageService.load_all()

        header = Container(
            content=Column(
                controls=[
                    Text("试卷导出", size=30, weight=FontWeight.W_700),
                    Text("选择错题，一键生成精美试卷 (Word/PDF/HTML)",
                         size=15, color=Colors.ON_SURFACE_VARIANT),
                ],
                spacing=4,
            ),
            padding=ft.Padding.only(bottom=16),
        )

        left_panel = self._build_left_panel()
        right_panel = self._build_right_panel()

        main_layout = ft.ResponsiveRow(
            controls=[
                ft.Column([left_panel], col={"xs": 12, "md": 5, "lg": 4}),
                ft.Column([right_panel], col={"xs": 12, "md": 7, "lg": 8}),
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

    # -------------------- 左侧面板 --------------------
    def _build_left_panel(self) -> Card:
        self.select_all_switch = Switch(
            label="全选/取消全选",
            value=False,
            on_change=self._on_select_all,
        )

        # 时间筛选
        self.date_start_input = TextField(filled=True, fill_color=surface_input_color(self.page),
            label="起始日期 (YYYY-MM-DD)",
            value="",
            prefix_icon=Icons.DATE_RANGE,
            hint_text="留空则不限",
            width=160,
        )
        self.date_end_input = TextField(filled=True, fill_color=surface_input_color(self.page),
            label="结束日期 (YYYY-MM-DD)",
            value="",
            prefix_icon=Icons.DATE_RANGE,
            hint_text="留空则不限",
            width=160,
        )

        # 学科/知识点多选按钮 (issue #5)
        self.subject_filter_btn = OutlinedButton(
            "学科筛选 (0)",
            icon=Icons.FILTER_LIST,
            on_click=self._open_subject_filter,
        )
        self.tag_filter_btn = OutlinedButton(
            "知识点筛选 (0)",
            icon=Icons.LABEL_OUTLINE,
            on_click=self._open_tag_filter,
        )

        filter_btn = OutlinedButton(
            "应用筛选",
            icon=Icons.FILTER_ALT_OUTLINED,
            on_click=self._on_apply_filters,
        )

        # 筛选摘要
        self.filter_summary_text = Text(
            "", size=12, color=Colors.ON_SURFACE_VARIANT,
        )

        self.checkbox_list = Column(
            controls=[self._build_mistake_checkbox(m) for m in self.all_mistakes]
                     or [Text("暂无错题", color=Colors.ON_SURFACE_VARIANT)],
            spacing=4,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        self.title_input = TextField(filled=True, fill_color=surface_input_color(self.page),
            label="试卷标题",
            value="我的错题本",
        )

        self.include_solutions_switch = Switch(
            label="包含标准解析",
            value=True,
            on_change=lambda e: self._refresh_preview(),
        )

        # 导出按钮: Word / PDF / HTML (issue #6)
        export_docx_btn = ElevatedButton(
            "导出 Word",
            icon=Icons.DESCRIPTION,
            on_click=self._on_export_docx,
            width=140,
            disabled=self._exporting,
        )
        export_pdf_btn = ElevatedButton(
            "导出 PDF",
            icon=Icons.PICTURE_AS_PDF,
            on_click=self._on_export_pdf,
            width=140,
            style=ft.ButtonStyle(
                bgcolor=Colors.ERROR_CONTAINER,
                color=Colors.ON_ERROR_CONTAINER,
            ),
            disabled=self._exporting,
        )
        export_html_btn = ElevatedButton(
            "导出 HTML",
            icon=Icons.WEB,
            on_click=self._on_export_html,
            width=140,
            style=ft.ButtonStyle(
                bgcolor=Colors.TERTIARY_CONTAINER,
                color=Colors.ON_TERTIARY_CONTAINER,
            ),
            disabled=self._exporting,
        )

        self.loading_bar = ProgressBar(visible=False, color=Colors.PRIMARY)
        self.progress_text = Text(
            "", size=13, color=Colors.PRIMARY,
            weight=FontWeight.W_500, visible=False,
        )

        self.selected_count_text = Text(
            "已选 0 道", size=14, color=Colors.PRIMARY, weight=FontWeight.W_600,
        )

        # 字体设置
        self.font_cjk_input = TextField(filled=True, fill_color=surface_input_color(self.page),
            label="中文字体",
            value=self.settings.get("export_font_cjk", "宋体"),
            width=140,
        )
        self.font_latin_input = TextField(filled=True, fill_color=surface_input_color(self.page),
            label="英文字体",
            value=self.settings.get("export_font_latin", "Times New Roman"),
            width=160,
        )
        self.font_size_input = TextField(filled=True, fill_color=surface_input_color(self.page),
            label="字号",
            value=self.settings.get("export_font_size", "10.5pt"),
            width=100,
        )
        self.line_spacing_input = TextField(filled=True, fill_color=surface_input_color(self.page),
            label="行距",
            value=self.settings.get("export_line_spacing", "1.0"),
            width=80,
        )

        # 工具状态检测 (issue #7: 增加路径来源, 解决用户已装但显示未装)
        pandoc_ok = check_pandoc_installed()
        wkhtmltopdf_ok = check_wkhtmltopdf_installed()
        wk_path_display = ""
        if wkhtmltopdf_ok:
            try:
                wk_path_display = f" ({os.path.basename(get_wkhtmltopdf_path() or '')})"
            except Exception:
                wk_path_display = ""
        tool_status = Column(
            controls=[
                Divider(),
                Row([
                    Icon(Icons.CIRCLE, size=10,
                         color=Colors.TERTIARY if pandoc_ok else Colors.ERROR),
                    Text(f"Word 导出 (Pandoc): {'✓ 已安装' if pandoc_ok else '✗ 未安装'}",
                         size=12, color=Colors.ON_SURFACE_VARIANT),
                ], spacing=4),
                Row([
                    Icon(Icons.CIRCLE, size=10,
                         color=Colors.TERTIARY if wkhtmltopdf_ok else Colors.ERROR),
                    Text(f"PDF 导出 (wkhtmltopdf): {'✓ 已安装' if wkhtmltopdf_ok else '✗ 未安装'}{wk_path_display}",
                         size=12, color=Colors.ON_SURFACE_VARIANT),
                ], spacing=4),
                Row([
                    Icon(Icons.CIRCLE, size=10, color=Colors.TERTIARY),
                    Text("HTML 导出: ✓ 无需外部工具 (移动端推荐)",
                         size=12, color=Colors.ON_SURFACE_VARIANT),
                ], spacing=4),
            ],
            spacing=4,
        )

        # 平台信息提示 (issue #8)
        if is_mobile(self.page):
            platform_tip = Text(
                "📱 当前为移动端: 导出后会调起系统分享面板 (微信/QQ/AirDrop 等)",
                size=12, color=Colors.PRIMARY,
            )
        else:
            platform_tip = Text(
                "💻 当前为桌面端: 导出后会在文件管理器中定位文件",
                size=12, color=Colors.ON_SURFACE_VARIANT,
            )

        return Card(
            elevation=0.5,
            content=Container(
                content=Column(
                    controls=[
                        Row(
                            controls=[
                                Icon(Icons.FILTER_LIST, color=Colors.PRIMARY, size=24),
                                Text("选择错题", size=20, weight=FontWeight.W_600),
                            ],
                            spacing=8,
                        ),
                        Divider(),
                        # 时间筛选
                        Row([
                            Icon(Icons.DATE_RANGE, color=Colors.PRIMARY, size=20),
                            Text("按导入时间筛选", size=15, weight=FontWeight.W_600),
                        ], spacing=6),
                        Row([
                            self.date_start_input,
                            self.date_end_input,
                        ], spacing=8, wrap=True),
                        # 学科/知识点筛选 (issue #5)
                        Row([
                            Icon(Icons.CATEGORY, color=Colors.PRIMARY, size=20),
                            Text("按属性筛选 (可多选)", size=15, weight=FontWeight.W_600),
                        ], spacing=6),
                        Row([
                            self.subject_filter_btn,
                            self.tag_filter_btn,
                            filter_btn,
                        ], spacing=8, wrap=True),
                        self.filter_summary_text,
                        Divider(),
                        Container(
                            content=Row(
                                controls=[
                                    Text(f"共 {len(self.all_mistakes)} 道错题",
                                         size=14, color=Colors.ON_SURFACE_VARIANT),
                                    Container(width=10),
                                    self.selected_count_text,
                                ],
                                spacing=8,
                            ),
                            padding=ft.Padding.only(bottom=8),
                        ),
                        self.select_all_switch,
                        Container(
                            content=self.checkbox_list,
                            height=240,
                            padding=ft.Padding.only(left=4),
                        ),
                        Divider(),
                        self.title_input,
                        self.include_solutions_switch,
                        Divider(),
                        # 字体设置
                        Row([
                            Icon(Icons.TEXT_FIELDS, color=Colors.PRIMARY, size=22),
                            Text("字体设置", size=18, weight=FontWeight.W_600),
                        ], spacing=8),
                        Row([
                            self.font_cjk_input,
                            self.font_latin_input,
                        ], spacing=8, wrap=True),
                        Row([
                            self.font_size_input,
                            self.line_spacing_input,
                        ], spacing=8, wrap=True),
                        tool_status,
                        platform_tip,
                        Divider(),
                        Row([export_docx_btn, export_pdf_btn, export_html_btn],
                            spacing=8, wrap=True),
                        self.loading_bar,
                        self.progress_text,
                    ],
                    spacing=10,
                ),
                padding=ft.Padding.all(20),
            ),
        )

    def _build_mistake_checkbox(self, mistake: Mistake) -> Control:
        from services.latex_service import latex_to_plain_text
        preview = latex_to_plain_text(mistake.original_question or "(无题干)")
        if len(preview) > 50:
            preview = preview[:50] + "..."

        cb = Checkbox(
            value=False,
            on_change=lambda e, mid=mistake.id: self._on_checkbox_change(mid, e.control.value),
        )
        cb.data = mistake.id

        created_at_str = ""
        try:
            if mistake.created_at:
                dt = datetime.fromisoformat(mistake.created_at)
                created_at_str = dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass

        has_solution = bool(mistake.standard_solution)
        status = "✓ 已解析" if has_solution else "⏳ 待生成"

        return Container(
            content=Row(
                controls=[
                    cb,
                    Container(
                        content=Column(
                            controls=[
                                Text(preview, size=14, max_lines=2,
                                     overflow=ft.TextOverflow.ELLIPSIS),
                                Text(
                                    f"{mistake.subject or '未分类'} · {mistake.knowledge_tag or '无标签'} · {status} · {created_at_str}",
                                    size=12, color=Colors.ON_SURFACE_VARIANT,
                                ),
                            ],
                            spacing=2,
                        ),
                        expand=True,
                    ),
                ],
                spacing=8,
            ),
            padding=ft.Padding.symmetric(horizontal=4, vertical=4),
        )

    # -------------------- 多选筛选 (issue #5) --------------------
    def _open_subject_filter(self, e: ControlEvent):
        """打开学科多选筛选对话框"""
        available_subjects = sorted({m.subject or "未分类" for m in self.all_mistakes})
        if not available_subjects:
            available_subjects = SUBJECTS[:]

        checkboxes = []
        temp_state = set(self.filter_subjects)

        def on_change(ev, s):
            if ev.control.value:
                temp_state.add(s)
            else:
                temp_state.discard(s)

        for s in available_subjects:
            cb = Checkbox(
                label=s,
                value=(s in temp_state),
                on_change=lambda ev, s=s: on_change(ev, s),
            )
            checkboxes.append(cb)

        def on_apply(ev):
            self.filter_subjects = set(temp_state)
            self.subject_filter_btn.text = f"学科筛选 ({len(self.filter_subjects)})"
            pop_dialog(self.page)
            self.page.update()

        def on_clear(ev):
            temp_state.clear()
            for cb in checkboxes:
                cb.value = False
            self.page.update()

        dlg = AlertDialog(
            modal=True,
            title=Row([
                Icon(Icons.CATEGORY, color=Colors.PRIMARY, size=22),
                Text("学科筛选 (可多选)", weight=FontWeight.W_600, size=18),
            ], spacing=8),
            content=Container(
                content=Column(
                    controls=checkboxes or [Text("暂无学科数据")],
                    spacing=4, tight=True,
                    scroll=ft.ScrollMode.AUTO,
                ),
                width=300, height=400,
            ),
            actions=[
                OutlinedButton("清空", icon=Icons.CLEAR, on_click=on_clear),
                TextButton("取消", on_click=lambda ev: pop_dialog(self.page)),
                ElevatedButton("应用", icon=Icons.CHECK, on_click=on_apply,
                               style=ft.ButtonStyle(
                                   bgcolor=Colors.PRIMARY_CONTAINER,
                                   color=Colors.ON_PRIMARY_CONTAINER,
                               )),
            ],
            actions_alignment=MainAxisAlignment.END,
        )
        show_dialog(self.page, dlg)

    def _open_tag_filter(self, e: ControlEvent):
        """打开知识点多选筛选对话框"""
        available_tags = sorted({
            m.knowledge_tag for m in self.all_mistakes
            if m.knowledge_tag and m.knowledge_tag.strip()
        })
        if not available_tags:
            show_snackbar(self.page, "暂无可筛选的知识点标签")
            return

        checkboxes = []
        temp_state = set(self.filter_tags)

        def on_change(ev, t):
            if ev.control.value:
                temp_state.add(t)
            else:
                temp_state.discard(t)

        for t in available_tags:
            cb = Checkbox(
                label=t,
                value=(t in temp_state),
                on_change=lambda ev, t=t: on_change(ev, t),
            )
            checkboxes.append(cb)

        def on_apply(ev):
            self.filter_tags = set(temp_state)
            self.tag_filter_btn.text = f"知识点筛选 ({len(self.filter_tags)})"
            pop_dialog(self.page)
            self.page.update()

        def on_clear(ev):
            temp_state.clear()
            for cb in checkboxes:
                cb.value = False
            self.page.update()

        dlg = AlertDialog(
            modal=True,
            title=Row([
                Icon(Icons.LABEL_OUTLINE, color=Colors.PRIMARY, size=22),
                Text("知识点筛选 (可多选)", weight=FontWeight.W_600, size=18),
            ], spacing=8),
            content=Container(
                content=Column(
                    controls=checkboxes,
                    spacing=4, tight=True,
                    scroll=ft.ScrollMode.AUTO,
                ),
                width=320, height=400,
            ),
            actions=[
                OutlinedButton("清空", icon=Icons.CLEAR, on_click=on_clear),
                TextButton("取消", on_click=lambda ev: pop_dialog(self.page)),
                ElevatedButton("应用", icon=Icons.CHECK, on_click=on_apply,
                               style=ft.ButtonStyle(
                                   bgcolor=Colors.PRIMARY_CONTAINER,
                                   color=Colors.ON_PRIMARY_CONTAINER,
                               )),
            ],
            actions_alignment=MainAxisAlignment.END,
        )
        show_dialog(self.page, dlg)

    def _on_apply_filters(self, e: ControlEvent):
        """综合应用日期 + 学科 + 知识点筛选 (issue #5)"""
        start_str = (self.date_start_input.value or "").strip()
        end_str = (self.date_end_input.value or "").strip()

        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d") if start_str else None
            end_date = datetime.strptime(end_str, "%Y-%m-%d") if end_str else None
        except ValueError:
            show_snackbar(self.page, "日期格式错误，应为 YYYY-MM-DD", is_error=True)
            return

        # 重新加载列表
        self.all_mistakes = MistakeStorageService.load_all()
        filtered = []
        for m in self.all_mistakes:
            # 日期筛选
            try:
                m_date = datetime.fromisoformat(m.created_at) if m.created_at else None
            except (ValueError, TypeError):
                m_date = None
            if m_date is None:
                continue
            if start_date and m_date < start_date:
                continue
            if end_date and m_date > end_date.replace(
                hour=23, minute=59, second=59):
                continue
            # 学科筛选 (空集合 = 不过滤)
            if self.filter_subjects:
                subj = m.subject or "未分类"
                if subj not in self.filter_subjects:
                    continue
            # 知识点筛选
            if self.filter_tags:
                tag = m.knowledge_tag or ""
                if tag not in self.filter_tags:
                    continue
            filtered.append(m)

        # 更新 checkbox 列表
        self.checkbox_list.controls.clear()
        if not filtered:
            self.checkbox_list.controls.append(
                Container(
                    content=Column([
                        Icon(Icons.SEARCH_OFF, size=40, color=Colors.OUTLINE),
                        Text("未找到符合条件的错题", size=13,
                             color=Colors.ON_SURFACE_VARIANT),
                    ], horizontal_alignment=CrossAxisAlignment.CENTER, spacing=6),
                    alignment=ft.Alignment(0, 0),
                    padding=ft.Padding.all(20),
                )
            )
        else:
            for m in filtered:
                self.checkbox_list.controls.append(self._build_mistake_checkbox(m))
        # 更新筛选摘要
        parts = [f"日期: {start_str or '不限'} ~ {end_str or '不限'}"]
        if self.filter_subjects:
            parts.append(f"学科: {','.join(sorted(self.filter_subjects))}")
        if self.filter_tags:
            parts.append(f"知识点: {','.join(sorted(self.filter_tags))}")
        self.filter_summary_text.value = " | ".join(parts)
        self.page.update()
        show_snackbar(self.page, f"✓ 筛选出 {len(filtered)} 道错题")

    def _on_checkbox_change(self, mistake_id: str, checked: bool):
        if checked:
            self.selected_ids.add(mistake_id)
        else:
            self.selected_ids.discard(mistake_id)
        visible_ids = {c.data for c in self._visible_checkboxes()
                       if isinstance(c.data, str)}
        if visible_ids:
            self.select_all_switch.value = visible_ids <= self.selected_ids
        self._refresh_preview()
        self._update_selected_count()

    def _visible_checkboxes(self):
        for ctrl in self.checkbox_list.controls:
            if hasattr(ctrl, "content") and isinstance(ctrl.content, Row):
                for c in ctrl.content.controls:
                    if isinstance(c, Checkbox):
                        yield c

    def _on_select_all(self, e: ControlEvent):
        all_checked = e.control.value
        visible_ids = set()
        for ctrl in self.checkbox_list.controls:
            if hasattr(ctrl, "content") and isinstance(ctrl.content, Row):
                for c in ctrl.content.controls:
                    if isinstance(c, Checkbox):
                        c.value = all_checked
                        if isinstance(c.data, str):
                            visible_ids.add(c.data)
        if all_checked:
            self.selected_ids = visible_ids
        else:
            self.selected_ids -= visible_ids
        self._refresh_preview()
        self._update_selected_count()
        self.page.update()

    def _update_selected_count(self):
        if self.selected_count_text:
            self.selected_count_text.value = f"已选 {len(self.selected_ids)} 道"
            self.page.update()

    # -------------------- 右侧预览 (HTML 嵌入) --------------------
    def _build_right_panel(self) -> Card:
        self.preview_panel = Container(
            content=self._build_preview_content(),
            expand=True,
        )
        # 预览 HTML 按钮 (issue #5): 把渲染好的 HTML 保存到临时文件,
        # 通过 UrlLauncher 在浏览器/WebView 打开
        preview_html_btn = OutlinedButton(
            "🌐 在浏览器预览 HTML",
            icon=Icons.OPEN_IN_BROWSER,
            on_click=self._on_preview_html,
        )
        refresh_btn = OutlinedButton(
            "刷新预览",
            icon=Icons.REFRESH,
            on_click=lambda e: self._refresh_preview(),
        )
        return Card(
            elevation=0.5,
            content=Container(
                content=Column(
                    controls=[
                        Row(
                            controls=[
                                Icon(Icons.PREVIEW, color=Colors.PRIMARY, size=24),
                                Text("预览", size=20, weight=FontWeight.W_600),
                                Container(
                                    content=Text("HTML 实时渲染",
                                                 size=11,
                                                 color=Colors.ON_TERTIARY_CONTAINER),
                                    padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                                    bgcolor=Colors.TERTIARY_CONTAINER,
                                    border_radius=10,
                                ),
                                Container(expand=True),
                                refresh_btn,
                                preview_html_btn,
                            ],
                            spacing=8,
                        ),
                        Divider(),
                        Container(
                            content=self.preview_panel,
                            height=600,
                            bgcolor=Colors.SURFACE_CONTAINER_HIGHEST,
                            border_radius=12,
                            padding=ft.Padding.all(8),
                        ),
                    ],
                    spacing=12,
                ),
                padding=ft.Padding.all(20),
            ),
        )

    def _build_preview_content(self) -> Control:
        selected = [m for m in self.all_mistakes if m.id in self.selected_ids]

        if not selected:
            return Container(
                content=Column(
                    controls=[
                        Icon(Icons.PREVIEW, size=56, color=Colors.OUTLINE),
                        Text("请从左侧选择错题进行预览",
                             size=14, color=Colors.ON_SURFACE_VARIANT),
                    ],
                    horizontal_alignment=CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
                alignment=ft.Alignment(0, 0),
                padding=ft.Padding.all(40),
            )

        title = self.title_input.value or "错题本"
        # 用 Markdown 预览 (与原版一致, 保留 $...$ 让 Flet Markdown 原生渲染 LaTeX)
        md_str = mistakes_to_markdown(selected, title=title)
        # 去除 YAML front matter (避免预览显示 title:/fontsize: 等)
        md_clean = markdown_to_preview(md_str)

        # issue #5: 预览栏字号略小一点 (size=13, latex_scale_factor=0.9)
        return ft.ListView(
            controls=[
                Container(
                    content=Markdown(
                        value=md_clean,
                        selectable=True,
                        extension_set=MarkdownExtensionSet.GITHUB_WEB,
                        auto_follow_links=True,
                        soft_line_break=True,
                        latex_scale_factor=0.9,
                        latex_style=ft.TextStyle(
                            color=ft.Colors.ON_SURFACE,
                            size=13,
                        ),
                    ),
                    padding=ft.Padding.all(8),
                ),
            ],
            expand=True,
        )

    async def _on_preview_html(self, e: ControlEvent):
        """预览 HTML: 保存到临时文件, 调起系统浏览器/WebView 打开"""
        selected = self._get_selected_mistakes()
        if not selected:
            show_snackbar(self.page, "请先选择错题", is_error=True)
            return
        title = self.title_input.value or "错题本预览"
        safe_title = sanitize_filename(title)
        html_str = mistakes_to_html(
            selected, title=title,
            include_solutions=bool(self.include_solutions_switch.value),
            font_cjk=(self.font_cjk_input.value or "宋体"),
            font_latin=(self.font_latin_input.value or "Times New Roman"),
            font_size=(self.font_size_input.value or "10.5pt"),
            line_spacing=(self.line_spacing_input.value or "1.0"),
        )
        # 保存到缓存目录
        os.makedirs(str(CACHE_DIR), exist_ok=True)
        tmp_path = str(CACHE_DIR / f"preview_{safe_title}.html")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(html_str)
        except Exception as ex:
            show_snackbar(self.page, f"预览文件保存失败: {ex}", is_error=True)
            return
        # 调起浏览器/WebView 打开
        url = to_file_uri(tmp_path)
        ok = await share_or_open_async(
            self.page, tmp_path,
            title="预览 HTML",
            open_in_browser=True,
        )
        if not ok:
            show_snackbar(self.page, "当前平台不支持预览, 文件已保存到: " + tmp_path)
        else:
            show_snackbar(self.page, f"✓ 已在浏览器打开预览: {tmp_path}")

    def _refresh_preview(self):
        self.preview_panel.content = self._build_preview_content()
        self.page.update()

    # -------------------- 导出操作 --------------------
    def _set_exporting(self, busy: bool, msg: str = "", percent: float = 0.0):
        from utils.run_guard import debug_log, Watchdog
        self._exporting = busy
        if busy:
            debug_log(f"[export] BUSY ON: {msg}")
            if not hasattr(self, "_export_watchdog") or self._export_watchdog is None:
                self._export_watchdog = Watchdog(
                    lambda: self._set_exporting(False), timeout=300, name="导出")
                self._export_watchdog.arm()
        else:
            debug_log("[export] BUSY OFF")
            wd = getattr(self, "_export_watchdog", None)
            if wd is not None:
                wd.disarm()
                self._export_watchdog = None
        self.loading_bar.visible = busy
        if busy:
            pct = int(percent * 100)
            self.progress_text.value = f"{msg} ({pct}%)"
            self.progress_text.visible = True
        else:
            self.progress_text.visible = False
        self.page.update()

    async def _on_export_docx(self, e: ControlEvent):
        if self._exporting:
            return
        if is_mobile(self.page):
            show_snackbar(self.page, "移动端不支持 Word 导出, 请用 HTML 导出", is_error=True)
            return
        selected = self._get_selected_mistakes()
        if not selected:
            show_snackbar(self.page, "请先选择错题", is_error=True)
            return

        no_solution = [m for m in selected if not m.standard_solution]
        if no_solution and self.include_solutions_switch.value:
            proceed, generate = await self._ask_generate_solutions(len(no_solution))
            if not proceed:
                return
        else:
            generate = False

        raw_title = self.title_input.value or "错题本"
        title = sanitize_filename(raw_title)
        export_dir = (self.settings.get("export_path") or get_default_export_dir()).strip()
        from utils.file_picker_helper import save_file_async
        output_path = await save_file_async(
            self.page,
            dialog_title="保存 Word 文件",
            file_name=f"{title}.docx",
            initial_directory=export_dir,
            allowed_extensions=["docx"],
        )
        if not output_path:
            return

        font_cjk = (self.font_cjk_input.value or "宋体").strip()
        font_latin = (self.font_latin_input.value or "Times New Roman").strip()
        font_size = (self.font_size_input.value or "10.5pt").strip()
        line_spacing = (self.line_spacing_input.value or "1.0").strip()
        include_sol = self.include_solutions_switch.value

        self._set_exporting(True, "准备导出...", 0.0)

        def _do_export():
            try:
                if generate:
                    self.page.run_thread(lambda: self._set_exporting(
                        True, "正在调用 AI 生成解析", 0.1))
                    self._generate_solutions_for_mistakes(selected,
                        lambda msg, pct: self.page.run_thread(
                            lambda: self._set_exporting(True, msg, pct)))

                def _progress(msg, pct):
                    self.page.run_thread(lambda: self._set_exporting(True, msg, pct))

                export_to_docx(selected, output_path, title=title,
                                font_cjk=font_cjk, font_latin=font_latin,
                                font_size=font_size, line_spacing=line_spacing,
                                include_solutions=bool(include_sol),
                                progress_callback=_progress)

                def _on_success():
                    self._set_exporting(False)
                    show_snackbar(self.page, f"✓ 已导出: {output_path}")
                    self._show_export_success_dialog(output_path, "Word")
                self.page.run_thread(_on_success)
            except Exception as ex:
                def _on_error(err=ex):
                    self._set_exporting(False)
                    show_snackbar(self.page, f"导出失败: {err}", is_error=True)
                    self._show_error_dialog(str(err))
                self.page.run_thread(_on_error)

        self.page.run_thread(_do_export)

    async def _on_export_pdf(self, e: ControlEvent):
        if self._exporting:
            return
        if is_mobile(self.page):
            show_snackbar(self.page, "移动端不支持 PDF 导出, 请用 HTML 导出", is_error=True)
            return
        selected = self._get_selected_mistakes()
        if not selected:
            show_snackbar(self.page, "请先选择错题", is_error=True)
            return

        no_solution = [m for m in selected if not m.standard_solution]
        if no_solution and self.include_solutions_switch.value:
            proceed, generate = await self._ask_generate_solutions(len(no_solution))
            if not proceed:
                return
        else:
            generate = False

        raw_title = self.title_input.value or "错题本"
        title = sanitize_filename(raw_title)
        export_dir = (self.settings.get("export_path") or get_default_export_dir()).strip()
        from utils.file_picker_helper import save_file_async
        output_path = await save_file_async(
            self.page,
            dialog_title="保存 PDF 文件",
            file_name=f"{title}.pdf",
            initial_directory=export_dir,
            allowed_extensions=["pdf"],
        )
        if not output_path:
            return

        include_sol = self.include_solutions_switch.value
        font_cjk = (self.font_cjk_input.value or "宋体").strip()
        font_latin = (self.font_latin_input.value or "Times New Roman").strip()
        font_size = (self.font_size_input.value or "10.5pt").strip()
        line_spacing = (self.line_spacing_input.value or "1.0").strip()

        self._set_exporting(True, "准备导出...", 0.0)

        def _do_export():
            try:
                if generate:
                    self.page.run_thread(lambda: self._set_exporting(
                        True, "正在调用 AI 生成解析", 0.1))
                    self._generate_solutions_for_mistakes(selected,
                        lambda msg, pct: self.page.run_thread(
                            lambda: self._set_exporting(True, msg, pct)))

                def _progress(msg, pct):
                    self.page.run_thread(lambda: self._set_exporting(True, msg, pct))

                export_to_pdf(selected, output_path, title=title,
                              include_solutions=include_sol,
                              font_cjk=font_cjk, font_latin=font_latin,
                              font_size=font_size, line_spacing=line_spacing,
                              progress_callback=_progress)

                def _on_success():
                    self._set_exporting(False)
                    show_snackbar(self.page, f"✓ 已导出: {output_path}")
                    self._show_export_success_dialog(output_path, "PDF")
                self.page.run_thread(_on_success)
            except Exception as ex:
                def _on_error(err=ex):
                    self._set_exporting(False)
                    show_snackbar(self.page, f"导出失败: {err}", is_error=True)
                    self._show_error_dialog(str(err))
                self.page.run_thread(_on_error)

        self.page.run_thread(_do_export)

    async def _on_export_html(self, e: ControlEvent):
        """导出 HTML (issue #6) - 桌面端保存到本地, 移动端保存后调起分享"""
        if self._exporting:
            return
        selected = self._get_selected_mistakes()
        if not selected:
            show_snackbar(self.page, "请先选择错题", is_error=True)
            return

        no_solution = [m for m in selected if not m.standard_solution]
        if no_solution and self.include_solutions_switch.value:
            proceed, generate = await self._ask_generate_solutions(len(no_solution))
            if not proceed:
                return
        else:
            generate = False

        raw_title = self.title_input.value or "错题本"
        title = sanitize_filename(raw_title)
        include_sol = self.include_solutions_switch.value
        font_cjk = (self.font_cjk_input.value or "宋体").strip()
        font_latin = (self.font_latin_input.value or "Times New Roman").strip()
        font_size = (self.font_size_input.value or "10.5pt").strip()
        line_spacing = (self.line_spacing_input.value or "1.0").strip()

        # 桌面端: 让用户选保存位置; 移动端: 自动保存到 app 文档目录
        if is_desktop(self.page):
            export_dir = (self.settings.get("export_path") or get_default_export_dir()).strip()
            from utils.file_picker_helper import save_file_async
            output_path = await save_file_async(
                self.page,
                dialog_title="保存 HTML 文件",
                file_name=f"{title}.html",
                initial_directory=export_dir,
                allowed_extensions=["html", "htm"],
            )
            if not output_path:
                return
        else:
            # 移动端/Web: 保存到 cache 目录, 之后调起系统分享
            try:
                docs_dir = str(CACHE_DIR)
            except Exception:
                docs_dir = tempfile.gettempdir()
            os.makedirs(docs_dir, exist_ok=True)
            output_path = os.path.join(docs_dir, f"{title}.html")

        self._set_exporting(True, "准备导出...", 0.0)

        def _do_export():
            try:
                if generate:
                    self.page.run_thread(lambda: self._set_exporting(
                        True, "正在调用 AI 生成解析", 0.1))
                    self._generate_solutions_for_mistakes(selected,
                        lambda msg, pct: self.page.run_thread(
                            lambda: self._set_exporting(True, msg, pct)))

                def _progress(msg, pct):
                    self.page.run_thread(lambda: self._set_exporting(True, msg, pct))

                export_to_html(selected, output_path, title=title,
                                include_solutions=include_sol,
                                font_cjk=font_cjk, font_latin=font_latin,
                                font_size=font_size, line_spacing=line_spacing,
                                progress_callback=_progress)

                def _on_success():
                    self._set_exporting(False)
                    show_snackbar(self.page, f"✓ 已导出: {output_path}")
                    # issue #8: 桌面端打开文件管理器; 移动端调起系统分享
                    async def _share():
                        await share_or_open_async(
                            self.page, output_path,
                            title=f"已导出 HTML: {title}",
                            open_in_browser=True,
                        )
                    self.page.run_task(_share)
                self.page.run_thread(_on_success)
            except Exception as ex:
                def _on_error(err=ex):
                    self._set_exporting(False)
                    show_snackbar(self.page, f"导出失败: {err}", is_error=True)
                    self._show_error_dialog(str(err))
                self.page.run_thread(_on_error)

        self.page.run_thread(_do_export)

    async def _ask_generate_solutions(self, count: int) -> Tuple[bool, bool]:
        future = asyncio.Future()

        dlg = AlertDialog(
            modal=True,
            title=Row([
                Icon(Icons.HELP_OUTLINE, color=Colors.PRIMARY, size=22),
                Text(f"发现 {count} 道无解析错题", weight=FontWeight.W_600, size=18),
            ], spacing=8),
            content=ft.Container(
                content=Text(
                    f"您选择的错题中有 {count} 道尚未生成标准解析。\n"
                    f"导出时如何处理？",
                    size=14,
                ),
                width=min(400, (self.page.window.width or 1280) - 64),
                padding=ft.Padding.symmetric(vertical=4, horizontal=4),
            ),
            actions=[
                TextButton(
                    "取消导出",
                    on_click=lambda e: self._resolve_ask(future, False, False, dlg),
                ),
                OutlinedButton(
                    "不生成 (导出为\"无解析\")",
                    on_click=lambda e: self._resolve_ask(future, True, False, dlg),
                ),
                ElevatedButton(
                    "调用 AI 生成解析",
                    icon=Icons.AUTO_AWESOME,
                    on_click=lambda e: self._resolve_ask(future, True, True, dlg),
                    style=ft.ButtonStyle(
                        bgcolor=Colors.PRIMARY_CONTAINER,
                        color=Colors.ON_PRIMARY_CONTAINER,
                    ),
                ),
            ],
            actions_alignment=MainAxisAlignment.END,
        )
        show_dialog(self.page, dlg)

        result = await future
        return result

    def _resolve_ask(self, future, proceed: bool, generate: bool, dlg):
        pop_dialog(self.page)
        if not future.done():
            future.set_result((proceed, generate))

    def _generate_solutions_for_mistakes(self, mistakes: list, progress_cb=None):
        llm = None
        no_solution = [m for m in mistakes if not m.standard_solution]
        total = len(no_solution)
        for i, m in enumerate(no_solution):
            try:
                if progress_cb:
                    progress_cb(f"正在生成解析 ({i+1}/{total})", 0.1 + 0.6 * (i+1) / total)
                image_path = m.enhanced_image or m.original_image
                purpose = "ocr" if image_path else "solution"
                llm = create_llm_service(self.settings, purpose=purpose)
                solution = llm.generate_solution_only(
                    question=m.original_question,
                    knowledge_tag=m.knowledge_tag,
                    image_path=image_path if image_path else None,
                )
                if solution:
                    m.standard_solution = solution
                    MistakeStorageService.update(m)
            except Exception as ex:
                print(f"[export] 生成解析失败 (mistake {m.id[:8]}): {ex}")
                m.standard_solution = "(无解析)"

    def _get_selected_mistakes(self) -> list:
        return sorted(
            [m for m in self.all_mistakes if m.id in self.selected_ids],
            key=lambda m: (m.subject or "其他", m.created_at),
        )

    def _show_export_success_dialog(self, file_path: str, fmt: str):
        """导出成功对话框: 桌面端展示"打开文件夹"按钮; 移动端展示"分享"按钮"""
        from utils.platform_helper import share_or_open_async, is_mobile

        def _open_or_share(ev):
            pop_dialog(self.page)
            async def _do():
                await share_or_open_async(
                    self.page, file_path,
                    title=f"已导出 {fmt} 文件",
                    open_in_browser=(fmt.upper() == "HTML"),
                )
            self.page.run_task(_do)

        actions = [
            TextButton("关闭", on_click=lambda e: pop_dialog(self.page)),
            ElevatedButton(
                "📁 打开文件位置" if not is_mobile(self.page) else "📤 分享文件",
                icon=Icons.FOLDER_OPEN if not is_mobile(self.page) else Icons.SHARE,
                on_click=_open_or_share,
                style=ft.ButtonStyle(
                    bgcolor=Colors.PRIMARY_CONTAINER,
                    color=Colors.ON_PRIMARY_CONTAINER,
                ),
            ),
        ]
        dlg = AlertDialog(
            modal=True,
            title=Row([
                Icon(Icons.CHECK_CIRCLE, color=Colors.TERTIARY, size=24),
                Text(f"{fmt} 导出成功", weight=FontWeight.W_600, size=18),
            ], spacing=8),
            content=ft.Container(
                content=Column([
                    Text("文件已保存到：", size=13,
                         color=Colors.ON_SURFACE_VARIANT),
                    Container(
                        content=Text(file_path, size=13, selectable=True,
                                     max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                        padding=ft.Padding.symmetric(horizontal=8, vertical=6),
                        bgcolor=Colors.SURFACE_CONTAINER_HIGHEST,
                        border_radius=6,
                    ),
                ], spacing=6, tight=True),
                width=min(420, (self.page.window.width or 1280) - 80),
                padding=ft.Padding.symmetric(vertical=4, horizontal=2),
            ),
            actions=actions,
            actions_alignment=MainAxisAlignment.END,
        )
        show_dialog(self.page, dlg)

    def _show_error_dialog(self, error: str):
        dlg = AlertDialog(
            modal=True,
            title=Row([
                Icon(Icons.ERROR, color=Colors.ERROR, size=24),
                Text("导出失败", weight=FontWeight.W_600, size=18),
            ], spacing=8),
            content=ft.Container(
                content=Column([
                    Text("详细错误：", size=13, color=Colors.ON_SURFACE_VARIANT),
                    Container(
                        content=Text(error, size=13, selectable=True,
                                     max_lines=4, overflow=ft.TextOverflow.ELLIPSIS),
                        padding=ft.Padding.symmetric(horizontal=8, vertical=6),
                        bgcolor=Colors.ERROR_CONTAINER,
                        border_radius=6,
                    ),
                    Divider(),
                    Text(
                        "提示：\n"
                        "• Word 导出需 Pandoc (项目内 tools/Pandoc/)\n"
                        "• PDF 导出需 wkhtmltopdf (项目内 tools/wkhtmltox/bin/)\n"
                        "• HTML 导出无需外部工具 (移动端推荐)",
                        size=12, color=Colors.ON_SURFACE_VARIANT,
                    ),
                ], spacing=6, tight=True),
                width=min(420, (self.page.window.width or 1280) - 80),
                padding=ft.Padding.symmetric(vertical=4, horizontal=2),
            ),
            actions=[
                TextButton("关闭", on_click=lambda e: pop_dialog(self.page)),
            ],
        )
        show_dialog(self.page, dlg)
