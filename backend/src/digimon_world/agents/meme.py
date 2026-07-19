"""
Meme System — 模因传播 / 技能文化
==================================

数码兽群体中的"模因"(meme) — 一段知识、信念、技能经验或谣言，
可以在 agent 间传播，形成文化现象。

参考:
- Dawkins "自私的基因" (1976) — 模因基本概念
- Stanford Generative Agents — agent 间信息传递
- 数码宝贝动画 — 数码兽之间会互相学习招式/分享情报

设计要点:
- Meme: 不可变数据类,代表一条传播中的信息
- MemePool: 世界级模因池,追踪所有模因的传播路径
- 传播机制: 对话/相遇时概率性转移,受关系向量和模因类别影响
- 文化指标: 热门模因排行、感染率、传播链可视化数据

用法::

    from digimon_world.agents.meme import Meme, MemePool, MemeCategory

    pool = MemePool()
    meme = pool.create(
        content="无限山上有黑暗齿轮",
        category=MemeCategory.RUMOR,
        origin_agent="Agumon",
    )
    pool.infect("Gabumon", meme.meme_id)  # Gabumon 也知道了
"""

from __future__ import annotations

import hashlib
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# MemeCategory — 模因类别
# ---------------------------------------------------------------------------

class MemeCategory(str, Enum):
    """模因类别，影响传播速度和受体权重。"""

    SKILL = "skill"        # 技能/战斗经验 — 高传播,战斗后转移
    RUMOR = "rumor"        # 谣言/情报 — 中传播,对话时转移
    BELIEF = "belief"      # 信念/价值观 — 低传播,深度互动转移
    CUSTOM = "custom"      # 自定义/其他


# 各类别的默认传播概率
CATEGORY_SPREAD_RATE: dict[MemeCategory, float] = {
    MemeCategory.SKILL: 0.40,
    MemeCategory.RUMOR: 0.55,
    MemeCategory.BELIEF: 0.15,
    MemeCategory.CUSTOM: 0.25,
}


# ---------------------------------------------------------------------------
# Meme — 一条模因
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Meme:
    """一条不可变的模因。

    Attributes:
        meme_id: 唯一标识 (SHA-256 前 12 位)
        content: 模因内容 (人类可读的短句)
        category: 类别
        origin_agent: 创建者名字
        created_at: 创建时间 (epoch秒)
        tags: 可选标签 (如 ["danger", "file_island"])
        generation: 代数 — 0=原创,每传播一次 +1
    """

    meme_id: str
    content: str
    category: MemeCategory
    origin_agent: str
    created_at: float
    tags: tuple[str, ...] = ()
    generation: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "meme_id": self.meme_id,
            "content": self.content,
            "category": self.category.value,
            "origin_agent": self.origin_agent,
            "created_at": self.created_at,
            "tags": list(self.tags),
            "generation": self.generation,
        }


def _make_meme_id(content: str, origin: str, ts: float) -> str:
    """生成唯一 meme_id。"""
    raw = f"{content}|{origin}|{ts:.6f}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# MemePool — 世界模因池
# ---------------------------------------------------------------------------

@dataclass
class MemePool:
    """管理世界所有模因的池子。

    每个世界实例持有一个 MemePool，追踪:
    - 所有被创建的模因 (registry)
    - 每个 agent 知道哪些模因 (infections)
    - 传播历史 (spread_log)

    用法::

        pool = MemePool()
        mid = pool.create("小心齿轮草原的黑色齿轮", MemeCategory.RUMOR, "Agumon")
        pool.infect("Gabumon", mid)
        assert pool.knows("Gabumon", mid)
    """

    # meme_id → Meme
    registry: dict[str, Meme] = field(default_factory=dict)
    # agent_name → set[meme_id]
    infections: dict[str, set[str]] = field(default_factory=dict)
    # 传播日志: [(from_agent, to_agent, meme_id, tick), ...]
    spread_log: list[tuple[str, str, str, float]] = field(default_factory=list)
    # 幂等索引: (content, origin_agent) → meme_id
    _idempotent_index: dict[tuple[str, str], str] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # 创建
    # ------------------------------------------------------------------

    def create(
        self,
        content: str,
        category: MemeCategory = MemeCategory.CUSTOM,
        origin_agent: str = "unknown",
        tags: tuple[str, ...] = (),
    ) -> str:
        """创建一条新模因，origin_agent 自动感染。

        幂等: 相同 (content, origin_agent) 返回相同 meme_id。

        Returns:
            meme_id
        """
        # 幂等检查
        key = (content, origin_agent)
        if key in self._idempotent_index:
            return self._idempotent_index[key]

        ts = time.time()
        meme_id = _make_meme_id(content, origin_agent, ts)
        # 极端情况: hash 碰撞 (极小概率)
        if meme_id in self.registry:
            return meme_id

        meme = Meme(
            meme_id=meme_id,
            content=content,
            category=category,
            origin_agent=origin_agent,
            created_at=ts,
            tags=tags,
            generation=0,
        )
        self.registry[meme_id] = meme
        self._idempotent_index[key] = meme_id
        self._ensure_agent(origin_agent)
        self.infections[origin_agent].add(meme_id)
        return meme_id

    # ------------------------------------------------------------------
    # 感染
    # ------------------------------------------------------------------

    def infect(self, agent_name: str, meme_id: str) -> bool:
        """让 agent 知道一个模因。已感染者返回 False。"""
        if meme_id not in self.registry:
            return False
        self._ensure_agent(agent_name)
        if meme_id in self.infections[agent_name]:
            return False
        self.infections[agent_name].add(meme_id)
        return True

    def knows(self, agent_name: str, meme_id: str) -> bool:
        """agent 是否知道此模因。"""
        return meme_id in self.infections.get(agent_name, set())

    # ------------------------------------------------------------------
    # 传播
    # ------------------------------------------------------------------

    def spread_check(
        self,
        from_agent: str,
        to_agent: str,
        meme_id: str,
        tick: float = 0.0,
        *,
        base_rate: float | None = None,
        affinity_bonus: float = 0.0,
    ) -> bool:
        """尝试将一条模因从 from_agent 传播到 to_agent。

        传播概率 = base_rate (或类别默认) + affinity_bonus。

        Args:
            from_agent: 源 agent
            to_agent: 目标 agent
            meme_id: 模因 ID
            tick: 当前世界 tick (用于日志)
            base_rate: 覆盖默认传播率 (0.0~1.0)
            affinity_bonus: 关系亲和度加成 (0.0~0.3)

        Returns:
            True 如果成功传播 (to_agent 新感染)
        """
        meme = self.registry.get(meme_id)
        if meme is None:
            return False
        if self.knows(to_agent, meme_id):
            return False  # 已感染
        if not self.knows(from_agent, meme_id):
            return False  # 源也没有(防御)

        rate = base_rate if base_rate is not None else CATEGORY_SPREAD_RATE.get(
            meme.category, 0.25
        )
        rate = min(1.0, max(0.0, rate + affinity_bonus))

        if random.random() < rate:
            self.infect(to_agent, meme_id)
            self.spread_log.append((from_agent, to_agent, meme_id, tick))
            return True
        return False

    def spread_batch(
        self,
        from_agent: str,
        to_agent: str,
        tick: float = 0.0,
        *,
        max_spread: int = 3,
        affinity_bonus: float = 0.0,
    ) -> list[str]:
        """尝试把 from_agent 的所有模因批量传播给 to_agent。

        每个模因独立判定，最多传播 max_spread 个。
        """
        if from_agent not in self.infections:
            return []
        spread_ids: list[str] = []
        for meme_id in list(self.infections[from_agent]):
            if len(spread_ids) >= max_spread:
                break
            if self.spread_check(from_agent, to_agent, meme_id, tick,
                                 affinity_bonus=affinity_bonus):
                spread_ids.append(meme_id)
        return spread_ids

    # ------------------------------------------------------------------
    # 进阶传播 — 带变异
    # ------------------------------------------------------------------

    def spread_with_mutation(
        self,
        from_agent: str,
        to_agent: str,
        meme_id: str,
        tick: float = 0.0,
        *,
        mutation_rate: float = 0.05,
        affinity_bonus: float = 0.0,
    ) -> str | None:
        """传播一条模因，有概率发生变异 (生成新版本)。

        变异: 在 content 末尾附加轻微变化，generation+1。
        突变模因成为独立新模因，与原始模因共存。

        Returns:
            新感染的 meme_id (可能是原模因或突变体)，失败返回 None
        """
        meme = self.registry.get(meme_id)
        if meme is None:
            return None
        if self.knows(to_agent, meme_id):
            return None
        if not self.knows(from_agent, meme_id):
            return None

        rate = CATEGORY_SPREAD_RATE.get(meme.category, 0.25) + affinity_bonus
        rate = min(1.0, max(0.0, rate))

        if random.random() >= rate:
            return None

        # 突变判定
        if random.random() < mutation_rate:
            mutated_content = f"{meme.content} (传闻变异)"
            new_id = self.create(
                content=mutated_content,
                category=meme.category,
                origin_agent=meme.origin_agent,
                tags=meme.tags,
            )
            # 覆盖 generation
            mutated = Meme(
                meme_id=new_id,
                content=mutated_content,
                category=meme.category,
                origin_agent=meme.origin_agent,
                created_at=time.time(),
                tags=meme.tags,
                generation=meme.generation + 1,
            )
            self.registry[new_id] = mutated
            self.infect(to_agent, new_id)
            self.spread_log.append((from_agent, to_agent, new_id, tick))
            return new_id

        # 正常传播
        self.infect(to_agent, meme_id)
        self.spread_log.append((from_agent, to_agent, meme_id, tick))
        return meme_id

    # ------------------------------------------------------------------
    # 文化指标
    # ------------------------------------------------------------------

    def cultural_metrics(self) -> dict[str, Any]:
        """计算当前世界的文化指标。

        Returns:
            {
                "total_memes": int,
                "total_infections": int,
                "avg_infections_per_meme": float,
                "trending": [meme.to_dict(), ...],  # 感染数 top 5
                "categories": {category: count},
                "spread_chain_depth": int,  # 最大代数
                "infection_rate": float,    # 平均每 agent 知道多少模因
                "orphan_memes": int,        # 无人知晓的模因 (仅 registry 有)
            }
        """
        total_memes = len(self.registry)
        total_infections = sum(len(s) for s in self.infections.values())
        agent_count = len(self.infections)

        # Trending: 按感染数排序, top 5
        meme_popularity: list[tuple[str, int]] = []
        for mid in self.registry:
            count = sum(1 for s in self.infections.values() if mid in s)
            meme_popularity.append((mid, count))
        meme_popularity.sort(key=lambda x: -x[1])
        trending = []
        for mid, count in meme_popularity[:5]:
            m = self.registry[mid]
            d = m.to_dict()
            d["infection_count"] = count
            trending.append(d)

        # 按类别统计
        categories: dict[str, int] = {}
        for m in self.registry.values():
            cat = m.category.value
            categories[cat] = categories.get(cat, 0) + 1

        # 最大代数
        max_gen = max(
            (m.generation for m in self.registry.values()), default=0
        )

        # 孤模因 (registry 有但无人感染)
        all_infected: set[str] = set()
        for s in self.infections.values():
            all_infected.update(s)
        orphans = sum(1 for mid in self.registry if mid not in all_infected)

        return {
            "total_memes": total_memes,
            "total_infections": total_infections,
            "avg_infections_per_meme": (
                total_infections / total_memes if total_memes > 0 else 0.0
            ),
            "trending": trending,
            "categories": categories,
            "spread_chain_depth": max_gen,
            "infection_rate": (
                total_infections / agent_count if agent_count > 0 else 0.0
            ),
            "orphan_memes": orphans,
        }

    def agent_memes(self, agent_name: str) -> list[dict[str, Any]]:
        """获取某 agent 知道的所有模因。"""
        mids = self.infections.get(agent_name, set())
        return [self.registry[mid].to_dict() for mid in mids if mid in self.registry]

    def clear(self) -> None:
        """清空所有模因数据。"""
        self.registry.clear()
        self.infections.clear()
        self.spread_log.clear()
        self._idempotent_index.clear()

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _ensure_agent(self, name: str) -> None:
        if name not in self.infections:
            self.infections[name] = set()
