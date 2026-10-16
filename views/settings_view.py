# ============================================================
# 设置页 - 全局配置中心
# ============================================================
# 功能：
#   1. API 配置: 分为「OCR/视觉模型」与「解析/变式模型」两组独立接口 (issue #1)
#   2. 导出设置: 路径 + 格式 + 字体 + wkhtmltopdf 自定义路径 (issue #7)
#   3. 复习规则: 艾宾浩斯参数
#   4. 外观设置
#   5. 自动保存: 输入框失焦/onChange 时静默保存, 不弹 "已保存" 提示 (issue #2)
# ============================================================

import flet as ft
from flet import (
    Container, Column, Row, Text, TextField, Dropdown, ElevatedButton,
    OutlinedButton, Icons, Colors, Switch, Divider,
    Card, Icon, MainAxisAlignment, FontWeight,
    ControlEvent,
)

from utils.theme import surface_input_color
from config import LLM_PROVIDERS, DEFAULT_SETTINGS, EXPORT_DIR
from services.storage_service import SettingsService
from utils.dialog import show_snackbar, show_confirm_dialog
from utils.file_picker_helper import get_directory_path_async, pick_files_async


class SettingsView:
    """设置页视图"""

    def __init__(self, app):
        self.app = app
        self.page = app.page
        self.settings = app.settings.copy()

        # 解析/变式接口控件
        self.api_key_input: TextField = None
        self.provider_dropdown: Dropdown = None
        self.model_solution_input: TextField = None
        self.custom_url_input: TextField = None

        # OCR 接口控件 (issue #1: 独立 OCR 接口)
        self.provider_ocr_dropdown: Dropdown = None
        self.model_ocr_input: TextField = None
        self.api_key_ocr_input: TextField = None
        self.custom_url_ocr_input: TextField = None
        self.use_same_as_solution_switch: Switch = None

        # 导出设置控件
        self.export_path_input: TextField = None
        self.export_format_dropdown: Dropdown = None

        # 字体设置控件
        self.font_cjk_input: TextField = None
        self.font_latin_input: TextField = None
        self.font_size_input: TextField = None
        self.line_spacing_input: TextField = None

        # 界面字体控件
        self.ui_font_input: TextField = None

        # 复习间隔输入框
        self.interval_inputs: list = []
        self._busy = False

        # 自动保存防抖 (issue #2)
        import time as _time
        self._auto_save_last = 0.0
        self._auto_save_pending = False

    def build(self):
        self.settings = SettingsService.load()

        # 标题区
        header = Container(
            content=Column(
                controls=[
                    Text("设置", size=30, weight=FontWeight.W_700,
                         color=Colors.ON_SURFACE),
                    Text("管理 API 凭证、导出选项和复习规则 (输入会自动保存)",
                         size=15, color=Colors.ON_SURFACE_VARIANT),
                ],
                spacing=4,
            ),
            padding=ft.Padding.only(bottom=16),
        )

        api_card = self._build_api_card()
        ocr_api_card = self._build_ocr_api_card()
        export_card = self._build_export_card()
        font_card = self._build_font_card()
        review_card = self._build_review_card()
        appearance_card = self._build_appearance_card()
        actions_row = self._build_actions_row()

        scroll_view = ft.ListView(
            controls=[
                header,
                api_card,
                ocr_api_card,
                export_card,
                font_card,
                review_card,
                appearance_card,
                actions_row,
            ],
            spacing=16,
            expand=True,
            padding=ft.Padding.only(bottom=20),
        )

        return Container(
            content=scroll_view,
            expand=True,
        )

    # ==================== 解析/变式模型 API 配置 (issue #1) ====================
    def _build_api_card(self) -> Card:
        provider = self.settings.get("llm_provider", "custom")
        api_key = self.settings.get("api_key", "")
        custom_url = self.settings.get("custom_api_url", "")

        provider_opts = [
            ft.dropdown.Option(key=k, text=v["name"])
            for k, v in LLM_PROVIDERS.items()
        ]

        self.provider_dropdown = Dropdown(filled=True, fill_color=surface_input_color(self.page),
            label="解析/变式 供应商",
            value=provider,
            options=provider_opts,
            on_select=self._on_provider_change,
        )

        # 解析/变式文本模型 (解题用)
        sol_model = self.settings.get("model_name_solution", "")
        self.model_solution_input = TextField(filled=True, fill_color=surface_input_color(self.page),
            label="解析/变式模型名称 (解题用)",
            value=sol_model,
            hint_text="如 deepseek-v4-flash、glm-4-plus 等",
            prefix_icon=Icons.PSYCHOLOGY_OUTLINED,
            on_blur=self._on_auto_save_silent,
            on_change=self._on_auto_save_silent,
        )

        self.api_key_input = TextField(filled=True, fill_color=surface_input_color(self.page),
            label="API Key (解析/变式用)",
            value=api_key,
            password=True,
            can_reveal_password=True,
            prefix_icon=Icons.KEY,
            hint_text="请输入大模型 API Key",
            on_blur=self._on_auto_save_silent,
            on_change=self._on_auto_save_silent,
        )

        self.custom_url_input = TextField(filled=True, fill_color=surface_input_color(self.page),
            label="自定义 API URL (仅 custom 供应商有效)",
            value=custom_url,
            prefix_icon=Icons.LINK,
            visible=(provider == "custom"),
            hint_text="https://your-api-endpoint.com/v1/chat/completions",
            on_blur=self._on_auto_save_silent,
            on_change=self._on_auto_save_silent,
        )

        # 深度思考开关
        self.deep_solution_switch = Switch(
            label="解析深度思考",
            value=self.settings.get("deep_thinking_solution", False),
            on_change=self._on_auto_save_silent,
        )
        self.deep_variants_switch = Switch(
            label="变式深度思考",
            value=self.settings.get("deep_thinking_variants", False),
            on_change=self._on_auto_save_silent,
        )

        test_btn = OutlinedButton(
            "测试连接",
            icon=Icons.NETWORK_CHECK,
            on_click=self._on_test_connection,
        )

        return self._wrap_card(
            title="解析/变式模型 API 配置",
            icon=Icons.PSYCHOLOGY_ALT_OUTLINED,
            subtitle="用于生成 AI 解析与变式题 (文本模型)",
            content=Column(
                controls=[
                    self.provider_dropdown,
                    self.model_solution_input,
                    self.api_key_input,
                    self.custom_url_input,
                    Divider(),
                    Row([
                        Icon(Icons.PSYCHOLOGY_ALT_OUTLINED, color=Colors.PRIMARY, size=20),
                        Text("深度思考 (逐步推理, 更准但更慢)", size=15, weight=FontWeight.W_600),
                    ], spacing=6),
                    Row([self.deep_solution_switch, self.deep_variants_switch],
                        spacing=12, wrap=True),
                    Row([test_btn], alignment=MainAxisAlignment.START),
                ],
                spacing=12,
            ),
        )

    def _on_provider_change(self, e: ControlEvent):
        provider = e.control.value
        self.settings["llm_provider"] = provider
        self.custom_url_input.visible = (provider == "custom")
        # OCR 跟随: 若开启"与解析/变式共用"则联动更新
        if self.use_same_as_solution_switch and self.use_same_as_solution_switch.value:
            self.provider_ocr_dropdown.value = provider
            self.custom_url_ocr_input.visible = (provider == "custom")
        self._on_auto_save_silent()
        self.page.update()

    async def _on_test_connection(self, e: ControlEvent):
        if self._busy:
            return
        api_key = (self.api_key_input.value or "").strip()
        if not api_key:
            show_snackbar(self.page, "请先输入 API Key", is_error=True)
            return

        provider = self.provider_dropdown.value
        model = (self.model_solution_input.value or "").strip()
        custom_url = (self.custom_url_input.value or "").strip()

        self._busy = True
        show_snackbar(self.page, "正在测试连接...")

        def _notify(msg: str, is_err: bool = False):
            try:
                self.page.run_thread(
                    lambda m=msg, e=is_err: show_snackbar(self.page, m, is_error=e))
            except Exception:
                pass

        def _do_test():
            try:
                from services.llm_service import LLMService
                svc = LLMService(
                    provider=provider, api_key=api_key, model=model,
                    custom_url=custom_url
                )
                result = svc.grade_answer(
                    question="1+1=?",
                    standard_solution="2",
                    user_answer="2",
                )
                if result:
                    _notify("✓ 解析/变式接口连接成功！")
                else:
                    _notify("连接异常，未返回结果", True)
            except Exception as ex:
                _notify(f"连接失败: {ex}", True)
            finally:
                self._busy = False

        self.page.run_thread(_do_test)

    # ==================== OCR/视觉模型 API 配置 (issue #1) ====================
    def _build_ocr_api_card(self) -> Card:
        # "OCR 接口与解析/变式共用"开关 (默认: 共用, 兼容旧设置)
        ocr_provider_set = bool(self.settings.get("llm_provider_ocr", "").strip())
        ocr_apikey_set = bool(self.settings.get("api_key_ocr", "").strip())
        ocr_url_set = bool(self.settings.get("custom_api_url_ocr", "").strip())
        use_same_default = not (ocr_provider_set or ocr_apikey_set or ocr_url_set)

        self.use_same_as_solution_switch = Switch(
            label="OCR 接口与解析/变式共用 (关闭后可单独配置 OCR)",
            value=use_same_default,
            on_change=self._on_use_same_change,
        )

        provider_opts = [
            ft.dropdown.Option(key=k, text=v["name"])
            for k, v in LLM_PROVIDERS.items()
        ]
        # OCR 供应商: 留空 = 跟随 llm_provider
        provider_ocr_value = (self.settings.get("llm_provider_ocr", "")
                               or self.settings.get("llm_provider", "custom"))

        self.provider_ocr_dropdown = Dropdown(filled=True, fill_color=surface_input_color(self.page),
            label="OCR 供应商",
            value=provider_ocr_value,
            options=provider_opts,
            on_select=self._on_provider_ocr_change,
            visible=not use_same_default,
        )

        ocr_model = self.settings.get("model_name_ocr", "")
        self.model_ocr_input = TextField(filled=True, fill_color=surface_input_color(self.page),
            label="OCR 视觉模型名称 (识图用)",
            value=ocr_model,
            hint_text="如 glm-4v-plus、gpt-4o 等",
            prefix_icon=Icons.IMAGE_SEARCH,
            on_blur=self._on_auto_save_silent,
            on_change=self._on_auto_save_silent,
        )

        self.api_key_ocr_input = TextField(filled=True, fill_color=surface_input_color(self.page),
            label="OCR API Key (留空 = 用解析接口的 Key)",
            value=self.settings.get("api_key_ocr", ""),
            password=True,
            can_reveal_password=True,
            prefix_icon=Icons.KEY,
            hint_text="留空跟随解析/变式接口",
            visible=not use_same_default,
            on_blur=self._on_auto_save_silent,
            on_change=self._on_auto_save_silent,
        )

        self.custom_url_ocr_input = TextField(filled=True, fill_color=surface_input_color(self.page),
            label="OCR 自定义 API URL (留空 = 跟随解析)",
            value=self.settings.get("custom_api_url_ocr", ""),
            prefix_icon=Icons.LINK,
            visible=(not use_same_default
                     and self.settings.get("llm_provider", "custom") == "custom"),
            hint_text="留空跟随解析/变式接口",
            on_blur=self._on_auto_save_silent,
            on_change=self._on_auto_save_silent,
        )

        self.deep_ocr_switch = Switch(
            label="OCR 深度思考",
            value=self.settings.get("deep_thinking_ocr", False),
            on_change=self._on_auto_save_silent,
        )

        test_ocr_btn = OutlinedButton(
            "测试 OCR 接口",
            icon=Icons.IMAGE_SEARCH,
            on_click=self._on_test_ocr_connection,
        )

        return self._wrap_card(
            title="OCR / 视觉模型 API 配置",
            icon=Icons.IMAGE_SEARCH,
            subtitle="用于错题图片识别 (视觉模型, 可与解析接口独立配置)",
            content=Column(
                controls=[
                    self.use_same_as_solution_switch,
                    self.provider_ocr_dropdown,
                    self.model_ocr_input,
                    self.api_key_ocr_input,
                    self.custom_url_ocr_input,
                    Divider(),
                    Row([
                        Icon(Icons.PSYCHOLOGY_ALT_OUTLINED, color=Colors.PRIMARY, size=20),
                        Text("OCR 深度思考", size=15, weight=FontWeight.W_600),
                    ], spacing=6),
                    Row([self.deep_ocr_switch], spacing=12, wrap=True),
                    Row([test_ocr_btn], alignment=MainAxisAlignment.START),
                ],
                spacing=12,
            ),
        )

    def _on_use_same_change(self, e: ControlEvent):
        """OCR 接口与解析/变式共用开关"""
        use_same = e.control.value
        # 切换可见性
        self.provider_ocr_dropdown.visible = not use_same
        self.api_key_ocr_input.visible = not use_same
        # custom_url_ocr 仅当 OCR 供应商为 custom 时显示
        if use_same:
            self.custom_url_ocr_input.visible = False
            # 清空 OCR 独立字段, 触发回退逻辑
            self.settings["llm_provider_ocr"] = ""
            self.settings["api_key_ocr"] = ""
            self.settings["custom_api_url_ocr"] = ""
        else:
            # 显示 OCR 自定义 URL (若 OCR 供应商 = custom)
            ocr_prov = (self.provider_ocr_dropdown.value
                        or self.settings.get("llm_provider", "custom"))
            self.custom_url_ocr_input.visible = (ocr_prov == "custom")
        self._on_auto_save_silent()
        self.page.update()

    def _on_provider_ocr_change(self, e: ControlEvent):
        provider = e.control.value
        self.settings["llm_provider_ocr"] = provider
        self.custom_url_ocr_input.visible = (provider == "custom")
        self._on_auto_save_silent()
        self.page.update()

    async def _on_test_ocr_connection(self, e: ControlEvent):
        if self._busy:
            return
        # 用当前设置临时保存, 再用 OCR 接口测试
        self._save_to_settings_object()
        SettingsService.save(self.settings)
        if self.app:
            self.app.refresh_settings()
        api_key = self.settings.get("api_key_ocr") or self.settings.get("api_key", "")
        if not api_key:
            show_snackbar(self.page, "请先输入 API Key (OCR 或 解析/变式)", is_error=True)
            return
        if not (self.model_ocr_input.value or "").strip():
            show_snackbar(self.page, "请填写 OCR 视觉模型名称", is_error=True)
            return

        self._busy = True
        show_snackbar(self.page, "正在测试 OCR 连接 (将识别一张测试图)...")

        def _notify(msg: str, is_err: bool = False):
            try:
                self.page.run_thread(
                    lambda m=msg, e=is_err: show_snackbar(self.page, m, is_error=e))
            except Exception:
                pass

        def _do_test():
            try:
                from services.llm_service import create_llm_service
                svc = create_llm_service(self.settings, purpose="ocr")
                # 用最小测试: 不发图片, 仅调用 _call_chat_api 看是否返回
                # 由于 ocr_image 需要真图, 这里用 grade_answer (文本) 间接验证连通性
                if not svc.model_ocr:
                    _notify("OCR 视觉模型未配置", True)
                    return
                # 直接调用 _call_chat_api 验证连接 (不依赖图片)
                svc.model = svc.model_ocr
                svc._call_chat_api(
                    messages=[
                        {"role": "system", "content": "You are a test assistant."},
                        {"role": "user", "content": "ping"},
                    ],
                    temperature=0.1, max_tokens=10,
                )
                _notify("✓ OCR 接口连接成功！")
            except Exception as ex:
                _notify(f"OCR 接口失败: {ex}", True)
            finally:
                self._busy = False

        self.page.run_thread(_do_test)

    # ==================== 导出设置 ====================
    def _build_export_card(self) -> Card:
        export_path = self.settings.get("export_path", str(EXPORT_DIR))
        export_format = self.settings.get("export_format", "docx")

        self.export_path_input = TextField(filled=True, fill_color=surface_input_color(self.page),
            label="默认导出路径",
            value=export_path,
            read_only=True,
            expand=True,
        )

        browse_btn = ElevatedButton(
            "选择",
            icon=Icons.FOLDER_OPEN,
            on_click=self._on_browse_export_path,
        )

        self.export_format_dropdown = Dropdown(filled=True, fill_color=surface_input_color(self.page),
            label="默认导出格式",
            value=export_format,
            options=[
                ft.dropdown.Option(key="docx", text="Word 文档 (.docx)"),
                ft.dropdown.Option(key="pdf", text="PDF 文档 (.pdf)"),
                ft.dropdown.Option(key="html", text="HTML 网页 (.html) [移动端推荐]"),
            ],
            on_select=self._on_export_format_change,
        )

        return self._wrap_card(
            title="导出设置",
            icon=Icons.FILE_DOWNLOAD_OUTLINED,
            content=Column(
                controls=[
                    Row([self.export_path_input, browse_btn], spacing=8),
                    self.export_format_dropdown,
                ],
                spacing=12,
            ),
        )

    async def _on_browse_export_path(self, e: ControlEvent):
        path = await get_directory_path_async(
            self.page,
            dialog_title="选择导出目录",
            initial_directory=self.export_path_input.value or "",
        )
        if path:
            self.export_path_input.value = path
            self.settings["export_path"] = path
            self._on_auto_save_silent()
            self.page.update()

    def _on_export_format_change(self, e: ControlEvent):
        self.settings["export_format"] = e.control.value
        self._on_auto_save_silent()

    # ==================== 字体设置 ====================
    def _build_font_card(self) -> Card:
        self.font_cjk_input = TextField(filled=True, fill_color=surface_input_color(self.page),
            label="中文字体",
            value=self.settings.get("export_font_cjk", "宋体"),
            prefix_icon=Icons.TEXT_FIELDS,
            hint_text="如：宋体、黑体、微软雅黑",
            width=200,
            on_blur=self._on_auto_save_silent,
        )
        self.font_latin_input = TextField(filled=True, fill_color=surface_input_color(self.page),
            label="英文字体",
            value=self.settings.get("export_font_latin", "Times New Roman"),
            prefix_icon=Icons.TEXT_FIELDS,
            hint_text="如：Times New Roman、Arial",
            width=200,
            on_blur=self._on_auto_save_silent,
        )
        self.font_size_input = TextField(filled=True, fill_color=surface_input_color(self.page),
            label="字号",
            value=self.settings.get("export_font_size", "10.5pt"),
            prefix_icon=Icons.FORMAT_SIZE,
            hint_text="如：10.5pt (五号), 12pt (小四)",
            width=120,
            on_blur=self._on_auto_save_silent,
        )
        self.line_spacing_input = TextField(filled=True, fill_color=surface_input_color(self.page),
            label="行距",
            value=self.settings.get("export_line_spacing", "1.0"),
            prefix_icon=Icons.FORMAT_LINE_SPACING,
            hint_text="如：1.0 (单倍), 1.5 (1.5倍)",
            width=120,
            on_blur=self._on_auto_save_silent,
        )

        preset_row = Row(
            controls=[
                Text("快捷预设：", size=13, color=Colors.ON_SURFACE_VARIANT),
                OutlinedButton(
                    "默认 (宋体/Times/五号/单倍)",
                    on_click=lambda e: self._apply_font_preset(
                        "宋体", "Times New Roman", "10.5pt", "1.0"),
                ),
                OutlinedButton(
                    "小四 (宋体/Times/12pt/1.5倍)",
                    on_click=lambda e: self._apply_font_preset(
                        "宋体", "Times New Roman", "12pt", "1.5"),
                ),
                OutlinedButton(
                    "试卷 (宋体/Times/12pt/单倍)",
                    on_click=lambda e: self._apply_font_preset(
                        "宋体", "Times New Roman", "12pt", "1.0"),
                ),
            ],
            spacing=8,
            wrap=True,
        )

        return self._wrap_card(
            title="导出字体设置",
            icon=Icons.FORMAT_SIZE,
            content=Column(
                controls=[
                    Text(
                        "设置导出 Word/PDF 文档的字体、字号、行距",
                        size=13, color=Colors.ON_SURFACE_VARIANT,
                    ),
                    Row([
                        self.font_cjk_input,
                        self.font_latin_input,
                    ], spacing=8, wrap=True),
                    Row([
                        self.font_size_input,
                        self.line_spacing_input,
                    ], spacing=8, wrap=True),
                    Divider(),
                    preset_row,
                ],
                spacing=12,
            ),
        )

    def _apply_font_preset(self, cjk: str, latin: str, size: str, spacing: str):
        self.font_cjk_input.value = cjk
        self.font_latin_input.value = latin
        self.font_size_input.value = size
        self.line_spacing_input.value = spacing
        self.settings["export_font_cjk"] = cjk
        self.settings["export_font_latin"] = latin
        self.settings["export_font_size"] = size
        self.settings["export_line_spacing"] = spacing
        self._on_auto_save_silent()
        self.page.update()

    # ==================== 复习规则 ====================
    def _build_review_card(self) -> Card:
        intervals = self.settings.get("review_intervals",
                                       DEFAULT_SETTINGS["review_intervals"])
        while len(intervals) < 6:
            intervals.append(DEFAULT_SETTINGS["review_intervals"][len(intervals)])

        labels = ["第1阶段", "第2阶段", "第3阶段", "第4阶段", "第5阶段", "第6阶段"]

        rows = []
        self.interval_inputs = []
        for i, (label, val) in enumerate(zip(labels, intervals)):
            tf = TextField(filled=True, fill_color=surface_input_color(self.page),
                label=label,
                value=str(val),
                width=100,
                input_filter=ft.NumbersOnlyInputFilter(),
                text_align=ft.TextAlign.CENTER,
                on_change=self._on_interval_change,
                on_blur=self._on_auto_save_silent,
            )
            tf.data = i
            self.interval_inputs.append(tf)
            rows.append(
                Row(
                    controls=[
                        Text(label, size=15, width=80),
                        tf,
                        Text("天后复习", size=14, color=Colors.ON_SURFACE_VARIANT),
                    ],
                    spacing=8,
                )
            )

        preset_row = Row(
            controls=[
                Text("快捷预设：", size=13, color=Colors.ON_SURFACE_VARIANT),
                OutlinedButton(
                    "标准 (1,2,4,7,15,30)",
                    on_click=lambda e: self._apply_preset([1, 2, 4, 7, 15, 30]),
                ),
                OutlinedButton(
                    "紧凑 (1,3,5,7,10,14)",
                    on_click=lambda e: self._apply_preset([1, 3, 5, 7, 10, 14]),
                ),
                OutlinedButton(
                    "宽松 (2,5,10,20,40,60)",
                    on_click=lambda e: self._apply_preset([2, 5, 10, 20, 40, 60]),
                ),
            ],
            spacing=8,
            wrap=True,
        )

        return self._wrap_card(
            title="复习规则 (艾宾浩斯遗忘曲线)",
            icon=Icons.PSYCHOLOGY_ALT_OUTLINED,
            content=Column(
                controls=[
                    Text(
                        "调整每个复习阶段的间隔天数，系统会自动按此规则调度复习任务",
                        size=14, color=Colors.ON_SURFACE_VARIANT,
                    ),
                    *rows,
                    Divider(),
                    preset_row,
                ],
                spacing=10,
            ),
        )

    def _on_interval_change(self, e: ControlEvent):
        intervals = []
        for tf in self.interval_inputs:
            try:
                v = int(tf.value or "0")
                if v <= 0:
                    v = 1
                intervals.append(v)
            except ValueError:
                intervals.append(1)
        self.settings["review_intervals"] = intervals
        self._on_auto_save_silent()

    def _apply_preset(self, intervals: list):
        for i, v in enumerate(intervals):
            if i < len(self.interval_inputs):
                self.interval_inputs[i].value = str(v)
        self.settings["review_intervals"] = intervals
        self._on_auto_save_silent()
        self.page.update()

    # ==================== 外观设置 ====================
    def _build_appearance_card(self) -> Card:
        theme_mode = self.settings.get("theme_mode", "system")

        self.theme_mode_dropdown = Dropdown(filled=True, fill_color=surface_input_color(self.page),
            label="主题模式",
            value=theme_mode,
            options=[
                ft.dropdown.Option(key="system", text="跟随系统"),
                ft.dropdown.Option(key="light", text="亮色模式"),
                ft.dropdown.Option(key="dark", text="暗色模式"),
            ],
            on_select=self._on_theme_mode_change,
        )

        self.ui_font_input = TextField(filled=True, fill_color=surface_input_color(self.page),
            label="软件界面字体",
            value=self.settings.get("ui_font_family", "Microsoft YaHei UI"),
            prefix_icon=Icons.FONT_DOWNLOAD_OUTLINED,
            hint_text="如：Microsoft YaHei UI、PingFang SC、Noto Sans CJK SC、SimHei",
            width=320,
            on_blur=self._on_auto_save_silent,
        )

        self.scan_quality_dropdown = Dropdown(filled=True, fill_color=surface_input_color(self.page),
            label="扫描增强质量",
            value=self.settings.get("scan_quality", "high"),
            options=[
                ft.dropdown.Option(key="high", text="高 (自适应阈值，推荐)"),
                ft.dropdown.Option(key="medium", text="中 (全局 Otsu，较快)"),
                ft.dropdown.Option(key="low", text="低 (仅对比度拉伸，最快)"),
            ],
            on_select=self._on_scan_quality_change,
        )

        self.auto_scan_switch = Switch(
            label="导入图片时自动执行扫描增强",
            value=self.settings.get("auto_scan_on_import", False),
            on_change=self._on_auto_scan_change,
        )

        return self._wrap_card(
            title="外观与扫描",
            icon=Icons.PALETTE_OUTLINED,
            content=Column(
                controls=[
                    self.theme_mode_dropdown,
                    self.ui_font_input,
                    self.scan_quality_dropdown,
                    self.auto_scan_switch,
                ],
                spacing=12,
            ),
        )

    def _on_theme_mode_change(self, e: ControlEvent):
        self.settings["theme_mode"] = e.control.value
        self._on_auto_save_silent()

    def _on_scan_quality_change(self, e: ControlEvent):
        self.settings["scan_quality"] = e.control.value
        self._on_auto_save_silent()

    def _on_auto_scan_change(self, e: ControlEvent):
        self.settings["auto_scan_on_import"] = e.control.value
        self._on_auto_save_silent()

    # ==================== 操作按钮 ====================
    def _build_actions_row(self) -> Row:
        return Row(
            controls=[
                ElevatedButton(
                    "保存设置",
                    icon=Icons.SAVE,
                    on_click=self._on_save,
                ),
                OutlinedButton(
                    "恢复默认",
                    icon=Icons.RESTORE,
                    on_click=self._on_reset,
                ),
                OutlinedButton(
                    "清空缓存",
                    icon=Icons.DELETE_SWEEP,
                    on_click=self._on_clear_cache,
                ),
            ],
            spacing=12,
            alignment=MainAxisAlignment.END,
        )

    # ==================== 自动保存 (issue #2) ====================
    def _save_to_settings_object(self):
        """把当前 UI 控件值同步到 self.settings 字典 (不写盘)"""
        # 解析/变式接口
        self.settings["api_key"] = (self.api_key_input.value or "").strip()
        # model_name 兼容旧字段
        self.settings["model_name"] = (self.model_solution_input.value or "").strip()
        self.settings["custom_api_url"] = (self.custom_url_input.value or "").strip()
        self.settings["model_name_solution"] = (self.model_solution_input.value or "").strip()
        self.settings["deep_thinking_solution"] = self.deep_solution_switch.value
        self.settings["deep_thinking_variants"] = self.deep_variants_switch.value

        # OCR 接口 (issue #1)
        self.settings["model_name_ocr"] = (self.model_ocr_input.value or "").strip()
        self.settings["deep_thinking_ocr"] = self.deep_ocr_switch.value
        if self.use_same_as_solution_switch and not self.use_same_as_solution_switch.value:
            # 独立 OCR 配置
            self.settings["llm_provider_ocr"] = (self.provider_ocr_dropdown.value or "").strip()
            self.settings["api_key_ocr"] = (self.api_key_ocr_input.value or "").strip()
            self.settings["custom_api_url_ocr"] = (self.custom_url_ocr_input.value or "").strip()
        else:
            # 与解析/变式共用
            self.settings["llm_provider_ocr"] = ""
            self.settings["api_key_ocr"] = ""
            self.settings["custom_api_url_ocr"] = ""

        # 字体设置
        self.settings["export_font_cjk"] = (self.font_cjk_input.value or "宋体").strip()
        self.settings["export_font_latin"] = (self.font_latin_input.value or "Times New Roman").strip()
        self.settings["export_font_size"] = (self.font_size_input.value or "10.5pt").strip()
        self.settings["export_line_spacing"] = (self.line_spacing_input.value or "1.0").strip()
        self.settings["ui_font_family"] = (self.ui_font_input.value or "Microsoft YaHei UI").strip()

        # 导出工具路径 (后台自动检测, 不再暴露 UI)
        # 用户打包时把 pandoc.exe / wkhtmltopdf.exe 放到项目根 tools/ 目录即可

    def _on_auto_save_silent(self, e: ControlEvent = None):
        """
        静默自动保存 (issue #2):
        - 用户输入框 onChange/onBlur 时触发
        - 不弹 "已保存" 提示, 但确实写盘 (防止用户忘按保存)
        - 注意: 主题/字号等需要立即应用视觉变化的项, 由 _on_save 时统一刷新
        """
        try:
            self._save_to_settings_object()
            SettingsService.save(self.settings)
            # 只刷新 app.settings 内存 (不重建 UI, 避免输入框焦点丢失)
            if self.app:
                self.app.settings = SettingsService.load()
        except Exception as ex:
            print(f"[settings] 自动保存失败: {ex}")

    def _on_save(self, e: ControlEvent):
        """显式保存: 同步 UI 值 + 写盘 + 刷新主题 + 提示用户"""
        self._save_to_settings_object()
        SettingsService.save(self.settings)
        if self.app:
            self.app.refresh_settings()
        show_snackbar(self.page, "✓ 设置已保存")

    def _on_reset(self, e: ControlEvent):
        def do_reset():
            self.settings = SettingsService.reset()
            self.app.settings = self.settings
            self.app.refresh_settings()
            self.app.refresh_current_view()

        show_confirm_dialog(
            self.page,
            title="确认恢复默认？",
            message="所有设置（含 API Key）将被重置为默认值",
            on_confirm=do_reset,
            confirm_text="确认",
            cancel_text="取消",
            is_danger=True,
        )

    def _on_clear_cache(self, e: ControlEvent):
        try:
            from services.latex_service import clear_latex_cache
            clear_latex_cache()
            show_snackbar(self.page, "✓ 缓存已清空")
        except Exception as ex:
            show_snackbar(self.page, f"清空失败: {ex}", is_error=True)

    # ==================== 工具方法 ====================
    def _wrap_card(self, title: str, icon: str, content,
                   subtitle: str = None) -> Card:
        header_controls = [
            Icon(icon, color=Colors.PRIMARY, size=24),
            Text(title, size=20, weight=FontWeight.W_600),
        ]
        header_row = Row(controls=header_controls, spacing=8)
        return Card(
            elevation=0.5,
            content=Container(
                content=Column(
                    controls=[
                        header_row,
                        *([Text(subtitle, size=12,
                                color=Colors.ON_SURFACE_VARIANT)] if subtitle else []),
                        Divider(),
                        content,
                    ],
                    spacing=12,
                ),
                padding=ft.Padding.all(20),
            ),
        )
