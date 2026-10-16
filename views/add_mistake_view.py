# ============================================================
# 添加错题页 - 简化录入流
# ============================================================
# 功能：
#   1. 上传图片 (FilePicker 0.86 正确用法)
#   2. 可视化裁剪 (鼠标拖拽框选，弹出裁剪对话框)
#   3. 一键扫描增强
#   4. AI_OCR 识别题干
#   5. 设置学科/知识点
#   6. 保存到错题库 (导入时间自动记录)
# ============================================================

import shutil
import uuid

import flet as ft
from flet import (
    Container, Column, Row, Text, TextField, ElevatedButton, OutlinedButton,
    Icons, Colors, Card, Icon,
    MainAxisAlignment, CrossAxisAlignment, FontWeight,
    Image, AlertDialog, ProgressBar, ControlEvent, Stack, TextStyle,
    Dropdown, Divider,
)

from utils.theme import surface_input_color
from config import ORIGINAL_IMG_DIR
from services.storage_service import SettingsService, MistakeStorageService
from services.image_service import enhance_image, crop_image_region
from services.llm_service import create_llm_service
from utils.dialog import show_dialog, pop_dialog, show_snackbar
from utils.file_loader import image_to_base64, get_mime_type
from utils.file_picker_helper import pick_files_async
from models.mistake import Mistake, SUBJECTS


class AddMistakeView:
    """添加错题页视图"""

    def __init__(self, app):
        self.app = app
        self.page = app.page
        self.settings = SettingsService.load()

        # 当前导入的图片路径
        self.current_image_path = ""
        self.enhanced_image_path = ""
        self.cropped_image_path = ""
        self.showing_enhanced = True

        # 控件引用
        self.image_preview = None
        self.image_placeholder = None
        self.subject_dropdown = None
        self.tag_input = None
        self.question_input = None
        self.error_thinking_input = None
        self.loading_bar = None
        self.scan_btn = None
        self.crop_btn = None
        self.ocr_btn = None
        self.save_btn = None
        self.toggle_btn = None
        self.pick_btn = None

        # Loading 状态
        self._busy = False
        self._loading_text = Text("", size=13, color=Colors.PRIMARY,
                                    weight=FontWeight.W_500, visible=False)
        # OCR 流式输出文本 (实时显示识别结果)
        self._ocr_streaming_text = Text("", size=13,
                                        color=Colors.ON_SURFACE_VARIANT,
                                        selectable=True, max_lines=4,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                        visible=False)
        self._ocr_buf = {"text": "", "last_push": 0.0}

        # 裁剪状态
        self._crop_start_x = 0
        self._crop_start_y = 0
        self._crop_end_x = 0
        self._crop_end_y = 0
        self._crop_dragging = False

    def build(self):
        self.settings = SettingsService.load()

        header = Container(
            content=Column(
                controls=[
                    Text("添加错题", size=30, weight=FontWeight.W_700,
                         color=Colors.ON_SURFACE),
                    Text("上传图片 → 裁剪 → 扫描增强 → AI OCR → 保存",
                         size=15, color=Colors.ON_SURFACE_VARIANT),
                ],
                spacing=4,
            ),
            padding=ft.Padding.only(bottom=16),
        )

        left_panel = self._build_image_panel()
        right_panel = self._build_form_panel()

        main_layout = ft.ResponsiveRow(
            controls=[
                ft.Column([left_panel], col={"xs": 12, "md": 5, "lg": 4}),
                ft.Column([right_panel], col={"xs": 12, "md": 7, "lg": 8}),
            ],
            spacing=16,
            expand=True,
        )

        scroll_view = ft.ListView(
            controls=[header, main_layout],
            spacing=16,
            expand=True,
        )

        return Container(content=scroll_view, expand=True)

    async def _on_pick_image(self, e: ControlEvent):
        """选择图片 (Flet 0.86 正确用法: 直接 await ft.FilePicker().pick_files)"""
        if self._busy:
            return
        self._set_busy(True, "正在打开文件选择器...")

        files = await pick_files_async(
            self.page,
            dialog_title="选择错题图片",
            allowed_extensions=["jpg", "jpeg", "png", "webp", "bmp"],
            file_type=ft.FilePickerFileType.IMAGE,
        )

        if not files:
            self._set_busy(False)
            return

        file = files[0]
        safe_name = f"original_{uuid.uuid4().hex[:8]}_{file.name}"
        target = ORIGINAL_IMG_DIR / safe_name
        auto_scanned = False
        try:
            # Web 端 FilePicker 只提供 bytes; 桌面端提供 path
            file_bytes = getattr(file, "bytes", None)
            if file_bytes:
                target.write_bytes(file_bytes)
            else:
                # Flet 0.86 桌面端: file.path 是 WindowsPath / PosixPath 对象,
                # 需先 str() 再交给 shutil.copy, 否则下游会报
                # 'WindowsPath' object has no attribute 'lower' (get_mime_type 触发)
                src_path = file.path or file.name
                if not isinstance(src_path, str):
                    src_path = str(src_path)
                shutil.copy(src_path, target)
            # 统一用 str 存, 避免后续 .lower()/split 等字符串操作踩坑
            self.current_image_path = str(target)
            self.enhanced_image_path = ""
            self.cropped_image_path = ""
            self._show_image(self.current_image_path, is_enhanced=False)
            self.scan_btn.disabled = False
            self.crop_btn.disabled = False
            self.toggle_btn.visible = False
            self.showing_enhanced = False

            if self.settings.get("auto_scan_on_import", False):
                auto_scanned = True
                self._on_scan_enhance(None)
        except Exception as ex:
            show_snackbar(self.page, f"图片导入失败: {ex}", is_error=True)
        finally:
            # 自动扫描场景下 busy 由扫描流程自己收尾, 避免提前解锁 UI
            if not auto_scanned:
                self._set_busy(False)

    def _show_image(self, path, is_enhanced: bool):
        """显示图片 (data URL, 兼容 str / pathlib.Path)"""
        # 防御: 万一上游传了 Path 对象, 统一转 str
        if path is not None and not isinstance(path, str):
            path = str(path)
        b64 = image_to_base64(path)
        if not b64:
            show_snackbar(self.page, f"图片读取失败: {path}", is_error=True)
            return
        self.image_placeholder.visible = False
        self.image_preview.visible = True
        self.image_preview.src = f"data:{get_mime_type(path)};base64," + b64
        self.showing_enhanced = is_enhanced
        self.page.update()

    def _on_toggle_image(self, e: ControlEvent):
        if not self.enhanced_image_path:
            show_snackbar(self.page, "尚未进行扫描增强")
            return
        if self.showing_enhanced:
            self._show_image(self.current_image_path, is_enhanced=False)
        else:
            self._show_image(self.enhanced_image_path, is_enhanced=True)

    def _on_scan_enhance(self, e: ControlEvent):
        if not self.current_image_path:
            show_snackbar(self.page, "请先导入图片", is_error=True)
            return

        quality = self.settings.get("scan_quality", "high")
        self._set_busy(True, f"正在扫描增强 ({quality})...")

        def _do_scan():
            try:
                src = self.cropped_image_path or self.current_image_path
                output = enhance_image(src, quality=quality)
                self.enhanced_image_path = output

                def _on_done():
                    try:
                        self._show_image(output, is_enhanced=True)
                        self.toggle_btn.visible = True
                        self._set_busy(False, "✓ 扫描增强完成")
                        show_snackbar(self.page, "✓ 扫描增强完成")
                    except Exception:
                        self._set_busy(False)
                self.page.run_thread(_on_done)
            except BaseException as ex:
                def _on_err(err=ex):
                    self._set_busy(False)
                    show_snackbar(self.page, f"扫描增强失败: {err}", is_error=True)
                self.page.run_thread(_on_err)

        self.page.run_thread(_do_scan)

    # -------------------- 可视化裁剪对话框 (Word 风格 8 手柄) --------------------
    def _on_open_crop_dialog(self, e: ControlEvent):
        """
        打开可视化裁剪对话框 (Word 图片裁剪风格: 8 个可拖拽手柄 + 主体可整体平移)
        - 4 个角手柄 (TL/TR/BL/BR): 同时调整宽高
        - 4 个边手柄 (T/B/L/R): 仅调整单方向
        - 内部主体: 整体平移选区
        Flet 0.86 关键约束: Container 用 left/top/right/bottom 绝对定位时,
        必须是 Stack 的直接子元素 (不能嵌套在 GestureDetector/Container 内).
        所以这里所有可绝对定位的元素都直接挂到 Stack 上, GestureDetector
        通过自身 (也是 Stack 直接子元素) 的 left/top 跟随手柄位置.
        """
        if not self.current_image_path:
            show_snackbar(self.page, "请先上传图片", is_error=True)
            return

        b64 = image_to_base64(self.current_image_path)
        if not b64:
            show_snackbar(self.page, "图片读取失败", is_error=True)
            return

        # 裁剪预览图 (较大尺寸方便拖拽), 移动端按窗口宽度收缩
        crop_w = self._content_width(700)
        crop_h = int(crop_w * 5 / 7)

        preview_image = Image(
            src=f"data:{get_mime_type(self.current_image_path)};base64," + b64,
            fit=ft.BoxFit.CONTAIN,
            width=crop_w, height=crop_h,
        )

        # 选区状态: 默认 60% 居中
        state = {
            "x": crop_w * 0.2,
            "y": crop_h * 0.2,
            "w": crop_w * 0.6,
            "h": crop_h * 0.6,
        }
        MIN_W = 30
        MIN_H = 30

        tip = Text(
            "拖拽四角/四边手柄调整选区; 中间区域可整体平移 (类似 Word 图片裁剪)",
            size=13, color=Colors.ON_SURFACE_VARIANT,
        )
        coords_text = Text(
            "", size=13, color=Colors.PRIMARY, weight=FontWeight.W_500,
        )

        # 半透明遮罩 (4 个矩形, 直接挂 Stack)
        mask_top = Container(
            bgcolor=Colors.with_opacity(0.5, Colors.BLACK),
            left=0, top=0, width=crop_w, height=0,
        )
        mask_bottom = Container(
            bgcolor=Colors.with_opacity(0.5, Colors.BLACK),
            left=0, top=0, width=crop_w, height=0,
        )
        mask_left = Container(
            bgcolor=Colors.with_opacity(0.5, Colors.BLACK),
            left=0, top=0, width=0, height=0,
        )
        mask_right = Container(
            bgcolor=Colors.with_opacity(0.5, Colors.BLACK),
            left=0, top=0, width=0, height=0,
        )

        # 选区边框 (透明, 仅显示边框) - 直接挂 Stack, 可绝对定位
        selection_border = Container(
            content=None,
            bgcolor=Colors.with_opacity(0.0, Colors.WHITE),
            border=ft.Border.all(2, Colors.WHITE),
            width=state["w"], height=state["h"],
            left=state["x"], top=state["y"],
        )

        # 平移层 (透明 Container 覆盖整个选区, 接收拖拽) - 直接挂 Stack
        # 不能用 GestureDetector 包 selection_border, 因为 GestureDetector 不是 Stack.
        # 改为: 让 selection_border 自身的 on_pan_update 处理平移 (Flet 0.86 Container 支持手势事件)
        # 实际 Flet 0.86 Container 没有原生 on_pan_update, 所以用 GestureDetector,
        # 但 GestureDetector 也要直接挂 Stack, 它的 left/top/width/height 跟随选区
        move_gd = ft.GestureDetector(
            content=Container(bgcolor=Colors.with_opacity(0.0, Colors.TRANSPARENT)),
            mouse_cursor=ft.MouseCursor.MOVE,
            left=state["x"], top=state["y"],
            width=state["w"], height=state["h"],
        )

        # 9 宫格分割线 - 直接挂 Stack
        grid_v1 = Container(width=1, height=0,
                            bgcolor=Colors.with_opacity(0.4, Colors.WHITE),
                            left=0, top=0)
        grid_v2 = Container(width=1, height=0,
                            bgcolor=Colors.with_opacity(0.4, Colors.WHITE),
                            left=0, top=0)
        grid_h1 = Container(width=0, height=1,
                            bgcolor=Colors.with_opacity(0.4, Colors.WHITE),
                            left=0, top=0)
        grid_h2 = Container(width=0, height=1,
                            bgcolor=Colors.with_opacity(0.4, Colors.WHITE),
                            left=0, top=0)

        # 8 个手柄 - 每个是 GestureDetector, 直接挂 Stack (用 left/top 定位)
        HANDLE = 14

        def _make_handle_gd(mode: str, cursor: ft.MouseCursor) -> ft.GestureDetector:
            """构造一个手柄 GestureDetector, 自身用 left/top 定位 (作为 Stack 直接子元素)"""
            handle_visual = Container(
                width=HANDLE, height=HANDLE,
                bgcolor=Colors.WHITE,
                border=ft.Border.all(1.5, Colors.PRIMARY),
                border_radius=2,
            )

            def on_update(ev):
                # Flet 0.86: DragUpdateEvent.local_delta (Offset)
                dx, dy = 0.0, 0.0
                ld = getattr(ev, "local_delta", None)
                if ld is not None:
                    dx = float(getattr(ld, "x", 0) or 0)
                    dy = float(getattr(ld, "y", 0) or 0)
                else:
                    gd_ = getattr(ev, "global_delta", None)
                    if gd_ is not None:
                        dx = float(getattr(gd_, "x", 0) or 0)
                        dy = float(getattr(gd_, "y", 0) or 0)
                x, y, w, h = state["x"], state["y"], state["w"], state["h"]
                if mode == "tl":
                    nx = max(0, min(x + dx, x + w - MIN_W))
                    ny = max(0, min(y + dy, y + h - MIN_H))
                    state["w"] = w + (x - nx)
                    state["h"] = h + (y - ny)
                    state["x"] = nx
                    state["y"] = ny
                elif mode == "tr":
                    ny = max(0, min(y + dy, y + h - MIN_H))
                    state["w"] = max(MIN_W, min(w + dx, crop_w - x))
                    state["h"] = h + (y - ny)
                    state["y"] = ny
                elif mode == "bl":
                    nx = max(0, min(x + dx, x + w - MIN_W))
                    state["x"] = nx
                    state["w"] = w + (x - nx)
                    state["h"] = max(MIN_H, min(h + dy, crop_h - y))
                elif mode == "br":
                    state["w"] = max(MIN_W, min(w + dx, crop_w - x))
                    state["h"] = max(MIN_H, min(h + dy, crop_h - y))
                elif mode == "t":
                    ny = max(0, min(y + dy, y + h - MIN_H))
                    state["h"] = h + (y - ny)
                    state["y"] = ny
                elif mode == "b":
                    state["h"] = max(MIN_H, min(h + dy, crop_h - y))
                elif mode == "l":
                    nx = max(0, min(x + dx, x + w - MIN_W))
                    state["w"] = w + (x - nx)
                    state["x"] = nx
                elif mode == "r":
                    state["w"] = max(MIN_W, min(w + dx, crop_w - x))
                _apply()

            # 关键: GestureDetector 自身用 left/top/width/height 定位 (作为 Stack 子元素)
            return ft.GestureDetector(
                content=handle_visual,
                on_pan_update=on_update,
                mouse_cursor=cursor,
                width=HANDLE, height=HANDLE,
                left=0, top=0,  # 由 _apply() 实时更新
            )

        # 8 个手柄 (GestureDetector 实例, 直接挂 Stack)
        h_tl = _make_handle_gd("tl", ft.MouseCursor.RESIZE_UP_LEFT_DOWN_RIGHT)
        h_tr = _make_handle_gd("tr", ft.MouseCursor.RESIZE_UP_RIGHT_DOWN_LEFT)
        h_bl = _make_handle_gd("bl", ft.MouseCursor.RESIZE_UP_RIGHT_DOWN_LEFT)
        h_br = _make_handle_gd("br", ft.MouseCursor.RESIZE_UP_LEFT_DOWN_RIGHT)
        h_t = _make_handle_gd("t", ft.MouseCursor.RESIZE_UP_DOWN)
        h_b = _make_handle_gd("b", ft.MouseCursor.RESIZE_UP_DOWN)
        h_l = _make_handle_gd("l", ft.MouseCursor.RESIZE_LEFT_RIGHT)
        h_r = _make_handle_gd("r", ft.MouseCursor.RESIZE_LEFT_RIGHT)

        # 平移层的手势处理
        def on_move_update(ev):
            dx, dy = 0.0, 0.0
            ld = getattr(ev, "local_delta", None)
            if ld is not None:
                dx = float(getattr(ld, "x", 0) or 0)
                dy = float(getattr(ld, "y", 0) or 0)
            else:
                gd_ = getattr(ev, "global_delta", None)
                if gd_ is not None:
                    dx = float(getattr(gd_, "x", 0) or 0)
                    dy = float(getattr(gd_, "y", 0) or 0)
            x, y, w, h = state["x"], state["y"], state["w"], state["h"]
            state["x"] = max(0, min(x + dx, crop_w - w))
            state["y"] = max(0, min(y + dy, crop_h - h))
            _apply()

        move_gd.on_pan_update = on_move_update

        # Stack: 所有可绝对定位的元素都是直接子元素
        crop_stack = Stack(
            controls=[
                preview_image,
                mask_top, mask_bottom, mask_left, mask_right,
                selection_border,    # 选区边框
                move_gd,             # 平移层 (透明, 跟随选区位置/大小)
                grid_v1, grid_v2, grid_h1, grid_h2,
                h_tl, h_tr, h_bl, h_br,
                h_t, h_b, h_l, h_r,
            ],
            width=crop_w, height=crop_h,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

        def _apply():
            x, y, w, h = state["x"], state["y"], state["w"], state["h"]
            # 选区边框
            selection_border.left = x
            selection_border.top = y
            selection_border.width = w
            selection_border.height = h
            # 平移层 (跟随选区)
            move_gd.left = x
            move_gd.top = y
            move_gd.width = w
            move_gd.height = h
            # 4 遮罩
            mask_top.height = max(0, y)
            mask_top.top = 0
            mask_bottom.top = y + h
            mask_bottom.height = max(0, crop_h - (y + h))
            mask_left.top = y
            mask_left.height = h
            mask_left.width = max(0, x)
            mask_left.left = 0
            mask_right.left = x + w
            mask_right.top = y
            mask_right.height = h
            mask_right.width = max(0, crop_w - (x + w))
            # 9 宫格分割线
            grid_v1.left = x + w / 3
            grid_v1.top = y
            grid_v1.height = h
            grid_v2.left = x + 2 * w / 3
            grid_v2.top = y
            grid_v2.height = h
            grid_h1.left = x
            grid_h1.top = y + h / 3
            grid_h1.width = w
            grid_h2.left = x
            grid_h2.top = y + 2 * h / 3
            grid_h2.width = w
            # 手柄位置 (GestureDetector 自身的 left/top, 让手柄中心落在选区角/边中点)
            hx = HANDLE / 2
            h_tl.left, h_tl.top = x - hx, y - hx
            h_tr.left, h_tr.top = x + w - hx, y - hx
            h_bl.left, h_bl.top = x - hx, y + h - hx
            h_br.left, h_br.top = x + w - hx, y + h - hx
            h_t.left, h_t.top = x + w / 2 - hx, y - hx
            h_b.left, h_b.top = x + w / 2 - hx, y + h - hx
            h_l.left, h_l.top = x - hx, y + h / 2 - hx
            h_r.left, h_r.top = x + w - hx, y + h / 2 - hx
            # 坐标文本
            coords_text.value = (
                f"选区: x={int(x)}, y={int(y)}, 宽={int(w)}, 高={int(h)}"
            )
            try:
                self.page.update()
            except Exception:
                pass

        # 确认裁剪
        def do_crop(ev_click):
            x, y, w, h = state["x"], state["y"], state["w"], state["h"]
            if w < 10 or h < 10:
                show_snackbar(self.page, "选区太小, 请拖拽手柄调整", is_error=True)
                return
            # 图片 fit=CONTAIN, 显示坐标需换算回原图像素
            try:
                from services.image_service import get_image_info
                info = get_image_info(self.current_image_path)
                iw, ih = int(info["size"][0]), int(info["size"][1])
            except Exception:
                iw, ih = crop_w, crop_h
            try:
                self._set_busy(True, "正在裁剪...")
                scale = min(crop_w / iw, crop_h / ih)
                off_x = (crop_w - iw * scale) / 2
                off_y = (crop_h - ih * scale) / 2
                real_x = max(0, int((x - off_x) / scale))
                real_y = max(0, int((y - off_y) / scale))
                real_w = min(iw - real_x, max(1, int(w / scale)))
                real_h = min(ih - real_y, max(1, int(h / scale)))
                if real_w < 5 or real_h < 5:
                    show_snackbar(self.page, "选区无效", is_error=True)
                    return
                output = crop_image_region(self.current_image_path,
                                           real_x, real_y, real_w, real_h)
                self.cropped_image_path = output
                self.current_image_path = output
                self.enhanced_image_path = ""
                pop_dialog(self.page)
                self._show_image(output, is_enhanced=False)
                self.toggle_btn.visible = False
                self._set_busy(False)
                show_snackbar(self.page, "✓ 裁剪完成")
                if self.settings.get("auto_scan_on_import", False):
                    self._on_scan_enhance(None)
            except Exception as ex:
                self._set_busy(False)
                show_snackbar(self.page, f"裁剪失败: {ex}", is_error=True)

        # 重置选区
        def reset_selection(e=None):
            state["x"] = crop_w * 0.2
            state["y"] = crop_h * 0.2
            state["w"] = crop_w * 0.6
            state["h"] = crop_h * 0.6
            _apply()

        def cancel_crop(e):
            pop_dialog(self.page)

        dlg = AlertDialog(
            modal=True,
            title=Row([
                Icon(Icons.CROP, color=Colors.PRIMARY, size=24),
                Text("可视化裁剪", weight=FontWeight.W_600, size=20),
            ], spacing=8),
            content=Container(
                content=Column(
                    controls=[
                        tip,
                        coords_text,
                        Container(
                            content=crop_stack,
                            bgcolor=Colors.SURFACE_CONTAINER_HIGHEST,
                            border_radius=8,
                            padding=ft.Padding.all(4),
                            width=crop_w + 8,
                            height=crop_h + 8,
                        ),
                    ],
                    spacing=8, tight=True,
                ),
                width=crop_w + 24,
                padding=ft.Padding.all(8),
            ),
            actions=[
                OutlinedButton("重置选区", icon=Icons.REFRESH, on_click=reset_selection),
                OutlinedButton("取消", on_click=cancel_crop),
                ElevatedButton(
                    "✂ 确认裁剪",
                    icon=Icons.CONTENT_CUT,
                    on_click=do_crop,
                    style=ft.ButtonStyle(
                        bgcolor=Colors.PRIMARY_CONTAINER,
                        color=Colors.ON_PRIMARY_CONTAINER,
                    ),
                ),
            ],
            actions_alignment=MainAxisAlignment.END,
        )
        show_dialog(self.page, dlg)
        # 首次渲染
        _apply()

    # -------------------- 图片导入区 --------------------
    def _content_width(self, fixed: int) -> int:
        """根据窗口宽度收缩固定宽度, 避免移动端溢出 (断点 720)"""
        try:
            w = self.page.window.width or 1280
        except Exception:
            w = 1280
        return max(240, min(fixed, int(w) - 96))

    def _build_image_panel(self) -> Card:
        pw = self._content_width(400)
        # 占位提示
        self.image_placeholder = Container(
            content=Column(
                controls=[
                    Icon(Icons.ADD_PHOTO_ALTERNATE_OUTLINED, size=72,
                         color=Colors.ON_SURFACE_VARIANT),
                    Text("点击上传图片", size=16,
                         color=Colors.ON_SURFACE_VARIANT),
                    Text("支持 JPG / PNG / WEBP", size=13,
                         color=Colors.OUTLINE),
                ],
                horizontal_alignment=CrossAxisAlignment.CENTER,
                alignment=MainAxisAlignment.CENTER,
                spacing=8,
            ),
            width=pw, height=300,
            alignment=ft.Alignment(0, 0),
            border=ft.Border.all(2, Colors.OUTLINE),
            border_radius=12,
            bgcolor=Colors.SURFACE_CONTAINER_HIGHEST,
            ink=True,
            on_click=self._on_pick_image,
        )

        self.image_preview = Image(
            src="",
            fit=ft.BoxFit.CONTAIN,
            width=pw, height=300,
            border_radius=12,
            visible=False,
        )

        # 上传按钮
        self.pick_btn = ElevatedButton(
            "📁 上传图片",
            icon=Icons.UPLOAD_FILE,
            on_click=self._on_pick_image,
            width=pw, height=46,
        )

        # 裁剪按钮 (可视化裁剪对话框)
        self.crop_btn = OutlinedButton(
            "✂ 可视化裁剪",
            icon=Icons.CROP,
            on_click=self._on_open_crop_dialog,
            width=pw, height=46,
            disabled=True,
        )

        # 扫描增强按钮
        self.scan_btn = ElevatedButton(
            "📷 一键扫描增强",
            icon=Icons.DOCUMENT_SCANNER_OUTLINED,
            on_click=self._on_scan_enhance,
            width=pw, height=46,
            disabled=True,
        )

        # 切换原图/增强图
        self.toggle_btn = OutlinedButton(
            "查看原图 / 增强图",
            icon=Icons.SWAP_HORIZ,
            on_click=self._on_toggle_image,
            width=pw,
            visible=False,
        )

        hint = Text(
            "扫描增强：灰度化 → 去阴影 → 对比度拉伸 → 自适应二值化",
            size=12, color=Colors.ON_SURFACE_VARIANT,
            text_align=ft.TextAlign.CENTER,
        )

        return Card(
            elevation=0.5,
            content=Container(
                content=Column(
                    controls=[
                        Row(
                            controls=[
                                Icon(Icons.IMAGE_OUTLINED, color=Colors.PRIMARY, size=24),
                                Text("错题图片", size=20, weight=FontWeight.W_600),
                            ],
                            spacing=8,
                        ),
                        Divider(),
                        Stack(
                            controls=[self.image_placeholder, self.image_preview],
                            width=pw, height=300,
                        ),
                        self.pick_btn,
                        self.crop_btn,
                        self.scan_btn,
                        self.toggle_btn,
                        hint,
                    ],
                    spacing=10,
                    horizontal_alignment=CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.all(20),
            ),
        )

    # -------------------- 表单区 --------------------
    def _build_form_panel(self) -> Card:
        subject_opts = [ft.dropdown.Option(key="自动", text="自动识别 (由 AI 判断)")]
        for s in SUBJECTS:
            subject_opts.append(ft.dropdown.Option(key=s, text=s))

        self.subject_dropdown = Dropdown(filled=True, fill_color=surface_input_color(self.page), 
            label="学科",
            value="自动",
            options=subject_opts,
            on_select=lambda e: None,
        )

        self.tag_input = TextField(filled=True, fill_color=surface_input_color(self.page), 
            label="知识点标签",
            hint_text="如：三角函数、牛顿第二定律、化学平衡",
            prefix_icon=Icons.LABEL_OUTLINE,
        )

        self.question_input = TextField(filled=True, fill_color=surface_input_color(self.page), 
            label="题干 (可手动输入或点击下方 AI OCR 自动识别)",
            multiline=True,
            min_lines=4,
            max_lines=8,
            hint_text="点击 AI OCR 按钮，或手动输入题干",
        )

        self.error_thinking_input = TextField(filled=True, fill_color=surface_input_color(self.page), 
            label="当时的错误思路 (可选)",
            multiline=True,
            min_lines=2,
            max_lines=4,
            hint_text="简述你当时为什么选错 (供后续 AI 错因诊断)",
        )

        self.ocr_btn = ElevatedButton(
            "🔍 AI OCR 识别题干",
            icon=Icons.DOCUMENT_SCANNER,
            on_click=self._on_ocr,
            width=self._content_width(400), height=46,
            style=ft.ButtonStyle(
                bgcolor=Colors.TERTIARY_CONTAINER,
                color=Colors.ON_TERTIARY_CONTAINER,
            ),
        )

        self.save_btn = ElevatedButton(
            "💾 保存到错题库",
            icon=Icons.SAVE,
            on_click=self._on_save_mistake,
            width=self._content_width(400), height=50,
            style=ft.ButtonStyle(
                bgcolor=Colors.PRIMARY_CONTAINER,
                color=Colors.ON_PRIMARY_CONTAINER,
                text_style=TextStyle(size=16, weight=FontWeight.W_600),
            ),
        )

        self.loading_bar = ProgressBar(visible=False, color=Colors.PRIMARY)

        tip = Text(
            "💡 保存后，可在「错题库」页面生成 AI 解析与变式题",
            size=13, color=Colors.ON_SURFACE_VARIANT,
            text_align=ft.TextAlign.CENTER,
        )

        return Card(
            elevation=0.5,
            content=Container(
                content=Column(
                    controls=[
                        Row(
                            controls=[
                                Icon(Icons.EDIT_NOTE_OUTLINED, color=Colors.PRIMARY, size=24),
                                Text("题目信息", size=20, weight=FontWeight.W_600),
                            ],
                            spacing=8,
                        ),
                        Divider(),
                        self.subject_dropdown,
                        self.tag_input,
                        self.question_input,
                        self.error_thinking_input,
                        self.ocr_btn,
                        self.loading_bar,
                        self._loading_text,
                        self._ocr_streaming_text,
                        Divider(),
                        self.save_btn,
                        tip,
                    ],
                    spacing=12,
                    scroll=ft.ScrollMode.AUTO,
                ),
                padding=ft.Padding.all(20),
            ),
        )

    # -------------------- Loading 控制 --------------------
    def _set_busy(self, busy: bool, msg: str = ""):
        """设置 busy 状态 + 禁用所有按钮 + 显示 Loading (绝对保证 UI 可恢复)"""
        from utils.run_guard import debug_log, Watchdog
        self._busy = busy
        if busy:
            debug_log(f"[add] BUSY ON: {msg}")
            if not hasattr(self, "_busy_watchdog") or self._busy_watchdog is None:
                self._busy_watchdog = Watchdog(
                    lambda: self._set_busy(False, ""), timeout=120, name="添加页操作")
                self._busy_watchdog.arm()
        else:
            debug_log("[add] BUSY OFF")
            wd = getattr(self, "_busy_watchdog", None)
            if wd is not None:
                wd.disarm()
                self._busy_watchdog = None
        # 禁用/启用所有操作按钮
        for btn in [self.pick_btn, self.crop_btn, self.scan_btn,
                    self.ocr_btn, self.save_btn]:
            if btn is not None:
                try:
                    btn.disabled = busy
                except Exception:
                    pass
        # Loading 进度条
        try:
            self.loading_bar.visible = busy
        except Exception:
            pass
        # Loading 文字
        if msg:
            try:
                self._loading_text.value = msg
                self._loading_text.visible = True
            except Exception:
                pass
        else:
            try:
                self._loading_text.visible = False
            except Exception:
                pass
        try:
            self.page.update()
        except Exception:
            pass

    # -------------------- AI OCR --------------------
    def _on_ocr(self, e: ControlEvent):
        if self._busy:
            return
        img_path = self.enhanced_image_path or self.cropped_image_path or self.current_image_path
        if not img_path:
            show_snackbar(self.page, "请先上传图片", is_error=True)
            return

        if not self.settings.get("api_key"):
            show_snackbar(self.page, "请先到设置页配置 API Key", is_error=True)
            return

        # 检查视觉模型 (custom 供应商兼容 OpenAI 接口, 可能是任何视觉网关, 放行)
        provider = self.settings.get("llm_provider", "zai")
        from config import LLM_PROVIDERS
        cfg = LLM_PROVIDERS.get(provider, {})
        if provider != "custom" and not cfg.get("vision_models"):
            show_snackbar(
                self.page,
                f"供应商 {cfg.get('name', provider)} 不支持视觉，请选择支持视觉的供应商",
                is_error=True
            )
            return

        self._set_busy(True, "AI 正在识别题干 (约 5-15 秒)...")
        self.settings = SettingsService.load()

        # 流式 OCR: 识别出的文字实时显示 (复用 __init__ 中创建的控件)
        self._ocr_streaming_text.visible = True
        self._ocr_streaming_text.value = ""
        self._ocr_buf = {"text": "", "last_push": 0.0}
        try:
            self._loading_text.visible = False  # 让位给流式文本
            self.page.update()
        except Exception:
            pass

        def _push_ocr(text):
            import time as _time
            buf = self._ocr_buf
            buf["text"] += text
            if _time.time() - buf["last_push"] < 0.12:
                return
            buf["last_push"] = _time.time()
            try:
                self.page.run_thread(self._update_ocr_stream)
            except Exception:
                pass

        def _do_ocr():
            try:
                llm = create_llm_service(self.settings, purpose="ocr")
                text = llm.ocr_image_stream(
                    img_path, on_delta=lambda t, r: _push_ocr(t))

                def _on_done():
                    try:
                        if text:
                            self.question_input.value = text
                            self._set_busy(False, "✓ OCR 识别完成")
                            self._hide_ocr_stream()
                            show_snackbar(self.page, "✓ OCR 识别完成")
                        else:
                            self._set_busy(False)
                            self._hide_ocr_stream()
                            show_snackbar(self.page, "OCR 未识别到内容", is_error=True)
                    except Exception:
                        self._set_busy(False)
                self.page.run_thread(_on_done)
            except BaseException as ex:
                def _on_err(err=ex):
                    self._set_busy(False)
                    self._hide_ocr_stream()
                    show_snackbar(self.page, f"OCR 失败: {err}", is_error=True)
                self.page.run_thread(_on_err)

        self.page.run_thread(_do_ocr)

    def _update_ocr_stream(self):
        """刷新 OCR 流式显示"""
        try:
            self._ocr_streaming_text.value = self._ocr_buf.get("text", "")[-300:]
            self._ocr_streaming_text.visible = True
            self.page.update()
        except Exception:
            pass

    def _hide_ocr_stream(self):
        """OCR 完成后隐藏流式文本"""
        try:
            self._ocr_streaming_text.visible = False
            self._ocr_buf = {"text": "", "last_push": 0.0}
            self.page.update()
        except Exception:
            pass

    # -------------------- 保存到错题库 --------------------
    def _on_save_mistake(self, e: ControlEvent):
        if self._busy:
            return
        question = (self.question_input.value or "").strip()
        if not question and not self.current_image_path:
            show_snackbar(self.page, "请至少提供图片或题干", is_error=True)
            return

        self._set_busy(True, "正在保存...")

        subject = self.subject_dropdown.value or "自动"
        if subject == "自动":
            subject = ""
        tag = (self.tag_input.value or "").strip()

        intervals = self.settings.get("review_intervals", [1, 2, 4, 7, 15, 30])

        mistake = Mistake(
            subject=subject,
            knowledge_tag=tag,
            original_question=question,
            error_thinking=(self.error_thinking_input.value or "").strip(),
            original_image=self.current_image_path,
            enhanced_image=self.enhanced_image_path,
        )
        mistake.next_review_date = mistake.compute_next_review_date(intervals)
        MistakeStorageService.add(mistake)

        self._set_busy(False, "✓ 已保存")
        show_snackbar(self.page, "✓ 已保存到错题库 (可在错题库生成 AI 解析)")

        self._reset_form()
        self.app.navigate_to("library")

    def _reset_form(self):
        self.question_input.value = ""
        self.error_thinking_input.value = ""
        self.tag_input.value = ""
        self.subject_dropdown.value = "自动"
        self.current_image_path = ""
        self.enhanced_image_path = ""
        self.cropped_image_path = ""
        self.image_placeholder.visible = True
        self.image_preview.visible = False
        self.toggle_btn.visible = False
        self.scan_btn.disabled = True
        self.crop_btn.disabled = True
        self._loading_text.visible = False
        self._ocr_streaming_text.visible = False
        self._ocr_streaming_text.value = ""
        self._ocr_buf = {"text": "", "last_push": 0.0}
        self.page.update()
