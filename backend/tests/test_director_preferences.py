"""
导演偏好反馈系统 — 测试套件 (Phase 31 Task 3)

覆盖:
- PreferenceRecord 数据类
- DirectorPreferenceStore 记录/查询
- get_prompt_hints 格式化
- 单例模式
- 边界条件
"""
from __future__ import annotations

import pytest

from digimon_world.world.director_preferences import (
    ACTION_CATEGORY_LABELS,
    VALID_ACTION_CATEGORIES,
    VALID_PREFERENCES,
    DirectorPreferenceStore,
    PreferenceRecord,
    get_preference_store,
    reset_preference_store,
)


# ── PreferenceRecord 数据类 ──────────────────


class TestPreferenceRecord:
    """PreferenceRecord 数据类测试。"""

    def test_create_basic(self):
        """创建基本记录。"""
        rec = PreferenceRecord(
            agent_name="亚古兽",
            preference="like",
            action_category="explore",
        )
        assert rec.agent_name == "亚古兽"
        assert rec.preference == "like"
        assert rec.action_category == "explore"
        assert rec.context == ""
        assert rec.tick == 0
        assert rec.id == 0

    def test_create_full(self):
        """创建含所有字段的记录。"""
        rec = PreferenceRecord(
            agent_name="加布兽",
            preference="avoid",
            action_category="battle",
            context="太鲁莽了",
            tick=42,
            created_at="2026-07-21T12:00:00+00:00",
            id=5,
        )
        assert rec.agent_name == "加布兽"
        assert rec.preference == "avoid"
        assert rec.context == "太鲁莽了"
        assert rec.tick == 42
        assert rec.id == 5

    def test_to_dict(self):
        """序列化为字典。"""
        rec = PreferenceRecord(
            agent_name="比丘兽",
            preference="like",
            action_category="social",
            tick=10,
            id=1,
        )
        d = rec.to_dict()
        assert d["agent_name"] == "比丘兽"
        assert d["preference"] == "like"
        assert d["action_category"] == "social"
        assert d["tick"] == 10
        assert d["id"] == 1

    def test_equality_by_value(self):
        """值相等性（dataclass 默认行为）。"""
        a = PreferenceRecord(agent_name="x", preference="like", action_category="explore", id=1)
        b = PreferenceRecord(agent_name="x", preference="like", action_category="explore", id=1)
        assert a == b


# ── DirectorPreferenceStore ───────────────────


class TestPreferenceStore:
    """DirectorPreferenceStore 核心功能测试。"""

    def test_record_single(self):
        """记录单条偏好。"""
        store = DirectorPreferenceStore()
        rec = store.record("亚古兽", "like", "explore", tick=1)
        assert rec.id == 1
        assert rec.agent_name == "亚古兽"
        assert rec.preference == "like"
        assert rec.action_category == "explore"
        assert rec.tick == 1
        assert rec.created_at  # 自动填充

    def test_record_auto_increment_id(self):
        """ID 自增。"""
        store = DirectorPreferenceStore()
        r1 = store.record("a", "like", "explore")
        r2 = store.record("a", "avoid", "battle")
        assert r1.id == 1
        assert r2.id == 2

    def test_record_invalid_preference(self):
        """非法 preference 抛出 ValueError。"""
        store = DirectorPreferenceStore()
        with pytest.raises(ValueError, match="非法 preference"):
            store.record("a", "neutral", "explore")  # type: ignore[arg-type]

    def test_record_invalid_action_category(self):
        """非法 action_category 抛出 ValueError。"""
        store = DirectorPreferenceStore()
        with pytest.raises(ValueError, match="非法 action_category"):
            store.record("a", "like", "singing")  # type: ignore[arg-type]

    def test_record_context_saved(self):
        """附言字段保存正确。"""
        store = DirectorPreferenceStore()
        rec = store.record("a", "like", "social", context="多交朋友好")
        assert rec.context == "多交朋友好"


class TestGetForAgent:
    """get_for_agent 测试。"""

    def test_empty_returns_empty(self):
        """无记录时返回空列表。"""
        store = DirectorPreferenceStore()
        assert store.get_for_agent("不存在") == []

    def test_single_agent(self):
        """单只数码兽的偏好。"""
        store = DirectorPreferenceStore()
        store.record("亚古兽", "like", "explore")
        store.record("亚古兽", "avoid", "battle")
        results = store.get_for_agent("亚古兽")
        assert len(results) == 2
        assert {r.action_category for r in results} == {"explore", "battle"}

    def test_multiple_agents_isolation(self):
        """多只数码兽互不干扰。"""
        store = DirectorPreferenceStore()
        store.record("亚古兽", "like", "explore")
        store.record("加布兽", "avoid", "battle")
        assert len(store.get_for_agent("亚古兽")) == 1
        assert len(store.get_for_agent("加布兽")) == 1
        assert store.get_for_agent("比丘兽") == []

    def test_results_sorted_by_time(self):
        """结果按插入顺序（时间升序）。"""
        store = DirectorPreferenceStore()
        store.record("a", "like", "explore")
        store.record("a", "avoid", "battle")
        store.record("a", "like", "social")
        results = store.get_for_agent("a")
        assert [r.id for r in results] == [1, 2, 3]


class TestAllRecords:
    """all_records 和 count 测试。"""

    def test_empty(self):
        store = DirectorPreferenceStore()
        assert store.all_records() == []
        assert len(store.all_records()) == 0

    def test_multiple(self):
        store = DirectorPreferenceStore()
        store.record("a", "like", "explore")
        store.record("b", "avoid", "battle")
        assert len(store.all_records()) == 2


class TestGetPromptHints:
    """get_prompt_hints 格式化测试。"""

    def test_no_preferences_empty(self):
        """无偏好 → 空字符串。"""
        store = DirectorPreferenceStore()
        assert store.get_prompt_hints("亚古兽") == ""

    def test_single_like(self):
        """单条 like → "导演偏好: 喜欢探索"。"""
        store = DirectorPreferenceStore()
        store.record("亚古兽", "like", "explore")
        hints = store.get_prompt_hints("亚古兽")
        assert "喜欢" in hints
        assert "探索" in hints
        assert "导演偏好:" in hints

    def test_multiple_likes_same_category(self):
        """多条同类别 like → "导演偏好: 喜欢探索(×3)"。"""
        store = DirectorPreferenceStore()
        for _ in range(3):
            store.record("亚古兽", "like", "explore")
        hints = store.get_prompt_hints("亚古兽")
        assert "探索(×3)" in hints

    def test_single_avoid(self):
        """单条 avoid → "导演偏好: 避免战斗"。"""
        store = DirectorPreferenceStore()
        store.record("亚古兽", "avoid", "battle")
        hints = store.get_prompt_hints("亚古兽")
        assert "避免" in hints
        assert "战斗" in hints

    def test_mixed_like_avoid(self):
        """like 和 avoid 混合。"""
        store = DirectorPreferenceStore()
        for _ in range(3):
            store.record("亚古兽", "like", "explore")
        store.record("亚古兽", "like", "social")
        for _ in range(2):
            store.record("亚古兽", "avoid", "battle")
        hints = store.get_prompt_hints("亚古兽")
        assert "喜欢" in hints
        assert "探索(×3)" in hints
        assert "社交" in hints
        assert "避免" in hints
        assert "战斗(×2)" in hints
        # like 在 avoid 前面
        assert hints.index("喜欢") < hints.index("避免")

    def test_only_avoids(self):
        """只有 avoid → "导演偏好: 避免战斗(×2)"。"""
        store = DirectorPreferenceStore()
        for _ in range(2):
            store.record("亚古兽", "avoid", "battle")
        hints = store.get_prompt_hints("亚古兽")
        assert "避免" in hints
        assert "喜欢" not in hints

    def test_multiple_agents_hints(self):
        """不同 agent 的 hints 互不干扰。"""
        store = DirectorPreferenceStore()
        store.record("a", "like", "explore")
        store.record("b", "avoid", "battle")
        hints_a = store.get_prompt_hints("a")
        hints_b = store.get_prompt_hints("b")
        assert "探索" in hints_a
        assert "战斗" in hints_b

    def test_hints_use_chinese_labels(self):
        """hints 使用中文标签。"""
        store = DirectorPreferenceStore()
        store.record("亚古兽", "like", "aggressive")
        hints = store.get_prompt_hints("亚古兽")
        assert "攻击" in hints

    def test_large_number_of_records(self):
        """大量记录不会崩溃。"""
        store = DirectorPreferenceStore()
        for i in range(100):
            store.record("a", "like", "explore", tick=i)
        assert len(store.all_records()) == 100


# ── 单例模式 ─────────────────────────────────


class TestSingleton:
    """单例 get_preference_store / reset_preference_store 测试。"""

    def test_same_instance(self):
        """多次调用返回同一实例。"""
        reset_preference_store()
        a = get_preference_store()
        b = get_preference_store()
        assert a is b

    def test_reset_creates_new(self):
        """reset 后返回新实例。"""
        reset_preference_store()
        a = get_preference_store()
        a.record("x", "like", "explore")
        reset_preference_store()
        b = get_preference_store()
        assert a is not b
        assert len(b.all_records()) == 0


# ── 边界条件 ────────────────────────────────


class TestEdgeCases:
    """边界条件测试。"""

    def test_empty_agent_name(self):
        """空字符串 agent 名也能正常工作。"""
        store = DirectorPreferenceStore()
        rec = store.record("", "like", "explore")
        assert rec.agent_name == ""
        results = store.get_for_agent("")
        assert len(results) == 1

    def test_all_action_categories_valid(self):
        """所有 VALID_ACTION_CATEGORIES 都合法。"""
        store = DirectorPreferenceStore()
        for cat in VALID_ACTION_CATEGORIES:
            rec = store.record("test", "like", cat)
            assert rec.action_category == cat

    def test_action_labels_cover_all_categories(self):
        """ACTION_CATEGORY_LABELS 覆盖所有类别。"""
        for cat in VALID_ACTION_CATEGORIES:
            assert cat in ACTION_CATEGORY_LABELS, f"缺少 {cat} 的中文标签"

    def test_preference_values_complete(self):
        """VALID_PREFERENCES 包含 like 和 avoid。"""
        assert "like" in VALID_PREFERENCES
        assert "avoid" in VALID_PREFERENCES
        assert len(VALID_PREFERENCES) == 2

    def test_record_fields_complete(self):
        """所有字段都正确存储。"""
        store = DirectorPreferenceStore()
        rec = store.record("a", "like", "gather", context="好", tick=99)
        assert rec.id > 0
        assert rec.agent_name == "a"
        assert rec.preference == "like"
        assert rec.action_category == "gather"
        assert rec.context == "好"
        assert rec.tick == 99
        assert rec.created_at  # 非空
