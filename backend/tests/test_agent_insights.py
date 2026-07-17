"""
Phase 21: Agent 内省聚合仪表板 — 单元测试 + 集成测试
====================================================

测试覆盖:
- AgentInsightEngine 评分计算 (memory_health_score / plan_success_rate / world_model_maturity)
- AgentInsightEngine.assess() 完整聚合
- 缺少系统的降级处理
- 全局单例 get_insight_engine() / reset_insight_engine()
- API 端点 GET /api/digimon/{name}/insights
- API 端点 404 处理
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from digimon_world.agents.agent_insights import (
    AgentInsightEngine,
    get_insight_engine,
    reset_insight_engine,
)


# ──────────────────────────────────────────────
# 全局单例
# ──────────────────────────────────────────────


class TestGlobalSingleton:
    """全局单例模式。"""

    def test_get_returns_same_instance(self):
        reset_insight_engine()
        engine1 = get_insight_engine()
        engine2 = get_insight_engine()
        assert engine1 is engine2

    def test_reset_creates_new_instance(self):
        reset_insight_engine()
        engine1 = get_insight_engine()
        reset_insight_engine()
        engine2 = get_insight_engine()
        assert engine1 is not engine2


# ──────────────────────────────────────────────
# 评分计算
# ──────────────────────────────────────────────


class TestScoringCalculations:
    """评分算法单元测试。"""

    def test_memory_health_score_perfect(self):
        engine = AgentInsightEngine("test_agent")
        diagnosis = {
            "total_memories": 50,
            "strong_count": 45,
            "weak_count": 3,
            "stale_count": 2,
            "forgetting_half_life_hours": 24,
        }
        score = engine.memory_health_score(diagnosis)
        # (45/50)*70 + 30 = 63 + 30 = 93
        assert 85 <= score <= 100
        assert isinstance(score, float)

    def test_memory_health_score_empty(self):
        engine = AgentInsightEngine("test_agent")
        diagnosis = {
            "total_memories": 0,
            "strong_count": 0,
            "weak_count": 0,
            "stale_count": 0,
            "forgetting_half_life_hours": 24,
        }
        score = engine.memory_health_score(diagnosis)
        assert score == 0.0  # no memories = base score

    def test_memory_health_score_all_weak(self):
        engine = AgentInsightEngine("test_agent")
        diagnosis = {
            "total_memories": 20,
            "strong_count": 0,
            "weak_count": 15,
            "stale_count": 5,
            "forgetting_half_life_hours": 24,
        }
        score = engine.memory_health_score(diagnosis)
        assert 0 <= score <= 40  # should be low

    def test_plan_success_rate_all_completed(self):
        engine = AgentInsightEngine("test_agent")
        history = [
            type("FakePlan", (), {"status": type("S", (), {"name": "COMPLETED"})()}),
            type("FakePlan", (), {"status": type("S", (), {"name": "COMPLETED"})()}),
            type("FakePlan", (), {"status": type("S", (), {"name": "COMPLETED"})()}),
        ]
        result = engine.plan_success_rate(history)
        assert result["completed"] == 3
        assert result["total"] == 3
        assert result["success_rate"] == 1.0

    def test_plan_success_rate_mixed(self):
        engine = AgentInsightEngine("test_agent")
        history = [
            type("FakePlan", (), {"status": type("S", (), {"name": "COMPLETED"})()}),
            type("FakePlan", (), {"status": type("S", (), {"name": "ABANDONED"})()}),
            type("FakePlan", (), {"status": type("S", (), {"name": "COMPLETED"})()}),
            type("FakePlan", (), {"status": type("S", (), {"name": "ACTIVE"})()}),
        ]
        result = engine.plan_success_rate(history)
        assert result["completed"] == 2
        assert result["abandoned"] == 1
        assert result["active"] == 1
        assert result["total"] == 4
        assert result["success_rate"] == 0.5

    def test_plan_success_rate_empty(self):
        engine = AgentInsightEngine("test_agent")
        result = engine.plan_success_rate([])
        assert result["completed"] == 0
        assert result["total"] == 0
        assert result["success_rate"] == 0.0

    def test_world_model_maturity_high(self):
        engine = AgentInsightEngine("test_agent")
        snapshot = {
            "rules_count": 6,
            "episodes_count": 80,
            "avg_confidence": 0.75,
        }
        score = engine.world_model_maturity(snapshot)
        # rules: 6 * 15 = 90, episodes: 80 * 0.5 = 40, total = 130 → cap 100
        assert score == 100.0

    def test_world_model_maturity_low(self):
        engine = AgentInsightEngine("test_agent")
        snapshot = {
            "rules_count": 1,
            "episodes_count": 10,
            "avg_confidence": 0.3,
        }
        score = engine.world_model_maturity(snapshot)
        # 1*15 + 10*0.5 = 20
        assert 15 <= score <= 25

    def test_world_model_maturity_empty(self):
        engine = AgentInsightEngine("test_agent")
        snapshot = {
            "rules_count": 0,
            "episodes_count": 0,
            "avg_confidence": 0.0,
        }
        score = engine.world_model_maturity(snapshot)
        assert score == 0.0


# ──────────────────────────────────────────────
# assess() 聚合测试
# ──────────────────────────────────────────────


class TestAssess:
    """assess() 完整聚合测试。"""

    def test_assess_full(self):
        """三个系统都存在时返回完整报告。"""
        engine = AgentInsightEngine("亚古兽")

        # Mock MemoryAutonomy
        class MockMemoryAutonomy:
            def diagnose(self):
                return {
                    "status": "healthy",
                    "total_memories": 45,
                    "strong_count": 25,
                    "weak_count": 15,
                    "stale_count": 5,
                    "forgetting_half_life_hours": 24,
                    "top_weak": [
                        {"content": "路过创始村", "strength": 0.25},
                        {"content": "吃了一颗果实", "strength": 0.18},
                    ],
                }

        # Mock PlanPersistenceEngine
        class MockPlanEngine:
            def get_history(self, agent_name):
                return [
                    type("P", (), {"status": type("S", (), {"name": "COMPLETED"})()}),
                    type("P", (), {"status": type("S", (), {"name": "COMPLETED"})()}),
                    type("P", (), {"status": type("S", (), {"name": "COMPLETED"})()}),
                    type("P", (), {"status": type("S", (), {"name": "ABANDONED"})()}),
                    type("P", (), {"status": type("S", (), {"name": "ACTIVE"})()}),
                ]

        # Mock WorldModel
        class MockWorldModel:
            def get_snapshot(self):
                return {
                    "rules_count": 4,
                    "episodes_count": 60,
                    "avg_confidence": 0.65,
                }

        report = engine.assess(MockMemoryAutonomy(), MockPlanEngine(), MockWorldModel())

        assert report["agent_name"] == "亚古兽"
        assert "timestamp" in report
        assert "overall_score" in report
        assert isinstance(report["overall_score"], (int, float))

        dims = report["dimensions"]
        assert "memory_health" in dims
        assert "plan_execution" in dims
        assert "world_model" in dims

        # memory_health
        mh = dims["memory_health"]
        assert "score" in mh
        assert mh["details"]["total"] == 45
        assert mh["details"]["strong"] == 25
        assert "top_weak" in mh

        # plan_execution
        pe = dims["plan_execution"]
        assert pe["details"]["completed"] == 3
        assert pe["details"]["active"] == 1

        # world_model
        wm = dims["world_model"]
        assert wm["details"]["rules_count"] == 4
        assert wm["details"]["episodes_count"] == 60

    def test_assess_with_missing_system(self):
        """当某个系统为 None 时，该维度为 None，不影响其他维度。"""
        engine = AgentInsightEngine("测试兽")

        report = engine.assess(None, None, None)
        assert report["agent_name"] == "测试兽"
        assert report["overall_score"] == 0.0

        dims = report["dimensions"]
        assert dims["memory_health"] is None
        assert dims["plan_execution"] is None
        assert dims["world_model"] is None

    def test_assess_partial_systems(self):
        """部分系统缺失时只聚合可用的。"""
        engine = AgentInsightEngine("部分兽")

        class MockMemory:
            def diagnose(self):
                return {
                    "status": "ok",
                    "total_memories": 30,
                    "strong_count": 20,
                    "weak_count": 8,
                    "stale_count": 2,
                    "forgetting_half_life_hours": 24,
                    "top_weak": [],
                }

        report = engine.assess(MockMemory(), None, None)
        assert report["dimensions"]["memory_health"] is not None
        assert report["dimensions"]["plan_execution"] is None
        assert report["dimensions"]["world_model"] is None
        assert report["overall_score"] > 0  # only memory dimension contributes


# ──────────────────────────────────────────────
# API 端点测试
# ──────────────────────────────────────────────


class TestInsightsAPI:
    """GET /api/digimon/{name}/insights 端点测试。"""

    def test_insights_endpoint_returns_200(self):
        """已知 agent 应返回 200。"""
        from digimon_world.api.app import app
        from digimon_world.world.world_state import get_world

        world = get_world()
        agent = world.get("亚古兽")
        assert agent is not None, "亚古兽 should exist in world"

        client = TestClient(app)
        resp = client.get("/api/digimon/亚古兽/insights")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_name"] == "亚古兽"
        assert "overall_score" in data
        assert "dimensions" in data

    def test_insights_endpoint_returns_404_for_unknown(self):
        """不存在的 agent 应返回 404。"""
        from digimon_world.api.app import app

        client = TestClient(app)
        resp = client.get("/api/digimon/不存在的数码兽/insights")
        assert resp.status_code == 404

    def test_insights_endpoint_has_all_dimensions(self):
        """返回的数据包含三个维度。"""
        from digimon_world.api.app import app
        from digimon_world.world.world_state import get_world

        world = get_world()
        agents = list(world.agents.keys())
        assert len(agents) > 0, "Need at least one agent"

        client = TestClient(app)
        resp = client.get(f"/api/digimon/{agents[0]}/insights")
        assert resp.status_code == 200
        data = resp.json()

        dims = data["dimensions"]
        assert "memory_health" in dims
        assert "plan_execution" in dims
        assert "world_model" in dims

    def test_insights_memory_health_details(self):
        """memory_health 维度包含正确的 details 字段。"""
        from digimon_world.api.app import app
        from digimon_world.world.world_state import get_world

        world = get_world()
        agent = world.get("亚古兽")
        assert agent is not None

        client = TestClient(app)
        resp = client.get("/api/digimon/亚古兽/insights")
        assert resp.status_code == 200
        data = resp.json()

        mh = data["dimensions"]["memory_health"]
        if mh is not None:
            assert "score" in mh
            assert "details" in mh
            assert "total" in mh["details"]
            assert "strong" in mh["details"]
            assert "weak" in mh["details"]

    def test_insights_plan_execution_details(self):
        """plan_execution 维度包含正确的 details 字段。"""
        from digimon_world.api.app import app
        from digimon_world.world.world_state import get_world

        world = get_world()
        agent = world.get("加布兽")
        assert agent is not None

        client = TestClient(app)
        resp = client.get("/api/digimon/加布兽/insights")
        assert resp.status_code == 200
        data = resp.json()

        pe = data["dimensions"]["plan_execution"]
        if pe is not None:
            assert "score" in pe
            assert "details" in pe
            assert "total" in pe["details"]
            assert "completed" in pe["details"]

    def test_insights_world_model_details(self):
        """world_model 维度包含正确的 details 字段。"""
        from digimon_world.api.app import app
        from digimon_world.world.world_state import get_world

        world = get_world()
        agent = world.get("比丘兽")
        assert agent is not None

        client = TestClient(app)
        resp = client.get("/api/digimon/比丘兽/insights")
        assert resp.status_code == 200
        data = resp.json()

        wm = data["dimensions"]["world_model"]
        if wm is not None:
            assert "score" in wm
            assert "details" in wm
            assert "rules_count" in wm["details"]
            assert "episodes_count" in wm["details"]

    def test_overall_score_in_range(self):
        """综合评分在 0-100 范围内。"""
        from digimon_world.api.app import app
        from digimon_world.world.world_state import get_world

        world = get_world()
        agents = list(world.agents.keys())
        client = TestClient(app)

        for name in agents[:5]:
            resp = client.get(f"/api/digimon/{name}/insights")
            if resp.status_code == 200:
                data = resp.json()
                assert 0 <= data["overall_score"] <= 100, f"{name} score out of range: {data['overall_score']}"
