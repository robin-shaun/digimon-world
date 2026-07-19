"""
EnvironmentalEventSystem - 环境事件触发
======================================

环境不仅缓慢变化,还会突发剧烈事件:

1. 暴风雨 (STORM) — 地标"启程海滩"被淹没,数码兽躲进山洞
2. 长期干旱 (DROUGHT) — food_level < 10 持续 50 tick → 数码兽迁移到其他区域
3. 火山喷发 (VOLCANO) — 无限山周边数码兽 HP -20%, 但进化概率翻倍

事件触发时机:
- 暴风雨: 暴雨天气持续期间,每 20 tick 有 5% 概率触发
- 干旱迁移: ecology 检测到干旱时触发
- 火山: 无限山区域,每 500 tick 有 3% 概率触发

设计要点:
- 纯内存、纯同步、无 LLM 依赖
- 事件施加后写 world.events,让数码兽 observe
- 可通过 rng 控制随机性(测试友好)

典型用法:

    env_events = EnvironmentalEventSystem()
    ev = env_events.process(world, ecology, weather, tick_count=500)
    if ev: world.events.append(ev)
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .ecology import EcologySystem
    from .weather import WeatherSystem
    from .world_state import WorldState


# 暴风雨触发概率(暴雨期间每 20 tick)
STORM_CHANCE: float = 0.05
STORM_CHECK_INTERVAL: int = 20

# 干旱迁移阈值
DROUGHT_FOOD_THRESHOLD: int = 10
DROUGHT_TICK_THRESHOLD: int = 50

# 火山喷发概率(每 500 tick)
VOLCANO_CHANCE: float = 0.03
VOLCANO_CHECK_INTERVAL: int = 500
VOLCANO_HP_DAMAGE_PCT: float = 0.20  # HP -20%
VOLCANO_EVOLUTION_MULT: float = 2.0   # 进化概率翻倍


# 可迁移的目标区域(按优先级)
_MIGRATE_TARGETS: list[str] = [
    "village_of_beginnings",
    "file_island",
]


class EnvironmentalEventSystem:
    """环境事件系统: 检测条件并触发暴风雨/干旱/火山等事件。

    Attributes:
        volcano_cooldown: 火山冷却 tick(触发后 N tick 内不再触发)
    """

    def __init__(self, seed: int | None = None) -> None:
        self.volcano_cooldown: int = 0
        self._rng = random.Random(seed)

    def process(
        self,
        world: WorldState,
        ecology: EcologySystem,
        weather: WeatherSystem,
        tick_count: int,
        rng: random.Random | None = None,
    ) -> list[dict[str, Any]]:
        """每 tick 检测环境事件条件,返回触发的事件列表。

        Args:
            world: 世界状态
            ecology: 生态系统
            weather: 天气系统
            tick_count: 当前 tick
            rng: 可选随机源(测试用)

        Returns:
            触发的环境事件列表
        """
        r = rng if rng is not None else self._rng
        events: list[dict[str, Any]] = []

        # ---- 暴风雨 ----
        if (
            weather.current.value == "stormy"
            and tick_count % STORM_CHECK_INTERVAL == 0
            and r.random() < STORM_CHANCE
        ):
            ev = self._trigger_storm(world, ecology, tick_count)
            if ev:
                events.append(ev)

        # ---- 干旱迁移 ----
        drought_ev = self._check_drought_migration(world, ecology, tick_count)
        if drought_ev:
            events.append(drought_ev)

        # ---- 火山喷发 ----
        if (
            tick_count % VOLCANO_CHECK_INTERVAL == 0
            and tick_count > self.volcano_cooldown
            and r.random() < VOLCANO_CHANCE
        ):
            ev = self._trigger_volcano(world, ecology, tick_count)
            if ev:
                events.append(ev)
                self.volcano_cooldown = tick_count + VOLCANO_CHECK_INTERVAL

        return events

    def _trigger_storm(
        self,
        world: WorldState,
        ecology: EcologySystem,
        tick_count: int,
    ) -> dict[str, Any] | None:
        """暴风雨: 启程海滩被淹没,数码兽躲进山洞。"""
        # 找到启程海滩子区域内的数码兽
        affected: list[str] = []
        beach_agents: list[str] = []

        for agent in world.all():
            sr = world.get_sub_region(agent)
            if sr and sr.get("id") == "beach_of_departure":
                beach_agents.append(agent.name)

        # 海滩淹没: 数码兽迁移到暗黑洞窟
        for agent in world.all():
            sr = world.get_sub_region(agent)
            if sr and sr.get("id") == "beach_of_departure":
                # 迁移到暗黑洞窟坐标
                agent.region_id = "file_island"  # 仍在文件岛
                # 移到暗黑洞窟附近
                agent.location = (120, 300)
                agent.current_plan = "暴风雨!正在暗黑洞窟躲避"
                affected.append(agent.name)
                agent.observe({
                    "type": "environment_event",
                    "description": "暴风雨来袭!启程海滩被淹没,我躲进了暗黑洞窟。",
                    "importance": 8,
                })

        if affected:
            return {
                "type": "storm_flood",
                "description": f"暴风雨!启程海滩被巨浪淹没,{', '.join(affected)}躲进了山洞。",
                "affected": affected,
                "beach_agents": beach_agents,
                "tick": tick_count,
                "importance": 9,
                "source": "environment_events",
            }
        return None

    def _check_drought_migration(
        self,
        world: WorldState,
        ecology: EcologySystem,
        tick_count: int,
    ) -> dict[str, Any] | None:
        """长期干旱: food_level < 10 持续 50 tick → 数码兽迁移。"""
        migrants: list[str] = []

        for region_id, eco in ecology.regions.items():
            if not eco.is_drought:
                continue
            if eco.food_level >= DROUGHT_FOOD_THRESHOLD:
                continue

            # 找到该区域内的数码兽
            for agent in world.all():
                if agent.region_id == region_id:
                    # 迁移到更富饶的区域
                    target = self._find_richer_region(ecology, region_id)
                    if target:
                        agent.region_id = target
                        # 移到目标区域中心
                        agent.location = (480, 300)
                        agent.current_plan = f"干旱中: 从{region_id}迁移到{target}"
                        migrants.append(agent.name)
                        agent.observe({
                            "type": "environment_event",
                            "description": f"长期干旱迫使我从{region_id}迁移到{target}寻找食物。",
                            "importance": 9,
                        })

        if migrants:
            return {
                "type": "drought_migration",
                "description": f"长期干旱!{', '.join(migrants)}被迫迁移到食物更丰富的区域。",
                "migrants": migrants,
                "tick": tick_count,
                "importance": 9,
                "source": "environment_events",
            }
        return None

    def _find_richer_region(
        self,
        ecology: EcologySystem,
        current_region: str,
    ) -> str | None:
        """找到食物更丰富的迁移目标区域。"""
        best = None
        best_food = ecology.food_level(current_region)
        for target in _MIGRATE_TARGETS:
            if target == current_region:
                continue
            food = ecology.food_level(target)
            if food > best_food:
                best_food = food
                best = target
        return best

    def _trigger_volcano(
        self,
        world: WorldState,
        ecology: EcologySystem,
        tick_count: int,
    ) -> dict[str, Any] | None:
        """火山喷发: 无限山周边数码兽 HP -20%,进化概率翻倍。"""
        affected: list[str] = []

        for agent in world.all():
            # 检查是否在无限山区域或其子区域
            if agent.region_id == "infinity_mountain":
                # HP -20%
                stats = agent.stats
                dmg = max(1, int(stats.max_hp * VOLCANO_HP_DAMAGE_PCT))
                stats.hp = max(1, stats.hp - dmg)
                affected.append(agent.name)
                agent.observe({
                    "type": "environment_event",
                    "description": "无限山火山喷发!我被岩浆灼伤,但也感受到强大的进化能量...",
                    "importance": 9,
                })

        if affected:
            return {
                "type": "volcano_eruption",
                "description": f"无限山火山喷发!{', '.join(affected)}受到岩浆灼伤(HP -{int(VOLCANO_HP_DAMAGE_PCT * 100)}%),但进化能量涌动!",
                "affected": affected,
                "hp_damage_pct": VOLCANO_HP_DAMAGE_PCT,
                "evolution_mult": VOLCANO_EVOLUTION_MULT,
                "tick": tick_count,
                "importance": 10,
                "source": "environment_events",
            }
        return None


# ---- 进程级单例 ----
_env_events_system: EnvironmentalEventSystem | None = None


def get_env_events_system() -> EnvironmentalEventSystem:
    """获取(或延迟初始化)环境事件系统单例。"""
    global _env_events_system
    if _env_events_system is None:
        _env_events_system = EnvironmentalEventSystem()
    return _env_events_system


def reset_env_events_system() -> None:
    """重置环境事件系统(测试用)。"""
    global _env_events_system
    _env_events_system = None
