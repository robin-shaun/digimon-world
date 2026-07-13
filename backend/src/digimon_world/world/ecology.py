"""
EcologySystem - 数码世界生态环境
================================

世界不仅是数码兽在演化,环境本身也在自主变化。每个区域有独立的生态环境:
食物资源、植被覆盖率、生态位差异。

核心机制:
- 每个区域有 food_level (0-100),自然再生 +2/tick,数码兽进食 -5/tick
- 数码兽饥饿驱动: food_level < 30 时主动寻找食物, mood 下降
- 植被覆盖率随季节变化: 春天 +5%, 夏天 +0%, 秋天 -5%, 冬天 -20%
- 火灾/干旱等灾害影响植被: -30%
- 文件岛 vs 无限山: 不同生态特征

设计要点:
- 纯内存、纯同步、无 LLM 依赖
- process(world) 遍历数码兽,应用饥饿效果
- 每 tick 自动再生食物

典型用法:

    ecology = EcologySystem()
    ecology.process(world, tick_count=100, season="spring")
    ecology.food_level("file_island")   # -> 65
    ecology.is_hungry(agent)            # -> True if agent in low-food area
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..agents.digimon_agent import DigimonAgent
    from .world_state import WorldState

# 食物自然再生速率(每 tick)
FOOD_REGEN_PER_TICK: int = 2

# 数码兽进食消耗(每 tick 在低食物区域)
FOOD_EAT_PER_TICK: int = 5

# 饥饿阈值: food_level 低于此值触发饥饿行为
HUNGER_THRESHOLD: int = 30

# 饥饿时 mood 下降值(每 tick)
HUNGER_MOOD_DECAY: float = -0.02

# 食物充足时 mood 恢复值(每 tick)
FOOD_MOOD_BOOST: float = 0.01

# 植被覆盖率基础值(百分比,0-100)
BASE_VEGETATION_PCT: int = 60


# 区域生态参数映射
_REGION_ECOLOGY: dict[str, dict[str, Any]] = {
    "file_island": {
        "name": "文件岛",
        "description": "食物丰富的热带岛屿,数码兽的天堂。食物再生快。",
        "food_regen_bonus": 3,       # +3/tick (基础 2 + 3 = 5)
        "base_food_level": 80,       # 初始食物充足
        "evolution_chance": 1.0,     # 标准进化概率
        "vegetation_base": 65,       # 植被覆盖率基础值
    },
    "infinity_mountain": {
        "name": "无限山",
        "description": "食物稀缺的圣山,数码蛋的起源地。进化概率高。",
        "food_regen_bonus": 0,       # +0/tick (基础 2 + 0 = 2)
        "base_food_level": 40,       # 初始食物稀缺
        "evolution_chance": 2.0,     # 进化概率翻倍
        "vegetation_base": 35,       # 植被覆盖率基础值
    },
    "village_of_beginnings": {
        "name": "创始村",
        "description": "数码蛋的温床,食物适中。",
        "food_regen_bonus": 2,       # +2/tick (基础 2 + 2 = 4)
        "base_food_level": 60,       # 初始食物适中
        "evolution_chance": 1.0,
        "vegetation_base": 55,
    },
}


@dataclass
class RegionEcology:
    """单个区域的生态状态。

    Attributes:
        region_id: 区域 ID
        food_level: 当前食物量 (0-100)
        vegetation: 当前植被覆盖率 (0-100)
        drought_ticks: 连续低食物 tick 数(用于干旱检测)
    """

    region_id: str
    food_level: int = 0
    vegetation: int = 0
    drought_ticks: int = 0

    def __post_init__(self) -> None:
        params = _REGION_ECOLOGY.get(self.region_id, {})
        if self.food_level <= 0:
            self.food_level = params.get("base_food_level", 50)
        if self.vegetation <= 0:
            self.vegetation = params.get("vegetation_base", BASE_VEGETATION_PCT)

    @property
    def is_starving(self) -> bool:
        """是否处于饥荒状态(food_level < HUNGER_THRESHOLD)。"""
        return self.food_level < HUNGER_THRESHOLD

    @property
    def is_drought(self) -> bool:
        """是否处于干旱状态(连续 50 tick 低食物)。"""
        return self.drought_ticks >= 50


class EcologySystem:
    """生态系统: 管理各区域食物/植被,驱动数码兽的饥饿行为。

    Attributes:
        regions: region_id -> RegionEcology
    """

    def __init__(self) -> None:
        self.regions: dict[str, RegionEcology] = {}

    def _ensure_region(self, region_id: str) -> RegionEcology:
        """确保区域生态数据存在(惰性初始化)。"""
        if region_id not in self.regions:
            self.regions[region_id] = RegionEcology(region_id=region_id)
        return self.regions[region_id]

    # ---- 食物查询 ----
    def food_level(self, region_id: str) -> int:
        """获取区域当前食物量。"""
        return self._ensure_region(region_id).food_level

    def is_hungry(self, agent: "DigimonAgent") -> bool:
        """判断数码兽是否处于饥饿区域。"""
        eco = self._ensure_region(agent.region_id)
        return eco.food_level < HUNGER_THRESHOLD

    # ---- 植被覆盖率 ----
    def vegetation_pct(self, region_id: str) -> int:
        """获取区域当前植被覆盖率(0-100)。"""
        return self._ensure_region(region_id).vegetation

    def vegetation_color(self, region_id: str) -> str:
        """根据植被覆盖率返回地图颜色(前端用)。

        绿色=富饶, 棕色=贫瘠, 中间渐变。
        """
        v = self.vegetation_pct(region_id)
        if v >= 70:
            return "#2d6a4f"  # 深绿(富饶)
        elif v >= 50:
            return "#40916c"  # 绿
        elif v >= 30:
            return "#52b788"  # 浅绿
        elif v >= 15:
            return "#8a5a19"  # 棕色(贫瘠)
        else:
            return "#6b4226"  # 深棕(荒芜)

    # ---- 进化概率调整 ----
    def evolution_multiplier(self, region_id: str) -> float:
        """获取区域进化概率倍数。"""
        params = _REGION_ECOLOGY.get(region_id, {})
        return params.get("evolution_chance", 1.0)

    # ---- 每 tick 处理 ----
    def process(
        self,
        world: "WorldState",
        tick_count: int,
        season: str = "spring",
        weather_value: str = "sunny",
    ) -> list[dict[str, Any]]:
        """每 tick 更新生态并应用饥饿效果。返回生态事件列表。

        流程:
        1. 各区域食物自然再生
        2. 植被覆盖率受季节/天气影响
        3. 数码兽在低食物区域: 消耗食物,mood 下降
        4. 检测干旱状态

        Args:
            world: 世界状态
            tick_count: 当前 tick
            season: 当前季节 ("spring"/"summer"/"autumn"/"winter")
            weather_value: 当前天气值 ("sunny"/"stormy"/"foggy" 等)

        Returns:
            生态事件列表(饥饿/干旱/丰饶等)
        """
        events: list[dict[str, Any]] = []

        # 季节对植被的影响系数
        season_mult = _season_vegetation_mult(season)
        # 天气对植被的影响系数
        weather_mult = _weather_vegetation_mult(weather_value)

        # 1. 各区域再生
        for region_id in list(world.regions.keys()):
            eco = self._ensure_region(region_id)
            params = _REGION_ECOLOGY.get(region_id, {})

            # 食物再生
            regen = FOOD_REGEN_PER_TICK + params.get("food_regen_bonus", 0)
            eco.food_level = min(100, eco.food_level + regen)

            # 植被更新(每 10 tick 更新一次,减少波动)
            if tick_count % 10 == 0:
                target_veg = params.get("vegetation_base", BASE_VEGETATION_PCT)
                # 季节调整
                target_veg = int(target_veg * season_mult)
                # 天气调整
                target_veg = int(target_veg * weather_mult)
                target_veg = max(0, min(100, target_veg))
                # 渐变(不是突变)
                if eco.vegetation < target_veg:
                    eco.vegetation = min(target_veg, eco.vegetation + 1)
                elif eco.vegetation > target_veg:
                    eco.vegetation = max(target_veg, eco.vegetation - 1)

            # 干旱检测
            if eco.food_level < HUNGER_THRESHOLD:
                eco.drought_ticks += 1
            else:
                eco.drought_ticks = 0

            # 干旱事件
            if eco.is_drought:
                events.append({
                    "type": "drought",
                    "region_id": region_id,
                    "food_level": eco.food_level,
                    "drought_ticks": eco.drought_ticks,
                    "description": f"区域 {region_id} 持续干旱!食物极度匮乏。",
                    "importance": 8,
                })

        # 2. 数码兽饥饿效果
        for agent in world.all():
            eco = self._ensure_region(agent.region_id)

            if eco.is_starving:
                # 消耗食物
                eco.food_level = max(0, eco.food_level - FOOD_EAT_PER_TICK)

                # mood 下降
                ms = agent.mood_state
                if hasattr(ms, '__setitem__'):
                    current_sadness = ms.get("sadness", 0.0)
                    ms["sadness"] = min(1.0, current_sadness - HUNGER_MOOD_DECAY)

                # 饥饿驱动: 改变当前计划
                if tick_count % 5 == 0 and "找食物" not in (agent.current_plan or ""):
                    agent.current_plan = f"饥饿中: 在{eco.region_id}寻找食物"

                events.append({
                    "type": "hunger",
                    "agent": agent.name,
                    "region_id": agent.region_id,
                    "food_level": eco.food_level,
                    "description": f"{agent.name} 因区域食物不足而感到饥饿。",
                    "importance": 5,
                })
            else:
                # 食物充足: 轻微心情恢复
                ms = agent.mood_state
                if hasattr(ms, '__setitem__'):
                    current_sadness = ms.get("sadness", 0.0)
                    ms["sadness"] = max(0.0, current_sadness - FOOD_MOOD_BOOST)

        return events

    # ---- 序列化 ----
    def to_dict(self) -> dict[str, Any]:
        return {
            "regions": {
                rid: {
                    "food_level": eco.food_level,
                    "vegetation": eco.vegetation,
                    "is_starving": eco.is_starving,
                    "is_drought": eco.is_drought,
                    "drought_ticks": eco.drought_ticks,
                }
                for rid, eco in self.regions.items()
            },
            "hunger_threshold": HUNGER_THRESHOLD,
        }


def _season_vegetation_mult(season: str) -> float:
    """季节对植被的影响系数。"""
    mults = {
        "spring": 1.05,   # 春天植被 +5%
        "summer": 1.00,   # 夏天不变
        "autumn": 0.95,   # 秋天 -5%
        "winter": 0.80,   # 冬天 -20%
    }
    return mults.get(season, 1.0)


def _weather_vegetation_mult(weather_value: str) -> float:
    """天气对植被的影响系数。"""
    mults = {
        "sunny": 1.00,      # 晴天不变
        "overcast": 1.00,   # 多云不变
        "rainy": 1.03,      # 小雨有利
        "stormy": 0.90,     # 暴雨破坏植被
        "foggy": 1.00,      # 雾不变
    }
    return mults.get(weather_value, 1.0)


# ---- 进程级单例 ----
_ecology_system: Optional[EcologySystem] = None


def get_ecology_system() -> EcologySystem:
    """获取(或延迟初始化)生态系统单例。"""
    global _ecology_system
    if _ecology_system is None:
        _ecology_system = EcologySystem()
    return _ecology_system


def reset_ecology_system() -> None:
    """重置生态系统(测试用)。"""
    global _ecology_system
    _ecology_system = None
