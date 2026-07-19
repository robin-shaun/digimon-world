"""
Knowledge Economy — Citation Economy / Technology Tree / Skill Invention
=======================================================================

Models a "citation economy" in the Digimon world where agents can invent
knowledge and skills, cite each other's discoveries, and knowledge propagates
through social networks.

Core Components:
1. KnowledgeItem — a piece of knowledge invented by an agent
2. TechNode — a node in the technology tree
3. SkillInvention — logic for agents inventing new skills
4. KnowledgePropagation — knowledge spreading through social networks
5. TechTree — world-level technology tree with pre-defined domains
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Domains for technology tree and knowledge items
DOMAINS: list[str] = ["combat", "healing", "exploration", "social", "crafting"]

# Citation threshold for a knowledge item to be considered "hot"
HOT_CITATION_THRESHOLD: int = 5

# Base invention probability (per attempt)
BASE_INVENTION_PROBABILITY: float = 0.05

# Maximum invention probability (capped)
MAX_INVENTION_PROBABILITY: float = 0.80

# Creativity multiplier from MBTI N (intuition) dimension
CREATIVITY_N_MULTIPLIER: float = 2.0

# Experience/stat weight in invention probability
EXPERIENCE_WEIGHT: float = 0.15

# Propagation base probability
BASE_PROPAGATION_PROBABILITY: float = 0.10

# Citation boost per citation count (log-scaled internally)
CITATION_BOOST_FACTOR: float = 0.5

# Openness factor (from MBTI N dimension) multiplier
OPENNESS_MULTIPLIER: float = 1.5

# Minimum required stats for skill composition
MIN_COMPOSITION_STATS: float = 0.3

# Number of predefined tech nodes per domain
NODES_PER_DOMAIN: int = 4

# Event types for world events
EVENT_KNOWLEDGE_INVENTED: str = "knowledge_invented"
EVENT_SKILL_COMPOSED: str = "skill_composed"
EVENT_KNOWLEDGE_PROPAGATED: str = "knowledge_propagated"
EVENT_KNOWLEDGE_HOT: str = "knowledge_hot"
EVENT_TECH_UNLOCKED: str = "tech_node_unlocked"

# ===========================================================================
# 1. KnowledgeItem — a piece of knowledge
# ===========================================================================


@dataclass
class KnowledgeItem:
    """A single piece of knowledge / skill in the citation economy.

    Attributes:
        id: Unique knowledge identifier.
        inventor_name: The agent who invented this.
        domain: One of combat, healing, exploration, social, crafting.
        title: Short descriptive title.
        summary: Longer description.
        citation_count: How many times this has been cited by others.
        cited_by: Names of agents who cited this.
        created_at: World tick when invented.
        prerequisites: Knowledge IDs needed to learn/invent this.
        is_skill: Whether this knowledge can be used as a skill.
    """

    id: str
    inventor_name: str
    domain: str = "general"
    title: str = ""
    summary: str = ""
    citation_count: int = 0
    cited_by: list[str] = field(default_factory=list)
    created_at: int = 0
    prerequisites: list[str] = field(default_factory=list)
    is_skill: bool = False

    def add_citation(self, agent_name: str) -> bool:
        """Record a citation from the given agent.

        Self-citation is prevented. Returns True if the citation was accepted.
        """
        if agent_name == self.inventor_name:
            return False
        if agent_name not in self.cited_by:
            self.cited_by.append(agent_name)
            self.citation_count = len(self.cited_by)
            return True
        return False

    @property
    def is_hot(self) -> bool:
        """Whether this knowledge is considered 'hot' (citation threshold met)."""
        return self.citation_count >= HOT_CITATION_THRESHOLD

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "inventor_name": self.inventor_name,
            "domain": self.domain,
            "title": self.title,
            "summary": self.summary,
            "citation_count": self.citation_count,
            "cited_by": list(self.cited_by),
            "created_at": self.created_at,
            "prerequisites": list(self.prerequisites),
            "is_skill": self.is_skill,
            "is_hot": self.is_hot,
        }


# ===========================================================================
# 2. TechNode — a node in the technology tree
# ===========================================================================


@dataclass
class TechNode:
    """A node in the technology tree.

    Unlocks when all prerequisite nodes have been unlocked and
    relevant knowledge has been accumulated.

    Attributes:
        id: Unique node identifier.
        name: Display name.
        domain: Technology domain.
        description: Human-readable description.
        prerequisites: Node IDs that must be unlocked first.
        knowledge_ids: Knowledge item IDs belonging to this node.
        unlocked: Whether this node is currently unlocked.
        unlocked_at: World tick when unlocked.
    """

    id: str
    name: str
    domain: str = "general"
    description: str = ""
    prerequisites: list[str] = field(default_factory=list)
    knowledge_ids: list[str] = field(default_factory=list)
    unlocked: bool = False
    unlocked_at: int = -1

    def unlock(self, tick: int) -> None:
        """Mark this node as unlocked at the given tick."""
        if not self.unlocked:
            self.unlocked = True
            self.unlocked_at = tick
            logger.info("TechNode %s (%s) unlocked at tick %d", self.id, self.name, tick)

    def is_unlockable(self, unlocked_node_ids: set[str]) -> bool:
        """Check if all prerequisites are satisfied.

        Args:
            unlocked_node_ids: Set of currently unlocked node IDs.

        Returns:
            True if all prerequisite nodes are unlocked (or there are none).
        """
        if self.unlocked:
            return False
        if not self.prerequisites:
            return True
        return set(self.prerequisites).issubset(unlocked_node_ids)


# ===========================================================================
# 3. SkillInvention — logic for inventing new skills
# ===========================================================================


class SkillInvention:
    """Handles the logic for agents inventing new knowledge and skills.

    Agents with high experience in a domain may invent new knowledge.
    Probability depends on:
    - Agent's experience/stats in the relevant domain
    - Whether prerequisites are met
    - Creativity factor (derived from MBTI N/S dimension)
    """

    def __init__(self, seed: int | None = None) -> None:
        import random

        self._rng = random.Random(seed)
        self._invention_counter: int = 0

    def _agent_domain_stat(self, agent: Any, domain: str) -> float:
        """Extract the agent's stat value for a given domain.

        Args:
            agent: Agent object with stats dict or attributes.
            domain: Domain name.

        Returns:
            Stat value normalized to [0, 1].
        """
        try:
            if hasattr(agent, "stats") and isinstance(agent.stats, dict):
                return float(agent.stats.get(domain, 0.0))
            if hasattr(agent, "experience") and isinstance(agent.experience, dict):
                return float(agent.experience.get(domain, 0.0))
            if hasattr(agent, domain):
                return float(getattr(agent, domain))
        except (TypeError, ValueError, AttributeError):
            pass
        return 0.0

    def _agent_creativity(self, agent: Any) -> float:
        """Derive creativity from MBTI N/S dimension.

        High N (intuition) = high creativity. Range [0, 1].
        """
        try:
            sn_val = 0.0
            if hasattr(agent, "sn"):
                sn_val = float(agent.sn)
            elif hasattr(agent, "personality") and hasattr(agent.personality, "sn"):
                sn_val = float(agent.personality.sn)
            elif hasattr(agent, "personality_profile") and hasattr(agent.personality_profile, "sn"):
                sn_val = float(agent.personality_profile.sn)

            # N = intuition = negative sn value in our convention (S positive, N negative)
            # creativity = -sn clamped to [0, 1] then scaled to [0, 1]
            creativity = max(0.0, min(1.0, -sn_val))
            return creativity
        except (TypeError, ValueError, AttributeError):
            pass
        return 0.5  # default moderate creativity

    def _agent_knows(self, agent: Any, knowledge_id: str) -> bool:
        """Check whether agent already knows a knowledge item."""
        try:
            if hasattr(agent, "known_knowledge_ids") and isinstance(agent.known_knowledge_ids, list):
                return knowledge_id in agent.known_knowledge_ids
        except (TypeError, AttributeError):
            pass
        return False

    def _agent_knows_all(self, agent: Any, knowledge_ids: list[str]) -> bool:
        """Check whether agent knows all of the given knowledge IDs."""
        return all(self._agent_knows(agent, kid) for kid in knowledge_ids)

    def _compute_invention_probability(
        self,
        agent: Any,
        domain_stat: float,
        creativity: float,
        prerequisites_met: bool,
    ) -> float:
        """Compute the probability of successful invention.

        Formula:
            p = BASE + (domain_stat * EXPERIENCE_WEIGHT) + (creativity * CREATIVITY_N_MULTIPLIER * 0.05)
            p is capped at MAX_INVENTION_PROBABILITY.
            If prerequisites are not met, p is halved.
        """
        p = BASE_INVENTION_PROBABILITY
        p += domain_stat * EXPERIENCE_WEIGHT
        p += creativity * CREATIVITY_N_MULTIPLIER * 0.05

        if not prerequisites_met:
            p *= 0.5

        return max(0.0, min(MAX_INVENTION_PROBABILITY, p))

    def attempt_invention(
        self,
        agent: Any,
        domain: str,
        knowledge_pool: dict[str, KnowledgeItem],
        tick: int = 0,
        world_context: dict[str, Any] | None = None,
    ) -> KnowledgeItem | None:
        """Attempt to invent new knowledge in the given domain.

        Args:
            agent: The agent attempting invention.
            domain: Domain to attempt invention in.
            knowledge_pool: Existing knowledge items (id -> KnowledgeItem).
            tick: Current world tick.
            world_context: Optional additional context.

        Returns:
            A new KnowledgeItem if successful, None otherwise.
        """
        domain_stat = self._agent_domain_stat(agent, domain)
        creativity = self._agent_creativity(agent)

        # Basic prerequisite check: does the agent have at least minimal domain stat?
        prerequisites_met = domain_stat >= 0.1

        probability = self._compute_invention_probability(agent, domain_stat, creativity, prerequisites_met)

        roll = self._rng.random()
        logger.debug(
            "SkillInvention attempt: agent=%s domain=%s stat=%.2f creativity=%.2f p=%.3f roll=%.3f",
            getattr(agent, "name", "?"),
            domain,
            domain_stat,
            creativity,
            probability,
            roll,
        )

        if roll > probability:
            return None

        # Success: create a new knowledge item
        self._invention_counter += 1
        agent_name = getattr(agent, "name", "unknown")

        knowledge_id = f"ki_{domain}_{self._invention_counter:04d}"
        title = f"{domain.title()} Discovery #{self._invention_counter}"
        summary = f"Novel {domain} knowledge invented by {agent_name}."

        item = KnowledgeItem(
            id=knowledge_id,
            inventor_name=agent_name,
            domain=domain,
            title=title,
            summary=summary,
            created_at=tick,
            is_skill=(creativity > 0.4),  # high creativity → skill
        )

        knowledge_pool[item.id] = item
        logger.info(
            "SkillInvention: %s invented %s (%s) in %s at tick %d",
            agent_name,
            item.id,
            item.title,
            domain,
            tick,
        )
        return item

    def compose_skills(
        self,
        agent: Any,
        knowledge_a: KnowledgeItem,
        knowledge_b: KnowledgeItem,
        knowledge_pool: dict[str, KnowledgeItem],
        tick: int = 0,
    ) -> KnowledgeItem | None:
        """Combine two existing knowledge items to create a novel one (synthesis).

        Args:
            agent: The agent performing composition.
            knowledge_a: First knowledge item.
            knowledge_b: Second knowledge item.
            knowledge_pool: Existing knowledge items (id -> KnowledgeItem).
            tick: Current world tick.

        Returns:
            A new synthesized KnowledgeItem if successful, None otherwise.
        """
        # Cannot compose a knowledge item with itself
        if knowledge_a.id == knowledge_b.id:
            return None

        # Both items must belong to the same domain for meaningful composition
        if knowledge_a.domain != knowledge_b.domain:
            return None

        creativity = self._agent_creativity(agent)
        domain = knowledge_a.domain

        # Probability: based on creativity and whether both items are known
        composition_prob = 0.05 + creativity * 0.15

        # Boost if agent knows both items
        knows_a = self._agent_knows(agent, knowledge_a.id)
        knows_b = self._agent_knows(agent, knowledge_b.id)
        if knows_a and knows_b:
            composition_prob += 0.10

        roll = self._rng.random()
        if roll > composition_prob:
            return None

        self._invention_counter += 1
        agent_name = getattr(agent, "name", "unknown")

        knowledge_id = f"ki_{domain}_comp_{self._invention_counter:04d}"
        title = f"Composite {domain.title()} #{self._invention_counter}"
        summary = f"Synthesized from '{knowledge_a.title}' and '{knowledge_b.title}' by {agent_name}."

        item = KnowledgeItem(
            id=knowledge_id,
            inventor_name=agent_name,
            domain=domain,
            title=title,
            summary=summary,
            created_at=tick,
            prerequisites=[knowledge_a.id, knowledge_b.id],
            is_skill=True,  # composed items are always skills
        )

        knowledge_pool[item.id] = item
        logger.info(
            "SkillInvention (compose): %s synthesized %s from %s+%s",
            agent_name,
            item.id,
            knowledge_a.id,
            knowledge_b.id,
        )
        return item

    def set_seed(self, seed: int) -> None:
        """Reset the RNG with a new seed."""
        import random

        self._rng = random.Random(seed)


# ===========================================================================
# 4. KnowledgePropagation — spreading through social networks
# ===========================================================================


@dataclass
class PropagationEvent:
    """Emitted when knowledge successfully propagates from source to target.

    Also emitted as a world event when a knowledge item becomes 'hot'.
    """

    event_type: str
    knowledge_id: str
    source_agent: str
    target_agent: str = ""
    tick: int = 0
    citation_count: int = 0
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()


class KnowledgePropagation:
    """Handles knowledge spreading through social networks.

    Higher citation counts and stronger relationships increase
    the probability of successful propagation.
    """

    def __init__(self, seed: int | None = None) -> None:
        import random

        self._rng = random.Random(seed)
        self._propagation_events: list[PropagationEvent] = []
        self._citation_graph: dict[str, set[str]] = defaultdict(set)

    # ---- Public API ----

    def propagate(
        self,
        source_agent: Any,
        target_agent: Any,
        knowledge_item: KnowledgeItem,
        relationship_strength: float,
        knowledge_pool: dict[str, KnowledgeItem],
        tick: int = 0,
    ) -> bool:
        """Attempt to propagate knowledge from source to target.

        Probability depends on:
        - Relationship strength between agents
        - Citation count of the knowledge (high-citation spreads faster)
        - Target agent's openness (MBTI N dimension)
        - Whether target already knows this knowledge

        Args:
            source_agent: The agent who knows the knowledge.
            target_agent: The agent to propagate to.
            knowledge_item: The knowledge item being propagated.
            relationship_strength: Relationship strength [0, 1].
            knowledge_pool: All knowledge items for citation tracking.
            tick: Current world tick.

        Returns:
            True if propagation succeeded, False otherwise.
        """
        # Don't propagate if target already knows
        if self._agent_knows(target_agent, knowledge_item.id):
            return False

        # Don't propagate to self
        source_name = getattr(source_agent, "name", "")
        target_name = getattr(target_agent, "name", "")
        if source_name == target_name:
            return False

        probability = self._compute_propagation_probability(target_agent, knowledge_item, relationship_strength)

        roll = self._rng.random()
        if roll > probability:
            return False

        # Success
        self._record_propagation(knowledge_item, source_name, target_name, tick, knowledge_pool)
        return True

    def citation_chain(self, knowledge_id: str, knowledge_pool: dict[str, KnowledgeItem]) -> list[KnowledgeItem]:
        """Get the citation tree rooted at this knowledge item.

        Traverses prerequisites recursively to find all ancestor knowledge items.

        Args:
            knowledge_id: Root knowledge item ID.
            knowledge_pool: All knowledge items.

        Returns:
            List of KnowledgeItems in the citation chain (preorder).
        """
        result: list[KnowledgeItem] = []
        visited: set[str] = set()
        self._traverse_chain(knowledge_id, knowledge_pool, result, visited)
        return result

    def get_events(self) -> list[PropagationEvent]:
        """Return all recorded propagation events."""
        return list(self._propagation_events)

    def get_citation_network(self) -> dict[str, set[str]]:
        """Get the citation graph as adjacency set."""
        return dict(self._citation_graph)

    def clear_events(self) -> None:
        """Clear all recorded events."""
        self._propagation_events.clear()
        self._citation_graph.clear()

    # ---- Helpers ----

    def _agent_openness(self, agent: Any) -> float:
        """Derive openness from MBTI N dimension. Higher N = more open.

        Returns value in [0, 1].
        """
        try:
            sn_val = 0.0
            if hasattr(agent, "sn"):
                sn_val = float(agent.sn)
            elif hasattr(agent, "personality") and hasattr(agent.personality, "sn"):
                sn_val = float(agent.personality.sn)
            elif hasattr(agent, "personality_profile") and hasattr(agent.personality_profile, "sn"):
                sn_val = float(agent.personality_profile.sn)

            openness = max(0.0, min(1.0, -sn_val))
            return openness
        except (TypeError, ValueError, AttributeError):
            pass
        return 0.5

    def _agent_knows(self, agent: Any, knowledge_id: str) -> bool:
        """Check whether agent already knows a knowledge item."""
        try:
            if hasattr(agent, "known_knowledge_ids") and isinstance(agent.known_knowledge_ids, list):
                return knowledge_id in agent.known_knowledge_ids
        except (TypeError, AttributeError):
            pass
        return False

    def _compute_propagation_probability(
        self,
        target_agent: Any,
        knowledge_item: KnowledgeItem,
        relationship_strength: float,
    ) -> float:
        """Compute propagation probability.

        Formula:
            p = BASE + rel_strength * 0.2
                + log(1 + citation_count) * CITATION_BOOST_FACTOR * 0.1
                + openness * OPENNESS_MULTIPLIER * 0.05
            p capped at 0.95.
        """
        import math

        p = BASE_PROPAGATION_PROBABILITY
        p += relationship_strength * 0.20
        p += math.log(1 + knowledge_item.citation_count) * CITATION_BOOST_FACTOR * 0.10
        p += self._agent_openness(target_agent) * OPENNESS_MULTIPLIER * 0.05

        return max(0.0, min(0.95, p))

    def _record_propagation(
        self,
        knowledge_item: KnowledgeItem,
        source_name: str,
        target_name: str,
        tick: int,
        knowledge_pool: dict[str, KnowledgeItem],
    ) -> None:
        """Record a successful propagation and add citation."""
        # Add citation from target to knowledge item
        knowledge_item.add_citation(target_name)

        # Track citation edge
        self._citation_graph.setdefault(target_name, set()).add(knowledge_item.id)

        # Record propagation event
        event = PropagationEvent(
            event_type=EVENT_KNOWLEDGE_PROPAGATED,
            knowledge_id=knowledge_item.id,
            source_agent=source_name,
            target_agent=target_name,
            tick=tick,
            citation_count=knowledge_item.citation_count,
        )
        self._propagation_events.append(event)

        # Emit hot event if threshold reached
        if knowledge_item.is_hot:
            hot_event = PropagationEvent(
                event_type=EVENT_KNOWLEDGE_HOT,
                knowledge_id=knowledge_item.id,
                source_agent=source_name,
                target_agent="",
                tick=tick,
                citation_count=knowledge_item.citation_count,
            )
            self._propagation_events.append(hot_event)
            logger.info(
                "KNOWLEDGE_HOT: %s reached %d citations",
                knowledge_item.id,
                knowledge_item.citation_count,
            )

    def _traverse_chain(
        self,
        knowledge_id: str,
        knowledge_pool: dict[str, KnowledgeItem],
        result: list[KnowledgeItem],
        visited: set[str],
    ) -> None:
        """Recursively traverse prerequisite chain (DFS, preorder)."""
        if knowledge_id in visited:
            return
        visited.add(knowledge_id)

        item = knowledge_pool.get(knowledge_id)
        if item is None:
            return

        result.append(item)
        for prereq_id in item.prerequisites:
            self._traverse_chain(prereq_id, knowledge_pool, result, visited)

    def set_seed(self, seed: int) -> None:
        """Reset the RNG with a new seed."""
        import random

        self._rng = random.Random(seed)


# ===========================================================================
# 5. TechTree — world-level technology tree
# ===========================================================================


# Predefined technology tree nodes across 5 domains
def _build_default_nodes() -> list[TechNode]:
    """Build the complete default tech tree with 5 domains × 4 nodes each."""
    nodes: list[TechNode] = []

    # --- combat domain ---
    nodes.extend(
        [
            TechNode(
                id="combat_basics",
                name="Basic Combat",
                domain="combat",
                description="Fundamental fighting techniques.",
            ),
            TechNode(
                id="combat_advanced",
                name="Advanced Combat",
                domain="combat",
                description="Intermediate combat maneuvers.",
                prerequisites=["combat_basics"],
            ),
            TechNode(
                id="combat_special",
                name="Special Attacks",
                domain="combat",
                description="Signature combat moves.",
                prerequisites=["combat_advanced"],
            ),
            TechNode(
                id="combat_mastery",
                name="Combat Mastery",
                domain="combat",
                description="Ultimate fighting prowess.",
                prerequisites=["combat_special", "combat_tactics"],
            ),
            TechNode(
                id="combat_tactics",
                name="Battle Tactics",
                domain="combat",
                description="Strategic combat planning.",
                prerequisites=["combat_advanced"],
            ),
        ]
    )

    # --- healing domain ---
    nodes.extend(
        [
            TechNode(
                id="heal_basics",
                name="Basic Healing",
                domain="healing",
                description="Simple recovery techniques.",
            ),
            TechNode(
                id="heal_advanced",
                name="Advanced Recovery",
                domain="healing",
                description="Enhanced healing methods.",
                prerequisites=["heal_basics"],
            ),
            TechNode(
                id="heal_restoration",
                name="Full Restoration",
                domain="healing",
                description="Complete health restoration.",
                prerequisites=["heal_advanced"],
            ),
            TechNode(
                id="heal_mastery",
                name="Healing Mastery",
                domain="healing",
                description="Master-level healing arts.",
                prerequisites=["heal_restoration"],
            ),
        ]
    )

    # --- exploration domain ---
    nodes.extend(
        [
            TechNode(
                id="explore_basics",
                name="Basic Navigation",
                domain="exploration",
                description="Fundamental orientation skills.",
            ),
            TechNode(
                id="explore_scouting",
                name="Advanced Scouting",
                domain="exploration",
                description="Enhanced exploration techniques.",
                prerequisites=["explore_basics"],
            ),
            TechNode(
                id="explore_mapping",
                name="Cartography",
                domain="exploration",
                description="Map-making and territory knowledge.",
                prerequisites=["explore_scouting"],
            ),
            TechNode(
                id="explore_mastery",
                name="Exploration Mastery",
                domain="exploration",
                description="Expert-level exploration.",
                prerequisites=["explore_mapping"],
            ),
        ]
    )

    # --- social domain ---
    nodes.extend(
        [
            TechNode(
                id="social_basics",
                name="Basic Communication",
                domain="social",
                description="Fundamental social interaction.",
            ),
            TechNode(
                id="social_diplomacy",
                name="Diplomacy",
                domain="social",
                description="Negotiation and alliance skills.",
                prerequisites=["social_basics"],
            ),
            TechNode(
                id="social_leadership",
                name="Leadership",
                domain="social",
                description="Guiding and inspiring others.",
                prerequisites=["social_diplomacy"],
            ),
            TechNode(
                id="social_mastery",
                name="Social Mastery",
                domain="social",
                description="Ultimate social influence.",
                prerequisites=["social_leadership", "social_networking"],
            ),
            TechNode(
                id="social_networking",
                name="Social Networking",
                domain="social",
                description="Building extensive social connections.",
                prerequisites=["social_basics"],
            ),
        ]
    )

    # --- crafting domain ---
    nodes.extend(
        [
            TechNode(
                id="craft_basics",
                name="Basic Crafting",
                domain="crafting",
                description="Simple item creation.",
            ),
            TechNode(
                id="craft_tools",
                name="Tool Making",
                domain="crafting",
                description="Creating useful tools.",
                prerequisites=["craft_basics"],
            ),
            TechNode(
                id="craft_advanced",
                name="Advanced Crafting",
                domain="crafting",
                description="Complex item fabrication.",
                prerequisites=["craft_tools"],
            ),
            TechNode(
                id="craft_mastery",
                name="Crafting Mastery",
                domain="crafting",
                description="Master-level creation arts.",
                prerequisites=["craft_advanced"],
            ),
        ]
    )

    return nodes


class TechTree:
    """World-level technology tree.

    Manages tech nodes and unlocks them as knowledge accumulates.
    """

    def __init__(self, nodes: list[TechNode] | None = None) -> None:
        """Initialize the tech tree.

        Args:
            nodes: Optional custom node list. If None, uses default 5-domain tree.
        """
        self._nodes: dict[str, TechNode] = {}
        if nodes is not None:
            for node in nodes:
                self._nodes[node.id] = node
        else:
            for node in _build_default_nodes():
                self._nodes[node.id] = node

    # ---- Node Management ----

    def add_node(self, node: TechNode) -> None:
        """Register a new tech node."""
        self._nodes[node.id] = node

    def get_node(self, node_id: str) -> TechNode | None:
        """Get a node by ID."""
        return self._nodes.get(node_id)

    def get_all_nodes(self) -> list[TechNode]:
        """Get all registered nodes."""
        return list(self._nodes.values())

    def get_nodes_by_domain(self, domain: str) -> list[TechNode]:
        """Get all nodes in a given domain."""
        return [n for n in self._nodes.values() if n.domain == domain]

    # ---- Unlock Logic ----

    def get_unlocked_node_ids(self) -> set[str]:
        """Get IDs of all unlocked nodes."""
        return {nid for nid, node in self._nodes.items() if node.unlocked}

    def get_unlocked_nodes(self) -> list[TechNode]:
        """Get all currently unlocked nodes."""
        return [node for node in self._nodes.values() if node.unlocked]

    def get_available_unlocks(self) -> list[TechNode]:
        """Get nodes where all prerequisites are unlocked (but node itself is not)."""
        unlocked_ids = self.get_unlocked_node_ids()
        available: list[TechNode] = []
        for node in self._nodes.values():
            if node.is_unlockable(unlocked_ids):
                available.append(node)
        return available

    def check_unlock(self, knowledge_pool: dict[str, KnowledgeItem], tick: int = 0) -> list[TechNode]:
        """Check which nodes should unlock based on accumulated knowledge.

        A node unlocks if:
        1. All prerequisite nodes are unlocked.
        2. At least one knowledge item is associated with this node.

        Args:
            knowledge_pool: All known knowledge items.
            tick: Current world tick.

        Returns:
            List of newly unlocked TechNodes.
        """
        newly_unlocked: list[TechNode] = []
        unlocked_ids = self.get_unlocked_node_ids()

        # Iterate multiple times to handle cascading unlocks
        changed = True
        max_iterations = len(self._nodes) + 1
        iteration = 0

        while changed and iteration < max_iterations:
            changed = False
            iteration += 1
            for node in self._nodes.values():
                if node.unlocked:
                    continue
                if not node.is_unlockable(unlocked_ids):
                    continue
                # Node is unlockable — check if it has associated knowledge
                # If knowledge_ids is empty, unlock based on prerequisites alone
                # If knowledge_ids has entries, check if any exist in knowledge_pool
                if node.knowledge_ids:
                    has_knowledge = any(kid in knowledge_pool for kid in node.knowledge_ids)
                    if not has_knowledge:
                        continue

                node.unlock(tick)
                unlocked_ids.add(node.id)
                newly_unlocked.append(node)
                changed = True
                logger.info("TechTree: unlocked %s at tick %d", node.id, tick)

        return newly_unlocked

    def unlock_node(self, node_id: str, tick: int) -> bool:
        """Force-unlock a specific node.

        Args:
            node_id: Node to unlock.
            tick: Current world tick.

        Returns:
            True if the node was unlocked, False if already unlocked or not found.
        """
        node = self._nodes.get(node_id)
        if node is None:
            return False
        if node.unlocked:
            return False
        node.unlock(tick)
        return True

    def reset(self) -> None:
        """Reset all nodes to locked state."""
        for node in self._nodes.values():
            node.unlocked = False
            node.unlocked_at = -1

    # ---- Statistics ----

    def get_domain_progress(self) -> dict[str, dict[str, int]]:
        """Get unlock progress per domain.

        Returns:
            {domain: {"unlocked": N, "total": M}, ...}
        """
        progress: dict[str, dict[str, int]] = {}
        for domain in DOMAINS:
            nodes = self.get_nodes_by_domain(domain)
            unlocked = sum(1 for n in nodes if n.unlocked)
            progress[domain] = {"unlocked": unlocked, "total": len(nodes)}
        return progress

    def get_unlock_chain(self, node_id: str) -> list[str]:
        """Get the linear prerequisite chain for a node.

        Args:
            node_id: The target node.

        Returns:
            Ordered list of prerequisite node IDs (from root to node).
        """
        result: list[str] = []

        def _collect_prereqs(nid: str, visited: set[str]) -> None:
            if nid in visited:
                return
            visited.add(nid)
            node = self._nodes.get(nid)
            if node is None:
                return
            for prereq_id in node.prerequisites:
                _collect_prereqs(prereq_id, visited)
            result.append(nid)

        _collect_prereqs(node_id, set())
        return result


# ===========================================================================
# Global singleton
# ===========================================================================

_tech_tree: TechTree | None = None
_skill_invention: SkillInvention | None = None
_knowledge_propagation: KnowledgePropagation | None = None


def get_tech_tree() -> TechTree:
    """Get the global TechTree singleton."""
    global _tech_tree
    if _tech_tree is None:
        _tech_tree = TechTree()
    return _tech_tree


def get_skill_invention() -> SkillInvention:
    """Get the global SkillInvention singleton."""
    global _skill_invention
    if _skill_invention is None:
        _skill_invention = SkillInvention()
    return _skill_invention


def get_knowledge_propagation() -> KnowledgePropagation:
    """Get the global KnowledgePropagation singleton."""
    global _knowledge_propagation
    if _knowledge_propagation is None:
        _knowledge_propagation = KnowledgePropagation()
    return _knowledge_propagation


def reset_knowledge_economy() -> None:
    """Reset all global singletons (for testing)."""
    global _tech_tree, _skill_invention, _knowledge_propagation
    _tech_tree = None
    _skill_invention = None
    _knowledge_propagation = None
