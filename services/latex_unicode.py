# ============================================================
# LaTeX -> Unicode 数学文本 (可选中复制的真文本)
# ============================================================
# 高中范围 LaTeX 公式转成 Unicode 数学符号 (x²、√3、θ、≤、∫ 等),
# 用于正文内联公式渲染: 可选中/复制, 基线对齐, 暗色自适应, 零延迟
# ============================================================

import re

# 常用命令 -> Unicode 符号
_LATEX_TO_TEXT = [
    (r"\dfrac", r"\frac"),
    (r"\cdot", "·"),
    (r"\times", "×"),
    (r"\div", "÷"),
    (r"\leq", "≤"),
    (r"\geq", "≥"),
    (r"\le", "≤"),
    (r"\ge", "≥"),
    (r"\neq", "≠"),
    (r"\approx", "≈"),
    (r"\pm", "±"),
    (r"\infty", "∞"),
    (r"\theta", "θ"),
    (r"\alpha", "α"),
    (r"\beta", "β"),
    (r"\gamma", "γ"),
    (r"\delta", "δ"),
    (r"\varepsilon", "ε"),
    (r"\epsilon", "ε"),
    (r"\lambda", "λ"),
    (r"\mu", "μ"),
    (r"\sigma", "σ"),
    (r"\omega", "ω"),
    (r"\phi", "φ"),
    (r"\varphi", "φ"),
    (r"\pi", "π"),
    (r"\sin", "sin"),
    (r"\cos", "cos"),
    (r"\tan", "tan"),
    (r"\cot", "cot"),
    (r"\log", "log"),
    (r"\ln", "ln"),
    (r"\lg", "lg"),
    (r"\rightarrow", "→"),
    (r"\Rightarrow", "⇒"),
    (r"\leftarrow", "←"),
    (r"\Leftrightarrow", "⇔"),
    (r"\to", "→"),
    (r"\sum", "Σ"),
    (r"\prod", "∏"),
    (r"\int", "∫"),
    (r"\partial", "∂"),
    (r"\in", "∈"),
    (r"\notin", "∉"),
    (r"\subset", "⊂"),
    (r"\subseteq", "⊆"),
    (r"\cup", "∪"),
    (r"\cap", "∩"),
    (r"\circ", "°"),
    (r"\degree", "°"),
    (r"\triangle", "△"),
    (r"\angle", "∠"),
    (r"\perp", "⊥"),
    (r"\parallel", "∥"),
    (r"\sim", "∼"),
    (r"\cong", "≅"),
    (r"\because", "∵"),
    (r"\therefore", "∴"),
    (r"\forall", "∀"),
    (r"\exists", "∃"),
    (r"\emptyset", "∅"),
    (r"\cdots", "⋯"),
    (r"\ldots", "…"),
    (r"\prime", "′"),
]

# Unicode 上标/下标映射
_SUPER_MAP = {"0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
              "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
              "+": "⁺", "-": "⁻", "=": "⁼", "(": "⁽", ")": "⁾",
              "n": "ⁿ", "i": "ⁱ"}
_SUB_MAP = {"0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄",
            "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉",
            "+": "₊", "-": "₋", "=": "₌", "(": "₍", ")": "₎",
            "i": "ᵢ", "j": "ⱼ", "k": "ₖ", "n": "ₙ", "x": "ₓ"}


def _to_super(s: str) -> str:
    return "".join(_SUPER_MAP.get(ch, ch) for ch in s)


def _to_sub(s: str) -> str:
    return "".join(_SUB_MAP.get(ch, ch) for ch in s)


def _simple_frac(m):
    """frac{a}{b} -> a/b (含加减运算符时补括号)"""
    num, den = m.group(1), m.group(2)
    if re.search(r"[+\-]|\\pm", num) and not num.startswith("("):
        num = f"({num})"
    if re.search(r"[+\-]|\\pm", den) and not den.startswith("("):
        den = f"({den})"
    return f"{num}/{den}"


def _sqrt_conv(m):
    inner = m.group(1)
    if re.search(r"[+\-]|\\pm", inner) and not inner.startswith("("):
        return f"√({inner})"
    return f"√{inner}"


def latex_to_unicode(latex: str) -> str:
    """
    单个 LaTeX 公式 -> 可读的 Unicode 数学文本 (用于正文内联, 可选中复制)
    例: x^2 -> x² ; \\frac{1}{2} -> 1/2 ; \\sqrt{3} -> √3 ; \\theta -> θ
    """
    s = (latex or "").strip()
    if not s:
        return ""
    # 剥外层括号
    while s.startswith("(") and s.endswith(")"):
        s = s[1:-1].strip()
    # 常用命令替换 (先做: dfrac -> frac, 使后续 frac 正则生效)
    for old, new in _LATEX_TO_TEXT:
        s = s.replace(old, new)
    # 换行 -> 空格
    s = s.replace(r"\\", " ")
    # 分数 (支持一层嵌套)
    for _ in range(2):
        s = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", _simple_frac, s)
    # 根式 (n 次根优先, 再处理普通根式, 最后兜底替换残留 \\sqrt)
    s = re.sub(r"\\sqrt\[([^{}]*)\]\{([^{}]*)\}", r"\2", s)
    s = re.sub(r"\\sqrt\{([^{}]*)\}", _sqrt_conv, s)
    s = s.replace(r"\\sqrt", "√")
    # 上标: x^2 -> x², x^{n+1} -> 转换失败时 ^(n+1)
    def _sup(m):
        inner = m.group(1) or m.group(2)
        if inner in ("'", "′"):
            return "′"
        conv = _to_super(inner)
        if conv == inner:
            return f"^({inner})"
        return conv
    s = re.sub(r"\^\{([^{}]*)\}|\^([0-9a-zA-Z])", _sup, s)
    # 下标: x_1 -> x₁
    def _sub(m):
        inner = m.group(1) or m.group(2)
        conv = _to_sub(inner)
        if conv == inner:
            return f"_({inner})"
        return conv
    s = re.sub(r"_\{([^{}]*)\}|_([0-9a-zA-Z])", _sub, s)
    # text/mathrm/mathbf 包装 -> 保留内容
    s = re.sub(r"\\(?:text|mathrm|mathbf|mathit|boldsymbol)\{(?:([^{}]*))\}", r"\1", s)
    # 清理残留命令修饰符
    for _cmd in ("\\left", "\\right", "\\quad", "\\qquad", "\\displaystyle",
                 "\\textstyle", "\\limits", "\\,", "\\;", "\\!",
                 "\\big", "\\Big", "\\bigg", "\\Bigg", "\\dfrac",
                 "\\vec", "\\hat", "\\bar", "\\overline", "\\circ",
                 "\\operatorname", "\\begin", "\\end", "\\begin{cases}"):
        s = s.replace(_cmd, "")
    # 掉落剩余反斜杠命令
    s = re.sub(r"\\([a-zA-Z]+)\*?\b", "", s)
    s = s.replace("{", "").replace("}", "")
    s = re.sub(r"\s{2,}", " ", s)
    s = re.sub(r"\s*([×·÷≤≥≠≈±→⇒←⇔∈∉±√])\s*", r"\1", s)
    return s.strip()


def latex_to_plain_text(text: str) -> str:
    """
    将含 LaTeX 的文本转为可读纯文本 (用于列表预览)
    :param text: 含 $...$ 的原始文本
    :return: 去除 $ 标记并转为 Unicode 后的文本
    """
    s = text or ""
    parts = re.split(r"(\$\$[^\$]+\$\$|\$[^\$]+\$)", s)
    out = []
    for p in parts:
        m = re.fullmatch(r"\$\$([^\$]+)\$\$|\$([^\$]+)\$", p)
        if m:
            out.append(latex_to_unicode(m.group(1) or m.group(2)))
        else:
            out.append(p)
    s = "".join(out)
    s = re.sub(r"\s+", " ", s)
    return s.strip()
