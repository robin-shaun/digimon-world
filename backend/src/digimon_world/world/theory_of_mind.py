"""
Theory of Mind 模块 — Phase 28 核心模块
=======================================

每个 Digimon agent 维护对世界中其他 agent 的心智模型（MentalStateModel），
追踪其他 agent 的信念、欲望和意图。通过这些模型，agent 可以进行策略推理，
预测其他 agent 的行为。

纯算法实现，无 LLM 调用。

核心组件:
- MentalStateModel: 对另一个 agent 的信念/欲望/意图建模
- BeliefUpdate: 从观察中更新心智模型（贝叶斯风格级联更新）
- StrategicReasoning: 基于自我模型 + 心智模型进行策略推理
- TheoryOfMindRegistry: 全局注册表单例，管理所有 agent 的心智模型

集成点（本模块不实现，仅设计预留）:
- world/scheduler.py tick_once() → registry.step(agent, target, observation, tick)
- API endpoint: /api/digimon/{name}/theory_of_mind → registry.to_dict()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────

INITIAL_CONFIDENCE: float = 0.2
"""初始置信度 — 低值表示 agent 对其他 agent 的心智模型不确定。"""

MIN_CONFIDENCE: float = 0.01
"""置信度下限。"""

MAX_CONFIDENCE: float = 0.95
"""置信度上限 — 永远保留一点不确定性。"""

CONFIDENCE_DECAY_PER_TICK: float = 0.005
"""在没有新观察时，每 tick 置信度衰减量。"""

CONFIDENCE_DECAY_INTERVAL: int = 20
"""置信度衰减间隔（tick 数），仅在超过此间隔无观察时衰减。"""

INTENTION_LEARNING_RATE: float = 0.3
"""从观察更新意图的学习率（EMA 系数）。"""

DESIRE_LEARNING_RATE: float = 0.2
"""从意图反推欲望的学习率。"""

BELIEF_LEARNING_RATE: float = 0.15
"""从欲望贝叶斯更新信念的学习率。"""

OBSERVATION_CONFIDENCE_GAIN: float = 0.05
"""每次有效观察增加的置信度基础值。"""

MAX_MODELS_PER_AGENT: int = 50
"""单个 agent 最多维护的心智模型数量。"""

# ──────────────────────────────────────────────
# 映射表：action → intention → desire → belief
# ──────────────────────────────────────────────

ACTION_TO_INTENTION: dict[str, dict[str, float]] = {
    "move": {"move": 0.70, "explore": 0.30},
    "attack": {"attack": 0.80, "intimidate": 0.20},
    "talk": {"talk": 0.60, "socialize": 0.40},
    "gather": {"gather": 0.80, "explore": 0.20},
    "flee": {"flee": 0.70, "avoid_conflict": 0.30},
    "idle": {"rest": 0.70, "observe": 0.30},
    "trade": {"trade": 0.60, "socialize": 0.40},
    "heal": {"rest": 0.50, "survive": 0.50},
}
"""观察到的 action_type → 映射到意图类别及权重。"""

INTENTION_TO_DESIRE: dict[str, dict[str, float]] = {
    "move": {"explore": 0.40, "roam": 0.30, "wander": 0.30},
    "explore": {"explore": 0.70, "discover": 0.30},
    "attack": {"dominate": 0.60, "compete": 0.40},
    "intimidate": {"dominate": 0.50, "defend": 0.50},
    "talk": {"socialize": 0.60, "bond": 0.40},
    "socialize": {"socialize": 0.70, "bond": 0.30},
    "gather": {"survive": 0.60, "hoard": 0.40},
    "flee": {"avoid_danger": 0.70, "survive": 0.30},
    "avoid_conflict": {"avoid_danger": 0.60, "defend": 0.40},
    "rest": {"rest": 0.50, "conserve": 0.50},
    "observe": {"learn": 0.50, "assess": 0.50},
    "trade": {"socialize": 0.50, "survive": 0.50},
    "wander": {"explore": 0.50, "roam": 0.50},
}
"""推断的意图 → 映射到欲望类别及权重。"""

DESIRE_TO_BELIEF: dict[str, dict[str, float]] = {
    "explore": {"danger_level": -0.10, "world_unknown": 0.05},
    "discover": {"danger_level": -0.05, "world_unknown": 0.10},
    "dominate": {"others_weak": 0.10, "self_superior": 0.05},
    "compete": {"others_equal": 0.05, "resources_scarce": 0.05},
    "socialize": {"others_friendly": 0.10, "danger_level": -0.05},
    "bond": {"others_friendly": 0.05, "trust_others": 0.10},
    "survive": {"danger_level": 0.10, "resources_scarce": 0.05},
    "hoard": {"resources_scarce": 0.15, "others_selfish": 0.05},
    "avoid_danger": {"danger_level": 0.15, "world_hostile": 0.10},
    "defend": {"danger_level": 0.05, "others_threatening": 0.10},
    "rest": {"danger_level": -0.10, "environment_safe": 0.05},
    "conserve": {"resources_scarce": 0.05, "danger_level": 0.05},
    "learn": {"world_unknown": 0.10},
    "assess": {"uncertainty": 0.05},
    "roam": {"danger_level": -0.05, "world_unknown": 0.10},
}
"""推断的欲望 → 映射到信念调整方向（正=增加信念，负=减少信念）。"""

# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """将值限制在 [lo, hi] 范围内。"""
    return max(lo, min(hi, value))


def _ema_update(current: float, target: float, rate: float) -> float:
    """指数移动平均更新: current + rate * (target - current), clamped to [0, 1]."""
    return _clamp(current + rate * (target - current))


def _normalize_dict(d: dict[str, float]) -> dict[str, float]:
    """将字典值归一化使其和为 1（若总和为 0 则不改变）。"""
    total = sum(d.values())
    if total > 0:
        return {k: v / total for k, v in d.items()}
    return dict(d)


# ──────────────────────────────────────────────
# 数据结构
# ──────────────────────────────────────────────


@dataclass
class StrategyPrediction:
    """策略推理结果 — 基于自我模型与目标心智模型的预测。

    提供对目标的推荐行为策略及支撑分析数据。
    """

    agent_name: str
    """执行推理的 agent 名称。"""

    target_name: str
    """推理对象的目标 agent 名称。"""

    tick: int
    """推理发生的世界 tick。"""

    recommended_approach: str
    """推荐策略: engage_combat / avoid_combat / engage_social / avoid_social / neutral / observe。"""

    combat_advantage: float
    """战斗优势评估 [-1, 1]，正值表示我方占优，负值表示劣势。"""

    social_compatibility: float
    """社交兼容性 [0, 1]，高值表示社交互动有益。"""

    target_predicted_intentions: dict[str, float] = field(default_factory=dict)
    """预测目标最可能的意图。"""

    reasoning_confidence: float = 0.0
    """本次推理的置信度 [0, 1]。"""

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。"""
        return {
            "agent_name": self.agent_name,
            "target_name": self.target_name,
            "tick": self.tick,
            "recommended_approach": self.recommended_approach,
            "combat_advantage": round(self.combat_advantage, 4),
            "social_compatibility": round(self.social_compatibility, 4),
            "target_predicted_intentions": {
                k: round(v, 4) for k, v in self.target_predicted_intentions.items()
            },
            "reasoning_confidence": round(self.reasoning_confidence, 4),
        }


@dataclass
class MentalStateModel:
    """心智状态模型 — 对一个目标 agent 的信念/欲望/意图建模。

    每个 agent 维护一个 dict[target_name, MentalStateModel] 来追踪
    对其他 agent 的理解。模型从低置信度开始，随着观察增多逐渐精确。

    三维建模:
    1. **beliefs** — 我认为目标 agent 相信什么（如 danger_level, resources_scarce）
    2. **desires** — 我认为目标 agent 想要什么（如 explore, dominate, socialize）
    3. **intentions** — 我预测目标 agent 接下来会做什么（如 move, attack, talk）
    """

    target_name: str
    """此模型追踪的目标 agent 名称。"""

    beliefs: dict[str, float] = field(default_factory=dict)
    """目标 agent 对世界的信念 [0, 1]。默认包含 danger_level, others_friendly 等。"""

    desires: dict[str, float] = field(default_factory=dict)
    """目标 agent 的欲望强度 [0, 1]。如 explore, dominate, socialize, survive。"""

    intentions: dict[str, float] = field(default_factory=dict)
    """目标 agent 的预测意图强度 [0, 1]。如 move, attack, talk, flee。"""

    confidence: float = INITIAL_CONFIDENCE
    """对此模型的整体置信度 [0, 1]。"""

    last_updated_tick: int = 0
    """上次更新此模型的 tick 编号。"""

    observation_count: int = 0
    """累计观察次数。"""

    def __post_init__(self) -> None:
        """初始化默认的信念/欲望/意图基线值。

        所有值默认 0.0，表示尚未观察到任何信息。
        """
        # 确保 beliefs 至少包含常见维度
        default_beliefs = {
            "danger_level": 0.0,
            "others_friendly": 0.0,
            "resources_scarce": 0.0,
        }
        for k, v in default_beliefs.items():
            if k not in self.beliefs:
                self.beliefs[k] = v

        # 确保 desires 至少包含常见维度
        default_desires = {
            "explore": 0.0,
            "socialize": 0.0,
            "survive": 0.0,
        }
        for k, v in default_desires.items():
            if k not in self.desires:
                self.desires[k] = v

        # 确保 intentions 至少包含常见维度
        default_intentions = {
            "move": 0.0,
            "attack": 0.0,
            "talk": 0.0,
        }
        for k, v in default_intentions.items():
            if k not in self.intentions:
                self.intentions[k] = v

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。"""
        return {
            "target_name": self.target_name,
            "beliefs": {k: round(v, 4) for k, v in self.beliefs.items()},
            "desires": {k: round(v, 4) for k, v in self.desires.items()},
            "intentions": {k: round(v, 4) for k, v in self.intentions.items()},
            "confidence": round(self.confidence, 4),
            "last_updated_tick": self.last_updated_tick,
            "observation_count": self.observation_count,
        }


# ──────────────────────────────────────────────
# 信念更新器 — 从观察更新心智模型
# ──────────────────────────────────────────────


class BeliefUpdate:
    """信念更新器 — 从观察中更新 MentalStateModel。

    采用三级联更新机制:
    1. 观察 → 意图更新（直接）："观察到 X 移动" → 提高 intentions["move"]
    2. 意图 → 欲望更新（反向推理）："X 频繁移动" → 推断 X 渴望探索
    3. 欲望 → 信念更新（贝叶斯）: "X 渴望探索且去危险区域" → X 认为 danger 低

    纯算法实现，无 LLM 调用。
    """

    @staticmethod
    def update_from_observation(
        model: MentalStateModel,
        observation: dict[str, Any],
        tick: int,
    ) -> MentalStateModel:
        """从一次观察更新心智模型。

        Args:
            model: 目标 agent 的当前心智模型。
            observation: 观察数据字典，需包含:
                - action_type: str — 观察到的动作类型 (move/attack/talk/gather/flee/idle/trade/heal)
                - intensity: float (可选) — 动作强度 [0, 1]，默认 0.5
                - context: dict (可选) — 额外上下文（如 location, target_agent 等）
            tick: 当前世界 tick。

        Returns:
            更新后的 MentalStateModel（原地修改后返回同一实例）。
        """
        action_type = observation.get("action_type", "")
        if not action_type:
            logger.debug("BeliefUpdate: 空 action_type，返回未修改模型")
            return model

        intensity = float(observation.get("intensity", 0.5))
        intensity = _clamp(intensity)

        # 1️⃣ 观察 → 意图更新（直接映射）
        _update_intentions(model, action_type, intensity)

        # 2️⃣ 意图 → 欲望更新（反向推理）
        _update_desires_from_intentions(model, intensity)

        # 3️⃣ 欲望 → 信念更新（贝叶斯风格）
        _update_beliefs_from_desires(model, intensity)

        # 4️⃣ 置信度更新
        confidence_gain = OBSERVATION_CONFIDENCE_GAIN * (1.0 + intensity * 0.5)
        model.confidence = _clamp(
            model.confidence + confidence_gain,
            lo=MIN_CONFIDENCE,
            hi=MAX_CONFIDENCE,
        )

        # 5️⃣ 元数据更新
        model.last_updated_tick = tick
        model.observation_count += 1

        logger.debug(
            "BeliefUpdate: %s tick=%d action=%s intensity=%.2f count=%d conf=%.3f",
            model.target_name,
            tick,
            action_type,
            intensity,
            model.observation_count,
            model.confidence,
        )

        return model

    @staticmethod
    def decay_confidence(
        model: MentalStateModel,
        tick: int,
    ) -> MentalStateModel:
        """随时间衰减置信度（长时间未观察时调用）。

        如果距离上次更新超过 CONFIDENCE_DECAY_INTERVAL tick，置信度小幅衰减。
        置信度不会低于 MIN_CONFIDENCE。

        Args:
            model: 心智模型。
            tick: 当前世界 tick。

        Returns:
            原地修改后的 MentalStateModel。
        """
        ticks_since_update = tick - model.last_updated_tick
        if ticks_since_update >= CONFIDENCE_DECAY_INTERVAL:
            decay_cycles = ticks_since_update // CONFIDENCE_DECAY_INTERVAL
            model.confidence = _clamp(
                model.confidence - CONFIDENCE_DECAY_PER_TICK * decay_cycles,
                lo=MIN_CONFIDENCE,
            )
            logger.debug(
                "BeliefUpdate: %s 置信度衰减 ticks=%d→%.3f",
                model.target_name,
                ticks_since_update,
                model.confidence,
            )
        return model


# ──────────────────────────────────────────────
# 内部更新函数
# ──────────────────────────────────────────────


def _update_intentions(
    model: MentalStateModel,
    action_type: str,
    intensity: float,
) -> None:
    """第一步：从观察到的动作直接更新意图。

    使用 EMA 方式根据 ACTION_TO_INTENTION 映射更新意图值。
    历史观察的影响通过 EMA 平滑保留。
    """
    mapping = ACTION_TO_INTENTION.get(action_type)
    if mapping is None:
        logger.debug("BeliefUpdate: 未知 action_type=%s，跳过意图更新", action_type)
        return

    effective_rate = INTENTION_LEARNING_RATE * intensity

    for intention_key, weight in mapping.items():
        target_value = weight * intensity
        current = model.intentions.get(intention_key, 0.0)
        model.intentions[intention_key] = _ema_update(current, target_value, effective_rate)


def _update_desires_from_intentions(
    model: MentalStateModel,
    intensity: float,
) -> None:
    """第二步：从意图状态反向推理欲望。

    对当前非零意图，查询 INTENTION_TO_DESIRE 映射表进行 EMA 更新。
    此设计模拟 "若 X 频繁执行某意图，则 X 渴望某个目标" 的推理链。
    """
    effective_rate = DESIRE_LEARNING_RATE * intensity

    # 累积本次更新对所有 desire 维度的贡献
    desire_updates: dict[str, float] = {}

    for intention_key, intention_value in model.intentions.items():
        if intention_value <= 0.01:
            continue
        mapping = INTENTION_TO_DESIRE.get(intention_key)
        if mapping is None:
            continue

        # 意图越强，对欲望的推导越有力
        influence = intention_value * intensity
        for desire_key, weight in mapping.items():
            desire_updates[desire_key] = desire_updates.get(desire_key, 0.0) + weight * influence

    # 应用 EMA 更新
    for desire_key, target_value in desire_updates.items():
        target_value = _clamp(target_value)
        current = model.desires.get(desire_key, 0.0)
        model.desires[desire_key] = _ema_update(current, target_value, effective_rate)


def _update_beliefs_from_desires(
    model: MentalStateModel,
    intensity: float,
) -> None:
    """第三步：从欲望状态贝叶斯更新信念。

    对当前非零欲望，查询 DESIRE_TO_BELIEF 映射表进行增量调整。
    正值/负值表示信念应向哪个方向移动。
    """
    effective_rate = BELIEF_LEARNING_RATE * intensity

    for desire_key, desire_value in model.desires.items():
        if desire_value <= 0.01:
            continue
        mapping = DESIRE_TO_BELIEF.get(desire_key)
        if mapping is None:
            continue

        # 欲望越强，信念调整越大
        influence = desire_value * intensity
        for belief_key, delta in mapping.items():
            # delta 可为正（增加信念）或负（减少信念）
            target = _clamp(model.beliefs.get(belief_key, 0.0) + delta * influence)
            current = model.beliefs.get(belief_key, 0.0)
            model.beliefs[belief_key] = _ema_update(current, target, effective_rate)


# ──────────────────────────────────────────────
# 策略推理 — 基于自我模型 + 心智模型决策
# ──────────────────────────────────────────────


class StrategicReasoning:
    """策略推理器 — 基于自我模型和心智模型生成行为策略。

    比较我方能力与目标心智模型的预测，输出推荐策略。
    纯算法实现，无 LLM 调用。
    """

    @staticmethod
    def predict_strategy(
        agent_name: str,
        target_name: str,
        self_identity: dict[str, float],
        mental_model: MentalStateModel,
        tick: int = 0,
    ) -> StrategyPrediction:
        """基于自我模型和目标心智模型预测最优策略。

        分析流程:
        1. 评估战斗优劣势（我方 combat vs 目标攻击意图/支配欲望）
        2. 评估社交兼容性（我方 social vs 目标社交意图/欲望）
        3. 综合判断推荐策略

        Args:
            agent_name: 我方 agent 名称。
            target_name: 目标 agent 名称。
            self_identity: 我方的能力分数（来自 SelfModel.identity 或等价 dict）。
                需包含 combat_score, social_score, exploration_score, knowledge_score。
            mental_model: 目标 agent 的心智模型。
            tick: 当前世界 tick。

        Returns:
            StrategyPrediction 包含推荐策略和支撑数据。
        """
        my_combat = float(self_identity.get("combat_score", 0.0))
        my_social = float(self_identity.get("social_score", 0.0))

        # ── 战斗优势评估 ──
        # 目标的攻击意图 + 支配欲望 → 目标战斗倾向
        target_attack_intent = mental_model.intentions.get("attack", 0.0)
        target_intimidate_intent = mental_model.intentions.get("intimidate", 0.0)
        target_dominate_desire = mental_model.desires.get("dominate", 0.0)
        target_compete_desire = mental_model.desires.get("compete", 0.0)
        target_flee_intent = mental_model.intentions.get("flee", 0.0)
        target_avoid_danger_desire = mental_model.desires.get("avoid_danger", 0.0)

        # 目标战斗倾向综合评分
        target_combat_orientation = (
            target_attack_intent * 0.35
            + target_intimidate_intent * 0.15
            + target_dominate_desire * 0.30
            + target_compete_desire * 0.20
        )

        # 目标逃避倾向
        target_flee_orientation = (
            target_flee_intent * 0.50
            + target_avoid_danger_desire * 0.50
        )

        # 战斗优势 = 我方战斗 - 目标战斗倾向 + 目标逃避倾向
        combat_advantage_raw = my_combat - target_combat_orientation + target_flee_orientation * 0.5
        combat_advantage = _clamp(combat_advantage_raw, lo=-1.0, hi=1.0)

        # ── 社交兼容性评估 ──
        target_talk_intent = mental_model.intentions.get("talk", 0.0)
        target_socialize_intent = mental_model.intentions.get("socialize", 0.0)
        target_socialize_desire = mental_model.desires.get("socialize", 0.0)
        target_bond_desire = mental_model.desires.get("bond", 0.0)
        target_attack_intent_for_social = mental_model.intentions.get("attack", 0.0)

        # 目标社交开放性
        target_social_openness = (
            target_talk_intent * 0.30
            + target_socialize_intent * 0.20
            + target_socialize_desire * 0.30
            + target_bond_desire * 0.20
        )

        # 社交兼容性 = 我方社交 × 目标社交开放性（乘积模式：双方都需要兴趣）
        social_compatibility = _clamp(my_social * target_social_openness * 2.0)

        # 若目标有攻击意图，社交兼容性打折
        social_compatibility = social_compatibility * (1.0 - target_attack_intent_for_social * 0.5)

        # ── 推荐策略 ──
        recommended = _determine_approach(
            combat_advantage=combat_advantage,
            social_compatibility=social_compatibility,
            my_combat=my_combat,
            my_social=my_social,
            target_combat_orientation=target_combat_orientation,
            target_social_openness=target_social_openness,
        )

        # ── 目标预测意图（取 top 3 最高意图） ──
        predicted_intentions = dict(
            sorted(mental_model.intentions.items(), key=lambda x: x[1], reverse=True)[:3]
        )

        # ── 推理置信度 = 心智模型置信度 ──
        reasoning_confidence = mental_model.confidence

        return StrategyPrediction(
            agent_name=agent_name,
            target_name=target_name,
            tick=tick,
            recommended_approach=recommended,
            combat_advantage=round(combat_advantage, 4),
            social_compatibility=round(social_compatibility, 4),
            target_predicted_intentions=predicted_intentions,
            reasoning_confidence=round(reasoning_confidence, 4),
        )


def _determine_approach(
    combat_advantage: float,
    social_compatibility: float,
    my_combat: float,
    my_social: float,
    target_combat_orientation: float,
    target_social_openness: float,
) -> str:
    """根据战斗力/社交力对比决定推荐策略。

    决策逻辑:
    - 目标战斗倾向高且我方占优 → engage_combat
    - 目标战斗倾向高且我方劣势 → avoid_combat
    - 社交兼容性高 → engage_social
    - 目标社交开放性低且我方社交强 → avoid_social
    - 无明显倾向 → observe
    - 否则 → neutral
    """
    # 战斗场景：目标确实有战斗倾向
    if target_combat_orientation > 0.3:
        if combat_advantage > 0.2:
            return "engage_combat"
        elif combat_advantage < -0.2:
            return "avoid_combat"
        # 接近均势 → 观察
        return "observe"

    # 社交场景：目标有社交开放性
    if social_compatibility > 0.4:
        return "engage_social"
    elif target_social_openness < 0.1 and my_social > 0.5:
        return "avoid_social"

    # 目标无明显倾向 → 观察收集更多信息
    if target_combat_orientation < 0.1 and target_social_openness < 0.1:
        return "observe"

    return "neutral"


# ──────────────────────────────────────────────
# TheoryOfMindRegistry — 全局注册表
# ──────────────────────────────────────────────


@dataclass
class TheoryOfMindRegistry:
    """心智模型注册表 — 管理所有 agent 对其他 agent 的心智模型。

    数据结构: agent_name → {target_name → MentalStateModel}
    每个 agent 维护一个字典，键为目标 agent 名称，值为该目标的心智模型。

    单例通过 get_theory_of_mind_registry() 获取。
    提供 step() 方法供 scheduler 在每 tick 调用。
    """

    _models: dict[str, dict[str, MentalStateModel]] = field(default_factory=dict)
    """agent_name → {target_name → MentalStateModel} 两级映射。"""

    # ── CRUD ──

    def get(
        self,
        agent_name: str,
        target_name: str,
    ) -> MentalStateModel | None:
        """获取 agent 对 target 的心智模型（不自动创建）。"""
        targets = self._models.get(agent_name)
        if targets is None:
            return None
        return targets.get(target_name)

    def get_or_create(
        self,
        agent_name: str,
        target_name: str,
    ) -> MentalStateModel:
        """获取或创建 agent 对 target 的心智模型。

        首次调用时为该 (agent, target) 对创建新 MentalStateModel，
        置信度初始为 INITIAL_CONFIDENCE。

        同时校验 MAX_MODELS_PER_AGENT 上限：
        若已满且 target 不在其中，移除最久未更新的模型。
        """
        if agent_name not in self._models:
            self._models[agent_name] = {}

        targets = self._models[agent_name]

        if target_name not in targets:
            # 检查上限
            if len(targets) >= MAX_MODELS_PER_AGENT:
                _evict_oldest_model(targets)
            targets[target_name] = MentalStateModel(target_name=target_name)
            logger.info(
                "TheoryOfMindRegistry: %s → %s 创建心智模型",
                agent_name,
                target_name,
            )
        return targets[target_name]

    def set(
        self,
        agent_name: str,
        target_name: str,
        model: MentalStateModel,
    ) -> None:
        """手动设置心智模型（如从持久化恢复）。"""
        if agent_name not in self._models:
            self._models[agent_name] = {}
        self._models[agent_name][target_name] = model

    # ── tick step ──

    def step(
        self,
        agent_name: str,
        target_name: str,
        observation: dict[str, Any],
        tick: int,
        *,
        force: bool = False,
    ) -> MentalStateModel:
        """执行一次心智模型更新 step。

        由 scheduler.tick_once() 在每 tick 对每个 (agent, target) 观察对调用。

        Args:
            agent_name: 观察者 agent 名称。
            target_name: 被观察的目标 agent 名称。
            observation: 观察数据（同 BeliefUpdate.update_from_observation）。
            tick: 当前世界 tick。
            force: 若 True，即使无有效 action_type 也强制进行置信度衰减。

        Returns:
            更新后的 MentalStateModel。
        """
        model = self.get_or_create(agent_name, target_name)

        # 置信度衰减（基于时间间隔）
        BeliefUpdate.decay_confidence(model, tick)

        # 有有效观察时更新
        action_type = observation.get("action_type", "")
        if action_type:
            BeliefUpdate.update_from_observation(model, observation, tick)
        elif force:
            # 无观察但强制：仅进行衰减（已在上面完成）
            logger.debug(
                "TheoryOfMindRegistry: %s → %s force step (no observation)",
                agent_name,
                target_name,
            )

        return model

    # ── 查询 ──

    def get_all_models_for(self, agent_name: str) -> list[MentalStateModel]:
        """获取某个 agent 维护的所有心智模型列表。

        Args:
            agent_name: Agent 名称。

        Returns:
            MentalStateModel 列表（若 agent 不存在返回空列表）。
        """
        targets = self._models.get(agent_name)
        if targets is None:
            return []
        return list(targets.values())

    def get_target_names_for(self, agent_name: str) -> list[str]:
        """获取某个 agent 追踪的所有目标名称。"""
        targets = self._models.get(agent_name)
        if targets is None:
            return []
        return list(targets.keys())

    def list_agents(self) -> list[str]:
        """列出所有拥有心智模型的 agent 名称。"""
        return list(self._models.keys())

    def agent_count(self) -> int:
        """拥有心智模型的 agent 数量。"""
        return len(self._models)

    def model_count(self, agent_name: str) -> int:
        """某个 agent 维护的心智模型数量。"""
        targets = self._models.get(agent_name)
        if targets is None:
            return 0
        return len(targets)

    # ── 重置 ──

    def reset(self) -> None:
        """重置所有内部状态（测试用）。"""
        self._models.clear()
        logger.debug("TheoryOfMindRegistry: 已重置")

    # ── 序列化 ──

    def to_dict(self) -> dict[str, Any]:
        """序列化所有 agent 的心智模型。"""
        result: dict[str, dict[str, Any]] = {}
        for agent_name, targets in self._models.items():
            result[agent_name] = {
                target_name: model.to_dict()
                for target_name, model in targets.items()
            }
        return result


def _evict_oldest_model(targets: dict[str, MentalStateModel]) -> None:
    """移除最久未更新的心智模型（LRU 驱逐策略）。"""
    if not targets:
        return
    oldest = min(targets.items(), key=lambda item: item[1].last_updated_tick)
    logger.debug(
        "TheoryOfMindRegistry: 驱逐 %s (last_updated=%d)",
        oldest[0],
        oldest[1].last_updated_tick,
    )
    del targets[oldest[0]]


# ──────────────────────────────────────────────
# 全局单例
# ──────────────────────────────────────────────

_registry: TheoryOfMindRegistry | None = None


def get_theory_of_mind_registry() -> TheoryOfMindRegistry:
    """获取全局心智模型注册表单例。

    首次调用时自动创建。用于 scheduler / API 端点访问所有 agent 的心智模型。

    Returns:
        TheoryOfMindRegistry 单例。
    """
    global _registry
    if _registry is None:
        _registry = TheoryOfMindRegistry()
    return _registry


def reset_theory_of_mind_registry() -> None:
    """重置全局心智模型注册表（测试专用）。

    清空所有 agent 的 MentalStateModel，
    使下一次 get_theory_of_mind_registry() 创建全新实例。
    """
    global _registry
    _registry = None
