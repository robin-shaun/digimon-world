"""
DarkGearSystem - 黑色齿轮感染机制
===================================

数码宝贝大冒险 01 中，恶魔兽 (Devimon) 用黑色齿轮操控数码兽，
将它们变为狂暴的奴隶。本模块实现这个机制的数码世界版本：

- 黑色齿轮被投放到文件岛的某个子区域
- 齿轮持续感染同一子区域内的数码兽
- 被感染的数码兽：attribute 暂时变为 VIRUS，攻击倾向飙升
- 齿轮可被战斗摧毁（同一子区内的数码兽战斗有概率破坏齿轮）
- 齿轮数量影响世界威胁等级

这是 Phase 8 数码宝贝原作复刻的 🟡 P1 项。

设计要点：
- 纯内存、纯同步、无 LLM 依赖
- 每 N 个 tick 判定是否投放新齿轮（基于世界威胁等级）
- 齿轮放置有冷却时间，避免刷屏
- 感染是暂时的，齿轮被摧毁后数码兽恢复

典型用法::

    dgs = DarkGearSystem()
    # scheduler 每 tick 调用
    dgs.process(tick_count, world)
    # 检查某数码兽是否被感染
    dgs.is_infected(agent, sub_region_id)
    # 尝试摧毁齿轮
    dgs.try_destroy_gear(sub_region_id)
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .world_state import WorldState


# ---- 配置常量 ----

# 每隔多少 tick 判定一次是否投放新齿轮
PLACEMENT_INTERVAL_TICKS: int = 200

# 基准投放概率（会根据世界状态调整）
BASE_PLACEMENT_CHANCE: float = 0.15

# 齿轮的默认 HP（数码兽需在此子区战斗才能削减）
GEAR_DEFAULT_HP: int = 50

# 每次战斗尝试摧毁齿轮造成的伤害
GEAR_DAMAGE_PER_BATTLE: int = 20

# 齿轮最大同时存在数量
MAX_ACTIVE_GEARS: int = 5

# 投放齿轮的最小 tick 间隔（防刷屏）
PLACEMENT_COOLDOWN_TICKS: int = 300

# 被感染数码兽的攻击加成
INFECTION_ATTACK_BONUS: float = 1.3

# 被感染数码兽的防御惩罚
INFECTION_DEFENSE_PENALTY: float = 0.7


@dataclass
class DarkGear:
    """一个黑色齿轮，放置在某个子区域内。"""

    gear_id: str
    sub_region_id: str
    placed_at_tick: int
    hp: int = GEAR_DEFAULT_HP
    destroyed: bool = False

    def take_damage(self, amount: int) -> bool:
        """造成伤害，返回是否被摧毁。"""
        self.hp = max(0, self.hp - amount)
        if self.hp <= 0:
            self.destroyed = True
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "gear_id": self.gear_id,
            "sub_region_id": self.sub_region_id,
            "placed_at_tick": self.placed_at_tick,
            "hp": self.hp,
            "destroyed": self.destroyed,
        }


class DarkGearSystem:
    """黑色齿轮系统的全局管理器。

    由 scheduler 每 tick 调用 process()，负责：
    1. 判定是否投放新齿轮
    2. 清理已被摧毁的齿轮
    3. 提供感染状态查询
    """

    def __init__(self, rng: random.Random | None = None) -> None:
        self._gears: list[DarkGear] = []
        self._gear_counter: int = 0
        self._last_placement_tick: int = -PLACEMENT_COOLDOWN_TICKS
        self._rng = rng or random.Random()

    # ── 齿轮生命周期 ──────────────────────────────────────────

    def process(
        self,
        tick_count: int,
        world: "WorldState | None" = None,
    ) -> Optional[DarkGear]:
        """每 tick 主入口：清理 + 尝试投放。

        Returns:
            如果本 tick 投放了新齿轮，返回它；否则返回 None。
        """
        # 清理已摧毁的齿轮
        self._gears = [g for g in self._gears if not g.destroyed]

        # 只在 placement 间隔 tick 处判定
        if tick_count % PLACEMENT_INTERVAL_TICKS != 0:
            return None

        # 冷却检查
        if tick_count - self._last_placement_tick < PLACEMENT_COOLDOWN_TICKS:
            return None

        # 上限检查
        active_count = len([g for g in self._gears if not g.destroyed])
        if active_count >= MAX_ACTIVE_GEARS:
            return None

        # 概率判定
        chance = BASE_PLACEMENT_CHANCE
        # 已有齿轮越多，投放概率越低（边际递减）
        if active_count > 0:
            chance *= (MAX_ACTIVE_GEARS - active_count) / MAX_ACTIVE_GEARS

        if self._rng.random() > chance:
            return None

        # 选择投放目标子区域
        sub_region_id = self._pick_target_sub_region(world)

        self._gear_counter += 1
        gear = DarkGear(
            gear_id=f"dark_gear_{self._gear_counter:03d}",
            sub_region_id=sub_region_id,
            placed_at_tick=tick_count,
        )
        self._gears.append(gear)
        self._last_placement_tick = tick_count
        return gear

    def _pick_target_sub_region(
        self, world: "WorldState | None"
    ) -> str:
        """选择投放齿轮的目标子区域。

        优先选择有数码兽存在的子区域（齿轮需要有目标感染）。
        其次随机选择文件岛的 14 个子区域之一。
        """
        file_island_sub_regions = [
            "freezing_area",
            "miharashi_mountain",
            "ancient_dino_region",
            "shogungekomon_castle",
            "confusion_forest",
            "gear_savannah",
            "infinity_mountain_peak",
            "dark_cave",
            "dragon_eye_lake",
            "ogremon_fortress",
            "factory_area",
            "beach_of_departure",
            "vending_machine_area",
            "toy_town",
        ]

        if world is not None:
            # 收集有数码兽的子区域
            occupied = set()
            for agent in world.agents:
                sr = agent.get("sub_region") if isinstance(agent, dict) else getattr(agent, "sub_region", None)
                if sr:
                    sr_id = sr.get("id") if isinstance(sr, dict) else getattr(sr, "sub_region_id", None)
                    if sr_id and sr_id in file_island_sub_regions:
                        occupied.add(sr_id)

            if occupied:
                return self._rng.choice(sorted(occupied))

        # 没有世界状态或没有agent，随机选一个
        return self._rng.choice(file_island_sub_regions)

    # ── 齿轮战斗交互 ──────────────────────────────────────────

    def try_destroy_gear(
        self, sub_region_id: str, damage_multiplier: float = 1.0
    ) -> tuple[bool, str]:
        """数码兽在子区域内战斗时，尝试摧毁齿轮。

        Args:
            sub_region_id: 战斗发生的子区域
            damage_multiplier: 伤害倍率（如 MEGA 级数码兽伤害翻倍）

        Returns:
            (是否摧毁了齿轮, 消息文本)
        """
        damage = int(GEAR_DAMAGE_PER_BATTLE * damage_multiplier)

        for gear in self._gears:
            if gear.sub_region_id == sub_region_id and not gear.destroyed:
                destroyed = gear.take_damage(damage)
                if destroyed:
                    return True, (
                        f"💥 黑色齿轮 {gear.gear_id} 在 {sub_region_id} 被战斗余波摧毁！"
                        f"该区域的数码兽摆脱了感染！"
                    )
                else:
                    return False, (
                        f"⚔️ 黑色齿轮 {gear.gear_id} 受到 {damage} 点伤害 "
                        f"(剩余 HP: {gear.hp})"
                    )

        return False, "该子区域没有活动的黑色齿轮。"

    # ── 感染状态查询 ──────────────────────────────────────────

    def get_gears_in_sub_region(self, sub_region_id: str) -> list[DarkGear]:
        """获取某个子区域内的活动齿轮列表。"""
        return [
            g for g in self._gears
            if g.sub_region_id == sub_region_id and not g.destroyed
        ]

    def is_sub_region_infected(self, sub_region_id: str) -> bool:
        """检查子区域是否有活动齿轮。"""
        return len(self.get_gears_in_sub_region(sub_region_id)) > 0

    def is_agent_infected(
        self,
        agent_sub_region_id: str | None,
    ) -> bool:
        """检查数码兽是否在其子区域内被感染。

        Args:
            agent_sub_region_id: 数码兽当前所在的子区域ID
        """
        if agent_sub_region_id is None:
            return False
        return self.is_sub_region_infected(agent_sub_region_id)

    def get_infection_stats(
        self, agent_attack: int, agent_defense: int, agent_sub_region_id: str | None
    ) -> tuple[int, int, bool]:
        """计算感染对数码兽战斗属性的影响。

        Returns:
            (调整后的攻击力, 调整后的防御力, 是否被感染)
        """
        infected = self.is_agent_infected(agent_sub_region_id)
        if infected:
            boosted_attack = int(agent_attack * INFECTION_ATTACK_BONUS)
            penalized_defense = max(1, int(agent_defense * INFECTION_DEFENSE_PENALTY))
            return boosted_attack, penalized_defense, True
        return agent_attack, agent_defense, False

    # ── 全局状态查询 ──────────────────────────────────────────

    @property
    def active_gears(self) -> list[DarkGear]:
        """所有活动齿轮。"""
        return [g for g in self._gears if not g.destroyed]

    @property
    def total_gears_placed(self) -> int:
        """历史上投放过的齿轮总数。"""
        return self._gear_counter

    @property
    def threat_level(self) -> str:
        """当前世界威胁等级。

        基于活动齿轮数量：
        - 0: PEACEFUL（和平）
        - 1: CAUTIOUS（警惕）
        - 2-3: THREATENED（受威胁）
        - 4-5: CRISIS（危机）
        """
        count = len(self.active_gears)
        if count == 0:
            return "PEACEFUL"
        elif count == 1:
            return "CAUTIOUS"
        elif count <= 3:
            return "THREATENED"
        else:
            return "CRISIS"

    def to_dict(self) -> dict[str, Any]:
        """序列化为前端可用的字典。"""
        return {
            "active_gears": [g.to_dict() for g in self.active_gears],
            "total_placed": self._gear_counter,
            "threat_level": self.threat_level,
            "infected_sub_regions": list(set(
                g.sub_region_id for g in self.active_gears
            )),
        }

    def reset(self) -> None:
        """重置系统（测试用）。"""
        self._gears.clear()
        self._gear_counter = 0
        self._last_placement_tick = -PLACEMENT_COOLDOWN_TICKS

    def force_place_gear(
        self, sub_region_id: str | None = None, tick: int = 0
    ) -> DarkGear:
        """强制投放一个齿轮（测试用，绕过概率和冷却检查）。

        Args:
            sub_region_id: 目标子区域。None 时随机选。
            tick: 投放 tick。

        Returns:
            新创建的 DarkGear。
        """
        if sub_region_id is None:
            sub_region_id = self._rng.choice([
                "freezing_area", "miharashi_mountain", "ancient_dino_region",
                "shogungekomon_castle", "confusion_forest", "gear_savannah",
                "infinity_mountain_peak", "dark_cave", "dragon_eye_lake",
                "ogremon_fortress", "factory_area", "beach_of_departure",
                "vending_machine_area", "toy_town",
            ])
        self._gear_counter += 1
        gear = DarkGear(
            gear_id=f"dark_gear_{self._gear_counter:03d}",
            sub_region_id=sub_region_id,
            placed_at_tick=tick,
        )
        self._gears.append(gear)
        self._last_placement_tick = tick
        return gear


# ---- 模块级单例（与 disasters.py / economy.py 风格一致）----

_system: DarkGearSystem | None = None


def get_dark_gear_system() -> DarkGearSystem:
    """获取全局 DarkGearSystem 单例。"""
    global _system
    if _system is None:
        _system = DarkGearSystem()
    return _system


def reset_dark_gear_system() -> DarkGearSystem:
    """重置全局 DarkGearSystem（测试用）。"""
    global _system
    _system = DarkGearSystem()
    return _system
