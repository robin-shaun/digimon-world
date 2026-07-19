"""
知识经济与科技树系统 (Knowledge Economy & Tech Tree)
==================================================

Phase 27: 数字世界的知识经济——agent 发明知识/技能、互相引用、知识沿社交网络传播、
世界级科技树解锁。

核心组件:
1. KnowledgeItem — 一条可被发明、引用、传播的知识条目
2. InventedSkill — 继承 KnowledgeItem，agent 发明的可释放技能
3. KnowledgePropagation — 知识沿社交网络（差序格局圈层）的传播逻辑
4. TechTree — 世界级科技树，节点按前置条件 + 引用数逐步解锁
5. KnowledgePool — 全局知识池单例，管理所有知识条目的增删查改

设计要点:
- 纯 Python 规则引擎，不依赖外部 LLM 调用
- 与 DigimonAgent / WorldState 通过 try/except ImportError 解耦
- ID 生成使用 hashlib（确定性）
- 差序格局传播依赖 Phase 21 RelationalCircle
- InventedSkill 继承自 Phase 5 Skill/SkillType

典型用法::

    from digimon_world.economy.knowledge_economy import (
        get_knowledge_pool, KnowledgePool, KnowledgeItem, InventedSkill, TechTree,
    )

    pool = get_knowledge_pool()
    pool.propagate()          # 每 tick 传播一轮
    pool.check_inventions()    # 检查 agent 是否有资格发明新技能
"""

from __future__ import annotations

import hashlib
import logging
import math
import random as _random_mod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar

# ---------------------------------------------------------------------------
# 可选导入（解耦，允许测试时隔离）
# ---------------------------------------------------------------------------

try:
    from ..agents.digimon_agent import DigimonAgent as _DigimonAgent

    _HAS_AGENT: bool = True
except ImportError:
    _DigimonAgent: Any = None  # type: ignore[no-redef]
    _HAS_AGENT = False

try:
    from ..agents.skills import Skill, SkillType

    _HAS_SKILLS: bool = True
except ImportError:
    Skill = None  # type: ignore[assignment]
    SkillType = None  # type: ignore[assignment]
    _HAS_SKILLS = False

try:
    from ..world.relationships import get_tracker as _get_relationship_tracker

    _HAS_RELATIONSHIPS: bool = True
except ImportError:
    _get_relationship_tracker = None  # type: ignore[assignment]
    _HAS_RELATIONSHIPS = False

try:
    from ..world.relational_circle import RelationalCircle

    _HAS_CIRCLE: bool = True
except ImportError:
    RelationalCircle = None  # type: ignore[assignment]
    _HAS_CIRCLE = False

logger = logging.getLogger(__name__)


# ===========================================================================
# 常量
# ===========================================================================

# 知识领域
DOMAINS: list[str] = ["battle", "survival", "social", "exploration", "crafting"]

# 传播基础概率
BASE_SPREAD_RATE: float = 0.10

# 圈层关系 → 传播概率乘数
CIRCLE_MULTIPLIER: dict[str, float] = {
    "inner": 1.0,
    "middle": 0.5,
    "outer": 0.1,
}

# 引用数加成: 每 1 次引用提升 5% 传播概率
CITATION_BOOST_PER_CITE: float = 0.05

# 发明触发条件
INVENTION_BATTLE_WINS: int = 5        # ≥5 场战斗胜利 → 可尝试 battle 领域发明
INVENTION_SOCIAL_MIN: int = 10        # ≥10 次社交互动 → 可尝试 social 领域发明
INVENTION_EXPLORE_DIST: float = 500.0  # 探索距离 >500 → 可尝试 exploration 领域发明

# 发明成功率（每 eligible domain 每 tick）
INVENTION_BASE_PROBABILITY: float = 0.30

# "热门"知识的最低引用数
HOT_CITATION_THRESHOLD: int = 3

# 最大每个 tick 新增知识数（防止爆炸）
MAX_INVENTIONS_PER_TICK: int = 3

# 传播时每个 agent 最多尝试传播几条知识
MAX_SPREAD_PER_AGENT: int = 3

# agent 知识容量上限（防止列表膨胀）
MAX_KNOWLEDGE_PER_AGENT: int = 50


# ===========================================================================
# 1. KnowledgeItem — 知识条目
# ===========================================================================

@dataclass
class KnowledgeItem:
    """一条可被发明、引用、传播的知识。

    Attributes:
        id: 唯一标识（SHA-256 hash）。
        name: 知识名称（中文）。
        domain: 领域（battle/survival/social/exploration/crafting）。
        description: 详细描述。
        inventor_id: 发明者 agent 名称（id）。
        created_at: 发明时间（UTC）。
        citation_count: 被引用次数。
        citations: 引用该知识的 agent id 列表。
        tags: 标签列表。
    """

    id: str
    name: str
    domain: str
    description: str
    inventor_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    citation_count: int = 0
    citations: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        name: str,
        domain: str,
        description: str,
        inventor_id: str,
        tags: list[str] | None = None,
    ) -> KnowledgeItem:
        """工厂方法：用 hashlib 生成确定性 ID。"""
        raw = f"{name}:{domain}:{inventor_id}:{description}"[:256]
        kid = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        return cls(
            id=kid,
            name=name,
            domain=domain,
            description=description,
            inventor_id=inventor_id,
            created_at=datetime.now(UTC),
            tags=tags if tags is not None else [],
        )

    def add_citation(self, agent_id: str) -> bool:
        """记录一次引用。自引用忽略，重复引用忽略。

        Returns:
            True 如果引用被接受（首次引用）。
        """
        if agent_id == self.inventor_id:
            return False
        if agent_id not in self.citations:
            self.citations.append(agent_id)
            self.citation_count = len(self.citations)
            return True
        return False

    @property
    def is_hot(self) -> bool:
        """是否为"热门"知识（引用数达到阈值）。"""
        return self.citation_count >= HOT_CITATION_THRESHOLD

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。"""
        return {
            "id": self.id,
            "name": self.name,
            "domain": self.domain,
            "description": self.description,
            "inventor_id": self.inventor_id,
            "created_at": self.created_at.isoformat(),
            "citation_count": self.citation_count,
            "citations": list(self.citations),
            "tags": list(self.tags),
            "is_hot": self.is_hot,
        }


# ===========================================================================
# 2. InventedSkill — agent 发明的技能（继承 KnowledgeItem）
# ===========================================================================

@dataclass
class InventedSkill(KnowledgeItem):
    """agent 发明的新技能，继承自 KnowledgeItem。

    Attributes (inherited):
        id, name, domain, description, inventor_id, created_at,
        citation_count, citations, tags

    Attributes (new):
        skill_type: 技能类型（PHYSICAL/FIRE/ICE/SPECIAL）。
        power: 威力值。
        cost: EP 消耗。
        prerequisites: 发明该技能所需的前置知识 ID 列表。
    """

    skill_type: str = "PHYSICAL"
    power: int = 30
    cost: int = 10
    prerequisites: list[str] = field(default_factory=list)

    @classmethod
    def create_skill(
        cls,
        name: str,
        domain: str,
        description: str,
        inventor_id: str,
        skill_type: str,
        power: int,
        cost: int,
        prerequisites: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> InventedSkill:
        """工厂方法：创建一个发明技能。"""
        raw = f"skill:{name}:{domain}:{inventor_id}:{skill_type}"
        kid = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        return cls(
            id=kid,
            name=name,
            domain=domain,
            description=description,
            inventor_id=inventor_id,
            created_at=datetime.now(UTC),
            skill_type=skill_type,
            power=power,
            cost=cost,
            prerequisites=prerequisites if prerequisites is not None else [],
            tags=tags if tags is not None else [],
        )

    def to_skill(self) -> Any:
        """转换为 Skill 对象（如果 skills 模块可用）。"""
        if Skill is None or SkillType is None:
            return None
        try:
            st = SkillType(self.skill_type.lower())
        except ValueError:
            st = SkillType.PHYSICAL
        return Skill(name=self.name, type=st, power=self.power, cost=self.cost)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。"""
        d = super().to_dict()
        d.update({
            "skill_type": self.skill_type,
            "power": self.power,
            "cost": self.cost,
            "prerequisites": list(self.prerequisites),
            "is_invented_skill": True,
        })
        return d


# ===========================================================================
# 3. TechTree — 世界级科技树
# ===========================================================================

# 预定义科技树节点（10 个）
_PREDEFINED_TECH_NODES: list[dict[str, Any]] = [
    {
        "id": "tech_battle_basic",
        "name": "战斗基础",
        "domain": "battle",
        "prerequisite_node_ids": [],
        "required_citation_count": 0,
    },
    {
        "id": "tech_flame_mastery",
        "name": "火焰掌控",
        "domain": "battle",
        "prerequisite_node_ids": ["tech_battle_basic"],
        "required_citation_count": 5,
    },
    {
        "id": "tech_survival_instinct",
        "name": "生存直觉",
        "domain": "survival",
        "prerequisite_node_ids": [],
        "required_citation_count": 0,
    },
    {
        "id": "tech_herbology",
        "name": "草药学",
        "domain": "survival",
        "prerequisite_node_ids": ["tech_survival_instinct"],
        "required_citation_count": 3,
    },
    {
        "id": "tech_social_bond",
        "name": "社交纽带",
        "domain": "social",
        "prerequisite_node_ids": [],
        "required_citation_count": 0,
    },
    {
        "id": "tech_leadership",
        "name": "领袖气质",
        "domain": "social",
        "prerequisite_node_ids": ["tech_social_bond"],
        "required_citation_count": 8,
    },
    {
        "id": "tech_terrain_awareness",
        "name": "地形认知",
        "domain": "exploration",
        "prerequisite_node_ids": [],
        "required_citation_count": 0,
    },
    {
        "id": "tech_ancient_ruins",
        "name": "远古遗迹",
        "domain": "exploration",
        "prerequisite_node_ids": ["tech_terrain_awareness"],
        "required_citation_count": 10,
    },
    {
        "id": "tech_tool_crafting",
        "name": "工具制作",
        "domain": "crafting",
        "prerequisite_node_ids": ["tech_survival_instinct", "tech_terrain_awareness"],
        "required_citation_count": 5,
    },
    {
        "id": "tech_elemental_weapons",
        "name": "元素武器",
        "domain": "crafting",
        "prerequisite_node_ids": ["tech_tool_crafting", "tech_flame_mastery"],
        "required_citation_count": 15,
    },
]


@dataclass
class TechNode:
    """科技树中的一个节点。

    Attributes:
        id: 唯一标识。
        name: 节点名称（中文）。
        domain: 所属领域。
        description: 描述。
        prerequisite_node_ids: 前置节点 ID 列表。
        required_citation_count: 解锁本节点需要的前置节点总引用数。
        unlocked: 是否已解锁。
        unlocked_at: 解锁时的 world tick。
    """

    id: str
    name: str
    domain: str = "general"
    description: str = ""
    prerequisite_node_ids: list[str] = field(default_factory=list)
    required_citation_count: int = 0
    unlocked: bool = False
    unlocked_at: int = -1

    def is_unlockable(
        self,
        unlocked_node_ids: set[str],
        prerequisite_citation_total: int,
    ) -> bool:
        """检查是否满足解锁条件。

        Args:
            unlocked_node_ids: 已解锁的节点 ID 集合。
            prerequisite_citation_total: 前置节点所关联知识的总引用数。

        Returns:
            True 如果所有前置节点已解锁 且 引用数达到要求。
        """
        if self.unlocked:
            return False
        # 所有前置节点必须已解锁
        if not set(self.prerequisite_node_ids).issubset(unlocked_node_ids):
            return False
        # 引用数达标
        if prerequisite_citation_total < self.required_citation_count:
            return False
        return True

    def unlock(self, tick: int) -> bool:
        """解锁本节点。

        Returns:
            True 如果是首次解锁。
        """
        if self.unlocked:
            return False
        self.unlocked = True
        self.unlocked_at = tick
        logger.info(
            "🔓 TechTree 节点解锁: %s (%s) @ tick %d",
            self.name, self.id, tick,
        )
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "domain": self.domain,
            "description": self.description,
            "prerequisite_node_ids": list(self.prerequisite_node_ids),
            "required_citation_count": self.required_citation_count,
            "unlocked": self.unlocked,
            "unlocked_at": self.unlocked_at,
        }


class TechTree:
    """世界级科技树，管理所有 TechNode 的解锁逻辑。

    解锁条件：
    1. 所有前置节点已解锁。
    2. 前置节点关联知识的总引用数 ≥ required_citation_count。
    """

    def __init__(self) -> None:
        self._nodes: dict[str, TechNode] = {}
        self._node_knowledge_map: dict[str, list[str]] = defaultdict(list)
        self._init_predefined()

    def _init_predefined(self) -> None:
        """初始化预定义的 10 个科技节点。"""
        for raw in _PREDEFINED_TECH_NODES:
            node = TechNode(
                id=raw["id"],
                name=raw["name"],
                domain=raw["domain"],
                prerequisite_node_ids=list(raw["prerequisite_node_ids"]),
                required_citation_count=raw["required_citation_count"],
            )
            self._nodes[node.id] = node

    @property
    def nodes(self) -> dict[str, TechNode]:
        """所有节点（只读）。"""
        return self._nodes

    def get_node(self, node_id: str) -> TechNode | None:
        """按 ID 获取节点。"""
        return self._nodes.get(node_id)

    def get_unlocked_nodes(self) -> list[TechNode]:
        """获取所有已解锁节点。"""
        return [n for n in self._nodes.values() if n.unlocked]

    def get_by_domain(self, domain: str) -> list[TechNode]:
        """按领域获取节点。"""
        return [n for n in self._nodes.values() if n.domain == domain]

    def link_knowledge(self, node_id: str, knowledge_id: str) -> None:
        """将一条知识关联到科技节点。"""
        if node_id in self._nodes:
            self._node_knowledge_map[node_id].append(knowledge_id)

    def get_prerequisite_citation_total(self, node_id: str, knowledge_pool: KnowledgePool) -> int:
        """计算某节点的前置节点关联知识的总引用数。

        遍历所有前置节点，汇总它们关联知识的 citation_count。
        这是解锁本节点所需的引用数判断依据。
        """
        node = self._nodes.get(node_id)
        if node is None:
            return 0
        total = 0
        for prereq_id in node.prerequisite_node_ids:
            kid_list = self._node_knowledge_map.get(prereq_id, [])
            for kid in kid_list:
                ki = knowledge_pool.get(kid)
                if ki is not None:
                    total += ki.citation_count
        return total

    def get_node_citation_total(self, node_id: str, knowledge_pool: KnowledgePool) -> int:
        """计算某节点自身关联知识的总引用数。"""
        kid_list = self._node_knowledge_map.get(node_id, [])
        total = 0
        for kid in kid_list:
            ki = knowledge_pool.get(kid)
            if ki is not None:
                total += ki.citation_count
        return total

    def check_unlocks(self, knowledge_pool: KnowledgePool, tick: int) -> list[TechNode]:
        """检查所有未解锁节点是否满足条件，并尝试解锁。

        解锁条件：
        1. 所有前置节点已解锁。
        2. 前置节点关联知识的总引用数 ≥ required_citation_count。

        Args:
            knowledge_pool: 知识池引用。
            tick: 当前 world tick。

        Returns:
            本 tick 新解锁的节点列表。
        """
        unlocked_ids = {n.id for n in self._nodes.values() if n.unlocked}
        newly_unlocked: list[TechNode] = []

        for node in self._nodes.values():
            if node.unlocked:
                continue
            citation_total = self.get_prerequisite_citation_total(node.id, knowledge_pool)
            if node.is_unlockable(unlocked_ids, citation_total):
                node.unlock(tick)
                newly_unlocked.append(node)
                unlocked_ids.add(node.id)  # 级联：本 tick 内后续节点也能用

        return newly_unlocked

    def stats(self) -> dict[str, Any]:
        """科技树统计。"""
        total = len(self._nodes)
        unlocked = sum(1 for n in self._nodes.values() if n.unlocked)
        return {
            "total_nodes": total,
            "unlocked_nodes": unlocked,
            "unlock_percentage": round(unlocked / total * 100, 1) if total else 0,
            "by_domain": {
                d: sum(1 for n in self._nodes.values() if n.domain == d and n.unlocked)
                for d in DOMAINS
            },
        }

    def reset(self) -> None:
        """重置所有节点为未解锁状态（测试用）。"""
        for node in self._nodes.values():
            node.unlocked = False
            node.unlocked_at = -1
        self._node_knowledge_map.clear()

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": {k: v.to_dict() for k, v in self._nodes.items()},
            "node_knowledge_map": {
                k: list(v) for k, v in self._node_knowledge_map.items()
            },
        }


# ===========================================================================
# 4. KnowledgePropagation — 知识传播引擎
# ===========================================================================

class KnowledgePropagation:
    """知识沿社交网络的传播逻辑。

    传播规则:
    - 每个 tick，对每条知识，每个知道它的 agent 有概率传播给附近的 agent。
    - 概率 = BASE_SPREAD_RATE × 圈层乘数 × (1 + CITATION_BOOST_PER_CITE × citation_count)
    - 圈层: inner=1.0, middle=0.5, outer=0.1（基于 RelationalCircle）
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = _random_mod.Random(seed)

    def _classify_relationship(
        self, agent_a: str, agent_b: str
    ) -> str:
        """根据关系得分确定圈层。

        Returns:
            "inner" | "middle" | "outer" | "none"
        """
        if not _HAS_CIRCLE or not _HAS_RELATIONSHIPS:
            return "middle"  # 默认中圈
        try:
            # Phase 21 RelationalCircle 与 Phase 6 RelationshipTracker 集成
            tracker = _get_relationship_tracker()  # type: ignore[misc]
            composite = tracker.get_composite_score(agent_a, agent_b)
            circle = RelationalCircle.from_composite(composite)  # type: ignore[union-attr]
            # 映射到三圈模型
            if circle in (
                RelationalCircle.INTIMATE,  # type: ignore[union-attr]
                RelationalCircle.FRIENDLY,  # type: ignore[union-attr]
            ):
                return "inner"
            elif circle == RelationalCircle.ACQUAINTANCE:  # type: ignore[union-attr]
                return "middle"
            elif circle == RelationalCircle.NEUTRAL:  # type: ignore[union-attr]
                return "outer"
            else:  # HOSTILE
                return "outer"
        except Exception:
            return "middle"

    def _compute_spread_probability(
        self,
        relationship_circle: str,
        citation_count: int,
    ) -> float:
        """计算传播概率。

        p = BASE_SPREAD_RATE × circle_multiplier × (1 + citation_boost_per_cite × citation_count)
        """
        circle_mult = CIRCLE_MULTIPLIER.get(relationship_circle, 0.1)
        citation_boost = 1.0 + CITATION_BOOST_PER_CITE * citation_count
        return BASE_SPREAD_RATE * circle_mult * citation_boost

    def propagate_one(
        self,
        source_agent_id: str,
        target_agent_id: str,
        knowledge: KnowledgeItem,
        tick: int = 0,
    ) -> bool:
        """尝试将一条知识从 source 传播到 target。

        Args:
            source_agent_id: 源 agent。
            target_agent_id: 目标 agent。
            knowledge: 要传播的知识。
            tick: 当前 world tick。

        Returns:
            True 如果传播成功。
        """
        if source_agent_id == target_agent_id:
            return False

        circle = self._classify_relationship(source_agent_id, target_agent_id)
        prob = self._compute_spread_probability(circle, knowledge.citation_count)

        if self._rng.random() < prob:
            knowledge.add_citation(target_agent_id)
            logger.debug(
                "📡 知识传播: %s → %s (%s, 圈层=%s, p=%.3f)",
                source_agent_id, target_agent_id, knowledge.name, circle, prob,
            )
            return True
        return False

    def set_seed(self, seed: int) -> None:
        """重置随机种子。"""
        self._rng = _random_mod.Random(seed)


# ===========================================================================
# 5. KnowledgePool — 全局知识池（单例）
# ===========================================================================

class KnowledgePool:
    """全局知识池：管理所有 KnowledgeItem，提供增删查改 + 传播 + 发明。

    Attributes:
        _items: id → KnowledgeItem
        _agent_knowledge: agent_id → set[knowledge_id]（agent 知道哪些知识）
        _inventor_index: inventor_id → list[knowledge_id]
        _tech_tree: TechTree 实例
        _propagation: KnowledgePropagation 实例
        _tick_invention_count: 每个 tick 的发明计数（防爆）
        _current_tick: 当前 tick
    """

    def __init__(self, seed: int | None = None) -> None:
        self._items: dict[str, KnowledgeItem] = {}
        self._agent_knowledge: dict[str, set[str]] = defaultdict(set)
        self._inventor_index: dict[str, list[str]] = defaultdict(list)
        self._tech_tree = TechTree()
        self._propagation = KnowledgePropagation(seed=seed)
        self._rng = _random_mod.Random(seed)
        self._tick_invention_count: int = 0
        self._current_tick: int = 0

    # ---- 基本 CRUD ----

    def add_knowledge(self, item: KnowledgeItem) -> KnowledgeItem:
        """添加一条知识到池中。

        自动地将知识注册到发明者名下，并尝试将知识关联到对应领域的科技节点。
        """
        self._items[item.id] = item
        self._agent_knowledge[item.inventor_id].add(item.id)
        self._inventor_index[item.inventor_id].append(item.id)

        # 尝试关联到科技树节点（同领域、名称匹配的首个节点）
        for node in self._tech_tree.nodes.values():
            if node.domain == item.domain and item.name in node.name:
                self._tech_tree.link_knowledge(node.id, item.id)
                break

        logger.info(
            "📚 知识入库: %s (%s) by %s [%s]",
            item.name, item.id, item.inventor_id, item.domain,
        )
        return item

    def get(self, knowledge_id: str) -> KnowledgeItem | None:
        """按 ID 获取知识。"""
        return self._items.get(knowledge_id)

    def get_by_domain(self, domain: str) -> list[KnowledgeItem]:
        """按领域获取所有知识。"""
        return [ki for ki in self._items.values() if ki.domain == domain]

    def get_hot(self, n: int = 10) -> list[KnowledgeItem]:
        """获取热门知识（按引用数降序，引用数 ≥ HOT_CITATION_THRESHOLD）。"""
        hot = [ki for ki in self._items.values() if ki.is_hot]
        hot.sort(key=lambda ki: ki.citation_count, reverse=True)
        return hot[:n]

    def get_by_inventor(self, inventor_id: str) -> list[KnowledgeItem]:
        """按发明者获取所有知识。"""
        kid_list = self._inventor_index.get(inventor_id, [])
        return [self._items[kid] for kid in kid_list if kid in self._items]

    def agent_knows(self, agent_id: str, knowledge_id: str) -> bool:
        """查询 agent 是否知道某条知识。"""
        return knowledge_id in self._agent_knowledge.get(agent_id, set())

    def agent_known_items(self, agent_id: str) -> list[KnowledgeItem]:
        """获取 agent 已知的所有知识条目。"""
        kid_set = self._agent_knowledge.get(agent_id, set())
        return [self._items[kid] for kid in kid_set if kid in self._items]

    def agent_learn(self, agent_id: str, knowledge_id: str) -> bool:
        """让 agent 学习某条知识（如果容量未满）。"""
        if knowledge_id not in self._items:
            return False
        known = self._agent_knowledge[agent_id]
        if len(known) >= MAX_KNOWLEDGE_PER_AGENT:
            return False
        if knowledge_id in known:
            return False
        known.add(knowledge_id)
        return True

    # ---- 传播 ----

    def propagate(self, current_tick: int = 0) -> int:
        """执行一轮知识传播。

        对每条知识，遍历所有知道它的 agent，尝试传播给一个随机 agent。

        Args:
            current_tick: 当前 world tick。

        Returns:
            本 tick 成功传播的次数。
        """
        self._current_tick = current_tick
        self._tick_invention_count = 0
        spread_count = 0

        # 获取所有 agent 名称列表（从 agent_knowledge 和 items 推断）
        all_agents = set(self._agent_knowledge.keys())
        all_agents.update(ki.inventor_id for ki in self._items.values())
        agent_list = list(all_agents)

        if len(agent_list) < 2:
            return 0

        for knowledge_id, ki in list(self._items.items()):
            # 知道此知识的 agent
            knowers = [
                a for a in agent_list
                if knowledge_id in self._agent_knowledge.get(a, set())
                or a == ki.inventor_id
            ]
            if not knowers:
                continue

            # 每个 knower 最多尝试传播 MAX_SPREAD_PER_AGENT 条
            attempts = min(len(knowers), MAX_SPREAD_PER_AGENT)
            selected_knowers = self._rng.sample(knowers, attempts) if len(knowers) > attempts else knowers

            for knower in selected_knowers:
                # 随机选一个不认识的 target
                non_knowers = [a for a in agent_list if a != knower and knowledge_id not in self._agent_knowledge.get(a, set())]
                if not non_knowers:
                    continue
                target = self._rng.choice(non_knowers)

                if self._propagation.propagate_one(knower, target, ki, current_tick):
                    self.agent_learn(target, knowledge_id)
                    spread_count += 1

        if spread_count > 0:
            logger.info("📡 知识传播: %d 次成功 @ tick %d", spread_count, current_tick)

        return spread_count

    # ---- 发明检查 ----

    def _agent_eligible_domains(self, agent: Any) -> list[str]:
        """判断 agent 在哪些领域有资格尝试发明。

        - battle: battle_victories ≥ 5
        - social: 与前10名 agent 的平均关系得分 > 0 → 等效 ≥10 次社交互动
        - exploration: location 距离原点 >500
        - survival: 总是有资格（生存是基础）
        - crafting: 当 agent 已知道至少 1 条 crafting 知识时
        """
        eligible: list[str] = []

        # battle: 检查 battle_victories
        battle_wins = getattr(agent, "battle_victories", 0)
        if isinstance(battle_wins, int) and battle_wins >= INVENTION_BATTLE_WINS:
            eligible.append("battle")

        # social: 检查关系数量或关系得分
        # 我们将 ≥10 次社交互动映射为: agent 至少有 1 个正向关系朋友
        if _HAS_RELATIONSHIPS:
            try:
                tracker = _get_relationship_tracker()  # type: ignore[misc]
                agent_name = getattr(agent, "name", "")
                all_pairs = tracker.all_pairs()
                friend_count = sum(
                    1 for p in all_pairs
                    if (p["a"] == agent_name or p["b"] == agent_name)
                    and p.get("score", 0) > 0
                )
                if friend_count > 0:
                    # 将"有正向朋友"视为社交足迹
                    eligible.append("social")
            except Exception:
                pass

        # survival: 总是有资格
        eligible.append("survival")

        # exploration: 检查 location 距离原点
        loc = getattr(agent, "location", (0, 0))
        if isinstance(loc, (tuple, list)) and len(loc) >= 2:
            dist = math.sqrt(loc[0] ** 2 + loc[1] ** 2)
            if dist > INVENTION_EXPLORE_DIST:
                eligible.append("exploration")

        # crafting: agent 已知至少 1 条 crafting 知识
        agent_name = getattr(agent, "name", "")
        crafting_known = any(
            ki.domain == "crafting"
            for ki in self.agent_known_items(agent_name)
        )
        if crafting_known:
            eligible.append("crafting")

        return eligible

    def _build_skill_name(self, domain: str, inventor_name: str) -> tuple[str, str]:
        """根据领域生成技能名称和描述。"""
        templates: dict[str, tuple[str, str]] = {
            "battle": (
                f"{inventor_name}的战斗心得",
                f"{inventor_name}在无数次战斗中领悟的格斗技巧。",
            ),
            "survival": (
                f"{inventor_name}的生存秘术",
                f"{inventor_name}在恶劣环境中摸索出的生存之道。",
            ),
            "social": (
                f"{inventor_name}的社交智慧",
                f"{inventor_name}通过频繁互动领悟的社交策略。",
            ),
            "exploration": (
                f"{inventor_name}的探索日志",
                f"{inventor_name}长途跋涉中发现的地形与资源知识。",
            ),
            "crafting": (
                f"{inventor_name}的工匠技艺",
                f"{inventor_name}结合多种知识创造出的制作方法。",
            ),
        }
        return templates.get(domain, (f"{domain}知识", f"{inventor_name}发现的{domain}知识"))

    def _invent_skill_for_domain(
        self, agent: Any, domain: str
    ) -> InventedSkill | None:
        """尝试在指定领域为 agent 发明一个新技能。

        规则（Deterministic，无 LLM）:
        - 基于先有知识的组合（如果 agent 在 domain 已有 ≥2 条知识 → 更容易发明）
        - 成功率 ~30%
        - 技能威力由 battle_victories + 已有知识数决定
        """
        agent_name = getattr(agent, "name", "unknown")

        # 查找 agent 在该领域已有的知识作为前置
        agent_items = self.agent_known_items(agent_name)
        domain_knowledge = [ki for ki in agent_items if ki.domain == domain]
        prereq_ids = [ki.id for ki in domain_knowledge[:3]]

        # 技能类型映射
        skill_type_map = {
            "battle": "PHYSICAL",
            "survival": "SPECIAL",
            "social": "SPECIAL",
            "exploration": "SPECIAL",
            "crafting": "FIRE",
        }

        # 威力：基于 battle_victories + 已有知识数
        battle_wins = getattr(agent, "battle_victories", 0)
        base_power = 20 + len(domain_knowledge) * 5 + battle_wins * 2
        power = min(100, base_power)
        cost = max(5, power // 3)

        name, desc = self._build_skill_name(domain, agent_name)

        skill = InventedSkill.create_skill(
            name=name,
            domain=domain,
            description=desc,
            inventor_id=agent_name,
            skill_type=skill_type_map.get(domain, "PHYSICAL"),
            power=power,
            cost=cost,
            prerequisites=prereq_ids,
            tags=[domain, "invented"],
        )

        self.add_knowledge(skill)
        logger.info(
            "💡 技能发明: %s 发明了 %s (power=%d, cost=%d, domain=%s)",
            agent_name, skill.name, power, cost, domain,
        )
        return skill

    def check_inventions(
        self, agents: list[Any] | None = None, current_tick: int = 0
    ) -> list[InventedSkill]:
        """检查是否有 agent 满足发明条件，并触发发明。

        Args:
            agents: agent 列表（None 时尝试从 world_state 获取）。
            current_tick: 当前 world tick。

        Returns:
            本 tick 新发明的技能列表。
        """
        if self._tick_invention_count >= MAX_INVENTIONS_PER_TICK:
            return []

        self._current_tick = current_tick

        # 获取 agent 列表
        if agents is None:
            try:
                from ..world.world_state import get_world
                world = get_world()
                agents = list(world.agents.values())
            except Exception:
                return []

        new_skills: list[InventedSkill] = []

        # 打乱顺序（避免总是前面几个 agent 发明）
        shuffled = list(agents)
        self._rng.shuffle(shuffled)

        for agent in shuffled:
            if self._tick_invention_count >= MAX_INVENTIONS_PER_TICK:
                break

            eligible_domains = self._agent_eligible_domains(agent)
            if not eligible_domains:
                continue

            # 对每个 eligible domain 以 ~30% 概率尝试发明
            for domain in eligible_domains:
                if self._tick_invention_count >= MAX_INVENTIONS_PER_TICK:
                    break
                if self._rng.random() < INVENTION_BASE_PROBABILITY:
                    skill = self._invent_skill_for_domain(agent, domain)
                    if skill is not None:
                        new_skills.append(skill)
                        self._tick_invention_count += 1

        return new_skills

    # ---- 科技树 ----

    @property
    def tech_tree(self) -> TechTree:
        """科技树实例。"""
        return self._tech_tree

    def check_tech_unlocks(self, tick: int = 0) -> list[TechNode]:
        """检查并尝试解锁科技树节点。"""
        return self._tech_tree.check_unlocks(self, tick)

    # ---- 统计 & 序列化 ----

    def stats(self) -> dict[str, Any]:
        """知识池统计信息。"""
        return {
            "total_knowledge": len(self._items),
            "total_skills": sum(1 for ki in self._items.values() if isinstance(ki, InventedSkill)),
            "by_domain": {
                d: sum(1 for ki in self._items.values() if ki.domain == d)
                for d in DOMAINS
            },
            "hot_count": sum(1 for ki in self._items.values() if ki.is_hot),
            "total_agents_with_knowledge": len(self._agent_knowledge),
            "tech_tree": self._tech_tree.stats(),
        }

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。"""
        return {
            "items": {k: v.to_dict() for k, v in self._items.items()},
            "agent_knowledge": {
                k: list(v) for k, v in self._agent_knowledge.items()
            },
            "tech_tree": self._tech_tree.to_dict(),
            "stats": self.stats(),
        }

    def reset(self) -> None:
        """重置知识池（测试用）。"""
        self._items.clear()
        self._agent_knowledge.clear()
        self._inventor_index.clear()
        self._tech_tree.reset()
        self._tick_invention_count = 0
        self._current_tick = 0


# ===========================================================================
# 单例管理
# ===========================================================================

_pool_instance: KnowledgePool | None = None


def get_knowledge_pool(seed: int | None = None) -> KnowledgePool:
    """获取（或延迟初始化）全局知识池单例。

    Args:
        seed: 可选随机种子（仅首次初始化时生效）。
    """
    global _pool_instance
    if _pool_instance is None:
        _pool_instance = KnowledgePool(seed=seed)
    return _pool_instance


def reset_knowledge_pool() -> None:
    """重置知识池单例（测试用）。"""
    global _pool_instance
    if _pool_instance is not None:
        _pool_instance.reset()
    _pool_instance = None


# ===========================================================================
# 导出
# ===========================================================================

__all__ = [
    # 常量
    "BASE_SPREAD_RATE",
    "CIRCLE_MULTIPLIER",
    "DOMAINS",
    "HOT_CITATION_THRESHOLD",
    "INVENTION_BASE_PROBABILITY",
    "MAX_INVENTIONS_PER_TICK",
    "MAX_KNOWLEDGE_PER_AGENT",
    "MAX_SPREAD_PER_AGENT",
    # 数据结构
    "InventedSkill",
    "KnowledgeItem",
    "TechNode",
    # 引擎
    "KnowledgePool",
    "KnowledgePropagation",
    "TechTree",
    # 单例
    "get_knowledge_pool",
    "reset_knowledge_pool",
]
