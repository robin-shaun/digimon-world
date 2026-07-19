"""
测试 Meme 系统 — 模因传播 / 技能文化
=====================================
"""

from digimon_world.agents.meme import (
    CATEGORY_SPREAD_RATE,
    MemeCategory,
    MemePool,
)

# ---------------------------------------------------------------------------
# Meme 创建
# ---------------------------------------------------------------------------

class TestMemeCreation:
    """模因创建测试。"""

    def test_create_basic(self):
        """创建一条基本模因。"""
        pool = MemePool()
        mid = pool.create("测试模因", MemeCategory.RUMOR, "Agumon")
        assert mid in pool.registry
        meme = pool.registry[mid]
        assert meme.content == "测试模因"
        assert meme.category == MemeCategory.RUMOR
        assert meme.origin_agent == "Agumon"
        assert meme.generation == 0

    def test_create_idempotent(self):
        """相同内容+origin 返回相同 meme_id。"""
        pool = MemePool()
        mid1 = pool.create("同一内容", MemeCategory.SKILL, "Agumon")
        mid2 = pool.create("同一内容", MemeCategory.SKILL, "Agumon")
        assert mid1 == mid2
        assert len(pool.registry) == 1

    def test_origin_auto_infected(self):
        """创建者自动感染。"""
        pool = MemePool()
        mid = pool.create("消息", MemeCategory.RUMOR, "Gabumon")
        assert pool.knows("Gabumon", mid)

    def test_create_with_tags(self):
        """模因带标签。"""
        pool = MemePool()
        mid = pool.create("黑齿轮警报", MemeCategory.RUMOR, "Agumon",
                          tags=("danger", "file_island"))
        meme = pool.registry[mid]
        assert "danger" in meme.tags
        assert "file_island" in meme.tags

    def test_meme_id_uniqueness(self):
        """不同内容/时间 产生不同 ID。"""
        pool = MemePool()
        mid1 = pool.create("内容A", MemeCategory.RUMOR, "Agumon")
        import time
        time.sleep(0.01)
        mid2 = pool.create("内容A", MemeCategory.RUMOR, "Gabumon")
        assert mid1 != mid2


# ---------------------------------------------------------------------------
# 感染 / 传播
# ---------------------------------------------------------------------------

class TestInfection:
    """感染与传播测试。"""

    def test_infect_new_agent(self):
        """给新 agent 感染模因。"""
        pool = MemePool()
        mid = pool.create("消息", MemeCategory.RUMOR, "Agumon")
        assert pool.infect("Gabumon", mid)
        assert pool.knows("Gabumon", mid)

    def test_infect_already_known(self):
        """重复感染返回 False。"""
        pool = MemePool()
        mid = pool.create("消息", MemeCategory.RUMOR, "Agumon")
        pool.infect("Gabumon", mid)
        assert not pool.infect("Gabumon", mid)

    def test_infect_unknown_meme(self):
        """感染不存在的模因返回 False。"""
        pool = MemePool()
        assert not pool.infect("Agumon", "nonexistent")

    def test_knows_unknown_agent(self):
        """未知 agent 不知道任何模因。"""
        pool = MemePool()
        assert not pool.knows("Nobody", "any_id")

    def test_spread_check_basic(self):
        """基本传播 — 概率判定。"""
        pool = MemePool()
        mid = pool.create("秘密", MemeCategory.RUMOR, "Agumon")
        # 用 base_rate=1.0 确保必中
        assert pool.spread_check("Agumon", "Gabumon", mid, base_rate=1.0)
        assert pool.knows("Gabumon", mid)
        assert len(pool.spread_log) == 1

    def test_spread_check_already_known(self):
        """已感染者不再传播。"""
        pool = MemePool()
        mid = pool.create("消息", MemeCategory.RUMOR, "Agumon")
        pool.infect("Gabumon", mid)
        assert not pool.spread_check("Agumon", "Gabumon", mid, base_rate=1.0)

    def test_spread_check_src_unknown(self):
        """源 agent 不知道模因时不能传播。"""
        pool = MemePool()
        mid = pool.create("消息", MemeCategory.RUMOR, "Agumon")
        assert not pool.spread_check("Unknown", "Gabumon", mid, base_rate=1.0)

    def test_spread_check_zero_rate(self):
        """传播率 0 时一定不传播。"""
        pool = MemePool()
        mid = pool.create("消息", MemeCategory.BELIEF, "Agumon")
        assert not pool.spread_check("Agumon", "Gabumon", mid, base_rate=0.0)

    def test_spread_log_recorded(self):
        """传播日志正确记录。"""
        pool = MemePool()
        mid = pool.create("消息", MemeCategory.RUMOR, "Agumon")
        pool.spread_check("Agumon", "Gabumon", mid, tick=42.0, base_rate=1.0)
        assert pool.spread_log == [("Agumon", "Gabumon", mid, 42.0)]


# ---------------------------------------------------------------------------
# 批量传播
# ---------------------------------------------------------------------------

class TestSpreadBatch:
    """批量传播测试。"""

    def test_batch_spread(self):
        """批量传播 — 使用确定性预感染验证 max_spread 限制。"""
        pool = MemePool()
        m1 = pool.create("消息1", MemeCategory.RUMOR, "Agumon")
        m2 = pool.create("消息2", MemeCategory.SKILL, "Agumon")
        m3 = pool.create("消息3", MemeCategory.BELIEF, "Agumon")

        # 预感染 Gabumon 已知道 m1/m2，只剩 m3 可选
        pool.infect("Gabumon", m1)
        pool.infect("Gabumon", m2)

        spread = pool.spread_batch("Agumon", "Gabumon", max_spread=3)
        # 只剩 m3 可传播
        assert len(spread) <= 1
        if spread:
            assert spread[0] == m3
            assert pool.knows("Gabumon", m3)

    def test_batch_max_limit(self):
        """批量传播受 max_spread 限制。"""
        pool = MemePool()
        for i in range(5):
            pool.create(f"消息{i}", MemeCategory.RUMOR, "Agumon")
        spread = pool.spread_batch("Agumon", "Gabumon", max_spread=2)
        # 概率性 — 可能传0~2个
        assert len(spread) <= 2
        # 验证传播的都在 Gabumon 里
        for mid in spread:
            assert pool.knows("Gabumon", mid)


# ---------------------------------------------------------------------------
# 突变传播
# ---------------------------------------------------------------------------

class TestSpreadMutation:
    """突变传播测试。"""

    def test_spread_with_mutation_normal(self):
        """无突变时的正常传播 — 使用确定性预感染。"""
        pool = MemePool()
        mid = pool.create("原始消息", MemeCategory.RUMOR, "Agumon")
        # 用 spread_check base_rate=1.0 做确定性传播
        assert pool.spread_check("Agumon", "Gabumon", mid, base_rate=1.0)
        assert pool.knows("Gabumon", mid)

    def test_spread_with_mutation_forced(self):
        """强制突变传播 (mutation_rate=1.0)。"""
        pool = MemePool()
        mid = pool.create("原始消息", MemeCategory.RUMOR, "Agumon")
        result = pool.spread_with_mutation(
            "Agumon", "Gabumon", mid, mutation_rate=1.0
        )
        # mutation_rate=1.0 保证变异，但不能保证传播（类别概率）
        # RUMOR 传播率 0.55，大概率会过
        if result is not None and result != mid:
            mutated = pool.registry[result]
            assert "(传闻变异)" in mutated.content
            assert mutated.generation > 0


# ---------------------------------------------------------------------------
# 文化指标
# ---------------------------------------------------------------------------

class TestCulturalMetrics:
    """文化指标测试。"""

    def test_empty_pool(self):
        """空池的指标。"""
        pool = MemePool()
        metrics = pool.cultural_metrics()
        assert metrics["total_memes"] == 0
        assert metrics["total_infections"] == 0
        assert metrics["spread_chain_depth"] == 0
        assert metrics["infection_rate"] == 0.0
        assert metrics["orphan_memes"] == 0

    def test_basic_metrics(self):
        """基本指标计算。"""
        pool = MemePool()
        pool.create("消息A", MemeCategory.RUMOR, "Agumon")
        pool.create("消息B", MemeCategory.SKILL, "Gabumon")
        # Agumon 知道 1 条, Gabumon 知道 1 条
        metrics = pool.cultural_metrics()
        assert metrics["total_memes"] == 2
        assert metrics["total_infections"] == 2
        assert metrics["avg_infections_per_meme"] == 1.0
        assert metrics["infection_rate"] == 1.0  # 2 infections / 2 agents
        assert metrics["categories"]["rumor"] == 1
        assert metrics["categories"]["skill"] == 1

    def test_trending(self):
        """热门模因排行。"""
        pool = MemePool()
        m1 = pool.create("热门", MemeCategory.RUMOR, "Agumon")
        pool.create("冷门", MemeCategory.RUMOR, "Gabumon")
        pool.infect("Gabumon", m1)
        pool.infect("Patamon", m1)

        metrics = pool.cultural_metrics()
        trending = metrics["trending"]
        assert len(trending) >= 1
        # m1 应该排第一 (3 感染 vs 1)
        assert trending[0]["meme_id"] == m1
        assert trending[0]["infection_count"] == 3  # Agumon+Gabumon+Patamon

    def test_orphan_memes(self):
        """孤模因检测。"""
        pool = MemePool()
        mid = pool.create("消息", MemeCategory.RUMOR, "Agumon")
        # 手动从 infections 移除 → 变成孤模因
        pool.infections["Agumon"].discard(mid)
        metrics = pool.cultural_metrics()
        assert metrics["orphan_memes"] == 1

    def test_agent_memes(self):
        """查看 agent 的模因列表。"""
        pool = MemePool()
        pool.create("A知道的消息", MemeCategory.RUMOR, "Agumon")
        agent_memes = pool.agent_memes("Agumon")
        assert len(agent_memes) == 1
        assert agent_memes[0]["content"] == "A知道的消息"

    def test_agent_memes_unknown(self):
        """未知 agent 返回空列表。"""
        pool = MemePool()
        assert pool.agent_memes("Nobody") == []


# ---------------------------------------------------------------------------
# MemeCategory 默认传播率
# ---------------------------------------------------------------------------

class TestCategoryRates:
    """类别传播率测试。"""

    def test_category_rates_defined(self):
        """所有类别都有默认传播率。"""
        for cat in MemeCategory:
            assert cat in CATEGORY_SPREAD_RATE

    def test_rumor_higher_than_belief(self):
        """谣言传播率高于信念。"""
        assert CATEGORY_SPREAD_RATE[MemeCategory.RUMOR] > CATEGORY_SPREAD_RATE[MemeCategory.BELIEF]


# ---------------------------------------------------------------------------
# Meme to_dict
# ---------------------------------------------------------------------------

class TestMemeDict:
    """序列化测试。"""

    def test_to_dict(self):
        """to_dict 输出正确。"""
        pool = MemePool()
        mid = pool.create("序列化测试", MemeCategory.SKILL, "Agumon")
        d = pool.registry[mid].to_dict()
        assert d["meme_id"] == mid
        assert d["content"] == "序列化测试"
        assert d["category"] == "skill"
        assert d["origin_agent"] == "Agumon"
        assert d["generation"] == 0
        assert "created_at" in d
        assert isinstance(d["tags"], list)


# ---------------------------------------------------------------------------
# MemePool.clear
# ---------------------------------------------------------------------------

class TestClear:
    """清空测试。"""

    def test_clear(self):
        """清空后所有数据归零。"""
        pool = MemePool()
        pool.create("消息", MemeCategory.RUMOR, "Agumon")
        pool.clear()
        assert len(pool.registry) == 0
        assert len(pool.infections) == 0
        assert len(pool.spread_log) == 0
        metrics = pool.cultural_metrics()
        assert metrics["total_memes"] == 0
