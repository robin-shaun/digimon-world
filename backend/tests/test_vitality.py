"""Phase 7: 世界活力指标测试。"""

from __future__ import annotations

from digimon_world.agents import DigimonAgent
from digimon_world.world import compute_vitality
from digimon_world.world.world_state import WorldState


def test_compute_vitality_empty_world() -> None:
    """空世界返回全零指标。"""
    w = WorldState()
    vitality = compute_vitality(w)
    assert vitality.overall_vitality == 0.0
    assert vitality.entropy == 0.0
    assert vitality.social_density == 0.0
    assert vitality.event_diversity == 0.0


def test_compute_vitality_with_agents() -> None:
    """有数码兽的世界的活力指标在合理范围。"""
    w = WorldState()
    w.spawn(DigimonAgent(name="a", species="a", location=(100, 100)))
    w.spawn(DigimonAgent(name="b", species="b", location=(800, 500)))
    w.spawn(DigimonAgent(name="c", species="c", location=(400, 300)))

    vitality = compute_vitality(w)
    # 位置分散 → entropy > 0
    assert vitality.entropy >= 0.0
    # 综合分数在 0-100 之间
    assert 0.0 <= vitality.overall_vitality <= 100.0


def test_compute_vitality_social_density() -> None:
    """接近的 agent 应产生高社交密度。"""
    w = WorldState()
    w.spawn(DigimonAgent(name="a", species="a", location=(100, 100)))
    w.spawn(DigimonAgent(name="b", species="b", location=(120, 105)))  # 很近
    w.spawn(DigimonAgent(name="c", species="c", location=(900, 500)))  # 很远

    vitality = compute_vitality(w)
    # 2/3 有邻居 → social_density ≈ 0.67
    assert vitality.social_density > 0.3


def test_compute_vitality_to_dict() -> None:
    """to_dict 返回包含所有字段的字典。"""
    w = WorldState()
    w.spawn(DigimonAgent(name="a", species="a", location=(100, 100)))
    vitality = compute_vitality(w)
    d = vitality.to_dict()
    assert "entropy" in d
    assert "social_density" in d
    assert "event_diversity" in d
    assert "interaction_rate" in d
    assert "mood_variance" in d
    assert "overall_vitality" in d
    assert all(isinstance(v, int | float) for v in d.values())


def test_compute_vitality_event_diversity() -> None:
    """有事件的世界事件多样性应 > 0。"""
    w = WorldState()
    w.spawn(DigimonAgent(name="a", species="a", location=(100, 100)))
    # 注入不同事件
    w.append_event({"type": "moved", "agent": "a", "description": "移动"})
    w.append_event({"type": "dialogue", "agent": "a", "description": "对话"})
    w.append_event({"type": "battle", "agent": "a", "description": "战斗"})

    vitality = compute_vitality(w)
    # 3 种不同事件 → diversity > 0
    assert vitality.event_diversity > 0.0
