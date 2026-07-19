"""
需求系统 (Needs System) — 饥饿 & 食物链
=======================================

参考 Stanford Generative Agents 的 "生理需求驱动行为": 数码兽不只是漫无目的
地闲逛,饥饿会压过其它意图,把觅食提到计划的最前面。

模型 (Phase 5):
- 每只数码兽维护一个 hunger 值 (0-100),越低越饿。
- 世界每 tick 掉 1 点 (HUNGER_DECAY_PER_TICK)。
- hunger < HUNGRY_THRESHOLD (20) 时,计划应优先觅食 (should_forage=True)。
- 食物来源按地区配置: 文件岛有 berries / fish / meat。
- 觅食成功 hunger += FORAGE_RESTORE (30),夹紧到 100。

设计要点:
- NeedsState 与 DigimonAgent 解耦: agent 只多持有一个 needs 字段,
  觅食/衰减逻辑集中在本模块,方便单测与后续扩展 (口渴/疲劳…)。
- 觅食是否成功依赖地区是否有食物,不依赖 LLM,保证确定性。

详细设计: docs/DESIGN.md 第 6 节 "需求与食物链"。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

# ----------------------------------------------------------------------------
# 常量
# ----------------------------------------------------------------------------

HUNGER_MAX: int = 100
HUNGER_MIN: int = 0
HUNGER_DECAY_PER_TICK: int = 1     # 每 tick 饥饿加深
HUNGRY_THRESHOLD: int = 20         # 低于此值触发优先觅食
FORAGE_RESTORE: int = 30           # 觅食成功恢复的饥饿值


# ----------------------------------------------------------------------------
# 食物类型 & 地区食物来源
# ----------------------------------------------------------------------------

class FoodType(StrEnum):
    """食物类型 (数码世界的食物链底层)。"""

    BERRIES = "berries"   # 浆果 (植物系随处可采)
    FISH = "fish"         # 鱼 (近水地区)
    MEAT = "meat"         # 肉 (捕猎所得)


# region_id -> 该地区可觅得的食物来源。
# 文件岛资源丰富: 浆果 / 鱼 / 肉都有;无限山贫瘠,只有零星浆果。
REGION_FOOD: dict[str, list[FoodType]] = {
    "file_island": [FoodType.BERRIES, FoodType.FISH, FoodType.MEAT],
    "infinity_mountain": [FoodType.BERRIES],
}


def food_sources(region_id: str) -> list[FoodType]:
    """返回某地区可觅得的食物来源;未配置的地区返回空列表 (无处觅食)。"""
    return list(REGION_FOOD.get(region_id, []))


# ----------------------------------------------------------------------------
# NeedsState
# ----------------------------------------------------------------------------

@dataclass
class NeedsState:
    """一只数码兽的生理需求状态。

    Attributes:
        hunger: 饥饿值 (0-100),越低越饿。初始为饱食 (100)。
        last_food: 最近一次觅食吃到的食物类型 (None 表示还没吃过)。
    """

    hunger: int = HUNGER_MAX
    last_food: FoodType | None = field(default=None)

    def tick(self, decay: int = HUNGER_DECAY_PER_TICK) -> int:
        """世界推进一 tick: 饥饿加深 (hunger -= decay),夹紧到 [0, 100]。

        Returns:
            衰减后的 hunger。
        """
        self.hunger = max(HUNGER_MIN, self.hunger - decay)
        return self.hunger

    def is_hungry(self) -> bool:
        """是否已饿到需要优先觅食 (hunger < HUNGRY_THRESHOLD)。"""
        return self.hunger < HUNGRY_THRESHOLD

    def eat(self, food: FoodType, restore: int = FORAGE_RESTORE) -> int:
        """吃到食物,恢复饥饿值 (夹紧到 100),记录 last_food。

        Returns:
            恢复后的 hunger。
        """
        self.hunger = min(HUNGER_MAX, self.hunger + restore)
        self.last_food = food
        return self.hunger

    def to_dict(self) -> dict:
        return {
            "hunger": self.hunger,
            "last_food": self.last_food.value if self.last_food else None,
        }


# ----------------------------------------------------------------------------
# 与 agent 协作的辅助
# ----------------------------------------------------------------------------

# 计划文本前缀: 饥饿时插到计划最前,压过原有意图。
FORAGE_PLAN = "肚子饿了, 优先去寻找食物 (觅食)"


def should_forage(needs: NeedsState) -> bool:
    """饥饿到阈值以下时应优先觅食。"""
    return needs.is_hungry()


def forage(needs: NeedsState, region_id: str) -> FoodType | None:
    """在所在地区觅食一次。

    地区有食物 → 取第一种可得食物,恢复 hunger,返回吃到的食物类型。
    地区无食物 → 觅食失败,hunger 不变,返回 None。

    Args:
        needs: 觅食者的需求状态 (会被就地修改)。
        region_id: 觅食所在地区。

    Returns:
        吃到的 FoodType;觅食失败返回 None。
    """
    sources = food_sources(region_id)
    if not sources:
        return None
    food = sources[0]
    needs.eat(food)
    return food


def prioritized_plan(needs: NeedsState, base_plan: str | None) -> str:
    """若饥饿,把觅食计划提到最前;否则返回原计划。

    Returns:
        最终计划字符串。饥饿时为 FORAGE_PLAN (可附带原计划做补充)。
    """
    if should_forage(needs):
        if base_plan:
            return f"{FORAGE_PLAN}; 之后再{base_plan}"
        return FORAGE_PLAN
    return base_plan or ""


__all__ = [
    "FORAGE_PLAN",
    "FORAGE_RESTORE",
    "HUNGER_DECAY_PER_TICK",
    "HUNGER_MAX",
    "HUNGER_MIN",
    "HUNGRY_THRESHOLD",
    "REGION_FOOD",
    "FoodType",
    "NeedsState",
    "food_sources",
    "forage",
    "prioritized_plan",
    "should_forage",
]
