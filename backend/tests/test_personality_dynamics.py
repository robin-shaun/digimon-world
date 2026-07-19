"""人格动力学测试 — Phase 26 Task 1。

覆盖 SocialInfluence / PersonalityVector / PersonalityDynamicsEngine 全部功能。
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock

import pytest

from digimon_world.world.personality_dynamics import (
    _DEFAULT_INFLUENCE_FACTOR,
    _MAX_DEBT_NORMALIZE,
    _SHIFT_DRIFT_THRESHOLD,
    INTERACTION_BASE_VECTORS,
    PersonalityDynamicsEngine,
    PersonalityShift,
    PersonalityVector,
    SocialInfluenceRecord,
    SocialInfluenceTracker,
    get_personality_dynamics_engine,
    reset_personality_dynamics_engine,
)
from digimon_world.world.personality_engine import (
    PersonalityEvolutionEngine,
    PersonalityProfile,
    reset_personality_engine,
)

# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_engines():
    """每个测试前重置全局单例。"""
    reset_personality_dynamics_engine()
    reset_personality_engine()
    yield
    reset_personality_dynamics_engine()
    reset_personality_engine()


@pytest.fixture
def engine() -> PersonalityDynamicsEngine:
    """创建独立的人格动力学引擎（确定性初始人格）。"""
    evo = PersonalityEvolutionEngine()
    dyn = PersonalityDynamicsEngine(evolution_engine=evo)
    # 为 agent "b" 预创建零值向量（跳过随机初始化）
    _init_deterministic_vector(dyn, "b")
    return dyn


def _init_deterministic_vector(engine: PersonalityDynamicsEngine, name: str) -> PersonalityVector:
    """创建确定性零值人格向量（避免随机初始化干扰测试）。"""
    profile = PersonalityProfile(ei=0.0, sn=0.0, tf=0.0, jp=0.0)
    engine.evolution_engine.set(name, profile)
    vec = PersonalityVector(ei=0.0, sn=0.0, tf=0.0, jp=0.0)
    engine.vectors[name] = vec
    return vec


def _ensure_deterministic(engine: PersonalityDynamicsEngine, *names: str) -> None:
    """确保指定 agent 拥有确定性零值向量。"""
    for name in names:
        if name not in engine.vectors:
            _init_deterministic_vector(engine, name)


@pytest.fixture
def tracker() -> SocialInfluenceTracker:
    """创建空的社会影响力追踪器。"""
    return SocialInfluenceTracker()


@pytest.fixture
def sample_profile() -> PersonalityProfile:
    """创建一个示例人格档案。"""
    return PersonalityProfile(ei=0.5, sn=-0.3, tf=0.7, jp=-0.2)


# ---------------------------------------------------------------------------
# PersonalityVector 测试 (10)
# ---------------------------------------------------------------------------

class TestPersonalityVector:
    """PersonalityVector 创建、距离、漂移、类型推导。"""

    def test_create_default(self):
        """默认创建：全零，原始值记录正确。"""
        vec = PersonalityVector()
        assert vec.ei == 0.0
        assert vec.sn == 0.0
        assert vec.tf == 0.0
        assert vec.jp == 0.0
        assert vec.stability_score == 1.0
        assert vec.drift_total == 0.0
        assert vec.original_type == "ESTJ"  # 0 → positive
        assert vec.original_values == {"ei": 0.0, "sn": 0.0, "tf": 0.0, "jp": 0.0}

    def test_create_with_values(self):
        """指定值创建。"""
        vec = PersonalityVector(ei=0.8, sn=-0.5, tf=-0.3, jp=0.6)
        assert vec.ei == 0.8
        assert vec.sn == -0.5
        assert vec.tf == -0.3
        assert vec.jp == 0.6
        assert vec.original_values["ei"] == 0.8
        assert vec.original_type == "ENFJ"

    def test_from_personality_profile(self, sample_profile):
        """从 PersonalityProfile 工厂方法创建。"""
        vec = PersonalityVector.from_personality_profile(sample_profile)
        assert vec.ei == 0.5
        assert vec.sn == -0.3
        assert vec.tf == 0.7
        assert vec.jp == -0.2
        assert vec.original_type == "ENTP"
        assert vec.original_values["ei"] == 0.5

    def test_to_dict(self):
        """to_dict 包含所有关键字段。"""
        vec = PersonalityVector(ei=0.5, sn=-0.3, tf=0.7, jp=-0.1)
        d = vec.to_dict()
        assert d["ei"] == 0.5
        assert d["sn"] == -0.3
        assert d["tf"] == 0.7
        assert d["jp"] == -0.1
        assert d["current_type"] == "ENTP"
        assert d["original_type"] == "ENTP"
        assert "stability_score" in d
        assert "drift_total" in d
        assert "drift_from_original" in d
        assert "original_values" in d

    def test_distance_to_same(self):
        """同向量距离为 0。"""
        a = PersonalityVector(ei=0.5, sn=0.3, tf=-0.2, jp=0.1)
        b = PersonalityVector(ei=0.5, sn=0.3, tf=-0.2, jp=0.1)
        assert a.distance_to(b) == pytest.approx(0.0)

    def test_distance_to_different(self):
        """不同向量的欧几里得距离。"""
        a = PersonalityVector(ei=0.0, sn=0.0, tf=0.0, jp=0.0)
        b = PersonalityVector(ei=1.0, sn=0.0, tf=0.0, jp=0.0)
        assert a.distance_to(b) == pytest.approx(1.0)

        c = PersonalityVector(ei=1.0, sn=1.0, tf=0.0, jp=0.0)
        assert a.distance_to(c) == pytest.approx(math.sqrt(2.0))

    def test_distance_to_opposite(self):
        """完全相反向量的距离。"""
        a = PersonalityVector(ei=1.0, sn=1.0, tf=1.0, jp=1.0)
        b = PersonalityVector(ei=-1.0, sn=-1.0, tf=-1.0, jp=-1.0)
        # 每个维度差 2.0, 四个维度: sqrt(4*4) = 4.0
        assert a.distance_to(b) == pytest.approx(4.0)

    def test_drift_from_original_zero(self):
        """初始漂移为 0。"""
        vec = PersonalityVector(ei=0.5, sn=0.3, tf=-0.2, jp=0.1)
        assert vec.drift_from_original() == pytest.approx(0.0)

    def test_drift_from_original_after_shift(self):
        """应用偏移后漂移距离增加。"""
        vec = PersonalityVector(ei=0.5, sn=0.3, tf=-0.2, jp=0.1)
        vec._apply_shifts({"ei": 0.1, "sn": -0.05, "tf": 0.0, "jp": 0.0}, 0.12)
        # drift 应该 > 0
        assert vec.drift_from_original() > 0.0
        # 漂移应接近 sqrt(0.1^2 + 0.05^2)
        expected_drift = math.sqrt(0.1**2 + 0.05**2)
        assert vec.drift_from_original() == pytest.approx(expected_drift, abs=1e-4)

    def test_mbti_type_all_positive(self):
        """全正向 → ESTJ。"""
        vec = PersonalityVector(ei=0.5, sn=0.3, tf=0.2, jp=0.1)
        assert vec.mbti_type() == "ESTJ"

    def test_mbti_type_all_negative(self):
        """全负向 → INFP。"""
        vec = PersonalityVector(ei=-0.5, sn=-0.3, tf=-0.2, jp=-0.1)
        assert vec.mbti_type() == "INFP"

    def test_mbti_type_mixed(self):
        """混合类型。"""
        vec = PersonalityVector(ei=0.8, sn=-0.7, tf=0.6, jp=-0.9)
        assert vec.mbti_type() == "ENTP"


# ---------------------------------------------------------------------------
# SocialInfluenceRecord 测试 (3)
# ---------------------------------------------------------------------------

class TestSocialInfluenceRecord:
    """SocialInfluenceRecord 创建与属性。"""

    def test_record_creation(self):
        """基本创建。"""
        rec = SocialInfluenceRecord(
            influencer_name="agumon",
            influenced_name="gabumon",
            interaction_type="dialogue",
            magnitude=0.8,
            dimension_shifts={"ei": 0.016, "tf": -0.008},
            tick=100,
        )
        assert rec.influencer_name == "agumon"
        assert rec.influenced_name == "gabumon"
        assert rec.interaction_type == "dialogue"
        assert rec.magnitude == 0.8
        assert rec.dimension_shifts == {"ei": 0.016, "tf": -0.008}
        assert rec.tick == 100
        assert rec.timestamp != ""

    def test_record_auto_timestamp(self):
        """自动生成时间戳。"""
        rec = SocialInfluenceRecord(
            influencer_name="a",
            influenced_name="b",
            interaction_type="battle",
            magnitude=0.5,
            dimension_shifts={"ei": 0.01},
            tick=1,
        )
        assert rec.timestamp  # 非空
        assert "T" in rec.timestamp  # ISO 格式

    def test_record_explicit_timestamp(self):
        """显式传入时间戳。"""
        rec = SocialInfluenceRecord(
            influencer_name="a",
            influenced_name="b",
            interaction_type="help",
            magnitude=0.3,
            dimension_shifts={},
            tick=5,
            timestamp="2025-01-01T00:00:00Z",
        )
        assert rec.timestamp == "2025-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# SocialInfluenceTracker 测试 (6)
# ---------------------------------------------------------------------------

class TestSocialInfluenceTracker:
    """SocialInfluenceTracker 记录/查询/网络。"""

    def _make_record(self, inf: str, infd: str, itype: str = "dialogue", mag: float = 0.5) -> SocialInfluenceRecord:
        return SocialInfluenceRecord(
            influencer_name=inf,
            influenced_name=infd,
            interaction_type=itype,
            magnitude=mag,
            dimension_shifts={},
            tick=1,
        )

    def test_add_and_get_influences_on(self, tracker):
        """添加记录后可通过 get_influences_on 查询。"""
        r1 = self._make_record("agumon", "gabumon", mag=0.3)
        r2 = self._make_record("patamon", "gabumon", mag=0.7)
        r3 = self._make_record("gabumon", "agumon", mag=0.5)
        tracker.add_record(r1)
        tracker.add_record(r2)
        tracker.add_record(r3)

        results = tracker.get_influences_on("gabumon")
        assert len(results) == 2
        assert results[0].influencer_name == "agumon"
        assert results[1].influencer_name == "patamon"

    def test_get_influences_on_empty(self, tracker):
        """无记录时返回空列表。"""
        assert tracker.get_influences_on("nobody") == []

    def test_get_influence_network(self, tracker):
        """影响力矩阵正确构建。"""
        tracker.add_record(self._make_record("A", "B", mag=0.3))
        tracker.add_record(self._make_record("A", "B", mag=0.2))
        tracker.add_record(self._make_record("B", "C", mag=0.5))
        tracker.add_record(self._make_record("A", "C", mag=0.1))

        net = tracker.get_influence_network()
        assert net["A"]["B"] == pytest.approx(0.5)
        assert net["B"]["C"] == pytest.approx(0.5)
        assert net["A"]["C"] == pytest.approx(0.1)

    def test_get_top_influencers(self, tracker):
        """按影响力降序返回 top N。"""
        tracker.add_record(self._make_record("X", "target", mag=0.1))
        tracker.add_record(self._make_record("Y", "target", mag=0.8))
        tracker.add_record(self._make_record("Z", "target", mag=0.5))
        tracker.add_record(self._make_record("Y", "target", mag=0.1))

        top = tracker.get_top_influencers("target", n=2)
        assert len(top) == 2
        assert top[0][0] == "Y"
        assert top[0][1] == pytest.approx(0.9)  # 0.8 + 0.1
        assert top[1][0] == "Z"

    def test_get_top_influencers_fewer_than_n(self, tracker):
        """当记录数少于 n 时返回全部。"""
        tracker.add_record(self._make_record("X", "target", mag=0.5))
        top = tracker.get_top_influencers("target", n=10)
        assert len(top) == 1

    def test_get_interaction_count(self, tracker):
        """双向互动计数。"""
        tracker.add_record(self._make_record("A", "B"))
        tracker.add_record(self._make_record("B", "A"))
        tracker.add_record(self._make_record("A", "B"))
        assert tracker.get_interaction_count("A", "B") == 3
        assert tracker.get_interaction_count("A", "C") == 0


# ---------------------------------------------------------------------------
# PersonalityDynamicsEngine.get_or_create_vector 测试 (2)
# ---------------------------------------------------------------------------

class TestGetOrCreateVector:
    """向量生命周期管理。"""

    def test_get_or_create_vector_new(self, engine):
        """为新 agent 自动创建向量。"""
        vec = engine.get_or_create_vector("new_agent")
        assert vec is not None
        assert "new_agent" in engine.vectors
        assert vec.original_type == vec.mbti_type()

    def test_get_or_create_vector_existing(self, engine):
        """已有向量时返回同一实例。"""
        vec1 = engine.get_or_create_vector("agent")
        vec2 = engine.get_or_create_vector("agent")
        assert vec1 is vec2

    def test_get_vector_returns_none_for_unknown(self, engine):
        """未知 agent 返回 None。"""
        assert engine.get_vector("ghost") is None


# ---------------------------------------------------------------------------
# PersonalityDynamicsEngine.record_interaction 测试 (10)
# ---------------------------------------------------------------------------

class TestRecordInteraction:
    """record_interaction 各互动类型 + 边界。"""

    def test_record_interaction_basic(self, engine):
        """基本互动记录。"""
        rec = engine.record_interaction("agumon", "gabumon", "dialogue", 0.5, tick=10)
        assert rec.influencer_name == "agumon"
        assert rec.influenced_name == "gabumon"
        assert rec.interaction_type == "dialogue"
        assert rec.magnitude == 0.5
        assert rec.tick == 10
        assert "ei" in rec.dimension_shifts
        # 验证追踪器有记录
        assert len(engine.influence_tracker) >= 1

    def test_record_interaction_affects_vector(self, engine):
        """互动影响被影响方的向量值。"""
        vec_before = engine.get_or_create_vector("gabumon")
        ei_before = vec_before.ei

        engine.record_interaction("agumon", "gabumon", "dialogue", 1.0, tick=1)
        # dialogue: ei +0.02, tf -0.01
        assert vec_before.ei > ei_before  # 增加了
        assert vec_before.drift_total > 0.0

    def test_record_interaction_dialogue(self, engine):
        """对话类型: ei+0.02, tf-0.01 (mag=1.0)。"""
        engine.record_interaction("a", "b", "dialogue", 1.0, tick=1)
        vec = engine.get_vector("b")
        # magnitude=1.0, influence_factor=1.0 → ei+0.02, tf-0.01
        assert vec.ei == pytest.approx(0.02)
        assert vec.tf == pytest.approx(-0.01)

    def test_record_interaction_battle(self, engine):
        """战斗类型: ei+0.01, tf+0.02, jp+0.01。"""
        engine.record_interaction("a", "b", "battle", 1.0, tick=1)
        vec = engine.get_vector("b")
        assert vec.ei == pytest.approx(0.01)
        assert vec.tf == pytest.approx(0.02)
        assert vec.jp == pytest.approx(0.01)

    def test_record_interaction_help(self, engine):
        """帮助类型: ei+0.01, tf-0.02。"""
        engine.record_interaction("a", "b", "help", 1.0, tick=1)
        vec = engine.get_vector("b")
        assert vec.ei == pytest.approx(0.01)
        assert vec.tf == pytest.approx(-0.02)

    def test_record_interaction_trade(self, engine):
        """交易类型: sn+0.01, jp-0.01。"""
        engine.record_interaction("a", "b", "trade", 1.0, tick=1)
        vec = engine.get_vector("b")
        assert vec.sn == pytest.approx(0.01)
        assert vec.jp == pytest.approx(-0.01)

    def test_record_interaction_gift(self, engine):
        """送礼类型: sn-0.01, tf-0.01。"""
        engine.record_interaction("a", "b", "gift", 1.0, tick=1)
        vec = engine.get_vector("b")
        assert vec.sn == pytest.approx(-0.01)
        assert vec.tf == pytest.approx(-0.01)

    def test_record_interaction_wakeup(self, engine):
        """唤醒类型: ei+0.02, tf-0.01。"""
        engine.record_interaction("a", "b", "wakeup", 1.0, tick=1)
        vec = engine.get_vector("b")
        assert vec.ei == pytest.approx(0.02)
        assert vec.tf == pytest.approx(-0.01)

    def test_record_interaction_unknown_type_raises(self, engine):
        """未知互动类型抛出 ValueError。"""
        with pytest.raises(ValueError, match="未知互动类型"):
            engine.record_interaction("a", "b", "nonexistent", 1.0, tick=1)

    def test_record_interaction_magnitude_effect(self, engine):
        """magnitude 缩放效果。"""
        engine.record_interaction("a", "b", "dialogue", 0.5, tick=1)
        vec = engine.get_vector("b")
        # 0.5 × 0.02 = 0.01
        assert vec.ei == pytest.approx(0.01)
        assert vec.tf == pytest.approx(-0.005)

    def test_record_interaction_clamps_dimensions(self, engine):
        """维度值被限制在 [-1, 1]。"""
        vec = engine.get_or_create_vector("b")
        vec.ei = 0.995
        # dialogue ei+0.02 会超过 1.0，应被 clamp
        engine.record_interaction("a", "b", "dialogue", 1.0, tick=1)
        assert vec.ei == pytest.approx(1.0)

        vec.ei = -0.995
        # wakeup ei+0.02 但是先要把负值拉回来? 不对, wakeup 是正向
        # 我们需要一个负向偏移来测试 clamp
        # 手动设置后再测试别的方向...
        # 直接用 _apply_shifts 测试
        vec._apply_shifts({"ei": -0.5}, 0.5)
        assert vec.ei == pytest.approx(-1.0)

    def test_record_interaction_with_mock_altruism(self, engine):
        """有 ReciprocalAltruism 债务时 influence_factor 增大。"""
        _ensure_deterministic(engine, "debtor")
        mock_altruism = MagicMock()
        mock_altruism.get_debt.return_value = 25.0  # 欠 25
        engine.set_altruism(mock_altruism)

        engine.record_interaction("creditor", "debtor", "dialogue", 1.0, tick=1)
        vec = engine.get_vector("debtor")
        # influence_factor = 1.0 + 25/50 = 1.5
        # ei = 0.02 * 1.5 = 0.03
        assert vec.ei == pytest.approx(0.03)
        mock_altruism.get_debt.assert_called_once_with("debtor", "creditor")

    def test_record_interaction_multiple_accumulate(self, engine):
        """多次互动累积漂移。"""
        for _ in range(5):
            engine.record_interaction("a", "b", "dialogue", 1.0, tick=1)
        vec = engine.get_vector("b")
        # 5 × 0.02 = 0.10
        assert vec.ei == pytest.approx(0.10)
        # 5 × -0.01 = -0.05
        assert vec.tf == pytest.approx(-0.05)
        assert vec.drift_total > 0.0


# ---------------------------------------------------------------------------
# PersonalityDynamicsEngine.step + PersonalityShift 测试 (7)
# ---------------------------------------------------------------------------

class TestStepAndShift:
    """step() 稳定性计算 + 重大转变检测。"""

    def test_step_computes_stability_low(self, engine):
        """多次大幅漂移 → 稳定性下降。"""
        vec = engine.get_or_create_vector("agent")
        # 施加多次不同幅度的漂移
        vec._apply_shifts({"ei": 0.05, "sn": 0.01, "tf": 0.0, "jp": 0.0}, 0.051)
        vec._apply_shifts({"ei": -0.1, "sn": 0.0, "tf": 0.0, "jp": 0.0}, 0.1)
        vec._apply_shifts({"ei": 0.02, "sn": 0.0, "tf": -0.03, "jp": 0.0}, 0.036)
        vec._apply_shifts({"ei": 0.08, "sn": 0.0, "tf": 0.0, "jp": 0.0}, 0.08)
        vec._apply_shifts({"ei": -0.04, "sn": 0.0, "tf": 0.0, "jp": 0.01}, 0.041)

        engine.step(10)
        # 经过多次不同幅度漂移，稳定性应 < 1.0
        assert vec.stability_score < 1.0

    def test_step_computes_stability_high(self, engine):
        """少量小幅漂移 → 稳定性保持高位。"""
        vec = engine.get_or_create_vector("agent")
        vec._apply_shifts({"ei": 0.005, "sn": 0.0, "tf": 0.0, "jp": 0.0}, 0.005)
        vec._apply_shifts({"ei": 0.005, "sn": 0.0, "tf": 0.0, "jp": 0.0}, 0.005)

        engine.step(10)
        # 漂移幅度非常一致（标准差接近 0）→ 稳定性接近 1.0
        assert vec.stability_score == pytest.approx(1.0)

    def test_step_no_shift_when_drift_below_threshold(self, engine):
        """漂移距离 < 阈值 → 不触发转变。"""
        _ensure_deterministic(engine, "agent")
        vec = engine.get_vector("agent")
        # 小幅漂移（距原始 0.0 不远），不触发类型变化
        vec.ei = 0.15  # 距 0.0 的漂移 sqrt(0.15^2+0.1^2+0.1^2+0.05^2) ≈ 0.21 < 0.3
        vec.sn = -0.1
        vec.tf = 0.1
        vec.jp = -0.05
        # 类型应为 ESTJ (全0时) → 现在 ei=0.15>0(E), sn=-0.1<0(N), tf=0.1>0(T), jp=-0.05<0(P) → ENTP
        # 但 drift_from_original ≈ 0.21 < 0.3, 不触发 shift

        shifts = engine.step(10)
        assert len(shifts) == 0
        assert len(engine.shifts) == 0

    def test_step_detects_shift_when_type_changes(self, engine):
        """跨 MBTI 类型 + 漂移 > 阈值 → 触发 PersonalityShift。"""
        _ensure_deterministic(engine, "test_agent")
        vec = engine.get_vector("test_agent")
        # 原始为 ESTJ (全0)，设置值使类型改变且漂移 > 0.3
        vec.ei = -0.8   # E→I
        vec.sn = -0.3   # S→N
        vec.tf = -0.7   # T→F
        vec.jp = -0.5   # J→P
        # 新类型: I N F P = INFP ≠ ESTJ
        # drift = sqrt(0.8^2+0.3^2+0.7^2+0.5^2) = sqrt(0.64+0.09+0.49+0.25) = sqrt(1.47) ≈ 1.21 > 0.3

        shifts = engine.step(50)
        assert len(shifts) == 1
        shift = shifts[0]
        assert shift.agent_name == "test_agent"
        assert shift.old_type == "ESTJ"
        assert shift.new_type == "INFP"
        assert shift.drift_distance > _SHIFT_DRIFT_THRESHOLD
        assert shift.significance > 0.0

    def test_step_no_shift_when_type_unchanged(self, engine):
        """类型未改变 → 不触发转变（即使漂移大）。"""
        _ensure_deterministic(engine, "agent")
        vec = engine.get_vector("agent")
        # 原始为 ESTJ (全0)，设置同类型但极端值: E S T J
        vec.ei = 0.9
        vec.sn = 0.9
        vec.tf = 0.9
        vec.jp = 0.9
        # 类型仍为 ESTJ
        assert vec.mbti_type() == "ESTJ"
        # 漂移距离: sqrt(0.9^2 * 4) = 1.8 > 0.3 但类型未变

        shifts = engine.step(10)
        for s in shifts:
            assert s.agent_name != "agent"

    def test_step_avoids_duplicate_shift(self, engine):
        """相同类型转变不重复记录。"""
        _ensure_deterministic(engine, "agent")
        vec = engine.get_vector("agent")
        # 手动触发类型改变: ESTJ → INFP
        vec.ei = -0.9
        vec.sn = -0.5
        vec.tf = -0.7
        vec.jp = -0.5

        # 第一次 step
        shifts1 = engine.step(10)
        assert len(shifts1) == 1  # ESTJ → INFP

        # 第二次 step（类型未再变）
        shifts2 = engine.step(20)
        assert len(shifts2) == 0  # 类型未再改变

    def test_step_records_trajectory_snapshot(self, engine):
        """step 记录轨迹快照。"""
        engine.get_or_create_vector("agent")
        engine.step(10)
        engine.step(20)

        traj = engine.get_personality_trajectory("agent")
        assert len(traj) == 2
        assert traj[0]["tick"] == 10
        assert traj[1]["tick"] == 20
        assert "ei" in traj[0]
        assert "mbti_type" in traj[0]

    def test_trajectory_unknown_agent(self, engine):
        """未知 agent 返回空列表。"""
        assert engine.get_personality_trajectory("nobody") == []


# ---------------------------------------------------------------------------
# 边界 / 集成 / 单例 测试 (7)
# ---------------------------------------------------------------------------

class TestBoundaryAndIntegration:
    """边界条件、集成、单例。"""

    def test_influence_factor_default(self, engine):
        """无 altruism 时 influence_factor 为 1.0。"""
        factor = engine._compute_influence_factor("a", "b")
        assert factor == _DEFAULT_INFLUENCE_FACTOR

    def test_influence_factor_with_debt(self, engine):
        """有债务时 influence_factor > 1.0。"""
        mock = MagicMock()
        mock.get_debt.return_value = 30.0
        engine.set_altruism(mock)

        factor = engine._compute_influence_factor("debtor", "creditor")
        expected = 1.0 + min(1.0, 30.0 / _MAX_DEBT_NORMALIZE)
        assert factor == pytest.approx(expected)

    def test_influence_factor_max(self, engine):
        """债务达到上限时 influence_factor = 2.0。"""
        mock = MagicMock()
        mock.get_debt.return_value = _MAX_DEBT_NORMALIZE + 100  # 远超上限
        engine.set_altruism(mock)

        factor = engine._compute_influence_factor("d", "c")
        assert factor == pytest.approx(2.0)

    def test_profile_sync_after_interaction(self, engine):
        """互动后底层 profile 同步更新。"""
        engine.record_interaction("a", "b", "dialogue", 1.0, tick=1)
        profile = engine.evolution_engine.get("b")
        assert profile is not None
        # profile 的值应与 vector 一致
        vec = engine.get_vector("b")
        assert profile.ei == pytest.approx(vec.ei)
        assert profile.tf == pytest.approx(vec.tf)

    def test_singleton_pattern(self):
        """get_personality_dynamics_engine 返回单例。"""
        e1 = get_personality_dynamics_engine()
        e2 = get_personality_dynamics_engine()
        assert e1 is e2

    def test_reset(self, engine):
        """reset 清空所有状态。"""
        engine.get_or_create_vector("agent")
        engine.record_interaction("a", "b", "dialogue", 1.0, tick=1)
        engine.shifts.append(PersonalityShift(
            agent_name="x", old_type="ESTJ", new_type="ISTJ",
            drift_distance=0.5, tick=10,
        ))

        engine.reset()
        assert len(engine.vectors) == 0
        assert len(engine.influence_tracker) == 0
        assert len(engine.shifts) == 0

    def test_all_interaction_types_have_base_vectors(self):
        """所有 6 种互动类型均有定义。"""
        expected = {"dialogue", "battle", "help", "trade", "gift", "wakeup"}
        assert set(INTERACTION_BASE_VECTORS.keys()) == expected

    def test_stability_clamped_zero_to_one(self, engine):
        """稳定性始终在 [0, 1] 范围内。"""
        vec = engine.get_or_create_vector("agent")
        # 手动注入极端漂移值
        vec._recent_shift_magnitudes = [0.5, 0.001, 0.5, 0.001, 0.5, 0.001, 0.5, 0.001, 0.5, 0.001]
        engine.step(10)
        assert 0.0 <= vec.stability_score <= 1.0


# ---------------------------------------------------------------------------
# INTERACTION_BASE_VECTORS 常量验证
# ---------------------------------------------------------------------------

class TestInteractionBaseVectors:
    """验证基向量定义的正确性。"""

    def test_dialogue_vector(self):
        base = INTERACTION_BASE_VECTORS["dialogue"]
        assert base["ei"] == 0.02
        assert base["tf"] == -0.01

    def test_battle_vector(self):
        base = INTERACTION_BASE_VECTORS["battle"]
        assert base["ei"] == 0.01
        assert base["tf"] == 0.02
        assert base["jp"] == 0.01

    def test_help_vector(self):
        base = INTERACTION_BASE_VECTORS["help"]
        assert base["ei"] == 0.01
        assert base["tf"] == -0.02

    def test_trade_vector(self):
        base = INTERACTION_BASE_VECTORS["trade"]
        assert base["sn"] == 0.01
        assert base["jp"] == -0.01

    def test_gift_vector(self):
        base = INTERACTION_BASE_VECTORS["gift"]
        assert base["sn"] == -0.01
        assert base["tf"] == -0.01

    def test_wakeup_vector(self):
        base = INTERACTION_BASE_VECTORS["wakeup"]
        assert base["ei"] == 0.02
        assert base["tf"] == -0.01
