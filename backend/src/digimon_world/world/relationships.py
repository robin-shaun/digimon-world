"""
RelationshipTracker - 数码兽社交关系
====================================

维护数码兽两两之间的双向关系值 (-100 ~ 100):
- 正数 = 友好, 负数 = 敌对, 0 = 中立
- 对话 / 相遇 → 关系变友好
- 战斗 → 关系变敌对 (输方对赢方生出敬畏, 稍稍回暖)

参考 Stanford Generative Agents 里 persona 之间隐含的"熟悉度",这里把它
显式建模成一个对称的关系分数表,方便前端画"派系图"、Director 观察阵营。

设计要点:
- 关系对称: score(a, b) == score(b, a)。内部用排序后的 (name, name) 元组做 key,
  只存一份,update 时天然双向。
- 纯内存、纯同步、无 LLM 依赖(高频调用 / 好测试)。
- 分数夹紧在 [MIN_SCORE, MAX_SCORE]。

典型用法:

    rt = RelationshipTracker()
    rt.update("亚古兽", "加布兽", +3)      # 一次友好对话
    rt.get_relationship("亚古兽", "加布兽") # -> 3.0
    rt.get_faction("亚古兽")               # -> {"ally": "加布兽", "rival": None}
"""

from __future__ import annotations

from typing import Any, Optional

# 关系值边界
MIN_SCORE: float = -100.0
MAX_SCORE: float = 100.0

# 各类互动的默认增量(供 scheduler / api 引用,避免魔数散落)
DIALOGUE_DELTA: float = 3.0       # 一次对话 → 双方 +3 友好
PROXIMITY_DELTA: float = 1.0      # 相遇但没对话(冷却中) → +1 友好
BATTLE_DELTA: float = -10.0       # 战斗 → 双方 -10 敌对
BATTLE_AWE_DELTA: float = 5.0     # 输方对赢方额外 +5 敬畏(抵消部分敌对)


def _key(a: str, b: str) -> tuple[str, str]:
    """把一对名字规范成排序后的 key,保证 (a,b) 与 (b,a) 命中同一条记录。"""
    return (a, b) if a <= b else (b, a)


class RelationshipTracker:
    """数码兽社交关系表:维护两两之间的双向关系分数。"""

    def __init__(self) -> None:
        # (name_a, name_b) 已排序 -> 关系分数
        self._scores: dict[tuple[str, str], float] = {}

    @staticmethod
    def _clamp(value: float) -> float:
        return max(MIN_SCORE, min(MAX_SCORE, value))

    def get_relationship(self, a: str, b: str) -> float:
        """查 a 与 b 的关系值。从未互动过 → 0.0(中立)。自我关系恒为 0。"""
        if a == b:
            return 0.0
        return self._scores.get(_key(a, b), 0.0)

    def update(self, a: str, b: str, delta: float) -> float:
        """更新 a 与 b 的双向关系(对称),返回更新后的分数。

        自我更新 (a == b) 是 no-op,返回 0.0。
        分数夹紧在 [MIN_SCORE, MAX_SCORE]。
        """
        if a == b:
            return 0.0
        key = _key(a, b)
        new_score = self._clamp(self._scores.get(key, 0.0) + delta)
        self._scores[key] = new_score
        return new_score

    def get_faction(self, a: str) -> dict[str, Optional[str]]:
        """返回 a 最友好 (ally) 和最敌对 (rival) 的对象。

        - ally: 关系值最高且 > 0 的那只;没有正关系 → None
        - rival: 关系值最低且 < 0 的那只;没有负关系 → None
        并列时取名字字典序较小者(确定性)。
        """
        best_ally: Optional[str] = None
        best_ally_score = 0.0
        worst_rival: Optional[str] = None
        worst_rival_score = 0.0

        for (x, y), score in self._scores.items():
            if a not in (x, y):
                continue
            other = y if x == a else x
            if score > best_ally_score or (
                score == best_ally_score and best_ally is not None and other < best_ally
            ):
                if score > 0:
                    best_ally, best_ally_score = other, score
            if score < worst_rival_score or (
                score == worst_rival_score and worst_rival is not None and other < worst_rival
            ):
                if score < 0:
                    worst_rival, worst_rival_score = other, score

        return {"ally": best_ally, "rival": worst_rival}

    def record_dialogue(self, a: str, b: str) -> float:
        """一次对话后调用:双方 +DIALOGUE_DELTA 友好。"""
        return self.update(a, b, DIALOGUE_DELTA)

    def record_proximity(self, a: str, b: str) -> float:
        """相遇但没对话(冷却中)后调用:双方 +PROXIMITY_DELTA 友好。"""
        return self.update(a, b, PROXIMITY_DELTA)

    def record_battle(self, winner: Optional[str], loser: Optional[str]) -> None:
        """一场战斗后调用:双方 -BATTLE_DELTA 敌对,输方对赢方 +BATTLE_AWE_DELTA 敬畏。

        winner / loser 任一为 None(平局或缺失)时,只施加基础敌对(若两方都在)。
        """
        if winner is None or loser is None or winner == loser:
            return
        # 打了一架,关系变差
        self.update(winner, loser, BATTLE_DELTA)
        # 输的一方对赢的一方生出敬畏,回一点
        self.update(winner, loser, BATTLE_AWE_DELTA)

    def reset(self) -> None:
        """抹平所有关系,回到全员中立(黑暗塔波动等灾难调用)。"""
        self._scores.clear()

    def all_pairs(self) -> list[dict[str, Any]]:
        """导出所有关系对: [{a, b, score}, ...],按 (a, b) 排序(确定性)。"""
        return [
            {"a": a, "b": b, "score": score}
            for (a, b), score in sorted(self._scores.items())
        ]


# ---- 进程级单例 ----
_tracker: Optional[RelationshipTracker] = None


def get_tracker() -> RelationshipTracker:
    """获取(或延迟初始化)关系表单例。"""
    global _tracker
    if _tracker is None:
        _tracker = RelationshipTracker()
    return _tracker


def reset_tracker() -> None:
    """重置关系表(测试用)。"""
    global _tracker
    _tracker = None
