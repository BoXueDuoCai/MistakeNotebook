# ============================================================
# 复习调度服务 (艾宾浩斯遗忘曲线)
# ============================================================
# 说明：
#   根据艾宾浩斯遗忘曲线的间隔天数，管理错题的复习周期
#   标准间隔：1天、2天、4天、7天、15天、30天
# ============================================================

from typing import List, Dict

from models.mistake import Mistake
from services.storage_service import MistakeStorageService


class ReviewService:
    """复习调度服务"""

    def __init__(self, intervals: List[int] = None):
        """
        :param intervals: 复习间隔天数列表，如 [1, 2, 4, 7, 15, 30]
        """
        self.intervals = intervals or [1, 2, 4, 7, 15, 30]

    # -------------------- 统计 --------------------
    def get_today_review_list(self) -> List[Mistake]:
        """获取今日待复习的错题"""
        return MistakeStorageService.get_today_review(self.intervals)

    def get_today_count(self) -> int:
        """今日待复习数量"""
        return len(self.get_today_review_list())

    def get_mastered_count(self) -> int:
        """已掌握数量"""
        return sum(1 for m in MistakeStorageService.load_all() if m.is_mastered)

    def get_total_count(self) -> int:
        """错题总数"""
        return len(MistakeStorageService.load_all())

    def get_pending_count(self) -> int:
        """待复习数量 (不含今日已复习)"""
        return sum(1 for m in MistakeStorageService.load_all()
                   if not m.is_mastered and m.next_review_date)

    def get_stats(self) -> Dict[str, int]:
        """综合统计"""
        all_mistakes = MistakeStorageService.load_all()
        today_review = [m for m in all_mistakes
                        if not m.is_mastered and m.is_due_for_review()]
        mastered = [m for m in all_mistakes if m.is_mastered]
        pending = [m for m in all_mistakes
                   if not m.is_mastered and m.next_review_date]

        # 按学科统计
        by_subject = {}
        for m in all_mistakes:
            sub = m.subject or "其他"
            by_subject[sub] = by_subject.get(sub, 0) + 1

        return {
            "total": len(all_mistakes),
            "today_review": len(today_review),
            "mastered": len(mastered),
            "pending": len(pending),
            "by_subject": by_subject,
        }

    # -------------------- 复习操作 --------------------
    def mark_mastered(self, mistake_id: str) -> Mistake:
        """标记为已掌握"""
        mistake = MistakeStorageService.get(mistake_id)
        if not mistake:
            raise ValueError(f"错题不存在: {mistake_id}")
        mistake.mark_reviewed("mastered", self.intervals,
                              note="用户标记为已掌握")
        return MistakeStorageService.update(mistake)

    def mark_continue(self, mistake_id: str) -> Mistake:
        """标记为继续复习 (进入下一阶段)"""
        mistake = MistakeStorageService.get(mistake_id)
        if not mistake:
            raise ValueError(f"错题不存在: {mistake_id}")
        mistake.mark_reviewed("continue", self.intervals,
                              note="用户选择继续复习")
        return MistakeStorageService.update(mistake)

    def mark_skipped(self, mistake_id: str) -> Mistake:
        """跳过本次复习"""
        mistake = MistakeStorageService.get(mistake_id)
        if not mistake:
            raise ValueError(f"错题不存在: {mistake_id}")
        mistake.mark_reviewed("skipped", self.intervals, note="跳过")
        return MistakeStorageService.update(mistake)

    # -------------------- 阶段信息 --------------------
    def get_stage_info(self, mistake: Mistake) -> Dict:
        """
        获取错题的复习阶段信息
        语义：
            stage=0 → 待首次复习，下次将在 intervals[0] 天后
            stage=n (n>=1) → 已完成第 n 次复习，下次将在 intervals[n] 天后
            stage>=len(intervals) → 已掌握
        """
        stage = mistake.review_stage
        total_stages = len(self.intervals)
        if mistake.is_mastered or stage >= total_stages:
            return {
                "stage": total_stages,
                "total": total_stages,
                "label": "已掌握",
                "progress": 1.0,
                "next_review": "—",
                "interval_days": 0,
            }
        # 当前阶段即将进行的复习对应的间隔天数
        next_interval = self.intervals[stage]
        if stage == 0:
            label = f"待首次复习 ({next_interval}天后)"
        else:
            label = f"第 {stage}/{total_stages} 阶段"
        progress = stage / total_stages if total_stages > 0 else 0.0
        return {
            "stage": stage,
            "total": total_stages,
            "label": label,
            "progress": progress,
            "next_review": mistake.next_review_date or "今日",
            "interval_days": next_interval,
        }
