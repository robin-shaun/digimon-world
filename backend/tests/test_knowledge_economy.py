"""知识经济测试 — KnowledgeItem / InventedSkill / KnowledgePool / TechTree / Singleton.

覆盖 KnowledgeItem 创建(工厂方法)/引用(is_hot)/序列化、DOMAINS 常量、KnowledgePool
CRUD/传播/发明、TechTree/TechNode 解锁逻辑、KnowledgePropagation 传播概率、
单例模式等全部核心功能。
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from digimon_world.economy.knowledge_economy import (
    BASE_SPREAD_RATE,
    CIRCLE_MULTIPLIER,
    DOMAINS,
    HOT_CITATION_THRESHOLD,
    INVENTION_BASE_PROBABILITY,
    MAX_INVENTIONS_PER_TICK,
    MAX_KNOWLEDGE_PER_AGENT,
    InventedSkill,
    KnowledgeItem,
    KnowledgePool,
    KnowledgePropagation,
    TechNode,
    TechTree,
    get_knowledge_pool,
    reset_knowledge_pool,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Mock Helpers
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class MockAgent:
    """Minimal mock agent for testing knowledge economy.

    Attributes used by KnowledgePool._agent_eligible_domains():
        name, battle_victories, location (tuple of x,y)
    """

    name: str = "mock_agent"
    battle_victories: int = 0
    location: tuple[float, float] = (0.0, 0.0)


def make_agent(
    name: str = "agent",
    battle_victories: int = 0,
    location: tuple[float, float] = (0.0, 0.0),
) -> MockAgent:
    return MockAgent(name=name, battle_victories=battle_victories, location=location)


def _fresh_pool(seed: int = 42) -> KnowledgePool:
    """Create a fresh KnowledgePool with a fixed seed for deterministic tests."""
    return KnowledgePool(seed=seed)


# ═══════════════════════════════════════════════════════════════════════════════
# KnowledgeItem Tests (9)
# ═══════════════════════════════════════════════════════════════════════════════


class TestKnowledgeItem:
    """KnowledgeItem creation (factory), citation, is_hot, to_dict."""

    def test_create_minimal(self):
        """Factory create() with minimal fields returns valid item."""
        ki = KnowledgeItem.create(
            name="Fireball",
            domain="battle",
            description="A basic fireball.",
            inventor_id="agumon_1",
        )
        assert ki.id  # non-empty hash
        assert len(ki.id) == 16
        assert ki.name == "Fireball"
        assert ki.domain == "battle"
        assert ki.description == "A basic fireball."
        assert ki.inventor_id == "agumon_1"
        assert ki.citation_count == 0
        assert ki.citations == []
        assert ki.tags == []

    def test_create_with_tags(self):
        """Factory create() accepts optional tags."""
        ki = KnowledgeItem.create(
            name="IceShield", domain="battle",
            description="Frozen barrier.", inventor_id="gabu",
            tags=["ice", "defense"],
        )
        assert ki.tags == ["ice", "defense"]

    def test_create_deterministic_id(self):
        """Same inputs produce the same hash-based ID."""
        ki1 = KnowledgeItem.create("Test", "battle", "desc", "inv")
        ki2 = KnowledgeItem.create("Test", "battle", "desc", "inv")
        assert ki1.id == ki2.id

    def test_create_different_inputs_different_ids(self):
        """Different inputs produce different IDs."""
        ki1 = KnowledgeItem.create("SkillA", "battle", "desc", "inv")
        ki2 = KnowledgeItem.create("SkillB", "battle", "desc", "inv")
        assert ki1.id != ki2.id

    def test_add_citation_increments(self):
        """First citation from a new agent increments count."""
        ki = KnowledgeItem.create("Fire", "battle", "desc", "agumon")
        assert ki.add_citation("gabumon") is True
        assert ki.citation_count == 1
        assert ki.citations == ["gabumon"]

    def test_add_citation_self_citation_prevented(self):
        """Inventor cannot cite their own knowledge."""
        ki = KnowledgeItem.create("Self", "battle", "desc", "agumon")
        assert ki.add_citation("agumon") is False
        assert ki.citation_count == 0
        assert ki.citations == []

    def test_add_citation_duplicate_ignored(self):
        """Same agent citing twice only counts once."""
        ki = KnowledgeItem.create("Dup", "survival", "desc", "inv")
        assert ki.add_citation("patamon") is True
        assert ki.add_citation("patamon") is False
        assert ki.citation_count == 1

    def test_is_hot_property(self):
        """is_hot is True when citations >= HOT_CITATION_THRESHOLD."""
        ki = KnowledgeItem.create("Hot", "social", "desc", "inv")
        assert ki.is_hot is False
        for i in range(HOT_CITATION_THRESHOLD):
            ki.add_citation(f"agent_{i}")
        assert ki.is_hot is True

    def test_to_dict(self):
        """to_dict returns all expected keys."""
        ki = KnowledgeItem.create("Wind", "exploration", "A windy skill.", "birdmon")
        ki.add_citation("other")
        d = ki.to_dict()
        assert d["id"] == ki.id
        assert d["name"] == "Wind"
        assert d["domain"] == "exploration"
        assert d["description"] == "A windy skill."
        assert d["inventor_id"] == "birdmon"
        assert d["citation_count"] == 1
        assert d["citations"] == ["other"]
        assert d["tags"] == []
        assert d["is_hot"] is False
        assert "created_at" in d


# ═══════════════════════════════════════════════════════════════════════════════
# InventedSkill Tests (5)
# ═══════════════════════════════════════════════════════════════════════════════


class TestInventedSkill:
    """InventedSkill inherits KnowledgeItem, factory, to_dict, to_skill."""

    def test_inherits_from_knowledge_item(self):
        """InventedSkill is a subclass of KnowledgeItem."""
        assert issubclass(InventedSkill, KnowledgeItem)

    def test_instance_is_knowledge_item(self):
        """An InventedSkill instance passes isinstance check for KnowledgeItem."""
        skill = InventedSkill.create_skill(
            name="FirePunch", domain="battle", description="Fiery.",
            inventor_id="agumon", skill_type="FIRE", power=40, cost=15,
        )
        assert isinstance(skill, KnowledgeItem)
        assert isinstance(skill, InventedSkill)

    def test_default_values(self):
        """InventedSkill has sensible defaults."""
        skill = InventedSkill(
            id="is_default", name="Default", domain="battle",
            description="Default.", inventor_id="inv",
        )
        assert skill.skill_type == "PHYSICAL"
        assert skill.power == 30
        assert skill.cost == 10
        assert skill.prerequisites == []

    def test_create_skill_factory(self):
        """create_skill() factory produces a valid InventedSkill with unique ID."""
        skill = InventedSkill.create_skill(
            name="IceStorm", domain="battle", description="Frozen.",
            inventor_id="gabu", skill_type="ICE", power=50, cost=20,
            prerequisites=["ki_1", "ki_2"], tags=["ice"],
        )
        assert len(skill.id) == 16
        assert skill.name == "IceStorm"
        assert skill.domain == "battle"
        assert skill.skill_type == "ICE"
        assert skill.power == 50
        assert skill.cost == 20
        assert skill.prerequisites == ["ki_1", "ki_2"]
        assert skill.tags == ["ice"]

    def test_to_dict_includes_skill_fields(self):
        """to_dict of InventedSkill includes is_invented_skill=True and skill fields."""
        skill = InventedSkill.create_skill(
            name="Thunder", domain="battle", description="Zap.",
            inventor_id="elec", skill_type="SPECIAL", power=45, cost=18,
        )
        d = skill.to_dict()
        assert d["skill_type"] == "SPECIAL"
        assert d["power"] == 45
        assert d["cost"] == 18
        assert d["is_invented_skill"] is True
        assert d["prerequisites"] == []
        # Parent keys present
        assert d["name"] == "Thunder"
        assert d["domain"] == "battle"


# ═══════════════════════════════════════════════════════════════════════════════
# DOMAINS & Constants Tests (3)
# ═══════════════════════════════════════════════════════════════════════════════


class TestDomainsAndConstants:
    """DOMAINS list and module-level constants."""

    def test_domains_has_five_entries(self):
        """DOMAINS contains exactly 5 domain strings."""
        assert len(DOMAINS) == 5
        assert "battle" in DOMAINS
        assert "survival" in DOMAINS
        assert "social" in DOMAINS
        assert "exploration" in DOMAINS
        assert "crafting" in DOMAINS

    def test_constants_are_positive(self):
        """All rate/limit constants are reasonable positive values."""
        assert BASE_SPREAD_RATE > 0
        assert INVENTION_BASE_PROBABILITY > 0
        assert MAX_INVENTIONS_PER_TICK > 0
        assert MAX_KNOWLEDGE_PER_AGENT > 0
        assert HOT_CITATION_THRESHOLD > 0

    def test_circle_multiplier_ordering(self):
        """Inner > Middle > Outer spread multipliers."""
        assert CIRCLE_MULTIPLIER["inner"] > CIRCLE_MULTIPLIER["middle"]
        assert CIRCLE_MULTIPLIER["middle"] > CIRCLE_MULTIPLIER["outer"]


# ═══════════════════════════════════════════════════════════════════════════════
# KnowledgePool CRUD Tests (10)
# ═══════════════════════════════════════════════════════════════════════════════


class TestKnowledgePoolCRUD:
    """KnowledgePool add/get/query/agent_knowledge operations."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.pool = _fresh_pool(42)

    def _add(self, name: str, domain: str = "battle", inventor: str = "inv") -> KnowledgeItem:
        ki = KnowledgeItem.create(name, domain, f"Desc: {name}", inventor)
        self.pool.add_knowledge(ki)
        return ki

    def test_add_and_get(self):
        """add_knowledge stores item; get() retrieves it."""
        ki = self._add("TestItem")
        assert self.pool.get(ki.id) is ki

    def test_get_nonexistent(self):
        """get() returns None for unknown IDs."""
        assert self.pool.get("nonexistent_id") is None

    def test_get_by_domain(self):
        """get_by_domain filters by domain string."""
        self._add("B1", "battle")
        self._add("B2", "battle")
        self._add("S1", "survival")
        assert len(self.pool.get_by_domain("battle")) == 2
        assert len(self.pool.get_by_domain("survival")) == 1
        assert self.pool.get_by_domain("crafting") == []

    def test_get_hot(self):
        """get_hot returns items with citation_count >= threshold, sorted desc."""
        for i in range(5):
            ki = self._add(f"Hot{i}")
            for j in range(i + 3):  # all will be "hot" since threshold is 3
                ki.add_citation(f"c{j}")
        hot = self.pool.get_hot()
        assert len(hot) >= 1
        # Sorted descending
        counts = [h.citation_count for h in hot]
        assert counts == sorted(counts, reverse=True)

    def test_get_hot_respects_limit(self):
        """get_hot(n) limits results."""
        for i in range(10):
            ki = self._add(f"H{i}")
            for j in range(5):
                ki.add_citation(f"c{j}")
        assert len(self.pool.get_hot(3)) <= 3

    def test_get_by_inventor(self):
        """get_by_inventor returns all items by a specific inventor."""
        self._add("I1", "battle", "agumon")
        self._add("I2", "social", "agumon")
        self._add("I3", "battle", "gabumon")
        assert len(self.pool.get_by_inventor("agumon")) == 2
        assert len(self.pool.get_by_inventor("gabumon")) == 1
        assert self.pool.get_by_inventor("nobody") == []

    def test_agent_knows(self):
        """agent_knows returns True/False correctly."""
        ki = self._add("AK", inventor="inventor_a")
        # Inventor automatically knows their own knowledge
        assert self.pool.agent_knows("inventor_a", ki.id) is True
        assert self.pool.agent_knows("stranger", ki.id) is False

    def test_agent_known_items(self):
        """agent_known_items returns items an agent has learned."""
        ki1 = self._add("AK1", inventor="inv1")
        ki2 = self._add("AK2", "crafting", "inv2")
        self.pool.agent_learn("learner", ki1.id)
        self.pool.agent_learn("learner", ki2.id)
        items = self.pool.agent_known_items("learner")
        assert len(items) == 2
        ids = {it.id for it in items}
        assert ki1.id in ids
        assert ki2.id in ids

    def test_agent_learn_capacity_limit(self):
        """agent_learn returns False when agent is at capacity."""
        ki = self._add("Cap")
        pool = _fresh_pool(99)
        pool.add_knowledge(ki)
        # Fill capacity
        for i in range(MAX_KNOWLEDGE_PER_AGENT):
            pool._agent_knowledge["full_agent"].add(f"fake_{i}")
        assert pool.agent_learn("full_agent", ki.id) is False

    def test_stats(self):
        """stats() returns a dict with expected keys."""
        self._add("S1", "battle")
        self._add("S2", "crafting")
        s = self.pool.stats()
        assert s["total_knowledge"] == 2
        assert "by_domain" in s
        assert s["by_domain"]["battle"] == 1
        assert s["by_domain"]["crafting"] == 1
        assert "tech_tree" in s


# ═══════════════════════════════════════════════════════════════════════════════
# KnowledgePool Propagation Tests (4)
# ═══════════════════════════════════════════════════════════════════════════════


class TestKnowledgePoolPropagation:
    """KnowledgePool.propagate() — knowledge spread via KnowledgePropagation."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.pool = _fresh_pool(42)

    def test_propagate_no_agents(self):
        """Propagation with no agents returns 0."""
        assert self.pool.propagate(0) == 0

    def test_propagate_single_agent(self):
        """Propagation needs at least 2 agents to spread."""
        ki = KnowledgeItem.create("Solo", "battle", "desc", "loner")
        self.pool.add_knowledge(ki)
        assert self.pool.propagate(0) == 0

    def test_propagate_with_two_agents(self):
        """With 2 agents, knowledge may spread probabilistically."""
        ki = KnowledgeItem.create("Share", "battle", "desc", "agent_a")
        self.pool.add_knowledge(ki)
        # Give it citations to boost probability
        for j in range(10):
            ki.add_citation(f"cit{j}")
        # Second agent needs to be in agent_knowledge too (as inventor)
        # We need the agent to be discoverable
        ki2 = KnowledgeItem.create("Other", "battle", "desc", "agent_b")
        self.pool.add_knowledge(ki2)
        # Both agents are now in the system
        result = self.pool.propagate(0)
        assert isinstance(result, int)
        assert result >= 0

    def test_propagate_returns_int(self):
        """propagate always returns an integer (spread count)."""
        ki = KnowledgeItem.create("P1", "battle", "desc", "a1")
        self.pool.add_knowledge(ki)
        ki2 = KnowledgeItem.create("P2", "battle", "desc", "a2")
        self.pool.add_knowledge(ki2)
        result = self.pool.propagate(5)
        assert isinstance(result, int)


# ═══════════════════════════════════════════════════════════════════════════════
# KnowledgePool Invention Tests (4)
# ═══════════════════════════════════════════════════════════════════════════════


class TestKnowledgePoolInventions:
    """KnowledgePool.check_inventions() — invention eligibility and generation."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.pool = _fresh_pool(42)

    def test_check_inventions_empty_agents(self):
        """No agents → no inventions."""
        assert self.pool.check_inventions([]) == []

    def test_check_inventions_battle_eligible(self):
        """Agent with ≥5 battle victories is eligible for battle domain."""
        agent = make_agent(name="fighter", battle_victories=10)
        inventions = self.pool.check_inventions([agent], current_tick=1)
        assert isinstance(inventions, list)
        for inv in inventions:
            assert isinstance(inv, InventedSkill)
            assert inv.inventor_id == "fighter"

    def test_check_inventions_respects_max_per_tick(self):
        """Invention count is capped at MAX_INVENTIONS_PER_TICK."""
        # Create many eligible agents
        agents = [make_agent(name=f"fighter_{i}", battle_victories=20) for i in range(10)]
        inventions = self.pool.check_inventions(agents, current_tick=1)
        assert len(inventions) <= MAX_INVENTIONS_PER_TICK

    def test_agent_eligible_domains_battle(self):
        """Agent with high battle victories gets battle + survival domains."""
        agent = make_agent(name="warrior", battle_victories=15)
        domains = self.pool._agent_eligible_domains(agent)
        assert "battle" in domains
        assert "survival" in domains  # always eligible


# ═══════════════════════════════════════════════════════════════════════════════
# TechNode Tests (5)
# ═══════════════════════════════════════════════════════════════════════════════


class TestTechNode:
    """TechNode creation, unlock, is_unlockable."""

    def test_default_creation(self):
        """Default TechNode has sensible values."""
        node = TechNode(id="tn_001", name="TestNode")
        assert node.id == "tn_001"
        assert node.name == "TestNode"
        assert node.domain == "general"
        assert node.description == ""
        assert node.prerequisite_node_ids == []
        assert node.required_citation_count == 0
        assert node.unlocked is False
        assert node.unlocked_at == -1

    def test_unlock_sets_state(self):
        """unlock() sets unlocked=True and records the tick."""
        node = TechNode(id="tn_u", name="UnlockMe")
        assert node.unlock(42) is True
        assert node.unlocked is True
        assert node.unlocked_at == 42

    def test_unlock_idempotent(self):
        """Unlocking twice returns False on second call."""
        node = TechNode(id="tn_i", name="Idem")
        assert node.unlock(10) is True
        assert node.unlock(20) is False
        assert node.unlocked_at == 10  # unchanged

    def test_is_unlockable_no_prereqs(self):
        """Node with no prerequisites is unlockable with sufficient citations."""
        node = TechNode(id="tn_np", name="NoPrereq", required_citation_count=0)
        assert node.is_unlockable(set(), 0) is True
        assert node.is_unlockable(set(), 5) is True
        # Already unlocked → False
        node.unlock(0)
        assert node.is_unlockable(set(), 100) is False

    def test_is_unlockable_with_prereqs(self):
        """Node needs all prerequisites unlocked AND sufficient citations."""
        node = TechNode(
            id="tn_pr", name="WithPrereq",
            prerequisite_node_ids=["tn_a", "tn_b"],
            required_citation_count=10,
        )
        # Missing one prerequisite
        assert node.is_unlockable({"tn_a"}, 20) is False
        # Both prerequisites but insufficient citations
        assert node.is_unlockable({"tn_a", "tn_b"}, 5) is False
        # All conditions met
        assert node.is_unlockable({"tn_a", "tn_b", "tn_c"}, 15) is True


# ═══════════════════════════════════════════════════════════════════════════════
# TechTree Tests (5)
# ═══════════════════════════════════════════════════════════════════════════════


class TestTechTree:
    """TechTree initialization, unlock, linking, reset, stats."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.tree = TechTree()

    def test_initialized_with_10_nodes(self):
        """TechTree starts with 10 predefined nodes."""
        assert len(self.tree.nodes) == 10
        assert all(isinstance(n, TechNode) for n in self.tree.nodes.values())

    def test_get_node(self):
        """get_node returns the correct node or None."""
        node = self.tree.get_node("tech_battle_basic")
        assert node is not None
        assert node.name == "战斗基础"
        assert self.tree.get_node("nonexistent") is None

    def test_get_by_domain(self):
        """get_by_domain filters nodes by domain string."""
        battle_nodes = self.tree.get_by_domain("battle")
        assert len(battle_nodes) >= 1
        assert all(n.domain == "battle" for n in battle_nodes)

    def test_check_unlocks_tier1(self):
        """Tier 1 nodes (no prerequisites) unlock on first check."""
        pool = _fresh_pool(42)
        unlocked = self.tree.check_unlocks(pool, tick=1)
        tier1_ids = {n.id for n in unlocked}
        assert "tech_battle_basic" in tier1_ids
        assert "tech_survival_instinct" in tier1_ids
        assert "tech_social_bond" in tier1_ids
        assert "tech_terrain_awareness" in tier1_ids

    def test_reset_clears_all(self):
        """reset() clears all unlocks and knowledge mappings."""
        pool = _fresh_pool(42)
        self.tree.check_unlocks(pool, tick=1)
        assert len(self.tree.get_unlocked_nodes()) > 0

        self.tree.reset()
        assert self.tree.get_unlocked_nodes() == []
        for node in self.tree.nodes.values():
            assert node.unlocked is False
            assert node.unlocked_at == -1


# ═══════════════════════════════════════════════════════════════════════════════
# KnowledgePropagation Tests (3)
# ═══════════════════════════════════════════════════════════════════════════════


class TestKnowledgePropagation:
    """KnowledgePropagation probability computation and propagation."""

    def test_compute_spread_probability_inner(self):
        """Inner circle gives highest spread probability."""
        prop = KnowledgePropagation(seed=42)
        p = prop._compute_spread_probability("inner", citation_count=0)
        expected = BASE_SPREAD_RATE * CIRCLE_MULTIPLIER["inner"] * 1.0
        assert p == pytest.approx(expected)

    def test_compute_spread_probability_with_citations(self):
        """Higher citation count boosts probability."""
        prop = KnowledgePropagation(seed=42)
        p_low = prop._compute_spread_probability("inner", citation_count=0)
        p_high = prop._compute_spread_probability("inner", citation_count=10)
        assert p_high > p_low

    def test_propagate_one_same_agent(self):
        """Cannot propagate to self."""
        prop = KnowledgePropagation(seed=42)
        ki = KnowledgeItem.create("Test", "battle", "desc", "inv")
        assert prop.propagate_one("agent_a", "agent_a", ki) is False


# ═══════════════════════════════════════════════════════════════════════════════
# Singleton Tests (3)
# ═══════════════════════════════════════════════════════════════════════════════


class TestSingleton:
    """get_knowledge_pool / reset_knowledge_pool singleton pattern."""

    def teardown_method(self):
        reset_knowledge_pool()

    def test_get_returns_same_instance(self):
        """Multiple calls return the same object."""
        p1 = get_knowledge_pool()
        p2 = get_knowledge_pool()
        assert p1 is p2

    def test_reset_creates_new_instance(self):
        """After reset, a new instance is created."""
        p1 = get_knowledge_pool()
        reset_knowledge_pool()
        p2 = get_knowledge_pool()
        assert p1 is not p2

    def test_reset_clears_state(self):
        """After reset, the new pool is empty."""
        p1 = get_knowledge_pool()
        ki = KnowledgeItem.create("Test", "battle", "desc", "a")
        p1.add_knowledge(ki)
        assert len(p1.get_by_domain("battle")) >= 1

        reset_knowledge_pool()
        p2 = get_knowledge_pool()
        assert p2.get_by_domain("battle") == []


# ═══════════════════════════════════════════════════════════════════════════════
# Edge Case Tests (5)
# ═══════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Edge cases: empty pool, invalid operations, reset behavior."""

    def test_nonexistent_item_get(self):
        """get() returns None for non-existent item."""
        pool = _fresh_pool(42)
        assert pool.get("ghost_id") is None

    def test_agent_learn_nonexistent_knowledge(self):
        """agent_learn with non-existent knowledge returns False."""
        pool = _fresh_pool(42)
        assert pool.agent_learn("learner", "fake_id") is False

    def test_agent_learn_duplicate(self):
        """Learning already-known knowledge returns False."""
        pool = _fresh_pool(42)
        ki = KnowledgeItem.create("Dup", "battle", "desc", "inv")
        pool.add_knowledge(ki)
        assert pool.agent_learn("learner", ki.id) is True
        assert pool.agent_learn("learner", ki.id) is False

    def test_pool_reset_clears_everything(self):
        """reset() clears items, agent knowledge, inventor index, and tech tree."""
        pool = _fresh_pool(42)
        ki = KnowledgeItem.create("R", "battle", "desc", "a")
        pool.add_knowledge(ki)
        pool.agent_learn("learner", ki.id)
        pool.tech_tree.check_unlocks(pool, tick=1)

        assert len(pool.get_by_domain("battle")) == 1
        assert len(pool.agent_known_items("learner")) == 1

        pool.reset()
        assert pool.get_by_domain("battle") == []
        assert pool.agent_known_items("learner") == []
        assert pool.tech_tree.get_unlocked_nodes() == []

    def test_to_dict_roundtrip(self):
        """KnowledgePool.to_dict() produces serializable structure."""
        pool = _fresh_pool(42)
        ki = KnowledgeItem.create("Dict", "crafting", "desc", "inv")
        pool.add_knowledge(ki)
        d = pool.to_dict()
        assert "items" in d
        assert "agent_knowledge" in d
        assert "tech_tree" in d
        assert "stats" in d
        assert ki.id in d["items"]


# ═══════════════════════════════════════════════════════════════════════════════
# KnowledgePool linked with TechTree Tests (2)
# ═══════════════════════════════════════════════════════════════════════════════


class TestKnowledgePoolTechTreeIntegration:
    """Integration between KnowledgePool and its TechTree."""

    def test_tech_tree_property(self):
        """KnowledgePool.tech_tree returns the TechTree instance."""
        pool = _fresh_pool(42)
        assert isinstance(pool.tech_tree, TechTree)
        assert len(pool.tech_tree.nodes) == 10

    def test_check_tech_unlocks_delegates(self):
        """check_tech_unlocks() delegates to TechTree.check_unlocks()."""
        pool = _fresh_pool(42)
        unlocked = pool.check_tech_unlocks(tick=1)
        assert isinstance(unlocked, list)
        # Tier 1 nodes should unlock
        assert len(unlocked) >= 4
        for node in unlocked:
            assert isinstance(node, TechNode)
            assert node.unlocked is True
