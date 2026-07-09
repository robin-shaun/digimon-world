"""
ItemSystem - 数码世界宝藏 / 道具掉落
====================================

数码兽在世界里通过战斗与探索获得道具,道具分三类:

- heal            恢复类  —— 恢复 HP(数码兽 HP<50 时会自动使用)
- buff            强化类  —— 永久提升某项数值(攻击 / 防御 / 速度)
- evolution_stone 进化石  —— 稀有,仅在「奥加兽商店」附近掉落

三条获取途径:
1. 战斗胜利 —— 有 DROP_CHANCE 概率掉落一件 heal/buff(见 roll_battle_drop)。
2. 商店拾荒 —— 靠近奥加兽商店(坐标复用 landmarks 里的 ogremon_shop)有
   STONE_DROP_CHANCE 概率捡到一枚进化石(见 process_shop_drops)。
3. (未来)地标 / 剧情奖励。

自动行为:
- auto_use_heal: 数码兽 HP < HEAL_THRESHOLD 且背包里有 heal 道具时,自动嗑一个
  回血。scheduler 每 tick 调 process() 顺带处理。

设计要点:
- 纯内存、纯同步、无 LLM 依赖(scheduler 每 tick 高频调用)。
- 随机性(掉落 / 商店)走可注入的 random.Random,测试可复现。
- 背包按 agent.name 存(与 relationships / landmarks 一致),便于持久化与查询。

典型用法::

    items = ItemSystem()
    drop = items.roll_battle_drop(winner_name, rng)  # 战斗胜利后
    items.process(world)                              # 每 tick: 商店掉落 + 自动回血
    items.inventory_of("亚古兽")                       # -> [Item, ...]
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from math import hypot
from typing import TYPE_CHECKING, Any, Optional

from .landmarks import DEFAULT_LANDMARKS, TRIGGER_RADIUS

if TYPE_CHECKING:
    from ..agents.digimon_agent import DigimonAgent
    from .world_state import WorldState


# ---- 掉落 / 使用参数 ----
# 战斗胜利掉落一件 heal/buff 道具的概率
DROP_CHANCE: float = 0.35

# 靠近奥加兽商店时捡到进化石的概率(稀有)
STONE_DROP_CHANCE: float = 0.05

# HP 低于此值(占 max_hp 的比例无关,直接比绝对 HP)时自动嗑 heal 道具
HEAL_THRESHOLD: int = 50

# 奥加兽商店坐标 / region —— 复用 landmarks 里的定义,避免坐标漂移
_OGREMON_SHOP = next(lm for lm in DEFAULT_LANDMARKS if lm.landmark_id == "ogremon_shop")


class ItemType(str, Enum):
    """道具类型。value 用于序列化 / 前端显示。"""

    HEAL = "heal"                        # 恢复类(自动使用)
    BUFF = "buff"                        # 强化类(永久加成)
    EVOLUTION_STONE = "evolution_stone"  # 进化石(稀有)


@dataclass(frozen=True)
class Item:
    """一件道具: 类型 + 效果。

    effect 是描述效果的字典,按 type 解读:
        heal            {"heal": 40}                恢复 40 HP
        buff            {"stat": "attack", "amount": 5}  攻击永久 +5
        evolution_stone {"stage_up": True}          可推进一次进化(手动 / 剧情使用)
    """

    item_id: str
    name: str
    item_type: ItemType
    effect: dict[str, Any]
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.item_id,
            "name": self.name,
            "type": self.item_type.value,
            "effect": dict(self.effect),
            "description": self.description,
        }


# ---- 道具目录 ----
HEAL_ITEMS: tuple[Item, ...] = (
    Item("small_potion", "恢复药水", ItemType.HEAL, {"heal": 40}, "恢复 40 点 HP 的常见药水。"),
    Item("large_potion", "大型恢复药水", ItemType.HEAL, {"heal": 80}, "恢复 80 点 HP 的高级药水。"),
)

BUFF_ITEMS: tuple[Item, ...] = (
    Item("power_seed", "力量之种", ItemType.BUFF, {"stat": "attack", "amount": 5}, "永久提升攻击力 5 点。"),
    Item("guard_seed", "防御之种", ItemType.BUFF, {"stat": "defense", "amount": 5}, "永久提升防御力 5 点。"),
    Item("swift_seed", "迅捷之种", ItemType.BUFF, {"stat": "speed", "amount": 5}, "永久提升速度 5 点。"),
)

EVOLUTION_STONE: Item = Item(
    "evolution_stone",
    "进化石",
    ItemType.EVOLUTION_STONE,
    {"stage_up": True},
    "蕴含数码原力的神秘结晶,能推动数码兽进化。仅在奥加兽商店附近出现。",
)

# 战斗胜利可掉落的道具池(不含稀有的进化石)
BATTLE_DROP_POOL: tuple[Item, ...] = HEAL_ITEMS + BUFF_ITEMS

# id -> Item 索引(查目录用)
CATALOG: dict[str, Item] = {
    it.item_id: it for it in (*HEAL_ITEMS, *BUFF_ITEMS, EVOLUTION_STONE)
}


class ItemSystem:
    """道具系统: 战斗掉落 / 商店进化石 / 背包管理 / 自动回血。

    Attributes:
        inventory: {agent_name: [Item, ...]} —— 每只数码兽的背包
    """

    def __init__(self) -> None:
        self.inventory: dict[str, list[Item]] = {}
        self._rng = random.Random()

    # ---- 背包 ----
    def grant(self, agent_name: str, item: Item) -> None:
        """给某只数码兽的背包加一件道具。"""
        self.inventory.setdefault(agent_name, []).append(item)

    def inventory_of(self, agent_name: str) -> list[Item]:
        """返回某只数码兽的背包(副本,防外部改动)。"""
        return list(self.inventory.get(agent_name, []))

    # ---- 战斗掉落 ----
    def roll_battle_drop(
        self, winner_name: str, rng: Optional[random.Random] = None
    ) -> Optional[Item]:
        """战斗胜利后掷一次掉落: DROP_CHANCE 概率掉一件 heal/buff。

        Args:
            winner_name: 赢家名字,掉落直接进它的背包。
            rng: 可选随机源(测试用,保证可复现)。默认用系统内置 rng。

        Returns:
            掉落的 Item(未中概率则返回 None)。
        """
        r = rng if rng is not None else self._rng
        if r.random() >= DROP_CHANCE:
            return None
        item = r.choice(BATTLE_DROP_POOL)
        self.grant(winner_name, item)
        return item

    # ---- 商店进化石掉落 ----
    def process_shop_drops(
        self, world: "WorldState", rng: Optional[random.Random] = None
    ) -> list[dict[str, Any]]:
        """遍历世界: 靠近奥加兽商店的数码兽有概率捡到进化石。

        Returns:
            掉落事件 dict 列表(未掉落的不计入)。
        """
        r = rng if rng is not None else self._rng
        events: list[dict[str, Any]] = []
        for agent in world.all():
            if not self._near_shop(agent):
                continue
            if r.random() >= STONE_DROP_CHANCE:
                continue
            self.grant(agent.name, EVOLUTION_STONE)
            events.append({
                "type": "item_drop",
                "agent": agent.name,
                "item": EVOLUTION_STONE.item_id,
                "item_name": EVOLUTION_STONE.name,
                "item_type": EVOLUTION_STONE.item_type.value,
                "source": "ogremon_shop",
            })
        return events

    @staticmethod
    def _near_shop(agent: "DigimonAgent") -> bool:
        """数码兽是否在奥加兽商店的触发半径内(同 region + 距离 < 半径)。"""
        if agent.region_id != _OGREMON_SHOP.region_id:
            return False
        x, y = agent.location
        return hypot(_OGREMON_SHOP.x - x, _OGREMON_SHOP.y - y) < TRIGGER_RADIUS

    # ---- 自动使用 heal ----
    def auto_use_heal(self, agent: "DigimonAgent") -> Optional[dict[str, Any]]:
        """数码兽 HP < HEAL_THRESHOLD 且背包有 heal 道具时,自动嗑一个回血。

        每次调用最多用一个 heal 道具(回血后即使仍低于阈值,也等下一 tick)。

        Returns:
            使用事件 dict(未用则返回 None)。
        """
        if agent.stats.hp >= HEAL_THRESHOLD:
            return None
        bag = self.inventory.get(agent.name)
        if not bag:
            return None
        # 找第一个 heal 道具
        for i, item in enumerate(bag):
            if item.item_type is ItemType.HEAL:
                bag.pop(i)
                before = agent.stats.hp
                heal_amount = int(item.effect.get("heal", 0))
                agent.stats.hp = min(agent.stats.max_hp, before + heal_amount)
                return {
                    "type": "item_used",
                    "agent": agent.name,
                    "item": item.item_id,
                    "item_name": item.name,
                    "hp_from": before,
                    "hp_to": agent.stats.hp,
                    "healed": agent.stats.hp - before,
                }
        return None

    # ---- 批量处理(scheduler 每 tick 调用) ----
    def process(
        self, world: "WorldState", rng: Optional[random.Random] = None
    ) -> list[dict[str, Any]]:
        """一次 tick 的道具处理: 商店进化石掉落 + 所有数码兽自动回血。

        Returns:
            本 tick 触发的所有道具事件(掉落 + 使用)。
        """
        events = self.process_shop_drops(world, rng=rng)
        for agent in world.all():
            ev = self.auto_use_heal(agent)
            if ev is not None:
                events.append(ev)
        return events

    # ---- 序列化 / 状态查询 ----
    def status_of(self, agent_name: str) -> dict[str, Any]:
        """某只数码兽的背包视图(前端 GET /api/digimon/{name}/items 用)。"""
        bag = self.inventory.get(agent_name, [])
        return {
            "name": agent_name,
            "count": len(bag),
            "items": [it.to_dict() for it in bag],
        }


# ---- 进程级单例 ----
_item_system: Optional[ItemSystem] = None


def get_item_system() -> ItemSystem:
    """获取(或延迟初始化)道具系统单例。"""
    global _item_system
    if _item_system is None:
        _item_system = ItemSystem()
    return _item_system


def reset_item_system() -> None:
    """重置道具系统(测试用)。"""
    global _item_system
    _item_system = None


__all__ = [
    "BATTLE_DROP_POOL",
    "BUFF_ITEMS",
    "CATALOG",
    "DROP_CHANCE",
    "EVOLUTION_STONE",
    "HEAL_ITEMS",
    "HEAL_THRESHOLD",
    "STONE_DROP_CHANCE",
    "Item",
    "ItemSystem",
    "ItemType",
    "get_item_system",
    "reset_item_system",
]
