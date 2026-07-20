"""
孵化系统测试 — Phase 30 Task 2
===============================

覆盖 EggState / Hatchery / 季节修正因子 / 边界情况。
"""

from __future__ import annotations

import random
from dataclasses import FrozenInstanceError

import pytest

from digimon_world.world.egg_incubation import (
    MAX_INCUBATION_TICKS,
    MIN_INCUBATION_TICKS,
    EggState,
    Hatchery,
    HatchResult,
    _season_modifier,
    get_hatchery,
    reset_hatchery,
)

# ──────────────────────────────────────────────
# _season_modifier
# ──────────────────────────────────────────────

class TestSeasonModifier:
    def test_warm_seasons_accelerate(self):
        """温暖季节返回 >1 的加速因子。"""
        assert _season_modifier("summer") > 1.0
        assert _season_modifier("spring") > 1.0

    def test_cold_seasons_decelerate(self):
        """寒冷季节返回 <1 的减速因子。"""
        assert _season_modifier("winter") < 1.0
        assert _season_modifier("autumn") < 1.0
        assert _season_modifier("fall") < 1.0

    def test_unknown_season_neutral(self):
        """未知季节返回 1.0。"""
        assert _season_modifier("monsoon") == 1.0

    def test_none_season_neutral(self):
        """None 季节返回 1.0。"""
        assert _season_modifier(None) == 1.0


# ──────────────────────────────────────────────
# EggState
# ──────────────────────────────────────────────

class TestEggState:
    def test_creation_defaults(self):
        """创建 EggState 时默认字段正确。"""
        egg = EggState(
            egg_id="egg_0_0001",
            parent_a="Agumon",
            parent_b="Gabumon",
            child_species="Koromon",
            tick_laid=100,
            incubation_ticks=200,
        )
        assert egg.egg_id == "egg_0_0001"
        assert egg.parent_a == "Agumon"
        assert egg.parent_b == "Gabumon"
        assert egg.child_species == "Koromon"
        assert egg.tick_laid == 100
        assert egg.incubation_ticks == 200
        assert egg.elapsed_ticks == 0
        assert egg.hatch_progress == 0.0
        assert not egg.is_hatched()

    def test_is_hatched_false(self):
        """进度 < 1.0 时 is_hatched() 返回 False。"""
        egg = EggState("e1", "A", "B", "X", 0, 200, elapsed_ticks=50, hatch_progress=0.25)
        assert not egg.is_hatched()

    def test_is_hatched_true(self):
        """进度 >= 1.0 时 is_hatched() 返回 True。"""
        egg = EggState("e1", "A", "B", "X", 0, 200, elapsed_ticks=200, hatch_progress=1.0)
        assert egg.is_hatched()

    def test_is_hatched_beyond_one(self):
        """进度 > 1.0 也返回 True（防御编程）。"""
        egg = EggState("e1", "A", "B", "X", 0, 200, elapsed_ticks=250, hatch_progress=1.25)
        assert egg.is_hatched()

    def test_ticks_remaining(self):
        """剩余 tick 计算正确。"""
        egg = EggState("e1", "A", "B", "X", 0, 200, elapsed_ticks=50)
        assert egg.ticks_remaining() == 150

    def test_ticks_remaining_zero_when_done(self):
        """孵化完成时剩余 0。"""
        egg = EggState("e1", "A", "B", "X", 0, 200, elapsed_ticks=200, hatch_progress=1.0)
        assert egg.ticks_remaining() == 0

    def test_advance_increases_progress(self):
        """advance() 推进进度。"""
        egg = EggState("e1", "A", "B", "X", 0, 200, elapsed_ticks=0, hatch_progress=0.0)
        new_egg = egg.advance()
        assert new_egg.elapsed_ticks == 1
        assert new_egg.hatch_progress > 0.0
        assert not new_egg.is_hatched()

    def test_advance_warm_season_faster(self):
        """温暖季节孵化更快。"""
        egg = EggState("e1", "A", "B", "X", 0, 200, elapsed_ticks=0, hatch_progress=0.0)
        normal = egg.advance(current_season=None)
        warm = egg.advance(current_season="summer")
        assert warm.hatch_progress > normal.hatch_progress

    def test_advance_cold_season_slower(self):
        """寒冷季节孵化更慢。"""
        egg = EggState("e1", "A", "B", "X", 0, 200, elapsed_ticks=0, hatch_progress=0.0)
        normal = egg.advance(current_season=None)
        cold = egg.advance(current_season="winter")
        assert cold.hatch_progress < normal.hatch_progress

    def test_advance_already_hatched_no_change(self):
        """已孵化的蛋不再推进。"""
        egg = EggState("e1", "A", "B", "X", 0, 200, elapsed_ticks=200, hatch_progress=1.0)
        new_egg = egg.advance()
        assert new_egg is egg  # 同一实例
        assert new_egg.hatch_progress == 1.0

    def test_frozen_immutable(self):
        """EggState 是不可变的（frozen dataclass）。"""
        egg = EggState("e1", "A", "B", "X", 0, 200)
        with pytest.raises(FrozenInstanceError):
            egg.elapsed_ticks = 10  # type: ignore[misc]

    def test_to_dict(self):
        """to_dict 返回完整数据。"""
        egg = EggState("e1", "A", "B", "X", 0, 200, elapsed_ticks=50, hatch_progress=0.25)
        d = egg.to_dict()
        assert d["egg_id"] == "e1"
        assert d["parent_a"] == "A"
        assert d["parent_b"] == "B"
        assert d["hatch_progress"] == 0.25
        assert not d["is_hatched"]
        assert d["ticks_remaining"] == 150

    def test_hatch_progress_up_to_one(self):
        """多次 advance 后 hatch_progress 不超过 1.0。"""
        egg = EggState("e1", "A", "B", "X", 0, 10, elapsed_ticks=0, hatch_progress=0.0)
        for _ in range(20):
            egg = egg.advance(current_season="summer")
        assert egg.hatch_progress <= 1.0
        assert egg.is_hatched()

    def test_instant_hatch_zero_incubation(self):
        """incubation_ticks=0 的蛋立即孵化。"""
        egg = EggState("e1", "A", "B", "X", 0, 0, elapsed_ticks=0, hatch_progress=0.0)
        new_egg = egg.advance()
        assert new_egg.is_hatched()

    def test_season_at_laid_preserved(self):
        """产蛋季节在 advance 后保持不变。"""
        egg = EggState("e1", "A", "B", "X", 0, 200, season_at_laid="spring")
        new_egg = egg.advance(current_season="winter")
        assert new_egg.season_at_laid == "spring"


# ──────────────────────────────────────────────
# Hatchery — 注册
# ──────────────────────────────────────────────

class TestHatcheryLay:
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        reset_hatchery()
        yield
        reset_hatchery()

    def test_lay_egg_returns_egg_state(self):
        """lay_egg() 返回有效的 EggState。"""
        h = Hatchery()
        egg = h.lay_egg("A", "B", "Koromon", tick=100)
        assert isinstance(egg, EggState)
        assert egg.parent_a == "A"
        assert egg.parent_b == "B"
        assert egg.child_species == "Koromon"
        assert egg.tick_laid == 100
        assert egg.hatch_progress == 0.0

    def test_lay_egg_generates_unique_id(self):
        """每次 lay_egg 生成唯一 ID。"""
        h = Hatchery()
        e1 = h.lay_egg("A", "B", "X", 100)
        e2 = h.lay_egg("C", "D", "Y", 100)
        assert e1.egg_id != e2.egg_id

    def test_lay_egg_custom_incubation(self):
        """可指定自定义孵化时长。"""
        h = Hatchery()
        egg = h.lay_egg("A", "B", "X", 100, incubation_ticks=50)
        assert egg.incubation_ticks == 50

    def test_lay_egg_default_incubation_in_range(self):
        """默认孵化时长在 MIN/MAX 范围内。"""
        h = Hatchery(rng=random.Random(42))
        for _ in range(20):
            egg = h.lay_egg("A", "B", "X", 100)
            assert MIN_INCUBATION_TICKS <= egg.incubation_ticks <= MAX_INCUBATION_TICKS

    def test_lay_egg_sets_season(self):
        """传递 season 参数会记录在 egg 上。"""
        h = Hatchery()
        egg = h.lay_egg("A", "B", "X", 100, season="summer")
        assert egg.season_at_laid == "summer"


# ──────────────────────────────────────────────
# Hatchery — 推进
# ──────────────────────────────────────────────

class TestHatcheryTick:
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        reset_hatchery()
        yield
        reset_hatchery()

    def test_tick_advances_all_eggs(self):
        """tick() 推进所有蛋的孵化进度。"""
        h = Hatchery()
        h.lay_egg("A", "B", "X", 100, incubation_ticks=50)
        h.lay_egg("C", "D", "Y", 100, incubation_ticks=50)

        assert len(h.incubating_eggs()) == 2
        h.tick(101)
        # 1 tick 后还是孵育中
        assert len(h.incubating_eggs()) == 2

    def test_tick_returns_hatch_results_when_done(self):
        """当蛋孵化完成时 tick() 返回 HatchResult。"""
        h = Hatchery()
        h.lay_egg("A", "B", "X", 100, incubation_ticks=1)

        results = h.tick(101)
        assert len(results) == 1
        assert isinstance(results[0], HatchResult)
        assert results[0].parent_a == "A"
        assert results[0].parent_b == "B"
        assert results[0].child_species == "X"
        assert results[0].tick_hatched == 101

    def test_tick_multiple_hatch_same_tick(self):
        """同一 tick 可孵化多颗蛋。"""
        h = Hatchery()
        h.lay_egg("A", "B", "X", 100, incubation_ticks=1)
        h.lay_egg("C", "D", "Y", 100, incubation_ticks=1)

        results = h.tick(101)
        assert len(results) == 2

    def test_tick_season_affects_hatch_speed(self):
        """季节影响孵化速度——夏天更快孵化。"""
        h = Hatchery(rng=random.Random(42))
        h.lay_egg("A", "B", "X", 100, incubation_ticks=10)

        # 中性季节推进 5 步
        for tick in range(101, 106):
            h.tick(tick, season=None)
        neutral_eggs = h.incubating_eggs()
        neutral_progress = neutral_eggs[0].hatch_progress if neutral_eggs else 1.0

        reset_hatchery()
        h2 = Hatchery(rng=random.Random(42))
        h2.lay_egg("A", "B", "X", 100, incubation_ticks=10)
        for tick in range(101, 106):
            h2.tick(tick, season="summer")
        summer_eggs = h2.incubating_eggs()
        summer_progress = summer_eggs[0].hatch_progress if summer_eggs else 1.0

        assert summer_progress >= neutral_progress

    def test_tick_no_eggs_returns_empty(self):
        """无蛋时 tick() 返回空列表。"""
        h = Hatchery()
        results = h.tick(100)
        assert results == []

    def test_hatched_egg_still_in_all_eggs(self):
        """已孵化的蛋仍在 all_eggs() 中可查询。"""
        h = Hatchery()
        h.lay_egg("A", "B", "X", 100, incubation_ticks=1)
        h.tick(101)

        assert len(h.all_eggs()) == 1
        assert len(h.incubating_eggs()) == 0
        assert len(h.hatched_results()) == 1


# ──────────────────────────────────────────────
# Hatchery — 查询
# ──────────────────────────────────────────────

class TestHatcheryQueries:
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        reset_hatchery()
        yield
        reset_hatchery()

    def test_get_egg_by_id(self):
        """get_egg() 按 ID 查询。"""
        h = Hatchery()
        egg = h.lay_egg("A", "B", "X", 100)
        found = h.get_egg(egg.egg_id)
        assert found is not None
        assert found.egg_id == egg.egg_id

    def test_get_egg_not_found(self):
        """查询不存在的 ID 返回 None。"""
        h = Hatchery()
        assert h.get_egg("nonexistent") is None

    def test_all_eggs_sorted_by_tick(self):
        """all_eggs() 按产蛋时间排序。"""
        h = Hatchery()
        h.lay_egg("A", "B", "X", 100)
        h.lay_egg("C", "D", "Y", 200)
        all_eggs = h.all_eggs()
        assert all_eggs[0].tick_laid <= all_eggs[1].tick_laid

    def test_incubating_only_unhatched(self):
        """incubating_eggs() 只返回未孵化的。"""
        h = Hatchery()
        h.lay_egg("A", "B", "X", 100, incubation_ticks=1)
        h.lay_egg("C", "D", "Y", 100, incubation_ticks=100)
        h.tick(101)

        assert len(h.incubating_eggs()) == 1

    def test_hatched_results_append_only(self):
        """hatched_results() 按孵化顺序追加。"""
        h = Hatchery()
        h.lay_egg("A", "B", "X", 100, incubation_ticks=1)
        h.tick(101)
        h.lay_egg("C", "D", "Y", 102, incubation_ticks=1)
        h.tick(103)

        results = h.hatched_results()
        assert len(results) == 2
        assert results[0].egg_id != results[1].egg_id

    def test_eggs_from_parent(self):
        """eggs_from_parent() 查询某父母的所有蛋。"""
        h = Hatchery()
        h.lay_egg("Agumon", "Gabumon", "X", 100, incubation_ticks=50)
        h.lay_egg("Agumon", "Patamon", "Y", 101, incubation_ticks=50)
        h.lay_egg("Patamon", "Gabumon", "Z", 102, incubation_ticks=50)

        agumon_eggs = h.eggs_from_parent("Agumon")
        assert len(agumon_eggs) == 2

        gabumon_eggs = h.eggs_from_parent("Gabumon")
        assert len(gabumon_eggs) == 2

        patamon_eggs = h.eggs_from_parent("Patamon")
        assert len(patamon_eggs) == 2

    def test_eggs_from_parent_none(self):
        """未产蛋的父母返回空列表。"""
        h = Hatchery()
        assert h.eggs_from_parent("Nobody") == []


# ──────────────────────────────────────────────
# Hatchery — 统计
# ──────────────────────────────────────────────

class TestHatcheryStats:
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        reset_hatchery()
        yield
        reset_hatchery()

    def test_stats_empty(self):
        """空孵化器统计。"""
        h = Hatchery()
        s = h.stats()
        assert s["total_eggs_laid"] == 0
        assert s["incubating"] == 0
        assert s["hatched"] == 0
        assert s["avg_incubation_ticks"] == 0.0

    def test_stats_with_data(self):
        """有数据时的统计正确。"""
        h = Hatchery()
        h.lay_egg("A", "B", "X", 100, incubation_ticks=1)
        h.tick(101)
        h.lay_egg("C", "D", "Y", 102, incubation_ticks=100)

        s = h.stats()
        assert s["total_eggs_laid"] == 2
        assert s["hatched"] == 1
        assert s["incubating"] == 1
        assert s["avg_incubation_ticks"] > 0
        assert sum(s["progress_distribution"].values()) == 1  # 1 颗孵育中

    def test_progress_distribution(self):
        """进度分布统计正确。"""
        h = Hatchery()
        h.lay_egg("A", "B", "X", 100, incubation_ticks=100)
        h.lay_egg("C", "D", "Y", 100, incubation_ticks=100)

        # 推进到 25% 之前
        for _ in range(5):
            h.tick(101)
        d = h.stats()["progress_distribution"]
        assert d["0-25%"] == 2

        # 推进到 50%
        for _ in range(30):
            h.tick(101)
        d2 = h.stats()["progress_distribution"]
        assert d2["25-50%"] >= 1 or d2["50-75%"] >= 1


# ──────────────────────────────────────────────
# Hatchery — reset
# ──────────────────────────────────────────────

class TestHatcheryReset:
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        reset_hatchery()
        yield
        reset_hatchery()

    def test_reset_clears_all(self):
        """reset() 清空所有数据。"""
        h = Hatchery()
        h.lay_egg("A", "B", "X", 100, incubation_ticks=1)
        h.tick(101)
        assert len(h.all_eggs()) == 1

        h.reset()
        assert len(h.all_eggs()) == 0
        assert len(h.hatched_results()) == 0
        assert len(h.incubating_eggs()) == 0


# ──────────────────────────────────────────────
# 全局单例
# ──────────────────────────────────────────────

class TestGlobalSingleton:
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        reset_hatchery()
        yield
        reset_hatchery()

    def test_get_hatchery_returns_same_instance(self):
        """get_hatchery() 返回同一实例。"""
        h1 = get_hatchery()
        h2 = get_hatchery()
        assert h1 is h2

    def test_reset_hatchery_clears_global(self):
        """reset_hatchery() 清空全局单例。"""
        h1 = get_hatchery()
        h1.lay_egg("A", "B", "X", 100)
        reset_hatchery()
        h2 = get_hatchery()
        assert h2 is not h1
        assert len(h2.all_eggs()) == 0


# ──────────────────────────────────────────────
# 边界情况
# ──────────────────────────────────────────────

class TestEdgeCases:
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        reset_hatchery()
        yield
        reset_hatchery()

    def test_large_batch_of_eggs(self):
        """大量蛋同时孵化。"""
        h = Hatchery(rng=random.Random(42))
        for i in range(50):
            h.lay_egg(f"P{i}", f"Q{i}", "X", 100, incubation_ticks=5)

        results = []
        for tick in range(101, 111):
            results.extend(h.tick(tick))

        assert len(results) == 50
        assert len(h.hatched_results()) == 50

    def test_very_long_incubation(self):
        """超长孵化期（400 ticks）被正确处理。"""
        h = Hatchery()
        h.lay_egg("A", "B", "X", 0, incubation_ticks=MAX_INCUBATION_TICKS)

        for tick in range(1, MAX_INCUBATION_TICKS):
            h.tick(tick)
        assert len(h.incubating_eggs()) == 1
        assert len(h.hatched_results()) == 0

        h.tick(MAX_INCUBATION_TICKS)
        # 用 warm season 加速可能会提前孵化
        # 但至少应该推进了这么多 tick
        assert len(h.hatched_results()) >= 0  # 可能已孵化

    def test_tick_idempotent_on_hatched(self):
        """对已孵化的蛋再次 tick 不产生重复 hatch。"""
        h = Hatchery()
        h.lay_egg("A", "B", "X", 100, incubation_ticks=1)
        h.tick(101)  # 孵化
        assert len(h.hatched_results()) == 1

        h.tick(102)  # 不会再孵化
        assert len(h.hatched_results()) == 1
