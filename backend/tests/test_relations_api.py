"""
Tests for /api/relations/{name} — 差序格局 (Differential Mode of Association) API endpoint.

Phase 16 Task 2: 验证关系视图端点的正确性。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from digimon_world.api import app
from digimon_world.world import (
    get_tracker,
    get_world,
    reset_tracker,
    reset_world,
)
from digimon_world.world.relationships import RelationshipTracker, RelationshipVector


@pytest.fixture(autouse=True)
def _reset() -> None:
    """每个测试前重置世界和关系表单例，避免污染。"""
    reset_world()
    reset_tracker()
    yield
    reset_world()
    reset_tracker()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _ensure_agents() -> list[str]:
    """确保世界中有 agents 并返回名称列表。"""
    world = get_world()
    agents = world.all()
    assert len(agents) >= 3, f"Expected >= 3 agents, got {len(agents)}"
    return [a.name for a in agents]


def _setup_known_relations() -> tuple[list[str], RelationshipTracker]:
    """设置已知的关系数据用于测试。

    在亚古兽、加布兽、恶魔兽之间设置三条关系:
    - 亚古兽-加布兽: INTIMATE (亲和高)
    - 亚古兽-恶魔兽: HOSTILE (敌对)
    """
    names = _ensure_agents()
    tracker = get_tracker()

    # 直接按名字查找 agent (扩容后同物种多个,按名字精确匹配)
    world = get_world()
    agumon_name = "亚古兽"
    gabumon_name = "加布兽"
    devimon_name = "恶魔兽"

    assert world.get(agumon_name), f"Missing agent: {agumon_name}"
    assert world.get(gabumon_name), f"Missing agent: {gabumon_name}"
    assert world.get(devimon_name), f"Missing agent: {devimon_name}"

    # 设置关系: 亚古兽-加布兽 亲密 (INTIMATE)
    tracker._vectors[(agumon_name, gabumon_name)] = RelationshipVector(
        affinity=40.0, rivalry=0.0, respect=30.0, fear=0.0
    )
    # 设置关系: 亚古兽-恶魔兽 敌对 (HOSTILE)
    tracker._vectors[(agumon_name, devimon_name)] = RelationshipVector(
        affinity=-50.0, rivalry=40.0, respect=10.0, fear=60.0
    )

    return names, tracker


class TestRelationsApi:
    """测试 /api/relations/{name} 端点。"""

    def test_get_relations_existing_agent(self, client: TestClient) -> None:
        """验证返回结构完整。"""
        _setup_known_relations()
        world = get_world()

        # 用第一个已有的 agent 做测试
        agumon = world.get("亚古兽")
        assert agumon is not None

        r = client.get("/api/relations/亚古兽")
        assert r.status_code == 200
        data = r.json()

        # 顶层字段
        assert data["agent"] == "亚古兽"
        assert data["self_circle"] == "INTIMATE"
        assert data["self_circle_label"] == "至交"
        assert "relations" in data
        assert "summary" in data

        # relations 结构
        relations = data["relations"]
        assert isinstance(relations, dict)
        # 应该有 29 个其他 agent (30 total, 去掉自己)
        assert len(relations) >= 3

        # 检查单个 relation 条目
        for other_name, rel in relations.items():
            assert "circle" in rel
            assert rel["circle"] in ("INTIMATE", "FRIENDLY", "ACQUAINTANCE", "NEUTRAL", "HOSTILE")
            assert "circle_label" in rel
            assert rel["circle_label"] in ("至交", "友好", "相识", "中立", "敌对")
            assert "distance" in rel
            assert 0.0 <= rel["distance"] <= 1.0
            assert "affect" in rel
            assert set(rel["affect"].keys()) == {"trust", "affection", "respect", "fear"}
            assert "composite_score" in rel
            assert "cooperation_threshold" in rel
            ct = rel["cooperation_threshold"]
            assert set(ct.keys()) == {"low_risk", "medium_risk", "high_risk"}

        # summary 结构
        summary = data["summary"]
        assert set(summary.keys()) == {
            "intimate_count", "friendly_count", "acquaintance_count",
            "neutral_count", "hostile_count",
        }
        # 所有计数之和应等于 relations 数量
        total = sum(summary.values())
        assert total == len(relations)

    def test_get_relations_nonexistent_agent(self, client: TestClient) -> None:
        """验证不存在的 agent 返回 404。"""
        r = client.get("/api/relations/不存在的数码兽")
        assert r.status_code == 404
        data = r.json()
        assert "detail" in data

    def test_circle_classification(self, client: TestClient) -> None:
        """验证圈层分类: 亚古兽对加布兽为 INTIMATE，对恶魔兽为 HOSTILE。"""
        _setup_known_relations()

        r = client.get("/api/relations/亚古兽")
        assert r.status_code == 200
        data = r.json()
        relations = data["relations"]

        # 亚古兽的亲密朋友加布兽
        assert relations["加布兽"]["circle"] == "INTIMATE"
        assert relations["加布兽"]["circle_label"] == "至交"
        assert relations["加布兽"]["composite_score"] > 15

        # 亚古兽的敌人恶魔兽
        assert relations["恶魔兽"]["circle"] == "HOSTILE"
        assert relations["恶魔兽"]["circle_label"] == "敌对"
        assert relations["恶魔兽"]["composite_score"] < -5

    def test_affect_vector_values(self, client: TestClient) -> None:
        """验证情感向量值在 0-1 范围内。"""
        _setup_known_relations()

        r = client.get("/api/relations/亚古兽")
        assert r.status_code == 200
        data = r.json()

        for other_name, rel in data["relations"].items():
            affect = rel["affect"]
            for dim in ("trust", "affection", "respect", "fear"):
                val = affect[dim]
                assert 0.0 <= val <= 1.0, \
                    f"{other_name}.affect.{dim} = {val} is out of [0, 1]"

        # 加布兽的信任应该很高
        gabu = data["relations"]["加布兽"]["affect"]
        assert gabu["trust"] > 0.6
        assert gabu["fear"] < 0.2

        # 恶魔兽的恐惧应该很高
        devi = data["relations"]["恶魔兽"]["affect"]
        assert devi["fear"] > 0.4
        assert devi["trust"] < 0.5

    def test_summary_counts_match(self, client: TestClient) -> None:
        """验证 summary 计数与 relations 数据一致。"""
        _setup_known_relations()

        r = client.get("/api/relations/亚古兽")
        assert r.status_code == 200
        data = r.json()

        relations = data["relations"]
        summary = data["summary"]

        # 手动统计各圈层数量
        actual_intimate = sum(1 for rel in relations.values() if rel["circle"] == "INTIMATE")
        actual_friendly = sum(1 for rel in relations.values() if rel["circle"] == "FRIENDLY")
        actual_acquaintance = sum(1 for rel in relations.values() if rel["circle"] == "ACQUAINTANCE")
        actual_neutral = sum(1 for rel in relations.values() if rel["circle"] == "NEUTRAL")
        actual_hostile = sum(1 for rel in relations.values() if rel["circle"] == "HOSTILE")

        assert summary["intimate_count"] == actual_intimate
        assert summary["friendly_count"] == actual_friendly
        assert summary["acquaintance_count"] == actual_acquaintance
        assert summary["neutral_count"] == actual_neutral
        assert summary["hostile_count"] == actual_hostile

        # 已知: 亚古兽-加布兽 INTIMATE, 亚古兽-恶魔兽 HOSTILE
        assert summary["intimate_count"] >= 1
        assert summary["hostile_count"] >= 1

        # 总数一致
        total = sum(summary.values())
        assert total == len(relations)
