"""
世代传承系统 (Lineage System) — Phase 30
=========================================

数码世界的人口不是静止的——数码兽繁衍后代，形成家族树，世代交替。
本模块提供完整的族谱追踪和特质遗传计算。

核心组件:
- LineageRecord: 不可变的亲子关系记录（父母 → 子女 + 出生 tick + 世代编号）
- LineageTracker: 全局族谱管理器（注册/查询/统计）
- InheritanceEngine: 子代特质遗传计算（人格/知识/徽章亲和力）

设计原则:
- 纯数据驱动，无 LLM 依赖
- 族谱记录 append-only，写入后不可修改
- 查询复杂度 O(1)（哈希表索引）用于单 agent 查询
- 遗传规则以父母平均值 + jitter 为基础，可扩展

基础设施: Phase 5 (breeding) + Phase 8 (evolution) + Phase 26 (personality dynamics)
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LineageRecord — 不可变的亲子关系记录
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LineageRecord:
    """一条不可变的亲子关系记录。

    Attributes:
        parent_a: 父/母 A 的名字。
        parent_b: 父/母 B 的名字。
        child: 子代名字。
        tick_born: 子代出生的世界 tick。
        generation: 子代的世代编号（Gen 0 = 始祖，Gen 1 = 始祖的子代...）。
        child_species: 子代出生时的物种。
    """

    parent_a: str
    parent_b: str
    child: str
    tick_born: int
    generation: int
    child_species: str = ""

    def parents(self) -> tuple[str, str]:
        """返回父母名字对（字典序排序）。"""
        return (self.parent_a, self.parent_b) if self.parent_a <= self.parent_b else (self.parent_b, self.parent_a)

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_a": self.parent_a,
            "parent_b": self.parent_b,
            "child": self.child,
            "tick_born": self.tick_born,
            "generation": self.generation,
            "child_species": self.child_species,
        }


# ---------------------------------------------------------------------------
# LineageTracker — 全局族谱管理器
# ---------------------------------------------------------------------------


class LineageTracker:
    """全局族谱追踪器。

    管理所有亲子关系记录，提供快速查询:
    - 某数码兽的父母是谁
    - 某数码兽的子女是谁
    - 某数码兽的兄弟姐妹是谁
    - 某数码兽的世代编号
    - 全族统计（总代数、最大代数、最多产的家族等）
    """

    def __init__(self) -> None:
        self._records: list[LineageRecord] = []
        # 索引: name → list[LineageRecord] (该 name 作为 parent 或 child 的所有记录)
        self._by_name: dict[str, list[LineageRecord]] = {}
        # 索引: child_name → LineageRecord
        self._by_child: dict[str, LineageRecord] = {}
        # 世代 → name 列表
        self._by_generation: dict[int, list[str]] = {}
        # 世代计数器: name → generation
        self._generation_of: dict[str, int] = {}

    # ── 注册 ──────────────────────────────────────────

    def register(
        self,
        parent_a: str,
        parent_b: str,
        child: str,
        tick_born: int,
        child_species: str = "",
    ) -> LineageRecord:
        """注册一条亲子关系。

        自动计算子代的世代编号 = max(父母世代) + 1。
        始祖数码兽（无父母记录）默认为 Gen 0，由外部在初始化时设置。

        Args:
            parent_a: 父/母 A 的名字。
            parent_b: 父/母 B 的名字。
            child: 子代名字。
            tick_born: 出生 tick。
            child_species: 子代物种。

        Returns:
            新创建的 LineageRecord（不可变）。

        Raises:
            ValueError: 如果 child 已在族谱中。
        """
        if child in self._by_child:
            raise ValueError(f"Child '{child}' already registered in lineage")

        # 计算世代: max(父母世代) + 1, 父母无记录时视为 Gen 0
        gen_a = self._generation_of.get(parent_a, 0)
        gen_b = self._generation_of.get(parent_b, 0)
        generation = max(gen_a, gen_b) + 1

        record = LineageRecord(
            parent_a=parent_a,
            parent_b=parent_b,
            child=child,
            tick_born=tick_born,
            generation=generation,
            child_species=child_species,
        )

        self._records.append(record)
        self._by_child[child] = record
        self._generation_of[child] = generation

        # 更新 by_name 索引
        for name in (parent_a, parent_b, child):
            if name not in self._by_name:
                self._by_name[name] = []
            self._by_name[name].append(record)

        # 更新 by_generation
        if generation not in self._by_generation:
            self._by_generation[generation] = []
        self._by_generation[generation].append(child)

        logger.debug("Lineage registered: %s + %s → %s (Gen %d, tick %d)", parent_a, parent_b, child, generation, tick_born)
        return record

    def set_founder(self, name: str) -> None:
        """将某数码兽标记为始祖（Gen 0），如果尚未在族谱中。

        不会覆盖已有的世代编号。
        """
        if name not in self._generation_of:
            self._generation_of[name] = 0

    def set_founders(self, names: list[str]) -> None:
        """批量标记始祖。"""
        for name in names:
            self.set_founder(name)

    # ── 查询 — 单 agent ───────────────────────────────

    def get_parents(self, name: str) -> tuple[str, str] | None:
        """获取某数码兽的父母名字对。无记录返回 None。"""
        record = self._by_child.get(name)
        if record is None:
            return None
        return record.parents()

    def get_children(self, name: str) -> list[str]:
        """获取某数码兽的所有子女名字列表。"""
        children: list[str] = []
        for rec in self._by_name.get(name, []):
            if name in (rec.parent_a, rec.parent_b) and rec.child not in children:
                children.append(rec.child)
        return sorted(children)

    def get_siblings(self, name: str) -> list[str]:
        """获取某数码兽的兄弟姐妹（共享至少一个父母的其他子女）。"""
        parents = self.get_parents(name)
        if parents is None:
            return []
        pa, pb = parents
        siblings: set[str] = set()
        for rec in self._records:
            if (rec.parent_a == pa or rec.parent_a == pb or rec.parent_b == pa or rec.parent_b == pb) and rec.child != name:
                siblings.add(rec.child)
        return sorted(siblings)

    def get_generation(self, name: str) -> int | None:
        """获取某数码兽的世代编号。无记录返回 None。"""
        return self._generation_of.get(name)

    def get_record(self, name: str) -> LineageRecord | None:
        """获取某数码兽（作为子代）的亲子记录。始祖返回 None。"""
        return self._by_child.get(name)

    # ── 查询 — 家族树 ─────────────────────────────────

    def get_ancestors(self, name: str, max_depth: int = 10) -> list[str]:
        """递归获取所有祖先名字（按辈分从近到远排列）。"""
        ancestors: list[str] = []
        current = name
        for _ in range(max_depth):
            record = self._by_child.get(current)
            if record is None:
                break
            ancestors.append(record.parent_a)
            ancestors.append(record.parent_b)
            # 继续追溯 parent_a 的血脉（走一条线即可覆盖两侧）
            current = record.parent_a
        return ancestors

    def get_descendants(self, name: str) -> list[str]:
        """获取某数码兽的所有后代（递归）。"""
        descendants: list[str] = []
        queue = self.get_children(name)
        while queue:
            child = queue.pop(0)
            if child not in descendants:
                descendants.append(child)
                queue.extend(self.get_children(child))
        return sorted(descendants)

    def get_family_tree(self, name: str) -> dict[str, Any]:
        """以 name 为中心构建家族树字典。

        Returns:
            {
                "name": str,
                "generation": int | None,
                "parents": [str, str] | null,
                "children": [str, ...],
                "siblings": [str, ...],
                "descendants_count": int,
            }
        """
        parents = self.get_parents(name)
        return {
            "name": name,
            "generation": self.get_generation(name),
            "parents": list(parents) if parents else None,
            "children": self.get_children(name),
            "siblings": self.get_siblings(name),
            "descendants_count": len(self.get_descendants(name)),
        }

    # ── 统计 ───────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """全局族谱统计。

        Returns:
            {
                "total_records": int,        # 总亲子记录数
                "total_generations": int,    # 总代数
                "deepest_generation": int,   # 最深代数
                "gen_distribution": dict,    # 每代个体数
                "most_children": str | None, # 最多产的数码兽
                "most_children_count": int,
                "founders": [str, ...],      # 始祖列表 (Gen 0)
            }
        """
        founders = [name for name, gen in self._generation_of.items() if gen == 0]

        # 最深代数
        deepest = max(self._generation_of.values()) if self._generation_of else 0

        # 最多产: 统计每个 name 作为 parent 出现的次数
        parent_counts: dict[str, int] = {}
        for rec in self._records:
            parent_counts[rec.parent_a] = parent_counts.get(rec.parent_a, 0) + 1
            parent_counts[rec.parent_b] = parent_counts.get(rec.parent_b, 0) + 1

        most_children_name = None
        most_children_count = 0
        for name, count in parent_counts.items():
            if count > most_children_count:
                most_children_count = count
                most_children_name = name

        return {
            "total_records": len(self._records),
            "total_generations": deepest + 1 if self._generation_of else 0,
            "deepest_generation": deepest,
            "gen_distribution": {str(k): len(v) for k, v in sorted(self._by_generation.items())},
            "most_children": most_children_name,
            "most_children_count": most_children_count,
            "founders": sorted(founders),
        }

    def all_records(self) -> list[LineageRecord]:
        """返回所有亲子记录（按注册顺序）。"""
        return list(self._records)

    def reset(self) -> None:
        """清空所有族谱数据（主要用于测试）。"""
        self._records.clear()
        self._by_name.clear()
        self._by_child.clear()
        self._by_generation.clear()
        self._generation_of.clear()


# ---------------------------------------------------------------------------
# InheritanceEngine — 特质遗传计算
# ---------------------------------------------------------------------------

# 遗传的默认参数
DEFAULT_INHERITANCE_STRENGTH = 0.6   # 子代从父母平均值继承的比例 (0-1)
DEFAULT_INHERITANCE_JITTER = 0.15    # 随机抖动幅度
DEFAULT_MUTATION_CHANCE = 0.05       # 完全随机突变的概率（非父母任何一方）


@dataclass
class InheritedTraits:
    """子代从父母继承的综合特质。

    Attributes:
        personality_vector: 四维人格向量 (E/I, S/N, T/F, J/P)，每维 0-1。
        knowledge_affinity: 知识领域亲和力映射 {domain: affinity 0-1}。
        crest_affinity: 徽章亲和力映射 {crest_name: affinity 0-1}。
        attribute_bias: 属性偏向映射 {attribute: weight}（用于决定子代属性）。
    """

    personality_vector: dict[str, float] = field(default_factory=dict)
    knowledge_affinity: dict[str, float] = field(default_factory=dict)
    crest_affinity: dict[str, float] = field(default_factory=dict)
    attribute_bias: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "personality_vector": self.personality_vector,
            "knowledge_affinity": self.knowledge_affinity,
            "crest_affinity": self.crest_affinity,
            "attribute_bias": self.attribute_bias,
        }


class InheritanceEngine:
    """特质遗传引擎。

    从父母双方的特质计算子代继承值。核心公式:
        child_value = midpoint + random_jitter * (1 - strength)
    其中 midpoint = (parent_a_value + parent_b_value) / 2。

    每个特质维度独立计算，外加低概率的完全随机突变。
    """

    def __init__(
        self,
        rng: random.Random | None = None,
        strength: float = DEFAULT_INHERITANCE_STRENGTH,
        jitter: float = DEFAULT_INHERITANCE_JITTER,
        mutation_chance: float = DEFAULT_MUTATION_CHANCE,
    ) -> None:
        self._rng = rng or random.Random()
        self.strength = max(0.0, min(1.0, strength))
        self.jitter = max(0.0, min(1.0, jitter))
        self.mutation_chance = max(0.0, min(1.0, mutation_chance))

    def _inherit_scalar(self, val_a: float, val_b: float) -> float:
        """继承单个标量值。

        Args:
            val_a: 父/母 A 的值。
            val_b: 父/母 B 的值。

        Returns:
            子代继承值 [0, 1]。
        """
        if self._rng.random() < self.mutation_chance:
            # 完全随机突变
            return self._rng.random()

        midpoint = (val_a + val_b) / 2.0
        jitter_amount = self._rng.uniform(-self.jitter, self.jitter) * (1.0 - self.strength)
        result = midpoint + jitter_amount
        return max(0.0, min(1.0, result))

    def inherit_personality(
        self,
        personality_a: dict[str, float],
        personality_b: dict[str, float],
    ) -> dict[str, float]:
        """从父母人格向量计算子代人格。

        Args:
            personality_a: 父/母 A 的人格向量 (如 {"E/I": 0.7, "S/N": 0.3, ...})。
            personality_b: 父/母 B 的人格向量。

        Returns:
            子代人格向量（相同 keys）。
        """
        all_dims = set(personality_a.keys()) | set(personality_b.keys())
        result: dict[str, float] = {}
        for dim in sorted(all_dims):
            va = personality_a.get(dim, 0.5)
            vb = personality_b.get(dim, 0.5)
            result[dim] = self._inherit_scalar(va, vb)
        return result

    def inherit_knowledge_affinity(
        self,
        knowledge_a: dict[str, float],
        knowledge_b: dict[str, float],
    ) -> dict[str, float]:
        """从父母知识亲和力计算子代亲和力。

        额外规则: 如果父母双方都对某领域有高亲和力 (>0.6)，子代有加成（+0.1 cap）。

        Args:
            knowledge_a: 父/母 A 的知识亲和力。
            knowledge_b: 父/母 B 的知识亲和力。

        Returns:
            子代知识亲和力。
        """
        all_domains = set(knowledge_a.keys()) | set(knowledge_b.keys())
        result: dict[str, float] = {}
        for domain in sorted(all_domains):
            va = knowledge_a.get(domain, 0.0)
            vb = knowledge_b.get(domain, 0.0)
            inherited = self._inherit_scalar(va, vb)
            # 双亲高亲和力加成
            if va > 0.6 and vb > 0.6:
                inherited = min(1.0, inherited + 0.1)
            result[domain] = inherited
        return result

    def inherit_crest_affinity(
        self,
        crests_a: dict[str, float],
        crests_b: dict[str, float],
    ) -> dict[str, float]:
        """从父母徽章亲和力计算子代亲和力。

        Args:
            crests_a: 父/母 A 的徽章亲和力。
            crests_b: 父/母 B 的徽章亲和力。

        Returns:
            子代徽章亲和力。
        """
        all_crests = set(crests_a.keys()) | set(crests_b.keys())
        result: dict[str, float] = {}
        for crest in sorted(all_crests):
            va = crests_a.get(crest, 0.0)
            vb = crests_b.get(crest, 0.0)
            result[crest] = self._inherit_scalar(va, vb)
        return result

    def inherit_attribute_bias(
        self,
        attr_a: str,
        attr_b: str,
    ) -> dict[str, float]:
        """从父母属性计算子代属性偏向。

        Args:
            attr_a: 父/母 A 的属性 (如 "vaccine", "data", "virus")。
            attr_b: 父/母 B 的属性。

        Returns:
            属性偏向映射，和为 1.0。
        """
        # 基础: 父母各贡献 0.5
        bias: dict[str, float] = {}
        base_weight = 0.5
        for attr in (attr_a, attr_b):
            bias[attr] = bias.get(attr, 0.0) + base_weight

        # 加小随机抖动
        for attr in list(bias.keys()):
            jitter = self._rng.uniform(-0.1, 0.1)
            bias[attr] = max(0.0, bias[attr] + jitter)

        # 归一化
        total = sum(bias.values())
        if total > 0:
            for attr in bias:
                bias[attr] /= total

        return bias

    def compute_all(
        self,
        personality_a: dict[str, float],
        personality_b: dict[str, float],
        knowledge_a: dict[str, float],
        knowledge_b: dict[str, float],
        crests_a: dict[str, float],
        crests_b: dict[str, float],
        attr_a: str,
        attr_b: str,
    ) -> InheritedTraits:
        """一站式计算所有遗传特质。

        Args:
            personality_a, personality_b: 父母人格向量。
            knowledge_a, knowledge_b: 父母知识亲和力。
            crests_a, crests_b: 父母徽章亲和力。
            attr_a, attr_b: 父母属性。

        Returns:
            InheritedTraits 包含所有维度的子代继承值。
        """
        return InheritedTraits(
            personality_vector=self.inherit_personality(personality_a, personality_b),
            knowledge_affinity=self.inherit_knowledge_affinity(knowledge_a, knowledge_b),
            crest_affinity=self.inherit_crest_affinity(crests_a, crests_b),
            attribute_bias=self.inherit_attribute_bias(attr_a, attr_b),
        )


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

_lineage_tracker: LineageTracker | None = None


def get_lineage_tracker() -> LineageTracker:
    """获取全局 LineageTracker 单例。"""
    global _lineage_tracker
    if _lineage_tracker is None:
        _lineage_tracker = LineageTracker()
    return _lineage_tracker


def reset_lineage_tracker() -> None:
    """重置全局 LineageTracker（主要用于测试）。"""
    global _lineage_tracker
    if _lineage_tracker is not None:
        _lineage_tracker.reset()
    _lineage_tracker = None


__all__ = [
    "DEFAULT_INHERITANCE_JITTER",
    "DEFAULT_INHERITANCE_STRENGTH",
    "DEFAULT_MUTATION_CHANCE",
    "InheritanceEngine",
    "InheritedTraits",
    "LineageRecord",
    "LineageTracker",
    "get_lineage_tracker",
    "reset_lineage_tracker",
]
