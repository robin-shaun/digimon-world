"""
世代传承系统测试 — Phase 30
============================

覆盖 LineageRecord / LineageTracker / InheritanceEngine 全部功能。

测试范围:
- LineageRecord 创建与不变性
- LineageTracker 注册 / 查询（父母/子女/兄弟姐妹/世代/祖先/后代）
- LineageTracker 统计（代数分布 / 最多产 / 始祖）
- InheritanceEngine 标量继承 / 人格继承 / 知识亲和力 / 徽章亲和力 / 属性偏向
- 突变机制
- 边界情况（重复注册 / 空族谱 / 孤儿查询 / 零值）
"""

from __future__ import annotations

import random
from dataclasses import FrozenInstanceError

import pytest

from digimon_world.world.lineage import (
    DEFAULT_INHERITANCE_JITTER,
    DEFAULT_INHERITANCE_STRENGTH,
    DEFAULT_MUTATION_CHANCE,
    InheritanceEngine,
    InheritedTraits,
    LineageRecord,
    LineageTracker,
    get_lineage_tracker,
    reset_lineage_tracker,
)

# ──────────────────────────────────────────────
# 夹具
# ──────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_tracker() -> None:
    """每个测试前后重置全局 tracker，确保测试隔离。"""
    reset_lineage_tracker()
    random.seed(42)
    yield
    reset_lineage_tracker()


@pytest.fixture
def tracker() -> LineageTracker:
    """创建独立的 LineageTracker 实例。"""
    return LineageTracker()


# ──────────────────────────────────────────────
# LineageRecord 测试
# ──────────────────────────────────────────────


class TestLineageRecord:
    """LineageRecord 数据类测试。"""

    def test_create_record(self) -> None:
        rec = LineageRecord(
            parent_a="agumon",
            parent_b="gabumon",
            child="baby_01",
            tick_born=500,
            generation=1,
            child_species="botamon",
        )
        assert rec.parent_a == "agumon"
        assert rec.parent_b == "gabumon"
        assert rec.child == "baby_01"
        assert rec.tick_born == 500
        assert rec.generation == 1
        assert rec.child_species == "botamon"

    def test_parents_sorted(self) -> None:
        """parents() 返回字典序排序的 tuple。"""
        rec = LineageRecord(
            parent_a="gabumon",  # 字典序在 agumon 之前
            parent_b="agumon",
            child="baby",
            tick_born=0,
            generation=1,
        )
        assert rec.parents() == ("agumon", "gabumon")

    def test_parents_already_sorted(self) -> None:
        rec = LineageRecord(
            parent_a="agumon",
            parent_b="gabumon",
            child="baby",
            tick_born=0,
            generation=1,
        )
        assert rec.parents() == ("agumon", "gabumon")

    def test_immutable(self) -> None:
        """LineageRecord 是 frozen dataclass。"""
        rec = LineageRecord(
            parent_a="a", parent_b="b", child="c", tick_born=0, generation=1
        )
        with pytest.raises(FrozenInstanceError):
            rec.generation = 2  # type: ignore[misc]

    def test_to_dict(self) -> None:
        rec = LineageRecord(
            parent_a="agumon",
            parent_b="gabumon",
            child="baby",
            tick_born=100,
            generation=1,
            child_species="botamon",
        )
        d = rec.to_dict()
        assert d["parent_a"] == "agumon"
        assert d["parent_b"] == "gabumon"
        assert d["child"] == "baby"
        assert d["tick_born"] == 100
        assert d["generation"] == 1
        assert d["child_species"] == "botamon"


# ──────────────────────────────────────────────
# LineageTracker 注册测试
# ──────────────────────────────────────────────


class TestLineageTrackerRegister:
    """LineageTracker 注册功能测试。"""

    def test_register_single(self, tracker: LineageTracker) -> None:
        rec = tracker.register("agumon", "gabumon", "baby", tick_born=500)
        assert rec.child == "baby"
        assert rec.parent_a == "agumon"
        assert rec.parent_b == "gabumon"
        assert rec.tick_born == 500

    def test_register_computes_generation_from_founders(self, tracker: LineageTracker) -> None:
        """始祖的子代应为 Gen 1。"""
        tracker.set_founders(["agumon", "gabumon"])
        rec = tracker.register("agumon", "gabumon", "baby", tick_born=100)
        assert rec.generation == 1

    def test_register_computes_generation_from_parents(self, tracker: LineageTracker) -> None:
        """Gen 1 父母的子代应为 Gen 2。"""
        tracker.set_founders(["agumon", "gabumon"])
        tracker.register("agumon", "gabumon", "baby_gen1", tick_born=100)
        rec2 = tracker.register("baby_gen1", "other", "baby_gen2", tick_born=200)
        assert rec2.generation == 2

    def test_register_deep_generation(self, tracker: LineageTracker) -> None:
        """多代注册测试世代编号。"""
        tracker.set_founders(["alpha", "beta"])
        rec1 = tracker.register("alpha", "beta", "gen1", tick_born=100)
        assert rec1.generation == 1
        rec2 = tracker.register("gen1", "gamma", "gen2", tick_born=200)
        assert rec2.generation == 2
        rec3 = tracker.register("gen2", "delta", "gen3", tick_born=300)
        assert rec3.generation == 3

    def test_register_duplicate_child_raises(self, tracker: LineageTracker) -> None:
        """重复注册同一个 child 应报 ValueError。"""
        tracker.register("a", "b", "baby", tick_born=0)
        with pytest.raises(ValueError, match="already registered"):
            tracker.register("a", "b", "baby", tick_born=0)

    def test_register_with_species(self, tracker: LineageTracker) -> None:
        rec = tracker.register("a", "b", "baby", tick_born=50, child_species="botamon")
        assert rec.child_species == "botamon"

    def test_set_founder_does_not_overwrite(self, tracker: LineageTracker) -> None:
        """set_founder 不覆盖已有世代编号。"""
        tracker.register("a", "b", "child", tick_born=0)  # Gen 1
        tracker.set_founder("child")  # 不应改
        assert tracker.get_generation("child") == 1

    def test_set_founders_batch(self, tracker: LineageTracker) -> None:
        tracker.set_founders(["a", "b", "c", "d"])
        assert tracker.get_generation("a") == 0
        assert tracker.get_generation("b") == 0
        assert tracker.get_generation("c") == 0
        assert tracker.get_generation("d") == 0


# ──────────────────────────────────────────────
# LineageTracker 查询测试
# ──────────────────────────────────────────────


class TestLineageTrackerQuery:
    """LineageTracker 查询功能测试。"""

    @pytest.fixture
    def populated(self, tracker: LineageTracker) -> LineageTracker:
        """建立一个简单家族树:
        alpha + beta → child1 (Gen 1)
        alpha + beta → child2 (Gen 1)  [child1 的兄弟姐妹]
        child1 + gamma → grandchild (Gen 2)
        """
        tracker.set_founders(["alpha", "beta"])
        tracker.register("alpha", "beta", "child1", tick_born=100)
        tracker.register("alpha", "beta", "child2", tick_born=150)
        tracker.register("child1", "gamma", "grandchild", tick_born=300)
        return tracker

    def test_get_parents(self, populated: LineageTracker) -> None:
        parents = populated.get_parents("child1")
        assert parents is not None
        assert set(parents) == {"alpha", "beta"}

    def test_get_parents_founder_returns_none(self, populated: LineageTracker) -> None:
        assert populated.get_parents("alpha") is None

    def test_get_parents_unknown_returns_none(self, populated: LineageTracker) -> None:
        assert populated.get_parents("nonexistent") is None

    def test_get_children(self, populated: LineageTracker) -> None:
        children = populated.get_children("alpha")
        assert "child1" in children
        assert "child2" in children
        assert len(children) == 2

    def test_get_children_none(self, populated: LineageTracker) -> None:
        assert populated.get_children("grandchild") == []

    def test_get_siblings(self, populated: LineageTracker) -> None:
        siblings = populated.get_siblings("child1")
        assert siblings == ["child2"]

    def test_get_siblings_mutual(self, populated: LineageTracker) -> None:
        """兄弟姐妹关系应是对称的。"""
        assert populated.get_siblings("child2") == ["child1"]

    def test_get_siblings_none(self, populated: LineageTracker) -> None:
        assert populated.get_siblings("alpha") == []

    def test_get_siblings_founder(self, populated: LineageTracker) -> None:
        """始祖无父母记录，siblings 应为空。"""
        assert populated.get_siblings("alpha") == []

    def test_get_generation(self, populated: LineageTracker) -> None:
        assert populated.get_generation("alpha") == 0
        assert populated.get_generation("child1") == 1
        assert populated.get_generation("grandchild") == 2

    def test_get_generation_unknown(self, populated: LineageTracker) -> None:
        assert populated.get_generation("unknown") is None

    def test_get_record(self, populated: LineageTracker) -> None:
        rec = populated.get_record("child1")
        assert rec is not None
        assert rec.child == "child1"
        assert rec.generation == 1

    def test_get_record_founder(self, populated: LineageTracker) -> None:
        assert populated.get_record("alpha") is None

    def test_get_ancestors(self, populated: LineageTracker) -> None:
        ancestors = populated.get_ancestors("grandchild")
        # grandchild → child1 (parent) → alpha+beta (grandparents)
        assert "child1" in ancestors
        assert "alpha" in ancestors
        assert "beta" in ancestors

    def test_get_ancestors_founder(self, populated: LineageTracker) -> None:
        assert populated.get_ancestors("alpha") == []

    def test_get_descendants(self, populated: LineageTracker) -> None:
        descendants = populated.get_descendants("alpha")
        assert "child1" in descendants
        assert "child2" in descendants
        assert "grandchild" in descendants
        assert len(descendants) == 3

    def test_get_descendants_leaf(self, populated: LineageTracker) -> None:
        assert populated.get_descendants("grandchild") == []

    def test_get_family_tree(self, populated: LineageTracker) -> None:
        tree = populated.get_family_tree("child1")
        assert tree["name"] == "child1"
        assert tree["generation"] == 1
        assert tree["parents"] is not None
        assert set(tree["parents"]) == {"alpha", "beta"}
        assert "child2" in tree["siblings"]
        assert "grandchild" in tree["children"]
        assert tree["descendants_count"] == 1

    def test_get_family_tree_founder(self, populated: LineageTracker) -> None:
        tree = populated.get_family_tree("alpha")
        assert tree["name"] == "alpha"
        assert tree["generation"] == 0
        assert tree["parents"] is None
        assert len(tree["children"]) == 2


# ──────────────────────────────────────────────
# LineageTracker 统计测试
# ──────────────────────────────────────────────


class TestLineageTrackerStats:
    """LineageTracker 统计功能测试。"""

    def test_empty_stats(self, tracker: LineageTracker) -> None:
        s = tracker.stats()
        assert s["total_records"] == 0
        assert s["total_generations"] == 0
        assert s["deepest_generation"] == 0
        assert s["gen_distribution"] == {}
        assert s["most_children"] is None
        assert s["most_children_count"] == 0
        assert s["founders"] == []

    def test_stats_with_data(self, tracker: LineageTracker) -> None:
        tracker.set_founders(["a", "b", "c"])
        tracker.register("a", "b", "child1", tick_born=100)
        tracker.register("a", "b", "child2", tick_born=200)
        tracker.register("child1", "c", "grandchild", tick_born=300)

        s = tracker.stats()
        assert s["total_records"] == 3
        assert s["total_generations"] == 3  # Gen 0, 1, 2
        assert s["deepest_generation"] == 2
        assert s["gen_distribution"]["1"] == 2
        assert s["gen_distribution"]["2"] == 1
        # a 有 2 个子女 (child1, child2)
        assert s["most_children"] == "a"
        assert s["most_children_count"] == 2
        assert set(s["founders"]) == {"a", "b", "c"}

    def test_all_records(self, tracker: LineageTracker) -> None:
        tracker.register("a", "b", "c1", tick_born=0)
        tracker.register("a", "b", "c2", tick_born=100)
        records = tracker.all_records()
        assert len(records) == 2
        assert records[0].child == "c1"
        assert records[1].child == "c2"

    def test_reset(self, tracker: LineageTracker) -> None:
        tracker.register("a", "b", "c", tick_born=0)
        assert len(tracker.all_records()) == 1
        tracker.reset()
        assert len(tracker.all_records()) == 0
        assert tracker.get_generation("a") is None


# ──────────────────────────────────────────────
# InheritanceEngine 测试
# ──────────────────────────────────────────────


class TestInheritanceEngine:
    """InheritanceEngine 遗传计算测试。"""

    @pytest.fixture
    def engine(self) -> InheritanceEngine:
        """固定种子的确定性引擎。"""
        return InheritanceEngine(rng=random.Random(42))

    @pytest.fixture
    def chaotic_engine(self) -> InheritanceEngine:
        """高突变引擎用于测试突变路径。"""
        return InheritanceEngine(
            rng=random.Random(7),
            mutation_chance=1.0,  # 100% 突变
        )

    # ── _inherit_scalar ───────────────────────

    def test_inherit_scalar_midpoint(self, engine: InheritanceEngine) -> None:
        """确定性引擎（seed=42），测试标量继承在合理范围内。"""
        result = engine._inherit_scalar(0.5, 0.5)
        assert 0.0 <= result <= 1.0

    def test_inherit_scalar_from_one(self, engine: InheritanceEngine) -> None:
        """父母一方极端值。"""
        result = engine._inherit_scalar(1.0, 0.0)
        assert 0.0 <= result <= 1.0

    def test_inherit_scalar_identical_parents(self, engine: InheritanceEngine) -> None:
        """相同父母值应接近原值。"""
        # 种子确定性，多次调用中值应接近 0.7
        results = [engine._inherit_scalar(0.7, 0.7) for _ in range(10)]
        avg = sum(results) / len(results)
        assert 0.55 < avg < 0.85  # 应当在父母值附近

    def test_inherit_scalar_mutation(self, chaotic_engine: InheritanceEngine) -> None:
        """100% 突变率下，每次结果应该不同（可能偶尔相同但极低概率）。"""
        results = {chaotic_engine._inherit_scalar(0.5, 0.5) for _ in range(20)}
        # 20 次全相同概率 ≈ 0，至少有 2 个不同值
        assert len(results) > 1

    # ── 人格继承 ──────────────────────────────

    def test_inherit_personality(self, engine: InheritanceEngine) -> None:
        p_a = {"E/I": 0.8, "S/N": 0.3, "T/F": 0.6, "J/P": 0.4}
        p_b = {"E/I": 0.4, "S/N": 0.7, "T/F": 0.4, "J/P": 0.6}
        result = engine.inherit_personality(p_a, p_b)
        assert set(result.keys()) == {"E/I", "J/P", "S/N", "T/F"}
        for v in result.values():
            assert 0.0 <= v <= 1.0

    def test_inherit_personality_asymmetric_keys(self, engine: InheritanceEngine) -> None:
        """父/母人格维度不完全对齐（一方多出维度）。"""
        p_a = {"E/I": 0.8, "S/N": 0.3}
        p_b = {"E/I": 0.4, "T/F": 0.6}
        result = engine.inherit_personality(p_a, p_b)
        assert set(result.keys()) == {"E/I", "S/N", "T/F"}
        # S/N 只在 p_a，应使用默认 0.5 补 p_b
        assert 0.0 <= result["S/N"] <= 1.0
        # T/F 只在 p_b，应使用默认 0.5 补 p_a
        assert 0.0 <= result["T/F"] <= 1.0

    # ── 知识亲和力继承 ─────────────────────────

    def test_inherit_knowledge(self, engine: InheritanceEngine) -> None:
        k_a = {"combat": 0.8, "social": 0.3}
        k_b = {"combat": 0.6, "social": 0.5, "exploration": 0.9}
        result = engine.inherit_knowledge_affinity(k_a, k_b)
        assert set(result.keys()) == {"combat", "exploration", "social"}
        for v in result.values():
            assert 0.0 <= v <= 1.0

    def test_inherit_knowledge_double_high_affinity(self, engine: InheritanceEngine) -> None:
        """双方高亲和力 (>0.6) 应有加成。"""
        # 使用确定性 rng，多次测试中至少有一次有加成效果
        k_a = {"combat": 0.9}
        k_b = {"combat": 0.9}
        # 用同一个 seed 尝试多次，应该有加成出现
        results = []
        for seed in range(100):
            e = InheritanceEngine(rng=random.Random(seed))
            r = e.inherit_knowledge_affinity(k_a, k_b)
            results.append(r["combat"])
        # 至少有些结果应 > 0.7（因为 parent avg=0.9, strength=0.6, 加成+0.1）
        assert any(r > 0.7 for r in results), f"Expected some results > 0.7, got max {max(results):.3f}"

    # ── 徽章亲和力继承 ─────────────────────────

    def test_inherit_crest_affinity(self, engine: InheritanceEngine) -> None:
        c_a = {"courage": 0.7, "friendship": 0.3}
        c_b = {"courage": 0.5, "knowledge": 0.8}
        result = engine.inherit_crest_affinity(c_a, c_b)
        assert set(result.keys()) == {"courage", "friendship", "knowledge"}
        for v in result.values():
            assert 0.0 <= v <= 1.0

    # ── 属性偏向继承 ──────────────────────────

    def test_inherit_attribute_bias_same(self, engine: InheritanceEngine) -> None:
        """相同属性父母，子代应偏向该属性。"""
        bias = engine.inherit_attribute_bias("vaccine", "vaccine")
        assert "vaccine" in bias
        assert bias["vaccine"] > 0.7  # 应高度偏向 vaccine

    def test_inherit_attribute_bias_mixed(self, engine: InheritanceEngine) -> None:
        """混合属性父母。"""
        bias = engine.inherit_attribute_bias("vaccine", "virus")
        assert "vaccine" in bias
        assert "virus" in bias
        # 总和应 ≈ 1.0
        assert 0.95 < sum(bias.values()) < 1.05

    def test_inherit_attribute_bias_mixed_three(self, engine: InheritanceEngine) -> None:
        """不同属性父母，只有两种属性出现。"""
        bias = engine.inherit_attribute_bias("data", "virus")
        assert set(bias.keys()) == {"data", "virus"}

    # ── compute_all ────────────────────────────

    def test_compute_all(self, engine: InheritanceEngine) -> None:
        traits = engine.compute_all(
            personality_a={"E/I": 0.8, "S/N": 0.3},
            personality_b={"E/I": 0.4, "S/N": 0.7},
            knowledge_a={"combat": 0.8},
            knowledge_b={"combat": 0.5},
            crests_a={"courage": 0.9},
            crests_b={"courage": 0.7},
            attr_a="vaccine",
            attr_b="data",
        )
        assert isinstance(traits, InheritedTraits)
        assert len(traits.personality_vector) == 2
        assert len(traits.knowledge_affinity) == 1
        assert len(traits.crest_affinity) == 1
        assert len(traits.attribute_bias) == 2

    def test_compute_all_to_dict(self, engine: InheritanceEngine) -> None:
        traits = engine.compute_all(
            personality_a={"E/I": 0.8},
            personality_b={"E/I": 0.4},
            knowledge_a={},
            knowledge_b={},
            crests_a={},
            crests_b={},
            attr_a="vaccine",
            attr_b="vaccine",
        )
        d = traits.to_dict()
        assert "personality_vector" in d
        assert "knowledge_affinity" in d
        assert "crest_affinity" in d
        assert "attribute_bias" in d


# ──────────────────────────────────────────────
# 全局单例测试
# ──────────────────────────────────────────────


class TestGlobalSingleton:
    """全局 LineageTracker 单例测试。"""

    def test_get_returns_same_instance(self) -> None:
        t1 = get_lineage_tracker()
        t2 = get_lineage_tracker()
        assert t1 is t2

    def test_reset_creates_new_instance(self) -> None:
        t1 = get_lineage_tracker()
        reset_lineage_tracker()
        t2 = get_lineage_tracker()
        assert t1 is not t2

    def test_reset_clears_data(self) -> None:
        t = get_lineage_tracker()
        t.register("a", "b", "c", tick_born=0)
        assert len(t.all_records()) == 1
        reset_lineage_tracker()
        t2 = get_lineage_tracker()
        assert len(t2.all_records()) == 0


# ──────────────────────────────────────────────
# 边界情况
# ──────────────────────────────────────────────


class TestEdgeCases:
    """边界情况测试。"""

    def test_single_parent_chain(self, tracker: LineageTracker) -> None:
        """单亲链（同一 parent 反复出现）——仅用于测试多代。"""
        tracker.set_founders(["origin"])
        tracker.register("origin", "origin", "gen1", tick_born=100)
        assert tracker.get_generation("gen1") == 1
        # origin + origin 仍是合法输入（数码世界无性别区分）
        tracker.register("gen1", "gen1", "gen2", tick_born=200)
        assert tracker.get_generation("gen2") == 2

    def test_empty_parents_query(self, tracker: LineageTracker) -> None:
        """查询未注册 name 应返回安全默认值。"""
        assert tracker.get_parents("nobody") is None
        assert tracker.get_children("nobody") == []
        assert tracker.get_siblings("nobody") == []
        assert tracker.get_generation("nobody") is None
        assert tracker.get_record("nobody") is None

    def test_large_generation_chain(self, tracker: LineageTracker) -> None:
        """深世代链条。"""
        tracker.set_founders(["g0"])
        names = ["g0"]
        for i in range(1, 11):
            child = f"g{i}"
            tracker.register(names[i - 1], names[max(0, i - 2)], child, tick_born=i * 100)
            names.append(child)
        assert tracker.get_generation("g10") == 10

    def test_inheritance_engine_defaults(self) -> None:
        """默认构造参数。"""
        engine = InheritanceEngine()
        assert engine.strength == DEFAULT_INHERITANCE_STRENGTH
        assert engine.jitter == DEFAULT_INHERITANCE_JITTER
        assert engine.mutation_chance == DEFAULT_MUTATION_CHANCE
