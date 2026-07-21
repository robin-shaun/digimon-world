"""
EmergenceMetrics — 涌现指标计算器
===============================

Phase 11: 科研级实时涌现分析。
参考 Stanford Generative Agents 和复杂网络理论,
实时计算多维度涌现指标用于论文级分析:

- 社交网络: 聚类系数、平均路径长度、模块度
- 行为多样性: 不同 plan 类型的香农熵
- 情绪传染: 相邻 agent mood 相关性
- 涌现事件: 非脚本触发的意外事件计数
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .world_state import WorldState


@dataclass
class EmergenceSnapshot:
    """一次涌现指标快照。"""

    # ── 社交网络指标 ──
    clustering_coefficient: float = 0.0          # 聚类系数 (0-1)
    avg_path_length: float = 0.0                 # 平均路径长度
    network_density: float = 0.0                 # 网络密度
    modularity: float = 0.0                      # 模块度 (简易版)

    # ── 行为多样性 ──
    plan_entropy: float = 0.0                    # 计划和行为类型的香农熵
    plan_type_count: int = 0                     # 不同计划类型的数量
    dominant_plan_types: list[str] = field(default_factory=list)  # 主导行为类型

    # ── 情绪指标 ──
    avg_mood_joy: float = 0.0                    # 平均 joy
    avg_mood_fear: float = 0.0                   # 平均 fear
    avg_mood_anger: float = 0.0                  # 平均 anger
    avg_mood_sadness: float = 0.0               # 平均 sadness
    emotional_contagion: float = 0.0             # 情绪传染指数 (相邻agent情绪相似度)
    emotional_variance: float = 0.0              # 情绪方差 (越大越多样)

    # ── 涌现事件 ──
    emergent_event_count: int = 0                # 涌现事件总数
    recent_emergent_events: list[str] = field(default_factory=list)  # 最近涌现事件

    # ── 综合 ──
    emergence_score: float = 0.0                 # 综合涌现分数 (0-100)
    agent_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "clustering_coefficient": round(self.clustering_coefficient, 4),
            "avg_path_length": round(self.avg_path_length, 2),
            "network_density": round(self.network_density, 4),
            "modularity": round(self.modularity, 4),
            "plan_entropy": round(self.plan_entropy, 4),
            "plan_type_count": self.plan_type_count,
            "dominant_plan_types": self.dominant_plan_types[:5],
            "avg_mood_joy": round(self.avg_mood_joy, 3),
            "avg_mood_fear": round(self.avg_mood_fear, 3),
            "avg_mood_anger": round(self.avg_mood_anger, 3),
            "avg_mood_sadness": round(self.avg_mood_sadness, 3),
            "emotional_contagion": round(self.emotional_contagion, 4),
            "emotional_variance": round(self.emotional_variance, 4),
            "emergent_event_count": self.emergent_event_count,
            "recent_emergent_events": self.recent_emergent_events[-5:],
            "emergence_score": round(self.emergence_score, 1),
            "agent_count": self.agent_count,
        }


# 被归为「涌现事件」的事件类型 (非脚本、意外产生)
_EMERGENT_EVENT_TYPES = frozenset({
    "faction_create",    # 自组织派系
    "dialogue",          # 自发的社交互动
    "evolution",         # 非导演触发的进化
    "first_meet",        # 首次相遇
    "disaster",          # 自然灾害的涌现效应
    "rebirth",           # 重生
})

# 计划意图关键词分类 (用于行为熵)
_PLAN_INTENT_CATEGORIES: dict[str, list[str]] = {
    "探索": ["探索", "巡视", "巡逻", "飞行", "调查", "探查", "寻找", "前往"],
    "社交": ["朋友", "交朋友", "聊天", "打招呼", "拜访", "组队", "团队"],
    "战斗": ["战斗", "攻击", "防守", "复仇", "挑战", "变强", "修炼"],
    "休息": ["休息", "睡觉", "发呆", "等待", "安静", "晒太阳", "放松"],
    "觅食": ["食物", "觅食", "吃", "找食物", "饿", "进食"],
    "守护": ["守护", "保护", "守卫", "家园", "警戒"],
    "支配": ["支配", "控制", "统治", "阴谋", "策划"],
}


def _classify_plan(plan: str) -> str:
    """将计划文本归类到意图类型。"""
    if not plan:
        return "无计划"
    for category, keywords in _PLAN_INTENT_CATEGORIES.items():
        if any(kw in plan for kw in keywords):
            return category
    return "其他"


def _is_emergent_event(event: dict[str, Any]) -> bool:
    """判断一个事件是否为涌现事件(非导演手动注入)。"""
    if event.get("source") == "director":
        return False
    return event.get("type", "") in _EMERGENT_EVENT_TYPES


def compute_emergence_metrics(world: WorldState) -> EmergenceSnapshot:
    """计算当前世界的所有涌现指标。

    无外部依赖,只在 WorldState 上做纯计算,适合高频轮询。
    """
    agents = world.all()
    snap = EmergenceSnapshot(agent_count=len(agents))

    if len(agents) == 0:
        return snap

    # ═══════════════════════════════════════════
    # 1. 社交网络指标 (基于 proximity 空间距离构建网络)
    # ═══════════════════════════════════════════
    proximity_radius = 200  # 距离 < 此值视为"邻居"
    adjacency: dict[str, set[str]] = {a.name: set() for a in agents}

    for i, a1 in enumerate(agents):
        x1, y1 = a1.location
        for j in range(i + 1, len(agents)):
            a2 = agents[j]
            x2, y2 = a2.location
            dist = math.hypot(x2 - x1, y2 - y1)
            if dist < proximity_radius:
                adjacency[a1.name].add(a2.name)
                adjacency[a2.name].add(a1.name)

    # 边数
    edges = sum(len(neighbors) for neighbors in adjacency.values()) // 2
    n = len(agents)
    max_edges = n * (n - 1) // 2
    snap.network_density = edges / max_edges if max_edges > 0 else 0.0

    # 聚类系数 (每个节点的三元组比例)
    cluster_coeffs: list[float] = []
    for name, neighbors in adjacency.items():  # noqa: B007
        deg = len(neighbors)
        if deg < 2:
            continue
        # 计算邻居之间的边数
        nb_edges = 0
        nb_list = list(neighbors)
        for ni, nb1 in enumerate(nb_list):
            for nb2 in nb_list[ni + 1:]:
                if nb2 in adjacency[nb1]:
                    nb_edges += 1
        max_nb_edges = deg * (deg - 1) // 2
        if max_nb_edges > 0:
            cluster_coeffs.append(nb_edges / max_nb_edges)

    snap.clustering_coefficient = (
        sum(cluster_coeffs) / len(cluster_coeffs) if cluster_coeffs else 0.0
    )

    # 平均路径长度 (BFS 近似, 只在连通分量内)
    total_path = 0
    path_count = 0
    for name in adjacency:
        visited = {name}
        queue = [(name, 0)]
        while queue:
            cur, dist = queue.pop(0)
            for nb in adjacency[cur]:
                if nb not in visited:
                    visited.add(nb)
                    queue.append((nb, dist + 1))
                    total_path += dist + 1
                    path_count += 1

    snap.avg_path_length = total_path / path_count if path_count > 0 else 0.0

    # 简易模块度: 基于 agent 属性(vaccine/data/virus/free)划分社区
    communities: dict[str, list[str]] = {}
    for a in agents:
        attr = a.attribute.value
        if attr not in communities:
            communities[attr] = []
        communities[attr].append(a.name)

    total_degree = sum(deg for deg in (len(adjacency[n]) for n in adjacency))
    modularity = 0.0
    if total_degree > 0:
        for comm_members in communities.values():
            for mem1 in comm_members:
                for mem2 in comm_members:
                    if mem1 < mem2:
                        # actual: 1 if edge exists, 0 otherwise
                        actual = 1 if mem2 in adjacency.get(mem1, set()) else 0
                        # expected: deg1 * deg2 / (2 * total_edges)
                        deg1 = len(adjacency.get(mem1, set()))
                        deg2 = len(adjacency.get(mem2, set()))
                        expected = (deg1 * deg2) / total_degree if total_degree > 0 else 0
                        modularity += actual - expected
        modularity /= total_degree

    snap.modularity = modularity

    # ═══════════════════════════════════════════
    # 2. 行为多样性 — 香农熵
    # ═══════════════════════════════════════════
    plan_types = [_classify_plan(a.current_plan or "") for a in agents]
    type_counter = Counter(plan_types)
    snap.plan_type_count = len(type_counter)

    total_plans = len(plan_types)
    entropy = 0.0
    for count in type_counter.values():
        prob = count / total_plans
        if prob > 0:
            entropy -= prob * math.log2(prob)
    snap.plan_entropy = entropy

    # 主导行为类型 (频率 top 3)
    snap.dominant_plan_types = [
        f"{tp}({cnt}/{total_plans})"
        for tp, cnt in type_counter.most_common(3)
    ]

    # ═══════════════════════════════════════════
    # 3. 情绪指标
    # ═══════════════════════════════════════════
    joys, fears, angers, sadnesses = [], [], [], []
    for a in agents:
        ms = a.mood_state
        joys.append(ms.get("joy", 0.0))
        fears.append(ms.get("fear", 0.0))
        angers.append(ms.get("anger", 0.0))
        sadnesses.append(ms.get("sadness", 0.0))

    snap.avg_mood_joy = sum(joys) / n
    snap.avg_mood_fear = sum(fears) / n
    snap.avg_mood_anger = sum(angers) / n
    snap.avg_mood_sadness = sum(sadnesses) / n

    # 情绪方差
    all_moods = joys + fears + angers + sadnesses
    mean_all = sum(all_moods) / len(all_moods)
    snap.emotional_variance = sum((m - mean_all) ** 2 for m in all_moods) / len(all_moods)

    # 情绪传染: 邻居之间 mood_state 的平均余弦相似度
    contagion_sims: list[float] = []
    for a1 in agents:
        for nb_name in adjacency.get(a1.name, set()):
            a2 = world.get(nb_name)
            if a2 is None:
                continue
            v1 = [a1.mood_state.get(dim, 0.0) for dim in ("joy", "fear", "anger", "sadness")]
            v2 = [a2.mood_state.get(dim, 0.0) for dim in ("joy", "fear", "anger", "sadness")]
            dot = sum(a * b for a, b in zip(v1, v2, strict=False))
            mag1 = math.sqrt(sum(a * a for a in v1))
            mag2 = math.sqrt(sum(b * b for b in v2))
            if mag1 > 0 and mag2 > 0:
                contagion_sims.append(dot / (mag1 * mag2))

    snap.emotional_contagion = (
        sum(contagion_sims) / len(contagion_sims) if contagion_sims else 0.0
    )

    # ═══════════════════════════════════════════
    # 4. 涌现事件
    # ═══════════════════════════════════════════
    emergent_events = [e for e in world.events if _is_emergent_event(e)]
    snap.emergent_event_count = len(emergent_events)

    # 最近涌现事件描述 (最多5条)
    recent = emergent_events[-5:]
    snap.recent_emergent_events = [
        f"[{e.get('type', '?')}] {e.get('description', e.get('line', str(e)))[:80]}"
        for e in reversed(recent)
    ]

    # ═══════════════════════════════════════════
    # 5. 综合涌现分数 (0-100)
    # ═══════════════════════════════════════════
    # 高聚类+高行为熵+高情绪传染+有涌现事件 = 高涌现
    score = 0.0
    score += snap.clustering_coefficient * 25           # 聚类越高,社会结构越涌现
    score += min(snap.plan_entropy / 3.0, 1.0) * 25    # 行为熵越高,多样性越涌现
    score += max(0.0, snap.emotional_contagion) * 20    # 情绪传染越强,社会性越涌现
    score += min(snap.emergent_event_count / 50, 1.0) * 15  # 涌现事件越多
    score += min(snap.network_density * 10, 10)         # 网络密度贡献
    score += min(snap.emotional_variance * 20, 5)       # 情绪多样性
    snap.emergence_score = min(100.0, score)

    return snap


# ═══════════════════════════════════════════════════════════════
# Phase 31 Task 2: 涌现真实性验证 — 基于耦合增益的涌现真伪判别
# ═══════════════════════════════════════════════════════════════

@dataclass
class EmergenceValiditySnapshot:
    """涌现真实性验证快照 — Phase 31 Task 2, 基于 arXiv:2606.22203."""

    coupling_gain: float = 0.0           # 耦合增益 (信息耦合 / 行为一致性)
    info_coupling: float = 0.0           # agent间信息耦合度 (0-1)
    behavioral_consistency: float = 0.0  # 行为一致性 (0-1)
    validity_score: float = 0.0          # 涌现可信度 (0-100)
    verdict: str = "unknown"             # genuine / neutral / suspected_noise / insufficient_data
    coupling_threshold: float = 0.5      # 使用的阈值
    agent_count: int = 0
    details: dict[str, float] = field(default_factory=dict)  # plan_coupling, location_coupling, plan_alignment, mood_alignment

    def to_dict(self) -> dict[str, Any]:
        return {
            "coupling_gain": round(self.coupling_gain, 4),
            "info_coupling": round(self.info_coupling, 4),
            "behavioral_consistency": round(self.behavioral_consistency, 4),
            "validity_score": round(self.validity_score, 1),
            "verdict": self.verdict,
            "coupling_threshold": round(self.coupling_threshold, 4),
            "agent_count": self.agent_count,
            "details": {k: round(v, 4) for k, v in self.details.items()},
        }


def compute_coupling_gain(world: WorldState) -> EmergenceValiditySnapshot:
    """计算耦合增益指标，区分真涌现与随机假象。

    参考 arXiv:2606.22203 — 涌现真实性验证框架：
    - 信息耦合高 + 行为一致性高 → 信息共享驱动，真涌现 (genuine)
    - 行为一致性高但信息耦合低 → 随机巧合，疑似噪音 (suspected_noise)
    - 正常社交行为 → 中性 (neutral)
    """
    agents = world.all()
    n = len(agents)

    snapshot = EmergenceValiditySnapshot(agent_count=n, coupling_threshold=0.5)

    if n < 2:
        snapshot.verdict = "insufficient_data"
        return snapshot

    # ── 1. 信息耦合 (Info Coupling) ──
    # Plan category coupling: 对每对 agent，若它们属于同一计划类别则计分
    plan_categories = [_classify_plan(getattr(a, "current_plan", None) or "") for a in agents]
    total_pairs = n * (n - 1) // 2

    plan_coupled_pairs = 0
    for i in range(n):
        for j in range(i + 1, n):
            if plan_categories[i] == plan_categories[j]:
                plan_coupled_pairs += 1

    plan_coupling = plan_coupled_pairs / total_pairs if total_pairs > 0 else 0.0

    # Location/spatial coupling: agent 对中距离 < 200px 的比例
    proximity_radius = 200
    location_coupled_pairs = 0
    for i in range(n):
        x1, y1 = agents[i].location
        for j in range(i + 1, n):
            x2, y2 = agents[j].location
            dist = math.hypot(x2 - x1, y2 - y1)
            if dist < proximity_radius:
                location_coupled_pairs += 1

    location_coupling = location_coupled_pairs / total_pairs if total_pairs > 0 else 0.0

    # Combined info_coupling
    info_coupling = plan_coupling * 0.6 + location_coupling * 0.4

    # ── 2. 行为一致性 (Behavioral Consistency) ──
    # Plan type alignment: 主导 plan 类型频率 / 总 agent 数
    type_counter = Counter(plan_categories)
    dominant_count = type_counter.most_common(1)[0][1] if type_counter else 0
    plan_alignment = dominant_count / n if n > 0 else 0.0

    # Mood alignment: 平均 pairwise 情绪向量余弦相似度
    mood_dims = ("joy", "fear", "anger", "sadness")
    mood_sims: list[float] = []
    for i in range(n):
        ms_i = getattr(agents[i], "mood_state", {}) or {}
        v1 = [ms_i.get(dim, 0.0) for dim in mood_dims]
        mag1 = math.sqrt(sum(a * a for a in v1))
        if mag1 == 0:
            continue
        for j in range(i + 1, n):
            ms_j = getattr(agents[j], "mood_state", {}) or {}
            v2 = [ms_j.get(dim, 0.0) for dim in mood_dims]
            mag2 = math.sqrt(sum(b * b for b in v2))
            if mag2 == 0:
                continue
            dot = sum(a * b for a, b in zip(v1, v2, strict=False))
            sim = dot / (mag1 * mag2)
            mood_sims.append(sim)

    mood_alignment = sum(mood_sims) / len(mood_sims) if mood_sims else 0.0

    # Combined behavioral consistency
    behavioral_consistency = plan_alignment * 0.5 + mood_alignment * 0.5

    # ── 3. 耦合增益 (Coupling Gain) ──
    coupling_gain = info_coupling / (behavioral_consistency + 0.01)

    # ── 4. 判定 ──
    if n < 5:
        verdict = "insufficient_data"
    elif coupling_gain > 1.5 and info_coupling > 0.2:
        verdict = "genuine"
    elif coupling_gain > 0.8:
        verdict = "neutral"
    elif coupling_gain <= 0.8 and behavioral_consistency > 0.3:
        verdict = "suspected_noise"
    else:
        verdict = "neutral"

    # ── 5. 有效性分数 (0-100) ──
    # 将 coupling_gain 映射到 0-100, 以 1.0 为中心 (耦合增益=1 时约50分)
    validity_score = min(100.0, max(0.0, (coupling_gain / 3.0) * 100.0))

    snapshot.coupling_gain = coupling_gain
    snapshot.info_coupling = info_coupling
    snapshot.behavioral_consistency = behavioral_consistency
    snapshot.validity_score = validity_score
    snapshot.verdict = verdict
    snapshot.details = {
        "plan_coupling": plan_coupling,
        "location_coupling": location_coupling,
        "plan_alignment": plan_alignment,
        "mood_alignment": mood_alignment,
    }

    return snapshot
