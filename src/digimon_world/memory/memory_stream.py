"""
MemoryStream - 记忆流
=====================

参考 Stanford Generative Agents (Park et al., 2023) 的 memory_stream.py。

每条记忆 = 时间戳 + 描述 + 重要性(1-10) + 类型

检索: 时序近因 (0.3) + 重要性 (0.4) + 关联性 (0.3)

Phase 0: 骨架,先做基本 add / retrieve,无 LLM 反思
Phase 2: 接入 LLM 反思、关联性评估
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class MemoryNode:
    """一条记忆。"""

    timestamp: datetime
    description: str
    importance: int  # 1-10
    memory_type: str = "observation"  # observation / reflection / plan
    embedding_id: str | None = None  # 预留向量检索
    node_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "timestamp": self.timestamp.isoformat(),
            "description": self.description,
            "importance": self.importance,
            "memory_type": self.memory_type,
            "embedding_id": self.embedding_id,
        }


@dataclass
class MemoryStream:
    """一个 agent 的全部记忆。

    Phase 0: list 存储,简单 add
    Phase 2: 触发反思,生成 reflection 类型记忆
    """

    entries: list[MemoryNode] = field(default_factory=list)
    next_id: int = 0
    # 反思阈值(可调): 累计 importance 和
    reflection_threshold: int = 100

    def add(
        self,
        event: dict[str, Any] | str,
        importance: int = 5,
        memory_type: str = "observation",
    ) -> MemoryNode:
        """添加一条记忆。

        Args:
            event: 事件 dict(由 DigimonAgent.observe 传入)或字符串描述
            importance: 1-10 的重要性评分
            memory_type: 记忆类型

        Returns:
            新建的 MemoryNode
        """
        if isinstance(event, dict):
            desc = event.get("description") or str(event)
        else:
            desc = event

        node = MemoryNode(
            timestamp=datetime.utcnow(),
            description=desc,
            importance=importance,
            memory_type=memory_type,
            node_id=self.next_id,
        )
        self.entries.append(node)
        self.next_id += 1
        return node

    @property
    def importance_sum(self) -> int:
        """累计重要性之和,用于判断是否触发反思。"""
        return sum(m.importance for m in self.entries)

    def should_reflect(self) -> bool:
        """是否应该触发反思。"""
        return self.importance_sum >= self.reflection_threshold

    def retrieve(
        self,
        query: str,
        now: datetime | None = None,
        top_k: int = 10,
    ) -> list[MemoryNode]:
        """检索最相关的记忆。

        Phase 0: 用关键词 + 重要性 + 时序近因 三维评分(简化版)
        Phase 2: 接入 embedding 做关联性评估
        """
        now = now or datetime.utcnow()
        scored: list[tuple[float, MemoryNode]] = []
        q_tokens = set(query.lower().split())

        for node in self.entries:
            # 重要性分 (0-1)
            importance_score = node.importance / 10.0

            # 时序近因分(记忆越新分越高,半衰期 24 小时)
            age_hours = (now - node.timestamp).total_seconds() / 3600
            recency_score = math.exp(-age_hours / 24.0)

            # 关联性分(Phase 0 简化版: 关键词重合比例)
            desc_tokens = set(node.description.lower().split())
            if q_tokens:
                relevance_score = len(q_tokens & desc_tokens) / len(q_tokens | desc_tokens)
            else:
                relevance_score = 0.0

            # 加权求和(参考 Stanford 论文权重)
            score = 0.3 * recency_score + 0.4 * importance_score + 0.3 * relevance_score
            scored.append((score, node))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [node for _, node in scored[:top_k]]

    def to_dict(self) -> list[dict[str, Any]]:
        return [m.to_dict() for m in self.entries]
