# ============================================================
# LaTeX 渲染服务 (matplotlib)
# ============================================================
# 说明：
#   由于 Flet 的 Markdown 控件无法直接渲染复杂 LaTeX 公式，
#   本模块负责：
#     1. 解析大模型返回的字符串，提取所有 $$...$$ 或 $...$ 包裹的公式
#     2. 使用 matplotlib 将 LaTeX 渲染为 PNG 图片
#     3. 缓存渲染结果避免重复渲染
#     4. 在 Flet UI 中用 Image 控件替换显示
# ============================================================

import re
import hashlib
import base64
from typing import List, Tuple, Optional

import matplotlib
matplotlib.use("Agg")  # 非交互式后端
import matplotlib.pyplot as plt

from config import CACHE_DIR


# -------------------- 公式提取 --------------------
# 匹配 $$...$$ (块级) 或 $...$ (行内)
LATEX_PATTERN = re.compile(r"\$\$([^\$]+)\$\$|\$([^\$]+)\$")

# matplotlib mathtext 不支持的环境/命令 (AI 输出常见，需降级处理)
_UNSUPPORTED_ENVS = r"aligned|array|cases|matrix|pmatrix|bmatrix|vmatrix|Vmatrix|gathered|split|eqnarray|smallmatrix"


def _preprocess_latex(latex: str) -> str:
    """
    将 AI 返回的 LaTeX 降级为 mathtext 可渲染的形式 (best-effort)
    处理：环境标签、换行、underbrace、含中文的 \\text{}、CJK 字符、\\displaystyle 等
    """
    s = latex
    # 移除不支持的 \\begin{...} / \\end{...} 环境标签
    s = re.sub(r"\\begin\{(?:%s)[*]?\}" % _UNSUPPORTED_ENVS, "", s)
    s = re.sub(r"\\end\{(?:%s)[*]?\}" % _UNSUPPORTED_ENVS, "", s)
    # 换行符替换为间隔
    s = s.replace(r"\\", ",\\; ")
    # \\underbrace{X}_{Y} -> X
    s = re.sub(r"\\underbrace\{([^{}]*)\}_?\{?[^{}]*\}?", r"\1", s)
    # \\text{...} 含中文时直接去掉，保留纯英文
    def _drop_cjk_text(m):
        inner = m.group(1)
        if re.search(r"[\u4e00-\u9fff]", inner):
            return ""
        return inner
    s = re.sub(r"\\text\{([^{}]*)\}", _drop_cjk_text, s)
    # 移除任何剩余 CJK 字符
    s = re.sub(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]", "", s)
    # 移除 mathtext 不支持的命令
    for cmd in (r"\displaystyle", r"\textstyle", r"\limits",
                r"\quad", r"\qquad", r"\hspace", r"\vspace"):
        s = s.replace(cmd, " ")
    # 处理中文引号等残留
    s = s.strip()
    return s if s else latex.replace(" ", "")


def extract_latex(text: str) -> List[Tuple[str, str, int, int]]:
    """
    从文本中提取所有 LaTeX 公式
    :return: [(latex, display_type, start, end), ...]
             display_type: "block" (块级 $$) 或 "inline" (行内 $)
    """
    results = []
    for m in LATEX_PATTERN.finditer(text):
        if m.group(1) is not None:
            results.append((m.group(1).strip(), "block", m.start(), m.end()))
        elif m.group(2) is not None:
            results.append((m.group(2).strip(), "inline", m.start(), m.end()))
    return results


def render_latex_to_png(latex: str, display_type: str = "inline",
                         fontsize: int = 14, dpi: int = 200,
                         color: Optional[str] = None) -> str:
    """
    使用 matplotlib 将单个 LaTeX 公式渲染为 PNG
    :param latex: LaTeX 公式字符串
    :param display_type: "block" 或 "inline"
    :param fontsize: 字号
    :param dpi: 分辨率
    :param color: 文字颜色 (默认亮色 #1D1B20; 暗色主题传 #E6E0E9 以保证可见)
    :return: PNG 文件路径
    """
    color = color or ("#1D1B20" if display_type == "inline" else "#21005D")
    # 计算缓存键 (避免重复渲染相同公式)
    cache_key = hashlib.md5(
        f"{latex}_{display_type}_{fontsize}_{dpi}_{color}".encode("utf-8")
    ).hexdigest()
    cache_path = CACHE_DIR / f"latex_{cache_key}.png"
    if cache_path.exists():
        return str(cache_path)

    # 配置 matplotlib 数学渲染
    matplotlib.rcParams["mathtext.fontset"] = "cm"  # Computer Modern
    matplotlib.rcParams["font.family"] = "serif"

    latex_candidates = [latex]
    # 含 CJK 的中文 + mathtext 无法显示中文，先尝试降级版本
    if re.search(r"[\u4e00-\u9fff]", latex):
        try:
            processed = _preprocess_latex(latex)
            if processed and processed != latex:
                latex_candidates.insert(0, processed)
        except Exception:
            pass
    else:
        # 首次渲染失败时尝试降级处理
        try:
            processed = _preprocess_latex(latex)
            if processed and processed != latex:
                latex_candidates.append(processed)
        except Exception:
            pass

    last_err: Optional[Exception] = None
    for candidate in latex_candidates:
        try:
            # 创建 Figure (无坐标轴)
            fig = plt.figure(figsize=(0.01, 0.01))
            fig.text(0, 0, f"${candidate}$", fontsize=fontsize,
                     color=color)

            # 保存 (透明背景, bbox_inches="tight" 自动裁剪)
            fig.savefig(
                str(cache_path),
                dpi=dpi,
                transparent=True,
                bbox_inches="tight",
                pad_inches=0.05,
            )
            plt.close(fig)
            return str(cache_path)
        except Exception as e:
            last_err = e
            plt.close("all")

    raise last_err or ValueError(f"LaTeX 渲染失败: {latex[:200]}")


def render_latex_to_base64(latex: str, display_type: str = "inline",
                            fontsize: int = 14,
                            color: Optional[str] = None) -> str:
    """
    将 LaTeX 渲染为 base64 字符串 (适合在 Flet Image.src 中使用)
    :return: base64 字符串 (不含 data: 前缀)
    """
    png_path = render_latex_to_png(latex, display_type, fontsize, color=color)
    with open(png_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def parse_mixed_content(text: str) -> List[dict]:
    """
    解析含 LaTeX 的混合文本，返回可渲染的分段列表
    :return: [{"type": "text", "content": "..."}, {"type": "latex",
              "content": "...", "display": "inline"/"block"}]
    """
    segments = []
    last_end = 0
    for m in LATEX_PATTERN.finditer(text):
        # 添加公式前的文本
        if m.start() > last_end:
            text_before = text[last_end:m.start()].strip()
            if text_before:
                segments.append({"type": "text", "content": text_before})

        # 添加公式
        if m.group(1) is not None:
            segments.append({"type": "latex", "content": m.group(1).strip(),
                             "display": "block"})
        else:
            segments.append({"type": "latex", "content": m.group(2).strip(),
                             "display": "inline"})

        last_end = m.end()

    # 添加最后一段文本
    if last_end < len(text):
        tail = text[last_end:].strip()
        if tail:
            segments.append({"type": "text", "content": tail})

    return segments if segments else [{"type": "text", "content": text}]


# -------------------- 公式转 Unicode 文本 (可选中复制的真文本) --------------------
# 实现移至 services/latex_unicode.py; 此处重新导出保持兼容


def latex_to_unicode(latex: str) -> str:
    """单个 LaTeX 公式 -> Unicode 数学文本"""
    from services.latex_unicode import latex_to_unicode as _f
    return _f(latex)


def latex_to_plain_text(text: str) -> str:
    """含 LaTeX 文本 -> 可读纯文本 (列表预览)"""
    from services.latex_unicode import latex_to_plain_text as _f
    return _f(text)


def clear_latex_cache():
    """清空 LaTeX 渲染缓存"""
    for f in CACHE_DIR.glob("latex_*.png"):
        try:
            f.unlink()
        except OSError:
            pass
