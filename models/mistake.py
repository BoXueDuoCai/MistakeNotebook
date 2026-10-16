# ============================================================
# 错题数据模型
# ============================================================
# 说明：定义错题、变式题、复习记录等核心数据结构
#       使用 dataclass + JSON 序列化，便于本地存储
# ============================================================

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import uuid


# -------------------- 变式题模型 --------------------
@dataclass
class Variant:
    """变式题数据结构"""
    question: str = ""                    # 变式题题干 (含 $$..$$ LaTeX 公式)
    solution: str = ""                    # 变式题解析
    user_answer: str = ""                 # 用户作答
    ai_feedback: str = ""                 # AI 批改反馈
    is_correct: Optional[bool] = None     # 是否正确
    answered_at: Optional[str] = None    # 作答时间 ISO 格式

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Variant":
        """从字典反序列化"""
        return cls(
            question=d.get("question", ""),
            solution=d.get("solution", ""),
            user_answer=d.get("user_answer", ""),
            ai_feedback=d.get("ai_feedback", ""),
            is_correct=d.get("is_correct"),
            answered_at=d.get("answered_at"),
        )


# -------------------- 复习记录模型 --------------------
@dataclass
class ReviewRecord:
    """单次复习记录"""
    reviewed_at: str                      # 复习时间 ISO
    result: str                           # "mastered" / "continue" / "skipped"
    note: str = ""                        # 备注


# -------------------- 错题主模型 --------------------
@dataclass
class Mistake:
    """
    错题核心数据模型
    一个错题包含：原图、题干、错因、解析、变式题、复习历史
    """
    # 标识
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # 学科与标签
    subject: str = ""                            # 学科：数学/物理/化学/...
    knowledge_tag: str = ""                      # 知识点标签

    # 题目内容
    original_question: str = ""                  # 纯净题干 (含 LaTeX)
    image_desc: str = ""                         # 图形特征描述
    error_analysis: str = ""                     # 错因诊断
    standard_solution: str = ""                  # 标准解析
    error_thinking: str = ""                     # 当时错误思路 (用户输入)

    # 图片路径 (相对于项目根)
    original_image: str = ""                     # 原始图片路径
    enhanced_image: str = ""                    # 增强后图片路径

    # 变式题列表
    variants: List[Variant] = field(default_factory=list)

    # 复习相关
    review_history: List[Dict] = field(default_factory=list)  # 复习记录
    review_stage: int = 0                        # 当前复习阶段 (0=未开始, 1=第一次复习, ...)
    next_review_date: str = ""                   # 下次复习日期 (ISO yyyy-mm-dd)
    is_mastered: bool = False                    # 是否已掌握

    # 时间戳
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Mistake":
        """从字典反序列化"""
        # 处理 variants 列表
        variants_data = d.get("variants", [])
        variants = [Variant.from_dict(v) if isinstance(v, dict) else v
                    for v in variants_data]
        return cls(
            id=d.get("id", str(uuid.uuid4())),
            subject=d.get("subject", ""),
            knowledge_tag=d.get("knowledge_tag", ""),
            original_question=d.get("original_question", ""),
            image_desc=d.get("image_desc", ""),
            error_analysis=d.get("error_analysis", ""),
            standard_solution=d.get("standard_solution", ""),
            error_thinking=d.get("error_thinking", ""),
            original_image=d.get("original_image", ""),
            enhanced_image=d.get("enhanced_image", ""),
            variants=variants,
            review_history=d.get("review_history", []),
            review_stage=d.get("review_stage", 0),
            next_review_date=d.get("next_review_date", ""),
            is_mastered=d.get("is_mastered", False),
            created_at=d.get("created_at", datetime.now().isoformat()),
            updated_at=d.get("updated_at", datetime.now().isoformat()),
        )

    # -------------------- 复习相关方法 --------------------
    def compute_next_review_date(self, intervals: List[int]) -> str:
        """
        根据艾宾浩斯遗忘曲线间隔计算下次复习日期
        :param intervals: 间隔天数列表 [1, 2, 4, 7, 15, 30]
        :return: ISO 格式日期字符串
        """
        if not intervals:
            # 防御：若 intervals 空，默认 1 天后
            interval_days = 1
        elif self.review_stage >= len(intervals):
            # 已完成所有复习阶段，标记为掌握
            self.is_mastered = True
            return ""
        else:
            interval_days = intervals[self.review_stage]

        next_date = datetime.now() + timedelta(days=interval_days)
        return next_date.strftime("%Y-%m-%d")

    def is_due_for_review(self, today: Optional[datetime] = None) -> bool:
        """
        检查是否到了复习时间
        """
        if self.is_mastered or not self.next_review_date:
            return False

        today = today or datetime.now()
        try:
            review_date = datetime.strptime(self.next_review_date, "%Y-%m-%d")
            return today.date() >= review_date.date()
        except (ValueError, TypeError):
            return False

    def mark_reviewed(self, result: str, intervals: List[int], note: str = ""):
        """
        标记为已复习
        :param result: "mastered" / "continue" / "skipped"
        :param intervals: 艾宾浩斯间隔列表
        :param note: 备注
        """
        record = {
            "reviewed_at": datetime.now().isoformat(),
            "result": result,
            "note": note,
        }
        self.review_history.append(record)
        self.updated_at = datetime.now().isoformat()

        if result == "mastered":
            self.is_mastered = True
            self.next_review_date = ""
        elif result == "continue":
            self.review_stage += 1
            self.next_review_date = self.compute_next_review_date(intervals)
        # skipped 不改变下次复习日期

    def add_variants(self, variants_data: List[Dict]):
        """添加变式题"""
        for v in variants_data:
            self.variants.append(Variant(
                question=v.get("question", ""),
                solution=v.get("solution", ""),
            ))
        self.updated_at = datetime.now().isoformat()


# -------------------- 学科常量 --------------------
SUBJECTS = ["数学", "物理", "化学", "生物", "语文", "英语",
            "历史", "地理", "政治", "信息科技"]

# 学科对应的图标 (Material Icons)
SUBJECT_ICONS = {
    "数学": "FUNCTIONS",
    "物理": "SCIENCE",
    "化学": "BIOTECH",
    "生物": "ECO",
    "语文": "MENU_BOOK",
    "英语": "TRANSLATE",
    "历史": "HISTORY_EDU",
    "地理": "PUBLIC",
    "政治": "ACCOUNT_BALANCE",
    "信息科技": "COMPUTER",
}
