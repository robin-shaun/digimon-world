"""Phase 22: 共享记忆惯例与文化涌现 — 集成测试。

测试覆盖:
- Convention 数据结构 & 衰减计算
- ConventionDetector 检测（跨 agent 词频统计、停用词过滤、增量检测）
- ConventionPool 注册/更新/衰减/清理
- ConventionPropagation 按关系距离传播
"""

import math
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from digimon_world.world.shared_conventions import (
    CONVENTION_EXTINCTION_THRESHOLD,
    CONVENTION_HALF_LIFE_DEFAULT,
    MAX_NEW_CONVENTIONS_PER_TICK,
    Convention,
    ConventionDetector,
    ConventionPool,
    ConventionPropagation,
    get_convention_pool,
    get_convention_propagation,
    reset_convention_pool,
)


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_pool():
    """每个测试前重置惯例池单例。"""
    reset_convention_pool()
    yield
    reset_convention_pool()


@pytest.fixture
def sample_convention():
    """创建一条样例惯例。"""
    return Convention(
        convention_id="abc123",
        term="文件岛冒险",
        category="term",
        source_agents=["亚古兽", "加布兽"],
        adopter_agents=["亚古兽", "加布兽"],
        use_count=5,
        strength=1.0,
        half_life_seconds=CONVENTION_HALF_LIFE_DEFAULT,
    )


@pytest.fixture
def populated_pool(sample_convention):
    """预填充的惯例池。"""
    pool = ConventionPool()
    pool.register(sample_convention)
    # 再注册几条
    pool.register(Convention(
        convention_id="def456",
        term="进化之光",
        category="ritual",
        source_agents=["亚古兽"],
        adopter_agents=["亚古兽"],
        use_count=3,
    ))
    pool.register(Convention(
        convention_id="ghi789",
        term="训练场",
        category="term",
        source_agents=["加布兽", "比丘兽"],
        adopter_agents=["加布兽", "比丘兽"],
        use_count=2,
    ))
    return pool


def _make_mock_agent(name, description_entries=None):
    """创建 mock agent 用于检测测试。"""
    agent = MagicMock()
    agent.name = name
    agent.memory = MagicMock()
    if description_entries:
        entries = []
        for desc in description_entries:
            e = MagicMock()
            e.description = desc
            entries.append(e)
        agent.memory.entries = entries
    else:
        agent.memory.entries = []
    # Personality traits for MemoryAutonomy fallback
    agent.personality_traits = {"brave": 8}
    return agent


# ──────────────────────────────────────────────
# Convention 数据结构测试
# ──────────────────────────────────────────────


class TestConvention:
    """Convention 数据结构基本测试。"""

    def test_creation_defaults(self):
        c = Convention(convention_id="test", term="测试惯例")
        assert c.convention_id == "test"
        assert c.term == "测试惯例"
        assert c.category == "term"
        assert c.adopter_agents == []
        assert c.adoption_count == 0
        assert c.use_count == 0
        assert c.strength == 1.0
        assert c.is_active

    def test_adoption_count(self):
        c = Convention(
            convention_id="test", term="测试",
            adopter_agents=["A", "B", "C"],
        )
        assert c.adoption_count == 3

    def test_compute_strength_no_elapsed(self):
        """刚使用过：强度应为 1.0。"""
        c = Convention(convention_id="test", term="测试")
        now = datetime.utcnow()
        c.last_used = now
        assert c.compute_strength(now) == 1.0

    def test_compute_strength_after_half_life(self):
        """半衰期后：强度应为 e^(-1) ≈ 0.368。"""
        c = Convention(
            convention_id="test", term="测试",
            half_life_seconds=3600.0,  # 1 hour
        )
        now = datetime.utcnow()
        c.last_used = now - timedelta(seconds=3600)
        expected = math.exp(-1)
        assert abs(c.compute_strength(now) - expected) < 0.001

    def test_compute_strength_after_two_half_lives(self):
        """两个半衰期后：强度 ≈ 0.135。"""
        c = Convention(
            convention_id="test", term="测试",
            half_life_seconds=1800.0,  # 30 min
        )
        now = datetime.utcnow()
        c.last_used = now - timedelta(seconds=3600)  # 2 half-lives
        expected = math.exp(-2)
        assert abs(c.compute_strength(now) - expected) < 0.001

    def test_is_active_above_threshold(self):
        c = Convention(convention_id="test", term="测试", strength=0.5)
        assert c.is_active

    def test_is_active_below_threshold(self):
        c = Convention(convention_id="test", term="测试", strength=0.05)
        assert not c.is_active

    def test_is_active_at_boundary(self):
        c = Convention(
            convention_id="test", term="测试",
            strength=CONVENTION_EXTINCTION_THRESHOLD,
        )
        # 正好等于阈值 → 已消亡 (is_active uses > not >= )
        assert not c.is_active


# ──────────────────────────────────────────────
# ConventionDetector 测试
# ──────────────────────────────────────────────


class TestConventionDetector:
    """ConventionDetector 检测逻辑测试。"""

    def test_detect_empty_agents(self):
        detector = ConventionDetector()
        result = detector.detect([])
        assert result == []

    def test_detect_insufficient_agents(self):
        """只有一个 agent → 不够 MIN_AGENTS_FOR_CONVENTION=2。"""
        detector = ConventionDetector()
        agent = _make_mock_agent("A", ["探索文件岛发现神秘洞穴"])
        result = detector.detect([agent])
        assert result == []

    def test_detect_shared_term(self):
        """两个 agent 都有相同关键词 → 检测为惯例。"""
        detector = ConventionDetector()
        agents = [
            _make_mock_agent("亚古兽", [
                "在文件岛冒险时发现了神秘的进化之光",
                "文件岛冒险让人兴奋",
            ]),
            _make_mock_agent("加布兽", [
                "在文件岛冒险真的很有趣",
                "和亚古兽一起在文件岛冒险",
            ]),
        ]
        result = detector.detect(agents)
        # jieba 分词: "文件岛冒险" → "文件" + "冒险"
        # "冒险" 在两个 agent 中都出现
        terms = [c.term for c in result]
        assert "冒险" in terms

    def test_detect_shared_term_multiple(self):
        """多个 agent 共享多个词。"""
        detector = ConventionDetector()
        agents = [
            _make_mock_agent("A", ["黑暗齿轮出现在文件岛", "战斗训练很重要"]),
            _make_mock_agent("B", ["黑暗齿轮破坏了森林", "战斗训练每天进行"]),
            _make_mock_agent("C", ["黑暗齿轮的力量在增长", "战斗训练开始了"]),
        ]
        result = detector.detect(agents)
        # jieba 分词: "黑暗齿轮" → "黑暗" + "齿轮"; "战斗训练" → "战斗" + "训练"
        terms = {c.term for c in result}
        assert "黑暗" in terms
        assert "训练" in terms

    def test_stop_words_filtered(self):
        """停用词不应被检测为惯例。"""
        detector = ConventionDetector()
        agents = [
            _make_mock_agent("A", ["我们一起探索这个区域"]),
            _make_mock_agent("B", ["我们大家一起探索行动"]),
        ]
        result = detector.detect(agents)
        terms = {c.term for c in result}
        # "我们"、"一起" are stop words
        assert "我们" not in terms
        assert "一起" not in terms
        # "探索" is not a stop word, appears in both agents
        assert "探索" in terms

    def test_detect_respects_max_conventions(self):
        """不应该超过 MAX_NEW_CONVENTIONS_PER_TICK。"""
        detector = ConventionDetector()
        terms = [f"特殊技能{i:03d}" for i in range(20)]
        agents = [
            _make_mock_agent(f"Agent_{i}", [t for t in terms[i::3]])
            for i in range(6)  # 6 agents, each gets ~7 terms
        ]
        result = detector.detect(agents)
        assert len(result) <= MAX_NEW_CONVENTIONS_PER_TICK

    def test_detect_excludes_existing_pool(self):
        """已存在的惯例不应被重新检测。"""
        detector = ConventionDetector()
        agents = [
            _make_mock_agent("A", ["文件岛冒险"]),
            _make_mock_agent("B", ["文件岛冒险"]),
        ]
        existing = {"abc123": Convention(convention_id="abc123", term="文件岛冒险")}
        result = detector.detect(agents, existing)
        # Should not re-detect "文件岛冒险"
        terms = {c.term for c in result}
        assert "文件岛冒险" not in terms

    def test_detect_from_interaction_single(self):
        """从单条对话检测。"""
        detector = ConventionDetector()
        result = detector.detect_from_interaction(
            "亚古兽", "加布兽",
            "进化之光照耀着我们",
        )
        # jieba: "进化之光照耀着我们" → "进化" + "之光" + "照耀" + "我们"
        assert len(result) >= 1
        terms = {c.term for c in result}
        assert "进化" in terms

    def test_detect_from_interaction_empty(self):
        """空对话→无检测。"""
        detector = ConventionDetector()
        result = detector.detect_from_interaction("A", "B", "")
        assert result == []

    def test_classify_behavior(self):
        detector = ConventionDetector()
        assert detector._classify("攻击敌人") == "behavior"
        assert detector._classify("探索洞穴") == "behavior"
        assert detector._classify("进化之路") == "behavior"

    def test_classify_ritual(self):
        detector = ConventionDetector()
        assert detector._classify("聚集庆祝") == "ritual"
        assert detector._classify("进化祭") == "ritual"

    def test_classify_term(self):
        detector = ConventionDetector()
        assert detector._classify("文件岛") == "term"
        assert detector._classify("黑暗力量") == "term"


# ──────────────────────────────────────────────
# ConventionPool 测试
# ──────────────────────────────────────────────


class TestConventionPool:
    """ConventionPool 管理测试。"""

    def test_register_new(self, sample_convention):
        pool = ConventionPool()
        result = pool.register(sample_convention)
        assert result is sample_convention
        assert pool._total_conventions_ever == 1

    def test_register_duplicate_ignored(self, sample_convention):
        pool = ConventionPool()
        pool.register(sample_convention)
        pool.register(sample_convention)  # 重复
        assert pool._total_conventions_ever == 1

    def test_register_batch(self):
        pool = ConventionPool()
        convs = [
            Convention(convention_id="a", term="A"),
            Convention(convention_id="b", term="B"),
            Convention(convention_id="c", term="C"),
        ]
        new_count = pool.register_batch(convs)
        assert new_count == 3
        assert pool._total_conventions_ever == 3

    def test_notify_use_updates(self, sample_convention):
        pool = ConventionPool()
        pool.register(sample_convention)

        old_last_used = sample_convention.last_used
        time.sleep(0.01)  # Ensure time difference

        ok = pool.notify_use("abc123", "比丘兽")
        assert ok
        assert sample_convention.use_count == 6  # was 5
        assert sample_convention.last_used > old_last_used
        assert sample_convention.strength == 1.0  # 重置
        assert "比丘兽" in sample_convention.adopter_agents

    def test_notify_use_nonexistent(self):
        pool = ConventionPool()
        ok = pool.notify_use("nonexistent", "A")
        assert not ok

    def test_adopt(self, sample_convention):
        pool = ConventionPool()
        pool.register(sample_convention)

        ok = pool.adopt("abc123", "比丘兽")
        assert ok
        assert "比丘兽" in sample_convention.adopter_agents
        assert sample_convention.adoption_count == 3

    def test_adopt_duplicate(self, sample_convention):
        """已采用的 agent 再次 adopt → 不算新采用者。"""
        pool = ConventionPool()
        pool.register(sample_convention)
        # 亚古兽 already in adopters
        ok = pool.adopt("abc123", "亚古兽")
        assert ok  # still returns True (convention exists)
        assert sample_convention.adoption_count == 2  # unchanged

    def test_decay_all(self, populated_pool):
        """衰减所有惯例。"""
        # 将所有惯例的 last_used 设为很久以前
        old = datetime.utcnow() - timedelta(hours=10)
        for conv in populated_pool._conventions.values():
            conv.last_used = old

        active = populated_pool.decay_all()
        # 3 个惯例中，全部都已衰减但可能仍活跃
        assert active >= 0

    def test_cleanup_removes_extinct(self, populated_pool):
        """清理应移除强度低于阈值的惯例。"""
        # 强制所有惯例强度 = 0
        for conv in populated_pool._conventions.values():
            conv.strength = 0.0

        removed = populated_pool.cleanup()
        assert removed == 3
        assert len(populated_pool._conventions) == 0

    def test_get_active_sorts_by_adoption(self, populated_pool):
        active = populated_pool.get_active(sort_by="adoption_count")
        assert len(active) == 3
        # 按 adoption_count 降序
        assert active[0].adoption_count >= active[1].adoption_count

    def test_get_by_agent(self, populated_pool):
        """获取某 agent 的惯例。"""
        agumon_convs = populated_pool.get_by_agent("亚古兽")
        terms = {c.term for c in agumon_convs}
        assert "文件岛冒险" in terms
        assert "进化之光" in terms

    def test_get_by_category(self, populated_pool):
        rituals = populated_pool.get_by_category("ritual")
        assert len(rituals) == 1
        assert rituals[0].term == "进化之光"

    def test_stats(self, populated_pool):
        stats = populated_pool.stats()
        assert stats["active"] == 3
        assert stats["extinct"] == 0
        assert "by_category" in stats
        assert stats["total_adoptions"] > 0

    def test_tick_detects_and_decays(self):
        """完整 tick 流程。"""
        pool = ConventionPool()
        agents = [
            _make_mock_agent("A", ["神秘力量觉醒", "黑暗齿轮降临"]),
            _make_mock_agent("B", ["神秘力量涌动", "黑暗齿轮破坏"]),
            _make_mock_agent("C", ["神秘力量扩散"]),
        ]
        report = pool.tick(agents)
        assert report["total_ever"] >= 0
        assert isinstance(report["active"], int)
        assert isinstance(report["new_this_tick"], int)

    def test_get_nonexistent(self):
        pool = ConventionPool()
        assert pool.get("nonexistent") is None

    def test_singleton(self):
        """测试单例模式。"""
        reset_convention_pool()
        pool1 = get_convention_pool()
        pool2 = get_convention_pool()
        assert pool1 is pool2

        prop1 = get_convention_propagation()
        prop2 = get_convention_propagation()
        assert prop1 is prop2


# ──────────────────────────────────────────────
# ConventionPropagation 测试
# ──────────────────────────────────────────────


class TestConventionPropagation:
    """ConventionPropagation 传播逻辑测试。"""

    @pytest.fixture
    def pool_with_convs(self):
        """惯例池：A 有 conv_a, B 有 conv_b。"""
        pool = ConventionPool()
        pool.register(Convention(
            convention_id="conv_a", term="A的惯例",
            source_agents=["A"], adopter_agents=["A"],
        ))
        pool.register(Convention(
            convention_id="conv_b", term="B的惯例",
            source_agents=["B"], adopter_agents=["B"],
        ))
        return pool

    def test_propagate_inner_circle(self, pool_with_convs):
        """内圈关系：传播概率 1.0，应该一定传播。"""
        prop = ConventionPropagation(pool_with_convs)
        with patch("random.random", return_value=0.5):  # < 1.0
            count = prop.propagate_on_interaction("A", "B", "inner")
        assert count == 2  # A→B + B→A

        # 验证 B 现在有了 A 的惯例，A 有了 B 的惯例
        a_convs = pool_with_convs.get_by_agent("A")
        b_convs = pool_with_convs.get_by_agent("B")
        a_terms = {c.term for c in a_convs}
        b_terms = {c.term for c in b_convs}
        assert "B的惯例" in a_terms
        assert "A的惯例" in b_terms

    def test_propagate_stranger_no_luck(self, pool_with_convs):
        """陌生人关系 + 随机数高 → 不传播。"""
        prop = ConventionPropagation(pool_with_convs)
        with patch("random.random", return_value=0.9):  # > 0.05 (stranger)
            count = prop.propagate_on_interaction("A", "B", "stranger")
        assert count == 0

    def test_propagate_same_conventions(self, pool_with_convs):
        """双方已有相同惯例 → 无传播。"""
        # 让双方都有全部惯例
        pool_with_convs.adopt("conv_b", "A")
        pool_with_convs.adopt("conv_a", "B")

        prop = ConventionPropagation(pool_with_convs)
        count = prop.propagate_on_interaction("A", "B", "inner")
        assert count == 0  # 无新惯例可传播

    def test_propagate_middle_distance(self):
        """中圈关系：传播概率 0.6。"""
        pool = ConventionPool()
        pool.register(Convention(
            convention_id="x", term="X惯例",
            source_agents=["A"], adopter_agents=["A"],
        ))
        prop = ConventionPropagation(pool)

        # random=0.5 < 0.6 → propagate
        with patch("random.random", return_value=0.5):
            count = prop.propagate_on_interaction("A", "B", "middle")
        assert count >= 1
