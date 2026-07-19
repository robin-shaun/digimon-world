"""
WeatherSystem - 数码世界天气
============================

数码世界有天气变化。天气每 30 tick 随机切换一次,
从五种天气中等概率选取(也可能连续同一天气)。

天气不是装饰,它改变数码兽的行为倾向 —— 通过一组行为系数(modifier)
作用在移动速度 / 社交频率 / 战斗概率 / 觅食 / 相遇半径 上:

- 晴 (SUNNY):    万里无云,火系数码兽(亚古兽)+10% 攻击力
- 多云 (OVERCAST): 阴天,无特殊影响(全 1.0)
- 小雨 (RAINY):  道路泥泞,移动 -15%
- 暴雨 (STORMY): 危险环境,移动 -50%,水系数码兽(哥玛兽)+20% 心情
- 雾 (FOGGY):    视野受限,社交 -30%,相遇半径 -50%

设计要点:
- 纯内存、纯同步、无 LLM 依赖(scheduler / 行为层高频查询)。
- 天气切换有随机性,每 30 tick 判断一次切换。
- modifier 默认 1.0(无影响),只有对应天气的那些维度被调整。
- 提供 per-species 效果(水系数码兽在暴雨下受益等)。

典型用法:

    weather = WeatherSystem()
    weather.update(tick_count=30)       # 可能切换天气
    weather.modifier("movement")       # 当前天气的移动系数
    weather.species_modifier("gomamon", "mood")  # 水系数码兽的心情系数
    weather.encounter_radius           # 当前天气的相遇半径系数
    weather.current                    # -> Weather.RAINY (举例)
"""

from __future__ import annotations

import random
from enum import Enum
from typing import Any

# 每多少 tick 尝试切换一次天气 (Phase 10: 30 tick 比原来的每天更频繁)
WEATHER_CHANGE_INTERVAL_TICKS: int = 30

# 切换天气的概率(每 WEATHER_CHANGE_INTERVAL_TICKS 掷一次骰子)
WEATHER_CHANGE_CHANCE: float = 0.35

# 行为维度(modifier 的键):移动 / 社交 / 战斗 / 觅食
BEHAVIOR_KEYS: tuple[str, ...] = ("movement", "social", "battle", "foraging")

# 水系数码兽物种(暴雨下心情加成)
WATER_SPECIES: frozenset[str] = frozenset({"gomamon"})

# 火系数码兽物种(晴天下攻击力加成)
FIRE_SPECIES: frozenset[str] = frozenset({"agumon"})


class Weather(Enum):
    """天气类型。value 用于序列化 / 前端显示。"""

    SUNNY = "sunny"
    OVERCAST = "overcast"
    RAINY = "rainy"
    STORMY = "stormy"
    FOGGY = "foggy"


# 每种天气的行为系数。未列出的维度默认 1.0(中性,无影响)。
_WEATHER_MODIFIERS: dict[Weather, dict[str, float]] = {
    Weather.SUNNY: {"battle": 1.05},                     # 晴天战斗略增
    Weather.OVERCAST: {},                                 # 多云无影响
    Weather.RAINY: {"movement": 0.85},                    # 小雨移动 -15%
    Weather.STORMY: {"movement": 0.50, "social": 0.70},   # 暴雨移动 -50%,社交 -30%
    Weather.FOGGY: {"social": 0.70, "movement": 0.90},    # 雾社交 -30%,移动 -10%
}

# 天气显示名(前端 / 日志用)
WEATHER_LABELS: dict[Weather, str] = {
    Weather.SUNNY: "晴",
    Weather.OVERCAST: "多云",
    Weather.RAINY: "小雨",
    Weather.STORMY: "暴雨",
    Weather.FOGGY: "雾",
}

# 天气图标(前端显示用)
WEATHER_ICONS: dict[Weather, str] = {
    Weather.SUNNY: "\u2600\ufe0f",     # ☀️
    Weather.OVERCAST: "\u26c5",        # ⛅
    Weather.RAINY: "\U0001f327\ufe0f", # 🌧️
    Weather.STORMY: "\u26c8\ufe0f",    # ⛈️
    Weather.FOGGY: "\U0001f32b\ufe0f", # 🌫️
}

# 天气对应的相遇半径系数(默认 1.0)
_ENCOUNTER_RADIUS_MODIFIERS: dict[Weather, float] = {
    Weather.FOGGY: 0.50,   # 雾中相遇半径 -50%
}

# 所有天气(用于随机选取)
_ALL_WEATHERS: list[Weather] = list(Weather)


class WeatherSystem:
    """天气系统: 每 WEATHER_CHANGE_INTERVAL_TICKS 随机切换天气,并给出当前行为系数。

    Attributes:
        current: 当前天气
        last_change_tick: 上次切换时的 tick 序号
    """

    def __init__(
        self,
        start_weather: Weather = Weather.SUNNY,
        start_tick: int = 0,
        seed: int | None = None,
    ) -> None:
        self.last_change_tick: int = max(0, start_tick)
        self.current: Weather = start_weather
        self._rng = random.Random(seed)

    # ---- 推进 ----
    def update(self, tick_count: int, rng: random.Random | None = None) -> bool:
        """推进到指定 tick,可能切换天气。返回是否切换了天气。

        scheduler 每 tick 调一次。只在 tick_count 跨过
        WEATHER_CHANGE_INTERVAL_TICKS 整数倍时判定。
        """
        tick_count = max(0, tick_count)
        if tick_count <= 0:
            return False

        # 只在检测点判定
        if tick_count % WEATHER_CHANGE_INTERVAL_TICKS != 0:
            return False

        # 同一次检测点不重复判定
        if tick_count <= self.last_change_tick:
            return False

        self.last_change_tick = tick_count

        r = rng if rng is not None else self._rng
        if r.random() >= WEATHER_CHANGE_CHANCE:
            return False  # 未命中,保持当前天气

        # 随机选取新天气(可能与当前相同)
        old = self.current
        self.current = r.choice(_ALL_WEATHERS)
        return self.current != old

    # ---- 查询通用系数 ----
    def modifier(self, key: str) -> float:
        """当前天气在某行为维度上的系数。未受影响的维度返回 1.0。"""
        return _WEATHER_MODIFIERS.get(self.current, {}).get(key, 1.0)

    def modifiers(self) -> dict[str, float]:
        """当前天气的完整系数表(四个维度都补齐,缺省 1.0)。"""
        weather_mod = _WEATHER_MODIFIERS.get(self.current, {})
        return {k: weather_mod.get(k, 1.0) for k in BEHAVIOR_KEYS}

    # ---- 相遇半径系数 ----
    @property
    def encounter_radius(self) -> float:
        """当前天气的相遇半径系数(0.0-1.0)。雾天相遇半径减半。"""
        return _ENCOUNTER_RADIUS_MODIFIERS.get(self.current, 1.0)

    # ---- 按物种的个体系数 ----
    def species_modifier(self, species: str, key: str) -> float:
        """给定物种在当前天气的某行为维度系数。

        水系数码兽(如哥玛兽): 暴雨下心情 +20%(返回 1.20)
        火系数码兽(如亚古兽): 晴天下攻击力 +10%(返回 1.10)
        """
        species_lower = species.lower()

        if key == "mood" and self.current is Weather.STORMY and species_lower in WATER_SPECIES:
            return 1.20  # 水系数码兽在暴雨中更开心

        if key == "battle" and self.current is Weather.SUNNY and species_lower in FIRE_SPECIES:
            return 1.10  # 火系数码兽晴天攻击加成

        # 默认走通用系数
        return self.modifier(key)

    # ---- 属性查询 ----
    @property
    def label(self) -> str:
        """当前天气显示名(晴/多云/小雨/暴雨/雾)。"""
        return WEATHER_LABELS[self.current]

    @property
    def icon(self) -> str:
        """当前天气图标。"""
        return WEATHER_ICONS[self.current]

    # ---- 序列化 ----
    def to_dict(self) -> dict[str, Any]:
        return {
            "weather": self.current.value,
            "label": self.label,
            "icon": self.icon,
            "modifiers": self.modifiers(),
            "encounter_radius": self.encounter_radius,
            "last_change_tick": self.last_change_tick,
            "change_interval_ticks": WEATHER_CHANGE_INTERVAL_TICKS,
        }


# ---- 进程级单例 ----
_weather_system: WeatherSystem | None = None


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
