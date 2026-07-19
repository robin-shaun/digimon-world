"""人格动力学集成测试 — Phase 26 Task 2。
覆盖 FastAPI 端点 + 人格动力学引擎与世界集成。≥30 个测试。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from digimon_world.api.app import app
from digimon_world.world.personality_dynamics import (
    _DEFAULT_INFLUENCE_FACTOR,
    _MAX_DEBT_NORMALIZE,
    _SHIFT_DRIFT_THRESHOLD,
    INTERACTION_BASE_VECTORS,
    PersonalityDynamicsEngine,
    PersonalityShift,
    PersonalityVector,
    SocialInfluenceTracker,
    get_personality_dynamics_engine,
    reset_personality_dynamics_engine,
)
from digimon_world.world.personality_engine import (
    PersonalityEvolutionEngine,
    PersonalityProfile,
    reset_personality_engine,
)
from digimon_world.world.world_state import reset_world

# ===========================================================================
# 夹具
# ===========================================================================


@pytest.fixture(autouse=True)
def _reset() -> None:
    """每个测试前重置全局单例：世界 + 人格引擎 + 人格动力学引擎。"""
    reset_world()
    reset_personality_engine()
    reset_personality_dynamics_engine()
    yield
    reset_world()
    reset_personality_engine()
    reset_personality_dynamics_engine()


@pytest.fixture
def client() -> TestClient:
    """创建 FastAPI TestClient。"""
    return TestClient(app)


def _init_deterministic_vector(engine: PersonalityDynamicsEngine, name: str) -> PersonalityVector:
    """为 engine 中的 agent 预创建确定性零值向量（覆盖随机初始化）。"""
    profile = PersonalityProfile(ei=0.0, sn=0.0, tf=0.0, jp=0.0)
    engine.evolution_engine.set(name, profile)
    vec = PersonalityVector(ei=0.0, sn=0.0, tf=0.0, jp=0.0)
    engine.vectors[name] = vec
    return vec


def _dyn() -> PersonalityDynamicsEngine:
    """获取人格动力学引擎单例（用于直接操控状态）。"""
    return get_personality_dynamics_engine()


# ===========================================================================
# 1. GET /api/digimon/{name}/personality — 人格档案 + 动力学端点 (6 tests)
# ===========================================================================


class TestPersonalityEndpoint:
    """测试 /api/digimon/{name}/personality 端点。"""

    def test_personality_endpoint_returns_profile(self, client: TestClient) -> None:
        """端点返回基本人格档案（类型代码、维度值、强度）。"""
        r = client.get("/api/digimon/亚古兽/personality")
        assert r.status_code == 200
        data = r.json()

        assert data["agent_name"] == "亚古兽"
        assert "type_code" in data
        assert "type_description" in data
        assert "is_clear" in data
        assert "dominant_dimension" in data
        assert "ei" in data
        assert "sn" in data
        assert "tf" in data
        assert "jp" in data
        # Phase 26 fields
        assert "dynamics" in data
        assert "trajectory" in data
        assert "top_influencers" in data
        assert "influences_on" in data
        assert "personality_shifts" in data

    def test_personality_endpoint_includes_dynamics_after_interaction(
        self, client: TestClient
    ) -> None:
        """互动后端点返回 dynamics 向量数据。"""
        dyn = _dyn()
        # 记录 亚古兽 对 加布兽 的互动（两者都在 world 中）
        dyn.record_interaction("亚古兽", "加布兽", "dialogue", 1.0, tick=1)

        r = client.get("/api/digimon/加布兽/personality")
        assert r.status_code == 200
        data = r.json()

        assert data["dynamics"] is not None
        d = data["dynamics"]
        assert "ei" in d
        assert "sn" in d
        assert "tf" in d
        assert "jp" in d
        assert "stability_score" in d
        assert "drift_total" in d
        assert "current_type" in d
        assert "original_type" in d
        assert "drift_from_original" in d

    def test_personality_endpoint_includes_trajectory(self, client: TestClient) -> None:
        """step() 后端点返回轨迹数据。"""
        dyn = _dyn()
        # 确保 亚古兽 有确定性向量
        _init_deterministic_vector(dyn, "亚古兽")

        dyn.step(10)
        dyn.step(20)

        r = client.get("/api/digimon/亚古兽/personality")
        assert r.status_code == 200
        data = r.json()

        assert "trajectory" in data
        traj = data["trajectory"]
        assert len(traj) == 2
        assert traj[0]["tick"] == 10
        assert traj[1]["tick"] == 20
        assert "ei" in traj[0]
        assert "mbti_type" in traj[0]

    def test_personality_endpoint_includes_influencers(self, client: TestClient) -> None:
        """端点返回 top_influencers 和 influences_on。"""
        dyn = _dyn()

        dyn.record_interaction("亚古兽", "加布兽", "dialogue", 0.8, tick=1)
        dyn.record_interaction("恶魔兽", "加布兽", "battle", 0.5, tick=2)
        # 加布兽 影响 别人
        dyn.record_interaction("加布兽", "巴达兽", "help", 0.3, tick=3)

        r = client.get("/api/digimon/加布兽/personality")
        assert r.status_code == 200
        data = r.json()

        assert "top_influencers" in data
        # 亚古兽(0.8) + 恶魔兽(0.5) influenced 加布兽
        assert len(data["top_influencers"]) == 2

        assert "influences_on" in data
        assert len(data["influences_on"]) == 1
        assert data["influences_on"][0]["name"] == "巴达兽"
        assert data["influences_on"][0]["total_influence"] == pytest.approx(0.3)

    def test_personality_endpoint_includes_shifts(self, client: TestClient) -> None:
        """端点返回该 agent 的相关人格转变事件。"""
        dyn = _dyn()
        _init_deterministic_vector(dyn, "亚古兽")
        vec = dyn.get_vector("亚古兽")
        assert vec is not None

        # 强制触发类型改变 + 大漂移
        vec.ei = -0.9
        vec.sn = -0.5
        vec.tf = -0.7
        vec.jp = -0.5
        dyn.step(50)

        r = client.get("/api/digimon/亚古兽/personality")
        assert r.status_code == 200
        data = r.json()

        assert "personality_shifts" in data
        shifts = data["personality_shifts"]
        assert len(shifts) >= 1
        shift = shifts[0]
        assert "old_type" in shift
        assert "new_type" in shift
        assert "drift_distance" in shift
        assert "tick" in shift
        assert "significance" in shift

    def test_personality_endpoint_not_found(self, client: TestClient) -> None:
        """未知 agent 返回 404。"""
        r = client.get("/api/digimon/nonexistent_agent_xyz/personality")
        assert r.status_code == 404


# ===========================================================================
# 2. GET /api/personality/network — 影响力网络 API (3 tests)
# ===========================================================================


class TestNetworkEndpoint:
    """测试 /api/personality/network 端点。"""

    def test_network_endpoint_returns_structure(self, client: TestClient) -> None:
        """端点返回 nodes / edges / summary 结构。"""
        r = client.get("/api/personality/network")
        assert r.status_code == 200
        data = r.json()

        assert "nodes" in data
        assert "edges" in data
        assert "summary" in data
        assert "total_interactions" in data["summary"]
        assert "total_agents_in_network" in data["summary"]
        # nodes 应该有至少 3 个（亚古兽、加布兽等）
        assert len(data["nodes"]) >= 3

    def test_network_endpoint_after_interactions(self, client: TestClient) -> None:
        """互动后网络包含正确的边。"""
        dyn = _dyn()

        # 使用真实 world agents
        dyn.record_interaction("亚古兽", "加布兽", "dialogue", 0.8, tick=1)
        dyn.record_interaction("加布兽", "恶魔兽", "help", 0.5, tick=2)
        dyn.record_interaction("亚古兽", "恶魔兽", "battle", 0.3, tick=3)

        r = client.get("/api/personality/network")
        assert r.status_code == 200
        data = r.json()

        edges = data["edges"]
        assert len(edges) == 3
        # 亚古兽→加布兽 weight=0.8
        edge_ab = [e for e in edges if e["source"] == "亚古兽" and e["target"] == "加布兽"]
        assert len(edge_ab) == 1
        assert edge_ab[0]["weight"] == pytest.approx(0.8)

    def test_network_endpoint_empty_no_interactions(self, client: TestClient) -> None:
        """无互动时网络边为空。"""
        r = client.get("/api/personality/network")
        assert r.status_code == 200
        data = r.json()
        assert data["edges"] == []
        assert data["summary"]["total_interactions"] == 0


# ===========================================================================
# 3. GET /api/personality/shifts — 重大转变事件 API (4 tests)
# ===========================================================================


class TestShiftsEndpoint:
    """测试 /api/personality/shifts 端点。"""

    def test_shifts_endpoint_empty(self, client: TestClient) -> None:
        """无转变时返回空列表。"""
        r = client.get("/api/personality/shifts")
        assert r.status_code == 200
        data = r.json()

        assert data["shifts"] == []
        assert data["total"] == 0
        assert data["total_significant"] == 0

    def test_shifts_endpoint_with_shifts(self, client: TestClient) -> None:
        """触发人格转变后端点返回事件。"""
        dyn = _dyn()
        _init_deterministic_vector(dyn, "亚古兽")
        vec = dyn.get_vector("亚古兽")
        assert vec is not None

        vec.ei = -0.9
        vec.sn = -0.5
        vec.tf = -0.7
        vec.jp = -0.5
        dyn.step(50)

        r = client.get("/api/personality/shifts")
        assert r.status_code == 200
        data = r.json()

        assert data["total"] >= 1
        assert len(data["shifts"]) >= 1
        shift = data["shifts"][0]
        assert shift["agent_name"] == "亚古兽"
        assert "old_type" in shift
        assert "new_type" in shift
        assert "drift_distance" in shift
        assert shift["tick"] == 50
        assert shift["significance"] > 0.0

    def test_shifts_endpoint_min_significance_filter(self, client: TestClient) -> None:
        """min_significance 参数过滤低显著度转变。"""
        dyn = _dyn()
        _init_deterministic_vector(dyn, "亚古兽")
        vec = dyn.get_vector("亚古兽")
        assert vec is not None

        vec.ei = -0.9
        vec.sn = -0.5
        vec.tf = -0.7
        vec.jp = -0.5
        dyn.step(50)

        # 漂移距离 ≈ 1.37, significance ≈ 0.91 → should pass 0.5 filter
        r = client.get("/api/personality/shifts?min_significance=0.5")
        assert r.status_code == 200
        data = r.json()
        assert data["total_significant"] >= 1

        # 0.91 < 0.99 → filtered out
        r2 = client.get("/api/personality/shifts?min_significance=0.99")
        assert r2.status_code == 200
        data2 = r2.json()
        assert data2["total_significant"] == 0

    def test_shifts_endpoint_by_agent_grouping(self, client: TestClient) -> None:
        """返回 by_agent 分组。"""
        dyn = _dyn()
        _init_deterministic_vector(dyn, "亚古兽")
        _init_deterministic_vector(dyn, "加布兽")

        v1 = dyn.get_vector("亚古兽")
        v2 = dyn.get_vector("加布兽")
        assert v1 is not None and v2 is not None

        v1.ei = -0.9
        v1.sn = -0.5
        v1.tf = -0.7
        v1.jp = -0.5
        dyn.step(10)

        v2.ei = -0.9
        v2.sn = -0.5
        v2.tf = -0.7
        v2.jp = -0.5
        dyn.step(20)

        r = client.get("/api/personality/shifts")
        assert r.status_code == 200
        data = r.json()

        assert "by_agent" in data
        assert len(data["by_agent"]) == 2
        assert "亚古兽" in data["by_agent"]
        assert "加布兽" in data["by_agent"]


# ===========================================================================
# 4. PersonalityDynamicsEngine — 全部互动类型 (6 tests)
# ===========================================================================


class TestRecordInteractionAllTypes:
    """验证所有 6 种互动类型的 record_interaction。"""

    def _setup_engine(self) -> PersonalityDynamicsEngine:
        """创建独立引擎并注入确定性向量。"""
        evo = PersonalityEvolutionEngine()
        dyn = PersonalityDynamicsEngine(evolution_engine=evo)
        _init_deterministic_vector(dyn, "b")
        return dyn

    def test_record_interaction_dialogue(self) -> None:
        """对话类型: ei+0.02, tf-0.01。"""
        dyn = self._setup_engine()
        dyn.record_interaction("a", "b", "dialogue", 1.0, tick=1)
        vec = dyn.get_vector("b")
        assert vec is not None
        assert vec.ei == pytest.approx(0.02)
        assert vec.tf == pytest.approx(-0.01)

    def test_record_interaction_battle(self) -> None:
        """战斗类型: ei+0.01, tf+0.02, jp+0.01。"""
        dyn = self._setup_engine()
        dyn.record_interaction("a", "b", "battle", 1.0, tick=1)
        vec = dyn.get_vector("b")
        assert vec is not None
        assert vec.ei == pytest.approx(0.01)
        assert vec.tf == pytest.approx(0.02)
        assert vec.jp == pytest.approx(0.01)

    def test_record_interaction_help(self) -> None:
        """帮助类型: ei+0.01, tf-0.02。"""
        dyn = self._setup_engine()
        dyn.record_interaction("a", "b", "help", 1.0, tick=1)
        vec = dyn.get_vector("b")
        assert vec is not None
        assert vec.ei == pytest.approx(0.01)
        assert vec.tf == pytest.approx(-0.02)

    def test_record_interaction_trade(self) -> None:
        """交易类型: sn+0.01, jp-0.01。"""
        dyn = self._setup_engine()
        dyn.record_interaction("a", "b", "trade", 1.0, tick=1)
        vec = dyn.get_vector("b")
        assert vec is not None
        assert vec.sn == pytest.approx(0.01)
        assert vec.jp == pytest.approx(-0.01)

    def test_record_interaction_gift(self) -> None:
        """送礼类型: sn-0.01, tf-0.01。"""
        dyn = self._setup_engine()
        dyn.record_interaction("a", "b", "gift", 1.0, tick=1)
        vec = dyn.get_vector("b")
        assert vec is not None
        assert vec.sn == pytest.approx(-0.01)
        assert vec.tf == pytest.approx(-0.01)

    def test_record_interaction_wakeup(self) -> None:
        """唤醒类型: ei+0.02, tf-0.01。"""
        dyn = self._setup_engine()
        dyn.record_interaction("a", "b", "wakeup", 1.0, tick=1)
        vec = dyn.get_vector("b")
        assert vec is not None
        assert vec.ei == pytest.approx(0.02)
        assert vec.tf == pytest.approx(-0.01)


# ===========================================================================
# 5. step() 轨迹 + 转变检测 (4 tests)
# ===========================================================================


class TestStepAndTrajectory:
    """验证 step() 的轨迹和转变检测。"""

    def _setup_engine(self) -> PersonalityDynamicsEngine:
        evo = PersonalityEvolutionEngine()
        return PersonalityDynamicsEngine(evolution_engine=evo)

    def test_step_generates_trajectory_snapshots(self) -> None:
        """step() 每次调用记录一次轨迹快照。"""
        dyn = self._setup_engine()
        _init_deterministic_vector(dyn, "agent")

        dyn.step(10)
        dyn.step(20)
        dyn.step(30)

        traj = dyn.get_personality_trajectory("agent")
        assert len(traj) == 3
        assert traj[0]["tick"] == 10
        assert traj[1]["tick"] == 20
        assert traj[2]["tick"] == 30

    def test_step_detects_personality_shift(self) -> None:
        """类型改变 + 漂移 > 阈值 → 触发 PersonalityShift。"""
        dyn = self._setup_engine()
        _init_deterministic_vector(dyn, "test_agent")

        vec = dyn.get_vector("test_agent")
        assert vec is not None
        vec.ei = -0.9
        vec.sn = -0.5
        vec.tf = -0.7
        vec.jp = -0.5

        shifts = dyn.step(50)
        assert len(shifts) == 1
        shift = shifts[0]
        assert shift.agent_name == "test_agent"
        assert shift.old_type == "ESTJ"
        assert shift.new_type == "INFP"
        assert shift.drift_distance > _SHIFT_DRIFT_THRESHOLD
        assert shift.significance > 0.0

    def test_step_no_duplicate_shift(self) -> None:
        """相同类型转变不重复记录。"""
        dyn = self._setup_engine()
        _init_deterministic_vector(dyn, "agent")

        vec = dyn.get_vector("agent")
        assert vec is not None
        vec.ei = -0.9
        vec.sn = -0.5
        vec.tf = -0.7
        vec.jp = -0.5

        shifts1 = dyn.step(10)
        assert len(shifts1) == 1

        shifts2 = dyn.step(20)
        assert len(shifts2) == 0

    def test_trajectory_for_unknown_agent_returns_empty(self) -> None:
        """未知 agent 的轨迹返回空列表。"""
        dyn = self._setup_engine()
        assert dyn.get_personality_trajectory("nobody") == []


# ===========================================================================
# 6. 影响力追踪器网络分析 (5 tests)
# ===========================================================================


class TestInfluenceTrackerNetwork:
    """验证影响力追踪器网络分析。"""

    def _setup_engine(self) -> PersonalityDynamicsEngine:
        evo = PersonalityEvolutionEngine()
        return PersonalityDynamicsEngine(evolution_engine=evo)

    def test_influence_tracker_network_after_interactions(self) -> None:
        """多次互动后网络矩阵正确。"""
        dyn = self._setup_engine()
        _init_deterministic_vector(dyn, "A")
        _init_deterministic_vector(dyn, "B")
        _init_deterministic_vector(dyn, "C")

        dyn.record_interaction("A", "B", "dialogue", 0.8, tick=1)
        dyn.record_interaction("A", "B", "help", 0.2, tick=2)
        dyn.record_interaction("B", "C", "battle", 0.5, tick=3)
        dyn.record_interaction("A", "C", "trade", 0.1, tick=4)

        network = dyn.influence_tracker.get_influence_network()
        assert network["A"]["B"] == pytest.approx(1.0)  # 0.8 + 0.2
        assert network["B"]["C"] == pytest.approx(0.5)
        assert network["A"]["C"] == pytest.approx(0.1)

    def test_get_top_influencers_fewer_than_n(self) -> None:
        """记录数少于 n 时返回全部。"""
        dyn = self._setup_engine()
        _init_deterministic_vector(dyn, "target")

        dyn.record_interaction("X", "target", "dialogue", 0.5, tick=1)

        top = dyn.influence_tracker.get_top_influencers("target", n=10)
        assert len(top) == 1

    def test_get_top_influencers_returns_all_sorted(self) -> None:
        """正常情况返回所有 influencer 按影响力降序。"""
        dyn = self._setup_engine()
        _init_deterministic_vector(dyn, "target")

        dyn.record_interaction("X", "target", "dialogue", 0.1, tick=1)
        dyn.record_interaction("Y", "target", "battle", 0.8, tick=2)
        dyn.record_interaction("Z", "target", "help", 0.5, tick=3)

        top = dyn.influence_tracker.get_top_influencers("target", n=5)
        assert len(top) == 3
        assert top[0][0] == "Y"
        assert top[1][0] == "Z"
        assert top[2][0] == "X"

    def test_get_interaction_count_bidirectional(self) -> None:
        """双向互动计数正确。"""
        dyn = self._setup_engine()
        _init_deterministic_vector(dyn, "A")
        _init_deterministic_vector(dyn, "B")

        dyn.record_interaction("A", "B", "dialogue", 1.0, tick=1)
        dyn.record_interaction("B", "A", "battle", 1.0, tick=2)
        dyn.record_interaction("A", "B", "help", 1.0, tick=3)

        assert dyn.influence_tracker.get_interaction_count("A", "B") == 3
        assert dyn.influence_tracker.get_interaction_count("A", "C") == 0

    def test_get_influences_on_empty(self) -> None:
        """无记录时 get_influences_on 返回空列表。"""
        tracker = SocialInfluenceTracker()
        assert tracker.get_influences_on("nobody") == []


# ===========================================================================
# 7. 重置 + 单例 (2 tests)
# ===========================================================================


class TestResetAndSingleton:
    """验证重置和单例模式。"""

    def _setup_engine(self) -> PersonalityDynamicsEngine:
        evo = PersonalityEvolutionEngine()
        return PersonalityDynamicsEngine(evolution_engine=evo)

    def test_reset_clears_all_state(self) -> None:
        """reset() 清空所有向量、影响力记录、转变事件。"""
        dyn = self._setup_engine()
        _init_deterministic_vector(dyn, "agent")
        dyn.record_interaction("a", "b", "dialogue", 1.0, tick=1)
        dyn.shifts.append(
            PersonalityShift(
                agent_name="x",
                old_type="ESTJ",
                new_type="ISTJ",
                drift_distance=0.5,
                tick=10,
            )
        )

        dyn.reset()
        assert len(dyn.vectors) == 0
        assert len(dyn.influence_tracker) == 0
        assert len(dyn.shifts) == 0

    def test_singleton_pattern(self) -> None:
        """get_personality_dynamics_engine 返回相同单例。"""
        e1 = get_personality_dynamics_engine()
        e2 = get_personality_dynamics_engine()
        assert e1 is e2


# ===========================================================================
# 8. influence_factor + 互惠利他债务 (4 tests)
# ===========================================================================


class TestInfluenceFactor:
    """验证 influence_factor 计算（含互惠利他债务）。"""

    def _setup_engine(self) -> PersonalityDynamicsEngine:
        evo = PersonalityEvolutionEngine()
        return PersonalityDynamicsEngine(evolution_engine=evo)

    def test_influence_factor_default(self) -> None:
        """无 altruism 时默认为 1.0。"""
        dyn = self._setup_engine()
        factor = dyn._compute_influence_factor("a", "b")
        assert factor == _DEFAULT_INFLUENCE_FACTOR

    def test_influence_factor_with_debt(self) -> None:
        """有债务时 influence_factor > 1.0。"""
        dyn = self._setup_engine()
        mock = MagicMock()
        mock.get_debt.return_value = 30.0
        dyn.set_altruism(mock)

        factor = dyn._compute_influence_factor("debtor", "creditor")
        expected = 1.0 + min(1.0, 30.0 / _MAX_DEBT_NORMALIZE)
        assert factor == pytest.approx(expected)

    def test_influence_factor_max(self) -> None:
        """债务达上限时 influence_factor = 2.0。"""
        dyn = self._setup_engine()
        mock = MagicMock()
        mock.get_debt.return_value = _MAX_DEBT_NORMALIZE + 100
        dyn.set_altruism(mock)

        factor = dyn._compute_influence_factor("d", "c")
        assert factor == pytest.approx(2.0)

    def test_influence_factor_with_mock_altruism_amplifies_shift(self) -> None:
        """mock altruism 债务使交互偏移放大。"""
        dyn = self._setup_engine()
        _init_deterministic_vector(dyn, "debtor")

        mock = MagicMock()
        mock.get_debt.return_value = 25.0
        dyn.set_altruism(mock)

        dyn.record_interaction("creditor", "debtor", "dialogue", 1.0, tick=1)
        vec = dyn.get_vector("debtor")
        assert vec is not None
        # influence_factor = 1.0 + 25/50 = 1.5
        # ei = 0.02 * 1.5 = 0.03
        assert vec.ei == pytest.approx(0.03)
        mock.get_debt.assert_called_once_with("debtor", "creditor")


# ===========================================================================
# 9. 向量夹紧 + 累积 + 缩放 (4 tests)
# ===========================================================================


class TestVectorClampAndAccumulate:
    """验证向量夹紧和累积。"""

    def _setup_engine(self) -> PersonalityDynamicsEngine:
        evo = PersonalityEvolutionEngine()
        return PersonalityDynamicsEngine(evolution_engine=evo)

    def test_personality_vector_clamp_upper(self) -> None:
        """维度值被夹紧在 1.0。"""
        dyn = self._setup_engine()
        _init_deterministic_vector(dyn, "b")

        vec = dyn.get_vector("b")
        assert vec is not None
        vec.ei = 0.995
        dyn.record_interaction("a", "b", "dialogue", 1.0, tick=1)
        assert vec.ei == pytest.approx(1.0)

    def test_personality_vector_clamp_lower(self) -> None:
        """维度值被夹紧在 -1.0。"""
        dyn = self._setup_engine()
        _init_deterministic_vector(dyn, "b")

        vec = dyn.get_vector("b")
        assert vec is not None
        vec.tf = -0.995
        dyn.record_interaction("a", "b", "help", 1.0, tick=1)  # tf -0.02
        assert vec.tf == pytest.approx(-1.0)

    def test_multiple_accumulated_interactions(self) -> None:
        """多次互动累积漂移。"""
        dyn = self._setup_engine()
        _init_deterministic_vector(dyn, "b")

        for _ in range(5):
            dyn.record_interaction("a", "b", "dialogue", 1.0, tick=1)
        vec = dyn.get_vector("b")
        assert vec is not None
        assert vec.ei == pytest.approx(0.10)
        assert vec.tf == pytest.approx(-0.05)
        assert vec.drift_total > 0.0

    def test_magnitude_scales_effect(self) -> None:
        """magnitude 参数缩放偏移量。"""
        dyn = self._setup_engine()
        _init_deterministic_vector(dyn, "b")

        dyn.record_interaction("a", "b", "dialogue", 0.5, tick=1)
        vec = dyn.get_vector("b")
        assert vec is not None
        assert vec.ei == pytest.approx(0.01)
        assert vec.tf == pytest.approx(-0.005)


# ===========================================================================
# 10. 稳定性 (3 tests)
# ===========================================================================


class TestStability:
    """验证稳定性计算。"""

    def _setup_engine(self) -> PersonalityDynamicsEngine:
        evo = PersonalityEvolutionEngine()
        return PersonalityDynamicsEngine(evolution_engine=evo)

    def test_stability_computation_high(self) -> None:
        """一致的小幅漂移 → 稳定性接近 1.0。"""
        dyn = self._setup_engine()
        vec = dyn.get_or_create_vector("agent")
        vec._recent_shift_magnitudes = [0.005, 0.005, 0.005, 0.005, 0.005]
        dyn.step(10)
        assert vec.stability_score == pytest.approx(1.0)

    def test_stability_computation_low(self) -> None:
        """波动大的漂移 → 稳定性下降。"""
        dyn = self._setup_engine()
        vec = dyn.get_or_create_vector("agent")
        vec._recent_shift_magnitudes = [
            0.01, 0.05, 0.001, 0.08, 0.02, 0.06, 0.001, 0.09, 0.01, 0.07,
        ]
        dyn.step(10)
        assert vec.stability_score < 1.0

    def test_stability_stays_in_zero_to_one(self) -> None:
        """稳定性始终在 [0, 1] 范围内。"""
        dyn = self._setup_engine()
        vec = dyn.get_or_create_vector("agent")
        vec._recent_shift_magnitudes = [
            0.5, 0.001, 0.5, 0.001, 0.5, 0.001, 0.5, 0.001, 0.5, 0.001,
        ]
        dyn.step(10)
        assert 0.0 <= vec.stability_score <= 1.0


# ===========================================================================
# 11. 基向量 + 向量生命周期 (5 tests)
# ===========================================================================


class TestBaseVectorsAndVectorLifecycle:
    """验证基向量定义和向量生命周期。"""

    def _setup_engine(self) -> PersonalityDynamicsEngine:
        evo = PersonalityEvolutionEngine()
        return PersonalityDynamicsEngine(evolution_engine=evo)

    def test_all_six_interaction_base_vectors_defined(self) -> None:
        """所有 6 种互动类型的基向量均已定义。"""
        expected = {"dialogue", "battle", "help", "trade", "gift", "wakeup"}
        assert set(INTERACTION_BASE_VECTORS.keys()) == expected

    def test_each_base_vector_has_all_dims(self) -> None:
        """每种基向量包含全部 4 维。"""
        for itype, vec in INTERACTION_BASE_VECTORS.items():
            for dim in ("ei", "sn", "tf", "jp"):
                assert dim in vec, f"{itype} missing {dim}"

    def test_get_or_create_vector_returns_same_instance(self) -> None:
        """多次调用 get_or_create_vector 返回同一实例。"""
        dyn = self._setup_engine()
        _init_deterministic_vector(dyn, "agent")
        vec1 = dyn.get_or_create_vector("agent")
        vec2 = dyn.get_or_create_vector("agent")
        assert vec1 is vec2

    def test_get_or_create_vector_creates_new(self) -> None:
        """首次调用 get_or_create_vector 创建向量。"""
        dyn = self._setup_engine()
        assert "new_agent" not in dyn.vectors
        vec = dyn.get_or_create_vector("new_agent")
        assert vec is not None
        assert "new_agent" in dyn.vectors

    def test_profile_sync_after_interaction(self) -> None:
        """互动后底层 profile 与 vector 保持同步。"""
        dyn = self._setup_engine()
        _init_deterministic_vector(dyn, "b")

        dyn.record_interaction("a", "b", "dialogue", 1.0, tick=1)
        profile = dyn.evolution_engine.get("b")
        assert profile is not None
        vec = dyn.get_vector("b")
        assert vec is not None
        assert profile.ei == pytest.approx(vec.ei)
        assert profile.tf == pytest.approx(vec.tf)
