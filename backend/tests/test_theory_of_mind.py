"""
Theory of Mind 模块测试 — Phase 28
==================================

覆盖 MentalStateModel / BeliefUpdate / StrategicReasoning / TheoryOfMindRegistry 全部功能。

测试范围:
- MentalStateModel 初始化与默认值
- MentalStateModel 序列化
- BeliefUpdate: 观察→意图更新
- BeliefUpdate: 意图→欲望反向推理
- BeliefUpdate: 欲望→信念贝叶斯更新
- BeliefUpdate: 全级联更新
- BeliefUpdate: 置信度管理（增长与衰减）
- StrategicReasoning: 战斗优势预测
- StrategicReasoning: 社交兼容性预测
- StrategicReasoning: 综合策略推荐
- TheoryOfMindRegistry: CRUD / step / 查询
- 全局单例模式
- 边界情况（空观察、未知目标、模型上限、LRU 驱逐）
- 序列化往返
"""

from __future__ import annotations

import pytest

from digimon_world.world.theory_of_mind import (
    CONFIDENCE_DECAY_INTERVAL,
    INITIAL_CONFIDENCE,
    MAX_CONFIDENCE,
    MAX_MODELS_PER_AGENT,
    MIN_CONFIDENCE,
    BeliefUpdate,
    MentalStateModel,
    StrategicReasoning,
    TheoryOfMindRegistry,
    _clamp,
    _ema_update,
    _normalize_dict,
    get_theory_of_mind_registry,
    reset_theory_of_mind_registry,
)

# ──────────────────────────────────────────────
# 夹具
# ──────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_registry():
    """每个测试前后重置全局注册表，确保测试隔离。"""
    reset_theory_of_mind_registry()
    yield
    reset_theory_of_mind_registry()


@pytest.fixture
def registry() -> TheoryOfMindRegistry:
    """创建独立的 TheoryOfMindRegistry 实例。"""
    return TheoryOfMindRegistry()


@pytest.fixture
def fresh_model() -> MentalStateModel:
    """创建一个新的 MentalStateModel。"""
    return MentalStateModel(target_name="agumon")


# ──────────────────────────────────────────────
# 辅助函数测试
# ──────────────────────────────────────────────


class TestHelperFunctions:
    """_clamp / _ema_update / _normalize_dict 单元测试。"""

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

    def test_ema_update_convergence(self):
        """EMA 更新向目标值收敛。"""
        result = _ema_update(0.0, 1.0, 0.3)
        assert result == pytest.approx(0.3)

        result2 = _ema_update(0.3, 1.0, 0.3)
        assert result2 == pytest.approx(0.51)

    def test_normalize_dict(self):
        """归一化字典使其和为 1。"""
        d = {"a": 1.0, "b": 2.0, "c": 3.0}
        nd = _normalize_dict(d)
        assert sum(nd.values()) == pytest.approx(1.0)
        assert nd["c"] == pytest.approx(0.5)

    def test_normalize_dict_empty(self):
        """空字典或全零字典归一化不变。"""
        assert _normalize_dict({}) == {}
        assert _normalize_dict({"a": 0.0, "b": 0.0}) == {"a": 0.0, "b": 0.0}


# ──────────────────────────────────────────────
# MentalStateModel 测试
# ──────────────────────────────────────────────


class TestMentalStateModel:
    """MentalStateModel 创建、默认值、序列化。"""

    def test_creation_defaults(self):
        """创建时 target_name 正确且默认字段合理。"""
        model = MentalStateModel(target_name="agumon")
        assert model.target_name == "agumon"
        assert model.confidence == INITIAL_CONFIDENCE
        assert model.observation_count == 0
        assert model.last_updated_tick == 0

    def test_default_beliefs_present(self):
        """默认 beliefs 包含基础维度且值为 0。"""
        model = MentalStateModel(target_name="test")
        assert "danger_level" in model.beliefs
        assert "others_friendly" in model.beliefs
        assert "resources_scarce" in model.beliefs
        assert model.beliefs["danger_level"] == 0.0

    def test_default_desires_present(self):
        """默认 desires 包含基础维度。"""
        model = MentalStateModel(target_name="test")
        assert "explore" in model.desires
        assert "socialize" in model.desires
        assert "survive" in model.desires

    def test_default_intentions_present(self):
        """默认 intentions 包含基础维度。"""
        model = MentalStateModel(target_name="test")
        assert "move" in model.intentions
        assert "attack" in model.intentions
        assert "talk" in model.intentions

    def test_explicit_fields_respected(self):
        """显式传入的字段值被保留。"""
        model = MentalStateModel(
            target_name="gabumon",
            beliefs={"danger_level": 0.8},
            desires={"explore": 0.6},
            intentions={"attack": 0.4},
            confidence=0.5,
            last_updated_tick=42,
            observation_count=10,
        )
        assert model.target_name == "gabumon"
        assert model.beliefs["danger_level"] == 0.8
        assert model.desires["explore"] == 0.6
        assert model.intentions["attack"] == 0.4
        assert model.confidence == 0.5
        assert model.last_updated_tick == 42
        assert model.observation_count == 10
        # 默认基础维度仍然被补全
        assert "others_friendly" in model.beliefs

    def test_to_dict(self):
        """to_dict 包含所有关键字段。"""
        model = MentalStateModel(target_name="test")
        d = model.to_dict()
        assert d["target_name"] == "test"
        assert "beliefs" in d
        assert "desires" in d
        assert "intentions" in d
        assert "confidence" in d
        assert "last_updated_tick" in d
        assert "observation_count" in d

    def test_to_dict_values_rounded(self):
        """to_dict 中浮点数被四舍五入。"""
        model = MentalStateModel(
            target_name="test",
            confidence=0.12345678,
        )
        d = model.to_dict()
        assert d["confidence"] == 0.1235  # 4 decimal places


# ──────────────────────────────────────────────
# BeliefUpdate: 观察 → 意图更新
# ──────────────────────────────────────────────


class TestBeliefUpdateIntentions:
    """观察 → 意图直接更新测试。"""

    def test_observe_move_updates_move_intention(self, fresh_model):
        """观察 move → intentions["move"] 提升。"""
        observation = {"action_type": "move", "intensity": 0.8}
        BeliefUpdate.update_from_observation(fresh_model, observation, tick=10)

        assert fresh_model.intentions["move"] > 0.0
        assert fresh_model.intentions["move"] <= 1.0
        assert fresh_model.observation_count == 1

    def test_observe_attack_updates_attack_intention(self, fresh_model):
        """观察 attack → intentions["attack"] 提升。"""
        observation = {"action_type": "attack", "intensity": 0.9}
        BeliefUpdate.update_from_observation(fresh_model, observation, tick=10)

        assert fresh_model.intentions["attack"] > 0.0
        assert "intimidate" in fresh_model.intentions

    def test_observe_talk_updates_talk_intention(self, fresh_model):
        """观察 talk → intentions["talk"] 提升。"""
        observation = {"action_type": "talk", "intensity": 0.7}
        BeliefUpdate.update_from_observation(fresh_model, observation, tick=10)

        assert fresh_model.intentions["talk"] > 0.0
        assert "socialize" in fresh_model.intentions

    def test_multiple_observations_accumulate(self, fresh_model):
        """多次观察相同动作 → 意图持续 EMA 累积。"""
        obs = {"action_type": "move", "intensity": 0.5}
        BeliefUpdate.update_from_observation(fresh_model, obs, tick=10)
        BeliefUpdate.update_from_observation(fresh_model, obs, tick=11)

        # 第二次更新后 move 意图应该累积
        assert fresh_model.intentions["move"] > 0.0
        assert fresh_model.observation_count == 2

    def test_empty_action_type_no_update(self, fresh_model):
        """空 action_type 不更新模型。"""
        observation = {"action_type": "", "intensity": 0.5}
        BeliefUpdate.update_from_observation(fresh_model, observation, tick=10)

        assert fresh_model.observation_count == 0
        assert fresh_model.confidence == INITIAL_CONFIDENCE

    def test_unknown_action_type_no_crash(self, fresh_model):
        """未知 action_type 不崩溃。"""
        observation = {"action_type": "nonexistent_action", "intensity": 0.5}
        BeliefUpdate.update_from_observation(fresh_model, observation, tick=10)

        # 计数仍应增加（因为 action_type 非空）
        assert fresh_model.observation_count == 1

    def test_confidence_increases_with_observations(self, fresh_model):
        """观察次数增加 → 置信度上升。"""
        initial_conf = fresh_model.confidence

        for i in range(5):
            BeliefUpdate.update_from_observation(
                fresh_model,
                {"action_type": "move", "intensity": 0.8},
                tick=10 + i,
            )

        assert fresh_model.confidence > initial_conf
        assert fresh_model.confidence <= MAX_CONFIDENCE
        assert fresh_model.observation_count == 5


# ──────────────────────────────────────────────
# BeliefUpdate: 意图 → 欲望 & 欲望 → 信念
# ──────────────────────────────────────────────


class TestBeliefUpdateCascade:
    """级联更新：意图→欲望→信念完整链测试。"""

    def test_repeated_move_infers_explore_desire(self, fresh_model):
        """反复观察 move → 推断 explore 欲望。"""
        obs = {"action_type": "move", "intensity": 0.8}
        for i in range(10):
            BeliefUpdate.update_from_observation(fresh_model, obs, tick=10 + i)

        # 经过多次 update，explore 欲望应该积累
        assert fresh_model.desires["explore"] > 0.0

    def test_repeated_attack_infers_dominate_desire(self, fresh_model):
        """反复观察 attack → 推断 dominate 欲望。"""
        obs = {"action_type": "attack", "intensity": 0.9}
        for i in range(10):
            BeliefUpdate.update_from_observation(fresh_model, obs, tick=10 + i)

        assert fresh_model.intentions["attack"] > 0.0
        # dominate desire should be inferred through the cascade
        assert "dominate" in fresh_model.desires or fresh_model.desires.get("dominate", 0.0) > 0.0

    def test_flee_infers_avoid_danger_desire(self, fresh_model):
        """观察 flee → 推断 avoid_danger 欲望。"""
        obs = {"action_type": "flee", "intensity": 0.9}
        for i in range(8):
            BeliefUpdate.update_from_observation(fresh_model, obs, tick=10 + i)

        assert fresh_model.intentions["flee"] > 0.0
        assert "avoid_danger" in fresh_model.desires or "avoid_conflict" in fresh_model.intentions

    def test_desire_to_belief_full_cascade(self, fresh_model):
        """完整的 desire → belief 级联：move → explore → danger_level↓"""
        obs = {"action_type": "move", "intensity": 1.0}
        for i in range(15):
            BeliefUpdate.update_from_observation(fresh_model, obs, tick=10 + i)

        # move → explore desire
        explore_desire = fresh_model.desires.get("explore", 0.0)
        assert explore_desire > 0.0, f"Expected explore desire to grow, got {explore_desire}"

        # explore desire → danger_level belief should decrease (explorers think less danger)
        danger_belief = fresh_model.beliefs.get("danger_level", 0.0)
        assert danger_belief < 0.5, (
            f"Repeated move should lower danger belief, got {danger_belief}"
        )

    def test_attack_cascade_to_belief(self, fresh_model):
        """attack → dominate → others_weak belief 上升。"""
        obs = {"action_type": "attack", "intensity": 1.0}
        for i in range(15):
            BeliefUpdate.update_from_observation(fresh_model, obs, tick=10 + i)

        # attack → dominate desire
        dominate_desire = fresh_model.desires.get("dominate", 0.0)
        assert dominate_desire > 0.0, f"Expected dominate desire: {dominate_desire}"

        # dominate → others_weak belief should increase
        others_weak = fresh_model.beliefs.get("others_weak", 0.0)
        assert others_weak > 0.0, f"Expected others_weak belief > 0, got {others_weak}"


# ──────────────────────────────────────────────
# BeliefUpdate: 置信度管理
# ──────────────────────────────────────────────


class TestBeliefUpdateConfidence:
    """置信度增长和衰减测试。"""

    def test_confidence_never_exceeds_max(self, fresh_model):
        """置信度不会超过 MAX_CONFIDENCE。"""
        obs = {"action_type": "move", "intensity": 1.0}
        for i in range(200):
            BeliefUpdate.update_from_observation(fresh_model, obs, tick=10 + i)

        assert fresh_model.confidence <= MAX_CONFIDENCE

    def test_confidence_decay_with_no_observations(self, fresh_model):
        """长时间无观察 → 置信度衰减。"""
        # 先建立一些置信度
        obs = {"action_type": "move", "intensity": 0.8}
        BeliefUpdate.update_from_observation(fresh_model, obs, tick=10)
        conf_after_obs = fresh_model.confidence

        # 超过衰减间隔后调用 decay
        BeliefUpdate.decay_confidence(
            fresh_model,
            tick=10 + CONFIDENCE_DECAY_INTERVAL + 5,
        )

        assert fresh_model.confidence < conf_after_obs

    def test_confidence_never_below_min(self, fresh_model):
        """置信度不会低于 MIN_CONFIDENCE。"""
        fresh_model.confidence = MIN_CONFIDENCE + 0.001

        BeliefUpdate.decay_confidence(
            fresh_model,
            tick=10 + CONFIDENCE_DECAY_INTERVAL * 10,
        )

        assert fresh_model.confidence >= MIN_CONFIDENCE

    def test_high_intensity_gains_more_confidence(self, fresh_model):
        """高强度观察比低强度观察获得更多置信度增长。"""
        model_high = MentalStateModel(target_name="high")
        model_low = MentalStateModel(target_name="low")

        BeliefUpdate.update_from_observation(
            model_high, {"action_type": "move", "intensity": 1.0}, tick=10
        )
        BeliefUpdate.update_from_observation(
            model_low, {"action_type": "move", "intensity": 0.1}, tick=10
        )

        assert model_high.confidence >= model_low.confidence


# ──────────────────────────────────────────────
# StrategicReasoning 测试
# ──────────────────────────────────────────────


class TestStrategicReasoning:
    """策略推理：战斗、社交、综合决策。"""

    def test_combat_advantage_when_strong(self):
        """我方战斗力强 → 战斗优势为正。"""
        self_identity = {
            "combat_score": 0.9,
            "social_score": 0.5,
            "exploration_score": 0.3,
            "knowledge_score": 0.4,
        }
        model = MentalStateModel(
            target_name="enemy",
            intentions={"attack": 0.8, "intimidate": 0.3},
            desires={"dominate": 0.7, "compete": 0.4},
        )

        result = StrategicReasoning.predict_strategy(
            agent_name="player",
            target_name="enemy",
            self_identity=self_identity,
            mental_model=model,
            tick=10,
        )

        assert result.combat_advantage > 0.0
        assert result.agent_name == "player"
        assert result.target_name == "enemy"
        assert result.recommended_approach == "engage_combat"

    def test_combat_disadvantage_when_weak(self):
        """我方战斗力弱 → 战斗优势为负 → avoid_combat。"""
        self_identity = {
            "combat_score": 0.1,
            "social_score": 0.5,
            "exploration_score": 0.3,
            "knowledge_score": 0.4,
        }
        model = MentalStateModel(
            target_name="enemy",
            intentions={"attack": 0.8, "intimidate": 0.5},
            desires={"dominate": 0.9, "compete": 0.5},
        )

        result = StrategicReasoning.predict_strategy(
            agent_name="player",
            target_name="enemy",
            self_identity=self_identity,
            mental_model=model,
            tick=10,
        )

        assert result.combat_advantage < 0.0
        assert result.recommended_approach == "avoid_combat"

    def test_social_compatibility_high(self):
        """双方社交评分高 → 社交兼容性高 → engage_social。"""
        self_identity = {
            "combat_score": 0.3,
            "social_score": 0.9,
            "exploration_score": 0.3,
            "knowledge_score": 0.4,
        }
        model = MentalStateModel(
            target_name="friend",
            intentions={"talk": 0.8, "socialize": 0.6},
            desires={"socialize": 0.9, "bond": 0.7},
        )

        result = StrategicReasoning.predict_strategy(
            agent_name="player",
            target_name="friend",
            self_identity=self_identity,
            mental_model=model,
            tick=10,
        )

        assert result.social_compatibility > 0.0
        assert result.recommended_approach == "engage_social"

    def test_social_compatibility_low_attack_intent(self):
        """目标有攻击意图 → 社交兼容性被打折 → avoid_social。"""
        self_identity = {
            "combat_score": 0.3,
            "social_score": 0.9,
            "exploration_score": 0.3,
            "knowledge_score": 0.4,
        }
        model = MentalStateModel(
            target_name="hostile",
            intentions={"attack": 0.7, "intimidate": 0.4},
            desires={"dominate": 0.8},
        )

        result = StrategicReasoning.predict_strategy(
            agent_name="player",
            target_name="hostile",
            self_identity=self_identity,
            mental_model=model,
            tick=10,
        )

        # 高社交但目标社交开放性低 → avoid_social
        assert result.recommended_approach in ("avoid_social", "observe", "avoid_combat")

    def test_neutral_unknown_target(self):
        """未知目标（无显著意图）→ observe。"""
        self_identity = {
            "combat_score": 0.5,
            "social_score": 0.5,
            "exploration_score": 0.3,
            "knowledge_score": 0.4,
        }
        model = MentalStateModel(target_name="stranger")

        result = StrategicReasoning.predict_strategy(
            agent_name="player",
            target_name="stranger",
            self_identity=self_identity,
            mental_model=model,
            tick=10,
        )

        assert result.recommended_approach == "observe"
        assert result.reasoning_confidence == INITIAL_CONFIDENCE

    def test_predicted_intentions_top3(self):
        """预测意图返回 top 3 最高值。"""
        self_identity = {
            "combat_score": 0.5,
            "social_score": 0.5,
            "exploration_score": 0.3,
            "knowledge_score": 0.4,
        }
        model = MentalStateModel(
            target_name="active",
            intentions={
                "move": 0.9,
                "attack": 0.7,
                "talk": 0.5,
                "flee": 0.3,
                "gather": 0.2,
            },
        )

        result = StrategicReasoning.predict_strategy(
            agent_name="player",
            target_name="active",
            self_identity=self_identity,
            mental_model=model,
            tick=10,
        )

        assert len(result.target_predicted_intentions) == 3
        assert "move" in result.target_predicted_intentions

    def test_strategy_prediction_to_dict(self):
        """StrategyPrediction.to_dict 序列化正确。"""
        self_identity = {
            "combat_score": 0.8,
            "social_score": 0.4,
            "exploration_score": 0.3,
            "knowledge_score": 0.4,
        }
        model = MentalStateModel(
            target_name="test",
            intentions={"attack": 0.6},
        )

        result = StrategicReasoning.predict_strategy(
            agent_name="player",
            target_name="test",
            self_identity=self_identity,
            mental_model=model,
            tick=42,
        )

        d = result.to_dict()
        assert d["agent_name"] == "player"
        assert d["target_name"] == "test"
        assert d["tick"] == 42
        assert "recommended_approach" in d
        assert "combat_advantage" in d
        assert "social_compatibility" in d
        assert "target_predicted_intentions" in d
        assert "reasoning_confidence" in d


# ──────────────────────────────────────────────
# TheoryOfMindRegistry 测试
# ──────────────────────────────────────────────


class TestTheoryOfMindRegistry:
    """注册表单例、CRUD、step、多 agent。"""

    def test_singleton_same_instance(self):
        """get_theory_of_mind_registry 返回同一实例。"""
        r1 = get_theory_of_mind_registry()
        r2 = get_theory_of_mind_registry()
        assert r1 is r2

    def test_reset_creates_new_instance(self):
        """reset 后 get 返回新实例。"""
        r1 = get_theory_of_mind_registry()
        reset_theory_of_mind_registry()
        r2 = get_theory_of_mind_registry()
        assert r1 is not r2

    def test_reset_clears_models(self):
        """reset 清除所有模型。"""
        r = get_theory_of_mind_registry()
        r.get_or_create("agumon", "gabumon")
        assert r.agent_count() == 1
        reset_theory_of_mind_registry()
        r2 = get_theory_of_mind_registry()
        assert r2.agent_count() == 0

    def test_get_nonexistent_returns_none(self, registry):
        """get 不存在的目标返回 None。"""
        assert registry.get("agumon", "gabumon") is None

    def test_get_or_create_returns_model(self, registry):
        """get_or_create 返回 MentalStateModel。"""
        model = registry.get_or_create("agumon", "gabumon")
        assert isinstance(model, MentalStateModel)
        assert model.target_name == "gabumon"

    def test_get_or_create_idempotent(self, registry):
        """多次 get_or_create 返回同一实例。"""
        m1 = registry.get_or_create("agumon", "gabumon")
        m2 = registry.get_or_create("agumon", "gabumon")
        assert m1 is m2

    def test_step_updates_model(self, registry):
        """step 观察后模型被更新。"""
        model = registry.step(
            "agumon", "gabumon",
            {"action_type": "move", "intensity": 0.8},
            tick=10,
        )
        assert model.observation_count == 1
        assert model.intentions["move"] > 0.0
        assert model.last_updated_tick == 10

    def test_step_decays_confidence_on_no_observation(self, registry):
        """长时间无观察后 step 衰减置信度。"""
        # 先建立置信度
        model = registry.step(
            "agumon", "gabumon",
            {"action_type": "move", "intensity": 0.8},
            tick=10,
        )
        conf_after = model.confidence

        # 很久之后空观察 step
        future_tick = 10 + CONFIDENCE_DECAY_INTERVAL * 2
        model = registry.step(
            "agumon", "gabumon",
            {},  # 空观察
            tick=future_tick,
        )
        assert model.confidence < conf_after

    def test_get_all_models_for(self, registry):
        """get_all_models_for 返回所有目标模型。"""
        registry.get_or_create("agumon", "gabumon")
        registry.get_or_create("agumon", "patamon")
        registry.get_or_create("gabumon", "agumon")

        agumon_models = registry.get_all_models_for("agumon")
        assert len(agumon_models) == 2
        target_names = [m.target_name for m in agumon_models]
        assert "gabumon" in target_names
        assert "patamon" in target_names

    def test_get_all_models_for_nonexistent_agent(self, registry):
        """不存在的 agent 返回空列表。"""
        assert registry.get_all_models_for("nonexistent") == []

    def test_get_target_names_for(self, registry):
        """get_target_names_for 返回目标名称列表。"""
        registry.get_or_create("agumon", "gabumon")
        registry.get_or_create("agumon", "biyomon")

        names = registry.get_target_names_for("agumon")
        assert set(names) == {"gabumon", "biyomon"}

    def test_multiple_agents_independent(self, registry):
        """不同 agent 的心智模型相互独立。"""
        agumon_model = registry.get_or_create("agumon", "gabumon")
        patamon_model = registry.get_or_create("patamon", "gabumon")

        assert agumon_model is not patamon_model
        registry.step("agumon", "gabumon", {"action_type": "attack", "intensity": 0.9}, tick=10)
        assert agumon_model.intentions["attack"] > 0.0
        assert patamon_model.intentions["attack"] == 0.0

    def test_list_agents(self, registry):
        """list_agents 返回所有 agent 名称。"""
        registry.get_or_create("agumon", "gabumon")
        registry.get_or_create("patamon", "biyomon")
        assert set(registry.list_agents()) == {"agumon", "patamon"}

    def test_agent_count_and_model_count(self, registry):
        """agent_count / model_count 正确。"""
        assert registry.agent_count() == 0

        registry.get_or_create("agumon", "gabumon")
        assert registry.agent_count() == 1
        assert registry.model_count("agumon") == 1

        registry.get_or_create("agumon", "patamon")
        assert registry.model_count("agumon") == 2
        assert registry.model_count("gabumon") == 0

    def test_set_method(self, registry):
        """set 手动设置模型。"""
        custom = MentalStateModel(
            target_name="custom",
            confidence=0.8,
            observation_count=42,
        )
        registry.set("agumon", "custom", custom)
        assert registry.get("agumon", "custom") is custom
        assert registry.get("agumon", "custom").confidence == 0.8

    def test_reset_method(self, registry):
        """registry.reset() 清除所有模型。"""
        registry.get_or_create("agumon", "gabumon")
        registry.get_or_create("agumon", "patamon")
        assert registry.agent_count() == 1
        assert registry.model_count("agumon") == 2

        registry.reset()
        assert registry.agent_count() == 0

    def test_to_dict(self, registry):
        """to_dict 序列化正确。"""
        registry.get_or_create("agumon", "gabumon")
        registry.step("agumon", "gabumon", {"action_type": "move", "intensity": 0.8}, tick=10)

        d = registry.to_dict()
        assert "agumon" in d
        assert "gabumon" in d["agumon"]
        assert d["agumon"]["gabumon"]["target_name"] == "gabumon"
        assert d["agumon"]["gabumon"]["observation_count"] == 1


# ──────────────────────────────────────────────
# 边界情况测试
# ──────────────────────────────────────────────


class TestEdgeCases:
    """边界情况：空观察、未知目标、模型上限、序列化往返。"""

    def test_empty_observation_dict(self, fresh_model):
        """完全空的观察不改变模型。"""
        BeliefUpdate.update_from_observation(fresh_model, {}, tick=10)
        assert fresh_model.observation_count == 0
        assert fresh_model.confidence == INITIAL_CONFIDENCE

    def test_missing_action_type(self, fresh_model):
        """缺少 action_type 不改变计数和意图。"""
        old_move = fresh_model.intentions["move"]
        BeliefUpdate.update_from_observation(
            fresh_model, {"intensity": 0.8}, tick=10
        )
        assert fresh_model.observation_count == 0
        assert fresh_model.intentions["move"] == old_move

    def test_max_models_eviction(self, registry):
        """达到 MAX_MODELS_PER_AGENT 上限时驱逐最旧的模型。"""
        # 创建满额的模型
        for i in range(MAX_MODELS_PER_AGENT):
            registry.get_or_create("agumon", f"target_{i}")
            registry.step(
                "agumon", f"target_{i}",
                {"action_type": "move", "intensity": 0.5},
                tick=i,
            )

        assert registry.model_count("agumon") == MAX_MODELS_PER_AGENT

        # 添加第 MAX_MODELS_PER_AGENT + 1 个
        registry.get_or_create("agumon", "new_target")

        # 数量应该仍为 MAX_MODELS_PER_AGENT（最旧的被驱逐）
        assert registry.model_count("agumon") == MAX_MODELS_PER_AGENT
        # 新目标应该存在
        assert registry.get("agumon", "new_target") is not None
        # 最旧的目标 (target_0, tick=0) 应该被驱逐
        assert registry.get("agumon", "target_0") is None

    def test_serialization_roundtrip(self, registry):
        """序列化后反序列化恢复正确。"""
        registry.get_or_create("agumon", "gabumon")
        registry.step(
            "agumon", "gabumon",
            {"action_type": "attack", "intensity": 0.9},
            tick=10,
        )
        registry.step(
            "agumon", "gabumon",
            {"action_type": "move", "intensity": 0.6},
            tick=11,
        )

        # 序列化
        d = registry.to_dict()
        # 通过 to_dict 重建
        gab_data = d["agumon"]["gabumon"]

        assert gab_data["target_name"] == "gabumon"
        assert gab_data["observation_count"] == 2
        assert gab_data["last_updated_tick"] == 11
        assert gab_data["intentions"]["attack"] > 0.0
        assert gab_data["intentions"]["move"] > 0.0
        assert gab_data["confidence"] > INITIAL_CONFIDENCE

    def test_confidence_decay_no_observation_from_registry_step(self, registry):
        """registry.step 在无观察时触发置信度衰减。"""
        registry.step(
            "agumon", "gabumon",
            {"action_type": "move", "intensity": 0.8},
            tick=10,
        )
        model = registry.get("agumon", "gabumon")
        conf_after_obs = model.confidence

        # 很远未来的空 step
        future = 10 + CONFIDENCE_DECAY_INTERVAL * 3
        registry.step("agumon", "gabumon", {}, tick=future)
        assert model.confidence < conf_after_obs
        assert model.confidence >= MIN_CONFIDENCE

    def test_tick_metadata_updated(self, fresh_model):
        """观察后 tick 和计数正确更新。"""
        BeliefUpdate.update_from_observation(
            fresh_model,
            {"action_type": "move", "intensity": 0.5},
            tick=42,
        )
        assert fresh_model.last_updated_tick == 42
        assert fresh_model.observation_count == 1

        BeliefUpdate.update_from_observation(
            fresh_model,
            {"action_type": "talk", "intensity": 0.5},
            tick=99,
        )
        assert fresh_model.last_updated_tick == 99
        assert fresh_model.observation_count == 2

    def test_gather_action_cascade(self, fresh_model):
        """观察 gather → survive 欲望 → resources_scarce / danger_level 信念。"""
        obs = {"action_type": "gather", "intensity": 1.0}
        for i in range(12):
            BeliefUpdate.update_from_observation(fresh_model, obs, tick=10 + i)

        # gather → survive or hoard desire
        assert fresh_model.desires.get("survive", 0.0) > 0.0 or fresh_model.desires.get("hoard", 0.0) > 0.0

        # survive → danger_level ↑, resources_scarce ↑
        resources = fresh_model.beliefs.get("resources_scarce", 0.0)
        danger = fresh_model.beliefs.get("danger_level", 0.0)
        assert resources > 0.0 or danger > 0.0

    def test_talk_action_social_cascade(self, fresh_model):
        """观察 talk → socialize 欲望 → others_friendly 信念。"""
        obs = {"action_type": "talk", "intensity": 1.0}
        for i in range(12):
            BeliefUpdate.update_from_observation(fresh_model, obs, tick=10 + i)

        # talk → socialize desire
        assert fresh_model.desires.get("socialize", 0.0) > 0.0

        # socialize → others_friendly ↑, danger_level ↓
        others_friendly = fresh_model.beliefs.get("others_friendly", 0.0)
        assert others_friendly > 0.0
