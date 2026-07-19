"""
LandmarkSystem - 数码世界地标探索
==================================

地图上的特定坐标是「地标」,拥有特殊效果。数码兽移动到地标附近
(欧氏距离 < TRIGGER_RADIUS 像素)时自动触发对应效果:

- 进化神殿   (470, 230)  EvolutionShrine  — 羁绊 +5/tick(封顶 100)
- 启程海滩   (173, 468)  BeachOfDeparture — 心情提升(mood → excited)
- 奥加兽商店 (745, 480)  OgremonShop      — 随机获得一件道具
- 创世者祭坛 (480, 120)  CreatorsAltar    — 极低概率触发 mega 进化

坐标与 WorldState 里 file_island / infinity_mountain 的 POI 对齐,
地标是这些 POI 的「行为化」封装。

设计要点:
- 纯内存、纯同步、无 LLM 依赖(scheduler 每 tick 高频调用)。
- 效果直接作用在 agent 上(stats.bond / mood / stage),便于持久化。
- 随机性(商店抽道具、祭坛究极进化)走可注入的 random.Random,测试可复现。
- process(world) 遍历所有 agent 应用效果;status(world) 给前端看地标状态。

典型用法:

    landmarks = LandmarkSystem()
    effects = landmarks.process(world)      # 每 tick 调一次,返回本 tick 触发的效果
    landmarks.status(world)                 # -> 各地标 + 附近数码兽
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from math import hypot
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..agents.digimon_agent import DigimonAgent
    from .world_state import WorldState


# ---- 触发参数 ----
# 数码兽与地标的距离小于此值(像素)才触发效果
TRIGGER_RADIUS: int = 50

# 进化神殿每 tick 提升的羁绊值(封顶 100)
BOND_PER_TICK: int = 5
BOND_CAP: int = 100

# 心情提升后的目标心情
BOOSTED_MOOD: str = "excited"

# 创世者祭坛触发究极进化的概率(极低)
MEGA_EVOLUTION_CHANCE: float = 0.005

# 奥加兽商店可随机获得的道具池
SHOP_ITEMS: tuple[str, ...] = (
    "恢复药水",
    "能量胶囊",
    "力量之种",
    "防御之种",
    "迅捷之种",
    "羁绊铃铛",
    "神秘徽章碎片",
)


class LandmarkEffect(str, Enum):
    """地标效果类型。value 用于序列化 / 前端显示。"""

    BOND_BOOST = "bond_boost"            # 羁绊提升
    MOOD_BOOST = "mood_boost"            # 心情提升
    RANDOM_ITEM = "random_item"          # 随机道具
    MEGA_EVOLUTION = "mega_evolution"    # 究极进化


@dataclass(frozen=True)
class Landmark:
    """一个地标: 特定坐标 + 特殊效果。"""

    landmark_id: str
    name: str
    x: int
    y: int
    effect: LandmarkEffect
    region_id: str
    description: str

    def distance_to(self, x: int, y: int) -> float:
        """到坐标 (x, y) 的欧氏距离。"""
        return hypot(self.x - x, self.y - y)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.landmark_id,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "effect": self.effect.value,
            "region_id": self.region_id,
            "description": self.description,
        }


# ---- 内置地标(坐标与 world_state POI 对齐) ----
DEFAULT_LANDMARKS: tuple[Landmark, ...] = (
    Landmark(
        landmark_id="evolution_shrine",
        name="进化神殿",
        x=470,
        y=230,
        effect=LandmarkEffect.BOND_BOOST,
        region_id="file_island",
        description="古老的进化神殿,靠近它能加深与训练师的羁绊。",
    ),
    Landmark(
        landmark_id="beach_of_departure",
        name="启程海滩",
        x=173,
        y=468,
        effect=LandmarkEffect.MOOD_BOOST,
        region_id="file_island",
        description="被选召的孩子们最初登陆之地,踏上沙滩令数码兽心情愉悦。",
    ),
    Landmark(
        landmark_id="ogremon_shop",
        name="奥加兽的商店",
        x=745,
        y=480,
        effect=LandmarkEffect.RANDOM_ITEM,
        region_id="file_island",
        description="奥加兽经营的杂货铺,路过的数码兽偶尔能白拿一件道具。",
    ),
    Landmark(
        landmark_id="creators_altar",
        name="创世者祭坛",
        x=480,
        y=120,
        effect=LandmarkEffect.MEGA_EVOLUTION,
        region_id="infinity_mountain",
        description="创世神栖息的祭坛,极少数被选中的数码兽会在此刻究极进化。",
    ),
)


class LandmarkSystem:
    """地标系统: 检测数码兽是否靠近地标并施加效果。

    Attributes:
        landmarks: 地标列表(默认 DEFAULT_LANDMARKS)
        granted_items: {agent_name: [道具...]} —— 商店累计发放的道具
    """

    def __init__(self, landmarks: list[Landmark] | None = None) -> None:
        self.landmarks: list[Landmark] = list(landmarks) if landmarks is not None else list(DEFAULT_LANDMARKS)
        self.granted_items: dict[str, list[str]] = {}
        self._rng = random.Random()

    # ---- 邻近检测 ----
    def nearby(self, agent: DigimonAgent) -> list[Landmark]:
        """返回该数码兽当前所在 region 内、距离 < TRIGGER_RADIUS 的地标。"""
        x, y = agent.location
        return [
            lm for lm in self.landmarks
            if lm.region_id == agent.region_id and lm.distance_to(x, y) < TRIGGER_RADIUS
        ]

    # ---- 施加效果 ----
    def apply_effects(
        self, agent: DigimonAgent, rng: random.Random | None = None
    ) -> list[dict[str, Any]]:
        """对单只数码兽应用它附近所有地标的效果,返回触发的效果事件列表。

        Args:
            agent: 目标数码兽。效果直接作用在它身上(bond / mood / stage)。
            rng: 可选随机源(测试用,保证可复现)。默认用系统内置 rng。

        Returns:
            效果事件 dict 列表。每项含 landmark / effect 及各自的细节字段。
            未产生实际变化的地标(如祭坛未中概率)不计入。
        """
        r = rng if rng is not None else self._rng
        effects: list[dict[str, Any]] = []
        for lm in self.nearby(agent):
            ev = self._apply_one(agent, lm, r)
            if ev is not None:
                effects.append(ev)
        return effects

    def _apply_one(
        self, agent: DigimonAgent, lm: Landmark, r: random.Random
    ) -> dict[str, Any] | None:
        """应用单个地标效果,返回效果事件(无实际变化时返回 None)。"""
        base = {
            "type": "landmark_effect",
            "agent": agent.name,
            "landmark": lm.landmark_id,
            "landmark_name": lm.name,
            "effect": lm.effect.value,
        }

        if lm.effect is LandmarkEffect.BOND_BOOST:
            before = agent.stats.bond
            agent.stats.bond = min(BOND_CAP, before + BOND_PER_TICK)
            gained = agent.stats.bond - before
            base["amount"] = gained
            base["bond"] = agent.stats.bond
            return base

        if lm.effect is LandmarkEffect.MOOD_BOOST:
            before = agent.mood
            agent.mood = BOOSTED_MOOD
            base["mood_from"] = before
            base["mood_to"] = agent.mood
            return base

        if lm.effect is LandmarkEffect.RANDOM_ITEM:
            item = r.choice(SHOP_ITEMS)
            self.granted_items.setdefault(agent.name, []).append(item)
            base["item"] = item
            return base

        if lm.effect is LandmarkEffect.MEGA_EVOLUTION:
            # 局部 import 避免与 agent 模块的循环依赖
            from ..agents.digimon_agent import EvolutionStage

            if agent.stage is EvolutionStage.MEGA:
                return None  # 已经是究极体,无事发生
            if r.random() >= MEGA_EVOLUTION_CHANCE:
                return None  # 未触发(极低概率)
            before = agent.stage
            agent.stage = EvolutionStage.MEGA
            base["stage_from"] = before.value
            base["stage_to"] = agent.stage.value
            return base

        return None

    # ---- 批量处理(scheduler 每 tick 调用) ----
    def process(
        self, world: WorldState, rng: random.Random | None = None
    ) -> list[dict[str, Any]]:
        """遍历世界里所有数码兽,应用地标效果,返回所有触发的效果事件。"""
        effects: list[dict[str, Any]] = []
        for agent in world.all():
            effects.extend(self.apply_effects(agent, rng=rng))
        return effects

    # ---- 序列化 / 状态查询 ----
    def status(self, world: WorldState | None = None) -> dict[str, Any]:
        """各地标状态。传入 world 时附带每个地标当前附近的数码兽名字。"""
        landmark_views: list[dict[str, Any]] = []
        for lm in self.landmarks:
            view = lm.to_dict()
            if world is not None:
                near = [
                    a.name for a in world.all()
                    if a.region_id == lm.region_id
                    and lm.distance_to(*a.location) < TRIGGER_RADIUS
                ]
                view["nearby_digimon"] = near
            landmark_views.append(view)
        return {
            "count": len(self.landmarks),
            "trigger_radius": TRIGGER_RADIUS,
            "landmarks": landmark_views,
            "granted_items": dict(self.granted_items),
        }


# ---- 进程级单例 ----
_landmark_system: LandmarkSystem | None = None


def get_landmark_system() -> LandmarkSystem:
    """获取(或延迟初始化)地标系统单例。"""
    global _landmark_system
    if _landmark_system is None:
        _landmark_system = LandmarkSystem()
    return _landmark_system


def reset_landmark_system() -> None:
    """重置地标系统(测试用)。"""
    global _landmark_system
    _landmark_system = None
