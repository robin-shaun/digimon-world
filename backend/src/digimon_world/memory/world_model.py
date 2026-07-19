"""
Self-Evolving World Model — Phase 20 核心模块
==============================================

基于 arXiv:2606.30639 "WorldEvolver: Self-Evolving World Models for Autonomous Agents"
框架实现。数码兽 agent 通过观察环境交互结果，逐渐建立对世界的因果理解。

三子系统:
1. EpisodicMemory — 情节记忆: 存储 (状态→动作→结果) 转换
2. SemanticMemory — 语义记忆: 从情节中提取启发式规则
3. SelectiveForesight — 选择性前瞻: 预测行动结果

主入口: WorldModel 协调所有子系统。
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────

MAX_EPISODES = 500
MAX_RULES = 50
DEFAULT_MIN_SUPPORT = 3
MIN_EPISODES_FOR_PREDICTION = 2
DEFAULT_RETRIEVE_K = 5

CATEGORICAL_STATE_FIELDS: tuple[str, ...] = (
    "region_id", "stage", "time_of_day", "weather",
)

NUMERIC_STATE_FIELDS: tuple[str, ...] = (
    "hp_pct", "nearby_agents_count",
)

NUMERIC_MAX_VALUES: dict[str, float] = {
    "hp_pct": 100.0,
    "nearby_agents_count": 20.0,
}

CATEGORICAL_WEIGHT = 0.5
NUMERIC_WEIGHT = 0.5


# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────


def _jaccard_categorical(state_a: dict[str, Any], state_b: dict[str, Any]) -> float:
    """两个状态在分类字段上的 Jaccard 相似度。"""
    matches = 0
    total = 0
    for key in CATEGORICAL_STATE_FIELDS:
        val_a = state_a.get(key)
        val_b = state_b.get(key)
        if val_a is not None and val_b is not None:
            total += 1
            if str(val_a).lower() == str(val_b).lower():
                matches += 1
    return matches / total if total > 0 else 0.0


def _normalized_euclidean(state_a: dict[str, Any], state_b: dict[str, Any]) -> float:
    """两个状态在数值字段上的归一化欧氏距离相似度。"""
    sum_sq = 0.0
    fields_compared = 0
    for key in NUMERIC_STATE_FIELDS:
        val_a = state_a.get(key)
        val_b = state_b.get(key)
        if val_a is None or val_b is None:
            continue
        try:
            max_val = NUMERIC_MAX_VALUES.get(key, 1.0)
            a_norm = float(val_a) / max_val
            b_norm = float(val_b) / max_val
            sum_sq += (a_norm - b_norm) ** 2
            fields_compared += 1
        except (ValueError, TypeError):
            continue
    if fields_compared == 0:
        return 0.0
    distance = math.sqrt(sum_sq)
    max_distance = math.sqrt(fields_compared)
    normalized_dist = distance / max_distance if max_distance > 0 else 0.0
    return 1.0 - normalized_dist


def state_similarity(state_a: dict[str, Any], state_b: dict[str, Any]) -> float:
    """综合状态相似度: Jaccard + 归一化欧氏的加权和 (0-1)。"""
    return CATEGORICAL_WEIGHT * _jaccard_categorical(state_a, state_b) + NUMERIC_WEIGHT * _normalized_euclidean(state_a, state_b)


def _action_similarity(action_a: str, action_b: str) -> float:
    """两个动作字符串的相似度（基于关键词重叠）。"""
    if action_a == action_b:
        return 1.0
    words_a = {w.lower() for w in re.findall(r"\w+", action_a) if len(w) >= 3}
    words_b = {w.lower() for w in re.findall(r"\w+", action_b) if len(w) >= 3}
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def _classify_action(action: str) -> str:
    """将动作文本归类到高级类别 (fight/move/talk/rest/observe/eat/evolve)。"""
    a = action.lower()
    for cat, kws in [
        ("fight", ["fight", "战斗", "battle", "攻击", "attack"]),
        ("move", ["move", "移动", "去", "走向", "travel", "go", "跑"]),
        ("talk", ["talk", "对话", "聊天", "speak", "social", "meet"]),
        ("rest", ["rest", "休息", "睡觉", "sleep", "wait"]),
        ("observe", ["观察", "巡视", "explore", "探索", "look"]),
        ("eat", ["吃", "eat", "觅食", "forage"]),
        ("evolve", ["进化", "evolv"]),
    ]:
        if any(kw in a for kw in kws):
            return cat
    return a[:20]


def _extract_actions_from_plan(plan_text: str) -> list[str]:
    """从计划文本中提取行动类别列表。"""
    plan_lower = plan_text.lower()
    actions: list[str] = []
    seen: set[str] = set()
    triggers = [
        ("去", "move"), ("移动", "move"), ("战斗", "fight"), ("攻击", "fight"),
        ("对话", "talk"), ("聊天", "talk"), ("遇见", "talk"),
        ("休息", "rest"), ("睡觉", "rest"), ("观察", "observe"), ("探索", "observe"),
        ("吃", "eat"), ("觅食", "eat"),
    ]
    for keyword, action_type in triggers:
        if keyword in plan_lower and action_type not in seen:
            actions.append(action_type)
            seen.add(action_type)
    return actions if actions else ["move"]


# ──────────────────────────────────────────────
# 数据结构
# ──────────────────────────────────────────────


@dataclass
class Episode:
    """一条情节记忆: agent 亲身经历的 (状态 → 动作 → 结果) 转换。"""
    state_snapshot: dict[str, Any]
    action: str
    outcome: dict[str, Any]
    tick_index: int
    confidence: float = 1.0
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_snapshot": self.state_snapshot, "action": self.action,
            "outcome": self.outcome, "tick_index": self.tick_index,
            "confidence": self.confidence, "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Episode:
        ts = data.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        return cls(
            state_snapshot=data.get("state_snapshot", {}),
            action=data.get("action", ""), outcome=data.get("outcome", {}),
            tick_index=data.get("tick_index", 0),
            confidence=data.get("confidence", 1.0),
            timestamp=ts if ts else datetime.utcnow(),
        )


@dataclass
class Rule:
    """一条语义规则: 从情节经验中提取的启发式知识。"""
    condition: dict[str, Any]
    conclusion: str
    confidence: float = 0.5
    source_episodes: int = 0
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition": self.condition, "conclusion": self.conclusion,
            "confidence": self.confidence, "source_episodes": self.source_episodes,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Rule:
        ts = data.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        return cls(
            condition=data.get("condition", {}),
            conclusion=data.get("conclusion", ""),
            confidence=data.get("confidence", 0.5),
            source_episodes=data.get("source_episodes", 0),
            timestamp=ts if ts else datetime.utcnow(),
        )

    def matches(self, state: dict[str, Any]) -> bool:
        """检查当前状态是否匹配此规则所有条件。"""
        for key, expected_val in self.condition.items():
            actual_val = state.get(key)
            if actual_val is None or str(actual_val).lower() != str(expected_val).lower():
                return False
        return True


@dataclass
class PredictionResult:
    """SelectiveForesight 的预测结果。"""
    predicted_outcome: dict[str, Any]
    confidence: float
    source: str
    supporting_episodes: int = 0
    supporting_rules: list[Rule] = field(default_factory=list)


# ──────────────────────────────────────────────
# 子系统 1: EpisodicMemory
# ──────────────────────────────────────────────


@dataclass
class EpisodicMemory:
    """情节记忆库 — 存储 agent 经历的具体交互记录。FIFO 驱逐。"""
    episodes: list[Episode] = field(default_factory=list)
    _max_episodes: int = MAX_EPISODES

    def add(self, state: dict[str, Any], action: str, outcome: dict[str, Any],
            tick: int, confidence: float = 1.0) -> Episode:
        ep = Episode(state_snapshot=dict(state), action=action,
                     outcome=dict(outcome), tick_index=tick, confidence=confidence)
        self.episodes.append(ep)
        while len(self.episodes) > self._max_episodes:
            self.episodes.pop(0)
        return ep

    def retrieve_similar(self, state: dict[str, Any], k: int = DEFAULT_RETRIEVE_K) -> list[Episode]:
        if not self.episodes:
            return []
        scored = [(state_similarity(state, ep.state_snapshot), ep) for ep in self.episodes]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [ep for sim, ep in scored[:k] if sim > 0.0]

    def count(self) -> int:
        return len(self.episodes)

    def recent(self, n: int = 50) -> list[Episode]:
        return sorted(self.episodes, key=lambda e: e.timestamp, reverse=True)[:n]

    def to_dict(self) -> dict[str, Any]:
        return {"episodes": [ep.to_dict() for ep in self.episodes], "_max_episodes": self._max_episodes}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EpisodicMemory:
        mem = cls(_max_episodes=data.get("_max_episodes", MAX_EPISODES))
        for ep_data in data.get("episodes", []):
            mem.episodes.append(Episode.from_dict(ep_data))
        return mem


# ──────────────────────────────────────────────
# 子系统 2: SemanticMemory
# ──────────────────────────────────────────────


@dataclass
class SemanticMemory:
    """语义记忆库 — 从情节中提取的启发式规则集合。"""
    rules: list[Rule] = field(default_factory=list)
    _max_rules: int = MAX_RULES

    def extract_rules(self, episodes: list[Episode], min_support: int = DEFAULT_MIN_SUPPORT) -> list[Rule]:
        if len(episodes) < min_support:
            return []
        pattern_counter: Counter = Counter()
        field_value_counter: Counter = Counter()

        for ep in episodes:
            state = ep.state_snapshot
            event_type = ep.outcome.get("event_type", "")
            if not event_type:
                continue
            for fld in CATEGORICAL_STATE_FIELDS:
                value = state.get(fld)
                if value is None:
                    continue
                val_str = str(value).lower()
                pattern_counter[(fld, val_str, event_type)] += 1
                field_value_counter[(fld, val_str)] += 1

        new_rules: list[Rule] = []
        for (fld, val_str, event_type), count in pattern_counter.items():
            if count < min_support:
                continue
            total = field_value_counter.get((fld, val_str), count)
            confidence = count / total if total > 0 else 0.0
            rule = Rule(
                condition={fld: val_str},
                conclusion=f"{event_type} more likely when {fld}={val_str}",
                confidence=round(confidence, 3), source_episodes=count,
            )
            new_rules.append(rule)

        self._merge_rules(new_rules)
        return new_rules

    def _merge_rules(self, new_rules: list[Rule]) -> None:
        existing: dict[tuple, int] = {}
        for i, rule in enumerate(self.rules):
            key = (*tuple(sorted(rule.condition.items())), rule.conclusion)
            existing[key] = i
        for new_rule in new_rules:
            key = (*tuple(sorted(new_rule.condition.items())), new_rule.conclusion)
            if key in existing:
                old = self.rules[existing[key]]
                if new_rule.confidence > old.confidence:
                    old.confidence = new_rule.confidence
                    old.source_episodes = new_rule.source_episodes
                    old.timestamp = datetime.utcnow()
                continue
            self.rules.append(new_rule)
        while len(self.rules) > self._max_rules:
            worst = min(self.rules, key=lambda r: r.confidence)
            self.rules.remove(worst)

    def match_rules(self, state: dict[str, Any]) -> list[Rule]:
        matched = [r for r in self.rules if r.matches(state)]
        matched.sort(key=lambda r: r.confidence, reverse=True)
        return matched

    def count(self) -> int:
        return len(self.rules)

    def to_dict(self) -> dict[str, Any]:
        return {"rules": [r.to_dict() for r in self.rules], "_max_rules": self._max_rules}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SemanticMemory:
        mem = cls(_max_rules=data.get("_max_rules", MAX_RULES))
        for r_data in data.get("rules", []):
            mem.rules.append(Rule.from_dict(r_data))
        return mem


# ──────────────────────────────────────────────
# 子系统 3: SelectiveForesight
# ──────────────────────────────────────────────


@dataclass
class SelectiveForesight:
    """选择性前瞻 — WorldEvolver 三级级联预测。"""

    def predict(self, episodic: EpisodicMemory, semantic: SemanticMemory,
                state: dict[str, Any], action: str, k: int = DEFAULT_RETRIEVE_K) -> PredictionResult:
        # Level 1: 情节匹配
        similar = episodic.retrieve_similar(state, k=k * 2)
        action_cat = _classify_action(action)
        action_matched = [ep for ep in similar if _classify_action(ep.action) == action_cat]

        if len(action_matched) >= MIN_EPISODES_FOR_PREDICTION:
            successes = sum(1 for ep in action_matched if ep.outcome.get("success", False))
            avg_hp = sum(ep.outcome.get("hp_change", 0) for ep in action_matched) / len(action_matched)
            avg_mood = sum(ep.outcome.get("mood_change", 0.0) for ep in action_matched) / len(action_matched)
            event_types: Counter = Counter()
            for ep in action_matched:
                event_types[str(ep.outcome.get("event_type", "unknown"))] += 1
            most_common = max(event_types, key=lambda k2: event_types[k2])
            conf = min(1.0, len(action_matched) / k) * (successes / max(1, len(action_matched)))
            return PredictionResult(
                predicted_outcome={
                    "success": successes > len(action_matched) / 2,
                    "hp_change": round(avg_hp), "mood_change": round(avg_mood, 2),
                    "event_type": most_common,
                    "description": f"基于 {len(action_matched)} 条相似经历",
                },
                confidence=round(conf, 3), source="episodic",
                supporting_episodes=len(action_matched),
            )

        # Level 2: 规则匹配
        matched_rules = semantic.match_rules(state)
        relevant = [r for r in matched_rules
                    if str(r.condition.get("action_category", "")).lower() == action_cat
                    or action_cat in r.conclusion.lower()]
        if relevant:
            best = relevant[0]
            return PredictionResult(
                predicted_outcome={
                    "success": best.confidence > 0.5, "hp_change": 0, "mood_change": 0.0,
                    "event_type": best.conclusion, "description": f"规则: {best.conclusion}",
                },
                confidence=round(best.confidence, 3), source="semantic",
                supporting_rules=[best],
            )

        # Level 3: Unknown
        return PredictionResult(
            predicted_outcome={"success": False, "hp_change": 0, "mood_change": 0.0,
                               "event_type": "unknown", "description": "无历史经验可供参考"},
            confidence=0.1, source="none",
        )

    def evaluate_plan(self, episodic: EpisodicMemory, semantic: SemanticMemory,
                      state: dict[str, Any], plan_text: str) -> dict[str, Any]:
        actions = _extract_actions_from_plan(plan_text)
        if not actions:
            return {"overall_confidence": 0.5, "predictions": [], "recommendation": "proceed"}

        predictions = []
        confidences = []
        for action in actions:
            pred = self.predict(episodic, semantic, state, action)
            predictions.append({
                "action": action, "predicted_outcome": pred.predicted_outcome,
                "confidence": pred.confidence, "source": pred.source,
            })
            confidences.append(pred.confidence)

        avg_conf = sum(confidences) / len(confidences) if confidences else 0.5
        if avg_conf >= 0.7:
            rec = "proceed"
        elif avg_conf >= 0.4:
            rec = "caution"
        else:
            rec = "reconsider"
        return {"overall_confidence": round(avg_conf, 3), "predictions": predictions, "recommendation": rec}


# ──────────────────────────────────────────────
# WorldModel — 主协调器
# ──────────────────────────────────────────────


@dataclass
class WorldModel:
    """自演化世界模型 — agent 对世界运作规律的认知。"""
    agent_name: str = "unknown"
    episodic: EpisodicMemory = field(default_factory=EpisodicMemory)
    semantic: SemanticMemory = field(default_factory=SemanticMemory)
    foresight: SelectiveForesight = field(default_factory=SelectiveForesight)
    _last_rule_extraction_tick: int = 0
    _rule_extraction_interval: int = 24
    _prediction_history: list[PredictionResult] = field(default_factory=list)
    _max_prediction_history: int = 100

    def observe(self, state: dict[str, Any], action: str,
                outcome: dict[str, Any], tick_index: int = 0) -> Episode:
        episode = self.episodic.add(state, action, outcome, tick_index)
        if tick_index - self._last_rule_extraction_tick >= self._rule_extraction_interval:
            self._last_rule_extraction_tick = tick_index
            recent = self.episodic.recent(n=50)
            self.semantic.extract_rules(recent)
        return episode

    def predict(self, state: dict[str, Any], action: str) -> PredictionResult:
        result = self.foresight.predict(self.episodic, self.semantic, state, action)
        self._prediction_history.append(result)
        while len(self._prediction_history) > self._max_prediction_history:
            self._prediction_history.pop(0)
        return result

    def evaluate_plan(self, state: dict[str, Any], plan_text: str) -> dict[str, Any]:
        return self.foresight.evaluate_plan(self.episodic, self.semantic, state, plan_text)

    def extract_rules(self, force: bool = False) -> int:
        if force:
            self._last_rule_extraction_tick = 0
        recent = self.episodic.recent(n=50)
        new = self.semantic.extract_rules(recent)
        return len(new)

    def stats(self) -> dict[str, Any]:
        recent_preds = self._prediction_history[-20:]
        avg_conf = sum(p.confidence for p in recent_preds) / len(recent_preds) if recent_preds else 0.0
        source_counts: dict[str, int] = {}
        for p in recent_preds:
            source_counts[p.source] = source_counts.get(p.source, 0) + 1
        return {
            "agent_name": self.agent_name,
            "total_episodes": self.episodic.count(),
            "total_rules": self.semantic.count(),
            "recent_predictions": len(recent_preds),
            "avg_confidence": round(avg_conf, 3),
            "prediction_sources": source_counts,
            "last_rule_extraction_tick": self._last_rule_extraction_tick,
        }

    def get_snapshot(self) -> dict[str, Any]:
        """返回世界模型快照，供 AgentInsightEngine 使用。

        Returns:
            {"episodes_count": int, "rules_count": int, "avg_confidence": float}
        """
        s = self.stats()
        return {
            "episodes_count": s.get("total_episodes", 0),
            "rules_count": s.get("total_rules", 0),
            "avg_confidence": s.get("avg_confidence", 0.0),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "episodes": self.episodic.to_dict(),
            "rules": self.semantic.to_dict(),
            "last_rule_extraction_tick": self._last_rule_extraction_tick,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorldModel:
        return cls(
            agent_name=data.get("agent_name", "unknown"),
            episodic=EpisodicMemory.from_dict(data.get("episodes", {})),
            semantic=SemanticMemory.from_dict(data.get("rules", {})),
            _last_rule_extraction_tick=data.get("last_rule_extraction_tick", 0),
        )
