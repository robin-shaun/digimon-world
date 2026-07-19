"""
合作阈值集成 (Cooperation Threshold Integration)
================================================

Phase 16 Task 5: 在对话/战斗/组队场景中用关系距离调节互动概率。

基于 RelationalDistance.get_circle() 判定两个 agent 的关系圈层,
返回互动概率乘数 (modifier), 实现对不同亲疏关系的差异化管理。

使用方式::

    from digimon_world.world.cooperation_thresholds import get_interaction_modifier
    modifier = get_interaction_modifier("Agumon", "Gabumon", tracker, "dialogue")
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .relational_circle import RelationalCircle, RelationalDistance

if TYPE_CHECKING:
    from .relationships import RelationshipTracker

# ---- 对话触发概率乘数 ----
# 关系越亲密, 越容易聊天
DIALOGUE_MODIFIERS: dict[RelationalCircle, float] = {
    RelationalCircle.INTIMATE: 1.5,       # 更容易聊
    RelationalCircle.FRIENDLY: 1.2,
    RelationalCircle.ACQUAINTANCE: 1.0,
    RelationalCircle.NEUTRAL: 0.6,        # 外人很少聊
    RelationalCircle.HOSTILE: 0.3,        # 几乎不聊
}

# ---- 战斗触发概率乘数 ----
# 关系越敌对, 越容易打
BATTLE_MODIFIERS: dict[RelationalCircle, float] = {
    RelationalCircle.INTIMATE: 0.1,       # 几乎不打
    RelationalCircle.FRIENDLY: 0.3,
    RelationalCircle.ACQUAINTANCE: 0.7,
    RelationalCircle.NEUTRAL: 1.0,        # 陌生人正常概率
    RelationalCircle.HOSTILE: 2.0,        # 更容易打
}

# ---- 合作倾向因子 ----
# 关系越亲密, 越倾向协同行动
COOPERATION_FACTORS: dict[RelationalCircle, float] = {
    RelationalCircle.INTIMATE: 1.5,
    RelationalCircle.FRIENDLY: 1.3,
    RelationalCircle.ACQUAINTANCE: 1.0,
    RelationalCircle.NEUTRAL: 0.6,
    RelationalCircle.HOSTILE: 0.1,
}


def get_interaction_modifier(
    agent_a: str,
    agent_b: str,
    tracker: RelationshipTracker,
    interaction_type: str,
) -> float:
    """获取两个 agent 之间的互动概率乘数。

    Args:
        agent_a: 第一个 agent 名字。
        agent_b: 第二个 agent 名字。
        tracker: 关系追踪器实例。
        interaction_type: 互动类型, "dialogue" / "battle" / "cooperation"。

    Returns:
        概率乘数 (≥0), 默认 1.0。

        乘数含义:
        - 1.0 = 无调节
        - >1.0 = 更容易触发
        - <1.0 = 更难触发
    """
    modifier_map = {
        "dialogue": DIALOGUE_MODIFIERS,
        "battle": BATTLE_MODIFIERS,
        "cooperation": COOPERATION_FACTORS,
    }
    modifiers = modifier_map.get(interaction_type, DIALOGUE_MODIFIERS)

    rd = RelationalDistance(agent_a, tracker)
    circle = rd.get_circle(agent_b)
    return modifiers.get(circle, 1.0)


def get_circle_between(
    agent_a: str,
    agent_b: str,
    tracker: RelationshipTracker,
) -> RelationalCircle:
    """获取两个 agent 之间的关系圈层 (从 agent_a 的视角)。

    Returns:
        关系圈层。如果无关系记录则返回 NEUTRAL。
    """
    rd = RelationalDistance(agent_a, tracker)
    return rd.get_circle(agent_b)


# ---- 衰减系数 (与 affect_propagation 保持一致) ----
# 用于传播/衰减类场景, 与 AffectPropagationEngine 中的系数一致
CIRCLE_DECAY_FACTORS: dict[RelationalCircle, float] = {
    RelationalCircle.INTIMATE: 0.8,
    RelationalCircle.FRIENDLY: 0.6,
    RelationalCircle.ACQUAINTANCE: 0.3,
    RelationalCircle.NEUTRAL: 0.1,
    RelationalCircle.HOSTILE: 0.0,  # 阻断
}
