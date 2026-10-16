# ============================================================
# 全局配置常量
# ============================================================
# 说明：此文件集中存放应用级的常量、默认值、API 端点等
#       便于统一管理和修改
# ============================================================

import os
import sys
from pathlib import Path

# -------------------- 版本 --------------------
APP_VERSION = "1.3.0"

# -------------------- 平台检测 --------------------
def _is_android() -> bool:
    """检测当前进程是否运行在 Android 上"""
    # Python-for-Android (P4A) 注入以下环境变量之一:
    #   P4A_BOOTSTRAP    = 'sdl2' / 'webview' ...
    #   ANDROID_ARGUMENT = /data/data/<pkg>/files/app/_python_bundle.tar.gz
    #   ANDROID_PRIVATE  = /data/data/<pkg>/files  (app 私有目录)
    # 注意: ANDROID_DATA 本身是 /data, ANDROID_ROOT 是 /system, 仅这两个不能确认是 app 进程
    if "P4A_BOOTSTRAP" in os.environ:
        return True
    if "ANDROID_ARGUMENT" in os.environ:
        return True
    if "ANDROID_PRIVATE" in os.environ:
        return True
    if getattr(sys, "android_api_level", None) is not None:
        return True
    return False


def _is_ios() -> bool:
    return sys.platform == "ios"


def _app_data_root() -> Path:
    """
    返回可写数据根目录.
    - 桌面端:   项目根目录 (BASE_DIR), 保持原行为
    - Android:  app 私有目录 /data/data/<pkg>/files (P4A 默认设置 PYTHONPATH 等)
    - iOS:      NSDocumentDirectory
    """
    if _is_android():
        # 优先: P4A 直接注入的私有目录
        for env_key in ("ANDROID_PRIVATE", "P4A_APP_DIR"):
            p = os.environ.get(env_key)
            if p:
                root = Path(p)
                try:
                    root.mkdir(parents=True, exist_ok=True)
                    if os.access(root, os.W_OK):
                        return root
                except OSError:
                    pass
        # 从 ANDROID_ARGUMENT 推断: /data/data/<pkg>/files/app/_python_bundle.tar.gz
        android_argument = os.environ.get("ANDROID_ARGUMENT", "")
        if android_argument:
            # 路径形如 /data/data/<package>/files/app/_python_bundle.tar.gz
            files_dir = Path(android_argument).resolve().parents[2]
            try:
                files_dir.mkdir(parents=True, exist_ok=True)
                if os.access(files_dir, os.W_OK):
                    return files_dir
            except OSError:
                pass
        # 最终回退: 用 Python 的 home 目录 (P4A 把 home 设为 /data/data/<pkg>/files)
        try:
            home = Path.home()
            home.mkdir(parents=True, exist_ok=True)
            if os.access(home, os.W_OK):
                return home
        except OSError:
            pass
        # 实在不行, 试 /sdcard (需要存储权限)
        return Path("/sdcard") / "MistakeNotebook"
    elif _is_ios():
        return Path(os.environ.get("IOS_DOCUMENT_DIR", str(Path.home() / "Documents")))
    else:
        # 桌面: 项目根目录 (与原行为一致, 便于 tools/ 目录就近访问)
        return Path(__file__).resolve().parent

# -------------------- 路径配置 --------------------
# 项目根目录 (源代码所在, Android 上可能只读)
BASE_DIR = Path(__file__).resolve().parent

# 数据根目录: 桌面=BASE_DIR, Android/iOS=app 沙盒
APP_DATA_ROOT = _app_data_root()

# 数据目录 (错题库 JSON + 图片 + 缓存)
DATA_DIR = APP_DATA_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 错题库 JSON 文件
MISTAKE_DB_FILE = DATA_DIR / "mistakes.json"

# 设置文件
SETTINGS_FILE = DATA_DIR / "settings.json"

# 缓存目录 (LaTeX 渲染图片, 临时图片)
CACHE_DIR = APP_DATA_ROOT / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 增强后的图片存储目录
ENHANCED_IMG_DIR = DATA_DIR / "images"
ENHANCED_IMG_DIR.mkdir(parents=True, exist_ok=True)

# 原始图片存储目录
ORIGINAL_IMG_DIR = DATA_DIR / "originals"
ORIGINAL_IMG_DIR.mkdir(parents=True, exist_ok=True)

# 裁剪后的图片存储目录
CROPPED_IMG_DIR = DATA_DIR / "cropped"
CROPPED_IMG_DIR.mkdir(parents=True, exist_ok=True)

# 导出文件默认目录:
# - 桌面: ~/Desktop
# - Android: app 沙盒内 export/ 目录 (用户通过分享面板导出)
if _is_android() or _is_ios():
    EXPORT_DIR = APP_DATA_ROOT / "export"
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
else:
    EXPORT_DIR = Path.home() / "Desktop"

# -------------------- 应用信息 --------------------
APP_NAME = "AI 错题本"
APP_SUBTITLE = "基于生成式 AI 的个性化错题本与变式训练系统"

# -------------------- 主题色 (Material 3 科技蓝紫) --------------------
PRIMARY_COLOR = "#6750A4"          # Material 3 默认主色
SECONDARY_COLOR = "#625B71"
TERTIARY_COLOR = "#7D5260"
ACCENT_COLOR = "#7C4DFF"
SUCCESS_COLOR = "#386A20"
WARNING_COLOR = "#7C5800"
ERROR_COLOR = "#B3261E"

# -------------------- 字体设置 (导出文档) --------------------
EXPORT_FONT_CJK = "宋体"
EXPORT_FONT_LATIN = "Times New Roman"
EXPORT_FONT_SIZE = "10.5pt"
EXPORT_LINE_SPACING = "1.0"

# -------------------- 界面字体 (UI) --------------------
# Windows 默认 "Microsoft YaHei UI"; macOS 默认 "PingFang SC"; Linux/Android 用内置字体
if sys.platform == "darwin":
    UI_FONT_FAMILY = "PingFang SC"
elif _is_android():
    UI_FONT_FAMILY = "Noto Sans CJK SC"   # Android 上 Python-for-Android 集成的字体
elif sys.platform.startswith("linux"):
    UI_FONT_FAMILY = "Noto Sans CJK SC"
else:
    UI_FONT_FAMILY = "Microsoft YaHei UI"

# -------------------- 大模型 API 默认配置 --------------------
LLM_PROVIDERS = {
    "zai": {
        "name": "Z.ai (智谱 GLM)",
        "chat_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "default_model": "glm-4v-plus",
        "vision_models": ["glm-4v-plus", "glm-4v", "glm-4v-flash"],
        "text_models": ["glm-4-plus", "glm-4", "glm-4-air", "glm-4-flash"],
    },
    "openai": {
        "name": "OpenAI",
        "chat_url": "https://api.openai.com/v1/chat/completions",
        "default_model": "gpt-4o",
        "vision_models": ["gpt-4o", "gpt-4o-mini", "gpt-4-vision-preview",
                          "gpt-4.1", "gpt-4.1-mini", "o1", "o1-mini", "o3-mini"],
        "text_models": ["gpt-4o", "gpt-4o-mini", "gpt-4", "gpt-4-turbo",
                        "gpt-4.1", "gpt-4.1-mini", "gpt-3.5-turbo",
                        "o1", "o1-mini", "o3-mini"],
    },
    "deepseek": {
        "name": "DeepSeek (深度求索)",
        "chat_url": "https://api.deepseek.com/v1/chat/completions",
        "default_model": "deepseek-chat",
        "vision_models": [],
        "text_models": ["deepseek-chat", "deepseek-reasoner"],
    },
    "moonshot": {
        "name": "Moonshot (月之暗面 Kimi)",
        "chat_url": "https://api.moonshot.cn/v1/chat/completions",
        "default_model": "moonshot-v1-8k-vision-preview",
        "vision_models": ["moonshot-v1-8k-vision-preview", "moonshot-v1-32k-vision-preview"],
        "text_models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
    },
    "custom": {
        "name": "自定义接口 (兼容 OpenAI 格式)",
        "chat_url": "",
        "default_model": "",
        "vision_models": [],
        "text_models": [],
    },
}

# -------------------- 默认设置 --------------------
DEFAULT_SETTINGS = {
    # ===== API 配置: 解析/变式文本模型 (默认接口) =====
    "llm_provider": "custom",
    "api_key": "",
    "model_name": "",              # 兼容旧字段 (不再使用, 保留以向后兼容)
    "model_name_solution": "",     # 解析/变式文本模型 (解题/变式用)
    "custom_api_url": "",

    # ===== API 配置: OCR/视觉模型 (识图用, 独立接口) =====
    "llm_provider_ocr": "",
    "api_key_ocr": "",
    "model_name_ocr": "",
    "custom_api_url_ocr": "",

    # 导出设置
    "export_path": "",
    "export_format": "docx",

    # 导出字体设置
    "export_font_cjk": EXPORT_FONT_CJK,
    "export_font_latin": EXPORT_FONT_LATIN,
    "export_font_size": "10.5pt",
    "export_line_spacing": "1.0",

    # 界面字体
    "ui_font_family": UI_FONT_FAMILY,

    # 深度思考开关
    "deep_thinking_ocr": False,
    "deep_thinking_solution": False,
    "deep_thinking_variants": False,

    # 复习规则
    "review_intervals": [1, 2, 4, 7, 15, 30],

    # 外观设置
    "theme_mode": "system",
    "primary_color": PRIMARY_COLOR,

    # 应用设置
    "scan_quality": "high",
    "auto_scan_on_import": False,

    # PDF/Word 导出工具路径 (后台自动检测, 无需用户配置)
    "wkhtmltopdf_path": "",
    "pandoc_path": "",
}

# -------------------- 调试开关 --------------------
DEBUG = os.environ.get("MISTAKE_DEBUG", "0") == "1"

# -------------------- 平台标志 (供其他模块直接 import) --------------------
IS_ANDROID = _is_android()
IS_IOS = _is_ios()
IS_MOBILE = IS_ANDROID or IS_IOS
IS_DESKTOP = not IS_MOBILE
