# ============================================================
# 本地存储服务
# ============================================================
# 说明：使用 JSON 文件持久化错题库和用户设置
#       提供 CRUD 接口供上层调用
# ============================================================

import json
import threading
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

from config import MISTAKE_DB_FILE, SETTINGS_FILE, DEFAULT_SETTINGS
from models.mistake import Mistake

# 文件写入锁: 防止后台线程 (导出/AI 生成) 与 UI 线程并发写坏 JSON
_IO_LOCK = threading.RLock()


# -------------------- 设置管理 --------------------
class SettingsService:
    """用户设置管理 (使用 Flet client_storage 的 JSON 备份)"""

    @staticmethod
    def _desktop_path() -> str:
        """获取桌面路径 (Windows / macOS / Linux 通用回退)"""
        home = Path.home()
        candidates = [home / "Desktop", home / "桌面", home]
        for c in candidates:
            try:
                if c.exists():
                    return str(c)
            except Exception:
                continue
        return str(home)

    @staticmethod
    def load() -> Dict[str, Any]:
        """加载设置 (合并默认值)
        - settings.json 不存在时自动按 DEFAULT_SETTINGS 生成
        - export_path 为空时自动回退到桌面路径
        """
        settings = DEFAULT_SETTINGS.copy()
        if not SETTINGS_FILE.exists():
            # 首次启动: 自动生成 settings.json (内容 = DEFAULT_SETTINGS)
            SettingsService.save(settings)
        else:
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                if isinstance(saved, dict):
                    settings.update(saved)
            except (json.JSONDecodeError, IOError, TypeError, ValueError):
                pass
        # 空导出路径 -> 桌面 (仅在内存里回退, 不写回文件, 保持文件里是 "")
        if not (settings.get("export_path") or "").strip():
            settings["export_path"] = SettingsService._desktop_path()
        return settings

    @staticmethod
    def save(settings: Dict[str, Any]) -> None:
        """保存设置"""
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _IO_LOCK:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)

    @staticmethod
    def update(key: str, value: Any) -> Dict[str, Any]:
        """更新单个设置项"""
        settings = SettingsService.load()
        settings[key] = value
        SettingsService.save(settings)
        return settings

    @staticmethod
    def reset() -> Dict[str, Any]:
        """恢复默认设置"""
        SettingsService.save(DEFAULT_SETTINGS.copy())
        return DEFAULT_SETTINGS.copy()


# -------------------- 错题库管理 --------------------
class MistakeStorageService:
    """错题库 CRUD 服务 (JSON 文件持久化)"""

    @staticmethod
    def load_all() -> List[Mistake]:
        """加载所有错题"""
        if not MISTAKE_DB_FILE.exists():
            return []
        try:
            with open(MISTAKE_DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                return []
            return [Mistake.from_dict(item) for item in data]
        except (json.JSONDecodeError, IOError, KeyError):
            return []

    @staticmethod
    def save_all(mistakes: List[Mistake]) -> None:
        """保存所有错题"""
        MISTAKE_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = [m.to_dict() for m in mistakes]
        with _IO_LOCK:
            with open(MISTAKE_DB_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def add(mistake: Mistake) -> Mistake:
        """添加一道错题"""
        mistakes = MistakeStorageService.load_all()
        mistakes.append(mistake)
        MistakeStorageService.save_all(mistakes)
        return mistake

    @staticmethod
    def update(mistake: Mistake) -> Mistake:
        """更新一道错题"""
        mistakes = MistakeStorageService.load_all()
        for i, m in enumerate(mistakes):
            if m.id == mistake.id:
                mistakes[i] = mistake
                break
        else:
            mistakes.append(mistake)
        MistakeStorageService.save_all(mistakes)
        return mistake

    @staticmethod
    def delete(mistake_id: str) -> bool:
        """删除一道错题 (同时清理图片文件)"""
        mistakes = MistakeStorageService.load_all()
        target = None
        new_list = []
        for m in mistakes:
            if m.id == mistake_id:
                target = m
            else:
                new_list.append(m)
        if not target:
            return False
        MistakeStorageService.save_all(new_list)
        # 清理图片文件
        for img_path in [target.original_image, target.enhanced_image]:
            if img_path:
                try:
                    p = Path(img_path)
                    if p.exists():
                        p.unlink()
                except OSError as e:
                    print(f"[storage] 删除图片失败 {img_path}: {e}")
        return True

    @staticmethod
    def get(mistake_id: str) -> Optional[Mistake]:
        """按 ID 获取"""
        for m in MistakeStorageService.load_all():
            if m.id == mistake_id:
                return m
        return None

    @staticmethod
    def filter_by_subject(subject: str) -> List[Mistake]:
        """按学科筛选"""
        if not subject or subject == "全部":
            return MistakeStorageService.load_all()
        return [m for m in MistakeStorageService.load_all() if m.subject == subject]

    @staticmethod
    def get_today_review(intervals: List[int]) -> List[Mistake]:
        """获取今日待复习的错题"""
        today = datetime.now()
        result = []
        for m in MistakeStorageService.load_all():
            if m.is_mastered:
                continue
            if m.is_due_for_review(today):
                result.append(m)
        return result
