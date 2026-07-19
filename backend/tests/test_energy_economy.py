"""Phase 24: 能量经济系统 — 集成测试。

测试覆盖:
- EnergyTransfer 数据结构与工厂方法
- ReciprocalAltruism 债务记录、评分、排名、衰败
- EnergyEconomy 转移提议、机会扫描、统计、步进
- 与 CognitiveEnergyPool 的集成（mock 验证）
"""

from unittest.mock import MagicMock

import pytest

from digimon_world.economy.energy_economy import (
    AWAKEN_HELPER_COST,
    AWAKEN_RESTORE_AMOUNT,
    DEBT_DECAY_INTERVAL,
    DESPERATION_ENERGY_THRESHOLD,
    MAX_DEBT,
    RECIPROCITY_DEBT_THRESHOLD,
    EnergyEconomy,
    EnergyTransfer,
    ReciprocalAltruism,
)

# ──────────────────────────────────────────────
# Mock Helpers
# ──────────────────────────────────────────────


def make_mock_agent(name, energy=50.0, is_dormant=False, max_energy=100.0):
    """Create a mock DigimonAgent with a cognitive_energy pool."""
    agent = MagicMock()
    agent.name = name
    agent.cognitive_energy = MagicMock()
    agent.cognitive_energy.energy = energy
    agent.cognitive_energy.max_energy = max_energy
    agent.cognitive_energy.is_dormant = is_dormant
    return agent


def make_mock_world(agents_dict):
    """Create a mock WorldState with given agents."""
    world = MagicMock()
    world.agents = agents_dict
    return world


def make_economy(agents_dict, altruism=None):
    """Create an EnergyEconomy with a mock world and the given agents."""
    world = make_mock_world(agents_dict)
    return EnergyEconomy(world, altruism=altruism)


# ──────────────────────────────────────────────
# EnergyTransfer Tests
# ──────────────────────────────────────────────


class TestEnergyTransfer:
    """Tests for the EnergyTransfer frozen dataclass."""

    def test_create_transfer_verify_all_fields(self):
        """Create transfer directly and verify all fields are set correctly."""
        transfer = EnergyTransfer(
            transfer_id="test-id-001",
            from_agent="agumon",
            to_agent="gabumon",
            amount=25.0,
            transfer_type="donation",
            reason="Helping a friend",
            tick=42,
            timestamp=1234567890.0,
        )
        assert transfer.transfer_id == "test-id-001"
        assert transfer.from_agent == "agumon"
        assert transfer.to_agent == "gabumon"
        assert transfer.amount == 25.0
        assert transfer.transfer_type == "donation"
        assert transfer.reason == "Helping a friend"
        assert transfer.tick == 42
        assert transfer.timestamp == 1234567890.0

    def test_to_dict_serialization(self):
        """to_dict() returns all fields correctly."""
        transfer = EnergyTransfer(
            transfer_id="test-id-002",
            from_agent="patamon",
            to_agent="tentomon",
            amount=10.0,
            transfer_type="trade",
            reason="Trading energy for food",
            tick=100,
            timestamp=9999999999.0,
        )
        d = transfer.to_dict()
        assert d["transfer_id"] == "test-id-002"
        assert d["from_agent"] == "patamon"
        assert d["to_agent"] == "tentomon"
        assert d["amount"] == 10.0
        assert d["transfer_type"] == "trade"
        assert d["reason"] == "Trading energy for food"
        assert d["tick"] == 100
        assert d["timestamp"] == 9999999999.0

    def test_create_factory_generates_uuid(self):
        """create() factory generates a UUID v4 transfer_id and current timestamp."""
        t1 = EnergyTransfer.create("agumon", "gabumon", 15.0, "donation", "test", 1)
        t2 = EnergyTransfer.create("agumon", "gabumon", 15.0, "donation", "test", 1)

        # UUIDs should be different
        assert t1.transfer_id != t2.transfer_id
        # Should look like UUIDs
        assert len(t1.transfer_id) == 36
        assert t1.transfer_id.count("-") == 4
        # Timestamps should be reasonable
        assert t1.timestamp > 0
        assert t2.timestamp > 0

    def test_frozen_dataclass_cannot_modify(self):
        """EnergyTransfer is frozen — modifying fields raises FrozenInstanceError."""
        transfer = EnergyTransfer.create("agumon", "gabumon", 5.0, "donation", "test", 1)

        with pytest.raises(Exception):  # noqa: B017  # dataclasses.FrozenInstanceError or similar
            transfer.amount = 999.0

    def test_edge_cases_zero_amount_and_empty_reason(self):
        """Edge cases: zero amount and empty reason are accepted at the dataclass level."""
        transfer = EnergyTransfer(
            transfer_id="edge-001",
            from_agent="a",
            to_agent="b",
            amount=0.0,
            transfer_type="donation",
            reason="",
            tick=0,
            timestamp=0.0,
        )
        assert transfer.amount == 0.0
        assert transfer.reason == ""
        d = transfer.to_dict()
        assert d["amount"] == 0.0
        assert d["reason"] == ""


# ──────────────────────────────────────────────
# ReciprocalAltruism Tests
# ──────────────────────────────────────────────


class TestReciprocalAltruism:
    """Tests for the ReciprocalAltruism debt tracking system."""

    @pytest.fixture(autouse=True)
    def setup_altruism(self):
        """Fresh ReciprocalAltruism instance for each test."""
        self.altruism = ReciprocalAltruism()

    # ---- record_help ----

    def test_record_help_creates_debt(self):
        """record_help creates a debt from recipient to helper."""
        debt = self.altruism.record_help("agumon", "gabumon", 20.0, 1)
        assert debt == 20.0
        assert self.altruism.get_debt("gabumon", "agumon") == 20.0

    def test_record_help_self_help_ignored(self):
        """Self-help returns 0.0 and creates no debt."""
        debt = self.altruism.record_help("agumon", "agumon", 50.0, 1)
        assert debt == 0.0
        assert self.altruism.get_debt("agumon", "agumon") == 0.0

    def test_record_help_accumulates_debt(self):
        """Multiple helps accumulate debt."""
        self.altruism.record_help("agumon", "gabumon", 10.0, 1)
        self.altruism.record_help("agumon", "gabumon", 15.0, 2)
        assert self.altruism.get_debt("gabumon", "agumon") == 25.0

    # ---- get_debt ----

    def test_get_debt_returns_correct_amount(self):
        """get_debt returns the exact debt amount owed."""
        self.altruism.record_help("patamon", "tentomon", 30.0, 1)
        assert self.altruism.get_debt("tentomon", "patamon") == 30.0
        # Non-existent debt returns 0.0
        assert self.altruism.get_debt("nobody", "someone") == 0.0

    # ---- debt cap ----

    def test_debt_capped_at_max(self):
        """Debt is capped at MAX_DEBT."""
        self.altruism.record_help("agumon", "gabumon", MAX_DEBT + 20.0, 1)
        assert self.altruism.get_debt("gabumon", "agumon") == MAX_DEBT

    def test_debt_capped_on_accumulation(self):
        """Accumulated debt is capped at MAX_DEBT."""
        self.altruism.record_help("agumon", "gabumon", 30.0, 1)
        self.altruism.record_help("agumon", "gabumon", 30.0, 2)
        assert self.altruism.get_debt("gabumon", "agumon") == MAX_DEBT

    # ---- should_reciprocate ----

    def test_should_reciprocate_triggers_above_threshold(self):
        """should_reciprocate returns True when debt > RECIPROCITY_DEBT_THRESHOLD."""
        self.altruism.record_help("agumon", "gabumon", RECIPROCITY_DEBT_THRESHOLD + 1.0, 1)
        assert self.altruism.should_reciprocate("gabumon", "agumon") is True

    def test_should_reciprocate_false_below_threshold(self):
        """should_reciprocate returns False when debt <= RECIPROCITY_DEBT_THRESHOLD."""
        self.altruism.record_help("agumon", "gabumon", RECIPROCITY_DEBT_THRESHOLD, 1)
        assert self.altruism.should_reciprocate("gabumon", "agumon") is False

    def test_should_reciprocate_false_no_debt(self):
        """should_reciprocate returns False when no debt exists."""
        assert self.altruism.should_reciprocate("gabumon", "agumon") is False

    # ---- get_altruism_score ----

    def test_get_altruism_score_for_helper(self):
        """get_altruism_score > 0 for agent who has helped others."""
        self.altruism.record_help("agumon", "gabumon", 50.0, 1)
        self.altruism.record_help("agumon", "patamon", 30.0, 2)
        score = self.altruism.get_altruism_score("agumon")
        # 50 + 30 = 80, normalized: 80 / 250 = 0.32
        assert score > 0.0
        assert score <= 1.0

    def test_get_altruism_score_for_pure_recipient(self):
        """get_altruism_score returns 0.0 for agent who only received help."""
        self.altruism.record_help("agumon", "gabumon", 50.0, 1)
        # gabumon is the recipient, not a helper
        score = self.altruism.get_altruism_score("gabumon")
        assert score == 0.0

    def test_get_altruism_score_unknown_agent(self):
        """get_altruism_score returns 0.0 for unknown agent."""
        assert self.altruism.get_altruism_score("nonexistent") == 0.0

    # ---- get_top_creditors ----

    def test_get_top_creditors_returns_correct_ranking(self):
        """get_top_creditors returns debtors sorted by debt descending."""
        self.altruism.record_help("agumon", "gabumon", 40.0, 1)
        self.altruism.record_help("agumon", "patamon", 10.0, 2)
        self.altruism.record_help("agumon", "tentomon", 25.0, 3)
        creditors = self.altruism.get_top_creditors("agumon")
        assert len(creditors) == 3
        assert creditors[0] == ("gabumon", 40.0)
        assert creditors[1] == ("tentomon", 25.0)
        assert creditors[2] == ("patamon", 10.0)

    def test_get_top_creditors_respects_n_limit(self):
        """get_top_creditors respects the n limit."""
        self.altruism.record_help("agumon", "a", 10.0, 1)
        self.altruism.record_help("agumon", "b", 20.0, 2)
        self.altruism.record_help("agumon", "c", 30.0, 3)
        assert len(self.altruism.get_top_creditors("agumon", n=2)) == 2

    def test_get_top_creditors_empty_when_none(self):
        """get_top_creditors returns empty list when agent has no debtors."""
        assert self.altruism.get_top_creditors("agumon") == []

    # ---- get_top_debtors ----

    def test_get_top_debtors_returns_correct_ranking(self):
        """get_top_debtors returns creditors sorted by debt descending."""
        self.altruism.record_help("agumon", "gabumon", 40.0, 1)
        self.altruism.record_help("patamon", "gabumon", 15.0, 2)
        self.altruism.record_help("tentomon", "gabumon", 30.0, 3)
        debtors = self.altruism.get_top_debtors("gabumon")
        assert len(debtors) == 3
        assert debtors[0] == ("agumon", 40.0)
        assert debtors[1] == ("tentomon", 30.0)
        assert debtors[2] == ("patamon", 15.0)

    def test_get_top_debtors_empty_when_none(self):
        """get_top_debtors returns empty list when agent owes no debts."""
        assert self.altruism.get_top_debtors("gabumon") == []

    # ---- decay_debts ----

    def test_decay_debts_reduces_debt_over_time(self):
        """decay_debts reduces all debts by the decay factor after interval."""
        self.altruism.record_help("agumon", "gabumon", 40.0, 0)
        self.altruism.record_help("patamon", "gabumon", 20.0, 0)

        # Advance past decay interval
        ticks_decayed = self.altruism.decay_debts(DEBT_DECAY_INTERVAL)
        assert ticks_decayed > 0

        # Both debts should be halved
        assert self.altruism.get_debt("gabumon", "agumon") == 20.0
        assert self.altruism.get_debt("gabumon", "patamon") == 10.0

    def test_decay_debts_no_decay_before_interval(self):
        """decay_debts does nothing before the interval elapses."""
        self.altruism.record_help("agumon", "gabumon", 40.0, 0)

        ticks_decayed = self.altruism.decay_debts(DEBT_DECAY_INTERVAL - 1)
        assert ticks_decayed == 0
        assert self.altruism.get_debt("gabumon", "agumon") == 40.0

    def test_decay_debts_removes_tiny_debts(self):
        """decay_debts removes debts that fall below 0.5."""
        # Record a small debt
        self.altruism.record_help("agumon", "gabumon", 0.8, 0)

        ticks_decayed = self.altruism.decay_debts(DEBT_DECAY_INTERVAL)
        assert ticks_decayed > 0

        # 0.8 * 0.5 = 0.4 < 0.5, should be removed
        assert self.altruism.get_debt("gabumon", "agumon") == 0.0

    def test_decay_debts_multiple_cycles(self):
        """decay_debts applies multiple decay cycles for long intervals."""
        self.altruism.record_help("agumon", "gabumon", 80.0, 0)

        # 2 decay cycles but MAX_DEBT caps at 50: 50 → 25 → 12.5
        ticks_decayed = self.altruism.decay_debts(DEBT_DECAY_INTERVAL * 2)
        assert ticks_decayed == DEBT_DECAY_INTERVAL * 2

        assert self.altruism.get_debt("gabumon", "agumon") == 12.5

    # ---- to_dict / clear ----

    def test_to_dict_serializes_debts(self):
        """to_dict serializes all debts correctly."""
        self.altruism.record_help("agumon", "gabumon", 25.5, 1)
        self.altruism.record_help("patamon", "tentomon", 10.0, 2)
        d = self.altruism.to_dict()
        assert "debts" in d
        assert "last_decay_tick" in d
        assert "gabumon->agumon" in d["debts"] or d["debts"] == {}
        assert d["last_decay_tick"] == 0

    def test_clear_resets_state(self):
        """clear() resets all debts and last_decay_tick."""
        self.altruism.record_help("agumon", "gabumon", 50.0, 1)
        self.altruism.decay_debts(DEBT_DECAY_INTERVAL)

        self.altruism.clear()
        assert self.altruism.get_debt("gabumon", "agumon") == 0.0
        assert self.altruism._last_decay_tick == 0
        assert len(self.altruism._debts) == 0


# ──────────────────────────────────────────────
# EnergyEconomy Tests
# ──────────────────────────────────────────────


class TestEnergyEconomy:
    """Tests for the EnergyEconomy engine."""

    @pytest.fixture(autouse=True)
    def setup_economy(self):
        """Fresh economy with two agents for each test."""
        self.agumon = make_mock_agent("agumon", energy=50.0)
        self.gabumon = make_mock_agent("gabumon", energy=50.0)
        self.economy = make_economy(
            {"agumon": self.agumon, "gabumon": self.gabumon}
        )

    # ---- propose_transfer ----

    def test_propose_transfer_successful_donation(self):
        """Successful donation returns a transfer and adjusts energy."""
        transfer = self.economy.propose_transfer(
            "agumon", "gabumon", 20.0, "donation", "Helping a friend", 1
        )
        assert transfer is not None
        assert transfer.from_agent == "agumon"
        assert transfer.to_agent == "gabumon"
        assert transfer.amount == 20.0
        assert transfer.transfer_type == "donation"
        assert transfer.tick == 1

        # Energy adjusted
        assert self.agumon.cognitive_energy.energy == 30.0
        assert self.gabumon.cognitive_energy.energy == 70.0

    def test_propose_transfer_insufficient_energy_rejected(self):
        """Transfer rejected when from_agent lacks enough energy."""
        transfer = self.economy.propose_transfer(
            "agumon", "gabumon", 45.0, "donation", "Too much", 1
        )
        # 50 - 45 = 5 < MIN_SURVIVAL_ENERGY (10)
        assert transfer is None
        # Energy unchanged
        assert self.agumon.cognitive_energy.energy == 50.0
        assert self.gabumon.cognitive_energy.energy == 50.0

    def test_propose_transfer_nonexistent_agent_rejected(self):
        """Transfer rejected when either agent doesn't exist."""
        assert self.economy.propose_transfer("agumon", "nonexistent", 10.0, "donation", "", 1) is None
        assert self.economy.propose_transfer("nonexistent", "gabumon", 10.0, "donation", "", 1) is None

    def test_propose_transfer_non_positive_amount_rejected(self):
        """Transfer rejected when amount <= 0."""
        assert self.economy.propose_transfer("agumon", "gabumon", 0.0, "donation", "", 1) is None
        assert self.economy.propose_transfer("agumon", "gabumon", -5.0, "donation", "", 1) is None

    def test_propose_transfer_awaken_requires_dormant_target(self):
        """Awaken transfer rejected when target is not dormant."""
        # amount must be > 0 to pass initial validation (awaken uses fixed values internally)
        transfer = self.economy.propose_transfer(
            "agumon", "gabumon", 1, "awaken", "Wake up!", 1
        )
        assert transfer is None

    def test_propose_transfer_awaken_succeeds(self):
        """Awaken succeeds: helper pays AWAKEN_HELPER_COST, target restored."""
        # Make gabumon dormant
        self.gabumon.cognitive_energy.is_dormant = True
        self.gabumon.cognitive_energy.energy = 0.0

        # Agumon needs enough energy (AWAKEN_MIN_HELPER_ENERGY = 15 + 10 = 25)
        self.agumon.cognitive_energy.energy = 50.0

        # amount must be > 0 to pass validation; awaken uses fixed AWAKEN cost/gain
        transfer = self.economy.propose_transfer(
            "agumon", "gabumon", 1, "awaken", "Wake up!", 1
        )
        assert transfer is not None
        assert transfer.transfer_type == "awaken"
        assert transfer.amount == AWAKEN_RESTORE_AMOUNT  # amount records what target gains

        # Helper consumed AWAKEN_HELPER_COST
        assert self.agumon.cognitive_energy.energy == 50.0 - AWAKEN_HELPER_COST
        # Target restored
        assert self.gabumon.cognitive_energy.energy == AWAKEN_RESTORE_AMOUNT
        assert self.gabumon.cognitive_energy.is_dormant is False

    def test_propose_transfer_awaken_helper_energy_insufficient(self):
        """Awaken rejected when helper lacks minimum energy."""
        self.gabumon.cognitive_energy.is_dormant = True
        self.agumon.cognitive_energy.energy = 20.0  # Below AWAKEN_MIN_HELPER_ENERGY (25)

        transfer = self.economy.propose_transfer(
            "agumon", "gabumon", 1, "awaken", "Wake up!", 1
        )
        assert transfer is None

    def test_propose_transfer_type_reflected_in_record(self):
        """Transfer record reflects the correct transfer_type."""
        transfer = self.economy.propose_transfer(
            "agumon", "gabumon", 10.0, "trade", "Trading", 1
        )
        assert transfer is not None
        assert transfer.transfer_type == "trade"

    def test_propose_transfer_records_in_history(self):
        """propose_transfer appends to transfer_history."""
        self.economy.propose_transfer("agumon", "gabumon", 10.0, "donation", "", 1)
        assert len(self.economy.transfer_history) == 1

        self.economy.propose_transfer("gabumon", "agumon", 5.0, "donation", "", 2)
        assert len(self.economy.transfer_history) == 2

    def test_propose_transfer_updates_altruism_donation(self):
        """Donation transfer updates altruism debts."""
        self.economy.propose_transfer("agumon", "gabumon", 15.0, "donation", "", 1)
        # gabumon now owes agumon 15.0
        assert self.economy.altruism.get_debt("gabumon", "agumon") == 15.0

    def test_propose_transfer_updates_altruism_awaken(self):
        """Awaken transfer updates altruism debts."""
        self.gabumon.cognitive_energy.is_dormant = True
        self.gabumon.cognitive_energy.energy = 0.0
        self.agumon.cognitive_energy.energy = 50.0

        self.economy.propose_transfer("agumon", "gabumon", 1, "awaken", "", 1)
        assert self.economy.altruism.get_debt("gabumon", "agumon") == AWAKEN_RESTORE_AMOUNT

    def test_propose_transfer_does_not_update_altruism_trade(self):
        """Trade transfer does NOT update altruism debts."""
        self.economy.propose_transfer("agumon", "gabumon", 10.0, "trade", "", 1)
        assert self.economy.altruism.get_debt("gabumon", "agumon") == 0.0

    # ---- check_awaken_opportunities ----

    def test_check_awaken_opportunities_finds_dormant(self):
        """check_awaken_opportunities finds dormant agents with indebted friends."""
        # Make gabumon dormant
        self.gabumon.cognitive_energy.is_dormant = True
        self.gabumon.cognitive_energy.energy = 0.0

        # Agumon helped gabumon before (gabumon owes agumon debt)
        self.economy.altruism.record_help("gabumon", "agumon", 30.0, 0)
        # Actually, gabumon helped agumon → agumon owes gabumon
        # Wait, let me re-read. get_top_creditors(agent) returns who owes agent.
        # For awaken: dormant agent is "agent" (creditor). We look for debtors who owe them.
        # So: dormant agent = gabumon. We need agumon to owe gabumon.
        # record_help("gabumon", "agumon", 30.0) → gabumon helped agumon → agumon owes gabumon 30.0
        # get_top_creditors("gabumon") → [(agumon, 30.0)] ✓

        opportunities = self.economy.check_awaken_opportunities()
        assert len(opportunities) == 1
        dormant_name, helper_name, debt = opportunities[0]
        assert dormant_name == "gabumon"
        assert helper_name == "agumon"
        assert debt == 30.0

    def test_check_awaken_opportunities_empty_when_none_dormant(self):
        """check_awaken_opportunities returns empty when no agents are dormant."""
        opportunities = self.economy.check_awaken_opportunities()
        assert opportunities == []

    def test_check_awaken_opportunities_skips_helper_with_insufficient_energy(self):
        """Dormant agent skipped when potential helper lacks energy."""
        self.gabumon.cognitive_energy.is_dormant = True
        self.gabumon.cognitive_energy.energy = 0.0

        # Agumon owes gabumon but has low energy
        self.economy.altruism.record_help("gabumon", "agumon", 30.0, 0)
        self.agumon.cognitive_energy.energy = 10.0  # < AWAKEN_MIN_HELPER_ENERGY (25)

        opportunities = self.economy.check_awaken_opportunities()
        assert len(opportunities) == 0

    def test_check_awaken_opportunities_skips_dormant_helper(self):
        """Dormant agent skipped when potential helper is also dormant."""
        self.gabumon.cognitive_energy.is_dormant = True
        self.gabumon.cognitive_energy.energy = 0.0
        self.agumon.cognitive_energy.is_dormant = True
        self.agumon.cognitive_energy.energy = 0.0

        self.economy.altruism.record_help("gabumon", "agumon", 30.0, 0)

        opportunities = self.economy.check_awaken_opportunities()
        assert len(opportunities) == 0

    # ---- check_desperation_relief ----

    def test_check_desperation_relief_finds_low_energy_agents(self):
        """check_desperation_relief finds agents below DESPERATION_ENERGY_THRESHOLD."""
        # Agumon is low energy
        self.agumon.cognitive_energy.energy = 15.0  # < DESPERATION_ENERGY_THRESHOLD (20)

        # Gabumon owes agumon a significant debt (gabumon helped agumon? No...)
        # Wait: get_top_creditors(agent_name) = who owes agent_name.
        # For relief: low-energy agent B is the creditor. Donor A owes B.
        # So: record_help("agumon", "gabumon", 20.0) → agumon helped gabumon → gabumon owes agumon
        # get_top_creditors("agumon") → [(gabumon, 20.0)]
        # At 20 debt, should_reciprocate("gabumon", "agumon") = debt > 10? YES
        self.economy.altruism.record_help("agumon", "gabumon", 20.0, 0)
        # Gabumon has enough energy for donation
        self.gabumon.cognitive_energy.energy = 50.0  # > DONATION_MIN_HELPER_ENERGY (30)

        reliefs = self.economy.check_desperation_relief()
        assert len(reliefs) == 1
        low_agent, donor, debt = reliefs[0]
        assert low_agent == "agumon"
        assert donor == "gabumon"
        assert debt == 20.0

    def test_check_desperation_relief_respects_debt_threshold(self):
        """check_desperation_relief skips when debt is below threshold."""
        self.agumon.cognitive_energy.energy = 15.0
        self.economy.altruism.record_help("agumon", "gabumon", 5.0, 0)  # Below threshold
        self.gabumon.cognitive_energy.energy = 50.0

        reliefs = self.economy.check_desperation_relief()
        assert len(reliefs) == 0

    def test_check_desperation_relief_no_debt(self):
        """check_desperation_relief returns empty when no debt exists."""
        self.agumon.cognitive_energy.energy = 15.0
        self.gabumon.cognitive_energy.energy = 50.0

        reliefs = self.economy.check_desperation_relief()
        assert len(reliefs) == 0

    def test_check_desperation_relief_skips_dormant_low_agent(self):
        """check_desperation_relief skips dormant low-energy agents."""
        self.agumon.cognitive_energy.is_dormant = True
        self.agumon.cognitive_energy.energy = 0.0
        self.economy.altruism.record_help("agumon", "gabumon", 30.0, 0)
        self.gabumon.cognitive_energy.energy = 50.0

        reliefs = self.economy.check_desperation_relief()
        assert len(reliefs) == 0  # Dormant agents are skipped

    def test_check_desperation_relief_donor_needs_min_energy(self):
        """check_desperation_relief skips donors below DONATION_MIN_HELPER_ENERGY."""
        self.agumon.cognitive_energy.energy = 15.0
        self.economy.altruism.record_help("agumon", "gabumon", 20.0, 0)
        self.gabumon.cognitive_energy.energy = 25.0  # < DONATION_MIN_HELPER_ENERGY (30)

        reliefs = self.economy.check_desperation_relief()
        assert len(reliefs) == 0

    # ---- get_transfer_history ----

    def test_get_transfer_history_all(self):
        """get_transfer_history returns all transfers when no agent filter."""
        self.economy.propose_transfer("agumon", "gabumon", 10.0, "donation", "", 1)
        self.economy.propose_transfer("gabumon", "agumon", 5.0, "donation", "", 2)

        history = self.economy.get_transfer_history()
        assert len(history) == 2

    def test_get_transfer_history_filter_by_agent(self):
        """get_transfer_history filters by agent name."""
        self.economy.propose_transfer("agumon", "gabumon", 10.0, "donation", "", 1)
        self.economy.propose_transfer("gabumon", "agumon", 5.0, "donation", "", 2)
        self.economy.propose_transfer("gabumon", "agumon", 3.0, "donation", "", 3)

        agumon_history = self.economy.get_transfer_history(agent_name="agumon")
        assert len(agumon_history) == 3  # All involve agumon

        gabumon_history = self.economy.get_transfer_history(agent_name="gabumon")
        assert len(gabumon_history) == 3

    def test_get_transfer_history_limits_results(self):
        """get_transfer_history respects the limit parameter."""
        for i in range(10):
            self.economy.propose_transfer("agumon", "gabumon", 1.0, "donation", "", i)

        history = self.economy.get_transfer_history(limit=3)
        assert len(history) == 3

    # ---- get_economy_stats ----

    def test_get_economy_stats_correct_totals(self):
        """get_economy_stats returns correct aggregated totals."""
        self.economy.propose_transfer("agumon", "gabumon", 10.0, "donation", "", 1)
        self.economy.propose_transfer("gabumon", "agumon", 5.0, "trade", "", 2)

        stats = self.economy.get_economy_stats()
        assert stats["total_transfers"] == 2
        assert stats["total_energy_transferred"] == 15.0
        assert stats["donation_count"] == 1
        assert stats["trade_count"] == 1
        assert stats["awaken_count"] == 0
        assert stats["tribute_count"] == 0
        assert "avg_altruism_score" in stats
        assert "total_debt_pairs" in stats

    def test_get_economy_stats_empty(self):
        """get_economy_stats returns zeros when no transfers."""
        stats = self.economy.get_economy_stats()
        assert stats["total_transfers"] == 0
        assert stats["total_energy_transferred"] == 0

    # ---- step() ----

    def test_step_executes_decay_and_scan(self):
        """step() executes debt decay + relief scan + awaken scan."""
        events = self.economy.step(DEBT_DECAY_INTERVAL)
        # No debts/no dormant → should return empty events
        assert isinstance(events, list)

    def test_step_triggers_relief(self):
        """step() triggers reciprocal relief when conditions are met."""
        # Setup: agumon is low energy, gabumon owes agumon debt
        self.agumon.cognitive_energy.energy = DESPERATION_ENERGY_THRESHOLD - 1  # 19
        self.economy.altruism.record_help("agumon", "gabumon", 20.0, 0)
        self.gabumon.cognitive_energy.energy = 50.0

        events = self.economy.step(0)
        # Check if relief was triggered
        relief_events = [e for e in events if e["type"] == "reciprocal_relief"]
        assert len(relief_events) >= 1
        assert relief_events[0]["donor"] == "gabumon"
        assert relief_events[0]["recipient"] == "agumon"

    def test_step_triggers_awaken(self):
        """step() triggers awaken when dormant agent has a friend."""
        self.gabumon.cognitive_energy.is_dormant = True
        self.gabumon.cognitive_energy.energy = 0.0
        self.agumon.cognitive_energy.energy = 50.0

        # Agumon owes gabumon → agumon should help awaken
        self.economy.altruism.record_help("gabumon", "agumon", 30.0, 0)

        events = self.economy.step(0)
        awaken_events = [e for e in events if e["type"] == "awaken"]
        assert len(awaken_events) >= 1
        assert awaken_events[0]["helper"] == "agumon"
        assert awaken_events[0]["dormant"] == "gabumon"

    # ---- to_dict ----

    def test_to_dict_serializes_correctly(self):
        """to_dict serializes altruism, transfer_history, and economy_stats."""
        self.economy.propose_transfer("agumon", "gabumon", 10.0, "donation", "test", 1)

        d = self.economy.to_dict()
        assert "altruism" in d
        assert "transfer_history" in d
        assert "economy_stats" in d
        assert len(d["transfer_history"]) == 1
        assert d["transfer_history"][0]["from_agent"] == "agumon"
        assert d["economy_stats"]["total_transfers"] == 1

    def test_to_dict_truncates_to_100(self):
        """to_dict truncates transfer_history to last 100 entries."""
        # Give enough energy for 150+ transfers (each 1.0, need 10 survival reserve)
        self.agumon.cognitive_energy.energy = 500.0
        self.gabumon.cognitive_energy.energy = 500.0
        for i in range(150):
            # Alternate direction so neither agent runs out
            if i % 2 == 0:
                self.economy.propose_transfer("agumon", "gabumon", 1.0, "donation", "", i)
            else:
                self.economy.propose_transfer("gabumon", "agumon", 1.0, "donation", "", i)

        d = self.economy.to_dict()
        assert len(d["transfer_history"]) == 100


# ──────────────────────────────────────────────
# Integration Tests with CognitiveEnergyPool
# ──────────────────────────────────────────────


class TestEnergyEconomyIntegration:
    """Integration tests verifying actual energy state mutations."""

    @pytest.fixture(autouse=True)
    def setup_integration(self):
        """Setup three agents with different states."""
        self.agumon = make_mock_agent("agumon", energy=50.0)
        self.gabumon = make_mock_agent("gabumon", energy=30.0, is_dormant=True)
        self.patamon = make_mock_agent("patamon", energy=80.0)
        self.economy = make_economy({
            "agumon": self.agumon,
            "gabumon": self.gabumon,
            "patamon": self.patamon,
        })

    def test_awaken_restores_energy_to_dormant_agent(self):
        """Awaken actually restores energy and clears dormant status."""
        # gabumon is dormant with 0 energy
        self.gabumon.cognitive_energy.energy = 0.0
        assert self.gabumon.cognitive_energy.is_dormant is True
        assert self.gabumon.cognitive_energy.energy == 0.0

        # Patamon has enough energy to awaken gabumon (amount must be > 0)
        transfer = self.economy.propose_transfer(
            "patamon", "gabumon", 1, "awaken", "Reviving gabumon", 1
        )
        assert transfer is not None
        assert self.gabumon.cognitive_energy.energy == AWAKEN_RESTORE_AMOUNT
        assert self.gabumon.cognitive_energy.is_dormant is False

    def test_donation_transfers_energy_between_agents(self):
        """Donation accurately transfers energy from donor to recipient."""
        initial_agumon = self.agumon.cognitive_energy.energy
        initial_patamon = self.patamon.cognitive_energy.energy

        transfer = self.economy.propose_transfer(
            "patamon", "agumon", 25.0, "donation", "Sharing energy", 1
        )
        assert transfer is not None

        # Patamon's energy decreased
        assert self.patamon.cognitive_energy.energy == initial_patamon - 25.0
        # Agumon's energy increased
        assert self.agumon.cognitive_energy.energy == initial_agumon + 25.0

    def test_after_transfer_from_agent_energy_decreases(self):
        """From agent's energy decreases by the transfer amount."""
        initial = self.patamon.cognitive_energy.energy

        self.economy.propose_transfer("patamon", "agumon", 15.0, "donation", "", 1)

        assert self.patamon.cognitive_energy.energy == initial - 15.0

    def test_awaken_drains_helper_energy(self):
        """Awaken deducts AWAKEN_HELPER_COST from helper."""
        initial = self.patamon.cognitive_energy.energy
        self.gabumon.cognitive_energy.energy = 0.0

        self.economy.propose_transfer("patamon", "gabumon", 1, "awaken", "", 1)

        assert self.patamon.cognitive_energy.energy == initial - AWAKEN_HELPER_COST

    def test_donation_below_survival_rejected(self):
        """Donation that would drop donor below MIN_SURVIVAL_ENERGY is rejected."""
        # patamon has 80, needs to keep 10 after transfer
        # max transfer: 80 - 10 = 70
        transfer = self.economy.propose_transfer(
            "patamon", "agumon", 75.0, "donation", "Too generous", 1
        )
        assert transfer is None
        # Energy unchanged
        assert self.patamon.cognitive_energy.energy == 80.0

    def test_transfer_history_grows_correctly(self):
        """Multiple transfers are all recorded in history."""
        self.economy.propose_transfer("patamon", "agumon", 10.0, "donation", "", 1)
        self.economy.propose_transfer("agumon", "patamon", 5.0, "tribute", "", 2)
        self.gabumon.cognitive_energy.energy = 0.0
        self.economy.propose_transfer("patamon", "gabumon", 1, "awaken", "", 3)

        history = self.economy.get_transfer_history()
        assert len(history) == 3
        types = {t.transfer_type for t in history}
        assert "donation" in types
        assert "tribute" in types
        assert "awaken" in types
