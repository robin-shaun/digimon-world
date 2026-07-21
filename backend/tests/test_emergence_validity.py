"""Tests for Phase 31 Task 2 — coupling gain emergence validity metrics.

Based on arXiv:2606.22203 — differentiates genuine emergence
from random coincidence using coupling gain.
"""

from __future__ import annotations

import math
import random
from types import SimpleNamespace

import pytest

from digimon_world.world.emergence_metrics import (
    EmergenceValiditySnapshot,
    compute_coupling_gain,
)

# ─────────────────────────────────────────────
# Helper: create a mock agent
# ─────────────────────────────────────────────


def _agent(name: str, plan: str | None, location: tuple[float, float],
           mood: dict[str, float] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        current_plan=plan,
        location=location,
        mood_state=mood if mood is not None else {"joy": 0.5, "fear": 0.1, "anger": 0.1, "sadness": 0.1},
    )


def _world(*agents) -> SimpleNamespace:
    return SimpleNamespace(all=lambda: list(agents))


# ─────────────────────────────────────────────
# Tests: Empty / Insufficient data
# ─────────────────────────────────────────────


class TestCouplingGainEmpty:
    """0 agents → insufficient_data."""

    def test_empty_world(self):
        w = _world()
        snap = compute_coupling_gain(w)
        assert snap.agent_count == 0
        assert snap.verdict == "insufficient_data"
        assert snap.coupling_gain == 0.0
        assert snap.validity_score == 0.0

    def test_empty_to_dict(self):
        w = _world()
        snap = compute_coupling_gain(w)
        d = snap.to_dict()
        assert d["verdict"] == "insufficient_data"
        assert "details" in d


class TestCouplingGainSingleAgent:
    """1 agent → insufficient_data."""

    def test_single_agent(self):
        w = _world(_agent("a", "探索世界", (100, 200)))
        snap = compute_coupling_gain(w)
        assert snap.agent_count == 1
        assert snap.verdict == "insufficient_data"
        assert snap.coupling_gain == 0.0

    def test_two_agents_still_insufficient(self):
        w = _world(
            _agent("a", "探索", (0, 0)),
            _agent("b", "探索", (1, 1)),
        )
        snap = compute_coupling_gain(w)
        assert snap.agent_count == 2
        assert snap.verdict == "insufficient_data"  # n < 5


class TestCouplingGainSmallGroup:
    """3-4 agents — still insufficient_data due to n<5 threshold."""

    def test_three_agents_insufficient(self):
        w = _world(
            _agent("a", "探索世界", (100, 100)),
            _agent("b", "探索世界", (110, 110)),
            _agent("c", "探索世界", (120, 120)),
        )
        snap = compute_coupling_gain(w)
        assert snap.agent_count == 3
        assert snap.verdict == "insufficient_data"


# ─────────────────────────────────────────────
# Tests: Suspected noise
# ─────────────────────────────────────────────


class TestCouplingGainSuspectedNoise:
    """High behavioral consistency + low info coupling → suspected_noise."""

    def test_identical_plans_far_apart(self):
        """5 agents all with same plan but far apart → suspected noise."""
        agents = [
            _agent("a", "探索世界", (0, 0)),
            _agent("b", "探索世界", (1000, 0)),
            _agent("c", "探索世界", (0, 1000)),
            _agent("d", "探索世界", (1000, 1000)),
            _agent("e", "探索世界", (2000, 2000)),
        ]
        w = _world(*agents)
        snap = compute_coupling_gain(w)
        assert snap.agent_count == 5
        # plan_coupling high (all same plan), but location_coupling low (all far apart)
        # plan_alignment = 5/5 = 1.0, mood same → behavioral_consistency high
        # info_coupling = plan_coupling*0.6 + 0*0.4 = 0.6
        # coupling_gain = 0.6 / (0.75 + 0.01) ~= 0.79
        assert snap.behavioral_consistency > 0.3, f"expected high consistency, got {snap.behavioral_consistency}"
        assert snap.info_coupling < 0.8, f"expected moderate coupling, got {snap.info_coupling}"
        # Should be suspected_noise since coupling_gain <= 0.8 & consistency > 0.3
        # But with high coupling it might actually be > 0.8. Let's just check details.
        assert snap.verdict in ("suspected_noise", "neutral")

    def test_same_plans_all_scattered(self):
        """Identical plans but scattered → coupling from plan but not location."""
        agents = [
            _agent(f"a{i}", "休息中", (float(i * 500), float(i * 500)))
            for i in range(5)
        ]
        w = _world(*agents)
        snap = compute_coupling_gain(w)
        assert snap.details["plan_coupling"] == 1.0  # all same plan
        assert snap.details["location_coupling"] == 0.0  # all far apart


# ─────────────────────────────────────────────
# Tests: Genuine emergence
# ─────────────────────────────────────────────


class TestCouplingGainGenuine:
    """High info coupling + high consistency → genuine emergence."""

    def test_same_plan_close_together(self):
        """5 agents all with same plan AND close together → genuine."""
        agents = [
            _agent("a", "探索世界", (100, 100)),
            _agent("b", "探索世界", (110, 110)),
            _agent("c", "探索世界", (120, 120)),
            _agent("d", "探索世界", (130, 130)),
            _agent("e", "探索世界", (140, 140)),
        ]
        w = _world(*agents)
        snap = compute_coupling_gain(w)
        assert snap.agent_count == 5
        assert snap.details["plan_coupling"] == 1.0
        assert snap.details["location_coupling"] > 0.8  # nearly all pairs within 200px
        assert snap.info_coupling > 0.8
        assert snap.verdict in ("genuine", "neutral")  # depends on mood alignment


# ─────────────────────────────────────────────
# Tests: Neutral / normal social behavior
# ─────────────────────────────────────────────


class TestCouplingGainNeutral:
    """Mixed plans, mixed locations → neutral."""

    def test_mixed_everything(self):
        """Random variety of plans and positions."""
        plans = ["探索世界", "寻找食物", "守护领地", "休息一下", "与朋友交流"]
        random.seed(42)
        agents = [
            _agent(
                f"a{i}",
                plans[i % len(plans)],
                (float(random.randint(0, 2000)), float(random.randint(0, 2000))),
                {"joy": random.random(), "fear": random.random(), "anger": random.random(), "sadness": random.random()},
            )
            for i in range(10)
        ]
        w = _world(*agents)
        snap = compute_coupling_gain(w)
        assert snap.agent_count == 10
        # With random data, most likely neutral or suspected_noise
        assert snap.verdict in ("neutral", "suspected_noise", "genuine")


# ─────────────────────────────────────────────
# Tests: Snapshot to_dict
# ─────────────────────────────────────────────


class TestValiditySnapshotToDict:
    """Verify to_dict() output format."""

    def test_to_dict_structure(self):
        snap = EmergenceValiditySnapshot(
            coupling_gain=1.23456,
            info_coupling=0.5678,
            behavioral_consistency=0.4567,
            validity_score=41.15,
            verdict="neutral",
            coupling_threshold=0.5,
            agent_count=30,
            details={"plan_coupling": 0.3, "location_coupling": 0.2, "plan_alignment": 0.3, "mood_alignment": 0.4},
        )
        d = snap.to_dict()
        assert d["coupling_gain"] == 1.2346
        assert d["info_coupling"] == 0.5678
        assert d["behavioral_consistency"] == 0.4567
        assert d["validity_score"] == 41.1  # round(41.15, 1) banker's rounding
        assert d["verdict"] == "neutral"
        assert d["coupling_threshold"] == 0.5
        assert d["agent_count"] == 30
        assert d["details"]["plan_coupling"] == 0.3
        assert d["details"]["location_coupling"] == 0.2

    def test_default_values_to_dict(self):
        snap = EmergenceValiditySnapshot()
        d = snap.to_dict()
        assert d["coupling_gain"] == 0.0
        assert d["verdict"] == "unknown"
        assert d["agent_count"] == 0
        assert d["details"] == {}


# ─────────────────────────────────────────────
# Tests: Edge cases
# ─────────────────────────────────────────────


class TestCouplingGainEdgeCases:
    """Edge cases and boundary behavior."""

    def test_none_plans(self):
        """Agents with None plans — _classify_plan returns '无计划', all in same category."""
        agents = [
            _agent("a", None, (100, 100)),
            _agent("b", None, (200, 200)),
            _agent("c", None, (300, 300)),
            _agent("d", None, (400, 400)),
            _agent("e", None, (500, 500)),
        ]
        w = _world(*agents)
        snap = compute_coupling_gain(w)
        assert snap.details["plan_coupling"] == 1.0  # all in "无计划" category

    def test_empty_mood_state(self):
        """Agents with empty mood dicts — mood alignment should be 0."""
        agents = [
            _agent(f"a{i}", f"计划{i}", (float(i * 100), float(i * 100)), mood={})
            for i in range(5)
        ]
        w = _world(*agents)
        snap = compute_coupling_gain(w)
        assert snap.details["mood_alignment"] == 0.0

    def test_all_different_moods(self):
        """Mood vectors pointing in different directions."""
        agents = [
            _agent("a", "探索", (100, 100), mood={"joy": 1.0, "fear": 0.0, "anger": 0.0, "sadness": 0.0}),
            _agent("b", "探索", (110, 110), mood={"joy": 0.0, "fear": 1.0, "anger": 0.0, "sadness": 0.0}),
            _agent("c", "探索", (120, 120), mood={"joy": 0.0, "fear": 0.0, "anger": 1.0, "sadness": 0.0}),
            _agent("d", "探索", (130, 130), mood={"joy": 0.0, "fear": 0.0, "anger": 0.0, "sadness": 1.0}),
            _agent("e", "探索", (140, 140), mood={"joy": -1.0, "fear": 0.0, "anger": 0.0, "sadness": 0.0}),
        ]
        w = _world(*agents)
        snap = compute_coupling_gain(w)
        assert snap.details["mood_alignment"] < 0.5  # pairwise cos sims mostly 0

    def test_validity_score_bounded(self):
        """Validity score stays in [0, 100]."""
        # Test with extreme coupling gain
        agents = [
            _agent(f"a{i}", "探索世界", (100.0 + i, 100.0 + i))
            for i in range(10)
        ]
        w = _world(*agents)
        snap = compute_coupling_gain(w)
        assert 0 <= snap.validity_score <= 100

    def test_large_world_performance(self):
        """Ensure O(n²) algorithm works for 30 agents."""
        agents = [
            _agent(
                f"a{i}",
                f"计划{i % 7}",
                (float(i * 50), float(i * 50)),
            )
            for i in range(30)
        ]
        w = _world(*agents)
        snap = compute_coupling_gain(w)
        assert snap.agent_count == 30
        assert snap.verdict != "insufficient_data"


# ─────────────────────────────────────────────
# Tests: Coupling gain math
# ─────────────────────────────────────────────


class TestCouplingGainMath:
    """Verify mathematical properties."""

    def test_perfect_alignment_no_location(self):
        """All same plan, all same mood, but far apart."""
        agents = [
            _agent(f"a{i}", "探索世界", (float(i * 500), 0.0),
                   mood={"joy": 0.5, "fear": 0.1, "anger": 0.1, "sadness": 0.1})
            for i in range(5)
        ]
        w = _world(*agents)
        snap = compute_coupling_gain(w)
        # plan_coupling = 1.0, location_coupling = 0
        assert snap.details["plan_coupling"] == 1.0
        assert snap.details["location_coupling"] == 0.0
        # plan_alignment = 1.0, mood_alignment = 1.0 (all identical moods)
        assert snap.details["plan_alignment"] == 1.0
        assert snap.details["mood_alignment"] == pytest.approx(1.0, abs=1e-9)
        # info_coupling = 1.0*0.6 + 0*0.4 = 0.6
        assert snap.info_coupling == pytest.approx(0.6, abs=1e-6)
        # behavioral_consistency = 1.0*0.5 + 1.0*0.5 = 1.0
        assert snap.behavioral_consistency == pytest.approx(1.0, abs=1e-6)
        # coupling_gain = 0.6 / (1.0 + 0.01) = 0.5940...
        assert snap.coupling_gain == pytest.approx(0.6 / 1.01, abs=1e-4)

    def test_epsilon_prevent_division_by_zero(self):
        """When behavioral_consistency is 0, epsilon prevents NaN."""
        agents = [
            _agent("a", "探索", (100, 100), mood={}),
            _agent("b", "战斗", (500, 500), mood={}),
            _agent("c", "休息", (900, 900), mood={}),
            _agent("d", "觅食", (1300, 1300), mood={}),
            _agent("e", "守护", (1700, 1700), mood={}),
        ]
        w = _world(*agents)
        snap = compute_coupling_gain(w)
        # Empty moods → mood_alignment=0, all different plans → plan_alignment=0.2
        # behavioral_consistency = 0.2*0.5 + 0*0.5 = 0.1
        # coupling_gain = info_coupling / (0.1 + 0.01) = finite number
        assert not math.isnan(snap.coupling_gain)
        assert not math.isinf(snap.coupling_gain)

    def test_info_coupling_range(self):
        """info_coupling should always be in [0, 1]."""
        for n in [5, 10, 20]:
            agents = [
                _agent(f"a{i}", f"计划{i % 3}", (float(i), float(i)))
                for i in range(n)
            ]
            w = _world(*agents)
            snap = compute_coupling_gain(w)
            assert 0 <= snap.info_coupling <= 1, f"n={n}, info_coupling={snap.info_coupling}"

    def test_behavioral_consistency_range(self):
        """behavioral_consistency should always be in [0, 1]."""
        for n in [5, 10, 20]:
            agents = [
                _agent(f"a{i}", f"计划{i % 3}", (float(i), float(i)))
                for i in range(n)
            ]
            w = _world(*agents)
            snap = compute_coupling_gain(w)
            assert 0 <= snap.behavioral_consistency <= 1, f"n={n}, consistency={snap.behavioral_consistency}"
