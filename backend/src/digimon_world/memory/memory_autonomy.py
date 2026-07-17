"""
记忆自主规划系统 — Phase 18 核心模块
=====================================

Agent 对自己的记忆拥有自主权：
1. LLM 自评记忆重要性 — 用 LLM 替代固定规则算法
2. Ebbinghaus 遗忘曲线 — 记忆强度随时间指数衰减
3. 记忆复述机制 — 定期重访重要记忆，恢复强度
4. 记忆更新检测 — 世界状态变化时标记过期记忆

论文依据:
- arXiv:2606.27472 "Supersede: Memory-Update Gap in LLM Agents"
- arXiv:2605.30690 "ElasticMem: Latent Memory for LLM Agents"
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TYPE_CHECKING

from ..memory.memory_stream import MemoryNode

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────

# 遗忘曲线参数
# Ebbinghaus: R = e^(-t/S)
# S 越大，遗忘越慢
FORGETTING_STRENGTH_DEFAULT = 3600.0   # 默认 1 小时强度半衰期（秒）
FORGETTING_STRENGTH_MIN = 600.0        # 最快遗忘（10 分钟半衰）
FORGETTING_STRENGTH_MAX = 86400.0      # 最慢遗忘（24 小时半衰）

# 复述阈值：当记忆强度低于此值时触发复述
REHEARSAL_STRENGTH_THRESHOLD = 0.3

# 每步最多复述的记忆数
MAX_REHEARSAL_PER_STEP = 2

# 自评重要性用 LLM 提示词模板
IMPORTANCE_SELF_ASSESS_SYSTEM = """你是一只数码兽的记忆评估助手。你的任务是评估一条记忆对这只数码兽的重要性。

评分标准（1-10）：
- 10: 改变一生的重大事件（进化、挚友死亡、宿敌诞生）
- 8-9: 重要里程碑（激烈战斗胜利/失败、建立深厚羁绊）
- 6-7: 有意义的事件（新发现、有趣的邂逅）
- 4-5: 日常观察（移动、觅食、普通社交）
- 1-3: 琐碎小事（重复的日常、无意义的移动）

返回 JSON 格式: {"importance": <1-10>, "reason": "<一句话理由>", "keywords": ["k1","k2"]}"""


# ──────────────────────────────────────────────
# 数据结构
# ──────────────────────────────────────────────

@dataclass
class MemoryHealth:
    """一条记忆的健康状态。"""

    memory: MemoryNode
    strength: float = 1.0               # 当前记忆强度 (0-1)，受遗忘曲线影响
    created_at: datetime = field(default_factory=datetime.utcnow)  # 创建时间（用于遗忘计算）
    last_rehearsed: datetime | None = None  # 最后一次复述时间
    rehearsal_count: int = 0            # 复述次数
    stale: bool = False                 # 是否已被标记为过期
    stale_reason: str = ""              # 过期原因


@dataclass
class EbbinghausCurve:
    """Ebbinghaus 遗忘曲线模型。

    R(t) = e^(-t/S)

    其中:
    - R: 记忆保留率 (0-1)
    - t: 经过的时间（秒）
    - S: 记忆强度参数（越大遗忘越慢）
    """

    S: float = FORGETTING_STRENGTH_DEFAULT  # 记忆强度参数

    @classmethod
    def for_agent(cls, agent_name: str, personality_trait: str = "neutral") -> EbbinghausCurve:
        """根据数码兽个性返回不同的遗忘速率。

        勇敢的数码兽更注重战斗记忆，温和的注重社交记忆。
        这里先用全局参数，后续可针对不同记忆类型使用不同 S。
        """
        # 基于个性的遗忘速率
        trait_factors = {
            "brave": 1.2,       # 勇敢: 更关注重要事件，遗忘日常稍快
            "timid": 0.8,       # 胆小: 记住更多危险，遗忘慢
            "curious": 1.0,     # 好奇: 标准
            "lazy": 1.5,        # 懒惰: 不太在乎，遗忘快
            "aggressive": 1.1,  # 好斗: 记住对手
            "gentle": 0.9,      # 温和: 记住朋友
        }
        factor = trait_factors.get(personality_trait.lower(), 1.0)
        return cls(S=FORGETTING_STRENGTH_DEFAULT / factor)

    def retention(self, elapsed_seconds: float) -> float:
        """计算经过 t 秒后的记忆保留率。"""
        if elapsed_seconds <= 0:
            return 1.0
        return math.exp(-elapsed_seconds / self.S)

    def half_life_seconds(self) -> float:
        """半衰期（秒）。"""
        return self.S * math.log(2)


# ──────────────────────────────────────────────
# 自评重要性
# ──────────────────────────────────────────────

@dataclass
class ImportanceAssessor:
    """LLM 驱动的记忆重要性自我评估。

    替代 MemoryStream 中原有的固定重要性赋值，
    让数码兽用 LLM 自己判断一件事对自己有多重要。
    """

    _last_llm_check: float = 0.0  # 上次 LLM 调用时间戳

    def assess(
        self,
        description: str,
        agent_name: str,
        agent_personality: str = "neutral",
        memory_type: str = "observation",
    ) -> dict[str, Any]:
        """对一条记忆进行重要性自评。

        Returns:
            {"importance": int, "reason": str, "keywords": list[str]}
        """
        # 快速启发式先行评估，减少不必要的 LLM 调用
        heuristic_score = self._heuristic_assess(description, memory_type)
        if heuristic_score is not None:
            return {
                "importance": heuristic_score,
                "reason": "heuristic",
                "keywords": [],
            }

        # 需要 LLM 评估（批量为异步调用预留接口）
        return self._llm_assess_fallback(description, agent_name, agent_personality, memory_type)

    def _heuristic_assess(self, description: str, memory_type: str) -> int | None:
        """快速启发式评估。对明显的事件直接判断，减少 LLM 调用。"""
        desc_lower = description.lower()

        # 高重要性事件直接给高分（检查 event type 和 description）
        high_signals = [
            "进化", "evolv", "战斗胜利", "battle_victory", "击败", "defeat",
            "羁绊", "bond", "朋友", "友情", "敌人", "宿敌",
            "宝石", "徽章", "badge", "齿轮", "gear",
            "蛋", "egg", "孵化", "hatch",
            "near_death", "濒死", "threat", "威胁",
        ]
        for kw in high_signals:
            if kw.lower() in desc_lower or kw.lower() in memory_type.lower():
                return 8

        # 中等重要性
        mid_signals = [
            "战斗", "battle", "对话", "dialogue", "探索",
            "发现", "discover", "新区域", "new area",
            "遇到", "meet", "first_meet",
        ]
        for kw in mid_signals:
            if kw.lower() in desc_lower:
                return 6

        # 低重要性
        low_signals = [
            "移动", "move", "走", "跑", "飞", "游",
            "休息", "rest", "睡觉", "sleep",
            "ate", "吃饭", "进食", "moved",
        ]
        for kw in low_signals:
            if kw.lower() in desc_lower or kw.lower() in memory_type.lower():
                return 3

        # 无法启发式判断的，返回 None 走 LLM
        return None

    def _llm_assess_fallback(
        self,
        description: str,
        agent_name: str,
        agent_personality: str,
        memory_type: str,
    ) -> dict[str, Any]:
        """LLM fallback 评估（同步版，供非 async 使用）。"""
        # 本地简单评估
        desc_len = len(description)
        if desc_len > 80:
            return {"importance": 6, "reason": "详细描述", "keywords": []}
        elif desc_len > 30:
            return {"importance": 5, "reason": "中等描述", "keywords": []}
        else:
            return {"importance": 4, "reason": "简短描述", "keywords": []}

    async def assess_async(
        self,
        description: str,
        agent_name: str,
        agent_personality: str = "neutral",
        memory_type: str = "observation",
        llm_complete=None,
    ) -> dict[str, Any]:
        """异步 LLM 自评（使用 MiniMax Text-01）。"""
        heuristic_score = self._heuristic_assess(description, memory_type)
        if heuristic_score is not None:
            return {
                "importance": heuristic_score,
                "reason": "heuristic",
                "keywords": [],
            }

        if llm_complete is None:
            return self._llm_assess_fallback(description, agent_name, agent_personality, memory_type)

        try:
            prompt = f"""数码兽名称: {agent_name}
        性格: {agent_personality}
        记忆类型: {memory_type}
        记忆内容: {description}

        请评估这条记忆对{agent_name}的重要性（1-10）。"""

            result = await llm_complete(
                system_prompt=IMPORTANCE_SELF_ASSESS_SYSTEM,
                user_prompt=prompt,
                model="MiniMax-Text-01",
            )

            # 尝试解析 JSON
            import json

            try:
                parsed = json.loads(result.strip())
                importance = max(1, min(10, int(parsed.get("importance", 5))))
                return {
                    "importance": importance,
                    "reason": parsed.get("reason", "LLM assessed"),
                    "keywords": parsed.get("keywords", []),
                }
            except (json.JSONDecodeError, ValueError):
                return {"importance": 5, "reason": "LLM parse fallback", "keywords": []}

        except Exception as e:
            logger.warning(f"LLM importance assess failed: {e}")
            return {"importance": 5, "reason": f"LLM error: {e}", "keywords": []}


# ──────────────────────────────────────────────
# 遗忘曲线引擎
# ──────────────────────────────────────────────

@dataclass
class ForgettingEngine:
    """管理一个 agent 的所有记忆健康状态，驱动遗忘曲线。"""

    curve: EbbinghausCurve = field(default_factory=EbbinghausCurve)
    memory_health: dict[int, MemoryHealth] = field(default_factory=dict)  # node_id -> health

    def register(self, memory: MemoryNode) -> MemoryHealth:
        """注册一条新记忆，初始强度 1.0。"""
        if memory.node_id is None:
            raise ValueError("MemoryNode must have a node_id assigned")
        health = MemoryHealth(
            memory=memory,
            strength=1.0,
            created_at=datetime.utcnow(),
        )
        self.memory_health[memory.node_id] = health
        return health

    def get_strength(self, node_id: int) -> float:
        """获取记忆当前强度（自动应用遗忘衰减）。"""
        health = self.memory_health.get(node_id)
        if health is None:
            return 0.0

        if health.stale:
            return 0.0

        # 对于非复述过的记忆，只需用创建时间计算
        elapsed = (datetime.utcnow() - health.created_at).total_seconds()
        decayed = self.curve.retention(elapsed)

        # 如果有复述，用最后复述时间重新计算
        if health.last_rehearsed and health.rehearsal_count > 0:
            rehearsal_age = (datetime.utcnow() - health.last_rehearsed).total_seconds()
            decayed = self.curve.retention(rehearsal_age) * (1.0 + 0.05 * health.rehearsal_count)
            decayed = min(decayed, 1.0)

        health.strength = decayed
        return decayed

    def update_all_strengths(self) -> dict[str, int]:
        """批量更新所有记忆强度。返回统计信息。

        Returns: {"total": int, "weak": int (strength<0.3), "strong": int (strength>0.7)}
        """
        total = len(self.memory_health)
        weak = 0
        strong = 0

        for h in self.memory_health.values():
            nid = h.memory.node_id
            if nid is None:
                continue
            s = self.get_strength(nid)
            if s < 0.3:
                weak += 1
            if s > 0.7:
                strong += 1

        return {"total": total, "weak": weak, "strong": strong}

    def get_weak_memories(self, threshold: float = REHEARSAL_STRENGTH_THRESHOLD) -> list[MemoryHealth]:
        """获取所有强度低于阈值的记忆（候选复述）。"""
        weak = []
        for h in self.memory_health.values():
            nid = h.memory.node_id
            if nid is None:
                continue
            s = self.get_strength(nid)
            if 0 < s < threshold and not h.stale:
                weak.append(h)
        return weak

    def mark_stale(self, node_id: int, reason: str) -> None:
        """标记一条记忆为过期。"""
        health = self.memory_health.get(node_id)
        if health:
            health.stale = True
            health.stale_reason = reason
            health.strength = 0.0

    def diagnose(self) -> dict[str, Any]:
        """记忆健康诊断报告。"""
        stats = self.update_all_strengths()
        stale_count = sum(1 for h in self.memory_health.values() if h.stale)
        weak = self.get_weak_memories()

        return {
            "total_memories": stats["total"],
            "strong_count": stats["strong"],
            "weak_count": stats["weak"],
            "stale_count": stale_count,
            "strong_threshold": 0.7,
            "weak_threshold": 0.3,
            "forgetting_half_life_seconds": self.curve.half_life_seconds(),
            "top_weak": [
                {
                    "node_id": h.memory.node_id,
                    "description": h.memory.description[:60],
                    "strength": round(h.strength, 3),
                    "importance": h.memory.importance,
                }
                for h in sorted(weak, key=lambda x: x.strength)[:5]
            ],
        }


# ──────────────────────────────────────────────
# 记忆复述
# ──────────────────────────────────────────────

@dataclass
class MemoryRehearsal:
    """记忆复述机制：定期选取高重要性但衰减的记忆进行复述。

    复述原理（Ebbinghaus 实验）：
    - 每次主动回忆（复述）重置遗忘曲线
    - 多次复述后记忆更牢固（memory consolidation）
    """

    def select_for_rehearsal(
        self,
        engine: ForgettingEngine,
        max_count: int = MAX_REHEARSAL_PER_STEP,
    ) -> list[MemoryHealth]:
        """选择需要复述的记忆。

        策略：
        1. 从弱记忆中筛选高重要性（importance >= 7）
        2. 按 (importance × (1-strength)) 加权随机选取
        3. 最多 max_count 条
        """
        weak = engine.get_weak_memories()
        if not weak:
            return []

        # 筛高重要性
        high_imp_weak = [h for h in weak if h.memory.importance >= 7]
        if not high_imp_weak:
            # 退一步：选 importance >= 5 的
            high_imp_weak = [h for h in weak if h.memory.importance >= 5]

        if not high_imp_weak:
            return []

        # 加权随机选取
        weights = [h.memory.importance * (1 - h.strength) for h in high_imp_weak]
        total_weight = sum(weights)
        if total_weight == 0:
            return []

        selected = []
        remaining = list(high_imp_weak)
        for _ in range(min(max_count, len(remaining))):
            r = random.uniform(0, total_weight)
            cum = 0
            for i, h in enumerate(remaining):
                cum += weights[i]
                if cum >= r:
                    selected.append(h)
                    remaining.pop(i)
                    # 重新计算权重
                    weights = [remaining[j].memory.importance * (1 - remaining[j].strength) for j in range(len(remaining))]
                    total_weight = sum(weights)
                    break

        return selected

    def rehearse(self, health: MemoryHealth) -> None:
        """执行一次复述：重置遗忘曲线，增加复述计数。"""
        health.last_rehearsed = datetime.utcnow()
        health.rehearsal_count += 1
        health.strength = 1.0  # 完全恢复
        logger.debug(
            f"Rehearsed memory #{health.memory.node_id}: "
            f"count={health.rehearsal_count} "
            f"'{health.memory.description[:40]}...'"
        )


# ──────────────────────────────────────────────
# 记忆更新检测
# ──────────────────────────────────────────────

@dataclass
class MemoryUpdateDetector:
    """检测世界状态变化导致的过期记忆。

    Supersede 问题 (arXiv:2606.27472):
    - 当事实变化时，agent 是否使用最新记忆
    - 例如：进化后，"我是成长期"的记忆应该标记为过期
    """

    STALE_PATTERNS: dict[str, list[str]] = field(default_factory=lambda: {
        "evolution": [
            "我是成长期", "我是成熟期", "我是完全体",
            "还是成长期", "还是幼年期",
            "目前是.*期",
            r"当前阶段.*:",
        ],
        "location": [
            "我在文件岛", "我在无限山", "我在齿轮草原",
            "目前在.*区域",
            "离开了.*前往",
        ],
        "relationship": [
            "和.*是朋友", "与.*敌对", "与.*结盟",
            "信任.*",
            "讨厌.*",
        ],
        "health": [
            "受伤了", "正在恢复", "濒临死亡",
            "HP不足", "体力不支",
        ],
    })

    def detect_stale(
        self,
        health: MemoryHealth,
        state_change: dict[str, Any],
    ) -> tuple[bool, str]:
        """检测一条记忆是否因世界状态变化而过期。

        Args:
            health: 记忆健康状态
            state_change: 世界状态变化字典
                {"type": "evolution"|"location"|"relationship"|"health",
                 "field": str, "old_value": str, "new_value": str}

        Returns:
            (is_stale: bool, reason: str)
        """
        import re

        change_type = state_change.get("type", "")
        desc = health.memory.description

        patterns = self.STALE_PATTERNS.get(change_type, [])
        if not patterns:
            return False, ""

        for pattern in patterns:
            if re.search(pattern, desc):
                # 找到匹配：这条记忆与状态变化相关
                old_val = state_change.get("old_value", "")
                new_val = state_change.get("new_value", "")

                # 检查记忆内容是否提到旧值
                if old_val and old_val.lower() in desc.lower():
                    return True, f"状态已从 '{old_val}' 变为 '{new_val}'"
                # 宽松匹配：只要记忆内容与变化类型匹配就标记
                return True, f"记忆与 {change_type} 变化相关，可能已过期 ({pattern})"

        return False, ""


# ──────────────────────────────────────────────
# 主入口类
# ──────────────────────────────────────────────

@dataclass
class MemoryAutonomy:
    """Agent 记忆自主规划主入口。

    整合：重要性自评 + 遗忘曲线 + 复述 + 过期检测。

    用法:
        autonomy = MemoryAutonomy(agent_name="亚古兽", personality="brave")
        autonomy.register(memory_node)
        ...
        report = autonomy.step()  # 每 tick 调用一次
    """

    agent_name: str = "Unknown"
    personality: str = "neutral"
    assessor: ImportanceAssessor = field(default_factory=ImportanceAssessor)
    forgetting_engine: ForgettingEngine = field(default_factory=ForgettingEngine)
    rehearsal: MemoryRehearsal = field(default_factory=MemoryRehearsal)
    update_detector: MemoryUpdateDetector = field(default_factory=MemoryUpdateDetector)
    pending_state_changes: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        self.forgetting_engine.curve = EbbinghausCurve.for_agent(
            self.agent_name, self.personality
        )

    def register(self, memory: MemoryNode) -> MemoryHealth:
        """注册新记忆到遗忘引擎。"""
        return self.forgetting_engine.register(memory)

    def assess_importance(
        self,
        description: str,
        memory_type: str = "observation",
    ) -> int:
        """自评记忆重要性（同步版）。"""
        result = self.assessor.assess(
            description=description,
            agent_name=self.agent_name,
            agent_personality=self.personality,
            memory_type=memory_type,
        )
        return result["importance"]

    async def assess_importance_async(
        self,
        description: str,
        memory_type: str = "observation",
        llm_complete=None,
    ) -> int:
        """自评记忆重要性（异步版）。"""
        result = await self.assessor.assess_async(
            description=description,
            agent_name=self.agent_name,
            agent_personality=self.personality,
            memory_type=memory_type,
            llm_complete=llm_complete,
        )
        return result["importance"]

    def step(self, current_tick: int = 0) -> dict[str, Any]:
        """每个世界 tick 调用一次。

        执行：
        1. 更新所有记忆强度（遗忘曲线）
        2. 检测过期记忆
        3. 选取并执行复述

        Returns:
            诊断报告
        """
        # 1. 更新遗忘曲线
        health_stats = self.forgetting_engine.update_all_strengths()

        # 2. 检测过期记忆
        stale_count = 0
        for change in self.pending_state_changes:
            for health in list(self.forgetting_engine.memory_health.values()):
                if health.stale:
                    continue
                is_stale, reason = self.update_detector.detect_stale(health, change)
                if is_stale:
                    nid = health.memory.node_id
                    if nid is not None:
                        self.forgetting_engine.mark_stale(nid, reason)
                        stale_count += 1
        self.pending_state_changes.clear()

        # 3. 选取并执行复述
        selected = self.rehearsal.select_for_rehearsal(self.forgetting_engine)
        for health in selected:
            self.rehearsal.rehearse(health)

        return {
            "tick": current_tick,
            "agent": self.agent_name,
            "health": health_stats,
            "stale_detected": stale_count,
            "rehearsed": len(selected),
        }

    def notify_state_change(self, change_type: str, old_value: str, new_value: str) -> None:
        """通知世界状态变化，供过期检测使用。"""
        self.pending_state_changes.append({
            "type": change_type,
            "old_value": old_value,
            "new_value": new_value,
        })

    def diagnose(self) -> dict[str, Any]:
        """完整记忆健康诊断报告。"""
        return {
            "agent": self.agent_name,
            "personality": self.personality,
            "forgetting_half_life_hours": self.forgetting_engine.curve.half_life_seconds() / 3600,
            **self.forgetting_engine.diagnose(),
        }
