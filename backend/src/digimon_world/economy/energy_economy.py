"""
能量经济系统 (Energy Economy System)
=====================================

Phase 24: 在 CognitiveEnergyPool 之上构建 agent 间的能量经济。
- Agent 可以互相转移/交易能量
- 利他行为跟踪（谁帮过谁）
- Agent 可消耗自己能量唤醒休眠朋友

核心概念:
- EnergyTransfer: agent 间能量转移的不可变记录
- ReciprocalAltruism: 追踪 agent 对之间的帮助历史，计算互惠利他评分
- EnergyEconomy: 能量经济主引擎，管理转移、触发利他行为

设计要点:
- 纯规则引擎，不依赖外部 LLM 调用
- 与 CognitiveEnergyPool / DigimonAgent 解耦
- 互惠机制: A 帮 B → B 欠 A 人情债 → A 低能量时 B 主动回报
- 债务随时间衰败（久远的帮助逐渐被遗忘）

典型用法::

    from digimon_world.economy.energy_economy import EnergyEconomy, ReciprocalAltruism

    altruism = ReciprocalAltruism()
    economy = EnergyEconomy(world_state, altruism)

    # Agent 间捐赠
    economy.propose_transfer("agumon", "gabumon", 15, "donation", "看到朋友饿了")

    # 每 tick 评估
    awaken_ops = economy.check_awaken_opportunities()
    relief_ops = economy.check_desperation_relief()
    events = economy.step(current_tick)
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..world.world_state import WorldState


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# Agent 间能量转移后 from_agent 最低保留能量（transfer_type=="awaken" 时豁免）
MIN_SURVIVAL_ENERGY: float = 10.0

# 唤醒一个休眠 agent: helper 消耗 15 能量, dormant 恢复到 25 能量
AWAKEN_HELPER_COST: float = 15.0
AWAKEN_RESTORE_AMOUNT: float = 25.0

# 债务衰败: 每 100 tick 衰减 50%
DEBT_DECAY_INTERVAL: int = 100
DEBT_DECAY_FACTOR: float = 0.5

# 单笔债务上限
MAX_DEBT: float = 50.0

# 互惠触发阈值: agent A 欠 B 债务 > RECIPROCITY_DEBT_THRESHOLD 且 B 能量 < RECIPROCITY_ENERGY_THRESHOLD
RECIPROCITY_DEBT_THRESHOLD: float = 10.0
RECIPROCITY_ENERGY_THRESHOLD: float = 20.0

# 绝望救济阈值: agent 能量 < 此值视为需要救济
DESPERATION_ENERGY_THRESHOLD: float = 20.0

# 尝试唤醒时 helper 最低能量要求（不能把自己也搞成休眠）
AWAKEN_MIN_HELPER_ENERGY: float = AWAKEN_HELPER_COST + MIN_SURVIVAL_ENERGY

# 捐赠时推荐的最低 helper 能量
DONATION_MIN_HELPER_ENERGY: float = 30.0


# ---------------------------------------------------------------------------
# EnergyTransfer — agent 间能量转移记录
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class EnergyTransfer:
    """一次 agent 间能量转移的不可变记录。

    Attributes:
        transfer_id: UUID v4 唯一标识。
        from_agent: 源 agent 名称。
        to_agent: 目标 agent 名称。
        amount: 转移能量量。
        transfer_type: "donation" | "trade" | "awaken" | "tribute"。
        reason: 决策原因摘要（LLM 生成或规则生成）。
        tick: 发生的 world tick。
        timestamp: Unix 时间戳。
    """

    transfer_id: str
    from_agent: str
    to_agent: str
    amount: float
    transfer_type: str
    reason: str
    tick: int
    timestamp: float

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。"""
        return {
            "transfer_id": self.transfer_id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "amount": self.amount,
            "transfer_type": self.transfer_type,
            "reason": self.reason,
            "tick": self.tick,
            "timestamp": self.timestamp,
        }

    @classmethod
    def create(
        cls,
        from_agent: str,
        to_agent: str,
        amount: float,
        transfer_type: str,
        reason: str,
        tick: int,
    ) -> "EnergyTransfer":
        """工厂方法：创建一条带自动生成 ID 和时间戳的转移记录。"""
        return cls(
            transfer_id=str(uuid.uuid4()),
            from_agent=from_agent,
            to_agent=to_agent,
            amount=amount,
            transfer_type=transfer_type,
            reason=reason,
            tick=tick,
            timestamp=time.time(),
        )


# ---------------------------------------------------------------------------
# ReciprocalAltruism — 互惠利他评分
# ---------------------------------------------------------------------------

class ReciprocalAltruism:
    """追踪 agent 对之间的帮助历史，计算互惠利他评分。

    核心模型:
    - agent A 帮助 B → B 对 A 的"好感度债务"增加（记录为 B 欠 A）
    - get_debt("B", "A") 返回 B 欠 A 多少
    - 债务随时间衰减（久远的帮助逐渐被遗忘）
    - 债务有上限（防止无限累积）

    Attributes:
        _debts: {(debtor, creditor): debt_amount} — debtor 欠 creditor 的债务。
        _last_decay_tick: 上次衰败执行的 tick。
    """

    def __init__(self) -> None:
        self._debts: dict[tuple[str, str], float] = defaultdict(float)
        self._last_decay_tick: int = 0

    # ---- 债务记录 ----

    def record_help(
        self,
        helper: str,
        recipient: str,
        amount: float,
        tick: int,
    ) -> float:
        """记录一次帮助：helper 帮助了 recipient，recipient 欠 helper 债务增加。

        Args:
            helper: 帮助者名称。
            recipient: 受助者名称。
            amount: 帮助量（能量点数），转换为等额债务。
            tick: 当前 world tick。

        Returns:
            更新后的债务余额。
        """
        if helper == recipient:
            return 0.0  # 自己帮自己不算

        key = (recipient, helper)  # recipient 欠 helper
        self._debts[key] = min(MAX_DEBT, self._debts[key] + amount)
        return self._debts[key]

    def get_debt(self, debtor: str, creditor: str) -> float:
        """查询 debtor 欠 creditor 的债务量。

        Args:
            debtor: 欠债方。
            creditor: 债权方。

        Returns:
            债务量（浮点）。
        """
        return self._debts.get((debtor, creditor), 0.0)

    # ---- 利他声誉 ----

    def get_altruism_score(self, agent_name: str) -> float:
        """计算 agent 的利他声誉 (0-1)。

        基于该 agent 作为帮助者（被欠债）的总债务量归一化。
        分数越高说明越多人欠这个 agent 人情，即该 agent 帮助他人越多。

        Args:
            agent_name: agent 名称。

        Returns:
            利他评分 (0.0 ~ 1.0)。
        """
        total_credit = 0.0
        for (debtor, creditor), debt in self._debts.items():
            if creditor == agent_name:
                total_credit += debt

        if total_credit <= 0:
            return 0.0

        # 归一化: 假设 MAX_DEBT * 最多 10 个债务人 = 500 为满分
        # 实际上用 min(1.0, total_credit / 250) 来得到一个平滑的分数
        return min(1.0, total_credit / 250.0)

    # ---- 互惠判断 ----

    def should_reciprocate(self, agent: str, target: str) -> bool:
        """判断 agent 是否应该回报 target。

        当 agent 欠 target 的债务超过 RECIPROCITY_DEBT_THRESHOLD 时返回 True。

        Args:
            agent: 待评估的 agent（欠债方）。
            target: 目标 agent（债权方，曾帮过 agent）。

        Returns:
            True 如果 agent 有义务回报 target。
        """
        debt = self.get_debt(agent, target)
        return debt > RECIPROCITY_DEBT_THRESHOLD

    # ---- 债务排名 ----

    def get_top_creditors(self, agent_name: str, n: int = 5) -> list[tuple[str, float]]:
        """查询谁欠 agent_name 的债务最多（agent_name 是债权人）。

        Args:
            agent_name: agent 名称。
            n: 返回前 N 名。

        Returns:
            [(debtor_name, debt_amount), ...] 按债务降序排列。
        """
        debts: list[tuple[str, float]] = []
        for (debtor, creditor), debt in self._debts.items():
            if creditor == agent_name and debt > 0:
                debts.append((debtor, debt))
        debts.sort(key=lambda x: x[1], reverse=True)
        return debts[:n]

    def get_top_debtors(self, agent_name: str, n: int = 5) -> list[tuple[str, float]]:
        """查询 agent_name 欠谁的债务最多（agent_name 是欠债方）。

        Args:
            agent_name: agent 名称。
            n: 返回前 N 名。

        Returns:
            [(creditor_name, debt_amount), ...] 按债务降序排列。
        """
        debts: list[tuple[str, float]] = []
        for (debtor, creditor), debt in self._debts.items():
            if debtor == agent_name and debt > 0:
                debts.append((creditor, debt))
        debts.sort(key=lambda x: x[1], reverse=True)
        return debts[:n]

    # ---- 衰败 ----

    def decay_debts(self, current_tick: int) -> int:
        """随时间衰减债务（久远的帮助逐渐被遗忘）。

        每 DEBT_DECAY_INTERVAL tick 所有债务衰减 DEBT_DECAY_FACTOR (50%)。
        只在跨越衰败间隔时执行。过小的债务 (< 0.5) 会被清除。

        Args:
            current_tick: 当前 world tick。

        Returns:
            衰减的 tick 数（0 表示未到衰减间隔）。
        """
        ticks_since_decay = current_tick - self._last_decay_tick
        if ticks_since_decay < DEBT_DECAY_INTERVAL:
            return 0

        # 执行衰败
        decay_cycles = ticks_since_decay // DEBT_DECAY_INTERVAL
        factor = DEBT_DECAY_FACTOR ** decay_cycles

        keys_to_remove: list[tuple[str, str]] = []
        for key in self._debts:
            self._debts[key] *= factor
            if self._debts[key] < 0.5:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self._debts[key]

        self._last_decay_tick = current_tick - (ticks_since_decay % DEBT_DECAY_INTERVAL)
        return decay_cycles * DEBT_DECAY_INTERVAL

    # ---- 序列化 ----

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典（用于持久化）。"""
        debt_entries: dict[str, float] = {}
        for (debtor, creditor), debt in self._debts.items():
            debt_entries[f"{debtor}->{creditor}"] = round(debt, 2)
        return {
            "debts": debt_entries,
            "last_decay_tick": self._last_decay_tick,
        }

    def clear(self) -> None:
        """清空所有债务记录（测试用）。"""
        self._debts.clear()
        self._last_decay_tick = 0


# ---------------------------------------------------------------------------
# EnergyEconomy — 能量经济主引擎
# ---------------------------------------------------------------------------

class EnergyEconomy:
    """能量经济主引擎：管理 agent 间能量转移 + 触发利他行为。

    职责:
    - 验证并执行 agent 间能量转移
    - 扫描休眠 agent，建议清醒的朋友唤醒
    - 扫描低能量 agent，建议利他评分高的朋友捐赠
    - 每 tick 评估并触发利他行为

    Attributes:
        world_state: 世界状态引用。
        altruism: 互惠利他追踪器。
        transfer_history: 转移记录列表。
    """

    def __init__(
        self,
        world_state: "WorldState",
        altruism: ReciprocalAltruism | None = None,
        transfer_history: list[EnergyTransfer] | None = None,
    ) -> None:
        self.world_state = world_state
        self.altruism = altruism if altruism is not None else ReciprocalAltruism()
        self.transfer_history: list[EnergyTransfer] = (
            transfer_history if transfer_history is not None else []
        )

    # ---- 能量转移 ----

    def propose_transfer(
        self,
        from_agent: str,
        to_agent: str,
        amount: float,
        transfer_type: str,
        reason: str,
        tick: int | None = None,
    ) -> EnergyTransfer | None:
        """提议并执行一次能量转移。

        验证规则:
        - from_agent 存在且能量充足
        - to_agent 存在
        - amount > 0
        - from_agent 转移后能量 ≥ MIN_SURVIVAL_ENERGY（awaken 类型豁免）
        - awaken 类型: helper 消耗 AWAKEN_HELPER_COST，dormant 恢复到 AWAKEN_RESTORE_AMOUNT

        Args:
            from_agent: 源 agent 名称。
            to_agent: 目标 agent 名称。
            amount: 转移能量量。
            transfer_type: "donation" | "trade" | "awaken" | "tribute"。
            reason: 决策原因摘要。
            tick: world tick（默认从 world_state 推断）。

        Returns:
            EnergyTransfer 记录，验证失败返回 None。
        """
        # 获取 agent
        from_digi = self.world_state.agents.get(from_agent)
        to_digi = self.world_state.agents.get(to_agent)

        if from_digi is None:
            return None
        if to_digi is None:
            return None
        if amount <= 0:
            return None

        from_pool = from_digi.cognitive_energy
        to_pool = to_digi.cognitive_energy

        # awaken 特殊规则: 忽略传入的 amount，使用固定值
        if transfer_type == "awaken":
            if not to_pool.is_dormant:
                return None  # 目标未休眠，无需唤醒
            if from_pool.energy < AWAKEN_MIN_HELPER_ENERGY:
                return None  # helper 能量不足
            # 执行唤醒
            actual_from_cost = AWAKEN_HELPER_COST
            actual_to_gain = AWAKEN_RESTORE_AMOUNT
        else:
            # 常规转移: 检查 from_agent 能量
            if from_pool.energy < amount + MIN_SURVIVAL_ENERGY:
                return None  # 保留最低生存能量
            actual_from_cost = amount
            actual_to_gain = amount

        # 确定 tick
        current_tick = tick if tick is not None else 0

        # 执行转移
        from_pool.energy = max(0, from_pool.energy - actual_from_cost)
        to_pool.energy = min(to_pool.max_energy, to_pool.energy + actual_to_gain)

        # 如果 transfer_type != "awaken"，检查 from_agent 是否触发休眠
        if transfer_type != "awaken" and from_pool.energy <= 0:
            from_pool.is_dormant = True
            from_pool.energy = 0

        # 唤醒逻辑: 目标恢复后自动解除休眠
        if to_pool.energy > 0:
            to_pool.is_dormant = False

        # 创建转移记录
        transfer = EnergyTransfer.create(
            from_agent=from_agent,
            to_agent=to_agent,
            amount=actual_to_gain,
            transfer_type=transfer_type,
            reason=reason,
            tick=current_tick,
        )

        # 记录历史
        self.transfer_history.append(transfer)

        # 更新互惠债务（只有 donation / tribute 才计为利他行为）
        if transfer_type in ("donation", "tribute", "awaken"):
            self.altruism.record_help(
                helper=from_agent,
                recipient=to_agent,
                amount=actual_to_gain,
                tick=current_tick,
            )

        return transfer

    # ---- 机会扫描 ----

    def check_awaken_opportunities(self) -> list[tuple[str, str, float]]:
        """扫描所有休眠 agent，找关系最好的清醒 agent 建议唤醒。

        对每个休眠 agent:
        1. 在 altruism 中查找谁欠这个休眠 agent 的债务最多（即休眠 agent 曾帮过谁）
        2. 筛选出清醒且能量充足的 candidate
        3. 返回 (dormant_name, helper_name, debt) 三元组

        Returns:
            [(dormant_agent, potential_helper, debt_owed), ...]
            按债务降序排列。
        """
        opportunities: list[tuple[str, str, float]] = []

        for agent_name, agent in self.world_state.agents.items():
            pool = agent.cognitive_energy

            # 只关注休眠 agent
            if not pool.is_dormant:
                continue

            # 找谁欠这个休眠 agent 最多（即他们受过休眠 agent 的帮助）
            creditors = self.altruism.get_top_creditors(agent_name, n=10)
            for debtor_name, debt in creditors:
                # debtor 必须清醒且有足够能量唤醒朋友
                debtor_digi = self.world_state.agents.get(debtor_name)
                if debtor_digi is None:
                    continue
                debtor_pool = debtor_digi.cognitive_energy
                if debtor_pool.is_dormant:
                    continue
                if debtor_pool.energy < AWAKEN_MIN_HELPER_ENERGY:
                    continue

                opportunities.append((agent_name, debtor_name, debt))
                break  # 每个休眠 agent 只取最佳候选

        # 按债务降序
        opportunities.sort(key=lambda x: x[2], reverse=True)
        return opportunities

    def check_desperation_relief(self) -> list[tuple[str, str, float]]:
        """扫描能量 < DESPERATION_ENERGY_THRESHOLD 的 agent，找曾欠其恩情的朋友建议捐赠。

        互惠规则 (spec 第 5 条):
        - agent A 欠 agent B 债务 > RECIPROCITY_DEBT_THRESHOLD
        - 且 B 当前能量 < RECIPROCITY_ENERGY_THRESHOLD
        - → A 有义务主动捐赠给 B

        即: 低能量 agent (B) 是债权人，捐赠者 (A) 是欠债方。

        步骤:
        1. 找所有能量 < DESPERATION_ENERGY_THRESHOLD 的 agent (B)
        2. 对每个 B，在 altruism 中查找谁欠 B 最多 → 这些是 A
        3. 若 A 欠 B 的债务 > RECIPROCITY_DEBT_THRESHOLD 且 A 清醒且有足够能量
           → 建议 A 捐赠给 B

        Returns:
            [(low_energy_agent_B, potential_donor_A, debt_owed), ...]
        """
        reliefs: list[tuple[str, str, float]] = []

        for agent_name, agent in self.world_state.agents.items():
            pool = agent.cognitive_energy

            # 只关注低能量但尚未休眠的 agent (B = 债权人 = 被帮助过的人)
            if pool.is_dormant:
                continue
            if pool.energy >= DESPERATION_ENERGY_THRESHOLD:
                continue

            # 查找谁欠这个低能量 agent (B) 的债务最多 → 这些是 A (欠债方/潜在捐赠者)
            creditors = self.altruism.get_top_creditors(agent_name, n=10)
            for debtor_name, debt in creditors:  # debtor_name = A, debt = A 欠 B 的量
                if debt <= RECIPROCITY_DEBT_THRESHOLD:
                    continue

                # A (debtor) 必须清醒且有足够能量捐赠
                debtor_digi = self.world_state.agents.get(debtor_name)
                if debtor_digi is None:
                    continue
                debtor_pool = debtor_digi.cognitive_energy
                if debtor_pool.is_dormant:
                    continue
                if debtor_pool.energy < DONATION_MIN_HELPER_ENERGY:
                    continue

                # 确认互惠触发: A 欠 B > 阈值, B 低能量 → A 应捐赠
                if self.altruism.should_reciprocate(debtor_name, agent_name):
                    reliefs.append((agent_name, debtor_name, debt))
                break  # 每个低能量 agent 只取最佳候选

        reliefs.sort(key=lambda x: x[2], reverse=True)
        return reliefs

    # ---- 查询 & 统计 ----

    def get_transfer_history(
        self, agent_name: str | None = None, limit: int = 50
    ) -> list[EnergyTransfer]:
        """获取转移历史。

        Args:
            agent_name: 可选，只返回与该 agent 相关的转移。
            limit: 最大返回条数。

        Returns:
            按时间戳降序排列的转移记录。
        """
        if agent_name is None:
            history = list(self.transfer_history)
        else:
            history = [
                t
                for t in self.transfer_history
                if t.from_agent == agent_name or t.to_agent == agent_name
            ]
        history.sort(key=lambda x: x.timestamp, reverse=True)
        return history[:limit]

    def get_economy_stats(self) -> dict[str, Any]:
        """获取能量经济统计摘要。

        Returns:
            包含以下字段的字典:
            - total_transfers: 总转移次数
            - total_energy_transferred: 总转移能量
            - transfers_by_type: 各类型转移次数
            - avg_altruism_score: 平均利他评分
            - awaken_count: 唤醒次数
            - donation_count: 捐赠次数
            - trade_count: 交易次数
            - tribute_count: 进贡次数
            - total_debt_pairs: 存在债务的 agent 对数
        """
        total_transfers = len(self.transfer_history)
        total_energy = sum(t.amount for t in self.transfer_history)

        transfers_by_type: dict[str, int] = defaultdict(int)
        for t in self.transfer_history:
            transfers_by_type[t.transfer_type] += 1

        # 平均利他评分
        agent_names = list(self.world_state.agents.keys())
        if agent_names:
            avg_altruism = sum(
                self.altruism.get_altruism_score(name) for name in agent_names
            ) / len(agent_names)
        else:
            avg_altruism = 0.0

        return {
            "total_transfers": total_transfers,
            "total_energy_transferred": round(total_energy, 1),
            "transfers_by_type": dict(transfers_by_type),
            "avg_altruism_score": round(avg_altruism, 3),
            "awaken_count": transfers_by_type.get("awaken", 0),
            "donation_count": transfers_by_type.get("donation", 0),
            "trade_count": transfers_by_type.get("trade", 0),
            "tribute_count": transfers_by_type.get("tribute", 0),
            "total_debt_pairs": len(self.altruism._debts),
        }

    # ---- 每 tick 评估 ----

    def step(self, current_tick: int) -> list[dict[str, Any]]:
        """每 tick 评估是否触发利他行为。

        执行顺序:
        1. 债务衰败
        2. 扫描绝望救济机会
        3. 扫描唤醒机会

        Args:
            current_tick: 当前 world tick。

        Returns:
            本 tick 触发的事件列表。
        """
        events: list[dict[str, Any]] = []

        # 1. 债务衰败
        self.altruism.decay_debts(current_tick)

        # 2. 绝望救济: 低能量 agent 获得曾受其帮助的朋友的捐赠
        relief_opportunities = self.check_desperation_relief()
        for low_agent, donor, debt in relief_opportunities:
            # 建议捐赠量: 取 debt 的 30%~50%，但不超过 donor 的可用能量
            suggested_amount = min(debt * 0.4, 15.0)
            transfer = self.propose_transfer(
                from_agent=donor,
                to_agent=low_agent,
                amount=suggested_amount,
                transfer_type="donation",
                reason=f"reciprocal relief: owed {debt:.1f} debt to {low_agent}",
                tick=current_tick,
            )
            if transfer is not None:
                events.append({
                    "type": "reciprocal_relief",
                    "donor": donor,
                    "recipient": low_agent,
                    "amount": transfer.amount,
                    "debt": round(debt, 1),
                })

        # 3. 唤醒: 休眠 agent 获得朋友唤醒
        awaken_opportunities = self.check_awaken_opportunities()
        for dormant_agent, helper, debt in awaken_opportunities:
            transfer = self.propose_transfer(
                from_agent=helper,
                to_agent=dormant_agent,
                amount=AWAKEN_HELPER_COST,
                transfer_type="awaken",
                reason=f"awakening dormant friend (debt owed: {debt:.1f})",
                tick=current_tick,
            )
            if transfer is not None:
                events.append({
                    "type": "awaken",
                    "helper": helper,
                    "dormant": dormant_agent,
                    "helper_cost": AWAKEN_HELPER_COST,
                    "restored": AWAKEN_RESTORE_AMOUNT,
                    "debt": round(debt, 1),
                })

        return events

    # ---- 序列化 ----

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。"""
        return {
            "altruism": self.altruism.to_dict(),
            "transfer_history": [t.to_dict() for t in self.transfer_history[-100:]],
            "economy_stats": self.get_economy_stats(),
        }


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------

__all__ = [
    "MIN_SURVIVAL_ENERGY",
    "AWAKEN_HELPER_COST",
    "AWAKEN_RESTORE_AMOUNT",
    "DEBT_DECAY_INTERVAL",
    "DEBT_DECAY_FACTOR",
    "MAX_DEBT",
    "RECIPROCITY_DEBT_THRESHOLD",
    "RECIPROCITY_ENERGY_THRESHOLD",
    "DESPERATION_ENERGY_THRESHOLD",
    "EnergyTransfer",
    "ReciprocalAltruism",
    "EnergyEconomy",
]
