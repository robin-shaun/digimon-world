"""
Agent Self-Model 测试 — Phase 28
================================

覆盖 SelfModel / SelfEvaluator / SelfModelRegistry 全部功能。

测试范围:
- SelfModel 初始化与默认值
- Identity / Self-assessment / Uncertainty 正确性
- SelfEvaluator 分数计算（combat / social / exploration / knowledge）
- 自我评估调整与不确定性衰减
- 轨迹记录
- 改进目标生成
- 注册表单例模式
- 多 agent 独立性
- 边界情况（零值、最大值、reset）
"""

from __future__ import annotations

import random

import pytest

from digimon_world.world.self_model import (
    DEFAULT_IDENTITY_TARGET,
    DEFAULT_INITIAL_UNCERTAINTY,
    DEFAULT_MAX_GOALS,
    MIN_UNCERTAINTY,
    SELF_ASSESSMENT_ADJUSTMENT_RATE,
    SELF_MODEL_DIMS,
    SelfEvaluator,
    SelfModel,
    SelfModelRegistry,
    _clamp,
    _compute_combat_score,
    _compute_exploration_score,
    _compute_knowledge_score,
    _compute_social_score,
    _jitter,
    _sigmoid_normalize,
    get_self_model_registry,
    reset_self_model_registry,
)

# ──────────────────────────────────────────────
# 夹具
# ──────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_registry():
    """每个测试前后重置全局注册表，确保测试隔离。"""
    reset_self_model_registry()
    random.seed(42)  # 确定性随机
    yield
    reset_self_model_registry()


@pytest.fixture
def registry() -> SelfModelRegistry:
    """创建独立的 SelfModelRegistry 实例。"""
    return SelfModelRegistry()


# ──────────────────────────────────────────────
# 辅助函数测试
# ──────────────────────────────────────────────


class TestHelperFunctions:
    """_clamp / _sigmoid_normalize / _jitter 单元测试。"""

    def test_clamp_within_range(self):
        assert _clamp(0.5) == 0.5
        assert _clamp(0.0) == 0.0
        assert _clamp(1.0) == 1.0

    def test_clamp_below_range(self):
        assert _clamp(-0.5) == 0.0
        assert _clamp(-100.0) == 0.0

    def test_clamp_above_range(self):
        assert _clamp(1.5) == 1.0
        assert _clamp(100.0) == 1.0

    def test_sigmoid_normalize_zero_max(self):
        assert _sigmoid_normalize(50.0, 0.0) == 0.0

    def test_sigmoid_normalize_normal(self):
        assert _sigmoid_normalize(25.0, 50.0) == 0.5
        assert _sigmoid_normalize(100.0, 50.0) == 1.0  # clamped
        assert _sigmoid_normalize(0.0, 50.0) == 0.0

    def test_jitter_in_range(self):
        base = 0.5
        for _ in range(100):
            result = _jitter(base, 0.15)
            assert 0.0 <= result <= 1.0
            assert abs(result - base) <= 0.15 + 1e-9


# ──────────────────────────────────────────────
# SelfModel 测试
# ──────────────────────────────────────────────


class TestSelfModel:
    """SelfModel 初始化、内省调度、轨迹、序列化。"""

    def test_default_initialization(self):
        """默认创建：identity 和 self_assessment 有合理的随机基线值。"""
        model = SelfModel(agent_name="agumon")
        assert model.agent_name == "agumon"

        for dim in SELF_MODEL_DIMS:
            # identity 应在 [0.05, 0.3] 范围内
            assert 0.0 < model.identity[dim] <= 0.3
            # self_assessment 应在 identity ± 0.15 范围内
            assert abs(model.self_assessment[dim] - model.identity[dim]) <= 0.15 + 1e-9

    def test_uncertainty_defaults(self):
        """所有维度不确定性初始为 DEFAULT_INITIAL_UNCERTAINTY (0.8)。"""
        model = SelfModel(agent_name="agumon")
        for dim in SELF_MODEL_DIMS:
            assert model.uncertainty[dim] == DEFAULT_INITIAL_UNCERTAINTY

    def test_trajectory_starts_empty(self):
        """初始轨迹为空。"""
        model = SelfModel(agent_name="agumon")
        assert model.trajectory == []

    def test_improvement_goals_starts_empty(self):
        """初始改进目标为空。"""
        model = SelfModel(agent_name="agumon")
        assert model.improvement_goals == []

    def test_default_fields(self):
        """检查默认字段值。"""
        model = SelfModel(agent_name="test")
        assert model.last_introspection_tick == 0
        assert model.introspection_interval == 10

    def test_explicit_identity(self):
        """显式设置 identity 时，self_assessment 自动在其基础上抖动。"""
        identity = {
            "combat_score": 0.8,
            "social_score": 0.6,
            "exploration_score": 0.4,
            "knowledge_score": 0.2,
        }
        model = SelfModel(agent_name="test", identity=identity)
        assert model.identity == identity
        for dim in SELF_MODEL_DIMS:
            assert abs(model.self_assessment[dim] - identity[dim]) <= 0.15 + 1e-9

    def test_explicit_self_assessment_no_jitter(self):
        """显式设置 self_assessment 时不再抖动。"""
        identity = {"combat_score": 0.7, "social_score": 0.5,
                     "exploration_score": 0.3, "knowledge_score": 0.1}
        self_assessment = {"combat_score": 0.75, "social_score": 0.45,
                           "exploration_score": 0.35, "knowledge_score": 0.15}
        model = SelfModel(agent_name="test", identity=identity,
                          self_assessment=self_assessment)
        assert model.self_assessment == self_assessment
        # identity 不变
        assert model.identity == identity

    def test_should_introspect_first_tick(self):
        """tick 0 时不应触发内省（0 - 0 < 10）。"""
        model = SelfModel(agent_name="test")
        assert not model.should_introspect(0)
        assert not model.should_introspect(5)
        assert not model.should_introspect(9)

    def test_should_introspect_at_interval(self):
        """tick 10 时应触发内省（10 - 0 >= 10）。"""
        model = SelfModel(agent_name="test")
        assert model.should_introspect(10)
        assert model.should_introspect(15)

    def test_should_introspect_after_last_tick(self):
        """更新 last_introspection_tick 后重新计算。"""
        model = SelfModel(agent_name="test")
        model.last_introspection_tick = 10
        assert not model.should_introspect(15)  # 15 - 10 = 5 < 10
        assert model.should_introspect(20)       # 20 - 10 = 10 >= 10

    def test_record_snapshot(self):
        """记录快照后 trajectory 包含正确的数据。"""
        model = SelfModel(agent_name="test")
        model.record_snapshot(10)
        assert len(model.trajectory) == 1
        snap = model.trajectory[0]
        assert snap["tick"] == 10
        assert "identity" in snap
        assert "self_assessment" in snap
        assert "uncertainty" in snap

    def test_to_dict(self):
        """to_dict 包含所有关键字段。"""
        model = SelfModel(agent_name="test")
        d = model.to_dict()
        assert d["agent_name"] == "test"
        assert "identity" in d
        assert "self_assessment" in d
        assert "uncertainty" in d
        assert "trajectory" in d
        assert "improvement_goals" in d
        assert "last_introspection_tick" in d
        assert "introspection_interval" in d


# ──────────────────────────────────────────────
# SelfEvaluator 分数计算测试
# ──────────────────────────────────────────────


class TestSelfEvaluatorComputeScores:
    """SelfEvaluator.compute_actual_scores 各维度分数计算。"""

    def test_empty_context_returns_near_zero(self):
        """空上下文返回接近 0 的分数。"""
        scores = SelfEvaluator.compute_actual_scores({})
        for dim in SELF_MODEL_DIMS:
            assert 0.0 <= scores[dim] < 0.15  # 带 stage_mult 可能略高

    def test_combat_from_battle_victories(self):
        """战斗胜利影响 combat_score。"""
        scores_zero = SelfEvaluator.compute_actual_scores({})
        scores_mid = SelfEvaluator.compute_actual_scores({
            "battle_victories": 25, "attack": 100, "defense": 75,
        })
        scores_max = SelfEvaluator.compute_actual_scores({
            "battle_victories": 50, "attack": 200, "defense": 150,
            "evolution_stage": "mega",
        })
        assert scores_mid["combat_score"] > scores_zero["combat_score"]
        assert scores_max["combat_score"] > scores_mid["combat_score"]
        assert scores_max["combat_score"] > 0.8

    def test_social_from_relationships(self):
        """关系和对话影响 social_score。"""
        scores_zero = SelfEvaluator.compute_actual_scores({})
        scores_high = SelfEvaluator.compute_actual_scores({
            "relationship_count": 20, "dialogue_count": 100,
            "friendship_levels": [0.9, 0.8, 0.7],
        })
        assert scores_high["social_score"] > scores_zero["social_score"]
        assert scores_high["social_score"] > 0.7

    def test_exploration_from_regions(self):
        """访问区域影响 exploration_score。"""
        scores_zero = SelfEvaluator.compute_actual_scores({})
        scores_high = SelfEvaluator.compute_actual_scores({
            "regions_visited": 10, "distance_traveled": 1000.0,
        })
        assert scores_high["exploration_score"] > scores_zero["exploration_score"]
        assert scores_high["exploration_score"] > 0.8

    def test_knowledge_from_skills(self):
        """技能/发明影响 knowledge_score。"""
        scores_zero = SelfEvaluator.compute_actual_scores({})
        scores_high = SelfEvaluator.compute_actual_scores({
            "skills_count": 10, "inventions_count": 10, "knowledge_citations": 10,
        })
        assert scores_high["knowledge_score"] > scores_zero["knowledge_score"]
        assert scores_high["knowledge_score"] > 0.8

    def test_evolution_stage_affects_combat(self):
        """更高进化阶段 → 更高 combat_score。"""
        scores_baby = SelfEvaluator.compute_actual_scores({
            "battle_victories": 25, "attack": 100, "defense": 75,
            "evolution_stage": "baby_i",
        })
        scores_mega = SelfEvaluator.compute_actual_scores({
            "battle_victories": 25, "attack": 100, "defense": 75,
            "evolution_stage": "mega",
        })
        assert scores_mega["combat_score"] > scores_baby["combat_score"]

    def test_max_context_all_ones(self):
        """最大上下文值产生接近 1.0 的分数。"""
        scores = SelfEvaluator.compute_actual_scores({
            "battle_victories": 100, "attack": 500, "defense": 500,
            "evolution_stage": "mega",
            "relationship_count": 50, "dialogue_count": 200,
            "friendship_levels": [1.0, 1.0, 1.0, 1.0],
            "regions_visited": 20, "distance_traveled": 5000.0,
            "skills_count": 20, "inventions_count": 20, "knowledge_citations": 20,
        })
        for dim in SELF_MODEL_DIMS:
            assert scores[dim] >= 0.9, f"{dim} should be high, got {scores[dim]}"

    def test_all_dims_returned(self):
        """返回所有四个维度。"""
        scores = SelfEvaluator.compute_actual_scores({})
        assert set(scores.keys()) == set(SELF_MODEL_DIMS)

    def test_internal_combat_function(self):
        """内部 _compute_combat_score 直接调用。"""
        score = _compute_combat_score({"battle_victories": 25, "attack": 100,
                                        "defense": 75, "evolution_stage": "champion"})
        assert 0.0 < score <= 1.0

    def test_internal_social_function(self):
        """内部 _compute_social_score 直接调用。"""
        score = _compute_social_score({"relationship_count": 10, "dialogue_count": 50})
        assert 0.0 < score <= 1.0

    def test_internal_exploration_function(self):
        """内部 _compute_exploration_score 直接调用。"""
        score = _compute_exploration_score({"regions_visited": 5, "distance_traveled": 500.0})
        assert 0.0 < score <= 1.0

    def test_internal_knowledge_function(self):
        """内部 _compute_knowledge_score 直接调用。"""
        score = _compute_knowledge_score({"skills_count": 5, "inventions_count": 3})
        assert 0.0 < score <= 1.0


# ──────────────────────────────────────────────
# SelfEvaluator evaluate 测试
# ──────────────────────────────────────────────


class TestSelfEvaluatorEvaluate:
    """SelfEvaluator.evaluate 完整评估流程。"""

    def test_evaluate_creates_model_if_none(self):
        """传入 None self_model 时自动创建。"""
        result = SelfEvaluator.evaluate(
            agent_name="agumon",
            agent_context={"battle_victories": 10, "attack": 100},
            tick=10,
        )
        assert result.agent_name == "agumon"
        assert result.tick == 10

    def test_evaluate_updates_identity(self):
        """评估后 identity 反映实际分数。"""
        model = SelfModel(agent_name="test")
        model.identity = {"combat_score": 0.0, "social_score": 0.0,
                          "exploration_score": 0.0, "knowledge_score": 0.0}
        model.self_assessment = {"combat_score": 0.0, "social_score": 0.0,
                                 "exploration_score": 0.0, "knowledge_score": 0.0}

        result = SelfEvaluator.evaluate(
            agent_name="test",
            agent_context={
                "battle_victories": 50, "attack": 200, "defense": 150,
                "evolution_stage": "mega",
            },
            self_model=model,
            tick=10,
        )
        assert model.identity["combat_score"] > 0.0
        assert result.actual_scores["combat_score"] == model.identity["combat_score"]

    def test_evaluate_adjusts_self_assessment_toward_identity(self):
        """self_assessment 向 identity 收敛。"""
        model = SelfModel(agent_name="test")
        model.identity = {"combat_score": 0.8, "social_score": 0.5,
                          "exploration_score": 0.5, "knowledge_score": 0.5}
        model.self_assessment = {"combat_score": 0.2, "social_score": 0.5,
                                 "exploration_score": 0.5, "knowledge_score": 0.5}

        SelfEvaluator.evaluate(
            agent_name="test",
            agent_context={"battle_victories": 50, "attack": 200, "defense": 150,
                           "evolution_stage": "mega"},
            self_model=model,
            tick=10,
        )

        # self_assessment 应该向 identity 方向移动
        assert model.self_assessment["combat_score"] > 0.2
        assert model.self_assessment["combat_score"] < model.identity["combat_score"]

    def test_evaluate_adjustment_rate(self):
        """调整量 = gap * SELF_ASSESSMENT_ADJUSTMENT_RATE。"""
        model = SelfModel(agent_name="test")
        model.identity = {"combat_score": 0.9, "social_score": 0.5,
                          "exploration_score": 0.5, "knowledge_score": 0.5}
        model.self_assessment = {"combat_score": 0.1, "social_score": 0.5,
                                 "exploration_score": 0.5, "knowledge_score": 0.5}

        result = SelfEvaluator.evaluate(
            agent_name="test",
            agent_context={"battle_victories": 50, "attack": 200, "defense": 150,
                           "evolution_stage": "mega"},
            self_model=model,
            tick=10,
        )

        expected_adjustment = (model.identity["combat_score"] - 0.1) * SELF_ASSESSMENT_ADJUSTMENT_RATE
        assert result.adjustments["combat_score"] == pytest.approx(expected_adjustment, abs=1e-4)

    def test_evaluate_reduces_uncertainty(self):
        """每次评估后不确定性下降。"""
        model = SelfModel(agent_name="test")
        initial_uncertainty = dict(model.uncertainty)

        SelfEvaluator.evaluate(
            agent_name="test",
            agent_context={
                "battle_victories": 25, "attack": 100,
                "relationship_count": 10, "dialogue_count": 50,
            },
            self_model=model,
            tick=10,
        )

        for dim in SELF_MODEL_DIMS:
            assert model.uncertainty[dim] < initial_uncertainty[dim]

    def test_evaluate_uncertainty_never_below_min(self):
        """不确定性不会低于 MIN_UNCERTAINTY。"""
        model = SelfModel(agent_name="test")
        # 直接设低值
        model.uncertainty = dict.fromkeys(SELF_MODEL_DIMS, MIN_UNCERTAINTY)

        SelfEvaluator.evaluate(
            agent_name="test",
            agent_context={
                "battle_victories": 50, "attack": 200, "defense": 150,
                "evolution_stage": "mega",
                "relationship_count": 20, "dialogue_count": 100,
            },
            self_model=model,
            tick=10,
        )

        for dim in SELF_MODEL_DIMS:
            assert model.uncertainty[dim] >= MIN_UNCERTAINTY

    def test_evaluate_uncertainty_decays_faster_with_experience(self):
        """经验更多 → 不确定性衰减更快。"""
        model_low_exp = SelfModel(agent_name="low")
        model_high_exp = SelfModel(agent_name="high")

        # 对齐初始 uncertainty
        model_high_exp.uncertainty = dict(model_low_exp.uncertainty)

        SelfEvaluator.evaluate(
            agent_name="low",
            agent_context={},  # 零经验
            self_model=model_low_exp,
            tick=10,
        )

        SelfEvaluator.evaluate(
            agent_name="high",
            agent_context={
                "battle_victories": 50, "attack": 200, "defense": 150,
                "evolution_stage": "mega",
                "relationship_count": 20, "dialogue_count": 100,
                "regions_visited": 10, "distance_traveled": 1000.0,
                "skills_count": 10, "inventions_count": 10,
            },
            self_model=model_high_exp,
            tick=10,
        )

        # 高经验 agent 的 uncertainty 更低
        for dim in SELF_MODEL_DIMS:
            assert model_high_exp.uncertainty[dim] < model_low_exp.uncertainty[dim]

    def test_evaluate_records_trajectory(self):
        """评估后 trajectory 增加一条快照。"""
        model = SelfModel(agent_name="test")
        assert len(model.trajectory) == 0

        SelfEvaluator.evaluate(
            agent_name="test",
            agent_context={"battle_victories": 10},
            self_model=model,
            tick=10,
        )
        assert len(model.trajectory) == 1
        assert model.trajectory[0]["tick"] == 10

    def test_evaluate_updates_last_introspection_tick(self):
        """评估后 last_introspection_tick 更新。"""
        model = SelfModel(agent_name="test")
        assert model.last_introspection_tick == 0

        SelfEvaluator.evaluate(
            agent_name="test",
            agent_context={},
            self_model=model,
            tick=15,
        )
        assert model.last_introspection_tick == 15

    def test_evaluate_returns_result_with_all_fields(self):
        """返回的 SelfAssessmentResult 包含所有字段。"""
        result = SelfEvaluator.evaluate(
            agent_name="test",
            agent_context={"battle_victories": 10},
            tick=10,
        )
        assert result.agent_name == "test"
        assert result.tick == 10
        assert isinstance(result.actual_scores, dict)
        assert isinstance(result.previous_self_assessment, dict)
        assert isinstance(result.new_self_assessment, dict)
        assert isinstance(result.uncertainty, dict)
        assert isinstance(result.adjustments, dict)
        assert isinstance(result.new_goals, list)

    def test_result_to_dict(self):
        """SelfAssessmentResult.to_dict 序列化正确。"""
        result = SelfEvaluator.evaluate(
            agent_name="test",
            agent_context={"battle_victories": 10},
            tick=10,
        )
        d = result.to_dict()
        assert d["agent_name"] == "test"
        assert d["tick"] == 10
        assert "actual_scores" in d


# ──────────────────────────────────────────────
# 改进目标生成测试
# ──────────────────────────────────────────────


class TestGoalGeneration:
    """SelfEvaluator.generate_goals 改进目标生成。"""

    def test_generates_goals_for_low_dimensions(self):
        """self_assessment 远低于目标时生成目标。"""
        model = SelfModel(agent_name="test")
        model.self_assessment = {
            "combat_score": 0.2,
            "social_score": 0.3,
            "exploration_score": 0.4,
            "knowledge_score": 0.5,
        }

        goals = SelfEvaluator.generate_goals(model)
        # combat (0.2→0.7 gap=0.5), social (0.3→0.7 gap=0.4),
        # exploration (0.4→0.7 gap=0.3), knowledge (0.5→0.7 gap=0.2)
        # All gaps > 0.15, so all 4 should generate goals
        # But max_goals=3, so only top 3
        assert len(goals) == min(4, DEFAULT_MAX_GOALS)
        # combat should be first (largest gap)
        assert goals[0]["dimension"] == "combat"

    def test_no_goals_when_close_to_target(self):
        """self_assessment 接近目标时不生成目标。"""
        model = SelfModel(agent_name="test")
        model.self_assessment = {
            "combat_score": 0.65,
            "social_score": 0.68,
            "exploration_score": 0.60,
            "knowledge_score": 0.70,
        }

        goals = SelfEvaluator.generate_goals(model)
        # combat: 0.7 - 0.65 = 0.05 < 0.15 → no goal
        # social: 0.7 - 0.68 = 0.02 < 0.15 → no goal
        # exploration: 0.7 - 0.60 = 0.10 < 0.15 → no goal
        # knowledge: 0.7 - 0.70 = 0.00 < 0.15 → no goal
        assert goals == []

    def test_goals_respect_max_goals(self):
        """生成目标不超过 max_goals。"""
        model = SelfModel(agent_name="test")
        model.self_assessment = dict.fromkeys(SELF_MODEL_DIMS, 0.1)

        goals = SelfEvaluator.generate_goals(model, max_goals=2)
        assert len(goals) == 2

    def test_goals_sorted_by_gap_desc(self):
        """目标按差距降序排列。"""
        model = SelfModel(agent_name="test")
        model.self_assessment = {
            "combat_score": 0.1,   # gap 0.6
            "social_score": 0.2,   # gap 0.5
            "exploration_score": 0.3,  # gap 0.4
            "knowledge_score": 0.4,    # gap 0.3
        }

        goals = SelfEvaluator.generate_goals(model)
        gaps = [g["target"] - g["current"] for g in goals]
        assert gaps == sorted(gaps, reverse=True)

    def test_goal_format(self):
        """验证目标的字段格式。"""
        model = SelfModel(agent_name="test")
        model.self_assessment = {"combat_score": 0.2, "social_score": 0.5,
                                 "exploration_score": 0.5, "knowledge_score": 0.5}

        goals = SelfEvaluator.generate_goals(model)
        goal = goals[0]
        assert goal["dimension"] == "combat"
        assert goal["current"] == 0.2
        assert goal["target"] == DEFAULT_IDENTITY_TARGET
        assert "reason" in goal
        assert "created_tick" in goal


# ──────────────────────────────────────────────
# SelfModelRegistry 测试
# ──────────────────────────────────────────────


class TestSelfModelRegistry:
    """注册表单例、CRUD、step、多 agent。"""

    def test_singleton_same_instance(self):
        """get_self_model_registry 返回同一实例。"""
        r1 = get_self_model_registry()
        r2 = get_self_model_registry()
        assert r1 is r2

    def test_reset_creates_new_instance(self):
        """reset 后 get 返回新实例。"""
        r1 = get_self_model_registry()
        reset_self_model_registry()
        r2 = get_self_model_registry()
        assert r1 is not r2

    def test_reset_clears_models(self):
        """reset 清除所有 agent 模型。"""
        r = get_self_model_registry()
        r.get_or_create("agumon")
        assert r.agent_count() == 1
        reset_self_model_registry()
        r2 = get_self_model_registry()
        assert r2.agent_count() == 0

    def test_get_nonexistent_returns_none(self):
        """get 不存在的 agent 返回 None。"""
        r = get_self_model_registry()
        assert r.get("nonexistent") is None

    def test_get_or_create_returns_model(self, registry):
        """get_or_create 返回 SelfModel。"""
        model = registry.get_or_create("agumon")
        assert isinstance(model, SelfModel)
        assert model.agent_name == "agumon"

    def test_get_or_create_idempotent(self, registry):
        """同一 agent 多次 get_or_create 返回同一实例。"""
        m1 = registry.get_or_create("agumon")
        m2 = registry.get_or_create("agumon")
        assert m1 is m2

    def test_multiple_agents_independent(self, registry):
        """不同 agent 各自独立的 SelfModel。"""
        agumon = registry.get_or_create("agumon")
        gabumon = registry.get_or_create("gabumon")

        assert agumon is not gabumon
        assert agumon.agent_name != gabumon.agent_name

        # 各自修改互不影响
        agumon.identity["combat_score"] = 0.9
        assert gabumon.identity["combat_score"] != 0.9

    def test_step_evaluates_at_correct_tick(self, registry):
        """tick 10 时 step 触发评估。"""
        registry.get_or_create("agumon")  # last_introspection_tick=0
        result = registry.step("agumon", {"battle_victories": 10}, tick=10)
        assert result is not None
        assert result.tick == 10

    def test_step_skips_before_interval(self, registry):
        """tick 5 时 step 跳过评估。"""
        registry.get_or_create("agumon")
        result = registry.step("agumon", {"battle_victories": 10}, tick=5)
        assert result is None

    def test_step_force_overrides_interval(self, registry):
        """force=True 在任何 tick 都触发评估。"""
        registry.get_or_create("agumon")
        result = registry.step("agumon", {"battle_victories": 10}, tick=3, force=True)
        assert result is not None
        assert result.tick == 3

    def test_list_agents(self, registry):
        """list_agents 返回所有 agent 名称。"""
        registry.get_or_create("agumon")
        registry.get_or_create("gabumon")
        agents = registry.list_agents()
        assert set(agents) == {"agumon", "gabumon"}

    def test_agent_count(self, registry):
        """agent_count 返回值正确。"""
        assert registry.agent_count() == 0
        registry.get_or_create("agumon")
        assert registry.agent_count() == 1
        registry.get_or_create("gabumon")
        assert registry.agent_count() == 2

    def test_set_method(self, registry):
        """set 手动设置模型。"""
        custom = SelfModel(agent_name="custom",
                           identity={"combat_score": 0.9, "social_score": 0.8,
                                     "exploration_score": 0.7, "knowledge_score": 0.6},
                           self_assessment={"combat_score": 0.85, "social_score": 0.75,
                                            "exploration_score": 0.65, "knowledge_score": 0.55})
        registry.set("custom", custom)
        assert registry.get("custom") is custom

    def test_reset_method(self, registry):
        """registry.reset() 清除所有模型。"""
        registry.get_or_create("agumon")
        registry.get_or_create("gabumon")
        assert registry.agent_count() == 2
        registry.reset()
        assert registry.agent_count() == 0

    def test_to_dict(self, registry):
        """to_dict 序列化所有 agent 模型。"""
        registry.get_or_create("agumon")
        d = registry.to_dict()
        assert "agumon" in d
        assert d["agumon"]["agent_name"] == "agumon"

    def test_multiple_evaluations_uncertainty_decay(self, registry):
        """多次 step 后不确定性持续下降。"""
        agumon = registry.get_or_create("agumon")

        initial_uncertainty = dict(agumon.uncertainty)

        # 多次评估（每 10 tick）
        for i in range(5):
            tick = (i + 1) * 10
            registry.step(
                "agumon",
                {
                    "battle_victories": 25, "attack": 100, "defense": 75,
                    "relationship_count": 10, "dialogue_count": 50,
                },
                tick=tick,
            )

        for dim in SELF_MODEL_DIMS:
            assert agumon.uncertainty[dim] < initial_uncertainty[dim]


# ──────────────────────────────────────────────
# 边界情况测试
# ──────────────────────────────────────────────


class TestEdgeCases:
    """边界情况：零值、最大值、轨迹裁剪。"""

    def test_agent_with_zero_stats(self):
        """全零上下文的 agent 有低但有效的分数。"""
        model = SelfModel(agent_name="zero")
        model.identity = dict.fromkeys(SELF_MODEL_DIMS, 0.0)
        model.self_assessment = dict.fromkeys(SELF_MODEL_DIMS, 0.0)

        result = SelfEvaluator.evaluate(
            agent_name="zero",
            agent_context={},
            self_model=model,
            tick=10,
        )

        for dim in SELF_MODEL_DIMS:
            assert 0.0 <= result.actual_scores[dim] <= 0.2

    def test_agent_with_max_stats(self):
        """最大值上下文产生接近 1.0 的分数。"""
        model = SelfModel(agent_name="max")
        model.identity = dict.fromkeys(SELF_MODEL_DIMS, 0.0)
        model.self_assessment = dict.fromkeys(SELF_MODEL_DIMS, 0.0)

        result = SelfEvaluator.evaluate(
            agent_name="max",
            agent_context={
                "battle_victories": 100, "attack": 500, "defense": 500,
                "evolution_stage": "mega",
                "relationship_count": 50, "dialogue_count": 200,
                "friendship_levels": [1.0, 1.0, 1.0, 1.0],
                "regions_visited": 20, "distance_traveled": 5000.0,
                "skills_count": 20, "inventions_count": 20, "knowledge_citations": 20,
            },
            self_model=model,
            tick=10,
        )

        for dim in SELF_MODEL_DIMS:
            assert result.actual_scores[dim] >= 0.9

    def test_trajectory_capped(self):
        """轨迹长度超过上限时被裁剪。"""
        model = SelfModel(agent_name="test")
        # 快速填充轨迹
        for i in range(500):
            model.record_snapshot(i)
        # 最大长度不超过 MAX_TRAJECTORY_LENGTH
        assert len(model.trajectory) <= 200

    def test_negative_stats_clamped(self):
        """负值输入被 clamp 到 0。"""
        model = SelfModel(agent_name="neg")
        result = SelfEvaluator.evaluate(
            agent_name="neg",
            agent_context={
                "battle_victories": -10, "attack": -50, "defense": -30,
                "relationship_count": -5, "dialogue_count": -20,
            },
            self_model=model,
            tick=10,
        )
        for dim in SELF_MODEL_DIMS:
            assert 0.0 <= result.actual_scores[dim] <= 1.0
            assert result.new_self_assessment[dim] >= 0.0

    def test_introspection_interval_custom(self):
        """自定义 introspection_interval。"""
        model = SelfModel(agent_name="custom", introspection_interval=5)
        assert model.introspection_interval == 5
        model.last_introspection_tick = 0
        assert not model.should_introspect(3)
        assert model.should_introspect(5)
        assert model.should_introspect(10)

    def test_registry_step_with_custom_interval(self, registry):
        """registry 中 agent 使用自定义间隔。"""
        model = registry.get_or_create("fast")
        model.introspection_interval = 3

        # tick 3 → 应该评估
        result = registry.step("fast", {"battle_victories": 10}, tick=3)
        assert result is not None

        # tick 4 → 应跳过 (4 - 3 = 1 < 3)
        result = registry.step("fast", {"battle_victories": 10}, tick=4)
        assert result is None

        # tick 6 → 应该评估 (6 - 3 = 3 >= 3)
        result = registry.step("fast", {"battle_victories": 10}, tick=6)
        assert result is not None
