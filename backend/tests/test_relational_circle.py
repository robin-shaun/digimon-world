"""
Tests for relational_circle.py — 差序格局 (Differential Mode of Association).

Inspired by ACL 2026 paper arXiv:2606.23764
"""

from digimon_world.world.relational_circle import (
    AffectVector,
    RelationalCircle,
    RelationalDistance,
)
from digimon_world.world.relationships import (
    RelationshipTracker,
    RelationshipVector,
    reset_tracker,
)


class TestRelationalCircleEnum:
    def test_five_circles_exist(self):
        assert RelationalCircle.INTIMATE.value == 0
        assert RelationalCircle.FRIENDLY.value == 1
        assert RelationalCircle.ACQUAINTANCE.value == 2
        assert RelationalCircle.NEUTRAL.value == 3
        assert RelationalCircle.HOSTILE.value == 4

    def test_ordering(self):
        circles = list(RelationalCircle)
        assert circles == [
            RelationalCircle.INTIMATE,
            RelationalCircle.FRIENDLY,
            RelationalCircle.ACQUAINTANCE,
            RelationalCircle.NEUTRAL,
            RelationalCircle.HOSTILE,
        ]

    def test_label_cn(self):
        assert RelationalCircle.INTIMATE.label_cn() == "至交"
        assert RelationalCircle.HOSTILE.label_cn() == "敌对"

    def test_distance_value(self):
        assert RelationalCircle.INTIMATE.distance_value() == 0.0
        assert RelationalCircle.FRIENDLY.distance_value() == 0.25
        assert RelationalCircle.HOSTILE.distance_value() == 1.0

    def test_from_composite(self):
        assert RelationalCircle.from_composite(30) == RelationalCircle.INTIMATE
        assert RelationalCircle.from_composite(15) == RelationalCircle.FRIENDLY
        assert RelationalCircle.from_composite(5) == RelationalCircle.ACQUAINTANCE
        assert RelationalCircle.from_composite(0) == RelationalCircle.NEUTRAL
        assert RelationalCircle.from_composite(-10) == RelationalCircle.HOSTILE


class TestAffectVector:
    def test_default_neutral(self):
        av = AffectVector()
        assert av.trust == 0.5
        assert av.affection == 0.5
        assert av.respect == 0.5
        assert av.fear == 0.0

    def test_custom_init(self):
        av = AffectVector(trust=0.8, affection=0.6, respect=0.4, fear=0.2)
        assert av.trust == 0.8
        assert av.affection == 0.6
        assert av.respect == 0.4
        assert av.fear == 0.2

    def test_clamp_to_range(self):
        av = AffectVector(trust=1.5, affection=-0.5, respect=2.0, fear=-1.0)
        assert av.trust == 1.0
        assert av.affection == 0.0
        assert av.respect == 1.0
        assert av.fear == 0.0

    def test_to_dict(self):
        av = AffectVector(trust=0.7, affection=0.8, respect=0.9, fear=0.1)
        d = av.to_dict()
        assert d == {"trust": 0.7, "affection": 0.8, "respect": 0.9, "fear": 0.1}

    def test_neutral(self):
        av = AffectVector.neutral()
        assert av.trust == 0.5
        assert av.affection == 0.5
        assert av.respect == 0.5
        assert av.fear == 0.0

    def test_intensity(self):
        av = AffectVector(trust=1.0, affection=0.0, respect=0.0, fear=0.0)
        assert av.intensity() == 0.5  # sqrt((1+0+0+0)/4)

    def test_propagate_intimate_low_decay(self):
        """Emotions propagate strongly through intimate relationships."""
        source = AffectVector(trust=0.9, affection=0.8, respect=0.7, fear=0.1)
        result = source.propagate(rel_distance=0.1)  # very close
        assert result.trust > 0.75
        assert result.affection > 0.7

    def test_propagate_hostile_high_decay(self):
        """Emotions barely propagate through hostile relationships."""
        source = AffectVector(trust=0.9, affection=0.8, respect=0.7, fear=0.1)
        result = source.propagate(rel_distance=0.9)  # very distant
        assert result.trust < 0.2
        assert result.affection < 0.2

    def test_propagate_zero_distance(self):
        """Distance 0 (self) = no decay."""
        source = AffectVector(trust=1.0, affection=1.0, respect=1.0, fear=0.0)
        result = source.propagate(rel_distance=0.0)
        assert result.trust == 1.0

    def test_from_relationship_vector_intimate(self):
        rv = RelationshipVector(affinity=30, rivalry=0, respect=25, fear=0)
        av = AffectVector.from_relationship_vector(rv)
        assert av.trust > 0.6  # (30+100)/200 = 0.65
        assert av.affection > 0.6
        assert av.respect == 0.25  # 25/100

    def test_from_relationship_vector_hostile(self):
        rv = RelationshipVector(affinity=-50, rivalry=40, respect=10, fear=60)
        av = AffectVector.from_relationship_vector(rv)
        assert av.trust < 0.5  # (-50+100)/200 = 0.25
        assert av.fear == 0.6  # 60/100
        # rivalry penalty kicks in
        assert av.affection < av.trust  # affection < trust due to rivalry


class TestRelationalDistance:
    @staticmethod
    def _setup_tracker() -> RelationshipTracker:
        reset_tracker()
        tracker = RelationshipTracker()
        tracker._vectors[("Agumon", "Gabumon")] = RelationshipVector(
            affinity=40.0, rivalry=0.0, respect=30.0, fear=0.0
        )
        tracker._vectors[("Agumon", "Devimon")] = RelationshipVector(
            affinity=-50.0, rivalry=40.0, respect=10.0, fear=60.0
        )
        tracker._vectors[("Agumon", "Tentomon")] = RelationshipVector(
            affinity=5.0, rivalry=0.0, respect=3.0, fear=0.0
        )
        return tracker

    def test_intimate_classification(self):
        tracker = self._setup_tracker()
        rd = RelationalDistance("Agumon", tracker)
        assert rd.get_circle("Gabumon") == RelationalCircle.INTIMATE

    def test_hostile_classification(self):
        tracker = self._setup_tracker()
        rd = RelationalDistance("Agumon", tracker)
        assert rd.get_circle("Devimon") == RelationalCircle.HOSTILE

    def test_acquaintance_classification(self):
        tracker = self._setup_tracker()
        rd = RelationalDistance("Agumon", tracker)
        assert rd.get_circle("Tentomon") == RelationalCircle.ACQUAINTANCE

    def test_unknown_is_neutral(self):
        tracker = self._setup_tracker()
        rd = RelationalDistance("Agumon", tracker)
        assert rd.get_circle("UnknownDigimon") == RelationalCircle.NEUTRAL

    def test_self_is_intimate(self):
        tracker = self._setup_tracker()
        rd = RelationalDistance("Agumon", tracker)
        assert rd.get_circle("Agumon") == RelationalCircle.INTIMATE

    def test_distance_intimate(self):
        tracker = self._setup_tracker()
        rd = RelationalDistance("Agumon", tracker)
        d = rd.get_relation_distance("Gabumon")
        assert d < 0.25  # composite=22 → distance=(40-22)/80=0.225

    def test_distance_hostile(self):
        tracker = self._setup_tracker()
        rd = RelationalDistance("Agumon", tracker)
        d = rd.get_relation_distance("Devimon")
        assert d > 0.7

    def test_distance_self(self):
        tracker = self._setup_tracker()
        rd = RelationalDistance("Agumon", tracker)
        assert rd.get_relation_distance("Agumon") == 0.0

    def test_cooperation_threshold_intimate(self):
        tracker = self._setup_tracker()
        rd = RelationalDistance("Agumon", tracker)
        threshold = rd.compute_cooperation_threshold("Gabumon", task_risk=0.3)
        assert threshold > 0.7

    def test_cooperation_threshold_hostile(self):
        tracker = self._setup_tracker()
        rd = RelationalDistance("Agumon", tracker)
        threshold = rd.compute_cooperation_threshold("Devimon", task_risk=0.3)
        assert threshold < 0.2

    def test_cooperation_high_risk_reduces(self):
        tracker = self._setup_tracker()
        rd = RelationalDistance("Agumon", tracker)
        # Tentomon is ACQUAINTANCE — risk matters for acquaintances
        low_risk = rd.compute_cooperation_threshold("Tentomon", task_risk=0.1)
        high_risk = rd.compute_cooperation_threshold("Tentomon", task_risk=0.9)
        assert high_risk < low_risk

    def test_all_circles(self):
        tracker = self._setup_tracker()
        rd = RelationalDistance("Agumon", tracker)
        circles = rd.all_circles()
        assert circles["Gabumon"] == RelationalCircle.INTIMATE
        assert circles["Devimon"] == RelationalCircle.HOSTILE
        assert circles["Tentomon"] == RelationalCircle.ACQUAINTANCE

    def test_get_affect_vector(self):
        tracker = self._setup_tracker()
        rd = RelationalDistance("Agumon", tracker)
        av = rd.get_affect_vector("Gabumon")
        assert av.trust > 0.6
        assert av.respect == 0.3  # 30/100

    def test_classify_with_explicit_vector(self):
        tracker = self._setup_tracker()
        rd = RelationalDistance("Agumon", tracker)
        rv = RelationshipVector(affinity=40, rivalry=0, respect=30, fear=0)
        circle = rd.classify("AnyTarget", relationship_vector=rv)
        assert circle == RelationalCircle.INTIMATE

    def test_invalidate_cache(self):
        tracker = self._setup_tracker()
        rd = RelationalDistance("Agumon", tracker)
        rd.get_circle("Gabumon")  # populate cache
        rd.invalidate_cache("Gabumon")
        # Should still work (recompute)
        assert rd.get_circle("Gabumon") == RelationalCircle.INTIMATE
