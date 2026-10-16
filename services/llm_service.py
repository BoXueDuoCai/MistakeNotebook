# ============================================================
# 大模型 API 调用服务
# ============================================================
# 说明：
#   1. 支持多家大模型供应商 (Z.ai / OpenAI / DeepSeek / Moonshot / 自定义)
#   2. 调用多模态模型，发送图片(base64)和文本
#   3. 返回严格 JSON 格式的结构化数据
#   4. 提供 Prompt 设计：错题分析 + 变式题生成
# ============================================================

import json
import base64
import requests
from typing import Optional, Dict, Any, List

from config import LLM_PROVIDERS


# -------------------- Prompt 设计 --------------------
# 错题分析 + 变式题生成 Prompt
SYSTEM_PROMPT = """你是一名资深高中教师，擅长分析学生错题并生成精准的解题与变式训练。

【任务要求】
1. 仔细分析用户提供的错题图片和文本说明
2. 识别学科、知识点、错因
3. 给出标准解析（含 LaTeX 公式，使用 $$...$$ 或 $...$ 包裹）
4. 生成 2 道同知识点的变式题，难度与原题相当或略高

【输出格式】
必须严格输出以下 JSON 格式（不要包含任何 Markdown 代码块标记，不要解释性文字）：

{
  "subject": "学科（数学/物理/化学/生物/语文/英语/历史/地理/政治/信息科技）",
  "knowledge_tag": "知识点标签（如：三角函数、牛顿第二定律、化学平衡）",
  "original_question": "纯净题干文本（不含解题部分，含 $$..$$ LaTeX 公式）",
  "image_desc": "对题目中图形的简要描述",
  "error_analysis": "学生当时为什么做错的诊断分析（基于用户提供的错误思路）",
  "standard_solution": "标准解析，分步骤说明（含 LaTeX 公式）",
  "variants": [
    {
      "question": "变式1题干（同知识点不同情境或数值）",
      "solution": "变式1详细解析（含 LaTeX 公式）"
    },
    {
      "question": "变式2题干",
      "solution": "变式2详细解析"
    }
  ]
}

【重要约束】
- 严格 JSON，不要 ```json 包裹
- 所有 LaTeX 公式必须用 $$ 或 $ 包裹
- variants 必须包含 2 道变式题
- 错因分析要结合用户提供的"错误思路"
"""

# 变式题批改 Prompt
GRADING_SYSTEM_PROMPT = """你是一名严格的高中教师，正在批改学生的变式题作业。

【任务】
1. 根据变式题题干和标准解析
2. 评估学生的作答
3. 给出评分与反馈

【输出格式】严格 JSON：
{
  "is_correct": true 或 false,
  "score": 0-100 整数,
  "feedback": "详细反馈，指出正确与错误之处，给出改进建议"
}
不要包含 Markdown 代码块标记。"""


# OCR Prompt (仅识别题干，不分析)
OCR_PROMPT = """你是一名专业的 OCR 识别引擎。请识别用户提供的图片中的题目文本。

【任务要求】
1. 仅识别图片中的题目文字 (题干)
2. 不要识别答题内容、解析、批注等
3. 数学公式用 $$...$$ 或 $...$ 包裹 (LaTeX 语法)
4. 图表用文字描述 (如：[图：一个直角三角形，边长分别为 3, 4, 5])

【输出格式】严格 JSON：
{
  "question_text": "识别出的题干文本 (含 LaTeX 公式)"
}
不要包含 Markdown 代码块标记。"""


# 仅生成解析的 Prompt (用于导出时为无解析错题生成)
SOLUTION_ONLY_PROMPT = """你是一名资深高中教师。请为以下错题生成标准解析（不要生成变式题）。

【任务要求】
1. 给出标准解析 (含 LaTeX 公式，使用 $$...$$ 或 $...$ 包裹)
2. 分步骤说明
3. 不要生成变式题

【输出格式】严格 JSON：
{
  "standard_solution": "标准解析文本 (含 LaTeX 公式)"
}
不要包含 Markdown 代码块标记。"""


class LLMService:
    """大模型调用服务"""

    def __init__(self, provider: str, api_key: str, model: str,
                 custom_url: str = "", timeout: int = 30,
                 model_ocr: str = "", deep_thinking: bool = False):
        """
        初始化
        :param provider: 供应商标识 (zai/openai/deepseek/moonshot/custom)
        :param api_key: API Key
        :param model: 解析/变式文本模型名称
        :param model_ocr: OCR 视觉模型名称 (为空时回退到 model)
        :param deep_thinking: 是否开启深度思考 (通过 API 参数, 而非仅提示词)
        """
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.model_ocr = model_ocr or model
        self.deep_thinking = deep_thinking
        self.timeout = timeout

        # 获取供应商配置
        if provider in LLM_PROVIDERS:
            self.provider_config = LLM_PROVIDERS[provider]
            self.chat_url = (custom_url if provider == "custom"
                             else self.provider_config.get("chat_url", ""))
        else:
            self.provider_config = LLM_PROVIDERS["custom"]
            self.chat_url = custom_url

    def _thinking_payload(self) -> dict:
        """
        深度思考的真实 API 参数 (按供应商)
        - zai / deepseek / moonshot: thinking: {type: enabled}
        - openai (o 系列/gpt-5): reasoning_effort
        - custom: 不支持参数, 返回空 (使用提示词降级)
        """
        if not self.deep_thinking or self.provider == "custom":
            return {}
        if self.provider == "openai":
            # OpenAI o1/o3/gpt-5 系列: reasoning_effort
            return {"reasoning_effort": "high"}
        # 智谱 GLM-4.5+ / DeepSeek V3.2+ / Kimi K2 均支持 thinking 参数
        return {"thinking": {"type": "enabled"}}

    def _with_model(self, model_name: str) -> "LLMService":
        """返回一个使用指定模型的新实例 (共享配置, 仅切换 model)"""
        svc = LLMService(
            provider=self.provider, api_key=self.api_key,
            model=model_name, custom_url=self.chat_url,
            timeout=self.timeout, model_ocr=self.model_ocr,
            deep_thinking=self.deep_thinking,
        )
        return svc

    def _inject_deep_thinking(self, system_prompt: str) -> str:
        """提示词层深度思考 (仅 custom 供应商无参数可传时使用; 已知供应商走 API 参数)"""
        if not self.deep_thinking or self.provider != "custom":
            return system_prompt
        return (system_prompt + "\n\n【深度思考要求】\n"
                "请在给出最终答案前, 先进行深入的逐步推理, 仔细验证每一步, "
                "确保结果的准确性和完整性。")

    # -------------------- 工具方法 --------------------
    _MAX_IMAGE_SIDE = 2048  # 视觉 API 常见限制, 超过自动缩小 (兼容性)

    @staticmethod
    def image_to_base64(image_path) -> str:
        """
        将本地图片转为 base64 字符串
        超过 2048px 自动等比例缩小, 避免超大图片被视觉 API 拒绝
        :param image_path: str 或 pathlib.Path 均可
        """
        from PIL import Image as _Image
        import io as _io
        # 容错: Flet FilePicker 在桌面端可能返回 WindowsPath/PosixPath
        if image_path is not None and not isinstance(image_path, str):
            image_path = str(image_path)
        with _Image.open(image_path) as img:
            fmt = (img.format or "PNG").upper()
            img = img.copy()
            max_side = max(img.size)
            if max_side > LLMService._MAX_IMAGE_SIDE:
                ratio = LLMService._MAX_IMAGE_SIDE / max_side
                img = img.resize(
                    (max(1, int(img.width * ratio)), max(1, int(img.height * ratio))),
                    _Image.LANCZOS,
                )
            if fmt in ("JPEG", "JPG"):
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                buf = _io.BytesIO()
                img.save(buf, "JPEG", quality=90)
                return base64.b64encode(buf.getvalue()).decode("utf-8")
            # 其他格式统一转 PNG (保留透明度)
            if img.mode not in ("RGB", "L", "RGBA"):
                img = img.convert("RGBA" if img.mode in ("P", "LA") else "RGB")
            buf = _io.BytesIO()
            img.save(buf, "PNG")
            return base64.b64encode(buf.getvalue()).decode("utf-8")

    @staticmethod
    def get_mime_type(image_path) -> str:
        """根据扩展名获取 MIME 类型 (兼容 str / pathlib.Path)"""
        # 关键修复: 先转 str 再 lower, 避免 'WindowsPath' object has no attribute 'lower'
        if image_path is None:
            return "image/jpeg"
        s = str(image_path).lower()
        ext = s.split(".")[-1] if "." in s else ""
        return {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "webp": "image/webp",
            "bmp": "image/bmp",
        }.get(ext, "image/jpeg")

    def _headers(self) -> Dict[str, str]:
        """构建请求头"""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _call_chat_api(self, messages: List[Dict], temperature: float = 0.3,
                        max_tokens: int = 4096,
                        use_response_format: bool = True) -> Dict:
        """
        通用 Chat Completions 调用
        - 支持 response_format 容错：若供应商不支持，自动重试一次
        - 超时 60s，无自动重试 (业务层自行处理)
        :raises: RuntimeError, ValueError
        """
        if not self.api_key:
            raise ValueError("API Key 未配置，请到设置页填写")
        if not self.chat_url:
            raise ValueError("API URL 未配置")
        if not self.model:
            raise ValueError("模型名称未配置")

        def _do_request(with_format: bool, with_thinking: bool) -> requests.Response:
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if with_format:
                # 强制 JSON 输出 (部分供应商支持)
                payload["response_format"] = {"type": "json_object"}
            if with_thinking:
                # 深度思考: 走真实 API 参数 (而非仅提示词)
                payload.update(self._thinking_payload())
            return requests.post(
                self.chat_url,
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
            )

        try:
            from utils.run_guard import debug_log
            import time as _time
            debug_log(f"[llm] 请求开始 model={self.model} 超时={self.timeout}s")
            _t0 = _time.time()
            resp = _do_request(use_response_format, self.deep_thinking)
            # 若 400 错误且启用 response_format / thinking, 逐项降级重试
            if resp.status_code == 400 and (use_response_format or self.deep_thinking):
                err_text = resp.text.lower()
                if ("response_format" in err_text or "json_object" in err_text
                        or "json mode" in err_text or "unsupported" in err_text
                        or "thinking" in err_text or "reasoning_effort" in err_text):
                    print("[LLM] response_format/thinking 不支持，降级重试...")
                    resp = _do_request(False, False)
            resp.raise_for_status()
            debug_log(f"[llm] 请求成功 耗时={_time.time() - _t0:.1f}s 模型={self.model}")
            return resp.json()
        except requests.exceptions.Timeout:
            debug_log(f"[llm] 超时 after {_time.time() - _t0:.1f}s")
            raise RuntimeError("请求超时，请检查网络或稍后重试")
        except requests.exceptions.HTTPError as e:
            debug_log(f"[llm] HTTP错误 {resp.status_code} after {_time.time() - _t0:.1f}s")
            detail = ""
            try:
                detail = resp.json().get("error", {}).get("message", "")
            except Exception:
                pass
            raise RuntimeError(f"API 返回错误 {resp.status_code}: {detail or str(e)}")
        except requests.exceptions.RequestException as e:
            debug_log(f"[llm] 网络错误 after {_time.time() - _t0:.1f}s: {e}")
            raise RuntimeError(f"网络请求失败: {e}")

    @staticmethod
    def _extract_content(resp_json: Dict) -> str:
        """从 OpenAI 兼容格式响应中提取内容"""
        try:
            choices = resp_json.get("choices", [])
            if not choices:
                raise ValueError("响应中没有 choices")
            return choices[0].get("message", {}).get("content", "")
        except (KeyError, IndexError) as e:
            raise ValueError(f"解析响应失败: {e}")

    @staticmethod
    def _parse_json_response(content: str) -> Dict[str, Any]:
        """
        健壮地解析 LLM 返回的 JSON
        (容忍 ```json 包裹、尾随逗号、前后空白等)
        """
        # 去除 markdown 代码块 / BOM
        cleaned = content.strip()
        if cleaned.startswith("\ufeff"):
            cleaned = cleaned.lstrip("\ufeff").strip()
        if cleaned.startswith("```"):
            # 去掉首行 ```json
            lines = cleaned.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)

        # 尝试直接解析
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # 尝试找到第一个 { 和最后一个 }
        first = cleaned.find("{")
        last = cleaned.rfind("}")
        if first != -1 and last != -1:
            try:
                return json.loads(cleaned[first:last + 1])
            except json.JSONDecodeError:
                pass

        # 容忍尾随逗号 (LLM 常见): 去掉 ] / } 前的多余逗号后重试
        import re as _re
        cleaned2 = _re.sub(r",\s*([}\]])", r"\1", cleaned)
        try:
            return json.loads(cleaned2)
        except json.JSONDecodeError:
            pass
        if first != -1 and last != -1:
            try:
                return json.loads(cleaned2[first:last + 1])
            except json.JSONDecodeError:
                pass

        raise ValueError(f"无法解析 JSON 响应: {content[:200]}...")

    # -------------------- 核心业务接口 --------------------
    def _call_chat_api_stream(self, messages: List[Dict], temperature: float = 0.3,
                              max_tokens: int = 4096,
                              use_response_format: bool = True):
        """
        流式调用 Chat Completions (SSE)
        :yield: (text_delta, reasoning_delta) 增量片段
                 reasoning_delta 为思维链内容 (支持 DeepSeek/Z.ai/通义等 reasoning_content)
        """
        from utils.run_guard import debug_log
        if not self.api_key:
            raise ValueError("API Key 未配置，请到设置页填写")
        if not self.chat_url:
            raise ValueError("API URL 未配置")
        if not self.model:
            raise ValueError("模型名称未配置")

        def _do_request(with_format: bool, with_thinking: bool) -> requests.Response:
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            }
            if with_format:
                payload["response_format"] = {"type": "json_object"}
            if with_thinking:
                # 深度思考: 走真实 API 参数 (而非仅提示词)
                payload.update(self._thinking_payload())
            return requests.post(
                self.chat_url,
                headers=self._headers(),
                json=payload,
                # (连接超时, 读超时): 流式有数据即不会触发读超时
                timeout=(10, 90),
                stream=True,
            )

        debug_log(f"[llm] 流式请求开始 model={self.model}")
        resp = _do_request(use_response_format, self.deep_thinking)
        if resp.status_code == 400 and (use_response_format or self.deep_thinking):
            err_text = resp.text.lower()
            if ("response_format" in err_text or "json_object" in err_text
                    or "json mode" in err_text or "unsupported" in err_text
                    or "thinking" in err_text or "reasoning_effort" in err_text):
                debug_log("[llm] response_format/thinking 不支持, 降级为流式重试")
                resp = _do_request(False, False)
        resp.raise_for_status()

        full_text = ""
        full_reasoning = ""
        try:
            # 注意: 必须用 bytes 迭代 (decode_unicode=True 会把 UTF-8 多字节
            # 中文在 chunk 边界撕裂, 导致丢帧/乱码)。按行字节找 "data:" 再解码。
            for raw in resp.iter_lines(decode_unicode=False):
                if not raw or not raw.startswith(b"data:"):
                    continue
                data = raw[5:].strip()
                if data == b"[DONE]":
                    break
                try:
                    chunk = json.loads(data.decode("utf-8", errors="replace"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                text = delta.get("content") or ""
                reasoning = delta.get("reasoning_content") or ""
                if text:
                    full_text += text
                if reasoning:
                    full_reasoning += reasoning
                if text or reasoning:
                    yield text, reasoning
        except requests.exceptions.RequestException as e:
            debug_log(f"[llm] 流式中断: {e} (已收到 {len(full_text)} 字)")
            if not full_text.strip():
                raise RuntimeError(f"流式连接中断: {e}")
        except Exception:
            if not full_text.strip():
                raise
        finally:
            debug_log(f"[llm] 流式结束 共 {len(full_text)} 字")

    # -------------------- 流式业务接口 --------------------
    def analyze_mistake_stream(self, image_path: Optional[str] = None,
                               question_text: str = "",
                               error_thinking: str = "",
                               on_delta=None) -> Dict[str, Any]:
        """流式分析错题 (on_delta(text, reasoning) 实时回调), 返回解析 JSON"""
        content_parts: List[Dict] = []
        if image_path:
            try:
                b64 = self.image_to_base64(image_path)
                mime = self.get_mime_type(image_path)
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"}
                })
            except (IOError, OSError) as e:
                print(f"[LLM] 图片读取失败: {e}")

        text_prompt = ""
        if question_text:
            text_prompt += f"【题目文本】\n{question_text}\n\n"
        if error_thinking:
            text_prompt += f"【我当时错误的解题思路】\n{error_thinking}\n\n"
        text_prompt += "请分析这道错题，并按指定 JSON 格式输出。"
        if not text_prompt.strip():
            raise ValueError("请提供题目图片或文本")
        content_parts.append({"type": "text", "text": text_prompt})

        messages = [
            {"role": "system", "content": self._inject_deep_thinking(SYSTEM_PROMPT)},
            {"role": "user", "content": content_parts},
        ]
        max_tokens = 8192 if (image_path and content_parts and
                              any(p.get("type") == "image_url" for p in content_parts)) else 4096
        full = ""
        for text, reasoning in self._call_chat_api_stream(
                messages, temperature=0.3, max_tokens=max_tokens):
            full += text
            if on_delta:
                try:
                    on_delta(text, reasoning)
                except Exception:
                    pass
        return self._parse_json_response(full)

    def ocr_image_stream(self, image_path: str, on_delta=None) -> str:
        """流式 OCR (实时回调), 返回题干文本"""
        b64 = self.image_to_base64(image_path)
        mime = self.get_mime_type(image_path)
        content_parts = [
            {"type": "image_url",
             "image_url": {"url": f"data:{mime};base64,{b64}"}},
            {"type": "text", "text": "请识别图片中的题目文字，按 JSON 格式输出。"},
        ]
        messages = [
            {"role": "system", "content": self._inject_deep_thinking(OCR_PROMPT)},
            {"role": "user", "content": content_parts},
        ]
        # OCR 使用视觉模型
        old_model = self.model
        self.model = self.model_ocr
        try:
            full = ""
            for text, reasoning in self._call_chat_api_stream(
                    messages, temperature=0.1, max_tokens=2048):
                full += text
                if on_delta:
                    try:
                        on_delta(text, reasoning)
                    except Exception:
                        pass
            parsed = self._parse_json_response(full)
            return parsed.get("question_text", "")
        finally:
            self.model = old_model  # 恢复

    def grade_answer_stream(self, question: str, standard_solution: str,
                            user_answer: str, on_delta=None) -> Dict[str, Any]:
        """流式 AI 批改 (实时回调), 返回反馈 JSON"""
        prompt = f"""请批改学生的作答：

【变式题】
{question}

【标准解析】
{standard_solution}

【学生作答】
{user_answer or "(未作答)"}

请按指定 JSON 格式输出批改结果。"""
        messages = [
            {"role": "system", "content": GRADING_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        full = ""
        for text, reasoning in self._call_chat_api_stream(
                messages, temperature=0.2, max_tokens=2048):
            full += text
            if on_delta:
                try:
                    on_delta(text, reasoning)
                except Exception:
                    pass
        return self._parse_json_response(full)

    # -------------------- 核心业务接口 --------------------
    def analyze_mistake(self, image_path: Optional[str] = None,
                        question_text: str = "",
                        error_thinking: str = "") -> Dict[str, Any]:
        """
        分析错题并生成解析 + 变式题
        :param image_path: 错题图片路径 (可选)
        :param question_text: 用户输入的题干 (可选)
        :param error_thinking: 用户输入的错误思路
        :return: 解析后的 JSON 字典
        """
        # 构建用户消息内容
        content_parts: List[Dict] = []

        # 添加图片 (如果存在)
        if image_path:
            try:
                b64 = self.image_to_base64(image_path)
                mime = self.get_mime_type(image_path)
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"}
                })
            except (IOError, OSError) as e:
                print(f"[LLM] 图片读取失败: {e}")

        # 添加文本提示
        text_prompt = ""
        if question_text:
            text_prompt += f"【题目文本】\n{question_text}\n\n"
        if error_thinking:
            text_prompt += f"【我当时错误的解题思路】\n{error_thinking}\n\n"
        text_prompt += "请分析这道错题，并按指定 JSON 格式输出。"

        if not text_prompt.strip():
            raise ValueError("请提供题目图片或文本")

        content_parts.append({"type": "text", "text": text_prompt})

        # 调用 API
        messages = [
            {"role": "system", "content": self._inject_deep_thinking(SYSTEM_PROMPT)},
            {"role": "user", "content": content_parts},
        ]
        # 视觉模型 max_tokens 提高，避免长题被截断
        max_tokens = 8192 if (image_path and content_parts and
                              any(p.get("type") == "image_url" for p in content_parts)) else 4096
        resp = self._call_chat_api(messages, temperature=0.3,
                                    max_tokens=max_tokens)
        content = self._extract_content(resp)
        return self._parse_json_response(content)

    def generate_variants(self, question: str, solution: str,
                          knowledge_tag: str = "",
                          num_variants: int = 2) -> List[Dict]:
        """
        生成变式题 (单独调用，用于错题库的"变式挑战")
        :return: [{"question":..., "solution":...}, ...]
        """
        prompt = f"""请基于以下原题生成 {num_variants} 道同知识点的变式题。

【原题】
{question}

【标准解析】
{solution}

【知识点】
{knowledge_tag or "未指定"}

请输出 JSON：
{{
  "variants": [
    {{"question": "变式题干", "solution": "变式解析"}}
  ]
}}
"""
        messages = [
            {"role": "system", "content": self._inject_deep_thinking(SYSTEM_PROMPT)},
            {"role": "user", "content": prompt},
        ]
        resp = self._call_chat_api(messages, temperature=0.7)
        content = self._extract_content(resp)
        parsed = self._parse_json_response(content)
        return parsed.get("variants", [])[:num_variants]

    def grade_answer(self, question: str, standard_solution: str,
                     user_answer: str) -> Dict[str, Any]:
        """
        AI 批改用户变式题作答
        :return: {"is_correct": bool, "score": int, "feedback": str}
        """
        prompt = f"""请批改学生的作答：

【变式题】
{question}

【标准解析】
{standard_solution}

【学生作答】
{user_answer or "(未作答)"}

请按指定 JSON 格式输出批改结果。"""
        messages = [
            {"role": "system", "content": GRADING_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        resp = self._call_chat_api(messages, temperature=0.2)
        content = self._extract_content(resp)
        return self._parse_json_response(content)

    # -------------------- OCR 识别 --------------------
    def ocr_image(self, image_path: str) -> str:
        """
        识别图片中的题干文字 (OCR)
        :return: 识别出的题干文本 (含 LaTeX 公式)
        """
        if not image_path:
            raise ValueError("请提供图片路径")

        b64 = self.image_to_base64(image_path)
        mime = self.get_mime_type(image_path)

        content_parts = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"}
            },
            {"type": "text", "text": "请识别图片中的题目文字，按 JSON 格式输出。"},
        ]

        messages = [
            {"role": "system", "content": self._inject_deep_thinking(OCR_PROMPT)},
            {"role": "user", "content": content_parts},
        ]
        old_model = self.model
        self.model = self.model_ocr
        try:
            # OCR 不需要太多 token
            resp = self._call_chat_api(messages, temperature=0.1, max_tokens=2048)
            content = self._extract_content(resp)
            parsed = self._parse_json_response(content)
            return parsed.get("question_text", "")
        finally:
            self.model = old_model

    # -------------------- 仅生成解析 (无变式) --------------------
    def generate_solution_only(self, question: str,
                                knowledge_tag: str = "",
                                image_path: Optional[str] = None) -> str:
        """
        仅为错题生成标准解析 (不生成变式题)
        用于导出试卷时为无解析的错题补全解析
        :return: 标准解析文本 (含 LaTeX)
        """
        content_parts: List[Dict] = []
        prompt_parts = []
        if knowledge_tag:
            prompt_parts.append(f"【知识点】\n{knowledge_tag}\n")
        if question:
            prompt_parts.append(f"【题目】\n{question}\n")
        if image_path:
            try:
                b64 = self.image_to_base64(image_path)
                mime = self.get_mime_type(image_path)
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"}
                })
            except (IOError, OSError) as e:
                print(f"[LLM] 图片读取失败: {e}")

        if not prompt_parts and not content_parts:
            raise ValueError("请提供题目文本或图片")

        content_parts.append({
            "type": "text",
            "text": "\n".join(prompt_parts) + "\n请生成标准解析，按 JSON 格式输出。",
        })

        messages = [
            {"role": "system", "content": self._inject_deep_thinking(SOLUTION_ONLY_PROMPT)},
            {"role": "user", "content": content_parts},
        ]
        resp = self._call_chat_api(messages, temperature=0.3, max_tokens=4096)
        content = self._extract_content(resp)
        parsed = self._parse_json_response(content)
        return parsed.get("standard_solution", "")


# -------------------- 工厂函数 --------------------
def create_llm_service(settings: Dict[str, Any],
                       purpose: str = "solution") -> LLMService:
    """
    根据设置创建 LLM 服务实例
    :param purpose: "ocr" 用视觉模型 (独立 OCR 接口), "solution"/"variants" 用文本模型
    """
    if purpose == "ocr":
        # OCR 接口: 优先用 OCR 专用字段; 留空则回退到解析/变式接口
        provider = (settings.get("llm_provider_ocr")
                    or settings.get("llm_provider", "custom"))
        api_key = (settings.get("api_key_ocr")
                   or settings.get("api_key", ""))
        # 注意: model_name_ocr 即使为空也不能回退到 model_name_solution,
        # 因为 OCR 必须用视觉模型; 留空时由 LLMService 在调用时校验
        model = (settings.get("model_name_ocr")
                 or settings.get("model_name_solution")
                 or settings.get("model_name", ""))
        custom_url = (settings.get("custom_api_url_ocr")
                      or settings.get("custom_api_url", ""))
        deep = settings.get("deep_thinking_ocr", False)
    else:
        # solution / variants: 用解析/变式文本模型
        provider = settings.get("llm_provider", "custom")
        api_key = settings.get("api_key", "")
        model = (settings.get("model_name_solution")
                 or settings.get("model_name", ""))
        custom_url = settings.get("custom_api_url", "")
        deep = settings.get(f"deep_thinking_{purpose}", False)
    return LLMService(
        provider=provider,
        api_key=api_key,
        model=model,
        custom_url=custom_url,
        deep_thinking=deep,
    )
