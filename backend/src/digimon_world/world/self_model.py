"""
Agent Self-Model — Phase 28 核心模块
====================================

每个 Digimon agent 拥有一个持久的自我模型，追踪：
- identity: 基于实际世界交互计算的能力分数
- self_assessment: agent 对自身能力的信念（可能不准确）
- uncertainty: agent 对自我评估的不确定性
- trajectory: 自我认知随时间的变化轨迹
- improvement_goals: 自我改进目标

纯算法实现，无 LLM 调用。

集成点（本模块不实现，仅设计预留）:
- world/scheduler.py tick_once() → registry.step(agent, tick)
- API endpoint: /api/digimon/{name}/self → self_model.to_dict()
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────

SELF_MODEL_DIMS: tuple[str, ...] = (
    "combat_score",
    "social_score",
    "exploration_score",
    "knowledge_score",
)
"""自我模型的四个能力维度。"""

DIM_READABLE_NAMES: dict[str, str] = {
    "combat_score": "combat",
    "social_score": "social",
    "exploration_score": "exploration",
    "knowledge_score": "knowledge",
}
"""维度键 → 人类可读名称的映射。"""

DEFAULT_INITIAL_UNCERTAINTY: float = 0.8
"""初始不确定性 — 高值表示 agent 对自己的能力认知很模糊。"""

SELF_ASSESSMENT_JITTER: float = 0.15
"""self_assessment 初始时在 identity 基础上的随机偏移范围。"""

# 归一化上限
MAX_BATTLE_VICTORIES: float = 50.0
MAX_ATTACK: float = 200.0
MAX_DEFENSE: float = 150.0
MAX_RELATIONSHIPS: float = 20.0
MAX_DIALOGUES: float = 100.0
MAX_REGIONS: float = 10.0
MAX_DISTANCE: float = 1000.0
MAX_SKILLS: float = 10.0
MAX_INVENTIONS: float = 10.0

# 进化阶段乘数（用于 combat_score 加权）
EVOLUTION_STAGE_MULTIPLIERS: dict[str, float] = {
    "baby_i": 0.1,
    "baby_ii": 0.2,
    "rookie": 0.3,
    "champion": 0.5,
    "ultimate": 0.7,
    "mega": 1.0,
}

# 自我评估调整率（self_assessment 向 identity 收敛的速度）
SELF_ASSESSMENT_ADJUSTMENT_RATE: float = 0.2
"""每次评估时，self_assessment 向 identity 移动的比例。"""

# 不确定性衰减
UNCERTAINTY_DECAY_RATE: float = 0.05
"""基础不确定性衰减量（每次评估）。"""

MIN_UNCERTAINTY: float = 0.1
"""不确定性下限。"""

# 改进目标
DEFAULT_MAX_GOALS: int = 3
"""默认最大改进目标数。"""

GOAL_GAP_THRESHOLD: float = 0.15
"""self_assessment 低于目标差距超过此阈值才生成改进目标。"""

DEFAULT_IDENTITY_TARGET: float = 0.7
"""默认的改进目标值。"""

MAX_TRAJECTORY_LENGTH: int = 200
"""轨迹最大记录数，超出后裁剪为一半。"""


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """将值限制在 [lo, hi] 范围内。"""
    return max(lo, min(hi, value))


def _sigmoid_normalize(value: float, max_val: float) -> float:
    """简单线性归一化: value / max_val, clamped [0, 1]."""
    if max_val <= 0:
        return 0.0
    return _clamp(value / max_val)


def _jitter(base: float, amount: float = SELF_ASSESSMENT_JITTER) -> float:
    """在 base 基础上添加 ±amount 的均匀随机抖动。"""
    return _clamp(base + random.uniform(-amount, amount))


# ──────────────────────────────────────────────
# 数据结构
# ──────────────────────────────────────────────


@dataclass
class SelfAssessmentResult:
    """一次自我评估的完整结果。

    包含评估前后的 self_assessment 对比、实际计算分数、调整量和生成的目标。
    """

    agent_name: str
    """被评估的 agent 名称。"""

    tick: int
    """评估发生的世界 tick。"""

    actual_scores: dict[str, float]
    """从世界上下文计算的实际能力分数 (identity)。"""

    previous_self_assessment: dict[str, float]
    """评估前的自我评估值。"""

    new_self_assessment: dict[str, float]
    """评估后的自我评估值。"""

    uncertainty: dict[str, float]
    """评估后的不确定性。"""

    adjustments: dict[str, float]
    """各维度调整量 (new - previous)。"""

    new_goals: list[dict[str, Any]]
    """本次生成的新改进目标。"""

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。"""
        return {
            "agent_name": self.agent_name,
            "tick": self.tick,
            "actual_scores": {k: round(v, 4) for k, v in self.actual_scores.items()},
            "previous_self_assessment": {
                k: round(v, 4) for k, v in self.previous_self_assessment.items()
            },
            "new_self_assessment": {
                k: round(v, 4) for k, v in self.new_self_assessment.items()
            },
            "uncertainty": {k: round(v, 4) for k, v in self.uncertainty.items()},
            "adjustments": {k: round(v, 4) for k, v in self.adjustments.items()},
            "new_goals": self.new_goals,
        }


@dataclass
class SelfModel:
    """Agent 自我模型 — 每个 agent 拥有一个实例。

    追踪五方面:
    1. **identity** — 从世界状态计算的实际能力分数（"客观真实"）
    2. **self_assessment** — agent 对自身能力的信念（可能偏离 identity）
    3. **uncertainty** — agent 对自我评估的确定程度（高→不确定）
    4. **trajectory** — 自我认知随时间变化的快照序列
    5. **improvement_goals** — 当前自我改进目标

    初始时 self_assessment 在 identity 基础上随机偏移 ±0.15，
    不确定性设为 0.8（高不确定）。每次评估后二者逐步收敛。
    """

    agent_name: str
    """Agent 名称。"""

    identity: dict[str, float] = field(default_factory=lambda: {
        "combat_score": 0.0,
        "social_score": 0.0,
        "exploration_score": 0.0,
        "knowledge_score": 0.0,
    })
    """实际能力分数 [0, 1]，由 SelfEvaluator.compute_actual_scores 计算。"""

    self_assessment: dict[str, float] = field(default_factory=lambda: {
        "combat_score": 0.0,
        "social_score": 0.0,
        "exploration_score": 0.0,
        "knowledge_score": 0.0,
    })
    """Agent 对自身能力的信念 [0, 1]，初始在 identity 附近随机抖动。"""

    uncertainty: dict[str, float] = field(default_factory=lambda: {
        "combat_score": DEFAULT_INITIAL_UNCERTAINTY,
        "social_score": DEFAULT_INITIAL_UNCERTAINTY,
        "exploration_score": DEFAULT_INITIAL_UNCERTAINTY,
        "knowledge_score": DEFAULT_INITIAL_UNCERTAINTY,
    })
    """各维度不确定性 [0, 1]。高值表示 agent 对自己该维度能力"不确定"。"""

    trajectory: list[dict[str, Any]] = field(default_factory=list)
    """时间轨迹快照序列: [{tick, identity, self_assessment, uncertainty}, ...]."""

    improvement_goals: list[dict[str, Any]] = field(default_factory=list)
    """当前改进目标: [{dimension, current, target, reason, created_tick}, ...]."""

    last_introspection_tick: int = 0
    """上次自我评估发生的 tick 编号。"""

    introspection_interval: int = 10
    """自我评估间隔（tick 数）。"""

    def __post_init__(self) -> None:
        # 若 identity 全为零（首次创建），设置随机基线值
        id_all_zero = all(v == 0.0 for v in self.identity.values())
        if id_all_zero:
            for dim in SELF_MODEL_DIMS:
                self.identity[dim] = round(random.uniform(0.05, 0.3), 4)

        # 若 self_assessment 全为零（未初始化），从 identity 带抖动生成
        sa_all_zero = all(v == 0.0 for v in self.self_assessment.values())
        if sa_all_zero:
            for dim in SELF_MODEL_DIMS:
                self.self_assessment[dim] = round(_jitter(self.identity[dim]), 4)

    # ── 内省调度 ──

    def should_introspect(self, tick: int) -> bool:
        """判断是否应该在此 tick 执行自我评估。"""
        return (tick - self.last_introspection_tick) >= self.introspection_interval

    # ── 轨迹 ──

    def record_snapshot(self, tick: int) -> None:
        """记录当前状态的快照到 trajectory 中。"""
        self.trajectory.append({
            "tick": tick,
            "identity": dict(self.identity),
            "self_assessment": dict(self.self_assessment),
            "uncertainty": dict(self.uncertainty),
        })
        # 限制轨迹长度
        if len(self.trajectory) > MAX_TRAJECTORY_LENGTH:
            self.trajectory = self.trajectory[-MAX_TRAJECTORY_LENGTH // 2 :]

    # ── 序列化 ──

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典（最近 20 条轨迹、当前改进目标）。"""
        return {
            "agent_name": self.agent_name,
            "identity": {k: round(v, 4) for k, v in self.identity.items()},
            "self_assessment": {k: round(v, 4) for k, v in self.self_assessment.items()},
            "uncertainty": {k: round(v, 4) for k, v in self.uncertainty.items()},
            "trajectory": self.trajectory[-20:],
            "improvement_goals": self.improvement_goals,
            "last_introspection_tick": self.last_introspection_tick,
            "introspection_interval": self.introspection_interval,
        }


# ──────────────────────────────────────────────
# SelfEvaluator — 自我评估器
# ──────────────────────────────────────────────


class SelfEvaluator:
    """自我评估器 — 计算实际能力分数、调整自我评估、生成改进目标。

    纯算法实现，无 LLM 调用。提供三个核心能力:
    1. compute_actual_scores() — 从 agent_context 计算 4 维能力分数
    2. evaluate() — 执行完整评估流程（计算→调整→衰减→目标）
    3. generate_goals() — 生成改进目标

    evaluate() 接受灵活的 agent_context 字典，避免模块间循环依赖。
    """

    # ── 分数计算 ──

    @staticmethod
    def compute_actual_scores(agent_context: dict[str, Any]) -> dict[str, float]:
        """从 agent_context 计算 4 维实际能力分数。

        Args:
            agent_context: 可包含以下键的字典（全部可选，默认 0）:
                combat 相关:
                  - battle_victories: int — 战斗胜利数
                  - attack: int — 攻击力
                  - defense: int — 防御力
                  - evolution_stage: str — 进化阶段 (baby_i/rookie/champion/...)
                social 相关:
                  - relationship_count: int — 关系数量
                  - dialogue_count: int — 对话次数
                  - friendship_levels: list[float] — 友谊等级列表 [0-1]
                exploration 相关:
                  - regions_visited: int — 访问区域数
                  - distance_traveled: float — 移动总距离
                knowledge 相关:
                  - skills_count: int — 技能数
                  - inventions_count: int — 发明/创新数
                  - knowledge_citations: int — 知识引用数

        Returns:
            {combat_score, social_score, exploration_score, knowledge_score}
            全部在 [0, 1] 范围内。
        """
        combat_score = _compute_combat_score(agent_context)
        social_score = _compute_social_score(agent_context)
        exploration_score = _compute_exploration_score(agent_context)
        knowledge_score = _compute_knowledge_score(agent_context)

        return {
            "combat_score": round(combat_score, 4),
            "social_score": round(social_score, 4),
            "exploration_score": round(exploration_score, 4),
            "knowledge_score": round(knowledge_score, 4),
        }

    # ── 评估 ──

    @staticmethod
    def evaluate(
        agent_name: str,
        agent_context: dict[str, Any],
        self_model: SelfModel | None = None,
        tick: int = 0,
    ) -> SelfAssessmentResult:
        """执行一次完整自我评估。

        流程:
        1. 从 agent_context 计算实际能力分数
        2. 更新 self_model.identity
        3. 调整 self_assessment 向 identity 收敛
        4. 衰减不确定性（经验越多衰减越快）
        5. 生成改进目标（识别短板维度）
        6. 记录轨迹快照

        Args:
            agent_name: Agent 名称。
            agent_context: 同 compute_actual_scores。
            self_model: 现有 SelfModel（若 None 则创建新实例）。
            tick: 当前世界 tick。

        Returns:
            SelfAssessmentResult 包含完整的评估前后对比。
        """
        if self_model is None:
            self_model = SelfModel(agent_name=agent_name)

        previous_assessment = dict(self_model.self_assessment)

        # 1. 计算实际分数
        actual_scores = SelfEvaluator.compute_actual_scores(agent_context)

        # 2. 更新 identity
        for dim in SELF_MODEL_DIMS:
            self_model.identity[dim] = actual_scores[dim]

        # 3. 调整 self_assessment 向 identity 收敛
        adjustments: dict[str, float] = {}
        for dim in SELF_MODEL_DIMS:
            gap = self_model.identity[dim] - self_model.self_assessment[dim]
            adjustment = gap * SELF_ASSESSMENT_ADJUSTMENT_RATE
            self_model.self_assessment[dim] = round(
                _clamp(self_model.self_assessment[dim] + adjustment), 4
            )
            adjustments[dim] = round(adjustment, 4)

        # 4. 衰减不确定性
        # 经验总量影响衰减速度：经验越多衰减越快
        total_experience = sum(actual_scores.values())
        decay = UNCERTAINTY_DECAY_RATE * (1.0 + total_experience * 0.5)
        for dim in SELF_MODEL_DIMS:
            self_model.uncertainty[dim] = round(
                max(MIN_UNCERTAINTY, self_model.uncertainty[dim] - decay), 4
            )

        # 5. 生成改进目标
        new_goals = SelfEvaluator.generate_goals(self_model)

        # 6. 记录轨迹
        self_model.record_snapshot(tick)
        self_model.last_introspection_tick = tick

        return SelfAssessmentResult(
            agent_name=agent_name,
            tick=tick,
            actual_scores=actual_scores,
            previous_self_assessment=previous_assessment,
            new_self_assessment=dict(self_model.self_assessment),
            uncertainty=dict(self_model.uncertainty),
            adjustments=adjustments,
            new_goals=new_goals,
        )

    # ── 改进目标生成 ──

    @staticmethod
    def generate_goals(
        self_model: SelfModel,
        max_goals: int = DEFAULT_MAX_GOALS,
    ) -> list[dict[str, Any]]:
        """生成自我改进目标。

        扫描四个维度，识别 self_assessment 显著低于目标值（默认 0.7）的维度，
        按差距降序排列，取前 max_goals 个生成目标。

        Args:
            self_model: 当前自我模型。
            max_goals: 最多生成的目标数。

        Returns:
            [{dimension, current, target, reason, created_tick}, ...]
        """
        goals: list[dict[str, Any]] = []

        for dim in SELF_MODEL_DIMS:
            current = self_model.self_assessment.get(dim, 0.0)
            target = DEFAULT_IDENTITY_TARGET

            # 只有差距超过阈值才生成目标
            gap = target - current
            if gap < GOAL_GAP_THRESHOLD:
                continue

            readable = DIM_READABLE_NAMES.get(dim, dim)
            goal = {
                "dimension": readable,
                "current": round(current, 4),
                "target": round(target, 4),
                "reason": f"Improve {readable} from {current:.2f} to {target:.2f}",
                "created_tick": self_model.last_introspection_tick,
            }
            goals.append(goal)

        # 按差距降序排列
        goals.sort(key=lambda g: g["target"] - g["current"], reverse=True)

        # 截断到 max_goals
        goals = goals[:max_goals]

        self_model.improvement_goals = goals
        return goals


# ──────────────────────────────────────────────
# 维度分数计算（内部函数）
# ──────────────────────────────────────────────


def _compute_combat_score(ctx: dict[str, Any]) -> float:
    """计算 combat_score [0, 1].

    公式: (victories_norm × 0.4 + attack_norm × 0.3 + defense_norm × 0.3)
          × (0.5 + 0.5 × stage_multiplier)
    """
    battle_victories = int(ctx.get("battle_victories", 0))
    attack = int(ctx.get("attack", 0))
    defense = int(ctx.get("defense", 0))
    stage = str(ctx.get("evolution_stage", "rookie")).lower()

    stage_mult = EVOLUTION_STAGE_MULTIPLIERS.get(stage, 0.3)
    battle_norm = _sigmoid_normalize(battle_victories, MAX_BATTLE_VICTORIES)
    attack_norm = _sigmoid_normalize(attack, MAX_ATTACK)
    defense_norm = _sigmoid_normalize(defense, MAX_DEFENSE)

    combat_raw = battle_norm * 0.4 + attack_norm * 0.3 + defense_norm * 0.3
    return _clamp(combat_raw * (0.5 + 0.5 * stage_mult))


def _compute_social_score(ctx: dict[str, Any]) -> float:
    """计算 social_score [0, 1].

    公式: rel_norm × 0.35 + dial_norm × 0.35 + friendship_norm × 0.30
    """
    relationship_count = int(ctx.get("relationship_count", 0))
    dialogue_count = int(ctx.get("dialogue_count", 0))
    friendship_levels = ctx.get("friendship_levels", [])

    rel_norm = _sigmoid_normalize(relationship_count, MAX_RELATIONSHIPS)
    dial_norm = _sigmoid_normalize(dialogue_count, MAX_DIALOGUES)

    if friendship_levels:
        friendship_avg = sum(float(f) for f in friendship_levels) / len(friendship_levels)
        friendship_norm = _clamp(friendship_avg)
    else:
        friendship_norm = 0.0

    return _clamp(rel_norm * 0.35 + dial_norm * 0.35 + friendship_norm * 0.30)


def _compute_exploration_score(ctx: dict[str, Any]) -> float:
    """计算 exploration_score [0, 1].

    公式: regions_norm × 0.6 + distance_norm × 0.4
    """
    regions_visited = int(ctx.get("regions_visited", 0))
    distance_traveled = float(ctx.get("distance_traveled", 0.0))

    regions_norm = _sigmoid_normalize(regions_visited, MAX_REGIONS)
    distance_norm = _sigmoid_normalize(distance_traveled, MAX_DISTANCE)

    return _clamp(regions_norm * 0.6 + distance_norm * 0.4)


def _compute_knowledge_score(ctx: dict[str, Any]) -> float:
    """计算 knowledge_score [0, 1].

    公式: skills_norm × 0.35 + inventions_norm × 0.35 + citations_norm × 0.30
    """
    skills_count = int(ctx.get("skills_count", 0))
    inventions_count = int(ctx.get("inventions_count", 0))
    knowledge_citations = int(ctx.get("knowledge_citations", 0))

    skills_norm = _sigmoid_normalize(skills_count, MAX_SKILLS)
    inventions_norm = _sigmoid_normalize(inventions_count, MAX_INVENTIONS)
    citations_norm = _sigmoid_normalize(knowledge_citations, MAX_INVENTIONS)

    return _clamp(skills_norm * 0.35 + inventions_norm * 0.35 + citations_norm * 0.30)


# ──────────────────────────────────────────────
# SelfModelRegistry — 全局注册表
# ──────────────────────────────────────────────


@dataclass
class SelfModelRegistry:
    """自模型注册表 — 管理所有 agent 的 SelfModel。

    单例通过 get_self_model_registry() 获取。
    提供 step() 方法供 scheduler 在每 tick 调用。
    """

    _models: dict[str, SelfModel] = field(default_factory=dict)
    """agent_name → SelfModel 映射。"""

    _evaluator: SelfEvaluator = field(default_factory=SelfEvaluator)
    """共享的 SelfEvaluator 实例。"""

    # ── CRUD ──

    def get(self, agent_name: str) -> SelfModel | None:
        """获取 agent 的 SelfModel（不自动创建）。"""
        return self._models.get(agent_name)

    def get_or_create(self, agent_name: str) -> SelfModel:
        """获取或创建 agent 的 SelfModel。

        首次调用时为 agent 创建 SelfModel，identity 和 self_assessment
        使用随机基线值（随后会随评估而收敛）。
        """
        if agent_name not in self._models:
            self._models[agent_name] = SelfModel(agent_name=agent_name)
            logger.info(
                "SelfModelRegistry: 为 %s 创建自我模型 (identity=%s)",
                agent_name,
                self._models[agent_name].identity,
            )
        return self._models[agent_name]

    def set(self, agent_name: str, model: SelfModel) -> None:
        """手动设置 agent 的 SelfModel（如从持久化恢复）。"""
        self._models[agent_name] = model

    # ── tick step ──

    def step(
        self,
        agent_name: str,
        agent_context: dict[str, Any],
        tick: int,
        *,
        force: bool = False,
    ) -> SelfAssessmentResult | None:
        """执行一次自我评估 step。

        如果 agent 未到 introspect 间隔且 force=False，跳过评估返回 None。
        由 scheduler.tick_once() 在每 tick 对每个 agent 调用。

        Args:
            agent_name: Agent 名称。
            agent_context: 世界上下文（同 SelfEvaluator.compute_actual_scores）。
            tick: 当前世界 tick。
            force: 若 True，忽略 introspect 间隔强制评估。

        Returns:
            SelfAssessmentResult 或 None（若此次跳过评估）。
        """
        model = self.get_or_create(agent_name)

        if not force and not model.should_introspect(tick):
            return None

        result = self._evaluator.evaluate(
            agent_name=agent_name,
            agent_context=agent_context,
            self_model=model,
            tick=tick,
        )

        logger.debug(
            "SelfModelRegistry: %s tick=%d combat=%.2f→%.2f social=%.2f→%.2f",
            agent_name,
            tick,
            result.previous_self_assessment.get("combat_score", 0.0),
            result.new_self_assessment.get("combat_score", 0.0),
            result.previous_self_assessment.get("social_score", 0.0),
            result.new_self_assessment.get("social_score", 0.0),
        )

        return result

    # ── 查询 ──

    def list_agents(self) -> list[str]:
        """列出所有已注册的 agent 名称。"""
        return list(self._models.keys())

    def agent_count(self) -> int:
        """已注册 agent 数量。"""
        return len(self._models)

    # ── 重置 ──

    def reset(self) -> None:
        """重置所有内部状态（测试用）。"""
        self._models.clear()
        logger.debug("SelfModelRegistry: 已重置")

    # ── 序列化 ──

    def to_dict(self) -> dict[str, Any]:
        """序列化所有 agent 的自我模型。"""
        return {name: model.to_dict() for name, model in self._models.items()}


# ──────────────────────────────────────────────
# 全局单例
# ──────────────────────────────────────────────

_registry: SelfModelRegistry | None = None


def get_self_model_registry() -> SelfModelRegistry:
    """获取全局自模型注册表单例。

    首次调用时自动创建。用于 scheduler / API 端点访问所有 agent 的自我模型。

    Returns:
        SelfModelRegistry 单例。
    """
    global _registry
    if _registry is None:
        _registry = SelfModelRegistry()
    return _registry


def reset_self_model_registry() -> None:
    """重置全局自模型注册表（测试专用）。

    清空所有 agent 的 SelfModel，使下一次 get_self_model_registry() 创建全新实例。
    """
    global _registry
    _registry = None
