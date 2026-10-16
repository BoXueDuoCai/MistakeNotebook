# ============================================================
# 主题配置 - Material 3 风格
# ============================================================
# 设计原则：
#   1. 字号略大 (默认 14→15, 标题 22→24)
#   2. 亮色/暗色模式对比度都足够强
#   3. AppBar 图标使用 on_surface (而非 outline) 保证可见性
# ============================================================

import flet as ft
from flet import Theme, ColorScheme


PRIMARY_SEED = "#6750A4"

# 亮色主题色彩 (对比度加强版)
LIGHT_COLORS = {
    "primary": "#6750A4",
    "on_primary": "#FFFFFF",
    "primary_container": "#EADDFF",
    "on_primary_container": "#21005D",

    "secondary": "#625B71",
    "on_secondary": "#FFFFFF",
    "secondary_container": "#E8DEF8",
    "on_secondary_container": "#1D192B",

    "tertiary": "#7D5260",
    "on_tertiary": "#FFFFFF",
    "tertiary_container": "#FFD8E4",
    "on_tertiary_container": "#31111D",

    "error": "#B3261E",
    "on_error": "#FFFFFF",
    "error_container": "#F9DEDC",
    "on_error_container": "#410E0B",

    "surface": "#FEF7FF",
    "on_surface": "#1D1B20",                # 主文字色 (近黑)
    "surface_tint": "#6750A4",
    "surface_bright": "#FEF7FF",
    "surface_container_lowest": "#FFFFFF",
    "surface_container_low": "#F7F2FA",
    "surface_container": "#F3EDF7",
    "surface_container_high": "#ECE6F0",
    "surface_container_highest": "#E6E0E9",
    "surface_dim": "#DED8E1",
    "on_surface_variant": "#49454F",        # 次要文字色 (深灰，对比度强)

    "outline": "#79747E",
    "outline_variant": "#CAC4D0",

    "shadow": "#000000",
    "scrim": "#000000",

    "inverse_surface": "#322F35",
    "on_inverse_surface": "#F5EFF7",
    "inverse_primary": "#D0BCFF",
}

# 暗色主题色彩 (对比度加强版)
DARK_COLORS = {
    "primary": "#D0BCFF",
    "on_primary": "#381E72",
    "primary_container": "#4F378B",
    "on_primary_container": "#EADDFF",

    "secondary": "#CCC2DC",
    "on_secondary": "#332D41",
    "secondary_container": "#4A4458",
    "on_secondary_container": "#E8DEF8",

    "tertiary": "#EFB8C8",
    "on_tertiary": "#492532",
    "tertiary_container": "#633B48",
    "on_tertiary_container": "#FFD8E4",

    "error": "#F2B8B5",
    "on_error": "#601410",
    "error_container": "#8C1D18",
    "on_error_container": "#F9DEDC",

    "surface": "#141218",
    "on_surface": "#E6E0E9",                # 暗色模式主文字色 (近白)
    "surface_tint": "#CFBCFF",
    "surface_bright": "#3B383E",
    "surface_container_lowest": "#0F0D13",
    "surface_container_low": "#1D1B20",
    "surface_container": "#211F26",
    "surface_container_high": "#2B2930",
    "surface_container_highest": "#36343B",
    "surface_dim": "#141218",
    "on_surface_variant": "#CAC4D0",         # 暗色模式次要文字色 (浅灰，对比度强)

    "outline": "#938F99",                    # 暗色模式 outline 调亮
    "outline_variant": "#49454F",

    "shadow": "#000000",
    "scrim": "#000000",

    "inverse_surface": "#E6E0E9",
    "on_inverse_surface": "#322F35",
    "inverse_primary": "#6750A4",
}


def build_color_scheme(dark: bool = False) -> ColorScheme:
    """构建 Material 3 色彩方案"""
    colors = DARK_COLORS if dark else LIGHT_COLORS
    return ColorScheme(
        primary=colors["primary"],
        on_primary=colors["on_primary"],
        primary_container=colors["primary_container"],
        on_primary_container=colors["on_primary_container"],

        secondary=colors["secondary"],
        on_secondary=colors["on_secondary"],
        secondary_container=colors["secondary_container"],
        on_secondary_container=colors["on_secondary_container"],

        tertiary=colors["tertiary"],
        on_tertiary=colors["on_tertiary"],
        tertiary_container=colors["tertiary_container"],
        on_tertiary_container=colors["on_tertiary_container"],

        error=colors["error"],
        on_error=colors["on_error"],
        error_container=colors["error_container"],
        on_error_container=colors["on_error_container"],

        surface=colors["surface"],
        on_surface=colors["on_surface"],
        surface_tint=colors["surface_tint"],
        surface_bright=colors["surface_bright"],
        surface_container_lowest=colors["surface_container_lowest"],
        surface_container_low=colors["surface_container_low"],
        surface_container=colors["surface_container"],
        surface_container_high=colors["surface_container_high"],
        surface_container_highest=colors["surface_container_highest"],
        surface_dim=colors["surface_dim"],
        on_surface_variant=colors["on_surface_variant"],

        outline=colors["outline"],
        outline_variant=colors["outline_variant"],

        shadow=colors["shadow"],
        scrim=colors["scrim"],

        inverse_surface=colors["inverse_surface"],
        on_inverse_surface=colors["on_inverse_surface"],
        inverse_primary=colors["inverse_primary"],
    )


def build_theme(dark: bool = False, font_family: str = "Microsoft YaHei UI") -> Theme:
    """构建 Material 3 主题 (字号略大)"""
    color_scheme = build_color_scheme(dark=dark)

    theme = Theme(
        color_scheme=color_scheme,
        use_material3=True,
        font_family=font_family or "Microsoft YaHei UI",
        visual_density=ft.VisualDensity.STANDARD,
    )

    # 卡片样式
    theme.card_theme = ft.CardTheme(
        color=color_scheme.surface,
        shadow_color=color_scheme.shadow,
        elevation=0.5,
    )

    # AppBar 样式 - 关键：使用 on_surface 而非默认值，保证图标可见
    theme.appbar_theme = ft.AppBarTheme(
        color=color_scheme.on_surface,           # 图标/文字色 (亮色=近黑, 暗色=近白)
        bgcolor=color_scheme.surface,
        elevation=0,
        center_title=False,
        title_text_style=ft.TextStyle(
            size=22,                            # 标题字号 22 (略大)
            weight=ft.FontWeight.W_600,
            color=color_scheme.on_surface,
        ),
    )

    # 底部导航栏样式
    theme.navigation_bar_theme = ft.NavigationBarTheme(
        bgcolor=color_scheme.surface,
        indicator_color=color_scheme.primary_container,
        indicator_shape=ft.StadiumBorder(),
        elevation=0,
        label_text_style=ft.TextStyle(size=13),
    )

    # 侧边导航栏样式 - 使用 on_surface_variant 保证未选中图标可见
    theme.navigation_rail_theme = ft.NavigationRailTheme(
        bgcolor=color_scheme.surface,
        indicator_color=color_scheme.primary_container,
        indicator_shape=ft.StadiumBorder(),
        elevation=0,
    )

    # 浮动按钮
    theme.floating_action_button_theme = ft.FloatingActionButtonTheme(
        bgcolor=color_scheme.primary_container,
        foreground_color=color_scheme.on_primary_container,
        shape=ft.StadiumBorder(),
        elevation=2,
    )

    # 文字按钮
    theme.text_button_theme = ft.TextButtonTheme(
        style=ft.ButtonStyle(
            shape=ft.StadiumBorder(),
        )
    )

    # 轮廓按钮
    theme.outlined_button_theme = ft.OutlinedButtonTheme(
        style=ft.ButtonStyle(
            shape=ft.StadiumBorder(),
            side=ft.BorderSide(1, color_scheme.outline),
        )
    )

    # 分隔线
    theme.divider_theme = ft.DividerTheme(
        color=color_scheme.outline_variant,
        thickness=1,
    )

    return theme


# -------------------- 通用样式工具 --------------------
def surface_input_color(page) -> str:
    """输入框/下拉框填充色 (按当前主题返回具体色值, 保证暗色下不是白底)"""
    try:
        from utils.latex_widgets import is_dark_mode
        if is_dark_mode(page):
            return "#2B2930"   # surface_container_high (dark)
    except Exception:
        pass
    return "#F3EDF7"          # surface_container (light)


def card_container(content, padding=20, margin=0, bgcolor=None,
                   border_radius=16, shadow=None, ink=False, on_click=None):
    """构建 Material 3 风格的卡片容器"""
    return ft.Container(
        content=content,
        padding=padding,
        margin=margin,
        bgcolor=bgcolor,
        border_radius=border_radius,
        shadow=shadow,
        ink=ink,
        on_click=on_click,
        animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
    )


def dashed_disclaimer_container(text: str, color: str = "#7C5800"):
    """构建虚线边框的免责提示容器"""
    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=color, size=20),
                ft.Text(
                    text,
                    size=14,
                    color=color,
                    weight=ft.FontWeight.W_500,
                ),
            ],
            spacing=8,
            alignment=ft.MainAxisAlignment.START,
        ),
        padding=ft.Padding.symmetric(horizontal=14, vertical=10),
        border=ft.Border.all(1, color),
        border_radius=10,
        bgcolor="#FFF8E1",
    )
