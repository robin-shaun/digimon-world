"""
思考成本 & 认知能量系统 (Thinking Cost & Cognitive Energy)
==========================================================

受论文 arXiv:2607.14865 启发——"Thinking Cost Aware Multi-Agent LLM Society Simulation"。
该论文提出: LLM 调用与 token 消耗并非免费，多智能体模拟中的认知资源应当被量化为
可消耗、可再生的"认知能量"。这引入了"自然选择"压力——能量充足的智能体进行更深入
的思考，而能量耗尽的智能体进入休眠/简化模式，从而涌现出更真实的群体行为。

Three design pillars (借鉴自论文):
1. 认知能量 (CogE) 作为有限资源，每次 LLM 调用按 token 估算消耗能量
2. 休眠机制: 能量耗尽 → 智能体休眠，失去自主性，等待恢复
3. 能量经济: 通过社交互动、觅食成功等行为恢复能量，形成反馈循环

模型:
- 每只数码兽拥有一个 CognitiveEnergyPool，追踪其认知能量 (0-100)
- 每 tick 被动消耗 1 点 (BASE_DRAIN_PER_TICK)，代表思维的自然消耗
- LLM 调用消耗 = max(1, estimated_tokens // 200)，约 200 tokens/能量点
- can_think() 检查能量 > 5 (THINK_THRESHOLD)，高于 DORMANCY_THRESHOLD (0)
  以确保刚恢复的智能体不会立刻再次休眠
- 能量恢复: 休眠/休息 +2/tick，社交互动 +5，成功觅食 +10
- 全局 EnergyLedger 单例追踪所有智能体的能量状态

设计要点:
- CognitiveEnergyPool 与 DigimonAgent 解耦，纯数据+简单逻辑，方便单测
- 能量消耗基于 estimated_tokens（调用前估算），不依赖实际 token 计数
- 能量历史记录最近 20 条变更，用于调试和分析
- 遵循代码库惯例: 中英双语 docstring、dataclass、from __future__ import annotations
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ----------------------------------------------------------------------------
# 常量 (Recovery & Cost Constants)
# ----------------------------------------------------------------------------

ENERGY_MAX: int = 100                # 最大能量上限
ENERGY_MIN: int = 0                  # 最低能量下限
BASE_DRAIN_PER_TICK: int = 1         # 每 tick 被动消耗 (自然思维消耗)
LLM_COST_DIVISOR: int = 200          # tokens per energy point (每能量点对应的 token 数)
RECOVER_REST: int = 2                # 休眠/休息时每 tick 恢复量
RECOVER_SOCIAL: int = 5              # 每次社交互动恢复量
RECOVER_EAT: int = 10                # 每次成功觅食恢复量
DORMANCY_THRESHOLD: int = 0          # energy <= 此值 → 进入休眠
THINK_THRESHOLD: int = 5             # energy 必须 > 此值才能使用 LLM
MAX_ENERGY_HISTORY: int = 20         # 能量历史最大记录数


# ----------------------------------------------------------------------------
# CognitiveEnergyPool — 每只数码兽的认知能量池
# ----------------------------------------------------------------------------

@dataclass
class CognitiveEnergyPool:
    """一只数码兽的认知能量池 (Cognitive Energy Pool)。

    追踪该智能体的认知能量水平，管理 LLM 调用成本与休眠/唤醒状态。
    能量是有限的——每次 LLM 调用消耗能量，能量耗尽后智能体进入休眠模式。

    Attributes:
        energy: 当前能量 (0-100)，初始满额。
        max_energy: 能量上限 (默认 100)。
        is_dormant: 是否休眠 (能量 ≤ 0 时自动进入休眠)。
        base_drain: 每 tick 被动消耗量 (默认 1)。
        total_llm_calls: 累计 LLM 调用次数。
        total_tokens_spent: 累计 token 消耗量。
        energy_history: 最近 20 条能量变更记录 [{tick, action, delta, reason}]。
    """

    energy: int = ENERGY_MAX
    max_energy: int = ENERGY_MAX
    is_dormant: bool = False
    base_drain: int = BASE_DRAIN_PER_TICK
    total_llm_calls: int = 0
    total_tokens_spent: int = 0
    energy_history: list[dict] = field(default_factory=list)

    def tick(self) -> int:
        """世界推进一 tick：应用被动能量消耗。

        每 tick 扣除 base_drain 点能量。若能量降至 ≤ DORMANCY_THRESHOLD，
        自动进入休眠状态 (is_dormant = True)。

        Returns:
            当前能量值。
        """
        self.energy = max(ENERGY_MIN, self.energy - self.base_drain)
        if self.energy <= DORMANCY_THRESHOLD:
            self.energy = ENERGY_MIN
            self.is_dormant = True
        self._record_history("tick", -self.base_drain, "passive_drain")
        return self.energy

    def spend(self, estimated_tokens: int, reason: str = "llm_call") -> int:
        """消耗能量：根据估算 token 数量扣除认知能量。

        计算公式: cost = max(1, estimated_tokens // LLM_COST_DIVISOR)
        即每约 200 个 token 消耗 1 点能量，最小消耗 1 点。

        同时更新 total_llm_calls (调用次数) 和 total_tokens_spent (累计 tokens)。

        Args:
            estimated_tokens: 估算的 token 消耗量。
            reason: 消耗原因标签 (用于历史记录)。

        Returns:
            消耗后的当前能量值。
        """
        cost: int = max(1, estimated_tokens // LLM_COST_DIVISOR)
        self.energy = max(ENERGY_MIN, self.energy - cost)
        self.total_llm_calls += 1
        self.total_tokens_spent += estimated_tokens

        if self.energy <= DORMANCY_THRESHOLD:
            self.energy = ENERGY_MIN
            self.is_dormant = True

        self._record_history("spend", -cost, reason)
        return self.energy

    def recover(self, amount: int, reason: str = "rest") -> int:
        """恢复能量：增加指定数量的认知能量 (夹紧到 max_energy)。

        若能量恢复后 > 0，自动唤醒 (is_dormant = False)。

        Args:
            amount: 恢复的能量点数。
            reason: 恢复原因标签。

        Returns:
            恢复后的当前能量值。
        """
        if amount <= 0:
            return self.energy  # 忽略非正恢复量
        self.energy = min(self.max_energy, self.energy + amount)
        if self.energy > DORMANCY_THRESHOLD:
            self.is_dormant = False
        self._record_history("recover", +amount, reason)
        return self.energy

    def can_think(self) -> bool:
        """是否可以执行 LLM 思考 (能量充足)。

        返回 True 当能量 > THINK_THRESHOLD (5)。
        这个缓冲区确保智能体刚恢复后不会立刻再次耗尽能量——不同于
        DORMANCY_THRESHOLD (0)，给恢复后的智能体一些"呼吸空间"。

        Returns:
            True 如果可以安全调用 LLM。
        """
        return self.energy > THINK_THRESHOLD and not self.is_dormant

    def to_dict(self) -> dict:
        """序列化为字典。

        Returns:
            包含所有关键字段的字典。
        """
        return {
            "energy": self.energy,
            "max_energy": self.max_energy,
            "is_dormant": self.is_dormant,
            "base_drain": self.base_drain,
            "total_llm_calls": self.total_llm_calls,
            "total_tokens_spent": self.total_tokens_spent,
            "can_think": self.can_think(),
            "energy_history": list(self.energy_history),  # 浅拷贝
        }

    def _record_history(self, action: str, delta: int, reason: str) -> None:
        """内部: 记录能量变更到历史 (维护最近 MAX_ENERGY_HISTORY 条)。"""
        entry: dict = {
            "action": action,
            "delta": delta,
            "reason": reason,
            "energy_after": self.energy,
        }
        self.energy_history.append(entry)
        # 保留最近 N 条
        if len(self.energy_history) > MAX_ENERGY_HISTORY:
            self.energy_history = self.energy_history[-MAX_ENERGY_HISTORY:]


# ----------------------------------------------------------------------------
# EnergyLedger — 全局能量账本 (单例)
# ----------------------------------------------------------------------------

class EnergyLedger:
    """全局认知能量账本 (Global Energy Ledger)。

    追踪世界中所有智能体的认知能量状态，提供汇总统计。
    单例模式——通过模块级 get_energy_ledger() 获取唯一实例。

    Attributes:
        pools: agent_name → CognitiveEnergyPool 的映射。
    """

    def __init__(self) -> None:
        self.pools: dict[str, CognitiveEnergyPool] = {}

    def get_or_create(self, name: str) -> CognitiveEnergyPool:
        """获取或创建指定智能体的能量池。

        如果该智能体已存在，返回现有池；否则创建新的满能量池。

        Args:
            name: 智能体名称。

        Returns:
            CognitiveEnergyPool 实例。
        """
        if name not in self.pools:
            self.pools[name] = CognitiveEnergyPool()
        return self.pools[name]

    def get_stats(self) -> dict:
        """获取全局能量统计摘要。

        Returns:
            包含以下字段的字典:
            - total_agents: 账本中智能体总数
            - active_count: 活跃 (非休眠) 智能体数
            - dormant_count: 休眠智能体数
            - avg_energy: 平均能量值 (浮点)
            - total_llm_calls: 累计 LLM 调用总数
            - total_tokens: 累计 token 消耗总数
        """
        total = len(self.pools)
        if total == 0:
            return {
                "total_agents": 0,
                "active_count": 0,
                "dormant_count": 0,
                "avg_energy": 0.0,
                "total_llm_calls": 0,
                "total_tokens": 0,
            }

        active = sum(1 for p in self.pools.values() if not p.is_dormant)
        dormant = total - active
        avg_energy = sum(p.energy for p in self.pools.values()) / total
        total_calls = sum(p.total_llm_calls for p in self.pools.values())
        total_tokens = sum(p.total_tokens_spent for p in self.pools.values())

        return {
            "total_agents": total,
            "active_count": active,
            "dormant_count": dormant,
            "avg_energy": round(avg_energy, 2),
            "total_llm_calls": total_calls,
            "total_tokens": total_tokens,
        }

    def reset_all(self) -> None:
        """重置账本：清空所有智能体的能量池。

        通常用于模拟重启或测试清理。
        """
        self.pools.clear()


# ----------------------------------------------------------------------------
# 模块级单例访问器
# ----------------------------------------------------------------------------

_energy_ledger: EnergyLedger | None = None


def get_energy_ledger() -> EnergyLedger:
    """获取全局 EnergyLedger 单例。

    懒初始化：首次调用时创建实例，后续调用返回同一实例。

    Returns:
        全局唯一的 EnergyLedger 实例。
    """
    global _energy_ledger
    if _energy_ledger is None:
        _energy_ledger = EnergyLedger()
    return _energy_ledger


# ----------------------------------------------------------------------------
# 导出
# ----------------------------------------------------------------------------

__all__ = [
    "ENERGY_MAX",
    "ENERGY_MIN",
    "BASE_DRAIN_PER_TICK",
    "LLM_COST_DIVISOR",
    "RECOVER_REST",
    "RECOVER_SOCIAL",
    "RECOVER_EAT",
    "DORMANCY_THRESHOLD",
    "THINK_THRESHOLD",
    "MAX_ENERGY_HISTORY",
    "CognitiveEnergyPool",
    "EnergyLedger",
    "get_energy_ledger",
]
