"""
SeasonSystem - 数码世界四季
============================

数码世界也有季节流转。季节不按现实日历走,而是按"世界天"推进: 每
DAYS_PER_SEASON 个世界天自动切换到下一个季节,四季循环往复
(春 → 夏 → 秋 → 冬 → 春 ……)。

季节不是装饰,它改变数码兽的行为倾向 —— 通过一组行为系数(modifier)
作用在移动速度 / 社交频率 / 战斗概率 / 觅食倾向上:

- 春 (SPRING): 万物复苏,社交 +30%
- 夏 (SUMMER): 血气方刚,战斗 +20%
- 秋 (AUTUMN): 囤积过冬,觅食 +30%
- 冬 (WINTER): 天寒地冻,移动 -20%

设计要点:
- 纯内存、纯同步、无 LLM 依赖(scheduler / 行为层高频查询)。
- 季节完全由"世界天"决定 → 同一世界时间必得同一季节,可复现、好测试。
- modifier 默认 1.0(无影响),只有当季对应的那一项被调整,其余保持中性。

典型用法:

    season_sys = SeasonSystem()
    season_sys.season_for_day(0)      # -> Season.SPRING
    season_sys.season_for_day(95)     # -> Season.SUMMER
    season_sys.update(world_day=200)  # 推进到某天,返回是否切换了季节
    season_sys.modifier("social")     # 当前季节的社交系数
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

# 每个季节持续多少"世界天"
DAYS_PER_SEASON: int = 90
# 一个世界天 = 多少世界分钟(与 WorldClock.elapsed_minutes 对齐)
MINUTES_PER_DAY: int = 24 * 60

# 行为维度(modifier 的键):移动 / 社交 / 战斗 / 觅食
BEHAVIOR_KEYS: tuple[str, ...] = ("movement", "social", "battle", "foraging")


class Season(Enum):
    """四季。value 用于序列化 / 前端显示。"""

    SPRING = "spring"
    SUMMER = "summer"
    AUTUMN = "autumn"
    WINTER = "winter"


# 季节循环顺序(索引 = 世界天 // DAYS_PER_SEASON % 4)
SEASON_CYCLE: tuple[Season, ...] = (
    Season.SPRING,
    Season.SUMMER,
    Season.AUTUMN,
    Season.WINTER,
)

# 每个季节的行为系数。未列出的维度默认 1.0(中性,无影响)。
_SEASON_MODIFIERS: dict[Season, dict[str, float]] = {
    Season.SPRING: {"social": 1.30},    # 社交 +30%
    Season.SUMMER: {"battle": 1.20},    # 战斗 +20%
    Season.AUTUMN: {"foraging": 1.30},  # 觅食 +30%
    Season.WINTER: {"movement": 0.80},  # 移动 -20%
}

# 季节显示名(前端 / 日志用)
SEASON_LABELS: dict[Season, str] = {
    Season.SPRING: "春",
    Season.SUMMER: "夏",
    Season.AUTUMN: "秋",
    Season.WINTER: "冬",
}


class SeasonSystem:
    """四季系统: 按世界天推进季节,并给出当季行为系数。

    Attributes:
        current: 当前季节
        current_day: 上次 update 记录的世界天(用于判断是否跨季)
    """

    def __init__(self, start_day: int = 0) -> None:
        self.current_day: int = max(0, start_day)
        self.current: Season = self.season_for_day(self.current_day)

    # ---- 纯函数:世界天 → 季节 ----
    @staticmethod
    def season_for_day(world_day: int) -> Season:
        """给定世界天,返回对应季节(纯函数,可复现)。"""
        idx = (max(0, world_day) // DAYS_PER_SEASON) % len(SEASON_CYCLE)
        return SEASON_CYCLE[idx]

    @staticmethod
    def day_from_minutes(elapsed_minutes: int) -> int:
        """把 WorldClock.elapsed_minutes 折算成世界天。"""
        return max(0, elapsed_minutes) // MINUTES_PER_DAY

    # ---- 推进 ----
    def update(self, world_day: int) -> bool:
        """推进到指定世界天,返回本次是否切换了季节。

        scheduler 每 tick(或每隔若干 tick)拿 clock 折算出的世界天调一次。
        """
        world_day = max(0, world_day)
        new_season = self.season_for_day(world_day)
        switched = new_season != self.current
        self.current_day = world_day
        self.current = new_season
        return switched

    def update_from_clock(self, elapsed_minutes: int) -> bool:
        """便捷入口: 直接吃 WorldClock.elapsed_minutes 推进。"""
        return self.update(self.day_from_minutes(elapsed_minutes))

    # ---- 查询系数 ----
    def modifier(self, key: str) -> float:
        """当前季节在某行为维度上的系数。未受影响的维度返回 1.0。"""
        return _SEASON_MODIFIERS.get(self.current, {}).get(key, 1.0)

    def modifiers(self) -> dict[str, float]:
        """当前季节的完整系数表(四个维度都补齐,缺省 1.0)。"""
        season_mod = _SEASON_MODIFIERS.get(self.current, {})
        return {k: season_mod.get(k, 1.0) for k in BEHAVIOR_KEYS}

    @property
    def label(self) -> str:
        """当前季节显示名(春/夏/秋/冬)。"""
        return SEASON_LABELS[self.current]

    @property
    def days_until_next(self) -> int:
        """距离下次切换季节还有多少世界天。"""
        return DAYS_PER_SEASON - (self.current_day % DAYS_PER_SEASON)

    def to_dict(self) -> dict[str, Any]:
        return {
            "season": self.current.value,
            "label": self.label,
            "world_day": self.current_day,
            "days_until_next": self.days_until_next,
            "modifiers": self.modifiers(),
        }


# ---- 进程级单例 ----
_season_system: Optional[SeasonSystem] = None


def get_season_system() -> SeasonSystem:
    """获取(或延迟初始化)四季系统单例。"""
    global _season_system
    if _season_system is None:
        _season_system = SeasonSystem()
    return _season_system


def reset_season_system() -> None:
    """重置四季系统(测试用)。"""
    global _season_system
    _season_system = None
