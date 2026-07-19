"""
FestivalSystem - 数码世界节日
=============================

数码世界每 DAYS_PER_FESTIVAL 个"世界天"举办一次节日。节日不是装饰:它是
一次全员事件 —— 所有数码兽被"召集"到一起,当天心情大涨、彼此关系回暖。

参考 Stanford Generative Agents 里 Isabella 办派对那种"把散落的个体拉到同一
时空、催生集体记忆"的做法。这里做成一个纯规则的周期事件:世界时间跨过某个
节日日 → 自动点火 → 施加全局增益 → 写入世界事件日志。

节日类型按周期轮换(进化祭 → 丰收祭 → 星光祭 → 进化祭 ……):

- 进化祭 (EVOLUTION): 庆祝成长与蜕变。
- 丰收祭 (HARVEST):   庆祝觅食与富足。
- 星光祭 (STARLIGHT): 仰望星空,寄托羁绊。

节日效果(点火当天一次性施加):
- 全员 happiness +HAPPINESS_BOOST(封顶 100)
- 所有已存在的关系对 +RELATIONSHIP_BOOST(封顶 MAX_SCORE)

设计要点:
- 纯内存、纯同步、无 LLM 依赖(scheduler 每 tick 廉价调用一次)。
- 节日日完全由"世界天"决定 → 同一世界时间必得同一状态,可复现、好测试。
- 每个节日日只点火一次(用 _last_festival_day 去重),避免同一天重复施加增益。

典型用法:

    fest = FestivalSystem()
    fest.is_festival_day(0)              # -> True(第 0 天就是节日)
    fest.festival_for_day(30)            # -> Festival.HARVEST
    fired = fest.update(world_day=30, world_state=world, tracker=tracker)
    # fired 非空 → 本次跨入了新节日,增益已施加
"""

from __future__ import annotations

from enum import Enum
from typing import Any

# 每隔多少"世界天"办一次节日
DAYS_PER_FESTIVAL: int = 30
# 一个世界天 = 多少世界分钟(与 WorldClock.elapsed_minutes / SeasonSystem 对齐)
MINUTES_PER_DAY: int = 24 * 60

# 节日增益
HAPPINESS_BOOST: int = 20        # 全员心情 +20
RELATIONSHIP_BOOST: float = 5.0  # 所有关系对 +5


class Festival(Enum):
    """节日类型。value 用于序列化 / 前端显示。"""

    EVOLUTION = "evolution"   # 进化祭
    HARVEST = "harvest"       # 丰收祭
    STARLIGHT = "starlight"   # 星光祭


# 节日轮换顺序(索引 = 第几个节日 % 3)
FESTIVAL_CYCLE: tuple[Festival, ...] = (
    Festival.EVOLUTION,
    Festival.HARVEST,
    Festival.STARLIGHT,
)

# 节日显示名(前端 / 日志用)
FESTIVAL_LABELS: dict[Festival, str] = {
    Festival.EVOLUTION: "进化祭",
    Festival.HARVEST: "丰收祭",
    Festival.STARLIGHT: "星光祭",
}

# 节日文案(点火时写进世界事件的 description)
FESTIVAL_DESCRIPTIONS: dict[Festival, str] = {
    Festival.EVOLUTION: "进化祭!数码兽齐聚一堂,为彼此的成长喝彩,全员心情大涨。",
    Festival.HARVEST: "丰收祭!大家分享觅得的果实,欢庆富足,情谊更深。",
    Festival.STARLIGHT: "星光祭!数码兽仰望夜空,许下羁绊之愿,心与心贴得更近。",
}


class FestivalSystem:
    """节日系统: 按世界天周期性举办节日,并对全世界施加节日增益。

    Attributes:
        current_day: 上次 update 记录的世界天。
        last_festival_day: 上次点火的那个"节日日"(世界天),用于去重。
    """

    def __init__(self, start_day: int = 0) -> None:
        self.current_day: int = max(0, start_day)
        # 尚未点火过任何节日(即便 start_day 恰好落在节日日,也留待首次 update 点火)
        self.last_festival_day: int | None = None

    # ---- 纯函数:世界天 → 节日 ----
    @staticmethod
    def is_festival_day(world_day: int) -> bool:
        """给定世界天是否为节日日(每 DAYS_PER_FESTIVAL 天一次)。"""
        return max(0, world_day) % DAYS_PER_FESTIVAL == 0

    @staticmethod
    def festival_for_day(world_day: int) -> Festival:
        """给定世界天,返回对应节日(纯函数,可复现)。

        非节日日也能算 —— 返回的是"该世界天所属周期"应办的节日,
        供前端预告"下一个节日是什么"。
        """
        idx = (max(0, world_day) // DAYS_PER_FESTIVAL) % len(FESTIVAL_CYCLE)
        return FESTIVAL_CYCLE[idx]

    @staticmethod
    def day_from_minutes(elapsed_minutes: int) -> int:
        """把 WorldClock.elapsed_minutes 折算成世界天。"""
        return max(0, elapsed_minutes) // MINUTES_PER_DAY

    # ---- 推进 ----
    def update(
        self,
        world_day: int,
        world_state: Any = None,
        tracker: Any = None,
    ) -> dict[str, Any] | None:
        """推进到指定世界天;若跨入一个尚未庆祝的节日日则点火。

        点火动作(仅在提供 world_state 时施加增益):
        - 全员 happiness += HAPPINESS_BOOST(封顶 100)
        - tracker 里所有关系对 += RELATIONSHIP_BOOST(封顶 MAX_SCORE)
        - 往 world_state.events 追加一条 festival 事件

        Args:
            world_day: 目标世界天。
            world_state: WorldState;提供则施加增益并写事件。省略时纯查询。
            tracker: RelationshipTracker;提供则给所有关系对加分。

        Returns:
            本次新点火的节日事件字典;未点火返回 None。
        """
        world_day = max(0, world_day)
        self.current_day = world_day

        if not self.is_festival_day(world_day):
            return None
        # 同一个节日日只点火一次
        if self.last_festival_day == world_day:
            return None

        self.last_festival_day = world_day
        festival = self.festival_for_day(world_day)
        gathered: list[str] = []

        # 施加全员心情增益 + 记录被召集者
        if world_state is not None:
            for agent in world_state.all():
                gathered.append(agent.name)
                happiness = getattr(agent, "happiness", None)
                if happiness is not None:
                    agent.happiness = min(100, happiness + HAPPINESS_BOOST)

        # 所有关系对回暖
        if tracker is not None:
            for pair in tracker.all_pairs():
                tracker.update(pair["a"], pair["b"], RELATIONSHIP_BOOST)

        payload: dict[str, Any] = {
            "type": "festival",
            "festival": festival.value,
            "label": FESTIVAL_LABELS[festival],
            "world_day": world_day,
            "description": FESTIVAL_DESCRIPTIONS[festival],
            "happiness_boost": HAPPINESS_BOOST,
            "relationship_boost": RELATIONSHIP_BOOST,
            "gathered": gathered,
            "importance": 8,
            "source": "festival_system",
        }
        if world_state is not None:
            world_state.events.append(payload)
        return payload

    def update_from_clock(
        self,
        elapsed_minutes: int,
        world_state: Any = None,
        tracker: Any = None,
    ) -> dict[str, Any] | None:
        """便捷入口: 直接吃 WorldClock.elapsed_minutes 推进。"""
        return self.update(
            self.day_from_minutes(elapsed_minutes),
            world_state=world_state,
            tracker=tracker,
        )

    # ---- 查询 ----
    @property
    def current(self) -> Festival:
        """当前世界天所属周期的节日。"""
        return self.festival_for_day(self.current_day)

    @property
    def label(self) -> str:
        """当前节日显示名。"""
        return FESTIVAL_LABELS[self.current]

    @property
    def is_active(self) -> bool:
        """今天(current_day)是否正是节日日。"""
        return self.is_festival_day(self.current_day)

    @property
    def days_until_next(self) -> int:
        """距离下一个节日还有多少世界天(节日当天返回 0)。"""
        if self.is_active:
            return 0
        return DAYS_PER_FESTIVAL - self.current_day % DAYS_PER_FESTIVAL

    def to_dict(self) -> dict[str, Any]:
        return {
            "festival": self.current.value,
            "label": self.label,
            "world_day": self.current_day,
            "is_active": self.is_active,
            "days_until_next": self.days_until_next,
            "happiness_boost": HAPPINESS_BOOST,
            "relationship_boost": RELATIONSHIP_BOOST,
        }


# ---- 进程级单例 ----
_festival_system: FestivalSystem | None = None


def get_festival_system() -> FestivalSystem:
    """获取(或延迟初始化)节日系统单例。"""
    global _festival_system
    if _festival_system is None:
        _festival_system = FestivalSystem()
    return _festival_system


def reset_festival_system() -> None:
    """重置节日系统(测试用)。"""
    global _festival_system
    _festival_system = None
