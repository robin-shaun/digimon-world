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
from datetime import datetime, timedelta
from typing import Any


@dataclass
class MemoryNode:
    """一条记忆。"""

    timestamp: datetime
    description: str
    importance: int  # 1-10
    memory_type: str = "observation"  # observation / reflection / plan / summary
    embedding_id: str | None = None  # 预留向量检索
    node_id: int | None = None
    tick_index: int = 0  # 记录产生时的世界 tick 序号，用于去重和摘要

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "timestamp": self.timestamp.isoformat(),
            "description": self.description,
            "importance": self.importance,
            "memory_type": self.memory_type,
            "embedding_id": self.embedding_id,
            "tick_index": self.tick_index,
        }


@dataclass
class MemoryStream:
    """一个 agent 的全部记忆。

    Phase 0: list 存储,简单 add
    Phase 2: 触发反思,生成 reflection 类型记忆
    Phase 7: 记忆压缩（去重 + 分级保留 + 摘要）
    """

    entries: list[MemoryNode] = field(default_factory=list)
    next_id: int = 0
    # 反思阈值(可调): 累计 importance 和
    reflection_threshold: int = 100
    # 压缩阈值: entries 超过此数量时自动压缩
    compress_threshold: int = 1000
    # 旧记忆判定: importance < 此值 且超过 max_age 天的记忆会被压缩
    compress_importance_cutoff: int = 3
    compress_max_age_days: int = 7
    # Phase 7: 压缩配置
    # 低重要性(imp<3)保留最近条数
    low_imp_keep: int = 50
    # 中等重要性(3-6)保留最近条数
    mid_imp_keep: int = 200
    # 中等重要性旧于多少 tick 后转为摘要
    mid_imp_summary_tick_age: int = 100
    # 相似移动去重窗口(tick 差)
    moved_dedup_tick_window: int = 5
    # 压缩统计
    total_deduped: int = 0
    total_summarized: int = 0
    total_pruned: int = 0

    def add(
        self,
        event: dict[str, Any] | str,
        importance: int = 5,
        memory_type: str = "observation",
        tick_index: int = 0,
    ) -> MemoryNode:
        """添加一条记忆。

        Args:
            event: 事件 dict(由 DigimonAgent.observe 传入)或字符串描述
            importance: 1-10 的重要性评分
            memory_type: 记忆类型
            tick_index: 世界 tick 序号(用于去重)

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
            tick_index=tick_index,
        )
        self.entries.append(node)
        self.next_id += 1
        self._maybe_compress()
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

    def _maybe_compress(self) -> None:
        """在 entries 超过阈值时自动触发压缩。"""
        if len(self.entries) > self.compress_threshold:
            self.compress_memories()

    def compress_memories(self, current_tick: int | None = None) -> dict[str, int]:
        """Phase 7: 三级记忆压缩。

        1. 相似移动去重: 同一 tick 窗口内同 agent 的同类型 moved 事件合并
        2. 重要性分级保留:
           - imp >= 7: 永久保留
           - imp 3-6: 保留最近 mid_imp_keep 条,旧于 mid_imp_summary_tick_age 的转为摘要
           - imp < 3: 保留最近 low_imp_keep 条,其余丢弃
        3. 摘要生成: 将一批中等重要性旧记忆压缩为一条摘要节点

        Returns:
            {"deduped": N, "summarized": N, "pruned": N}
        """
        deduped = 0
        summarized = 0
        pruned = 0

        # ---- 步骤1: 相似移动去重 ----
        # 在 5 tick 内、同类型 moved 的记忆合并
        dedup_window = self.moved_dedup_tick_window
        seen_groups: dict[tuple, list[int]] = {}  # (memory_type, desc_hash) -> [indices]

        for i, node in enumerate(self.entries):
            if node.memory_type in ("observation",) and node.importance < 5:
                # 提取类型关键词(如 moved、rested 等)
                key = (node.memory_type, self._event_type_key(node))
                seen_groups.setdefault(key, []).append(i)

        # 合并组内邻近的记忆
        to_remove: set[int] = set()
        for key, indices in seen_groups.items():
            if len(indices) < 2:
                continue
            # 按 tick_index 排序
            indices.sort(key=lambda i: self.entries[i].tick_index)
            group_start = 0
            for group_end in range(1, len(indices)):
                prev_idx = indices[group_start]
                curr_idx = indices[group_end]
                prev_node = self.entries[prev_idx]
                curr_node = self.entries[curr_idx]
                if curr_node.tick_index - prev_node.tick_index <= dedup_window:
                    # 合并: 标记 curr 删除，更新 prev 描述
                    prev_node.description = self._merge_descriptions(
                        prev_node.description, curr_node.description
                    )
                    to_remove.add(curr_idx)
                    deduped += 1
                else:
                    group_start = group_end

        # 移除重复项
        if to_remove:
            self.entries = [n for i, n in enumerate(self.entries) if i not in to_remove]

        # ---- 步骤2: 重要性分级保留 ----
        high: list[MemoryNode] = []
        mid: list[MemoryNode] = []
        low: list[MemoryNode] = []

        for node in self.entries:
            if node.importance >= 7 or node.memory_type in ("reflection", "diary", "summary"):
                high.append(node)
            elif node.importance >= 3:
                mid.append(node)
            else:
                low.append(node)

        # 低重要性: 保留最近 low_imp_keep 条
        kept_low = low[-self.low_imp_keep:] if len(low) > self.low_imp_keep else low
        pruned += max(0, len(low) - self.low_imp_keep)

        # 中等重要性: 保留最近 mid_imp_keep 条,旧于 mid_imp_summary_tick_age 的转摘要
        if mid and current_tick is not None:
            kept_mid: list[MemoryNode] = []
            stale_mid: list[MemoryNode] = []
            for node in mid:
                if current_tick - node.tick_index > self.mid_imp_summary_tick_age:
                    stale_mid.append(node)
                else:
                    kept_mid.append(node)
            # 保留最近 mid_imp_keep 条(按 tick 排序)
            kept_mid.sort(key=lambda n: n.tick_index)
            if len(kept_mid) > self.mid_imp_keep:
                overflow = kept_mid[: len(kept_mid) - self.mid_imp_keep]
                stale_mid.extend(overflow)
                kept_mid = kept_mid[-self.mid_imp_keep:]

            # 旧的中等记忆转为摘要
            if stale_mid:
                summary_node = self.generate_summary(stale_mid, current_tick)
                kept_mid = [summary_node] + kept_mid  # 摘要放前面
                summarized += len(stale_mid)
            mid = kept_mid
        elif mid and len(mid) > self.mid_imp_keep:
            # 没有 current_tick: 只按数量裁剪
            mid = mid[-self.mid_imp_keep:]
            pruned += max(0, len(mid) - self.mid_imp_keep)

        # 重建 entries
        self.entries = high + mid + kept_low
        self.total_deduped += deduped
        self.total_summarized += summarized
        self.total_pruned += pruned
        return {"deduped": deduped, "summarized": summarized, "pruned": pruned}

    @staticmethod
    def _event_type_key(node: MemoryNode) -> str:
        """从 memory description 提取事件类型关键词。"""
        desc = node.description
        if "移动" in desc or "走" in desc or "跑" in desc or "飞" in desc:
            return "moved"
        if "休息" in desc or "睡觉" in desc:
            return "rested"
        if "观察" in desc or "巡视" in desc:
            return "observed"
        if "对话" in desc or "聊天" in desc:
            return "dialogue"
        if "战斗" in desc:
            return "battle"
        if "吃饭" in desc or "进食" in desc:
            return "ate"
        return desc[:8]  # 用描述前8字符做分组，避免不同事件被错误合并

    @staticmethod
    def _merge_descriptions(prev: str, curr: str) -> str:
        """合并相邻相似事件的描述。"""
        # 如果 prev 已经是合并过的
        if "在区域游荡" in prev:
            return prev  # 不变
        # 提取移动区域关键词
        for kw in ["文件岛", "无限山", "沙滩", "神殿", "商店", "祭坛", "空地", "森林"]:
            if kw in prev or kw in curr:
                return f"在{kw}附近游荡"
        return "在区域游荡"

    def generate_summary(
        self, nodes: list[MemoryNode], current_tick: int
    ) -> MemoryNode:
        """Phase 7: 将一批旧记忆压缩为一条摘要节点。

        Args:
            nodes: 待合并的记忆列表
            current_tick: 当前世界 tick

        Returns:
            摘要 MemoryNode
        """
        if not nodes:
            raise ValueError("Cannot generate summary from empty node list")

        # 统计
        type_counts: dict[str, int] = {}
        for n in nodes:
            ek = self._event_type_key(n)
            type_counts[ek] = type_counts.get(ek, 0) + 1

        parts = [f"{v}次{k}" for k, v in sorted(type_counts.items())]
        count_part = "、".join(parts) if parts else "各种活动"

        # 取时间范围
        ticks = sorted(n.tick_index for n in nodes)
        tick_range = f"tick {ticks[0]}-{ticks[-1]}" if len(ticks) > 1 else f"tick {ticks[0]}"

        summary_desc = f"摘要({tick_range}): 期间经历了{count_part},共{len(nodes)}条记忆"

        summary_node = MemoryNode(
            timestamp=nodes[-1].timestamp,
            description=summary_desc,
            importance=3,
            memory_type="summary",
            node_id=self.next_id,
            tick_index=current_tick,
        )
        self.next_id += 1
        self.total_summarized += len(nodes)
        return summary_node

    def to_dict(self) -> list[dict[str, Any]]:
        return [m.to_dict() for m in self.entries]
