"""
DigimonAgent - 数码兽智能体核心循环
====================================

参考 Stanford Generative Agents (Park et al., 2023) 的 persona.py,
本类实现数码兽自主行为循环: Observe → Memory → Reflect → Plan → Act

设计要点:
- 循环在 WorldClock 驱动下周期性执行(不是自己 sleep)
- 每个 agent 独立,有自己的 LLM 客户端引用(分模型: opus 反思, haiku 移动)
- 状态可序列化,跨进程持久化

详细设计: docs/DESIGN.md 第 3 节
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional, TYPE_CHECKING

from ..memory.memory_stream import MemoryStream

if TYPE_CHECKING:
    from .reflector import Reflector


class EvolutionStage(str, Enum):
    """数码兽的进化阶段。"""

    BABY_I = "baby_i"          # 幼年期 I
    BABY_II = "baby_ii"        # 幼年期 II / 成长期
    ROOKIE = "rookie"          # 成熟期
    CHAMPION = "champion"      # 完全体
    MEGA = "mega"              # 究极体


class DigimonAttribute(str, Enum):
    """数码兽的属性(克制关系)。"""

    VACCINE = "vaccine"        # 疫苗种 - 克制 virus
    DATA = "data"              # 数据种 - 克制 vaccine
    VIRUS = "virus"            # 病毒种 - 克制 data
    FREE = "free"              # 自由种 - 无克制


@dataclass
class DigimonStats:
    """数码兽的基础数值。"""

    hp: int = 100          # 生命值
    max_hp: int = 100
    ep: int = 50           # 能量(技能消耗)
    max_ep: int = 50
    attack: int = 20
    defense: int = 15
    speed: int = 15
    bond: int = 0          # 羁绊值(0-100),与训练师/被选召孩子
    # TODO(Phase 3): 战斗技能列表
    skills: list[str] = field(default_factory=list)


@dataclass
class DigimonAgent:
    """一只数码兽。

    Attributes:
        name: 数码兽名字(如"亚古兽")
        species: 物种(如"亚古兽"对应 digimon_species_id="agumon")
        stage: 当前进化阶段
        attribute: 属性(疫苗/数据/病毒/自由)
        region_id: 所在地区
        location: 所在具体地点(用坐标或地点 ID 表示)
        stats: 战斗数值
        memory: 记忆流
        current_plan: 当前计划(简短字符串,Phase 2 实现完整 Plan 树)
    """

    name: str
    species: str
    stage: EvolutionStage = EvolutionStage.ROOKIE
    attribute: DigimonAttribute = DigimonAttribute.VACCINE
    region_id: str = "file_island"
    location: tuple[int, int] = (0, 0)
    stats: DigimonStats = field(default_factory=DigimonStats)
    memory: MemoryStream = field(default_factory=MemoryStream)
    current_plan: Optional[str] = None
    reflector: Optional["Reflector"] = field(default=None, repr=False)
    last_reflection_at: Optional[datetime] = None
    # TODO(Phase 3): evolution_requirements - 进化前置条件

    def observe(self, event: dict[str, Any]) -> None:
        """观察一个世界事件,写入记忆流。

        重要程度评分: TODO(Phase 2) 接入 LLM 评估,先用启发式。
        """
        importance = self._heuristic_importance(event)
        self.memory.add(event=event, importance=importance)

    def _heuristic_importance(self, event: dict[str, Any]) -> int:
        """启发式重要性评分(1-10),Phase 2 替换为 LLM。"""
        et = event.get("type", "")
        if et in {"battle_victory", "evolution", "near_death"}:
            return 9
        if et in {"first_meet", "gift_received", "threat"}:
            return 7
        if et in {"moved", "ate", "rested"}:
            return 3
        return 5

    async def reflect_if_needed(self) -> None:
        """如果记忆累积到阈值,触发反思。

        反思频率: 30 分钟世界时间内最多一次。
        需要 self.reflector 已设置,否则静默跳过。
        """
        if self.reflector is None:
            return
        if not self.memory.should_reflect():
            return
        # 30 分钟冷却
        now = datetime.utcnow()
        if self.last_reflection_at is not None:
            elapsed = (now - self.last_reflection_at).total_seconds()
            if elapsed < 30 * 60:
                return
        result = await self.reflector.reflect(self)
        if result:
            self.last_reflection_at = now

    def plan_next(self) -> str:
        """根据记忆和当前状态,生成下一个行动。Phase 2 实现。"""
        # TODO(Phase 2): 调用 LLM 生成下一段计划
        raise NotImplementedError("Phase 2 才实现")

    def act(self) -> dict[str, Any]:
        """执行当前计划的第一步,产生世界事件。Phase 2 实现。"""
        # TODO(Phase 2): 根据 plan 调用 WorldState 改写位置/发起对话/攻击
        raise NotImplementedError("Phase 2 才实现")

    def to_dict(self) -> dict[str, Any]:
        """序列化(用于持久化到 SQLite)。"""
        return {
            "name": self.name,
            "species": self.species,
            "stage": self.stage.value,
            "attribute": self.attribute.value,
            "region_id": self.region_id,
            "location": list(self.location),
            "stats": self.stats.__dict__,
            "memory": [m.to_dict() for m in self.memory.entries],
            "current_plan": self.current_plan,
        }
