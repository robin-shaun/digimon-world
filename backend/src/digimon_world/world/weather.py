"""
WeatherSystem - 数码世界天气
============================

数码世界有天气变化。天气每 24 世界小时(= 1 世界天)随机切换一次,
从四种天气中等概率选取(也可能连续同一天气)。

天气不是装饰,它改变数码兽的行为倾向 —— 通过一组行为系数(modifier)
作用在移动速度 / 社交频率 / 战斗概率 上:

- 晴 (SUNNY):  万里无云,无特殊影响(全 1.0)
- 雨 (RAINY):  道路泥泞,移动 -20%
- 暴风 (STORMY): 危险环境,战斗 -50%
- 雾 (FOGGY):  视野受限,社交 -30%

设计要点:
- 纯内存、纯同步、无 LLM 依赖(scheduler / 行为层高频查询)。
- 天气切换有随机性(不像季节那样完全确定),但切换时机确定:
  每过一个完整世界天(24h = 1440 分钟)才判断一次。
- modifier 默认 1.0(无影响),只有对应天气的那些维度被调整。

典型用法:

    weather = WeatherSystem()
    weather.update(world_day=3)       # 推进到第 3 天,可能切换天气
    weather.modifier("movement")      # 当前天气的移动系数
    weather.current                   # -> Weather.RAINY (举例)
"""

from __future__ import annotations

import random
from enum import Enum
from typing import Any, Optional

# 一个世界天 = 多少世界分钟(与 WorldClock.elapsed_minutes 对齐)
MINUTES_PER_DAY: int = 24 * 60

# 行为维度(modifier 的键):移动 / 社交 / 战斗 / 觅食
BEHAVIOR_KEYS: tuple[str, ...] = ("movement", "social", "battle", "foraging")


class Weather(Enum):
    """天气类型。value 用于序列化 / 前端显示。"""

    SUNNY = "sunny"
    RAINY = "rainy"
    STORMY = "stormy"
    FOGGY = "foggy"


# 每种天气的行为系数。未列出的维度默认 1.0(中性,无影响)。
_WEATHER_MODIFIERS: dict[Weather, dict[str, float]] = {
    Weather.SUNNY: {},                    # 无特殊影响
    Weather.RAINY: {"movement": 0.80},    # 移动 -20%
    Weather.STORMY: {"battle": 0.50},     # 战斗 -50%
    Weather.FOGGY: {"social": 0.70},      # 社交 -30%
}

# 天气显示名(前端 / 日志用)
WEATHER_LABELS: dict[Weather, str] = {
    Weather.SUNNY: "晴",
    Weather.RAINY: "雨",
    Weather.STORMY: "暴风",
    Weather.FOGGY: "雾",
}

# 所有天气(用于随机选取)
_ALL_WEATHERS: list[Weather] = list(Weather)


class WeatherSystem:
    """天气系统: 每世界天随机切换天气,并给出当前行为系数。

    Attributes:
        current: 当前天气
        current_day: 上次 update 记录的世界天(用于判断是否跨天切换)
    """

    def __init__(self, start_weather: Weather = Weather.SUNNY, start_day: int = 0) -> None:
        self.current_day: int = max(0, start_day)
        self.current: Weather = start_weather

    # ---- 推进 ----
    def update(self, world_day: int) -> bool:
        """推进到指定世界天,如果跨天则随机切换天气。返回是否切换了天气。

        scheduler 每 tick 拿 clock 折算出的世界天调一次。
        只有 world_day > current_day 时才会触发切换(同一天内多次调用幂等)。
        """
        world_day = max(0, world_day)
        if world_day <= self.current_day:
            return False
        # 跨天了,随机选取新天气
        old = self.current
        self.current = random.choice(_ALL_WEATHERS)
        self.current_day = world_day
        return self.current != old

    def update_from_minutes(self, elapsed_minutes: int) -> bool:
        """便捷入口: 直接吃 WorldClock.elapsed_minutes 推进。"""
        world_day = max(0, elapsed_minutes) // MINUTES_PER_DAY
        return self.update(world_day)

    # ---- 查询系数 ----
    def modifier(self, key: str) -> float:
        """当前天气在某行为维度上的系数。未受影响的维度返回 1.0。"""
        return _WEATHER_MODIFIERS.get(self.current, {}).get(key, 1.0)

    def modifiers(self) -> dict[str, float]:
        """当前天气的完整系数表(四个维度都补齐,缺省 1.0)。"""
        weather_mod = _WEATHER_MODIFIERS.get(self.current, {})
        return {k: weather_mod.get(k, 1.0) for k in BEHAVIOR_KEYS}

    @property
    def label(self) -> str:
        """当前天气显示名(晴/雨/暴风/雾)。"""
        return WEATHER_LABELS[self.current]

    def to_dict(self) -> dict[str, Any]:
        return {
            "weather": self.current.value,
            "label": self.label,
            "world_day": self.current_day,
            "modifiers": self.modifiers(),
        }


# ---- 进程级单例 ----
_weather_system: Optional[WeatherSystem] = None


def get_weather_system() -> WeatherSystem:
    """获取(或延迟初始化)天气系统单例。"""
    global _weather_system
    if _weather_system is None:
        _weather_system = WeatherSystem()
    return _weather_system


def reset_weather_system() -> None:
    """重置天气系统(测试用)。"""
    global _weather_system
    _weather_system = None
