"""memory_autonomy 模块测试。

覆盖:
- EbbinghausCurve: retention 计算, half-life, for_agent 工厂
- ImportanceAssessor: 启发式评估, LLM fallback
- ForgettingEngine: register, get_strength, update_all_strengths, get_weak_memories, mark_stale, diagnose
- MemoryRehearsal: select_for_rehearsal, rehearse
- MemoryUpdateDetector: detect_stale 四种变化类型
- MemoryAutonomy: register, assess_importance, step, notify_state_change, diagnose
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import pytest

from digimon_world.memory.memory_autonomy import (
    EbbinghausCurve,
    FORGETTING_STRENGTH_DEFAULT,
    ForgettingEngine,
    ImportanceAssessor,
    MemoryAutonomy,
    MemoryHealth,
    MemoryRehearsal,
    MemoryUpdateDetector,
    REHEARSAL_STRENGTH_THRESHOLD,
)
from digimon_world.memory.memory_stream import MemoryNode


# ──────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────

def make_node(
    description: str,
    importance: int = 5,
    memory_type: str = "observation",
    node_id: int = 0,
) -> MemoryNode:
    return MemoryNode(
        timestamp=datetime.utcnow(),
        description=description,
        importance=importance,
        memory_type=memory_type,
        node_id=node_id,
    )


def _register_health(engine: ForgettingEngine, node_id: int, **kw) -> MemoryHealth:
    """Helper: forcibly inject a MemoryHealth with custom fields into the engine."""
    node = make_node("test", node_id=node_id, **{k: v for k, v in kw.items() if k in ("importance", "memory_type")})
    health = MemoryHealth(memory=node, strength=kw.get("strength", 1.0))
    if "created_at" in kw:
        health.created_at = kw["created_at"]
    if "last_rehearsed" in kw:
        health.last_rehearsed = kw["last_rehearsed"]
    if "rehearsal_count" in kw:
        health.rehearsal_count = kw["rehearsal_count"]
    if "stale" in kw:
        health.stale = kw["stale"]
        health.stale_reason = kw.get("stale_reason", "")
    engine.memory_health[node_id] = health
    return health


# ──────────────────────────────────────────────
# EbbinghausCurve
# ──────────────────────────────────────────────

class TestEbbinghausCurve:
    def test_retention_at_zero_is_one(self):
        curve = EbbinghausCurve(S=1000)
        assert curve.retention(0) == 1.0

    def test_retention_negative_time_returns_one(self):
        curve = EbbinghausCurve(S=1000)
        assert curve.retention(-5) == 1.0

    def test_retention_at_half_life_is_about_half(self):
        curve = EbbinghausCurve(S=1000)
        half = curve.half_life_seconds()
        r = curve.retention(half)
        assert abs(r - 0.5) < 1e-6

    def test_retention_decays_over_time(self):
        curve = EbbinghausCurve(S=1000)
        r1 = curve.retention(100)
        r2 = curve.retention(500)
        r3 = curve.retention(2000)
        # 时间越长，保留率越低
        assert r1 > r2 > r3
        assert r1 < 1.0
        assert r3 > 0.0

    def test_half_life_formula(self):
        curve = EbbinghausCurve(S=3600)
        expected = 3600 * math.log(2)
        assert abs(curve.half_life_seconds() - expected) < 0.01

    def test_for_agent_brave_is_faster_forgetting(self):
        curve = EbbinghausCurve.for_agent("亚古兽", personality_trait="brave")
        # brave: factor=1.2 → S = 3600 / 1.2 = 3000
        assert curve.S == FORGETTING_STRENGTH_DEFAULT / 1.2

    def test_for_agent_timid_is_slower_forgetting(self):
        curve = EbbinghausCurve.for_agent("巴达兽", personality_trait="timid")
        # timid: factor=0.8 → S = 3600 / 0.8 = 4500
        assert curve.S == FORGETTING_STRENGTH_DEFAULT / 0.8

    def test_for_agent_lazy_is_fastest_forgetting(self):
        curve = EbbinghausCurve.for_agent("鼻涕兽", personality_trait="lazy")
        # lazy: factor=1.5 → S = 3600 / 1.5 = 2400
        assert curve.S == FORGETTING_STRENGTH_DEFAULT / 1.5

    def test_for_agent_unknown_personality_defaults_to_one(self):
        curve = EbbinghausCurve.for_agent("unknown", personality_trait="unknown_trait")
        assert curve.S == FORGETTING_STRENGTH_DEFAULT

    def test_for_agent_case_insensitive_personality(self):
        curve = EbbinghausCurve.for_agent("test", personality_trait="BRAVE")
        assert curve.S == FORGETTING_STRENGTH_DEFAULT / 1.2


# ──────────────────────────────────────────────
# ImportanceAssessor
# ──────────────────────────────────────────────

class TestImportanceAssessor:
    def test_heuristic_high_signals_return_8(self):
        assessor = ImportanceAssessor()
        for desc in ["进化了!", "击败敌人", "和太一建立了羁绊", "发现了徽章", "孵化了数码蛋"]:
            result = assessor.assess(desc, "亚古兽")
            assert result["importance"] == 8, f"desc={desc}"
            assert result["reason"] == "heuristic"

    def test_heuristic_mid_signals_return_6(self):
        assessor = ImportanceAssessor()
        for desc in ["战斗开始了", "和加布兽对话", "探索新区域"]:
            result = assessor.assess(desc, "亚古兽")
            assert result["importance"] == 6, f"desc={desc}"

    def test_heuristic_low_signals_return_3(self):
        assessor = ImportanceAssessor()
        for desc in ["向前移动", "休息一下", "睡觉了"]:
            result = assessor.assess(desc, "亚古兽")
            assert result["importance"] == 3, f"desc={desc}"

    def test_heuristic_returns_none_for_unknown_then_llm_fallback(self):
        assessor = ImportanceAssessor()
        # 这个描述不匹配任何启发式关键词 → 走 _llm_assess_fallback
        result = assessor.assess("一朵花在风中摇曳", "亚古兽")
        assert "importance" in result
        assert "reason" in result
        assert result["reason"] != "heuristic"

    def test_llm_fallback_short_description_is_low_importance(self):
        assessor = ImportanceAssessor()
        short = "hi"  # len=2, <=30
        result = assessor._llm_assess_fallback(short, "test", "neutral", "observation")
        assert result["importance"] == 4

    def test_llm_fallback_medium_description_is_mid_importance(self):
        assessor = ImportanceAssessor()
        medium = "a" * 35  # len=35, >30 and <=80
        result = assessor._llm_assess_fallback(medium, "test", "neutral", "observation")
        assert result["importance"] == 5

    def test_llm_fallback_long_description_is_higher_importance(self):
        assessor = ImportanceAssessor()
        long_desc = "x" * 100  # len=100, >80
        result = assessor._llm_assess_fallback(long_desc, "test", "neutral", "observation")
        assert result["importance"] == 6

    def test_assess_returns_dict_with_expected_keys(self):
        assessor = ImportanceAssessor()
        result = assessor.assess("进化了", "亚古兽", agent_personality="brave", memory_type="observation")
        assert set(result.keys()) == {"importance", "reason", "keywords"}
        assert isinstance(result["importance"], int)
        assert isinstance(result["reason"], str)
        assert isinstance(result["keywords"], list)


# ──────────────────────────────────────────────
# ForgettingEngine
# ──────────────────────────────────────────────

class TestForgettingEngine:
    def test_register_creates_health_with_strength_one(self):
        engine = ForgettingEngine()
        node = make_node("test memory", node_id=1)
        health = engine.register(node)
        assert health.strength == 1.0
        assert health.memory is node
        assert health.rehearsal_count == 0
        assert health.last_rehearsed is None
        assert not health.stale

    def test_register_raises_valueerror_for_none_node_id(self):
        engine = ForgettingEngine()
        node = MemoryNode(timestamp=datetime.utcnow(), description="x", importance=5)
        with pytest.raises(ValueError, match="node_id"):
            engine.register(node)

    def test_get_strength_unknown_node_returns_zero(self):
        engine = ForgettingEngine()
        assert engine.get_strength(999) == 0.0

    def test_get_strength_stale_memory_returns_zero(self):
        engine = ForgettingEngine()
        node = make_node("stale", node_id=1)
        engine.register(node)
        engine.mark_stale(1, "outdated")
        assert engine.get_strength(1) == 0.0

    def test_get_strength_decays_over_time(self):
        engine = ForgettingEngine(curve=EbbinghausCurve(S=100))
        node = make_node("decaying", node_id=1)
        health = engine.register(node)
        # 手动把 created_at 改到 100 秒前
        health.created_at = datetime.utcnow() - timedelta(seconds=100)
        s = engine.get_strength(1)
        # 100 秒 * e^(-100/100) = e^(-1) ≈ 0.3679
        assert 0.3 < s < 0.4

    def test_get_strength_with_rehearsal_boosts(self):
        engine = ForgettingEngine(curve=EbbinghausCurve(S=100))
        node = make_node("rehearsed", node_id=1)
        health = engine.register(node)
        # 模拟 50 秒前进行了复述
        health.last_rehearsed = datetime.utcnow() - timedelta(seconds=50)
        health.rehearsal_count = 3
        s = engine.get_strength(1)
        # e^(-50/100) * (1 + 0.05*3) = e^(-0.5) * 1.15 ≈ 0.6065 * 1.15 ≈ 0.697
        assert s > 0.6

    def test_get_strength_with_rehearsal_capped_at_one(self):
        engine = ForgettingEngine(curve=EbbinghausCurve(S=10000))
        node = make_node("capped", node_id=1)
        health = engine.register(node)
        health.last_rehearsed = datetime.utcnow()
        health.rehearsal_count = 100
        s = engine.get_strength(1)
        assert s <= 1.0

    def test_update_all_strengths_returns_stats(self):
        engine = ForgettingEngine(curve=EbbinghausCurve(S=10000))
        for i in range(3):
            engine.register(make_node(f"mem {i}", node_id=i))
        stats = engine.update_all_strengths()
        assert stats == {"total": 3, "weak": 0, "strong": 3}

    def test_update_all_strengths_detects_weak(self):
        engine = ForgettingEngine(curve=EbbinghausCurve(S=10))
        for i in range(5):
            node = make_node(f"weak mem {i}", node_id=i)
            health = engine.register(node)
            health.created_at = datetime.utcnow() - timedelta(seconds=20)
        stats = engine.update_all_strengths()
        assert stats["weak"] == 5  # all decayed below 0.3

    def test_get_weak_memories_filters_below_threshold(self):
        engine = ForgettingEngine(curve=EbbinghausCurve(S=10))
        for i in range(3):
            node = make_node(f"mem {i}", node_id=i)
            health = engine.register(node)
            health.created_at = datetime.utcnow() - timedelta(seconds=30)
        weak = engine.get_weak_memories(threshold=0.5)
        assert len(weak) == 3

    def test_get_weak_memories_excludes_stale(self):
        engine = ForgettingEngine(curve=EbbinghausCurve(S=10))
        node = make_node("stale weak", node_id=1)
        health = engine.register(node)
        health.created_at = datetime.utcnow() - timedelta(seconds=30)
        engine.mark_stale(1, "test")
        weak = engine.get_weak_memories()
        assert len(weak) == 0

    def test_get_weak_memories_excludes_zero_strength(self):
        engine = ForgettingEngine()
        _register_health(engine, 1, strength=0.0)
        weak = engine.get_weak_memories()
        assert len(weak) == 0

    def test_mark_stale_sets_flags_and_zero_strength(self):
        engine = ForgettingEngine()
        node = make_node("outdated", node_id=42)
        engine.register(node)
        engine.mark_stale(42, "evolution changed")
        health = engine.memory_health[42]
        assert health.stale is True
        assert health.stale_reason == "evolution changed"
        assert health.strength == 0.0

    def test_mark_stale_nonexistent_does_not_raise(self):
        engine = ForgettingEngine()
        # 不应抛出异常
        engine.mark_stale(999, "no such memory")

    def test_diagnose_returns_comprehensive_report(self):
        engine = ForgettingEngine(curve=EbbinghausCurve(S=10000))
        for i in range(5):
            engine.register(make_node(f"mem {i}", node_id=i, importance=5))
        engine.mark_stale(0, "test")
        report = engine.diagnose()
        assert report["total_memories"] == 5
        assert "strong_count" in report
        assert "weak_count" in report
        assert report["stale_count"] == 1
        assert "forgetting_half_life_seconds" in report
        assert "top_weak" in report


# ──────────────────────────────────────────────
# MemoryRehearsal
# ──────────────────────────────────────────────

class TestMemoryRehearsal:
    def test_select_for_rehearsal_empty_engine_returns_empty(self):
        rehearsal = MemoryRehearsal()
        engine = ForgettingEngine()
        selected = rehearsal.select_for_rehearsal(engine)
        assert selected == []

    def test_select_for_rehearsal_picks_high_importance_weak(self):
        engine = ForgettingEngine(curve=EbbinghausCurve(S=10))
        rehearsal = MemoryRehearsal()
        # 高重要性 + 弱强度
        node = make_node("important event", importance=9, node_id=1)
        health = engine.register(node)
        health.created_at = datetime.utcnow() - timedelta(seconds=30)
        selected = rehearsal.select_for_rehearsal(engine)
        assert len(selected) == 1
        assert selected[0].memory.node_id == 1

    def test_select_for_rehearsal_falls_back_to_importance_5(self):
        engine = ForgettingEngine(curve=EbbinghausCurve(S=10))
        rehearsal = MemoryRehearsal()
        # importance=6 < 7，但 >= 5
        node = make_node("mid event", importance=6, node_id=1)
        health = engine.register(node)
        health.created_at = datetime.utcnow() - timedelta(seconds=30)
        selected = rehearsal.select_for_rehearsal(engine)
        assert len(selected) == 1

    def test_select_for_rehearsal_skips_low_importance(self):
        engine = ForgettingEngine(curve=EbbinghausCurve(S=10))
        rehearsal = MemoryRehearsal()
        node = make_node("low event", importance=2, node_id=1)
        health = engine.register(node)
        health.created_at = datetime.utcnow() - timedelta(seconds=30)
        selected = rehearsal.select_for_rehearsal(engine)
        assert selected == []

    def test_select_for_rehearsal_respects_max_count(self):
        engine = ForgettingEngine(curve=EbbinghausCurve(S=10))
        rehearsal = MemoryRehearsal()
        for i in range(5):
            node = make_node(f"event {i}", importance=9, node_id=i)
            health = engine.register(node)
            health.created_at = datetime.utcnow() - timedelta(seconds=30)
        selected = rehearsal.select_for_rehearsal(engine, max_count=2)
        assert len(selected) <= 2

    def test_rehearse_resets_strength_and_increments_count(self):
        rehearsal = MemoryRehearsal()
        node = make_node("rehearse me", node_id=1)
        health = MemoryHealth(memory=node, strength=0.2)
        rehearsal.rehearse(health)
        assert health.strength == 1.0
        assert health.rehearsal_count == 1
        assert health.last_rehearsed is not None

    def test_multiple_rehearsals_increment_count(self):
        rehearsal = MemoryRehearsal()
        node = make_node("multi rehearse", node_id=1)
        health = MemoryHealth(memory=node, strength=0.2)
        for _ in range(4):
            rehearsal.rehearse(health)
        assert health.rehearsal_count == 4
        assert health.strength == 1.0


# ──────────────────────────────────────────────
# MemoryUpdateDetector
# ──────────────────────────────────────────────

class TestMemoryUpdateDetector:
    def test_detect_stale_evolution_with_old_value_match(self):
        detector = MemoryUpdateDetector()
        node = make_node("我是成长期", node_id=1)
        health = MemoryHealth(memory=node)
        change = {"type": "evolution", "old_value": "成长期", "new_value": "成熟期"}
        is_stale, reason = detector.detect_stale(health, change)
        assert is_stale is True
        assert "成长期" in reason

    def test_detect_stale_evolution_pattern_match_no_old_value(self):
        detector = MemoryUpdateDetector()
        node = make_node("目前是成长期数码兽", node_id=1)
        health = MemoryHealth(memory=node)
        change = {"type": "evolution", "old_value": "", "new_value": ""}
        is_stale, reason = detector.detect_stale(health, change)
        assert is_stale is True

    def test_detect_stale_location_change(self):
        detector = MemoryUpdateDetector()
        node = make_node("我在文件岛游荡", node_id=1)
        health = MemoryHealth(memory=node)
        change = {"type": "location", "old_value": "文件岛", "new_value": "无限山"}
        is_stale, reason = detector.detect_stale(health, change)
        assert is_stale is True
        assert "文件岛" in reason

    def test_detect_stale_relationship_change(self):
        detector = MemoryUpdateDetector()
        node = make_node("和加布兽是朋友", node_id=1)
        health = MemoryHealth(memory=node)
        change = {"type": "relationship", "old_value": "", "new_value": ""}
        is_stale, reason = detector.detect_stale(health, change)
        assert is_stale is True

    def test_detect_stale_health_change(self):
        detector = MemoryUpdateDetector()
        node = make_node("HP不足，受伤了", node_id=1)
        health = MemoryHealth(memory=node)
        change = {"type": "health", "old_value": "", "new_value": ""}
        is_stale, reason = detector.detect_stale(health, change)
        assert is_stale is True

    def test_detect_stale_no_match_returns_false(self):
        detector = MemoryUpdateDetector()
        node = make_node("今天天气很好", node_id=1)
        health = MemoryHealth(memory=node)
        change = {"type": "evolution", "old_value": "成长期", "new_value": "成熟期"}
        is_stale, reason = detector.detect_stale(health, change)
        assert is_stale is False
        assert reason == ""

    def test_detect_stale_unknown_type_returns_false(self):
        detector = MemoryUpdateDetector()
        node = make_node("some description", node_id=1)
        health = MemoryHealth(memory=node)
        change = {"type": "unknown_category", "old_value": "x", "new_value": "y"}
        is_stale, reason = detector.detect_stale(health, change)
        assert is_stale is False


# ──────────────────────────────────────────────
# MemoryAutonomy (主入口)
# ──────────────────────────────────────────────

class TestMemoryAutonomy:
    def test_register_delegates_to_forgetting_engine(self):
        autonomy = MemoryAutonomy(agent_name="亚古兽", personality="brave")
        node = make_node("test memory", node_id=1)
        health = autonomy.register(node)
        assert health.strength == 1.0
        assert 1 in autonomy.forgetting_engine.memory_health

    def test_assess_importance_returns_int(self):
        autonomy = MemoryAutonomy(agent_name="亚古兽", personality="brave")
        score = autonomy.assess_importance("进化了!")
        assert score == 8
        assert isinstance(score, int)

    def test_step_returns_diagnostic_report(self):
        autonomy = MemoryAutonomy(agent_name="亚古兽", personality="brave")
        node = make_node("test", node_id=1)
        autonomy.register(node)
        report = autonomy.step(current_tick=42)
        assert report["tick"] == 42
        assert report["agent"] == "亚古兽"
        assert "health" in report
        assert report["stale_detected"] == 0
        assert "rehearsed" in report

    def test_step_detects_stale_on_notify(self):
        autonomy = MemoryAutonomy(agent_name="亚古兽", personality="brave")
        node = make_node("我是成长期", node_id=1)
        autonomy.register(node)
        autonomy.notify_state_change("evolution", "成长期", "成熟期")
        report = autonomy.step(current_tick=1)
        assert report["stale_detected"] >= 1

    def test_notify_state_change_enqueues_pending(self):
        autonomy = MemoryAutonomy(agent_name="亚古兽", personality="brave")
        autonomy.notify_state_change("evolution", "幼年期", "成长期")
        assert len(autonomy.pending_state_changes) == 1
        assert autonomy.pending_state_changes[0]["type"] == "evolution"

    def test_step_clears_pending_state_changes(self):
        autonomy = MemoryAutonomy(agent_name="亚古兽", personality="brave")
        autonomy.notify_state_change("evolution", "a", "b")
        autonomy.step(current_tick=1)
        assert len(autonomy.pending_state_changes) == 0

    def test_step_rehearses_weak_memories(self):
        autonomy = MemoryAutonomy(agent_name="亚古兽", personality="brave")
        # 使用超快速遗忘曲线
        autonomy.forgetting_engine.curve = EbbinghausCurve(S=1)
        node = make_node("important memory about 进化", importance=9, node_id=1)
        health = autonomy.register(node)
        # 模拟 50 秒前创建 → 强度极低
        health.created_at = datetime.utcnow() - timedelta(seconds=50)
        report = autonomy.step(current_tick=1)
        # 应该触发复述或至少尝试
        assert "rehearsed" in report
        assert isinstance(report["rehearsed"], int)

    def test_diagnose_returns_comprehensive_report(self):
        autonomy = MemoryAutonomy(agent_name="加布兽", personality="timid")
        node = make_node("test", node_id=1)
        autonomy.register(node)
        report = autonomy.diagnose()
        assert report["agent"] == "加布兽"
        assert report["personality"] == "timid"
        assert "forgetting_half_life_hours" in report
        assert "total_memories" in report

    def test_post_init_sets_curve_from_personality(self):
        autonomy = MemoryAutonomy(agent_name="test", personality="lazy")
        # lazy factor=1.5, S = 3600/1.5 = 2400
        assert autonomy.forgetting_engine.curve.S == FORGETTING_STRENGTH_DEFAULT / 1.5

    def test_empty_engine_step_does_not_crash(self):
        autonomy = MemoryAutonomy(agent_name="test", personality="neutral")
        report = autonomy.step(current_tick=0)
        assert report["health"]["total"] == 0
        assert report["rehearsed"] == 0

    def test_multiple_notifications_in_one_step(self):
        autonomy = MemoryAutonomy(agent_name="亚古兽", personality="brave")
        # 两条都会引发 stale
        node1 = make_node("我在文件岛", node_id=1)
        node2 = make_node("和加布兽是朋友", node_id=2)
        autonomy.register(node1)
        autonomy.register(node2)
        autonomy.notify_state_change("location", "文件岛", "无限山")
        autonomy.notify_state_change("relationship", "", "")
        report = autonomy.step()
        assert report["stale_detected"] >= 2
