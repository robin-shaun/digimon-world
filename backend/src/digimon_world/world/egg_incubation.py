"""
孵化系统 (Egg Incubation System) — Phase 30
============================================

数码蛋不是立即孵化的——它需要经历一段孵化周期，期间受世界环境
（温度/季节/数码精灵数量）影响。本模块提供完整的孵化管理和状态追踪。

核心组件:
- EggState: 单颗蛋的孵化状态（不可变，每次 tick 生成新实例）
- Hatchery: 全局孵化管理器（注册/推进/孵化出生）

设计原则:
- 纯数据驱动，无 LLM 依赖
- EggState 不可变——每次推进返回新实例，保证历史状态可追溯
- Hatchery 单例模式，与 LineageTracker 协同工作
- 孵化速度受环境因素影响（温暖季节加速、寒季减速）

基础设施: Phase 5 (breeding) + Phase 30 (lineage)
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

DEFAULT_INCUBATION_TICKS: int = 200
"""默认孵化所需 tick 数（约 8.3 世界天，按 24 tick/天）。"""

MIN_INCUBATION_TICKS: int = 100
"""最短孵化时间（tick 数）。"""

MAX_INCUBATION_TICKS: int = 400
"""最长孵化时间（tick 数）。"""

HATCH_CHECK_INTERVAL: int = 1
"""孵化检查间隔（每个 tick 都检查）。"""

# 环境修正因子
SEASON_WARM_BONUS: float = 1.3
"""温暖季节（夏/春）孵化加速因子。"""

SEASON_COLD_PENALTY: float = 0.7
"""寒冷季节（冬/秋）孵化减速因子。"""

TEMP_NEUTRAL: float = 1.0
"""中性温度修正（默认）。"""

# 孵化进度的 warm/cold 判定阈值
PROGRESS_NOTIFY_THRESHOLD: float = 0.5
"""孵化进度超过 50% 时记录日志。"""

MAX_NAME_LENGTH: int = 30
"""蛋的名字最大长度。"""


# ---------------------------------------------------------------------------
# 环境季节辅助
# ---------------------------------------------------------------------------

_WARM_SEASONS: frozenset[str] = frozenset({"summer", "spring"})
_COLD_SEASONS: frozenset[str] = frozenset({"winter", "autumn", "fall"})


def _season_modifier(season: str | None) -> float:
    """根据季节返回孵化速度修正因子。

    Args:
        season: 当前季节名（如 'summer', 'winter'），None 视为中性。

    Returns:
        修正因子（>1 加速，<1 减速）。
    """
    if season is None:
        return TEMP_NEUTRAL
    s = season.lower()
    if s in _WARM_SEASONS:
        return SEASON_WARM_BONUS
    if s in _COLD_SEASONS:
        return SEASON_COLD_PENALTY
    return TEMP_NEUTRAL


# ---------------------------------------------------------------------------
# EggState — 不可变的蛋状态
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EggState:
    """一颗数码蛋的孵化状态（不可变）。

    Attributes:
        egg_id: 唯一标识符。
        parent_a: 父/母 A 名字。
        parent_b: 父/母 B 名字。
        child_species: 子代物种。
        tick_laid: 产蛋时的世界 tick。
        incubation_ticks: 总共需要的孵化 tick 数。
        elapsed_ticks: 已过去的孵化 tick 数。
        hatch_progress: 孵化进度 [0.0, 1.0]。
        season_at_laid: 产蛋时的季节。
    """

    egg_id: str
    parent_a: str
    parent_b: str
    child_species: str
    tick_laid: int
    incubation_ticks: int
    elapsed_ticks: int = 0
    hatch_progress: float = 0.0
    season_at_laid: str = "unknown"

    def is_hatched(self) -> bool:
        """是否已完成孵化。"""
        return self.hatch_progress >= 1.0

    def ticks_remaining(self) -> int:
        """剩余孵化 tick 数。"""
        return max(0, self.incubation_ticks - self.elapsed_ticks)

    def advance(self, current_season: str | None = None) -> EggState:
        """推进 1 tick 孵化进度，返回新 EggState。

        Args:
            current_season: 当前世界季节，影响孵化速度。

        Returns:
            新的 EggState（若已孵化完成则保持不变）。
        """
        if self.is_hatched():
            return self

        # 零孵化时长的蛋立即完成
        if self.incubation_ticks <= 0:
            return EggState(
                egg_id=self.egg_id,
                parent_a=self.parent_a,
                parent_b=self.parent_b,
                child_species=self.child_species,
                tick_laid=self.tick_laid,
                incubation_ticks=self.incubation_ticks,
                elapsed_ticks=self.elapsed_ticks + 1,
                hatch_progress=1.0,
                season_at_laid=self.season_at_laid,
            )

        modifier = _season_modifier(current_season)
        new_elapsed = self.elapsed_ticks + 1
        # 有效进度 = 1 tick × 季节修正
        effective_progress = min(1.0, new_elapsed / self.incubation_ticks * modifier)

        return EggState(
            egg_id=self.egg_id,
            parent_a=self.parent_a,
            parent_b=self.parent_b,
            child_species=self.child_species,
            tick_laid=self.tick_laid,
            incubation_ticks=self.incubation_ticks,
            elapsed_ticks=new_elapsed,
            hatch_progress=round(effective_progress, 4),
            season_at_laid=self.season_at_laid,
        )

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。"""
        return {
            "egg_id": self.egg_id,
            "parent_a": self.parent_a,
            "parent_b": self.parent_b,
            "child_species": self.child_species,
            "tick_laid": self.tick_laid,
            "incubation_ticks": self.incubation_ticks,
            "elapsed_ticks": self.elapsed_ticks,
            "hatch_progress": round(self.hatch_progress, 4),
            "is_hatched": self.is_hatched(),
            "ticks_remaining": self.ticks_remaining(),
            "season_at_laid": self.season_at_laid,
        }


# ---------------------------------------------------------------------------
# Hatchery — 孵化管理器
# ---------------------------------------------------------------------------


@dataclass
class HatchResult:
    """一颗蛋孵化后的结果。

    Attributes:
        egg_id: 孵化完成的蛋 ID。
        parent_a: 父/母 A 名字。
        parent_b: 父/母 B 名字。
        child_species: 子代物种。
        tick_hatched: 孵化发生的世界 tick。
    """

    egg_id: str
    parent_a: str
    parent_b: str
    child_species: str
    tick_hatched: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "egg_id": self.egg_id,
            "parent_a": self.parent_a,
            "parent_b": self.parent_b,
            "child_species": self.child_species,
            "tick_hatched": self.tick_hatched,
        }


class Hatchery:
    """全局孵化管理器。

    管理所有数码蛋的孵化进度，每 tick 推进所有蛋的状态，
    并在孵化完成时生成 HatchResult 供外部创建子代 agent。

    单例模式——通过 get_hatchery() 获取全局实例。

    生命周期:
    1. lay_egg() — 注册新蛋
    2. tick() — 推进所有蛋（由 scheduler 每 tick 调用）
    3. 孵化完成 → 生成 HatchResult → egg 移入已孵化列表
    """

    def __init__(self, rng: random.Random | None = None) -> None:
        self._eggs: dict[str, EggState] = {}
        """当前孵化中的蛋 (egg_id → EggState)。"""

        self._hatched: list[HatchResult] = []
        """已完成的孵化结果（按孵化顺序）。"""

        self._egg_counter: int = 0
        """自增序号，用于生成 egg_id。"""

        self._rng = rng or random.Random()

    # ── 注册 ──────────────────────────────────────

    def lay_egg(
        self,
        parent_a: str,
        parent_b: str,
        child_species: str,
        tick: int,
        incubation_ticks: int | None = None,
        season: str | None = None,
    ) -> EggState:
        """注册一颗新数码蛋。

        Args:
            parent_a: 父/母 A 名字。
            parent_b: 父/母 B 名字。
            child_species: 子代物种名（用于生成蛋的名字）。
            tick: 当前世界 tick。
            incubation_ticks: 自定义孵化时长；若为 None 则在默认范围随机。
            season: 当前季节。

        Returns:
            新创建的 EggState。
        """
        if incubation_ticks is None:
            incubation_ticks = self._rng.randint(MIN_INCUBATION_TICKS, MAX_INCUBATION_TICKS)

        self._egg_counter += 1
        egg_id = f"egg_{tick}_{self._egg_counter:04d}"

        egg = EggState(
            egg_id=egg_id,
            parent_a=parent_a,
            parent_b=parent_b,
            child_species=child_species,
            tick_laid=tick,
            incubation_ticks=incubation_ticks,
            elapsed_ticks=0,
            hatch_progress=0.0,
            season_at_laid=season or "unknown",
        )

        self._eggs[egg_id] = egg
        logger.info(
            "Egg laid: %s (%s + %s → %s, %d ticks to hatch)",
            egg_id, parent_a, parent_b, child_species, incubation_ticks,
        )
        return egg

    # ── 推进 ──────────────────────────────────────

    def tick(self, current_tick: int, season: str | None = None) -> list[HatchResult]:
        """推进所有孵化中蛋的孵化进度 1 tick。

        Args:
            current_tick: 当前世界 tick。
            season: 当前季节（影响孵化速度）。

        Returns:
            本 tick 新孵化完成的 HatchResult 列表。
        """
        newly_hatched: list[HatchResult] = []
        updated_eggs: dict[str, EggState] = {}

        for egg_id, egg in self._eggs.items():
            if egg.is_hatched():
                # 已孵化完成但尚未移出的蛋，保留在孵化列表
                updated_eggs[egg_id] = egg
                continue

            new_egg = egg.advance(current_season=season)

            # 日志：孵化过半时通知
            if egg.hatch_progress < PROGRESS_NOTIFY_THRESHOLD <= new_egg.hatch_progress:
                logger.debug(
                    "Egg %s hatch progress: %.1f%% (%d/%d ticks)",
                    egg_id,
                    new_egg.hatch_progress * 100,
                    new_egg.elapsed_ticks,
                    new_egg.incubation_ticks,
                )

            if new_egg.is_hatched():
                result = HatchResult(
                    egg_id=egg_id,
                    parent_a=new_egg.parent_a,
                    parent_b=new_egg.parent_b,
                    child_species=new_egg.child_species,
                    tick_hatched=current_tick,
                )
                newly_hatched.append(result)
                self._hatched.append(result)
                logger.info(
                    "Egg hatched: %s → %s (parents: %s + %s, tick %d)",
                    egg_id, new_egg.child_species, new_egg.parent_a, new_egg.parent_b, current_tick,
                )

            updated_eggs[egg_id] = new_egg

        self._eggs = updated_eggs
        return newly_hatched

    # ── 查询 ──────────────────────────────────────

    def get_egg(self, egg_id: str) -> EggState | None:
        """按 ID 查询蛋状态。"""
        return self._eggs.get(egg_id)

    def all_eggs(self) -> list[EggState]:
        """返回所有蛋（含已孵化），按产蛋 tick 排序。"""
        return sorted(self._eggs.values(), key=lambda e: e.tick_laid)

    def incubating_eggs(self) -> list[EggState]:
        """返回尚未孵化的蛋。"""
        return [e for e in self._eggs.values() if not e.is_hatched()]

    def hatched_results(self) -> list[HatchResult]:
        """返回所有已完成的孵化结果。"""
        return list(self._hatched)

    def eggs_from_parent(self, parent_name: str) -> list[EggState]:
        """查询某数码兽作为父母的所有蛋。"""
        return [
            e for e in self._eggs.values()
            if e.parent_a == parent_name or e.parent_b == parent_name
        ]

    # ── 统计 ──────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """孵化统计。"""
        all_eggs = self.all_eggs()
        incubating = self.incubating_eggs()
        hatched = self.hatched_results()

        # 平均孵化时长
        if hatched:
            total_ticks = 0
            for h in hatched:
                egg = self._eggs.get(h.egg_id)
                if egg:
                    total_ticks += egg.elapsed_ticks
            avg_incubation = round(total_ticks / len(hatched), 1)
        else:
            avg_incubation = 0.0

        # 孵化进度分布
        progress_buckets = {"0-25%": 0, "25-50%": 0, "50-75%": 0, "75-100%": 0}
        for e in incubating:
            p = e.hatch_progress
            if p < 0.25:
                progress_buckets["0-25%"] += 1
            elif p < 0.50:
                progress_buckets["25-50%"] += 1
            elif p < 0.75:
                progress_buckets["50-75%"] += 1
            else:
                progress_buckets["75-100%"] += 1

        return {
            "total_eggs_laid": len(all_eggs),
            "incubating": len(incubating),
            "hatched": len(hatched),
            "avg_incubation_ticks": avg_incubation,
            "progress_distribution": progress_buckets,
        }

    # ── 管理 ──────────────────────────────────────

    def reset(self) -> None:
        """清空所有孵化数据（主要用于测试）。"""
        self._eggs.clear()
        self._hatched.clear()
        self._egg_counter = 0


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

_hatchery: Hatchery | None = None


def get_hatchery() -> Hatchery:
    """获取全局 Hatchery 单例。"""
    global _hatchery
    if _hatchery is None:
        _hatchery = Hatchery()
    return _hatchery


def reset_hatchery() -> None:
    """重置全局 Hatchery（主要用于测试）。"""
    global _hatchery
    if _hatchery is not None:
        _hatchery.reset()
    _hatchery = None


__all__ = [
    "DEFAULT_INCUBATION_TICKS",
    "MAX_INCUBATION_TICKS",
    "MIN_INCUBATION_TICKS",
    "EggState",
    "HatchResult",
    "Hatchery",
    "_season_modifier",
    "get_hatchery",
    "reset_hatchery",
]
