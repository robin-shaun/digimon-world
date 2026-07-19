"""
DayNightSystem - 数码世界昼夜循环
==================================

数码世界有自己的昼夜更替。世界时间 06:00-18:00 为白天,18:00-06:00 为黑夜。

昼夜不是装饰,它改变数码兽的行为:
- 夜间所有数码兽移动速度 -30%
- 巴达兽(Patamon)和迪路兽(Tailmon)夜间更活跃: 移动速度夜间不减反增 +10%
- 夜间社交频率 -20%(大部分数码兽在休息)
- 白天火系数码兽(亚古兽)+10% 攻击力

前端通过 API 获取当前时段,Canvas 背景随昼夜变色。

设计要点:
- 纯内存、纯同步、无 LLM 依赖
- 时段由 WorldClock.elapsed_minutes 折算小时数判定
- 提供 per-digimon modifier(用于 scheduler 行为层)

典型用法:

    daynight = DayNightSystem()
    daynight.update_from_minutes(elapsed_minutes=720)  # 12:00 白天
    daynight.is_daytime     # -> True
    daynight.period_icon    # -> "☀️"
"""

from __future__ import annotations

from enum import Enum
from typing import Any

# 世界一天 = 1440 分钟
MINUTES_PER_DAY: int = 24 * 60

# 昼夜分界小时 (世界时间)
DAY_START_HOUR: int = 6   # 06:00 天亮
DAY_END_HOUR: int = 18    # 18:00 天黑


class DayPeriod(Enum):
    """昼夜时段。value 用于序列化 / 前端显示。"""

    DAY = "day"      # 白天 (06:00-18:00)
    NIGHT = "night"  # 黑夜 (18:00-06:00)


# 时段图标(前端显示用)
PERIOD_ICONS: dict[DayPeriod, str] = {
    DayPeriod.DAY: "\u2600\ufe0f",   # ☀️
    DayPeriod.NIGHT: "\U0001f319",   # 🌙
}

# 时段标签
PERIOD_LABELS: dict[DayPeriod, str] = {
    DayPeriod.DAY: "白天",
    DayPeriod.NIGHT: "黑夜",
}

# 夜间活跃的数码兽物种(夜间移动不减反增)
NIGHT_ACTIVE_SPECIES: frozenset[str] = frozenset({"patamon", "tailmon"})

# 火系数码兽(白天攻击力加成)
FIRE_SPECIES: frozenset[str] = frozenset({"agumon"})

# 行为维度
BEHAVIOR_KEYS: tuple[str, ...] = ("movement", "social", "battle", "foraging")


class DayNightSystem:
    """昼夜系统: 按世界时间判定昼/夜,并给出行为系数。

    Attributes:
        period: 当前时段(DAY / NIGHT)
        current_minutes: 最近一次 update 的世界分钟数
    """

    def __init__(self, start_minutes: int = 0) -> None:
        self.current_minutes: int = max(0, start_minutes)
        self.period: DayPeriod = self._period_for_minutes(self.current_minutes)

    # ---- 纯函数:世界分钟 → 时段 ----
    @staticmethod
    def _period_for_minutes(elapsed_minutes: int) -> DayPeriod:
        """给定世界总分钟数,返回当前时段。"""
        hours = (max(0, elapsed_minutes) // 60) % 24
        if DAY_START_HOUR <= hours < DAY_END_HOUR:
            return DayPeriod.DAY
        return DayPeriod.NIGHT

    @staticmethod
    def hours_for_minutes(elapsed_minutes: int) -> tuple[int, int]:
        """返回 (当前小时 0-23, 当前分钟 0-59)。"""
        total = max(0, elapsed_minutes)
        return (total // 60) % 24, total % 60

    # ---- 推进 ----
    def update(self, elapsed_minutes: int) -> bool:
        """推进到指定世界分钟,返回是否切换了时段。"""
        elapsed_minutes = max(0, elapsed_minutes)
        new_period = self._period_for_minutes(elapsed_minutes)
        switched = new_period != self.period
        self.period = new_period
        self.current_minutes = elapsed_minutes
        return switched

    # ---- 查询 ----
    @property
    def is_daytime(self) -> bool:
        """当前是否是白天。"""
        return self.period is DayPeriod.DAY

    @property
    def is_nighttime(self) -> bool:
        """当前是否是黑夜。"""
        return self.period is DayPeriod.NIGHT

    @property
    def icon(self) -> str:
        """当前时段图标(☀️/🌙)。"""
        return PERIOD_ICONS[self.period]

    @property
    def label(self) -> str:
        """当前时段标签(白天/黑夜)。"""
        return PERIOD_LABELS[self.period]

    @property
    def time_string(self) -> str:
        """当前世界时间字符串(HH:MM)。"""
        h, m = self.hours_for_minutes(self.current_minutes)
        return f"{h:02d}:{m:02d}"

    # ---- 通用系数(所有数码兽) ----
    def modifier(self, key: str) -> float:
        """当前时段在某行为维度上的通用系数。"""
        if self.period is DayPeriod.NIGHT:
            night_mods = {"movement": 0.70, "social": 0.80}
            return night_mods.get(key, 1.0)
        # 白天: 默认无影响
        return 1.0

    def modifiers(self) -> dict[str, float]:
        """当前时段的完整通用系数表。"""
        base = dict.fromkeys(BEHAVIOR_KEYS, 1.0)
        if self.period is DayPeriod.NIGHT:
            base["movement"] = 0.70
            base["social"] = 0.80
        return base

    # ---- 按物种的个体系数 ----
    def species_modifier(self, species: str, key: str) -> float:
        """给定物种在当前时段的某行为维度系数。

        夜间活跃物种(patamon/tailmon): 夜间移动 1.10(不减反增)
        火系物种(agumon): 白天攻击 1.10
        """
        if key == "movement" and self.period is DayPeriod.NIGHT and species.lower() in NIGHT_ACTIVE_SPECIES:
            return 1.10  # 夜间活跃,不减反增
        if key == "battle" and self.period is DayPeriod.DAY and species.lower() in FIRE_SPECIES:
            return 1.10  # 白天火系攻击力加成
        # 默认走通用系数
        return self.modifier(key)

    # ---- 序列化 ----
    def to_dict(self) -> dict[str, Any]:
        return {
            "period": self.period.value,
            "label": self.label,
            "icon": self.icon,
            "is_daytime": self.is_daytime,
            "is_nighttime": self.is_nighttime,
            "time": self.time_string,
            "world_minutes": self.current_minutes,
            "modifiers": self.modifiers(),
        }


# ---- 进程级单例 ----
_daynight_system: DayNightSystem | None = None


def get_daynight_system() -> DayNightSystem:
    """获取(或延迟初始化)昼夜系统单例。"""
    global _daynight_system
    if _daynight_system is None:
        _daynight_system = DayNightSystem()
    return _daynight_system


def reset_daynight_system() -> None:
    """重置昼夜系统(测试用)。"""
    global _daynight_system
    _daynight_system = None
