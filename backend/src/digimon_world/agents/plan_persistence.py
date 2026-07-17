"""
计划持久化系统 — Phase 19 核心模块
================================

参考 arXiv:2606.22953 "Plans Don't Persist:
Why Context Management Is Load Bearing for LLM Agents" —
计划仅存放在 memory_stream 上下文中时，每一步后退化 4.1×。

功能:
1. PlanCheckpoint — 计划快照数据结构（计划文本 + 状态 + 时间戳 + 进度）
2. PlanPersistenceEngine — 计划全生命周期管理（checkpoint/resume/progress/complete/abandon）
3. 计划相似度检测 — 检测重复计划，触发 SUPERSEDED 而非 COMPLETED
4. 计划过期机制 — TTL 过期自动 ABANDON
5. 全局单例 — get_plan_engine() / reset_plan_engine()
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────

PLAN_IMPORTANCE_BOOST = 2
PLAN_MEMORY_MIN_IMPORTANCE = 7
DEFAULT_MAX_PLANS = 20
DEFAULT_PLAN_TTL_TICKS = 48
SUPERSEDE_SIMILARITY_THRESHOLD = 0.70

# 别名（兼容旧引用）
PLAN_MIN_IMPORTANCE = PLAN_MEMORY_MIN_IMPORTANCE


# ──────────────────────────────────────────────
# 状态枚举
# ──────────────────────────────────────────────

class PlanStatus(Enum):
    """计划状态枚举。"""
    ACTIVE = auto()
    PAUSED = auto()
    COMPLETED = auto()
    ABANDONED = auto()
    SUPERSEDED = auto()


# ──────────────────────────────────────────────
# 计划检查点
# ──────────────────────────────────────────────

@dataclass
class PlanCheckpoint:
    """计划检查点 — 某一时刻 agent 行为计划的快照。"""

    plan_id: str
    agent_name: str
    plan_text: str
    status: PlanStatus
    importance: int  # 1-10
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]
    tick_created: int
    tick_expires: int  # 过期 tick, 0=永不过期
    sub_plans: list[str] = field(default_factory=list)
    parent_plan_id: Optional[str] = None
    progress_note: str = ""
    context_snapshot: str = ""

    @classmethod
    def create(
        cls,
        agent_name: str,
        plan_text: str,
        importance: int,
        tick: int,
        context_snapshot: str = "",
        plan_ttl_ticks: int = DEFAULT_PLAN_TTL_TICKS,
        parent_plan_id: Optional[str] = None,
    ) -> "PlanCheckpoint":
        """工厂方法: 创建新的计划检查点。"""
        now = datetime.now(timezone.utc)
        return cls(
            plan_id=str(uuid.uuid4()),
            agent_name=agent_name,
            plan_text=plan_text,
            status=PlanStatus.ACTIVE,
            importance=min(10, max(1, importance)),
            created_at=now,
            updated_at=now,
            completed_at=None,
            tick_created=tick,
            tick_expires=tick + plan_ttl_ticks,
            parent_plan_id=parent_plan_id,
            context_snapshot=context_snapshot,
        )

    def is_expired(self, current_tick: int) -> bool:
        """判断计划是否已过期。tick_expires=0 时永不过期。"""
        return self.tick_expires > 0 and current_tick > self.tick_expires

    def time_since_created(self) -> str:
        """返回计划创建了多久（人类可读）。"""
        delta = datetime.now(timezone.utc) - self.created_at
        hours = delta.total_seconds() / 3600
        if hours < 1:
            return f"{int(delta.total_seconds() / 60)}分钟"
        return f"{hours:.1f}小时"

    def to_dict(self) -> dict:
        """序列化为 dict。"""
        return {
            "plan_id": self.plan_id,
            "agent_name": self.agent_name,
            "plan_text": self.plan_text,
            "status": self.status.name,
            "importance": self.importance,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "tick_created": self.tick_created,
            "tick_expires": self.tick_expires,
            "sub_plans": list(self.sub_plans),
            "parent_plan_id": self.parent_plan_id,
            "progress_note": self.progress_note,
            "context_snapshot": self.context_snapshot,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PlanCheckpoint":
        """从 dict 反序列化。"""
        return cls(
            plan_id=data["plan_id"],
            agent_name=data["agent_name"],
            plan_text=data["plan_text"],
            status=PlanStatus[data["status"]],
            importance=data["importance"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            completed_at=datetime.fromisoformat(data["completed_at"])
            if data.get("completed_at") else None,
            tick_created=data["tick_created"],
            tick_expires=data["tick_expires"],
            sub_plans=list(data.get("sub_plans", [])),
            parent_plan_id=data.get("parent_plan_id"),
            progress_note=data.get("progress_note", ""),
            context_snapshot=data.get("context_snapshot", ""),
        )


# ──────────────────────────────────────────────
# 计划持久化引擎
# ──────────────────────────────────────────────

class PlanPersistenceEngine:
    """计划持久化引擎 — 计划检查点的 CRUD 管理。

    用法:
        engine = PlanPersistenceEngine(max_plans=20, plan_ttl_ticks=48)
        plan = engine.checkpoint("亚古兽", "去文件岛找食物", 7, tick=100)
        resumed = engine.resume("亚古兽", current_tick=105)
        engine.update_progress(plan.plan_id, "找到了苹果", tick=106)
        engine.complete(plan.plan_id)
    """

    def __init__(
        self,
        max_plans: int = DEFAULT_MAX_PLANS,
        plan_ttl_ticks: int = DEFAULT_PLAN_TTL_TICKS,
    ) -> None:
        self._plans: dict[str, list[PlanCheckpoint]] = {}  # public: _store 别名
        self._store = self._plans  # 兼容 app.py 直接访问
        self.max_plans = max_plans
        self.plan_ttl_ticks = plan_ttl_ticks

    # ── 查询 ──────────────────────────────────

    def get_active(self, agent_name: str) -> Optional[PlanCheckpoint]:
        """返回当前 ACTIVE 计划（最近创建者）。"""
        plans = self._plans.get(agent_name, [])
        for plan in reversed(plans):
            if plan.status == PlanStatus.ACTIVE:
                return plan
        return None

    def get_history(
        self, agent_name: str, limit: int = 10
    ) -> list[PlanCheckpoint]:
        """返回最近 N 条计划（按 updated_at 降序）。"""
        plans = self._plans.get(agent_name, [])
        return sorted(plans, key=lambda p: p.updated_at, reverse=True)[:limit]

    def get_by_id(self, plan_id: str) -> Optional[PlanCheckpoint]:
        """按 plan_id 查找计划（跨所有 agent）。"""
        return self._find_plan(plan_id)

    def get_stats(self, agent_name: str) -> dict:
        """获取 agent 的计划统计信息。"""
        plans = self._plans.get(agent_name, [])
        status_counts: dict[str, int] = {}
        for cp in plans:
            s = cp.status.name
            status_counts[s] = status_counts.get(s, 0) + 1

        active = self.get_active(agent_name)
        return {
            "agent_name": agent_name,
            "total_plans": len(plans),
            "status_counts": status_counts,
            "active_plan": active.to_dict() if active else None,
            "has_active": active is not None,
        }

    def all_agents(self) -> list[str]:
        """返回所有有计划的 agent 名称列表。"""
        return list(self._plans.keys())

    # ── 创建 ──────────────────────────────────

    def checkpoint(
        self,
        agent_name: str,
        plan_text: str,
        importance: int,
        tick: int,
        context_snapshot: str = "",
    ) -> PlanCheckpoint:
        """创建新计划检查点，同时处理旧的活跃计划。

        规则:
        - 相似度 > 70% → 标记旧计划为 SUPERSEDED
        - 否则 → 标记旧计划为 COMPLETED
        - 按 max_plans 裁剪旧记录
        """
        if agent_name not in self._plans:
            self._plans[agent_name] = []

        plans = self._plans[agent_name]

        # 处理旧的 ACTIVE 计划
        old_active = None
        for plan in reversed(plans):
            if plan.status == PlanStatus.ACTIVE:
                old_active = plan
                break

        if old_active is not None:
            similarity = self.check_similarity(old_active.plan_text, plan_text)
            if similarity > SUPERSEDE_SIMILARITY_THRESHOLD:
                old_active.status = PlanStatus.SUPERSEDED
                old_active.completed_at = datetime.now(timezone.utc)
                logger.debug("计划 %s 被取代 (相似度=%.2f)", old_active.plan_id, similarity)
            else:
                old_active.status = PlanStatus.COMPLETED
                old_active.completed_at = datetime.now(timezone.utc)
                logger.debug("计划 %s 自动完成 (相似度=%.2f)", old_active.plan_id, similarity)

        # 创建新计划（importance 使用 boosted 值）
        boosted = max(importance, PLAN_MEMORY_MIN_IMPORTANCE)
        new_plan = PlanCheckpoint.create(
            agent_name=agent_name,
            plan_text=plan_text,
            importance=boosted,
            tick=tick,
            context_snapshot=context_snapshot,
            plan_ttl_ticks=self.plan_ttl_ticks,
        )
        plans.append(new_plan)

        # 裁剪: 保留最近 max_plans 条
        if len(plans) > self.max_plans:
            plans.sort(key=lambda p: p.created_at)
            self._plans[agent_name] = plans[-self.max_plans:]

        logger.info("计划创建: %s → '%s' (tick=%d)", agent_name, plan_text[:50], tick)
        return new_plan

    # ── 恢复 ──────────────────────────────────

    def resume(self, agent_name: str, current_tick: int = 0) -> Optional[PlanCheckpoint]:
        """恢复最近的 ACTIVE 计划。

        若 current_tick > 0 且计划已过期，标记 ABANDONED 返回 None。
        """
        plan = self.get_active(agent_name)
        if plan is None:
            return None
        if current_tick > 0 and plan.is_expired(current_tick):
            plan.status = PlanStatus.ABANDONED
            plan.completed_at = datetime.now(timezone.utc)
            plan.progress_note = f"{plan.progress_note} [过期放弃: tick {current_tick}]".strip()
            logger.info(
                "计划 %s 过期放弃 (expired=%d, now=%d)",
                plan.plan_id, plan.tick_expires, current_tick,
            )
            return None
        return plan

    # ── 更新 ──────────────────────────────────

    def update_progress(self, plan_id: str, note: str, tick: int) -> bool:
        """更新进展记录并延长有效期。返回 True 如果成功。"""
        plan = self._find_plan(plan_id)
        if plan is None:
            logger.warning("update_progress: 找不到计划 %s", plan_id)
            return False
        plan.progress_note = f"{plan.progress_note}; {note}" if plan.progress_note else note
        plan.updated_at = datetime.now(timezone.utc)
        plan.tick_expires = tick + self.plan_ttl_ticks
        return True

    def complete(self, plan_id: str) -> bool:
        """标记计划为已完成。返回 True 如果成功。"""
        plan = self._find_plan(plan_id)
        if plan is None:
            logger.warning("complete: 找不到计划 %s", plan_id)
            return False
        plan.status = PlanStatus.COMPLETED
        plan.completed_at = datetime.now(timezone.utc)
        plan.updated_at = datetime.now(timezone.utc)
        logger.info("计划 %s 已完成", plan_id)
        return True

    def abandon(self, plan_id: str, reason: str = "") -> bool:
        """放弃计划并记录原因。返回 True 如果成功。"""
        plan = self._find_plan(plan_id)
        if plan is None:
            logger.warning("abandon: 找不到计划 %s", plan_id)
            return False
        plan.status = PlanStatus.ABANDONED
        plan.completed_at = datetime.now(timezone.utc)
        plan.updated_at = datetime.now(timezone.utc)
        if reason:
            plan.progress_note = f"{plan.progress_note} [放弃: {reason}]".strip()
        logger.info("计划 %s 已放弃: %s", plan_id, reason or "(无原因)")
        return True

    def pause(self, plan_id: str) -> bool:
        """暂停计划（保留以便恢复）。返回 True 如果成功。"""
        plan = self._find_plan(plan_id)
        if plan is None:
            return False
        plan.status = PlanStatus.PAUSED
        plan.updated_at = datetime.now(timezone.utc)
        return True

    # ── 相似度 ────────────────────────────────

    @staticmethod
    def check_similarity(text1: str, text2: str) -> float:
        """字符级 Jaccard 相似度。

        对中文友好(无须分词)，对短文本差异敏感。
        """
        if not text1 and not text2:
            return 1.0
        if not text1 or not text2:
            return 0.0
        set1, set2 = set(text1), set(text2)
        union = set1 | set2
        return len(set1 & set2) / len(union) if union else 0.0

    # ── 序列化 ────────────────────────────────

    def to_dict(self) -> dict:
        """序列化整个引擎状态。"""
        return {
            agent: [p.to_dict() for p in plans]
            for agent, plans in self._plans.items()
        }

    @classmethod
    def from_dict(
        cls,
        data: dict,
        max_plans: int = DEFAULT_MAX_PLANS,
        plan_ttl_ticks: int = DEFAULT_PLAN_TTL_TICKS,
    ) -> "PlanPersistenceEngine":
        """从 dict 反序列化恢复引擎。"""
        engine = cls(max_plans=max_plans, plan_ttl_ticks=plan_ttl_ticks)
        for agent, plan_dicts in data.items():
            engine._plans[agent] = [PlanCheckpoint.from_dict(pd) for pd in plan_dicts]
        return engine

    # ── 内部 ──────────────────────────────────

    def _find_plan(self, plan_id: str) -> Optional[PlanCheckpoint]:
        """按 plan_id 查找计划（跨所有 agent）。"""
        for plans in self._plans.values():
            for plan in plans:
                if plan.plan_id == plan_id:
                    return plan
        return None


# ──────────────────────────────────────────────
# 全局单例
# ──────────────────────────────────────────────

_plan_engine: Optional[PlanPersistenceEngine] = None


def get_plan_engine() -> PlanPersistenceEngine:
    """获取全局计划持久化引擎单例。"""
    global _plan_engine
    if _plan_engine is None:
        _plan_engine = PlanPersistenceEngine()
    return _plan_engine


def reset_plan_engine() -> None:
    """重置全局引擎（测试用）。"""
    global _plan_engine
    _plan_engine = None
