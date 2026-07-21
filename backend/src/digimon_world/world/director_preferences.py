"""
导演偏好反馈系统 (Director Preference Feedback System)
====================================================

基于 arXiv:2607.14485 的 step-level preference learning 理念:
导演可以对数码兽的具体行为表态 👍/👎，系统在后续 planning/reflection
prompt 中注入偏好信号——轻量级、无 RLHF。

核心类:
- PreferenceRecord: 单条导演偏好记录
- DirectorPreferenceStore: 内存持久化存储 + 提示信号生成
- get_preference_store / reset_preference_store: 全局单例工厂
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# 合法偏好值
VALID_PREFERENCES = frozenset({"like", "avoid"})

# 合法行为类别
VALID_ACTION_CATEGORIES = frozenset({
    "explore", "rest", "social", "battle", "hunt",
    "gather", "build", "play", "aggressive", "flee",
})

# 行为类别中文名
ACTION_CATEGORY_LABELS = {
    "explore": "探索", "rest": "休息", "social": "社交",
    "battle": "战斗", "hunt": "狩猎", "gather": "采集",
    "build": "建造", "play": "玩耍", "aggressive": "攻击",
    "flee": "逃跑",
}


@dataclass
class PreferenceRecord:
    """单条导演偏好记录。

    属性:
        id: 自增 ID（全局唯一）。
        agent_name: 被评价的数码兽名称。
        preference: "like" | "avoid"。
        action_category: 行为类别（explore/rest/social/...）。
        context: 导演的附言（可选）。
        tick: 记录时的世界 tick。
        created_at: ISO 8601 时间戳。
    """

    agent_name: str
    preference: str
    action_category: str
    context: str = ""
    tick: int = 0
    created_at: str = ""
    id: int = 0

    def to_dict(self) -> dict:
        """序列化为字典。"""
        return {
            "id": self.id,
            "agent_name": self.agent_name,
            "preference": self.preference,
            "action_category": self.action_category,
            "context": self.context,
            "tick": self.tick,
            "created_at": self.created_at,
        }


class DirectorPreferenceStore:
    """导演偏好持久化存储。

    单例模式，全局共享。偏好记录按 agent 索引，查询高效。
    当前默认内存存储，后续可扩展 SQLite 持久化。
    """

    MAX_RECORDS: int = 10000  # 防止无限增长

    def __init__(self) -> None:
        self._records: list[PreferenceRecord] = []
        self._next_id = 1
        # 索引: agent_name -> record id 列表
        self._index: dict[str, list[int]] = {}

    # ── 记录 ──────────────────────────────────

    def record(
        self,
        agent_name: str,
        preference: str,
        action_category: str,
        context: str = "",
        tick: int = 0,
    ) -> PreferenceRecord:
        """记录一条偏好。

        Args:
            agent_name: 被评价的数码兽。
            preference: "like" 或 "avoid"。
            action_category: 行为类别。
            context: 可选附言。
            tick: 世界 tick。

        Returns:
            新创建的 PreferenceRecord。

        Raises:
            ValueError: preference 或 action_category 非法。
        """
        if preference not in VALID_PREFERENCES:
            raise ValueError(
                f"非法 preference 值 '{preference}'，必须为 {sorted(VALID_PREFERENCES)}"
            )
        if action_category not in VALID_ACTION_CATEGORIES:
            raise ValueError(
                f"非法 action_category '{action_category}'，必须为 {sorted(VALID_ACTION_CATEGORIES)}"
            )

        rec = PreferenceRecord(
            id=self._next_id,
            agent_name=agent_name,
            preference=preference,
            action_category=action_category,
            context=context,
            tick=tick,
            created_at=datetime.now(UTC).isoformat(),
        )
        self._next_id += 1

        # 防止无限增长
        if len(self._records) >= self.MAX_RECORDS:
            oldest = self._records.pop(0)
            idx_list = self._index.get(oldest.agent_name, [])
            if oldest.id in idx_list:
                idx_list.remove(oldest.id)

        self._records.append(rec)
        self._index.setdefault(agent_name, []).append(rec.id)

        logger.debug(
            "导演偏好记录: %s %s %s (id=%d)",
            agent_name, preference, action_category, rec.id,
        )
        return rec

    # ── 查询 ──────────────────────────────────

    def get_for_agent(self, agent_name: str) -> list[PreferenceRecord]:
        """获取某只数码兽的所有偏好记录，按时间升序。"""
        ids = self._index.get(agent_name, [])
        return [r for r in self._records if r.id in ids]

    def all_records(self) -> list[PreferenceRecord]:
        """返回所有偏好记录（按时间升序）。"""
        return list(self._records)

    def count(self) -> int:
        """总记录数。"""
        return len(self._records)

    # ── Prompt 注入信号 ────────────────────────

    def get_prompt_hints(self, agent_name: str) -> str:
        """生成为 prompt 注入的偏好信号文本。

        统计每个 action_category 的 like/avoid 计数，
        生成简洁提示供 Planner/Reflector 在 prompt 前拼接。

        Returns:
            偏好信号文本，如：
            "导演偏好: 喜欢探索(×3)、社交；避免战斗(×2)"
            无偏好时返回空字符串。
        """
        records = self.get_for_agent(agent_name)
        if not records:
            return ""

        likes: Counter[str] = Counter()
        avoids: Counter[str] = Counter()
        for r in records:
            if r.preference == "like":
                likes[r.action_category] += 1
            else:
                avoids[r.action_category] += 1

        parts: list[str] = []
        if likes:
            like_parts = []
            for cat, cnt in sorted(likes.items()):
                label = ACTION_CATEGORY_LABELS.get(cat, cat)
                if cnt > 1:
                    like_parts.append(f"{label}(×{cnt})")
                else:
                    like_parts.append(label)
            parts.append("喜欢" + "、".join(like_parts))

        if avoids:
            avoid_parts = []
            for cat, cnt in sorted(avoids.items()):
                label = ACTION_CATEGORY_LABELS.get(cat, cat)
                if cnt > 1:
                    avoid_parts.append(f"{label}(×{cnt})")
                else:
                    avoid_parts.append(label)
            parts.append("避免" + "、".join(avoid_parts))

        if not parts:
            return ""
        return "导演偏好: " + "；".join(parts)


# ═══════════════════════════════════════════════
#  单例管理
# ═══════════════════════════════════════════════

_store: DirectorPreferenceStore | None = None


def get_preference_store() -> DirectorPreferenceStore:
    """获取全局导演偏好存储单例。"""
    global _store
    if _store is None:
        _store = DirectorPreferenceStore()
    return _store


def reset_preference_store() -> None:
    """重置导演偏好存储（用于测试）。"""
    global _store
    _store = None
