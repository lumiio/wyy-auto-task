"""反风控：熔断器 + 行为随机化。

设计原则：
1. 任何一次请求命中风控码（460/429/-460 等）就记一次失败，连续失败到阈值立刻熔断
2. 熔断期间所有任务直接跳过，冷却结束后自动半开试探一次
3. 行为层全部加随机抖动，避免固定时间、固定间隔、固定时长被指纹识别
"""
from __future__ import annotations

import logging
import random
import time
from typing import Iterable

log = logging.getLogger("ncm.antiban")

# 这些 code 出现 = 网易云风控了，立刻熔断
# 250 = 安全验证（滑块），发动态/评论敏感操作会触发
RISK_CODES = {460, -460, 429, -429, -405, -406, 512, 250}
# 301 = cookie 失效，不是风控，但也要停
AUTH_FAIL_CODES = {301, -301}


class RiskControlError(Exception):
    """命中风控码时抛出。"""


class CircuitBreaker:
    """简单的三态熔断器：closed → open → half-open → closed/open。"""

    def __init__(self, fail_threshold: int = 5, cooldown_seconds: int = 3600):
        self.fail_threshold = fail_threshold
        self.cooldown_seconds = cooldown_seconds
        self._fail = 0
        self._open_until: float = 0.0

    @property
    def is_open(self) -> bool:
        if self._open_until == 0:
            return False
        if time.time() >= self._open_until:
            # 冷却结束，自动半开
            self._open_until = 0.0
            self._fail = 0
            log.info("熔断器冷却结束，进入半开试探")
            return False
        remaining = int(self._open_until - time.time())
        log.info("熔断器打开中，剩余 %ds，跳过本次任务", remaining)
        return True

    def record_success(self) -> None:
        self._fail = 0
        self._open_until = 0.0

    def record_failure(self, reason: str = "") -> None:
        self._fail += 1
        log.warning("记录风控失败 %d/%d: %s", self._fail, self.fail_threshold, reason)
        if self._fail >= self.fail_threshold:
            self._open_until = time.time() + self.cooldown_seconds
            log.error("熔断！冷却 %d 秒后再试。原因: %s", self.cooldown_seconds, reason)


# ---------- 行为随机化工具 ----------

def jitter(base: float, ratio: float = 0.2) -> float:
    """在 base 上下浮动 ratio 比例。"""
    return base * (1 + random.uniform(-ratio, ratio))


def rand_sleep(lo: float, hi: float) -> None:
    """随机睡 lo~hi 秒。"""
    time.sleep(random.uniform(lo, hi))


def pick_play_duration(song_duration_sec: int) -> int:
    """模拟真人听歌时长。

    网易云规则：单首必须 >60 秒才计入听歌量。所以：
    - 85% 概率正常听完：65%~100% 时长，且至少 60 秒
    - 10% 概率中途切歌：60~90 秒（仍计入数量，只是 end=interrupt）
    - 5% 概率真的快速切歌：20~40 秒（不计入数量，纯拟真）
    """
    roll = random.random()
    if roll < 0.05:
        # 真·快速切歌，不计入数量
        return random.randint(20, 40)
    if roll < 0.15:
        # 中途切歌但仍 >=60 秒
        return random.randint(60, min(90, song_duration_sec))
    # 正常听完
    d = int(song_duration_sec * random.uniform(0.65, 1.0))
    return max(60, d)


def is_countable(play_sec: int) -> bool:
    """这首播放是否计入网易云听歌量（>60 秒）。"""
    return play_sec > 60


def pick_end_type(duration: int, full_duration: int) -> str:
    """根据实际播放时长决定 end 字段。"""
    if duration < full_duration * 0.5:
        return "interrupt"
    return "playend"


def jitter_daily_target(target: int) -> int:
    """每天目标数上下浮动，比如 300 → 280~310。"""
    return int(target + random.uniform(-20, 10))


def shuffle_weighted(items: Iterable, weights: list[float] | None = None) -> list:
    """带权重洗牌。"""
    items = list(items)
    if weights is None:
        random.shuffle(items)
        return items
    return random.choices(items, weights=weights, k=len(items))
