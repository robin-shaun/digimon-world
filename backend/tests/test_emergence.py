"""
Phase 11: 涌现指标测试 (EmergenceMetrics)
=======================================

测试 compute_emergence_metrics() 的各项指标计算:
- 空世界 / 单 agent / 多 agent 场景
- 社交网络指标 (聚类系数、网络密度、平均路径长度、模块度)
- 行为多样性 (计划香农熵、行为类型计数)
- 情绪指标 (平均情绪、情绪方差、情绪传染)
- 涌现事件计数
- 综合涌现分数
- API 端点 /api/emergence
- 辅助函数 _classify_plan / _is_emergent_event
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from digimon_world.agents.digimon_agent import (
    DigimonAgent,
    DigimonAttribute,
    DigimonStats,
)
from digimon_world.world.emergence_metrics import (
    EmergenceSnapshot,
    _classify_plan,
    _is_emergent_event,
    compute_emergence_metrics,
)
from digimon_world.world.world_state import WorldState, reset_world


@pytest.fixture(autouse=True)
def _clean_world():
    """每个测试前后重置世界单例,防止跨测试状态泄漏。"""
    reset_world()
    yield
    reset_world()


def _empty_world() -> WorldState:
    """创建一个完全空白的世界(无预置数码兽),用于隔离测试。"""
    return WorldState()


def _make_agent(
    name: str,
    x: int = 0,
    y: int = 0,
    plan: str = "",
    attribute: DigimonAttribute = DigimonAttribute.VACCINE,
) -> DigimonAgent:
    """快速创建一个位置可控的数码兽。"""
    return DigimonAgent(
        name=name,
        species=name,
        region_id="file_island",
        stats=DigimonStats(hp=100, ep=50, attack=20, defense=15, speed=15),
        location=(x, y),
        attribute=attribute,
        current_plan=plan,
    )


# ========== 辅助函数测试 ==========


class TestClassifyPlan:
    def test_empty_plan(self):
        assert _classify_plan("") == "无计划"
        assert _classify_plan(None) == "无计划"  # type: ignore

    def test_exploration_keywords(self):
        assert _classify_plan("探索文件岛") == "探索"
        assert _classify_plan("在无限山巡逻") == "探索"
        assert _classify_plan("前往创始村寻找食物") == "探索"

    def test_social_keywords(self):
        assert _classify_plan("和亚古兽交朋友") == "社交"
        assert _classify_plan("找加布兽聊天") == "社交"
        assert _classify_plan("拜访迪路兽") == "社交"

    def test_battle_keywords(self):
        assert _classify_plan("向恶魔兽挑战") == "战斗"
        assert _classify_plan("变强打败敌人") == "战斗"
        assert _classify_plan("修炼技能") == "战斗"

    def test_rest_keywords(self):
        assert _classify_plan("在树下休息") == "休息"
        assert _classify_plan("晒太阳放松") == "休息"

    def test_foraging_keywords(self):
        assert _classify_plan("找食物吃") == "觅食"
        assert _classify_plan("去湖边觅食") == "觅食"

    def test_guard_keywords(self):
        assert _classify_plan("守护创始村") == "守护"
        assert _classify_plan("警戒周围") == "守护"

    def test_dominance_keywords(self):
        assert _classify_plan("策划阴谋") == "支配"
        assert _classify_plan("统治文件岛") == "支配"

    def test_unmatched_plan(self):
        assert _classify_plan("做一些莫名其妙的事") == "其他"


class TestIsEmergentEvent:
    def test_director_event_not_emergent(self):
        assert _is_emergent_event({"type": "faction_create", "source": "director"}) is False

    def test_faction_create_is_emergent(self):
        assert _is_emergent_event({"type": "faction_create"}) is True

    def test_dialogue_is_emergent(self):
        assert _is_emergent_event({"type": "dialogue", "source": "autonomous"}) is True

    def test_evolution_is_emergent(self):
        assert _is_emergent_event({"type": "evolution"}) is True

    def test_first_meet_is_emergent(self):
        assert _is_emergent_event({"type": "first_meet"}) is True

    def test_disaster_is_emergent(self):
        assert _is_emergent_event({"type": "disaster"}) is True

    def test_rebirth_is_emergent(self):
        assert _is_emergent_event({"type": "rebirth"}) is True

    def test_unknown_type_not_emergent(self):
        assert _is_emergent_event({"type": "unknown_noise"}) is False

    def test_empty_event_not_emergent(self):
        assert _is_emergent_event({}) is False


# ========== compute_emergence_metrics 测试 ==========


class TestEmergenceMetricsEmptyWorld:
    def test_empty_world_returns_zero_snapshot(self):
        world = _empty_world()
        snap = compute_emergence_metrics(world)
        assert isinstance(snap, EmergenceSnapshot)
        assert snap.agent_count == 0
        assert snap.clustering_coefficient == 0.0
        assert snap.network_density == 0.0
        assert snap.plan_entropy == 0.0
        assert snap.emergence_score == 0.0


class TestEmergenceMetricsSingleAgent:
    def test_single_agent(self):
        world = _empty_world()
        agent = _make_agent("亚古兽", x=100, y=100, plan="探索文件岛")
        world.spawn(agent)

        snap = compute_emergence_metrics(world)
        assert snap.agent_count == 1
        # 单个 agent 无邻居,聚类系数/网络密度/情绪传染应为 0
        assert snap.clustering_coefficient == 0.0
        assert snap.network_density == 0.0
        assert snap.avg_path_length == 0.0
        assert snap.emotional_contagion == 0.0
        # 行为熵: 只有一种计划类型 → 熵为 0
        assert snap.plan_entropy == 0.0
        assert snap.plan_type_count == 1


class TestEmergenceMetricsNetwork:
    def test_agents_close_together_form_network(self):
        """3 只数码兽靠得很近 (< 200px),应形成全连通网络。"""
        world = _empty_world()
        a1 = _make_agent("亚古兽", x=100, y=100, plan="探索")
        a2 = _make_agent("加布兽", x=110, y=100, plan="社交")
        a3 = _make_agent("比丘兽", x=120, y=100, plan="战斗")
        for a in [a1, a2, a3]:
            world.spawn(a)

        snap = compute_emergence_metrics(world)
        assert snap.agent_count == 3
        # 全连通: 3 node → max edges = 3*2/2 = 3
        assert snap.network_density == 1.0
        # 全连通图聚类系数 = 1.0
        assert snap.clustering_coefficient == 1.0
        # BFS 平均路径: 每对都是 1 hop
        assert snap.avg_path_length == 1.0

    def test_agents_far_apart_no_network(self):
        """3 只数码兽距离 > 200px,应无连接。"""
        world = _empty_world()
        a1 = _make_agent("亚古兽", x=0, y=0, plan="探索")
        a2 = _make_agent("加布兽", x=500, y=500, plan="社交")
        a3 = _make_agent("比丘兽", x=1000, y=0, plan="战斗")
        for a in [a1, a2, a3]:
            world.spawn(a)

        snap = compute_emergence_metrics(world)
        assert snap.agent_count == 3
        assert snap.network_density == 0.0
        assert snap.clustering_coefficient == 0.0
        assert snap.avg_path_length == 0.0
        assert snap.emotional_contagion == 0.0

    def test_partial_network(self):
        """a1 和 a2 靠近, a3 远离 → 只有一条边。"""
        world = _empty_world()
        a1 = _make_agent("亚古兽", x=100, y=100)
        a2 = _make_agent("加布兽", x=110, y=100)
        a3 = _make_agent("比丘兽", x=800, y=800)
        for a in [a1, a2, a3]:
            world.spawn(a)

        snap = compute_emergence_metrics(world)
        assert snap.agent_count == 3
        # 只有 1 条边, max = 3*2/2 = 3 → density = 1/3
        assert snap.network_density == pytest.approx(1 / 3)
        # a1/a2 彼此邻居但共享 0 邻居 → 聚类 = 0
        assert snap.clustering_coefficient == 0.0
        # a1→a2 = 1, a2→a1 = 1 → mean = 1
        assert snap.avg_path_length == 1.0

    def test_agents_at_proximity_boundary(self):
        """距离刚好 = 200 时不算邻居 (< 200 才算)。"""
        world = _empty_world()
        a1 = _make_agent("亚古兽", x=0, y=0)
        a2 = _make_agent("加布兽", x=200, y=0)
        for a in [a1, a2]:
            world.spawn(a)

        snap = compute_emergence_metrics(world)
        assert snap.network_density == 0.0  # 距离 = 200, 不算


class TestEmergenceMetricsPlanEntropy:
    def test_all_same_plan(self):
        world = _empty_world()
        for i in range(4):
            world.spawn(_make_agent(f"兽{i}", x=i * 10, y=0, plan="探索森林"))
        snap = compute_emergence_metrics(world)
        assert snap.plan_type_count == 1
        assert snap.plan_entropy == 0.0

    def test_all_different_plans(self):
        world = _empty_world()
        plans = ["探索森林", "交朋友", "修炼战斗技能", "在树下休息"]
        for i, plan in enumerate(plans):
            world.spawn(_make_agent(f"兽{i}", x=i * 10, y=0, plan=plan))
        snap = compute_emergence_metrics(world)
        assert snap.plan_type_count == 4
        # 4 种等概率类型 → 熵 = -4 * (0.25 * log2(0.25)) = 2.0
        assert snap.plan_entropy == pytest.approx(2.0)
        assert len(snap.dominant_plan_types) == 3  # top 3

    def test_mixed_plans_with_dominance(self):
        world = _empty_world()
        for i in range(5):
            world.spawn(_make_agent(f"explorer_{i}", x=i * 10, y=0, plan="探索新区域"))
        for i in range(2):
            world.spawn(_make_agent(f"fighter_{i}", x=500 + i * 10, y=0, plan="修炼战斗"))
        world.spawn(_make_agent("lazy_one", x=700, y=0, plan="睡觉放松"))

        snap = compute_emergence_metrics(world)
        # 探索占主导
        assert snap.dominant_plan_types[0].startswith("探索")
        assert snap.plan_type_count == 3


class TestEmergenceMetricsMood:
    def test_mood_averages_are_zero_by_default(self):
        """数码兽默认 mood_state 全为 0。"""
        world = _empty_world()
        for i in range(3):
            world.spawn(_make_agent(f"兽{i}", x=i * 10, y=0))
        snap = compute_emergence_metrics(world)
        assert snap.avg_mood_joy == 0.0
        assert snap.avg_mood_fear == 0.0
        assert snap.avg_mood_anger == 0.0
        assert snap.avg_mood_sadness == 0.0
        assert snap.emotional_variance == 0.0

    def test_emotional_contagion_with_neighbors_same_mood(self):
        """邻居情绪相同 → 余弦相似度 = 1.0。"""
        world = _empty_world()
        for i in range(3):
            a = _make_agent(f"兽{i}", x=i * 10, y=0)
            a.mood_state = {"joy": 0.8, "fear": 0.1, "anger": 0.0, "sadness": 0.0}
            world.spawn(a)
        snap = compute_emergence_metrics(world)
        # 3 个 agent 全连通,每对有 2 条边(双向) → 6 条有向边 → 6 个 similarity
        assert snap.emotional_contagion == pytest.approx(1.0)
        # 情绪方差 > 0 (有非零值)
        assert snap.emotional_variance > 0.0

    def test_emotional_contagion_with_opposite_moods(self):
        """邻居情绪相反 → 可能有负余弦相似度。"""
        world = _empty_world()
        a1 = _make_agent("happy", x=0, y=0)
        a1.mood_state = {"joy": 1.0, "fear": 0.0, "anger": 0.0, "sadness": 0.0}
        world.spawn(a1)

        a2 = _make_agent("scared", x=10, y=0)
        a2.mood_state = {"joy": 0.0, "fear": 1.0, "anger": 0.0, "sadness": 0.0}
        world.spawn(a2)

        snap = compute_emergence_metrics(world)
        # 正交向量 → cosine similarity = 0
        assert snap.emotional_contagion == pytest.approx(0.0, abs=1e-6)

    def test_mood_averages_correct(self):
        world = _empty_world()
        a1 = _make_agent("a", x=0, y=0)
        a1.mood_state = {"joy": 0.5, "fear": 0.2, "anger": 0.1, "sadness": 0.0}
        world.spawn(a1)

        a2 = _make_agent("b", x=10, y=0)
        a2.mood_state = {"joy": 0.3, "fear": 0.4, "anger": 0.3, "sadness": 0.0}
        world.spawn(a2)

        snap = compute_emergence_metrics(world)
        assert snap.avg_mood_joy == pytest.approx(0.4)
        assert snap.avg_mood_fear == pytest.approx(0.3)
        assert snap.avg_mood_anger == pytest.approx(0.2)
        assert snap.avg_mood_sadness == 0.0


class TestEmergenceMetricsModularity:
    def test_modularity_by_attribute(self):
        """同属性的数码兽靠近 → 正模块度。"""
        world = _empty_world()
        # 2 疫苗种在一起 + 2 病毒种在一起, 两组彼此远离
        world.spawn(_make_agent("v1", x=0, y=0, attribute=DigimonAttribute.VACCINE))
        world.spawn(_make_agent("v2", x=10, y=0, attribute=DigimonAttribute.VACCINE))
        world.spawn(_make_agent("d1", x=500, y=0, attribute=DigimonAttribute.VIRUS))
        world.spawn(_make_agent("d2", x=510, y=0, attribute=DigimonAttribute.VIRUS))

        snap = compute_emergence_metrics(world)
        # 同属性间有边, 跨属性无边 → 正模块度
        assert snap.modularity > 0.0

    def test_modularity_mixed(self):
        """所有属性混在一起 → 接近 0 的模块度。"""
        world = _empty_world()
        world.spawn(_make_agent("v", x=0, y=0, attribute=DigimonAttribute.VACCINE))
        world.spawn(_make_agent("d", x=10, y=0, attribute=DigimonAttribute.DATA))
        world.spawn(_make_agent("vi", x=20, y=0, attribute=DigimonAttribute.VIRUS))

        snap = compute_emergence_metrics(world)
        # 虽然都连通但社区划分和全局边分布很接近 → 低模块度
        assert snap.modularity < 0.15


class TestEmergenceMetricsEvents:
    def test_no_emergent_events(self):
        world = _empty_world()
        world.spawn(_make_agent("a", x=0, y=0))
        snap = compute_emergence_metrics(world)
        assert snap.emergent_event_count == 0
        assert snap.recent_emergent_events == []

    def test_director_events_not_counted(self):
        world = _empty_world()
        world.spawn(_make_agent("a", x=0, y=0))
        world.events.append({
            "type": "faction_create",
            "source": "director",
            "description": "导演创建派系",
        })
        snap = compute_emergence_metrics(world)
        assert snap.emergent_event_count == 0

    def test_emergent_events_counted(self):
        world = _empty_world()
        world.spawn(_make_agent("a", x=0, y=0))
        world.events.append({"type": "dialogue", "description": "亚古兽和加布兽相遇"})
        world.events.append({"type": "evolution", "description": "亚古兽进化"})
        world.events.append({"type": "first_meet", "description": "亚古兽初次遇见比丘兽"})
        # 非涌现事件
        world.events.append({"type": "unknown", "description": "..."})
        world.events.append({"type": "walk", "source": "director", "description": "..."})

        snap = compute_emergence_metrics(world)
        assert snap.emergent_event_count == 3
        assert len(snap.recent_emergent_events) == 3

    def test_recent_events_capped_at_5(self):
        world = _empty_world()
        world.spawn(_make_agent("a", x=0, y=0))
        for i in range(10):
            world.events.append({
                "type": "dialogue",
                "description": f"对话事件 #{i}",
            })
        snap = compute_emergence_metrics(world)
        assert snap.emergent_event_count == 10
        assert len(snap.recent_emergent_events) == 5
        # 最近的是 #9
        assert "对话事件 #9" in snap.recent_emergent_events[0]


class TestEmergenceScoreRange:
    def test_score_is_between_0_and_100(self):
        """涌现分数始终在 0-100 之间。"""
        world = _empty_world()
        world.spawn(_make_agent("a", x=0, y=0))
        snap = compute_emergence_metrics(world)
        assert 0.0 <= snap.emergence_score <= 100.0

    def test_dense_clustered_world_scores_higher(self):
        """高聚类 + 高行为多样性 → 更高涌现分。"""
        world = _empty_world()
        plans = ["探索森林", "交朋友", "修炼技能", "在树下休息"]
        for i, plan in enumerate(plans):
            world.spawn(_make_agent(f"兽{i}", x=i * 15, y=0, plan=plan))
        # 给一些 emergent events
        world.events.append({"type": "dialogue", "description": "..."})
        world.events.append({"type": "evolution", "description": "..."})

        snap = compute_emergence_metrics(world)
        assert snap.clustering_coefficient == 1.0  # 全连通
        assert snap.plan_entropy > 1.5  # 4 种不同计划
        assert snap.emergence_score > 40.0  # 应该有较高分数

    def test_sparse_world_scores_lower(self):
        """无连接 + 无行为多样性 → 更低涌现分。"""
        world = _empty_world()
        world.spawn(_make_agent("a", x=0, y=0, plan="发呆"))
        world.spawn(_make_agent("b", x=500, y=500, plan="发呆"))
        snap = compute_emergence_metrics(world)
        assert snap.clustering_coefficient == 0.0
        assert snap.emergence_score < 10.0


class TestToDict:
    def test_to_dict_has_all_keys(self):
        snap = EmergenceSnapshot(agent_count=3)
        d = snap.to_dict()
        required_keys = [
            "clustering_coefficient",
            "avg_path_length",
            "network_density",
            "modularity",
            "plan_entropy",
            "plan_type_count",
            "dominant_plan_types",
            "avg_mood_joy",
            "avg_mood_fear",
            "avg_mood_anger",
            "avg_mood_sadness",
            "emotional_contagion",
            "emotional_variance",
            "emergent_event_count",
            "recent_emergent_events",
            "emergence_score",
            "agent_count",
        ]
        for key in required_keys:
            assert key in d, f"Missing key: {key}"

    def test_to_dict_rounds_values(self):
        snap = EmergenceSnapshot(
            clustering_coefficient=0.123456,
            emergence_score=45.6789,
            agent_count=5,
        )
        d = snap.to_dict()
        assert d["clustering_coefficient"] == 0.1235  # rounded to 4
        assert d["emergence_score"] == 45.7  # rounded to 1
        assert d["agent_count"] == 5


# ========== API 端点测试 ==========


class TestEmergenceAPI:
    @pytest.fixture
    def client(self):
        from digimon_world.api.app import app
        return TestClient(app)

    def test_get_emergence_metrics_empty(self, client):
        resp = client.get("/api/emergence")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_count"] > 0  # 默认初始化 N 只数码兽
        assert "emergence_score" in data
        assert "clustering_coefficient" in data
        assert "plan_entropy" in data
        assert "emotional_contagion" in data
        assert "emergent_event_count" in data

    def test_get_emergence_metrics_returns_valid_score(self, client):
        resp = client.get("/api/emergence")
        assert resp.status_code == 200
        data = resp.json()
        assert 0.0 <= data["emergence_score"] <= 100.0
        assert isinstance(data["agent_count"], int)
        assert isinstance(data["plan_type_count"], int)
        assert isinstance(data["emergent_event_count"], int)
