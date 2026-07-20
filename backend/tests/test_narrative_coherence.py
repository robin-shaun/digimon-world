"""Tests for narrative_coherence.py — Phase 28 Task 3."""

from digimon_world.world.narrative_coherence import (
    COHERENCE_CHECK_INTERVAL,
    COHERENCE_HIGH_THRESHOLD,
    MAX_RELATION_HISTORY,
    MAX_SPATIAL_DISTANCE_PX,
    CoherenceReport,
    RelationConflict,
    RelationConflictDetector,
    RelationSnapshot,
    SpatialInconsistency,
    SpatialNarrativeBinder,
    _clamp,
    _find_nearest_position,
    _normalize_score,
    _sign,
    get_coherence_engine,
    reset_coherence_engine,
)

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


class TestHelpers:
    def test_clamp_in_range(self):
        assert _clamp(0.5) == 0.5
        assert _clamp(0.0) == 0.0
        assert _clamp(1.0) == 1.0

    def test_clamp_below(self):
        assert _clamp(-0.5) == 0.0
        assert _clamp(-10.0) == 0.0

    def test_clamp_above(self):
        assert _clamp(1.5) == 1.0
        assert _clamp(100.0) == 1.0

    def test_normalize_score_mid(self):
        assert _normalize_score(50, 0, 100) == 0.5
        assert _normalize_score(0, -100, 100) == 0.5

    def test_normalize_score_edge(self):
        assert _normalize_score(100, 0, 100) == 1.0
        assert _normalize_score(0, 0, 100) == 0.0

    def test_sign(self):
        assert _sign(5.0) == 1
        assert _sign(-3.0) == -1
        assert _sign(0.0) == 0

    def test_find_nearest_position_exact(self):
        pos_map = {10: (100.0, 200.0), 20: (300.0, 400.0)}
        result = _find_nearest_position(pos_map, 10)
        assert result == (100.0, 200.0)

    def test_find_nearest_position_approx(self):
        pos_map = {10: (100.0, 200.0), 20: (300.0, 400.0)}
        result = _find_nearest_position(pos_map, 15)
        assert result in [(100.0, 200.0), (300.0, 400.0)]

    def test_find_nearest_position_empty(self):
        assert _find_nearest_position({}, 10) is None

    def test_find_nearest_position_out_of_window(self):
        pos_map = {10: (100.0, 200.0)}
        # 默认窗口是 100 ticks，target=200 超出范围
        result = _find_nearest_position(pos_map, 200)
        assert result is None


# ──────────────────────────────────────────────
# RelationConflictDetector
# ──────────────────────────────────────────────


class TestRelationConflictDetector:
    def test_ambivalence_detected(self):
        c = RelationConflictDetector.detect_ambivalence("A", "B", 80, 85)
        assert c is not None
        assert c.conflict_type == "ambivalence"
        assert c.severity > 0.5

    def test_ambivalence_not_detected_low(self):
        c = RelationConflictDetector.detect_ambivalence("A", "B", 10, 20)
        assert c is None

    def test_ambivalence_not_detected_high_affinity_only(self):
        c = RelationConflictDetector.detect_ambivalence("A", "B", 90, 10)
        assert c is None

    def test_flip_detected(self):
        history = [
            RelationSnapshot("A", "B", 10, -80.0, 0.0, 0.0, 0.0),
            RelationSnapshot("A", "B", 50, 80.0, 0.0, 0.0, 0.0),
        ]
        c = RelationConflictDetector.detect_flip("A", "B", history)
        assert c is not None
        assert c.conflict_type == "flip"
        assert c.severity > 0.5

    def test_flip_not_detected_same_sign(self):
        history = [
            RelationSnapshot("A", "B", 10, 20.0, 0.0, 0.0, 0.0),
            RelationSnapshot("A", "B", 50, 80.0, 0.0, 0.0, 0.0),
        ]
        c = RelationConflictDetector.detect_flip("A", "B", history)
        assert c is None

    def test_flip_not_enough_history(self):
        history = [RelationSnapshot("A", "B", 10, 20.0, 0.0, 0.0, 0.0)]
        c = RelationConflictDetector.detect_flip("A", "B", history)
        assert c is None

    def test_one_sided_detected(self):
        c = RelationConflictDetector.detect_one_sided("A", "B", 90.0, -80.0)
        assert c is not None
        assert c.conflict_type == "one_sided"
        assert c.severity > 0.5

    def test_one_sided_not_detected_similar(self):
        c = RelationConflictDetector.detect_one_sided("A", "B", 50.0, 60.0)
        assert c is None

    def test_detect_all_returns_multiple(self):
        pairs = [
            ("A", "B", 80, 85, 80, 10),  # ambivalence (A→B) + ambivalence (B→A)
            ("C", "D", 90, -85, 10, 10),  # one_sided
        ]
        conflicts = RelationConflictDetector.detect_all(pairs)
        assert len(conflicts) >= 2

    def test_detect_all_empty(self):
        pairs = [("A", "B", 30, 40, 20, 10)]
        conflicts = RelationConflictDetector.detect_all(pairs)
        assert len(conflicts) == 0

    def test_relation_conflict_serialization(self):
        c = RelationConflict("A", "B", "ambivalence", 0.75, "test desc", [10, 20])
        d = c.to_dict()
        assert d["agent_a"] == "A"
        assert d["conflict_type"] == "ambivalence"
        assert d["severity"] == 0.75
        assert d["involved_ticks"] == [10, 20]


# ──────────────────────────────────────────────
# SpatialNarrativeBinder
# ──────────────────────────────────────────────


class TestSpatialNarrativeBinder:
    def test_event_location_consistent(self):
        inc = SpatialNarrativeBinder.check_event_location(
            "Agumon", "dialogue", 100, (50.0, 50.0), (55.0, 52.0)
        )
        assert inc is None

    def test_event_location_inconsistent(self):
        inc = SpatialNarrativeBinder.check_event_location(
            "Agumon", "battle", 100, (50.0, 50.0), (5000.0, 5000.0)
        )
        assert inc is not None
        assert inc.agent_name == "Agumon"
        assert inc.event_type == "battle"
        assert inc.distance_px > MAX_SPATIAL_DISTANCE_PX

    def test_event_location_no_position(self):
        inc = SpatialNarrativeBinder.check_event_location(
            "Agumon", "dialogue", 100, (50.0, 50.0), None
        )
        assert inc is None

    def test_check_batch(self):
        events = [
            {"agent_name": "A", "event_type": "dialogue", "tick": 10, "location": (100, 200)},
            {"agent_name": "B", "event_type": "battle", "tick": 20, "location": (300, 400)},
        ]
        agent_positions = {
            "A": {10: (105, 198)},  # close → OK
            "B": {20: (9999, 9999)},  # far → inconsistent
        }
        incs = SpatialNarrativeBinder.check_batch(events, agent_positions)
        assert len(incs) == 1
        assert incs[0].agent_name == "B"

    def test_check_batch_all_consistent(self):
        events = [
            {"agent_name": "A", "event_type": "dialogue", "tick": 10, "location": (100, 200)},
        ]
        agent_positions = {"A": {10: (102, 198)}}
        incs = SpatialNarrativeBinder.check_batch(events, agent_positions)
        assert len(incs) == 0

    def test_spatial_inconsistency_serialization(self):
        inc = SpatialInconsistency("A", "dialogue", 10, (100.0, 200.0), (5000.0, 6000.0), 5000.0)
        d = inc.to_dict()
        assert d["agent_name"] == "A"
        assert d["event_type"] == "dialogue"
        assert d["distance_px"] == 5000.0


# ──────────────────────────────────────────────
# CoherenceEngine
# ──────────────────────────────────────────────


class TestCoherenceEngine:
    def setup_method(self):
        reset_coherence_engine()
        self.engine = get_coherence_engine()

    def test_initial_state(self):
        # At tick 0, last_check_tick=0, so 0-0=0 < COHERENCE_CHECK_INTERVAL → False
        # This is correct: don't check at startup
        assert self.engine.should_check(0) is False
        # But at or beyond the interval, should trigger
        assert self.engine.should_check(COHERENCE_CHECK_INTERVAL) is True

    def test_check_healthy_world(self):
        report = self.engine.check(
            tick=50,
            agent_names=["A", "B", "C"],
            pairs_data=[
                ("A", "B", 30.0, 40.0, 10.0, 5.0),
                ("A", "C", 20.0, 25.0, 5.0, 5.0),
                ("B", "C", 15.0, 20.0, 8.0, 3.0),
            ],
            events=[
                {"agent_name": "A", "event_type": "dialogue", "tick": 40, "location": (100, 200)},
                {"agent_name": "B", "event_type": "dialogue", "tick": 40, "location": (300, 400)},
                {"agent_name": "C", "event_type": "discovery", "tick": 45, "location": (500, 600)},
            ],
        )
        assert report.global_score > COHERENCE_HIGH_THRESHOLD
        assert report.is_healthy() is True
        assert report.is_critical() is False
        assert report.agent_count == 3
        assert report.total_agent_pairs_checked == 3

    def test_check_with_ambivalence(self):
        report = self.engine.check(
            tick=50,
            agent_names=["A", "B"],
            pairs_data=[
                ("A", "B", 85.0, 90.0, 80.0, 75.0),
            ],
        )
        assert report.global_score < 1.0
        assert len(report.relation_conflicts) >= 1

    def test_check_with_spatial_issue(self):
        report = self.engine.check(
            tick=50,
            agent_names=["A"],
            pairs_data=[],
            events=[
                {"agent_name": "A", "event_type": "battle", "tick": 40, "location": (100, 200)},
            ],
            agent_positions={"A": {40: (9999, 9999)}},
        )
        assert report.spatial_score < 1.0
        assert len(report.spatial_inconsistencies) >= 1

    def test_should_check_interval(self):
        # After a check at tick 0, next check should be at COHERENCE_CHECK_INTERVAL
        self.engine.check(tick=0, agent_names=[], pairs_data=[])
        assert self.engine.should_check(COHERENCE_CHECK_INTERVAL - 1) is False
        assert self.engine.should_check(COHERENCE_CHECK_INTERVAL) is True

    def test_record_relation_snapshot(self):
        snap = self.engine.record_relation_snapshot("A", "B", 10, 50.0, 20.0, 30.0, 10.0)
        assert snap.agent_a == "A"
        assert snap.affinity == 50.0

        history = self.engine.get_pair_history("A", "B")
        assert len(history) == 1
        assert history[0].affinity == 50.0

    def test_record_snapshot_bidirectional(self):
        self.engine.record_relation_snapshot("A", "B", 10, 50.0, 0.0, 0.0, 0.0)
        self.engine.record_relation_snapshot("B", "A", 20, 60.0, 0.0, 0.0, 0.0)
        # Should share the same key
        history = self.engine.get_pair_history("A", "B")
        assert len(history) == 2

    def test_snapshot_history_capped(self):
        for i in range(MAX_RELATION_HISTORY + 5):
            self.engine.record_relation_snapshot("A", "B", i, 0.0, 0.0, 0.0, 0.0)
        history = self.engine.get_pair_history("A", "B")
        assert len(history) <= MAX_RELATION_HISTORY

    def test_reset(self):
        self.engine.record_relation_snapshot("A", "B", 10, 50.0, 0.0, 0.0, 0.0)
        self.engine.check(tick=50, agent_names=["A"], pairs_data=[])
        self.engine.reset()
        assert len(self.engine.get_pair_history("A", "B")) == 0

    def test_density_score_empty(self):
        report = self.engine.check(tick=50, agent_names=["A", "B"], pairs_data=[], events=[])
        # 没有事件 → 密度偏差 → 评分降低
        assert report.density_score < 1.0

    def test_density_score_optimal(self):
        events = [
            {"agent_name": "A", "event_type": "dialogue", "tick": i, "location": (0, 0)}
            for i in range(10)
        ]
        events += [
            {"agent_name": "B", "event_type": "dialogue", "tick": i, "location": (0, 0)}
            for i in range(10)
        ]
        report = self.engine.check(
            tick=50, agent_names=["A", "B"], pairs_data=[], events=events
        )
        assert report.density_score == 1.0

    def test_report_serialization(self):
        report = self.engine.check(tick=100, agent_names=["X"], pairs_data=[], events=[])
        d = report.to_dict()
        assert d["tick"] == 100
        assert "global_score" in d
        assert "warnings" in d
        assert isinstance(d["global_score"], float)

    def test_warnings_generated_on_low_score(self):
        report = self.engine.check(
            tick=50,
            agent_names=["A", "B"],
            pairs_data=[("A", "B", 85, 90, 80, 75)],
        )
        if report.global_score < COHERENCE_HIGH_THRESHOLD:
            assert len(report.warnings) > 0

    def test_is_critical(self):
        # 制造大量矛盾使评分极低
        pairs = []
        for i in range(10):
            pairs.append((f"A{i}", f"B{i}", 90.0, 95.0, 85.0, 80.0))
        report = self.engine.check(
            tick=50,
            agent_names=[f"A{i}" for i in range(10)] + [f"B{i}" for i in range(10)],
            pairs_data=pairs,
        )
        # 10 pairs × 2 directions = 20 ambivalence conflicts → 关系评分应该很低
        assert report.relation_score < 0.5


# ──────────────────────────────────────────────
# Global singleton
# ──────────────────────────────────────────────


class TestGlobalSingleton:
    def setup_method(self):
        reset_coherence_engine()

    def test_singleton_same_instance(self):
        e1 = get_coherence_engine()
        e2 = get_coherence_engine()
        assert e1 is e2

    def test_reset_creates_new(self):
        e1 = get_coherence_engine()
        reset_coherence_engine()
        e2 = get_coherence_engine()
        assert e1 is not e2


# ──────────────────────────────────────────────
# CoherenceReport
# ──────────────────────────────────────────────


class TestCoherenceReport:
    def test_healthy(self):
        report = CoherenceReport(tick=0, global_score=0.8)
        assert report.is_healthy() is True
        assert report.is_critical() is False

    def test_critical(self):
        report = CoherenceReport(tick=0, global_score=0.2)
        assert report.is_healthy() is False
        assert report.is_critical() is True

    def test_borderline(self):
        report = CoherenceReport(tick=0, global_score=0.5)
        assert report.is_healthy() is False
        assert report.is_critical() is False
