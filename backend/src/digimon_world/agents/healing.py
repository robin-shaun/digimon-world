"""
HealingSystem - 数码兽治疗 / 自然恢复
=====================================

数码兽的 HP 恢复有三条途径,由本系统统一管理:

1. 自然回血    受伤(hp < max_hp)的数码兽每 tick 自动 +1 HP。
2. 神殿加持    靠近「进化神殿」(evolution_shrine 地标)时,回血从 +1 提升到 +5/tick。
3. 治疗道具    使用一件治疗道具立即回满 HP(手动触发,见 heal_with_item)。

与 world.items.ItemSystem 的分工:
- ItemSystem.auto_use_heal 处理「HP 危急时自动嗑固定回血量的药水」(战斗药水,+40/+80)。
- 本系统处理「持续的自然恢复」与「神殿驻扎回血」,以及「治疗道具一键回满」。
两者互补:一个是战斗续航,一个是场景/时间恢复。

设计要点:
- 纯内存、纯同步、无 LLM 依赖(scheduler 每 tick 高频调用 process)。
- 神殿坐标复用 world.landmarks 的 evolution_shrine 定义,避免坐标漂移。
- 效果直接作用在 agent.stats.hp 上,便于持久化。

典型用法::

    healing = get_healing_system()
    events = healing.process(world)              # 每 tick: 自然回血 + 神殿加持
    healing.heal_with_item("亚古兽", agent)      # 治疗道具立即回满
"""

from __future__ import annotations

from math import hypot
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..world.world_state import WorldState
    from .digimon_agent import DigimonAgent


# ---- 恢复参数 ----
# 受伤数码兽每 tick 自然恢复的 HP
REGEN_PER_TICK: int = 1

# 靠近进化神殿时每 tick 恢复的 HP(覆盖自然回血,不叠加)
SHRINE_HEAL_PER_TICK: int = 5


def _shrine() -> Any:
    """取进化神殿地标(坐标 / region / 触发半径复用 landmarks 定义)。

    局部 import 避免 agents 包与 world 包的循环依赖
    (world.landmarks 反过来 TYPE_CHECKING 依赖本包)。
    """
    from ..world.landmarks import DEFAULT_LANDMARKS

    return next(lm for lm in DEFAULT_LANDMARKS if lm.landmark_id == "evolution_shrine")


class HealingSystem:
    """治疗系统: 自然回血 + 神殿加持 + 治疗道具回满。

    无状态(不持有背包 / 累计量),所有效果直接落在 agent.stats.hp 上,
    因此进程级单例主要是为了与其它系统一致的获取方式,便于 scheduler / API 复用。
    """

    def __init__(self) -> None:
        # 缓存神殿地标,避免每 tick 遍历 DEFAULT_LANDMARKS
        self._shrine = _shrine()

    # ---- 邻近检测 ----
    def _near_shrine(self, agent: DigimonAgent) -> bool:
        """数码兽是否在进化神殿的触发半径内(同 region + 距离 < 半径)。"""
        from ..world.landmarks import TRIGGER_RADIUS

        if agent.region_id != self._shrine.region_id:
            return False
        x, y = agent.location
        return hypot(self._shrine.x - x, self._shrine.y - y) < TRIGGER_RADIUS

    # ---- 单只数码兽的自然恢复 ----
    def regenerate(self, agent: DigimonAgent) -> dict[str, Any] | None:
        """对单只受伤数码兽施加一次自然回血(神殿附近 +5,否则 +1)。

        Returns:
            回血事件 dict(满血 / 无变化时返回 None)。
        """
        before = agent.stats.hp
        if before >= agent.stats.max_hp:
            return None  # 满血,无需恢复

        near = self._near_shrine(agent)
        amount = SHRINE_HEAL_PER_TICK if near else REGEN_PER_TICK
        agent.stats.hp = min(agent.stats.max_hp, before + amount)
        healed = agent.stats.hp - before
        if healed <= 0:
            return None
        return {
            "type": "heal_regen",
            "agent": agent.name,
            "source": "evolution_shrine" if near else "natural",
            "hp_from": before,
            "hp_to": agent.stats.hp,
            "healed": healed,
        }

    # ---- 治疗道具: 立即回满 ----
    def heal_with_item(
        self, agent: DigimonAgent, item_name: str = "治疗道具"
    ) -> dict[str, Any]:
        """使用治疗道具,立即把 HP 回满。

        Args:
            agent: 目标数码兽。
            item_name: 道具名(仅用于事件展示)。

        Returns:
            使用事件 dict(即使已满血也返回,healed 可能为 0)。
        """
        before = agent.stats.hp
        agent.stats.hp = agent.stats.max_hp
        return {
            "type": "heal_item",
            "agent": agent.name,
            "item_name": item_name,
            "hp_from": before,
            "hp_to": agent.stats.hp,
            "healed": agent.stats.hp - before,
        }

    # ---- 批量处理(scheduler 每 tick 调用) ----
    def process(self, world: WorldState) -> list[dict[str, Any]]:
        """一次 tick 的治疗处理: 所有受伤数码兽自然回血(神殿附近加成)。

        Returns:
            本 tick 触发的所有回血事件(满血的不计入)。
        """
        events: list[dict[str, Any]] = []
        for agent in world.all():
            ev = self.regenerate(agent)
            if ev is not None:
                events.append(ev)
        return events


# ---- 进程级单例 ----
_healing_system: HealingSystem | None = None


def get_healing_system() -> HealingSystem:
    """获取(或延迟初始化)治疗系统单例。"""
    global _healing_system
    if _healing_system is None:
        _healing_system = HealingSystem()
    return _healing_system


def reset_healing_system() -> None:
    """重置治疗系统(测试用)。"""
    global _healing_system
    _healing_system = None


__all__ = [
    "REGEN_PER_TICK",
    "SHRINE_HEAL_PER_TICK",
    "HealingSystem",
    "get_healing_system",
    "reset_healing_system",
]
