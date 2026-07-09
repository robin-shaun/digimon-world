"""
切磋 API 测试
=============

覆盖 POST /api/battle/spar:
- 友好切磋:双方 happiness +5 / experience +2,不产生胜者、不加 victories
- 切磋不改社交关系(record_battle 未被调用)
- 404(找不到) / 400(自己切磋自己)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from digimon_world.api import app as fastapi_app
from digimon_world.world import get_tracker, get_world, reset_world


@pytest.fixture(autouse=True)
def _reset():
    reset_world()
    yield
    reset_world()


@pytest.fixture
def client() -> TestClient:
    return TestClient(fastapi_app)


def test_spar_gains_and_no_winner(client: TestClient) -> None:
    """友好切磋:双方各 happiness +5 / experience +2,不加 battle_victories。"""
    world = get_world()
    a = world.get("亚古兽")
    b = world.get("加布兽")
    assert a is not None and b is not None
    h0_a, e0_a = a.stats.happiness, a.stats.experience
    h0_b, e0_b = b.stats.happiness, b.stats.experience

    r = client.post(
        "/api/battle/spar",
        json={"attacker": "亚古兽", "defender": "加布兽"},
    )
    assert r.status_code == 200, r.text
    data = r.json()

    # 无胜负标记
    assert data["friendly"] is True
    assert "winner" not in data

    # 收益结算(happiness 夹紧到 100)
    assert data["attacker"]["happiness"] == min(100, h0_a + 5)
    assert data["attacker"]["experience"] == e0_a + 2
    assert data["defender"]["happiness"] == min(100, h0_b + 5)
    assert data["defender"]["experience"] == e0_b + 2

    # 不计胜负
    assert a.battle_victories == 0
    assert b.battle_victories == 0


def test_spar_does_not_change_relationships(client: TestClient) -> None:
    """切磋是友好行为,不应改动社交关系(与正式战斗相反)。"""
    tracker = get_tracker()
    score_before = tracker.get_relationship("亚古兽", "加布兽")

    r = client.post(
        "/api/battle/spar",
        json={"attacker": "亚古兽", "defender": "加布兽"},
    )
    assert r.status_code == 200

    assert tracker.get_relationship("亚古兽", "加布兽") == score_before


def test_spar_not_found_and_self(client: TestClient) -> None:
    """找不到数码兽 → 404;自己切磋自己 → 400。"""
    r_404 = client.post(
        "/api/battle/spar",
        json={"attacker": "不存在兽", "defender": "加布兽"},
    )
    assert r_404.status_code == 404

    r_self = client.post(
        "/api/battle/spar",
        json={"attacker": "亚古兽", "defender": "亚古兽"},
    )
    assert r_self.status_code == 400
