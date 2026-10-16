# ============================================================
# 看门狗 + 运行日志 (排查"卡在 working"问题)
# ============================================================
# 1. debug_log(): 追加写数据事件日志到 data/app_debug.log
#    (记录 busy 状态切换、LLM 调用开始/结束/耗时/错误)
# 2. Watchdog: 通用超时看门狗 - 任务启动时 arm, 完成后 disarm;
#    若超时未 disarm, 强制执行 reset 回调并记录日志
# ============================================================

import threading
import traceback
from datetime import datetime
from pathlib import Path

from config import DATA_DIR

_LOG_FILE = Path(DATA_DIR) / "app_debug.log"
_LOCK = threading.Lock()
_MAX_LOG_BYTES = 5 * 1024 * 1024  # 超过 5MB 时截断, 防止长期运行日志无限膨胀


def _truncate_log_if_needed():
    """日志文件过大时保留末尾 500KB, 避免磁盘/内存压力"""
    try:
        if _LOG_FILE.exists() and _LOG_FILE.stat().st_size > _MAX_LOG_BYTES:
            with open(_LOG_FILE, "rb") as f:
                f.seek(-500 * 1024, 2)
                tail = f.read()
            with open(_LOG_FILE, "wb") as f:
                f.write("... (日志已截断) ...\n".encode("utf-8") + tail)
    except Exception:
        pass


def debug_log(msg: str):
    """追加运行日志 (线程安全, 失败静默不影响业务)"""
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        with _LOCK:
            _truncate_log_if_needed()
            with open(_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def dump_traceback(prefix: str = ""):
    """记录当前调用栈"""
    try:
        debug_log(f"{prefix} stack:\n{''.join(traceback.format_stack()[:-1])}")
    except Exception:
        pass


class Watchdog:
    """
    超时看门狗:
        wd = Watchdog(reset_fn, timeout=60, name="导出")
        wd.arm()       # 任务开始
        wd.disarm()    # 任务正常结束 (必须调用)
    超时后自动执行 reset_fn (幂等) 并记录日志。
    """

    def __init__(self, reset_fn, timeout: int = 60, name: str = "task"):
        self.reset_fn = reset_fn
        self.timeout = timeout
        self.name = name
        self._timer = None
        self._lock = threading.Lock()

    def arm(self):
        with self._lock:
            self.disarm_no_log()
            debug_log(f"[watchdog] arm: {self.name} ({self.timeout}s)")
            self._timer = threading.Timer(self.timeout, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def disarm(self):
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None
                debug_log(f"[watchdog] disarm: {self.name} (正常完成)")

    def disarm_no_log(self):
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _fire(self):
        debug_log(f"[watchdog] TIMEOUT! {self.name} 超过 {self.timeout}s 未完成, 强制解除 busy")
        try:
            self.reset_fn()
        except Exception:
            dump_traceback(f"[watchdog] reset 失败: {self.name}")
