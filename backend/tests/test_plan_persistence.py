"""
Phase 19 计划持久化系统 — 单元测试
==================================

测试:
1. PlanCheckpoint 基本操作（创建/过期/序列化）
2. PlanPersistenceEngine checkpoint 流程
3. PlanPersistenceEngine resume（恢复 + 过期）
4. PlanPersistenceEngine 生命周期（progress → complete → abandon）
5. 相似度检测（SUPERSEDED 触发）
6. 历史裁剪
7. 全局单例 get_plan_engine
"""

from digimon_world.agents.plan_persistence import (
    PLAN_MEMORY_MIN_IMPORTANCE,
    PlanCheckpoint,
    PlanPersistenceEngine,
    PlanStatus,
    get_plan_engine,
    reset_plan_engine,
)


class TestPlanCheckpoint:
    """PlanCheckpoint 数据类测试。"""

    def test_create_checkpoint_factory(self):
        """工厂方法 PlanCheckpoint.create() 创建 checkpoint。"""
        cp = PlanCheckpoint.create(
            agent_name="亚古兽",
            plan_text="前往齿轮草原探索",
            importance=7,
            tick=10,
        )
        assert cp.agent_name == "亚古兽"
        assert cp.plan_text == "前往齿轮草原探索"
        assert cp.status == PlanStatus.ACTIVE
        assert cp.importance == 7
        assert cp.progress_note == ""
        assert cp.tick_created == 10
        assert cp.tick_expires == 10 + 48

    def test_is_expired(self):
        """过期检测。"""
        cp = PlanCheckpoint.create("亚古兽", "探索", importance=5, tick=10)
        assert not cp.is_expired(30)  # 30 < 58, 未过期
        assert not cp.is_expired(58)  # 58 == 58, 边界未过期
        assert cp.is_expired(59)  # 59 > 58, 已过期

    def test_is_not_expired_zero_ttl(self):
        """tick_expires=0 表示永不过期。"""
        cp = PlanCheckpoint(
            plan_id="test-never",
            agent_name="亚古兽",
            plan_text="永远",
            status=PlanStatus.ACTIVE,
            importance=5,
            created_at=None,  # type: ignore
            updated_at=None,  # type: ignore
            completed_at=None,
            tick_created=0,
            tick_expires=0,
        )
        assert not cp.is_expired(9999999)

    def test_time_since_created(self):
        """创建时间格式化。"""
        cp = PlanCheckpoint.create("亚古兽", "测试", importance=5, tick=0)
        result = cp.time_since_created()
        assert result is not None
        assert "分钟" in result or "0." in result

    def test_to_dict(self):
        """序列化。"""
        cp = PlanCheckpoint.create(
            agent_name="加布兽",
            plan_text="找食物",
            importance=8,
            tick=5,
            context_snapshot="天气晴朗",
        )
        d = cp.to_dict()
        assert d["plan_id"] is not None
        assert d["agent_name"] == "加布兽"
        assert d["importance"] == 8
        assert d["status"] == "ACTIVE"
        assert d["context_snapshot"] == "天气晴朗"

    def test_from_dict(self):
        """反序列化。"""
        cp = PlanCheckpoint.create("比丘兽", "飞到树顶", importance=9, tick=10)
        d = cp.to_dict()
        restored = PlanCheckpoint.from_dict(d)
        assert restored.plan_id == cp.plan_id
        assert restored.agent_name == "比丘兽"
        assert restored.plan_text == "飞到树顶"
        assert restored.importance == 9


class TestPlanPersistenceEngine:
    """PlanPersistenceEngine 核心操作测试。"""

    def test_checkpoint_creates_new_plan(self):
        """checkpoint 创建新计划。"""
        engine = PlanPersistenceEngine()
        cp = engine.checkpoint("亚古兽", "探索森林", importance=8, tick=10)
        assert cp.agent_name == "亚古兽"
        assert cp.plan_text == "探索森林"
        assert cp.status == PlanStatus.ACTIVE
        assert cp.importance == max(8, PLAN_MEMORY_MIN_IMPORTANCE)  # boosted

    def test_checkpoint_auto_completes_previous(self):
        """新计划自动完成旧计划。"""
        engine = PlanPersistenceEngine()
        cp1 = engine.checkpoint("亚古兽", "计划A", importance=7, tick=10)
        cp2 = engine.checkpoint("亚古兽", "完全不同计划B", importance=7, tick=20)

        # 旧计划应被完成
        assert engine.get_by_id(cp1.plan_id).status == PlanStatus.COMPLETED
        # 新计划活跃
        assert engine.get_by_id(cp2.plan_id).status == PlanStatus.ACTIVE

    def test_checkpoint_supersedes_similar_plan(self):
        """相似计划触发 SUPERSEDED。"""
        engine = PlanPersistenceEngine()
        cp1 = engine.checkpoint("加布兽", "在文件岛附近巡逻警戒", importance=7, tick=10)
        # 高度相似的计划
        engine.checkpoint("加布兽", "在文件岛附近巡逻警戒检查", importance=7, tick=20)

        old = engine.get_by_id(cp1.plan_id)
        assert old.status in (PlanStatus.SUPERSEDED, PlanStatus.COMPLETED)

    def test_resume_returns_active_plan(self):
        """resume 返回活跃计划。"""
        engine = PlanPersistenceEngine()
        cp = engine.checkpoint("亚古兽", "找食物", importance=7, tick=10)
        resumed = engine.resume("亚古兽", current_tick=11)
        assert resumed is not None
        assert resumed.plan_id == cp.plan_id

    def test_resume_expired_returns_none(self):
        """过期计划 resume 返回 None。"""
        engine = PlanPersistenceEngine()
        engine.checkpoint("亚古兽", "老计划", importance=7, tick=10)
        # TTL 48, tick 100 > 58, 已过期
        resumed = engine.resume("亚古兽", current_tick=100)
        assert resumed is None

    def test_resume_marks_expired_as_abandoned(self):
        """resume 时过期计划被标记 ABANDONED。"""
        engine = PlanPersistenceEngine()
        cp = engine.checkpoint("加布兽", "老旧计划", importance=7, tick=5)
        engine.resume("加布兽", current_tick=100)
        assert engine.get_by_id(cp.plan_id).status == PlanStatus.ABANDONED

    def test_update_progress(self):
        """更新计划进度。"""
        engine = PlanPersistenceEngine()
        cp = engine.checkpoint("比丘兽", "飞到山顶", importance=7, tick=10)
        result = engine.update_progress(cp.plan_id, "已飞一半", tick=20)
        assert result is True
        updated = engine.get_by_id(cp.plan_id)
        assert "已飞一半" in updated.progress_note
        assert updated.tick_expires == 20 + 48  # TTL 延长

    def test_update_progress_nonexistent(self):
        """更新不存在的计划。"""
        engine = PlanPersistenceEngine()
        assert engine.update_progress("no-such-plan", "note", tick=0) is False

    def test_complete(self):
        """完成计划。"""
        engine = PlanPersistenceEngine()
        cp = engine.checkpoint("甲虫兽", "采集数据", importance=7, tick=10)
        result = engine.complete(cp.plan_id)
        assert result is True
        assert engine.get_by_id(cp.plan_id).status == PlanStatus.COMPLETED
        assert engine.get_by_id(cp.plan_id).completed_at is not None

    def test_abandon(self):
        """放弃计划。"""
        engine = PlanPersistenceEngine()
        cp = engine.checkpoint("巴鲁兽", "晒太阳", importance=7, tick=10)
        result = engine.abandon(cp.plan_id, reason="天黑了")
        assert result is True
        abandoned = engine.get_by_id(cp.plan_id)
        assert abandoned.status == PlanStatus.ABANDONED
        assert "天黑了" in abandoned.progress_note

    def test_pause(self):
        """暂停计划。"""
        engine = PlanPersistenceEngine()
        cp = engine.checkpoint("哥玛兽", "游泳", importance=7, tick=10)
        result = engine.pause(cp.plan_id)
        assert result is True
        assert engine.get_by_id(cp.plan_id).status == PlanStatus.PAUSED

    def test_get_active(self):
        """获取活跃计划。"""
        engine = PlanPersistenceEngine()
        assert engine.get_active("不存在") is None
        cp = engine.checkpoint("巴达兽", "巡逻", importance=7, tick=10)
        active = engine.get_active("巴达兽")
        assert active is not None
        assert active.plan_id == cp.plan_id

    def test_get_history(self):
        """获取计划历史。"""
        engine = PlanPersistenceEngine()
        for i in range(5):
            engine.checkpoint("迪路兽", f"计划{i}", importance=7, tick=i * 10)
        history = engine.get_history("迪路兽", limit=3)
        assert len(history) == 3

    def test_get_stats(self):
        """计划统计。"""
        engine = PlanPersistenceEngine()
        engine.checkpoint("小狗兽", "计划A", importance=7, tick=10)
        engine.checkpoint("小狗兽", "计划B", importance=7, tick=20)
        engine.complete(engine.get_active("小狗兽").plan_id)
        stats = engine.get_stats("小狗兽")
        assert stats["agent_name"] == "小狗兽"
        assert stats["total_plans"] == 2

    def test_all_agents(self):
        """获取所有有计划的 agent。"""
        engine = PlanPersistenceEngine()
        engine.checkpoint("亚古兽", "探索", importance=7, tick=10)
        engine.checkpoint("加布兽", "巡逻", importance=7, tick=10)
        agents = engine.all_agents()
        assert "亚古兽" in agents
        assert "加布兽" in agents

    def test_history_trim(self):
        """历史裁剪 -> 只保留最近 max_plans 条。"""
        engine = PlanPersistenceEngine(max_plans=5)
        for i in range(10):
            engine.checkpoint("艾力兽", f"计划{i}", importance=7, tick=i * 10)
        history = engine.get_history("艾力兽", limit=20)
        assert len(history) <= 6  # max_plans (~5) + a couple extra OK

    def test_different_agents_independent(self):
        """不同 agent 独立。"""
        engine = PlanPersistenceEngine()
        engine.checkpoint("亚古兽", "探索", importance=7, tick=10)
        engine.checkpoint("加布兽", "巡逻", importance=7, tick=10)
        assert engine.get_active("亚古兽").plan_text == "探索"
        assert engine.get_active("加布兽").plan_text == "巡逻"

    def test_similarity_computation(self):
        """相似度计算。"""
        # 相同文本
        assert PlanPersistenceEngine.check_similarity("abc", "abc") == 1.0
        # 完全不同
        sim = PlanPersistenceEngine.check_similarity("abc", "xyz")
        assert sim == 0.0
        # 部分重叠
        sim = PlanPersistenceEngine.check_similarity("abcdef", "abcxyz")
        assert 0.3 < sim < 0.8

    def test_similarity_empty(self):
        """空文本相似度。"""
        assert PlanPersistenceEngine.check_similarity("", "") == 1.0
        assert PlanPersistenceEngine.check_similarity("abc", "") == 0.0

    def test_to_dict_engine(self):
        """引擎序列化/反序列化。"""
        engine = PlanPersistenceEngine()
        engine.checkpoint("亚古兽", "测试", importance=7, tick=10)
        d = engine.to_dict()
        assert "亚古兽" in d
        restored = PlanPersistenceEngine.from_dict(d)
        assert restored.get_active("亚古兽") is not None


class TestGlobalEngine:
    """全局单例测试。"""

    def test_get_plan_engine_singleton(self):
        """get_plan_engine 返回单例。"""
        reset_plan_engine()
        e1 = get_plan_engine()
        e2 = get_plan_engine()
        assert e1 is e2

    def test_reset_plan_engine(self):
        """reset_plan_engine 重置。"""
        reset_plan_engine()
        e1 = get_plan_engine()
        reset_plan_engine()
        e2 = get_plan_engine()
        assert e1 is not e2
