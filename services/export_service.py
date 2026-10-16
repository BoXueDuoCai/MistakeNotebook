# ============================================================
# 试卷导出服务
# ============================================================
# 功能：
#   1. 导出 Word (.docx)：pypandoc 转 Markdown (自动下载 Pandoc)
#   2. 导出 PDF：MathJax 2.7.7 HTML + pdfkit
#   3. 导出 HTML：与 PDF 同款 HTML, 单独保存供移动端分享
#   4. 字体设置：宋体 + Times New Roman, 五号, 单倍行距
#   5. 进度回调支持
#   6. Pandoc / wkhtmltopdf 路径检测: 优先用项目内 tools/ 目录,
#      便于打包时把工具一并发布 (无需用户配置)
# ============================================================

import os
import html as html_lib
from pathlib import Path
from typing import List, Optional, Dict, Callable
from datetime import datetime

from config import EXPORT_DIR, BASE_DIR, IS_ANDROID
from models.mistake import Mistake
import shutil

# -------------------- 移动端能力探测 --------------------
def is_mobile_platform() -> bool:
    """当前运行环境是否为移动端 (Android/iOS) - 移动端不支持 pandoc/wkhtmltopdf"""
    import sys as _sys
    return bool(IS_ANDROID) or _sys.platform == 'ios'

def is_docx_export_supported() -> bool:
    """Word 导出是否在当前平台受支持 (移动端不支持, 因 pandoc 不可用)"""
    return not is_mobile_platform()

def is_pdf_export_supported() -> bool:
    """PDF 导出是否在当前平台受支持 (移动端不支持, 因 wkhtmltopdf 不可用)"""
    return not is_mobile_platform()

def mobile_export_hint() -> str:
    """移动端导出能力说明文案 (供 UI 提示)"""
    return (
        "移动端暂不支持直接导出 Word/PDF (Pandoc 与 wkhtmltopdf 为桌面端二进制工具).\\n"
        "已为您生成 HTML 文件 (含完整 LaTeX 公式渲染), 可通过系统分享面板"
        "发送到电脑、或用浏览器打开后另存为 PDF."
    )


# -------------------- 项目内置工具路径 --------------------
# 打包发布时把 pandoc.exe / wkhtmltopdf.exe 放到项目根的 tools/ 目录,
# 这样软件无需用户手动配置即可找到这两个外部工具.
def _bundled_tool_path(*sub_paths: str) -> Optional[str]:
    """返回项目根 tools/ 下指定子路径的可执行文件绝对路径, 不存在返回 None"""
    candidate = BASE_DIR / "tools" / Path(*sub_paths)
    if candidate.exists():
        return str(candidate)
    return None


def _esc(text: str) -> str:
    """HTML 转义"""
    if not text:
        return ""
    return html_lib.escape(str(text))

def _normalize_newlines(text: str) -> str:
    """把任意多个连续换行折叠为单个换行 (\\n+ -> \\n), 同时去除每行首尾空白"""
    if not text:
        return ""
    import re as _re
    # 统一 Windows / 老 Mac 换行符
    s = str(text).replace("\r\n", "\n").replace("\r", "\n")
    # 连续 \n 折叠为单个 \n
    s = _re.sub(r"\n+", "\n", s)
    # 每行去首尾空白
    s = "\n".join(line.strip() for line in s.split("\n"))
    return s.strip("\n")

# -------------------- Markdown 生成 --------------------
def mistakes_to_markdown(mistakes: List[Mistake], title: str = "错题本导出",
                          font_cjk: str = "宋体",
                          font_latin: str = "Times New Roman",
                          font_size: str = "10.5pt",
                          line_spacing: str = "1.0",
                          include_solutions: bool = True) -> str:
    """
    将错题列表转换为 Markdown 字符串 (含 LaTeX 公式)
    字体设置通过 YAML front matter 注入
    """
    lines = []
    # YAML front matter (Pandoc 读取生成 Word 样式)
    lines.append("---")
    lines.append(f'title: "{title}"')
    lines.append(f'date: "{datetime.now().strftime("%Y-%m-%d %H:%M")}"')
    lines.append(f'fontsize: "{font_size}"')
    lines.append(f'mainfont: "{font_latin}"')
    lines.append(f'CJKmainfont: "{font_cjk}"')
    lines.append(f'linestretch: "{line_spacing}"')
    lines.append("---")
    lines.append("")

    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"> 导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"> 题目数量：{len(mistakes)} 道")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 按学科分组
    by_subject: Dict[str, List[Mistake]] = {}
    for m in mistakes:
        by_subject.setdefault(m.subject or "其他", []).append(m)

    for subject, items in by_subject.items():
        lines.append(f"## {subject}")
        lines.append("")
        for i, m in enumerate(items, 1):
            # 显示导入时间
            created_at = ""
            try:
                if m.created_at:
                    dt = datetime.fromisoformat(m.created_at)
                    created_at = dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                pass

            lines.append(f"### 第 {i} 题  {m.knowledge_tag or ''}  ({created_at})")
            lines.append("")
            # 题干
            lines.append("**【题目】**")
            lines.append("")
            q = _normalize_newlines(m.original_question) or "(无题干)"
            lines.append(q.replace("\n", "\\\n"))
            lines.append("")
            # 错因
            if m.error_analysis:
                lines.append("**【错因分析】**")
                lines.append("")
                e = _normalize_newlines(m.error_analysis)
                lines.append(e.replace("\n", "\\\n"))
                lines.append("")
            # 标准解析 (无解析时显示"无解析"); include_solutions=False 时跳过
            if include_solutions:
                solution_text = m.standard_solution or "(无解析)"
                lines.append("**【标准解析】**")
                lines.append("")
                a = _normalize_newlines(solution_text)
                lines.append(a.replace("\n", "\\\n"))
                lines.append("")
            # 变式题 (导出时不包含变式题)
            lines.append("---")
            lines.append("")

    return "\n".join(lines)


def markdown_to_preview(markdown: str) -> str:
    """
    将 Markdown 转为预览用文本 (去除 YAML front matter)
    用于 UI 预览，避免显示 title: fontsize: 等元数据
    """
    if markdown.startswith("---"):
        # 找到第二个 ---
        end = markdown.find("---", 3)
        if end != -1:
            return markdown[end + 3:].lstrip()
    return markdown


# -------------------- HTML 生成 (PDF 用) --------------------
def mistakes_to_html(mistakes: List[Mistake], title: str = "错题本导出",
                     include_solutions: bool = True,
                     font_cjk: str = "宋体",
                     font_latin: str = "Times New Roman",
                     font_size: str = "10.5pt",
                     line_spacing: str = "1.0") -> str:
    """生成带 MathJax 2.7.7 的 HTML (用于 PDF 导出)"""
    title_escaped = _esc(title)

    html_parts = [f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{title_escaped}</title>
<script type="text/x-mathjax-config">
MathJax.Hub.Config({{
  tex2jax: {{
    inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
    displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
    processEscapes: true
  }},
  "SVG": {{
    fontCache: "global",
    scale:135
  }},
  showMathMessages: false
}});
</script>
<script type="text/javascript" src="https://cdn.jsdelivr.net/npm/mathjax@2.7.7/MathJax.js?config=TeX-AMS-MML_SVG"></script>
<style>
  body {{
    font-family: "{font_cjk}", "{font_latin}", -apple-system, sans-serif;
    font-size: {font_size};
    line-height: {line_spacing};
    margin: 40px;
    color: #1D1B20;
    max-width: 800px;
    margin: 0 auto;
  }}
  h1 {{
    color: #6750A4;
    border-bottom: 3px solid #6750A4;
    padding-bottom: 10px;
    font-size: 18pt;
  }}
  h2 {{
    color: #6750A4;
    margin-top: 30px;
    border-left: 4px solid #6750A4;
    padding-left: 10px;
    font-size: 14pt;
  }}
  h3 {{
    color: #4F378B;
    margin-top: 24px;
    font-size: 12pt;
  }}
  .meta {{
    color: #79747E;
    font-size: 10pt;
    margin-bottom: 20px;
  }}
  .question-block {{
    background: #FEF7FF;
    padding: 15px 20px;
    border-radius: 8px;
    margin: 10px 0;
  }}
  .solution-block {{
    background: #F3EDF7;
    padding: 15px 20px;
    border-radius: 8px;
    margin: 10px 0;
    border-left: 3px solid #7C4DFF;
  }}
  .error-block {{
    background: #FFF8E1;
    padding: 10px 15px;
    border-radius: 8px;
    margin: 10px 0;
    border-left: 3px solid #FF9800;
  }}
  hr {{
    border: none;
    border-top: 1px solid #E0E0E0;
    margin: 25px 0;
  }}
</style>
</head>
<body>
<h1>{title_escaped}</h1>
<div class="meta">
  导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} ｜
  题目数量：{len(mistakes)} 道 ｜
  字体：{font_cjk} / {font_latin} {font_size}
</div>
"""]

    # 按学科分组
    by_subject: Dict[str, List[Mistake]] = {}
    for m in mistakes:
        by_subject.setdefault(m.subject or "其他", []).append(m)

    for subject, items in by_subject.items():
        html_parts.append(f"<h2>{_esc(subject)}</h2>")
        for i, m in enumerate(items, 1):
            # 显示导入时间
            created_at = ""
            try:
                if m.created_at:
                    dt = datetime.fromisoformat(m.created_at)
                    created_at = dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                pass

            html_parts.append(
                f"<h3>第 {i} 题  {_esc(m.knowledge_tag or '')}  ({created_at})</h3>"
            )
            # 题干
            html_parts.append('<div class="question-block">')
            html_parts.append("<strong>【题目】</strong><br>")
            html_parts.append(_esc(_normalize_newlines(m.original_question)).replace("\n", "<br>") or "(无题干)")
            html_parts.append("</div>")

            # 错因
            if m.error_analysis:
                html_parts.append('<div class="error-block">')
                html_parts.append("<strong>【错因分析】</strong><br>")
                html_parts.append(_esc(_normalize_newlines(m.error_analysis)).replace("\n", "<br>"))
                html_parts.append("</div>")

            # 标准解析
            if include_solutions:
                html_parts.append('<div class="solution-block">')
                html_parts.append("<strong>【标准解析】</strong><br>")
                solution_text = m.standard_solution or "(无解析)"
                html_parts.append(_esc(_normalize_newlines(solution_text)).replace("\n", "<br>"))
                html_parts.append("</div>")

            html_parts.append("<hr>")

    html_parts.append("</body></html>")
    return "\n".join(html_parts)


# -------------------- Pandoc / wkhtmltopdf 检测 --------------------
def get_pandoc_path() -> Optional[str]:
    """自动检测 Pandoc 路径 (优先级: 项目内 tools/ > 系统 PATH > pypandoc > 常见安装路径)"""
    # 0) 项目内 tools/Pandoc/pandoc[.exe] (打包时内置, 最高优先)
    bundled = _bundled_tool_path("Pandoc", "pandoc.exe") or _bundled_tool_path("Pandoc", "pandoc")
    if bundled:
        return bundled
    import shutil
    # 1) 系统 PATH (用户自己装的 pandoc)
    p = shutil.which("pandoc")
    if p:
        return p
    # 2) pypandoc 自带 / 之前 download_pandoc 下载过的
    try:
        import pypandoc
        return pypandoc.get_pandoc_path()
    except (OSError, ImportError, Exception):
        pass
    # 3) 常见安装路径 (Windows / macOS / Linux)
    common = [
        r"C:\Program Files\Pandoc\pandoc.exe",
        r"C:\Program Files (x86)\Pandoc\pandoc.exe",
        "/usr/bin/pandoc", "/usr/local/bin/pandoc",
        "/opt/homebrew/bin/pandoc",
    ]
    for c in common:
        if os.path.exists(c):
            return c
    return None


def check_pandoc_installed() -> bool:
    """检测 Pandoc 是否可用 (自动检测路径, 不再硬指定)"""
    return get_pandoc_path() is not None


def download_pandoc(progress_callback: Optional[Callable[[str], None]] = None) -> bool:
    """
    自动下载 Pandoc (pypandoc 内置功能)
    :param progress_callback: 进度回调
    :return: 是否成功
    """
    try:
        import pypandoc
        if progress_callback:
            progress_callback("正在下载 Pandoc (约 100MB)，请耐心等待...")
        pypandoc.download_pandoc()
        if progress_callback:
            progress_callback("✓ Pandoc 下载完成")
        return True
    except Exception as e:
        if progress_callback:
            progress_callback(f"Pandoc 下载失败: {e}")
        return False


def get_wkhtmltopdf_path() -> Optional[str]:
    """自动检测 wkhtmltopdf 路径 (优先级: 项目内 tools/ > 系统 PATH > 常见安装路径)"""
    # 0) 项目内 tools/wkhtmltox/bin/wkhtmltopdf[.exe] (打包时内置, 最高优先)
    bundled = (_bundled_tool_path("wkhtmltox", "bin", "wkhtmltopdf.exe")
               or _bundled_tool_path("wkhtmltox", "bin", "wkhtmltopdf")
               or _bundled_tool_path("wkhtmltopdf", "bin", "wkhtmltopdf.exe"))
    if bundled:
        return bundled
    # 1) 系统 PATH
    import shutil
    p = shutil.which("wkhtmltopdf")
    if p:
        return p
    # 2) 常见安装路径
    common_paths = [
        "/usr/bin/wkhtmltopdf", "/usr/local/bin/wkhtmltopdf",
        "/opt/homebrew/bin/wkhtmltopdf",
        r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe",
        r"C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe",
    ]
    for p in common_paths:
        if os.path.exists(p):
            return p
    return None


def check_wkhtmltopdf_installed() -> bool:
    """检测 wkhtmltopdf 是否可用 (兼容旧调用)"""
    return get_wkhtmltopdf_path() is not None


# -------------------- Word 导出 --------------------
def export_to_docx(mistakes: List[Mistake], output_path: str,
                   title: str = "错题本",
                   font_cjk: str = "宋体",
                   font_latin: str = "Times New Roman",
                   font_size: str = "10.5pt",
                   line_spacing: str = "1.0",
                   include_solutions: bool = True,
                   progress_callback: Optional[Callable[[str, float], None]] = None) -> str:
    """
    使用 pypandoc 将含 LaTeX 的 Markdown 转为 Word
    :param progress_callback: (message, percent 0.0-1.0)
    """
    if is_mobile_platform():
        # 移动端 fallback: 把 .docx 路径改为 .html, 调用 export_to_html
        html_path = str(Path(output_path).with_suffix('.html'))
        if progress_callback:
            progress_callback(mobile_export_hint(), 0.2)
        return export_to_html(mistakes, html_path, title=title,
                              include_solutions=include_solutions,
                              font_cjk=font_cjk, font_latin=font_latin,
                              font_size=font_size, line_spacing=line_spacing,
                              progress_callback=progress_callback)

    def _progress(msg, pct):
        if progress_callback:
            progress_callback(msg, pct)

    _progress("正在生成 Markdown...", 0.1)
    md = mistakes_to_markdown(mistakes, title=title,
                                font_cjk=font_cjk, font_latin=font_latin,
                                font_size=font_size, line_spacing=line_spacing,
                                include_solutions=include_solutions)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # 检测 Pandoc
    _progress("正在检测 Pandoc...", 0.2)
    try:
        import pypandoc
    except ImportError:
        raise RuntimeError("pypandoc 未安装，请运行 `pip install pypandoc`")

    pandoc_path = get_pandoc_path()
    if not pandoc_path:
        # 仅当真没找到 pandoc 时才尝试下载
        _progress("Pandoc 未安装，正在自动下载...", 0.3)
        try:
            pypandoc.download_pandoc()
            _progress("✓ Pandoc 下载完成", 0.5)
        except Exception as e:
            raise RuntimeError(
                f"Pandoc 未安装且自动下载失败: {e}\n"
                f"请手动安装 Pandoc: https://pandoc.org/installing.html"
            )
    elif pandoc_path.lower() != shutil.which("pandoc", ) if False else True:
        # 让 pypandoc 用我们检测到的路径
        os.environ["PYPANDOC_PANDOC"] = pandoc_path

    _progress("正在转换 Markdown → Word...", 0.6)
    pypandoc.convert_text(
        md,
        "docx",
        format="md",
        outputfile=output_path,
        extra_args=[
            "--standalone",
            "--toc",
            "--toc-depth=3",
            "--mathml",
        ],
    )
    _progress("✓ Word 导出完成", 1.0)
    return output_path


# -------------------- PDF 导出 --------------------
def export_to_pdf(mistakes: List[Mistake], output_path: str,
                  title: str = "错题本",
                  include_solutions: bool = True,
                  font_cjk: str = "宋体",
                  font_latin: str = "Times New Roman",
                  font_size: str = "10.5pt",
                  line_spacing: str = "1.0",
                  progress_callback: Optional[Callable[[str, float], None]] = None) -> str:
    """
    使用 pdfkit + MathJax 2.7.7 HTML 转 PDF
    """
    if is_mobile_platform():
        # 移动端 fallback: 直接导出 HTML (含 MathJax), 用户分享到电脑后再转 PDF
        html_path = str(Path(output_path).with_suffix('.html'))
        if progress_callback:
            progress_callback(mobile_export_hint(), 0.2)
        return export_to_html(mistakes, html_path, title=title,
                              include_solutions=include_solutions,
                              font_cjk=font_cjk, font_latin=font_latin,
                              font_size=font_size, line_spacing=line_spacing,
                              progress_callback=progress_callback)

    def _progress(msg, pct):
        if progress_callback:
            progress_callback(msg, pct)

    _progress("正在生成 HTML...", 0.1)
    html_str = mistakes_to_html(mistakes, title=title,
                                 include_solutions=include_solutions,
                                 font_cjk=font_cjk, font_latin=font_latin,
                                 font_size=font_size, line_spacing=line_spacing)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    tmp_html = Path(output_path).with_suffix(".html")
    with open(tmp_html, "w", encoding="utf-8") as f:
        f.write(html_str)

    _progress("正在检测 wkhtmltopdf...", 0.2)
    try:
        import pdfkit
    except ImportError:
        raise RuntimeError("pdfkit 未安装，请运行 `pip install pdfkit`")

    # 检测 wkhtmltopdf (优先用项目内 tools/)
    wk_path = get_wkhtmltopdf_path()
    if not wk_path:
        raise RuntimeError(
            f"wkhtmltopdf 未安装 (已检测项目内 tools/ + 系统 PATH + 常见安装路径)\n"
            f"已保存 HTML 文件: {tmp_html}\n"
            f"解决方案：\n"
            f"  1. 在项目根创建 tools/wkhtmltox/bin/wkhtmltopdf.exe (推荐, 打包时内置)\n"
            f"  2. 或安装到系统: https://wkhtmltopdf.org/downloads.html\n"
            f"  3. 或直接在浏览器打开 HTML 文件，按 Ctrl+P 另存为 PDF"
        )

    options = {
        "page-size": "A4",
        "margin-top": "20mm",
        "margin-right": "18mm",
        "margin-bottom": "20mm",
        "margin-left": "18mm",
        "encoding": "UTF-8",
        "enable-local-file-access": "",
        "javascript-delay": "5000",
        "no-stop-slow-scripts": "",
        "enable-javascript": "",
        "dpi": 150,
        "quiet": "",
    }

    config = pdfkit.configuration(wkhtmltopdf=wk_path)

    _progress("正在转换 HTML → PDF (需等待 MathJax 渲染)...", 0.4)
    try:
        pdfkit.from_file(str(tmp_html), output_path,
                         options=options, configuration=config)
    except Exception as e:
        raise RuntimeError(
            f"PDF 转换失败：{e}\n"
            f"已保存 HTML 文件: {tmp_html}，可在浏览器打开后另存为 PDF"
        )

    _progress("✓ PDF 导出完成", 1.0)
    return output_path




# -------------------- HTML 导出 -------------------
def export_to_html(mistakes: List[Mistake], output_path: str,
                   title: str = "错题本",
                   include_solutions: bool = True,
                   font_cjk: str = "宋体",
                   font_latin: str = "Times New Roman",
                   font_size: str = "10.5pt",
                   line_spacing: str = "1.0",
                   progress_callback: Optional[Callable[[str, float], None]] = None) -> str:
    """
    导出为离线 HTML (与 PDF 同款, MathJax 2.7.7 渲染 LaTeX)
    移动端推荐此格式 (PDF/Word 需要桌面端软件支持)
    """
    def _progress(msg, pct):
        if progress_callback:
            progress_callback(msg, pct)

    _progress("正在生成 HTML...", 0.2)
    html_str = mistakes_to_html(mistakes, title=title,
                                 include_solutions=include_solutions,
                                 font_cjk=font_cjk, font_latin=font_latin,
                                 font_size=font_size, line_spacing=line_spacing)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_str)

    _progress("✓ HTML 导出完成", 1.0)
    return output_path

# -------------------- 单题导出 --------------------
def export_single_mistake(mistake: Mistake, output_dir: str,
                          fmt: str = "docx") -> str:
    """导出单道错题"""
    output_path = os.path.join(output_dir, f"错题_{mistake.subject or '未分类'}_{mistake.id[:8]}.{fmt}")
    if fmt == "docx":
        return export_to_docx([mistake], output_path,
                              title=f"{mistake.subject} - {mistake.knowledge_tag}")
    else:
        return export_to_pdf([mistake], output_path,
                              title=f"{mistake.subject} - {mistake.knowledge_tag}")
