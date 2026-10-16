# ============================================================
# LaTeX 混排控件 (文本与公式同行显示)
# ============================================================
# 渲染方案: LaTeX -> Unicode 数学文本 (services/latex_unicode.py)
#   优点: 公式是真实 Text, 可选中/复制, 与正文同基线, 暗色自适应, 零延迟
#   兜底: 极端无法转换时显示原始公式文本
# ============================================================

import flet as ft

from services.latex_unicode import latex_to_unicode


def is_dark_mode(page) -> bool:
    """判断当前是否为暗色主题 (兼容 system 模式)"""
    try:
        mode = page.theme_mode
        if getattr(mode, "value", mode) == "dark":
            return True
        if getattr(mode, "value", mode) == "light":
            return False
        b = getattr(page, "platform_brightness", None)
        return "DARK" in str(b)
    except Exception:
        return False


# 公式文本字体 (Windows/Mac 自带衬线, 数学观感更好; 中文题面仍走默认字体)
MATH_FONT = "Georgia"


def build_latex_content(text: str, size: int = 14, dark: bool = False) -> ft.Control:
    """
    构建含 LaTeX 的混排控件 (全部为可选中/复制的真文本)
    :param text: 含 $...$ / $$...$$ 的原始文本
    :param size: 正文字号
    """
    if not text:
        return ft.Text("(无内容)", size=size, color=ft.Colors.ON_SURFACE_VARIANT)

    from services.latex_service import parse_mixed_content
    segments = parse_mixed_content(text)
    controls: list = []
    current_row: list = []

    def flush():
        if current_row:
            controls.append(ft.Row(
                controls=list(current_row),
                spacing=4,
                run_spacing=6,
                wrap=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ))
            current_row.clear()

    def add_text(content: str):
        import re as _re
        # 统一换行符并折叠多个 \n 为单个
        s = str(content).replace("\r\n", "\n").replace("\r", "\n")
        s = _re.sub(r"\n+", "\n", s)#.strip("\n")
        parts = s.split("\n")
        for i, part in enumerate(parts):
            if part.strip():
                current_row.append(ft.Text(part.strip(), size=size, selectable=True))
            if i < len(parts) - 1:
                flush()

    def add_inline(latex: str):
        uni = latex_to_unicode(latex)
        if uni:
            current_row.append(ft.Text(uni, size=size, selectable=True,
                                       font_family=MATH_FONT,
                                       color=ft.Colors.ON_SURFACE))
        else:
            current_row.append(ft.Text(f"${latex}$", size=size, selectable=True,
                                       color=ft.Colors.ON_SURFACE_VARIANT))

    def add_block(latex: str):
        uni = latex_to_unicode(latex)
        if uni:
            controls.append(ft.Container(
                content=ft.Text(uni, size=size + 2, selectable=True,
                                font_family=MATH_FONT,
                                color=ft.Colors.ON_SURFACE),
                alignment=ft.Alignment(0, 0),
                padding=ft.Padding.symmetric(horizontal=4, vertical=2),
            ))
        else:
            controls.append(ft.Text(f"$${latex}$$", size=size, selectable=True,
                                    color=ft.Colors.ON_SURFACE_VARIANT))

    for seg in segments:
        if seg["type"] == "text":
            add_text(seg["content"])
        elif seg["display"] == "block":
            flush()
            add_block(seg["content"])
        else:
            add_inline(seg["content"])
    flush()

    if not controls:
        return ft.Text(text, size=size, selectable=True)
    return ft.Column(controls=controls, spacing=6)
