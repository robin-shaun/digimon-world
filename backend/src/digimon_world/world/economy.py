"""
EconomySystem - 数码世界经济 / digital_bit 货币
================================================

数码世界流通一种货币 —— **digital_bit(数码比特,简称 bit)**。数码兽通过
日常的战斗与探索赚取 bit,再拿到「奥加兽商店」换购道具。这套系统把原本零散
的战斗掉落(items.py)与地标探索(landmarks.py)接到一条统一的经济链上:

    打怪 / 探索  ──赚──▶  digital_bit 钱包  ──花──▶  奥加兽商店买道具

三条赚钱途径:
1. 战斗胜利  —— 赢家获得 BATTLE_REWARD 枚 bit(见 reward_battle_win)。
2. 探索地标  —— 靠近任意地标(复用 landmarks 的坐标 / 半径)每 tick 有
   EXPLORE_REWARD_CHANCE 概率捡到 EXPLORE_REWARD 枚 bit(见 process_exploration)。
3. (未来)任务 / 剧情奖励。

花钱途径:
- 奥加兽商店按 SHOP_PRICES 明码标价卖 items.py 里的道具。数码兽必须站在商店
  触发半径内、且钱包余额充足才能买(见 buy)。买到的道具直接进 ItemSystem 背包。

设计要点:
- 纯内存、纯同步、无 LLM 依赖(scheduler 每 tick 高频调用 process())。
- 随机性(探索奖励)走可注入的 random.Random,测试可复现。
- 钱包按 agent.name 存(与 items / relationships / landmarks 一致),便于持久化。
- 商店定价复用 items.CATALOG,避免道具目录与售价漂移。

典型用法::

    economy = EconomySystem()
    economy.reward_battle_win("亚古兽")          # 战斗胜利后
    economy.process(world)                        # 每 tick: 探索奖励
    economy.buy("亚古兽", "small_potion", world)  # 靠近商店时买药水
    economy.balance_of("亚古兽")                  # -> int
"""

from __future__ import annotations

import random
from math import hypot
from typing import TYPE_CHECKING, Any

from .items import CATALOG, ItemSystem, get_item_system
from .landmarks import DEFAULT_LANDMARKS, TRIGGER_RADIUS

if TYPE_CHECKING:
    from ..agents.digimon_agent import DigimonAgent
    from .world_state import WorldState


# ---- 货币 ----
CURRENCY_ID: str = "digital_bit"
CURRENCY_NAME: str = "数码比特"

# ---- 赚钱参数 ----
# 战斗胜利奖励的 bit 数
BATTLE_REWARD: int = 25

# 探索(靠近地标)每 tick 捡到 bit 的概率与数额
EXPLORE_REWARD_CHANCE: float = 0.15
EXPLORE_REWARD: int = 5

# 新数码兽入场时的初始钱包(让它一开始就能买得起最便宜的道具)
STARTING_BALANCE: int = 50

# ---- 奥加兽商店定价(item_id -> 价格 bit) ----
# 只卖 items 目录里明确标价的道具;进化石稀有,定价最高。
SHOP_PRICES: dict[str, int] = {
    "small_potion": 20,
    "large_potion": 45,
    "power_seed": 60,
    "guard_seed": 60,
    "swift_seed": 60,
    "evolution_stone": 150,
}

# 奥加兽商店坐标 / region —— 复用 landmarks 里的定义,避免坐标漂移
_OGREMON_SHOP = next(lm for lm in DEFAULT_LANDMARKS if lm.landmark_id == "ogremon_shop")


class EconomySystem:
    """经济系统: digital_bit 钱包 / 战斗探索赚钱 / 奥加兽商店购物。

    Attributes:
        wallets: {agent_name: balance} —— 每只数码兽的 bit 余额
        items: 道具系统(购物时把买到的道具塞进背包);默认用进程级单例
    """

    def __init__(self, items: ItemSystem | None = None) -> None:
        self.wallets: dict[str, int] = {}
        self._items = items if items is not None else get_item_system()
        self._rng = random.Random()

    # ---- 钱包 ----
    def balance_of(self, agent_name: str) -> int:
        """某只数码兽的 bit 余额(未开钱包视为 0)。"""
        return self.wallets.get(agent_name, 0)

    def credit(self, agent_name: str, amount: int) -> int:
        """给钱包加 bit(amount 需 > 0),返回新余额。"""
        if amount <= 0:
            return self.balance_of(agent_name)
        new_balance = self.wallets.get(agent_name, 0) + amount
        self.wallets[agent_name] = new_balance
        return new_balance

    def ensure_wallet(self, agent_name: str) -> int:
        """确保数码兽有钱包,首次开户给 STARTING_BALANCE。返回余额。"""
        if agent_name not in self.wallets:
            self.wallets[agent_name] = STARTING_BALANCE
        return self.wallets[agent_name]

    # ---- 赚钱: 战斗 ----
    def reward_battle_win(self, winner_name: str, amount: int = BATTLE_REWARD) -> dict[str, Any]:
        """战斗胜利奖励 bit,返回赚钱事件 dict。"""
        balance = self.credit(winner_name, amount)
        return {
            "type": "bit_earned",
            "agent": winner_name,
            "amount": amount,
            "balance": balance,
            "source": "battle_win",
        }

    # ---- 赚钱: 探索地标 ----
    def process_exploration(
        self, world: WorldState, rng: random.Random | None = None
    ) -> list[dict[str, Any]]:
        """遍历世界: 靠近任意地标的数码兽每 tick 有概率捡到 bit。

        Returns:
            赚钱事件 dict 列表(未捡到的不计入)。
        """
        r = rng if rng is not None else self._rng
        events: list[dict[str, Any]] = []
        for agent in world.all():
            landmark = self._nearby_landmark(agent)
            if landmark is None:
                continue
            if r.random() >= EXPLORE_REWARD_CHANCE:
                continue
            balance = self.credit(agent.name, EXPLORE_REWARD)
            events.append({
                "type": "bit_earned",
                "agent": agent.name,
                "amount": EXPLORE_REWARD,
                "balance": balance,
                "source": "exploration",
                "landmark": landmark.landmark_id,
            })
        return events

    @staticmethod
    def _nearby_landmark(agent: DigimonAgent):
        """返回数码兽当前所在触发半径内的第一个地标(没有则 None)。"""
        for lm in DEFAULT_LANDMARKS:
            if agent.region_id != lm.region_id:
                continue
            x, y = agent.location
            if hypot(lm.x - x, lm.y - y) < TRIGGER_RADIUS:
                return lm
        return None

    # ---- 花钱: 奥加兽商店 ----
    def buy(
        self, agent_name: str, item_id: str, world: WorldState
    ) -> dict[str, Any]:
        """在奥加兽商店买一件道具。

        校验(任一不满足则返回 ok=False + reason,不扣钱、不发货):
        - 数码兽存在
        - 该 item_id 在售(SHOP_PRICES)
        - 数码兽站在商店触发半径内
        - 钱包余额 >= 售价

        成功时: 扣钱、道具进背包、返回 ok=True + 交易明细。
        """
        agent = world.get(agent_name)
        if agent is None:
            return {"ok": False, "reason": "digimon_not_found", "agent": agent_name}

        price = SHOP_PRICES.get(item_id)
        if price is None:
            return {"ok": False, "reason": "item_not_for_sale", "item": item_id}

        if not self._near_shop(agent):
            return {"ok": False, "reason": "not_at_shop", "agent": agent_name}

        balance = self.balance_of(agent_name)
        if balance < price:
            return {
                "ok": False,
                "reason": "insufficient_funds",
                "agent": agent_name,
                "balance": balance,
                "price": price,
            }

        # 扣钱 + 发货
        item = CATALOG[item_id]
        self.wallets[agent_name] = balance - price
        self._items.grant(agent_name, item)
        return {
            "ok": True,
            "type": "item_bought",
            "agent": agent_name,
            "item": item_id,
            "item_name": item.name,
            "price": price,
            "balance": self.wallets[agent_name],
            "source": "ogremon_shop",
        }

    @staticmethod
    def _near_shop(agent: DigimonAgent) -> bool:
        """数码兽是否在奥加兽商店的触发半径内(同 region + 距离 < 半径)。"""
        if agent.region_id != _OGREMON_SHOP.region_id:
            return False
        x, y = agent.location
        return hypot(_OGREMON_SHOP.x - x, _OGREMON_SHOP.y - y) < TRIGGER_RADIUS

    # ---- 批量处理(scheduler 每 tick 调用) ----
    def process(
        self, world: WorldState, rng: random.Random | None = None
    ) -> list[dict[str, Any]]:
        """一次 tick 的经济处理: 探索赚 bit。

        Returns:
            本 tick 触发的所有经济事件。
        """
        return self.process_exploration(world, rng=rng)

    # ---- 序列化 / 状态查询 ----
    def shop_catalog(self) -> list[dict[str, Any]]:
        """奥加兽商店货架: 每件在售道具的资料 + 售价(前端商店 UI 用)。"""
        shelf: list[dict[str, Any]] = []
        for item_id, price in SHOP_PRICES.items():
            item = CATALOG[item_id]
            entry = item.to_dict()
            entry["price"] = price
            shelf.append(entry)
        return shelf

    def to_dict(self, world: WorldState | None = None) -> dict[str, Any]:
        """经济系统整体状态(GET /api/economy 用)。

        Args:
            world: 传入时用它补齐尚未开钱包的数码兽(余额 0);不传只报已有钱包。
        """
        balances = dict(self.wallets)
        if world is not None:
            for agent in world.all():
                balances.setdefault(agent.name, 0)
        wallets = sorted(
            ({"name": name, "balance": bal} for name, bal in balances.items()),
            key=lambda w: w["balance"],
            reverse=True,
        )
        return {
            "currency": {"id": CURRENCY_ID, "name": CURRENCY_NAME},
            "total_bits": sum(balances.values()),
            "battle_reward": BATTLE_REWARD,
            "explore_reward": EXPLORE_REWARD,
            "explore_reward_chance": EXPLORE_REWARD_CHANCE,
            "starting_balance": STARTING_BALANCE,
            "wallets": wallets,
            "shop": {
                "landmark_id": _OGREMON_SHOP.landmark_id,
                "name": _OGREMON_SHOP.name,
                "catalog": self.shop_catalog(),
            },
        }


# ---- 进程级单例 ----
_economy_system: EconomySystem | None = None


def get_economy_system() -> EconomySystem:
    """获取(或延迟初始化)经济系统单例。"""
    global _economy_system
    if _economy_system is None:
        _economy_system = EconomySystem()
    return _economy_system


def reset_economy_system() -> None:
    """重置经济系统(测试用)。"""
    global _economy_system
    _economy_system = None


__all__ = [
    "BATTLE_REWARD",
    "CURRENCY_ID",
    "CURRENCY_NAME",
    "EXPLORE_REWARD",
    "EXPLORE_REWARD_CHANCE",
    "SHOP_PRICES",
    "STARTING_BALANCE",
    "EconomySystem",
    "get_economy_system",
    "reset_economy_system",
]
