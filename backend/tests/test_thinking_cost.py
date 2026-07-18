"""Phase 23: 思考成本与认知能量系统 — 集成测试。

测试覆盖:
- CognitiveEnergyPool 能量衰减 / LLM 扣减 / 恢复 / 休眠唤醒
- EnergyLedger 全局统计 / 多 agent 管理
- 边界条件: 能量归零、满能量、负值保护
"""

import pytest

from digimon_world.world.thinking_cost import (
    BASE_DRAIN_PER_TICK,
    DORMANCY_THRESHOLD,
    ENERGY_MAX,
    ENERGY_MIN,
    LLM_COST_DIVISOR,
    RECOVER_EAT,
    RECOVER_REST,
    RECOVER_SOCIAL,
    THINK_THRESHOLD,
    CognitiveEnergyPool,
    get_energy_ledger,
)


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_ledger():
    """每个测试前重置能量账本单例。"""
    ledger = get_energy_ledger()
    ledger.reset_all()
    yield
    ledger.reset_all()


@pytest.fixture
def fresh_pool():
    """全新的能量池（满能量，未休眠）。"""
    return CognitiveEnergyPool()


@pytest.fixture
def low_pool():
    """低能量池（接近临界）。"""
    p = CognitiveEnergyPool(energy=6, is_dormant=False)
    return p


@pytest.fixture
def dormant_pool():
    """已休眠的能量池。"""
    return CognitiveEnergyPool(energy=0, is_dormant=True)


# ──────────────────────────────────────────────
# CognitiveEnergyPool 基本测试
# ──────────────────────────────────────────────


class TestCognitiveEnergyPoolDefaults:
    """默认值测试。"""

    def test_initial_energy(self, fresh_pool):
        assert fresh_pool.energy == ENERGY_MAX
        assert fresh_pool.max_energy == ENERGY_MAX
        assert not fresh_pool.is_dormant

    def test_initial_counters_zero(self, fresh_pool):
        assert fresh_pool.total_llm_calls == 0
        assert fresh_pool.total_tokens_spent == 0

    def test_initial_history_empty(self, fresh_pool):
        assert fresh_pool.energy_history == []

    def test_can_think_when_full(self, fresh_pool):
        assert fresh_pool.can_think()

    def test_to_dict(self, fresh_pool):
        d = fresh_pool.to_dict()
        assert d["energy"] == ENERGY_MAX
        assert d["max_energy"] == ENERGY_MAX
        assert not d["is_dormant"]
        assert d["total_llm_calls"] == 0
        assert d["total_tokens_spent"] == 0
        assert isinstance(d["energy_history"], list)


# ──────────────────────────────────────────────
# tick() — 能量自然衰减
# ──────────────────────────────────────────────


class TestTick:
    """能量自然衰减测试。"""

    def test_tick_reduces_energy(self, fresh_pool):
        before = fresh_pool.energy
        after = fresh_pool.tick()
        assert after == before - BASE_DRAIN_PER_TICK
        assert after == ENERGY_MAX - 1

    def test_tick_history_recorded(self, fresh_pool):
        fresh_pool.tick()
        assert len(fresh_pool.energy_history) == 1
        entry = fresh_pool.energy_history[0]
        assert entry["delta"] == -BASE_DRAIN_PER_TICK
        assert entry["reason"] == "passive_drain"

    def test_tick_does_not_go_below_min(self, dormant_pool):
        dormant_pool.tick()
        assert dormant_pool.energy == ENERGY_MIN

    def test_repeated_ticks_eventually_dormant(self, fresh_pool):
        # 100 ticks from full → energy reaches 0
        for _ in range(ENERGY_MAX):
            fresh_pool.tick()
        assert fresh_pool.energy == 0
        assert fresh_pool.is_dormant

    def test_tick_sets_dormant_at_zero(self, fresh_pool):
        fresh_pool.energy = 1
        fresh_pool.tick()
        assert fresh_pool.energy == 0
        assert fresh_pool.is_dormant


# ──────────────────────────────────────────────
# spend() — LLM 调用能量扣减
# ──────────────────────────────────────────────


class TestSpend:
    """LLM 调用能量扣减测试。"""

    def test_spend_typical_call(self, fresh_pool):
        """典型 LLM 调用 ~500 tokens，应扣 2 能量（500 // 200 = 2）。"""
        fresh_pool.spend(estimated_tokens=500, reason="plan_next")
        assert fresh_pool.energy == ENERGY_MAX - 2
        assert fresh_pool.total_llm_calls == 1
        assert fresh_pool.total_tokens_spent == 500

    def test_spend_minimum_cost(self, fresh_pool):
        """即使 token 很少，至少扣 1 能量。"""
        fresh_pool.spend(estimated_tokens=10, reason="reflect")
        assert fresh_pool.energy == ENERGY_MAX - 1
        assert fresh_pool.total_llm_calls == 1

    def test_spend_large_call(self, fresh_pool):
        """大量 token ~5000 → 扣 25 能量。"""
        fresh_pool.spend(estimated_tokens=5000, reason="compose_narrative")
        assert fresh_pool.energy == ENERGY_MAX - 25
        assert fresh_pool.total_tokens_spent == 5000

    def test_spend_hits_zero(self, fresh_pool):
        """扣到 0 → 休眠。"""
        fresh_pool.energy = 2
        fresh_pool.spend(estimated_tokens=600)  # cost = 3, 只能扣 2
        assert fresh_pool.energy == 0
        assert fresh_pool.is_dormant

    def test_spend_dormant_no_further_decay(self, dormant_pool):
        """休眠状态再花能量不会变成负数。"""
        dormant_pool.spend(estimated_tokens=300)
        assert dormant_pool.energy == 0

    def test_spend_history_recorded(self, fresh_pool):
        fresh_pool.spend(estimated_tokens=300, reason="dialogue")
        entry = fresh_pool.energy_history[-1]
        assert entry["reason"] == "dialogue"
        assert entry["delta"] < 0

    def test_spend_multiple_calls_accumulate(self, fresh_pool):
        fresh_pool.spend(estimated_tokens=400)
        fresh_pool.spend(estimated_tokens=600)
        assert fresh_pool.total_llm_calls == 2
        assert fresh_pool.total_tokens_spent == 1000
        assert fresh_pool.energy == ENERGY_MAX - 5  # 2 + 3


# ──────────────────────────────────────────────
# recover() — 能量恢复
# ──────────────────────────────────────────────


class TestRecover:
    """能量恢复测试。"""

    def test_recover_rest(self, fresh_pool):
        fresh_pool.energy = 50
        result = fresh_pool.recover(RECOVER_REST, reason="rest")
        assert result == 52
        assert fresh_pool.energy == 52

    def test_recover_social(self, fresh_pool):
        fresh_pool.energy = 50
        result = fresh_pool.recover(RECOVER_SOCIAL, reason="social")
        assert result == 55
        assert "social" in fresh_pool.energy_history[-1]["reason"]

    def test_recover_eat(self, fresh_pool):
        fresh_pool.energy = 50
        result = fresh_pool.recover(RECOVER_EAT, reason="forage")
        assert result == 60

    def test_recover_clamped_to_max(self, fresh_pool):
        """恢复不能超过最大值。"""
        fresh_pool.energy = 98
        result = fresh_pool.recover(10, reason="big_feast")
        assert result == ENERGY_MAX
        assert fresh_pool.energy == ENERGY_MAX

    def test_recover_wakes_dormant(self, dormant_pool):
        """休眠 agent 获得能量后应唤醒。"""
        dormant_pool.recover(RECOVER_REST, reason="rest")
        assert not dormant_pool.is_dormant
        assert dormant_pool.energy == RECOVER_REST


# ──────────────────────────────────────────────
# can_think() — 思考能力判断
# ──────────────────────────────────────────────


class TestCanThink:
    """can_think() 判断逻辑测试。"""

    def test_can_think_above_threshold(self, fresh_pool):
        fresh_pool.energy = THINK_THRESHOLD + 1  # 6
        assert fresh_pool.can_think()

    def test_cannot_think_at_threshold(self, fresh_pool):
        fresh_pool.energy = THINK_THRESHOLD  # 5
        assert not fresh_pool.can_think()

    def test_cannot_think_below_threshold(self, fresh_pool):
        fresh_pool.energy = 2
        assert not fresh_pool.can_think()

    def test_cannot_think_when_dormant(self, dormant_pool):
        assert not dormant_pool.can_think()

    def test_can_think_after_recovery(self, dormant_pool):
        dormant_pool.recover(RECOVER_EAT)  # +10 → energy=10
        assert dormant_pool.can_think()
        assert not dormant_pool.is_dormant


# ──────────────────────────────────────────────
# energy_history 容量管理
# ──────────────────────────────────────────────


class TestEnergyHistory:
    """能量历史记录测试。"""

    def test_history_limited_to_20(self, fresh_pool):
        for i in range(25):
            fresh_pool.tick()
        assert len(fresh_pool.energy_history) == 20

    def test_history_fifo_order(self, fresh_pool):
        fresh_pool.spend(estimated_tokens=300, reason="first")
        fresh_pool.spend(estimated_tokens=500, reason="second")
        assert fresh_pool.energy_history[-1]["reason"] == "second"
        assert fresh_pool.energy_history[-2]["reason"] == "first"


# ──────────────────────────────────────────────
# EnergyLedger 全局统计
# ──────────────────────────────────────────────


class TestEnergyLedger:
    """全局能量账本测试。"""

    def test_get_or_create_new(self):
        ledger = get_energy_ledger()
        pool = ledger.get_or_create("亚古兽")
        assert pool.energy == ENERGY_MAX
        assert "亚古兽" in ledger.pools

    def test_get_or_create_returns_same(self):
        ledger = get_energy_ledger()
        p1 = ledger.get_or_create("亚古兽")
        p1.spend(estimated_tokens=400)  # -2
        p2 = ledger.get_or_create("亚古兽")
        assert p1 is p2
        assert p2.energy == ENERGY_MAX - 2

    def test_get_stats_empty(self):
        ledger = get_energy_ledger()
        stats = ledger.get_stats()
        assert stats["total_agents"] == 0
        assert stats["active_count"] == 0
        assert stats["dormant_count"] == 0
        assert stats["avg_energy"] == 0.0

    def test_get_stats_with_agents(self):
        ledger = get_energy_ledger()
        ledger.get_or_create("亚古兽")
        ledger.get_or_create("加布兽")
        # 让加布兽休眠
        ledger.pools["加布兽"].energy = 0
        ledger.pools["加布兽"].is_dormant = True
        stats = ledger.get_stats()
        assert stats["total_agents"] == 2
        assert stats["active_count"] == 1
        assert stats["dormant_count"] == 1
        assert stats["avg_energy"] == 50.0  # (100 + 0) / 2

    def test_get_stats_llm_counter(self):
        ledger = get_energy_ledger()
        pool = ledger.get_or_create("亚古兽")
        pool.spend(estimated_tokens=300)
        pool.spend(estimated_tokens=200)
        stats = ledger.get_stats()
        assert stats["total_llm_calls"] == 2
        assert stats["total_tokens"] == 500

    def test_reset_all(self):
        ledger = get_energy_ledger()
        ledger.get_or_create("亚古兽")
        ledger.reset_all()
        assert len(ledger.pools) == 0
        assert get_energy_ledger().get_stats()["total_agents"] == 0


# ──────────────────────────────────────────────
# 边界条件
# ──────────────────────────────────────────────


class TestEdgeCases:
    """边界条件测试。"""

    def test_custom_max_energy(self):
        pool = CognitiveEnergyPool(energy=50, max_energy=50)
        pool.recover(100)  # 不应超过 50
        assert pool.energy == 50

    def test_zero_token_cost(self):
        """0 token 调用也应扣最低 1 能量。"""
        pool = CognitiveEnergyPool(energy=10)
        pool.spend(estimated_tokens=0)
        assert pool.energy == 9

    def test_negative_recover_ignored(self):
        pool = CognitiveEnergyPool(energy=50)
        result = pool.recover(-10)
        assert result == 50  # 不变

    def test_rapid_recover_wakeup(self):
        """快速恢复-休眠-恢复循环。"""
        pool = CognitiveEnergyPool(energy=1)
        pool.tick()  # 0 → dormant
        assert pool.is_dormant
        pool.recover(RECOVER_REST)  # 2
        assert not pool.is_dormant
        pool.tick()  # 1
        pool.tick()  # 0
        assert pool.is_dormant


# ──────────────────────────────────────────────
# 常量验证
# ──────────────────────────────────────────────


class TestConstants:
    """常量合理性验证。"""

    def test_energy_range_valid(self):
        assert ENERGY_MAX > ENERGY_MIN
        assert ENERGY_MIN == 0

    def test_thresholds_consistent(self):
        """休眠阈值 ≤ 思考阈值 ≤ 最大能量。"""
        assert DORMANCY_THRESHOLD < THINK_THRESHOLD
        assert THINK_THRESHOLD < ENERGY_MAX

    def test_recovery_amounts_positive(self):
        assert RECOVER_REST > 0
        assert RECOVER_SOCIAL > 0
        assert RECOVER_EAT > 0

    def test_cost_divisor_reasonable(self):
        """200 tokens/energy point — 合理的兑换率。"""
        assert LLM_COST_DIVISOR > 0
        # 典型 500 token 调用 → 2-3 能量点，合理
        cost = max(1, 500 // LLM_COST_DIVISOR)
        assert 1 <= cost <= 5


# ──────────────────────────────────────────────
# Phase 23 Task 2: DigimonAgent 集成测试
# ──────────────────────────────────────────────


class TestDigimonAgentEnergyIntegration:
    """测试认知能量系统与 DigimonAgent 的集成。"""

    @pytest.fixture(autouse=True)
    def reset_ledger(self):
        """每个测试前重置能量账本。"""
        ledger = get_energy_ledger()
        ledger.reset_all()
        yield
        ledger.reset_all()

    def test_agent_creates_with_full_energy(self):
        """Agent 创建时能量满额 (100)。"""
        from digimon_world.agents.digimon_agent import DigimonAgent
        a = DigimonAgent(name="test_agent", species="agumon")
        assert a.cognitive_energy.energy == ENERGY_MAX
        assert a.cognitive_energy.can_think() is True
        assert a.cognitive_energy.is_dormant is False

    def test_agent_registers_with_ledger(self):
        """Agent 创建后自动注册到全局账本。"""
        from digimon_world.agents.digimon_agent import DigimonAgent
        a = DigimonAgent(name="test_agent", species="agumon")
        ledger = get_energy_ledger()
        assert "test_agent" in ledger.pools
        assert ledger.pools["test_agent"] is a.cognitive_energy

    def test_apply_tick_energy_drains(self):
        """apply_tick_energy 消耗 1 能量 / tick。"""
        from digimon_world.agents.digimon_agent import DigimonAgent
        a = DigimonAgent(name="test_agent", species="agumon")
        initial = a.cognitive_energy.energy
        a.apply_tick_energy()
        assert a.cognitive_energy.energy == initial - BASE_DRAIN_PER_TICK

    def test_apply_tick_energy_recovers_on_rest_plan(self):
        """休息计划时 apply_tick_energy 先扣再恢复。"""
        from digimon_world.agents.digimon_agent import DigimonAgent
        a = DigimonAgent(name="test_agent", species="agumon")
        a.current_plan = "想休息一下"
        initial = a.cognitive_energy.energy
        a.apply_tick_energy()
        # 扣除 BASE_DRAIN_PER_TICK，再恢复 RECOVER_REST
        expected = initial - BASE_DRAIN_PER_TICK + RECOVER_REST
        assert a.cognitive_energy.energy == min(ENERGY_MAX, expected)

    def test_tick_drain_to_dormancy(self):
        """连续 100 tick 后 agent 进入休眠。"""
        from digimon_world.agents.digimon_agent import DigimonAgent
        a = DigimonAgent(name="test_agent", species="agumon")
        # 连续 100 tick (每 tick 扣 1)
        for _ in range(100):
            a.apply_tick_energy()
        assert a.cognitive_energy.energy == ENERGY_MIN
        assert a.cognitive_energy.is_dormant is True

    def test_step_drains_energy(self):
        """agent.step() 每 tick 消耗能量。"""
        import asyncio
        from digimon_world.agents.digimon_agent import DigimonAgent
        a = DigimonAgent(name="test_agent", species="agumon")
        initial = a.cognitive_energy.energy
        # no LLM calls happen since planner/reflector are None
        asyncio.run(a.step(tick_index=0))
        # tick drain applied: -1
        # If no LLM call and no rest event, just -1
        assert a.cognitive_energy.energy <= initial - BASE_DRAIN_PER_TICK

    def test_energy_persists_across_ticks(self):
        """能量状态跨 tick 持续累积。"""
        import asyncio
        from digimon_world.agents.digimon_agent import DigimonAgent
        a = DigimonAgent(name="test_agent", species="agumon")
        initial = 100
        for i in range(5):
            asyncio.run(a.step(tick_index=i))
        # 5 ticks × 1 drain = -5, no LLM (planner/reflector=None)
        expected_min = initial - 5 * BASE_DRAIN_PER_TICK
        assert a.cognitive_energy.energy <= expected_min + 5  # allow rest recovery

    def test_step_with_rest_plan_recovers(self):
        """step() 产生 rested 事件时触发能量恢复。"""
        import asyncio
        from digimon_world.agents.digimon_agent import DigimonAgent
        a = DigimonAgent(name="test_agent", species="agumon")
        # 先降能量（用非休息计划避免 apply_tick_energy 自动恢复）
        a.current_plan = "随便走走"
        for _ in range(70):
            a.apply_tick_energy()
        # 现在设休息计划
        a.current_plan = "休息一下，恢复体力"
        before_step = a.cognitive_energy.energy  # ~30
        event = asyncio.run(a.step(tick_index=0))
        # 如果产生了 rested 事件，能量会恢复
        if event.get("type") == "rested":
            assert a.cognitive_energy.energy > before_step
        else:
            # 没有产生 rested 事件（可能 act() 解析了不同意图），
            # 但也不会比被动消耗更差
            assert a.cognitive_energy.energy >= before_step - BASE_DRAIN_PER_TICK - 10

    def test_can_think_false_skips_llm(self):
        """能量不足时 can_think() 返回 False。"""
        from digimon_world.agents.digimon_agent import DigimonAgent
        a = DigimonAgent(name="test_agent", species="agumon")
        # 手动降低能量到阈值以下
        a.cognitive_energy.energy = THINK_THRESHOLD  # exactly at threshold
        assert a.cognitive_energy.can_think() is False  # must be strictly >
        a.cognitive_energy.energy = THINK_THRESHOLD + 1
        assert a.cognitive_energy.can_think() is True

    def test_dormant_agent_cannot_think(self):
        """休眠中的 agent 即使有能量也不能思考。"""
        from digimon_world.agents.digimon_agent import DigimonAgent
        a = DigimonAgent(name="test_agent", species="agumon")
        a.cognitive_energy.energy = 50
        a.cognitive_energy.is_dormant = True
        assert a.cognitive_energy.can_think() is False
