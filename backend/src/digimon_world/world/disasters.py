"""
DisasterSystem - 数码世界随机灾难
==================================

数码世界并不总是风平浪静。每隔 CHECK_INTERVAL_TICKS 个 tick,世界会掷一次骰子:
以 DISASTER_CHANCE 的概率降下一场随机灾难。灾难不是装饰,它给整个世界施加一段
时间的压力 —— 数码兽寸步难行、掉血、甚至连彼此的羁绊都被抹去。

三种灾难(等概率随机选取):

- 暴风雪 (BLIZZARD):     漫天风雪封路,移动 -50%(持续期内一直生效)。
- 地震 (EARTHQUAKE):     大地撕裂,点火当下全员 HP -HP_DAMAGE。
- 黑暗塔波动 (DARK_TOWER): 黑暗塔释放乱流,点火当下抹平所有社交关系(关系重置为中立)。

灾难有持续时间(DISASTER_DURATION_TICKS 个 tick)。持续期内:
- 移动系数(movement modifier)一直生效(暴风雪 0.5,其余灾难 1.0)。
- HP / 关系类的一次性伤害只在**点火当下**施加一次,不会每 tick 反复扣。
持续期满后灾难自动解除,世界恢复常态。

设计要点:
- 纯内存、纯同步、无 LLM 依赖(scheduler 每 tick 廉价调用一次 process())。
- 随机性(是否触发 / 触发哪种)走可注入的 random.Random,测试可复现。
- 触发时机由 tick_count 决定:只在 tick_count 跨过 CHECK_INTERVAL_TICKS 整数倍、
  且当前没有正在进行的灾难时才判定,避免同一时刻重复点火。
- 一次性伤害(HP / 关系)需要 world_state / tracker 才施加;省略时纯推进状态机,
  便于测试与纯查询。

典型用法::

    dis = DisasterSystem()
    ev = dis.process(tick_count=500, world=world, tracker=tracker)
    # ev 非空 → 本 tick 点火了一场灾难,一次性伤害已施加
    dis.modifier("movement")   # 灾难持续期内的移动系数(暴风雪 0.5)
    dis.to_dict()              # GET /api/disaster 用
"""

from __future__ import annotations

import random
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .relationships import RelationshipTracker
    from .world_state import WorldState


# 每隔多少 tick 判定一次是否降灾
CHECK_INTERVAL_TICKS: int = 500
# 判定时降下灾难的概率
DISASTER_CHANCE: float = 0.30
# 一场灾难持续多少 tick
DISASTER_DURATION_TICKS: int = 100

# 地震一次性扣多少 HP(点火当下施加,HP 不会低于 HP_FLOOR)
HP_DAMAGE: int = 20
# 灾难扣血后 HP 的下限(不至于当场把数码兽扣没)
HP_FLOOR: int = 1

# 行为维度(modifier 的键):移动 / 社交 / 战斗 / 觅食 —— 与 weather 对齐
BEHAVIOR_KEYS: tuple[str, ...] = ("movement", "social", "battle", "foraging")


class Disaster(Enum):
    """灾难类型。value 用于序列化 / 前端显示。"""

    BLIZZARD = "blizzard"        # 暴风雪
    EARTHQUAKE = "earthquake"    # 地震
    DARK_TOWER = "dark_tower"    # 黑暗塔波动
    DARK_WAVE = "dark_wave"      # Phase 8: 黑暗波动


# 所有灾难(用于等概率随机选取)
_ALL_DISASTERS: list[Disaster] = list(Disaster)

# 灾难持续期内的行为系数。未列出的维度默认 1.0(中性,无影响)。
_DISASTER_MODIFIERS: dict[Disaster, dict[str, float]] = {
    Disaster.BLIZZARD: {"movement": 0.50},   # 移动 -50%
    Disaster.EARTHQUAKE: {},                  # 无持续系数(伤害是一次性 HP)
    Disaster.DARK_TOWER: {},                  # 无持续系数(一次性抹平关系)
    Disaster.DARK_WAVE: {"movement": 0.70, "battle": 1.30},  # Phase 8: 移速-30%, 战斗+30%
}

# 灾难显示名(前端 / 日志用)
DISASTER_LABELS: dict[Disaster, str] = {
    Disaster.BLIZZARD: "暴风雪",
    Disaster.EARTHQUAKE: "地震",
    Disaster.DARK_TOWER: "黑暗塔波动",
    Disaster.DARK_WAVE: "黑暗波动",
}

# 灾难文案(点火时写进世界事件的 description)
DISASTER_DESCRIPTIONS: dict[Disaster, str] = {
    Disaster.BLIZZARD: "暴风雪!漫天风雪封住了所有道路,数码兽举步维艰。",
    Disaster.EARTHQUAKE: "地震!大地剧烈撕裂,全员受创失血。",
    Disaster.DARK_TOWER: "黑暗塔波动!释放出的乱流冲刷记忆,数码兽间的羁绊被尽数抹去。",
    Disaster.DARK_WAVE: "黑暗波动!从黑暗龙卷山释放出的负面能量横扫大陆,所有数码兽感到生命力在流逝,同时变得格外好斗。",
}


class DisasterSystem:
    """灾难系统: 周期性掷骰降下随机灾难,施加持续 / 一次性影响。

    Attributes:
        active: 当前正在进行的灾难(无灾难时为 None)。
        started_at_tick: 当前灾难的点火 tick。
        ends_at_tick: 当前灾难解除的 tick(started_at_tick + DISASTER_DURATION_TICKS)。
        history: 历史灾难记录(每次点火追加一条,供前端 / 调试查看)。
    """

    def __init__(self, seed: int | None = None) -> None:
        self.active: Disaster | None = None
        self.started_at_tick: int | None = None
        self.ends_at_tick: int | None = None
        self.history: list[dict[str, Any]] = []
        self._rng = random.Random(seed)

    # ---- 查询系数 ----
    def modifier(self, key: str) -> float:
        """当前灾难在某行为维度上的系数。无灾难 / 未受影响的维度返回 1.0。"""
        if self.active is None:
            return 1.0
        return _DISASTER_MODIFIERS.get(self.active, {}).get(key, 1.0)

    def modifiers(self) -> dict[str, float]:
        """当前灾难的完整系数表(四个维度都补齐,缺省 1.0)。"""
        active_mod = _DISASTER_MODIFIERS.get(self.active, {}) if self.active else {}
        return {k: active_mod.get(k, 1.0) for k in BEHAVIOR_KEYS}

    @property
    def is_active(self) -> bool:
        """当前是否有灾难正在进行。"""
        return self.active is not None

    @property
    def label(self) -> str | None:
        """当前灾难显示名;无灾难返回 None。"""
        return DISASTER_LABELS[self.active] if self.active else None

    # ---- 推进 ----
    def process(
        self,
        tick_count: int,
        world: WorldState | None = None,
        tracker: RelationshipTracker | None = None,
        rng: random.Random | None = None,
    ) -> dict[str, Any] | None:
        """一次 tick 的灾难处理:先结算解除,再判定是否点火新灾难。

        流程:
        1. 若有正在进行的灾难且已到解除 tick → 解除,恢复常态。
        2. 否则,若 tick_count 跨过 CHECK_INTERVAL_TICKS 整数倍(且当前无灾难)→
           以 DISASTER_CHANCE 概率掷骰;命中则随机点火一场灾难并施加一次性伤害。

        一次性伤害(仅点火当下、且提供对应依赖时施加):
        - 地震: world 内全员 HP -= HP_DAMAGE(下限 HP_FLOOR)。
        - 黑暗塔波动: tracker 所有关系重置为中立(0)。

        Args:
            tick_count: 当前 tick 序号(由 scheduler 传入)。
            world: WorldState;提供则施加 HP 伤害并写事件到 world.events。
            tracker: RelationshipTracker;提供则在黑暗塔波动时重置关系。
            rng: 可注入随机源(测试复现);省略用实例内置 rng。

        Returns:
            本次新点火的灾难事件字典;未点火(含仅解除 / 未命中)返回 None。
        """
        # 1. 结算解除
        if self.active is not None and self.ends_at_tick is not None and tick_count >= self.ends_at_tick:
            self._clear(world, tick_count)

        # 2. 灾难进行中不再叠加新灾难
        if self.active is not None:
            return None

        # 3. 只在检测点判定(tick_count > 0 且为间隔整数倍)
        if tick_count <= 0 or tick_count % CHECK_INTERVAL_TICKS != 0:
            return None

        r = rng if rng is not None else self._rng
        if r.random() >= DISASTER_CHANCE:
            return None

        # 命中:点火一场随机灾难
        return self._fire(r.choice(_ALL_DISASTERS), tick_count, world, tracker)

    def _fire(
        self,
        disaster: Disaster,
        tick_count: int,
        world: WorldState | None,
        tracker: RelationshipTracker | None,
    ) -> dict[str, Any]:
        """点火一场灾难:设状态机 + 施加一次性伤害 + 记录事件。"""
        self.active = disaster
        self.started_at_tick = tick_count
        self.ends_at_tick = tick_count + DISASTER_DURATION_TICKS

        affected: list[str] = []
        relationships_reset = False

        # 地震: 全员一次性掉血
        if disaster is Disaster.EARTHQUAKE and world is not None:
            for agent in world.all():
                hp = getattr(agent, "hp", None)
                if hp is not None:
                    agent.hp = max(HP_FLOOR, hp - HP_DAMAGE)
                    affected.append(agent.name)

        # Phase 8: 黑暗波动 — 全体 HP -10% (按当前 max_hp 计算)
        if disaster is Disaster.DARK_WAVE and world is not None:
            for agent in world.all():
                stats = agent.stats
                dmg = max(1, int(stats.max_hp * 0.10))
                stats.hp = max(HP_FLOOR, stats.hp - dmg)
                affected.append(agent.name)

        # 黑暗塔波动: 抹平所有社交关系
        if disaster is Disaster.DARK_TOWER and tracker is not None:
            tracker.reset()
            relationships_reset = True

        payload: dict[str, Any] = {
            "type": "disaster",
            "disaster": disaster.value,
            "label": DISASTER_LABELS[disaster],
            "description": DISASTER_DESCRIPTIONS[disaster],
            "tick": tick_count,
            "ends_at_tick": self.ends_at_tick,
            "duration_ticks": DISASTER_DURATION_TICKS,
            "modifiers": self.modifiers(),
            "hp_damage": HP_DAMAGE if disaster is Disaster.EARTHQUAKE else 0,
            "affected": affected,
            "relationships_reset": relationships_reset,
            "importance": 9,
            "source": "disaster_system",
        }
        self.history.append(payload)
        if world is not None:
            world.events.append(payload)
        return payload

    def _clear(self, world: WorldState | None, tick_count: int) -> None:
        """解除当前灾难,恢复常态,并写一条解除事件。"""
        ended = self.active
        self.active = None
        self.started_at_tick = None
        self.ends_at_tick = None
        if world is not None and ended is not None:
            world.events.append({
                "type": "disaster_ended",
                "disaster": ended.value,
                "label": DISASTER_LABELS[ended],
                "description": f"{DISASTER_LABELS[ended]}平息了,数码世界恢复了平静。",
                "tick": tick_count,
                "importance": 6,
                "source": "disaster_system",
            })

    # ---- 序列化 ----
    def to_dict(self) -> dict[str, Any]:
        """灾难系统当前状态(GET /api/disaster 用)。"""
        return {
            "active": self.active is not None,
            "disaster": self.active.value if self.active else None,
            "label": self.label,
            "started_at_tick": self.started_at_tick,
            "ends_at_tick": self.ends_at_tick,
            "duration_ticks": DISASTER_DURATION_TICKS,
            "modifiers": self.modifiers(),
            "check_interval_ticks": CHECK_INTERVAL_TICKS,
            "disaster_chance": DISASTER_CHANCE,
            "hp_damage": HP_DAMAGE,
            "history": self.history,
        }


# ---- 进程级单例 ----
_disaster_system: DisasterSystem | None = None


def get_disaster_system() -> DisasterSystem:
    """获取(或延迟初始化)灾难系统单例。"""
    global _disaster_system
    if _disaster_system is None:
        _disaster_system = DisasterSystem()
    return _disaster_system


def reset_disaster_system() -> None:
    """重置灾难系统(测试用)。"""
    global _disaster_system
    _disaster_system = None


__all__ = [
    "CHECK_INTERVAL_TICKS",
    "DISASTER_CHANCE",
    "DISASTER_DURATION_TICKS",
    "HP_DAMAGE",
    "Disaster",
    "DisasterSystem",
    "get_disaster_system",
    "reset_disaster_system",
]
