"""
Interactions - 多 agent 互动检测
================================

数码兽在世界里移动时,如果彼此靠得足够近,就有机会触发一段对话。
本模块只负责"空间邻近检测",不关心对话内容(那是 agents.dialogue 的事)。

参考 Stanford Generative Agents 的做法:他们用 agent 的可见半径(vision radius)
判断"谁能看到谁",再决定是否发起对话。这里简化为固定半径的欧氏距离。

设计要点:
- 纯同步、无 LLM、无 asyncio 依赖(方便测试 / 高频调用)
- 两两比较(O(n^2)),数码兽数量小(Phase 2 只有几只),够用
- 只在同一 region 内配对(跨地图不算相遇)由调用方过滤或本函数内判断
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..agents.digimon_agent import DigimonAgent


def distance(a: DigimonAgent, b: DigimonAgent) -> float:
    """两只数码兽之间的欧氏距离(像素)。"""
    ax, ay = a.location
    bx, by = b.location
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


def detect_proximity(
    agents: list[DigimonAgent],
    radius: int = 100,
) -> list[tuple[DigimonAgent, DigimonAgent]]:
    """两两比较,返回距离 < radius 的数码兽配对。

    Args:
        agents: 参与检测的数码兽列表
        radius: 相遇半径(像素),距离严格小于此值才算靠近

    Returns:
        配对列表,每个元素是 (agent_a, agent_b) 元组。
        同一对只返回一次(i < j),不含自我配对。
    """
    pairs: list[tuple[DigimonAgent, DigimonAgent]] = []
    for i in range(len(agents)):
        for j in range(i + 1, len(agents)):
            a, b = agents[i], agents[j]
            if distance(a, b) < radius:
                pairs.append((a, b))
    return pairs
