"""
WorldVitality - 世界活力指标
===========================

Phase 7: 量化"世界活了没" —— 通过 entropy（位置分布熵）、
social_density（社交密度）、event_diversity（事件多样性）、
interaction_rate（互动率）、mood_variance（心情方差）等指标。

参考: 世界模拟需要可量化的活力分数来评估模拟质量。
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any

from .world_state import WorldState


@dataclass
class VitalitySnapshot:
    """一次活力快照，可被前端直接渲染。"""

    entropy: float = 0.0           # 位置分布熵 (0-1, 越高越分散)
    social_density: float = 0.0    # 社交密度 (0-1, 附近有同伴的概率)
    event_diversity: float = 0.0   # 事件多样性 (0-1, 香农指数归一化)
    interaction_rate: float = 0.0  # 互动率 (0-1, 对话/战斗事件占比)
    mood_variance: float = 0.0     # 心情方差 (0-1, 情绪波动程度)
    overall_vitality: float = 0.0  # 综合活力分数 (0-100)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entropy": round(self.entropy, 4),
            "social_density": round(self.social_density, 4),
            "event_diversity": round(self.event_diversity, 4),
            "interaction_rate": round(self.interaction_rate, 4),
            "mood_variance": round(self.mood_variance, 4),
            "overall_vitality": round(self.overall_vitality, 1),
        }


def compute_vitality(world: WorldState, recent_ticks: int = 50) -> VitalitySnapshot:
    """计算世界活力指标。

    Args:
        world: 世界状态
        recent_ticks: 只取最近 N 条事件做分析窗口

    Returns:
        VitalitySnapshot
    """
    agents = world.all()
    n_agents = len(agents)
    if n_agents == 0:
        return VitalitySnapshot()

    # ---- 1. 位置分布熵 (entropy) ----
    # 将画布 (960x600) 分成网格，计算 agent 位置的香农熵
    grid_cols = 8
    grid_rows = 5
    cell_w = 960 / grid_cols
    cell_h = 600 / grid_rows
    grid_counts: Counter = Counter()

    for agent in agents:
        x, y = agent.location
        col = min(int(x / cell_w), grid_cols - 1)
        row = min(int(y / cell_h), grid_rows - 1)
        grid_counts[(col, row)] += 1

    total_cells = grid_cols * grid_rows
    entropy = 0.0
    for count in grid_counts.values():
        p = count / n_agents
        if p > 0:
            entropy -= p * math.log2(p)
    max_entropy = math.log2(min(total_cells, n_agents))
    normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0.0

    # ---- 2. 社交密度 (social_density) ----
    # 每个 agent 附近 100px 内有至少一个同伴的比例
    SOCIAL_RADIUS = 100.0  # noqa: N806
    in_proximity = 0
    for agent in agents:
        ax, ay = agent.location
        has_neighbor = False
        for other in agents:
            if other.name == agent.name:
                continue
            ox, oy = other.location
            dist = math.hypot(ax - ox, ay - oy)
            if dist <= SOCIAL_RADIUS:
                has_neighbor = True
                break
        if has_neighbor:
            in_proximity += 1
    social_density = in_proximity / n_agents

    # ---- 3. 事件多样性 (event_diversity) ----
    # 取最近 N 条事件，计算事件类型的香农指数
    recent_events = world.events[-recent_ticks:] if len(world.events) > recent_ticks else world.events
    type_counts: Counter = Counter()
    for ev in recent_events:
        et = ev.get("type", "unknown")
        type_counts[et] += 1

    total_events = len(recent_events)
    event_entropy = 0.0
    for count in type_counts.values():
        p = count / total_events
        if p > 0:
            event_entropy -= p * math.log2(p)
    # 归一化: 如果只有1种事件 → 0, 均匀分布 → 1
    max_event_entropy = math.log2(max(len(type_counts), 1))
    event_diversity = event_entropy / max_event_entropy if max_event_entropy > 0 else 0.0

    # ---- 4. 互动率 (interaction_rate) ----
    # 最近事件中 dialogue/battle 类占比
    interaction_types = {"dialogue", "battle", "battle_victory", "first_meet", "spar"}
    interaction_count = sum(
        1 for ev in recent_events if ev.get("type") in interaction_types
    )
    interaction_rate = interaction_count / max(total_events, 1)

    # ---- 5. 心情方差 (mood_variance) ----
    # 所有 agent mood_state 的 joy 维度的方差
    joys = [a.mood_state.get("joy", 0.0) for a in agents]
    if joys:
        mean_joy = sum(joys) / len(joys)
        mood_variance = sum((j - mean_joy) ** 2 for j in joys) / len(joys)
        # 方差最大值为 0.25 (均值0.5时极端分布)，归一化到 [0, 1]
        mood_variance = min(1.0, mood_variance / 0.25)
    else:
        mood_variance = 0.0

    # ---- 综合活力分数 (0-100) ----
    # 权重: entropy 0.25, social_density 0.25, event_diversity 0.2,
    #       interaction_rate 0.2, mood_variance 0.1
    overall_vitality = (
        0.25 * normalized_entropy
        + 0.25 * social_density
        + 0.20 * event_diversity
        + 0.20 * interaction_rate
        + 0.10 * mood_variance
    ) * 100

    return VitalitySnapshot(
        entropy=normalized_entropy,
        social_density=social_density,
        event_diversity=event_diversity,
        interaction_rate=interaction_rate,
        mood_variance=mood_variance,
        overall_vitality=overall_vitality,
    )
