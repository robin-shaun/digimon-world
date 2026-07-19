"""
RelationshipTracker - 数码兽社交关系 (Phase 6: 向量化)
====================================================

维护数码兽两两之间的双向关系向量 (4 维):
- affinity: 亲和度 (-100 ~ 100), 等同于旧版 affection
- rivalry: 竞争度 (0 ~ 100)
- respect: 尊重度 (0 ~ 100)
- fear: 恐惧度 (0 ~ 100)

对话 / 相遇 → affinity↑
战斗 → rivalry↑, respect↑(赢家), fear↑(输家)
共同活动 → affinity↑, respect↑

向后兼容: `affection` property 返回亲和度, `get_relationship()` 返回综合倾向。

参考 Stanford Generative Agents + WorldSeed ⭐862 设计。
"""

from __future__ import annotations

from typing import Any

# 关系值边界
MIN_SCORE: float = -100.0
MAX_SCORE: float = 100.0
MIN_AFFINITY: float = -100.0
MAX_AFFINITY: float = 100.0
MIN_NON_AFFINITY: float = 0.0   # rivalry/respect/fear 不下负值
MAX_NON_AFFINITY: float = 100.0

# 各类互动的默认增量(供 scheduler / api 引用,避免魔数散落)
DIALOGUE_DELTA: float = 3.0       # 一次对话 → 双方 +3 亲和
PROXIMITY_DELTA: float = 1.0      # 相遇但没对话(冷却中) → +1 亲和
BATTLE_RIVALRY_DELTA: float = 8.0 # 战斗 → rivalry↑
BATTLE_RESPECT_DELTA: float = 5.0 # 赢家对输家 respect↑
BATTLE_FEAR_DELTA: float = 6.0    # 输家对赢家 fear↑
# 旧常量兼容(外部引用)
BATTLE_DELTA: float = -10.0       # 旧版战斗亲和扣减(保留兼容)
BATTLE_AWE_DELTA: float = 5.0     # 旧版敬畏回补(保留兼容)

# 隐性欲望社交加成
DESIRE_BONUS_FACTOR: float = 4.0   # 欲望兼容时额外加成的系数
DESIRE_BONUS_CAP: float = 6.0      # 欲望加成上限(一次互动最多加 6 分)

# MBTI 人格兼容加成
MBTI_BONUS_FACTOR: float = 3.0     # MBTI 兼容时额外加成的系数
MBTI_BONUS_CAP: float = 4.0        # MBTI 加成上限(一次互动最多加 4 分)


def _key(a: str, b: str) -> tuple[str, str]:
    """把一对名字规范成排序后的 key,保证 (a,b) 与 (b,a) 命中同一条记录。"""
    return (a, b) if a <= b else (b, a)


class RelationshipVector:
    """四维关系向量: affinity, rivalry, respect, fear。"""

    __slots__ = ("affinity", "fear", "respect", "rivalry")

    def __init__(
        self,
        affinity: float = 0.0,
        rivalry: float = 0.0,
        respect: float = 0.0,
        fear: float = 0.0,
    ) -> None:
        self.affinity = max(MIN_AFFINITY, min(MAX_AFFINITY, affinity))
        self.rivalry = max(MIN_NON_AFFINITY, min(MAX_NON_AFFINITY, rivalry))
        self.respect = max(MIN_NON_AFFINITY, min(MAX_NON_AFFINITY, respect))
        self.fear = max(MIN_NON_AFFINITY, min(MAX_NON_AFFINITY, fear))

    def to_dict(self) -> dict[str, float]:
        return {
            "affinity": self.affinity,
            "rivalry": self.rivalry,
            "respect": self.respect,
            "fear": self.fear,
        }

    @classmethod
    def from_dict(cls, d: dict[str, float]) -> RelationshipVector:
        return cls(
            affinity=d.get("affinity", 0.0),
            rivalry=d.get("rivalry", 0.0),
            respect=d.get("respect", 0.0),
            fear=d.get("fear", 0.0),
        )

    @classmethod
    def neutral(cls) -> RelationshipVector:
        """返回全零的中立向量。"""
        return cls(0.0, 0.0, 0.0, 0.0)

    def is_neutral(self) -> bool:
        """是否完全中立(所有维度接近零)。"""
        return (
            abs(self.affinity) < 0.01
            and abs(self.rivalry) < 0.01
            and abs(self.respect) < 0.01
            and abs(self.fear) < 0.01
        )

    # ---- 向后兼容属性 ----
    @property
    def affection(self) -> float:
        """向后兼容: 返回亲和度（旧称 affection）。"""
        return self.affinity


class RelationshipTracker:
    """数码兽社交关系表:维护两两之间的四维关系向量。"""

    def __init__(self) -> None:
        # (name_a, name_b) 已排序 -> RelationshipVector
        self._vectors: dict[tuple[str, str], RelationshipVector] = {}

    # ---- 向后兼容: _scores 属性(让旧代码能通过 tracker._scores 访问) ----
    @property
    def _scores(self) -> dict[tuple[str, str], float]:
        """向后兼容: 返回亲和度映射表,支持旧代码如 tracker._scores.clear()。

        这是一个动态代理: 读取时从 _vectors 实时构建,写入时同步回 _vectors。
        注意: 赋值操作(如 tracker._scores = {}) 不支持,只支持读取和 .clear()。
        """
        return _ScoreProxy(self)

    def get_relationship(self, a: str, b: str) -> float:
        """查 a 与 b 的关系亲和度(向后兼容,等同于旧版单值亲和度)。

        从未互动过 → 0.0(中立)。自我关系恒为 0。
        """
        if a == b:
            return 0.0
        v = self._vectors.get(_key(a, b))
        if v is None:
            return 0.0
        return v.affinity

    def get_composite_score(self, a: str, b: str) -> float:
        """查 a 与 b 的综合关系倾向(四维加权得分)。

        算法: affinity * 0.4 - rivalry * 0.25 + respect * 0.2 - fear * 0.15
        范围约 [-40, 40]。
        """
        if a == b:
            return 0.0
        v = self._vectors.get(_key(a, b))
        if v is None:
            return 0.0
        return (
            v.affinity * 0.4
            - v.rivalry * 0.25
            + v.respect * 0.2
            - v.fear * 0.15
        )

    def get_vector(self, a: str, b: str) -> RelationshipVector:
        """获取 a 与 b 的四维关系向量。不存在的返回零向量。"""
        if a == b:
            return RelationshipVector.neutral()
        return self._vectors.get(_key(a, b), RelationshipVector.neutral())

    def get_interaction_bias(self, a: str, b: str) -> str:
        """返回 a 对 b 的综合互动倾向(考虑四维加权)。

        Returns:
            "friendly" / "competitive" / "fearful" / "respectful" / "neutral"
        """
        v = self.get_vector(a, b)
        if v.is_neutral():
            return "neutral"
        # 按加权得分决定倾向
        scores = {
            "friendly": v.affinity * 0.4,
            "competitive": v.rivalry * 0.35,
            "fearful": v.fear * 0.3,
            "respectful": v.respect * 0.25,
        }
        best = max(scores, key=scores.get)  # type: ignore[arg-type]
        if scores[best] < 1.0:
            return "neutral"
        return best

    # ---- 向后兼容: update() ----
    def update(self, a: str, b: str, delta: float) -> float:
        """向后兼容: 更新亲和度,返回新亲和度值。

        自我更新 (a == b) 是 no-op,返回 0.0。
        """
        if a == b:
            return 0.0
        key = _key(a, b)
        v = self._vectors.get(key)
        if v is None:
            v = RelationshipVector.neutral()
        v.affinity = max(MIN_AFFINITY, min(MAX_AFFINITY, v.affinity + delta))
        self._vectors[key] = v
        return v.affinity

    def _update_vector_dim(
        self, a: str, b: str, dim: str, delta: float, clamp_min: float, clamp_max: float
    ) -> float:
        """更新四维向量的某一维度。"""
        if a == b:
            return 0.0
        key = _key(a, b)
        v = self._vectors.get(key)
        if v is None:
            v = RelationshipVector.neutral()
        current = getattr(v, dim)
        new_val = max(clamp_min, min(clamp_max, current + delta))
        setattr(v, dim, new_val)
        self._vectors[key] = v
        return new_val

    def get_faction(self, a: str) -> dict[str, str | None]:
        """返回 a 最友好 (ally) 和最敌对 (rival) 的对象。

        - ally: 亲和度最高且 > 0 的那只;没有正亲和度 → None
        - rival: 竞争度最高且 > 0 的那只;没有正竞争度 → None
        并列时取名字字典序较小者(确定性)。
        """
        best_ally: str | None = None
        best_ally_score = 0.0
        worst_rival: str | None = None
        worst_rival_score = 0.0

        for (x, y), v in self._vectors.items():
            if a not in (x, y):
                continue
            other = y if x == a else x
            # ally: 最高亲和度
            if (v.affinity > best_ally_score or (
                v.affinity == best_ally_score and best_ally is not None and other < best_ally
            )) and v.affinity > 0:
                best_ally, best_ally_score = other, v.affinity
            # rival: 最高竞争度 · 或高度负亲和 (update() 负 delta 走 affinity 通道)
            rival_strength = max(v.rivalry, -v.affinity if v.affinity < -20 else 0.0)
            if (rival_strength > worst_rival_score or (
                rival_strength == worst_rival_score and worst_rival is not None and other < worst_rival
            )) and rival_strength > 0:
                worst_rival, worst_rival_score = other, rival_strength

        return {"ally": best_ally, "rival": worst_rival}

    # ---- 记录方法(四维) ----

    def record_dialogue(self, a: str, b: str) -> float:
        """一次对话后调用: 双方 affinity↑, respect↑。返回新亲和度。"""
        self._update_vector_dim(a, b, "affinity", DIALOGUE_DELTA, MIN_AFFINITY, MAX_AFFINITY)
        self._update_vector_dim(a, b, "respect", DIALOGUE_DELTA * 0.5, MIN_NON_AFFINITY, MAX_NON_AFFINITY)
        return self.get_vector(a, b).affinity

    def record_proximity(self, a: str, b: str) -> float:
        """相遇但没对话(冷却中)后调用: 双方 affinity 微增。返回新亲和度。"""
        self._update_vector_dim(a, b, "affinity", PROXIMITY_DELTA, MIN_AFFINITY, MAX_AFFINITY)
        return self.get_vector(a, b).affinity

    def record_battle(self, winner: str | None, loser: str | None) -> None:
        """一场战斗后调用: rivalry↑(双方), respect↑(赢对输), fear↑(输对赢)。

        winner / loser 任一为 None(平局或缺失)时,只施加 rivalry。
        """
        if winner is None or loser is None or winner == loser:
            return
        # 打了一架: 竞争度上升
        self._update_vector_dim(winner, loser, "rivalry", BATTLE_RIVALRY_DELTA, MIN_NON_AFFINITY, MAX_NON_AFFINITY)
        # 赢家: 对输家 respect 上升(惺惺相惜)
        self._update_vector_dim(winner, loser, "respect", BATTLE_RESPECT_DELTA, MIN_NON_AFFINITY, MAX_NON_AFFINITY)
        # 输家: 对赢家 fear 上升
        self._update_vector_dim(winner, loser, "fear", BATTLE_FEAR_DELTA, MIN_NON_AFFINITY, MAX_NON_AFFINITY)
        # 亲和度略微下降(打架伤感情)
        self._update_vector_dim(winner, loser, "affinity", BATTLE_DELTA, MIN_AFFINITY, MAX_AFFINITY)

    def reset(self) -> None:
        """抹平所有关系,回到全员中立(黑暗塔波动等灾难调用)。"""
        self._vectors.clear()

    def all_pairs(self) -> list[dict[str, Any]]:
        """导出所有关系对: [{a, b, score, vector}, ...],按 (a, b) 排序(确定性)。

        score 字段保留向后兼容(原始亲和度 affinity), vector 字段为新四维向量。
        """
        result: list[dict[str, Any]] = []
        for (a, b), v in sorted(self._vectors.items()):
            result.append({
                "a": a,
                "b": b,
                "score": v.affinity,  # 向后兼容: 旧代码期望原始亲和度
                "vector": v.to_dict(),
            })
        return result

    # ---- 隐性欲望(latent desire)驱动的社交倾向 ----

    # 欲望关键词匹配映射: 相同类别欲望 → 高兼容度
    _DESIRE_CATEGORIES: dict[str, set[str]] = {
        "strength": {"想变强", "渴望力量", "变强", "想成为最强", "力量"},
        "social": {"想交朋友", "想交到朋友", "交朋友", "想要朋友", "想有同伴"},
        "explore": {"想探索远方", "想冒险", "探索", "想出去看看", "想去远方"},
        "territory": {"想守护领土", "守护", "保护家园", "想保护", "领土"},
        "food": {"想吃东西", "好饿", "想吃", "找食物", "觅食"},
    }

    @staticmethod
    def desire_affinity(desire_a: str, desire_b: str) -> float:
        """计算两个隐性欲望的兼容度(0-1)。"""
        if not desire_a or not desire_b:
            return 0.0
        if desire_a == desire_b:
            return 1.0
        for keywords in RelationshipTracker._DESIRE_CATEGORIES.values():
            in_a = any(kw in desire_a for kw in keywords)
            in_b = any(kw in desire_b for kw in keywords)
            if in_a and in_b:
                return 0.6
        return 0.0

    def record_dialogue_with_desire(
        self, a_name: str, a_desire: str, b_name: str, b_desire: str,
    ) -> float:
        """一次对话后调用: 基础亲和 + 欲望兼容加成。"""
        affinity = self.desire_affinity(a_desire, b_desire)
        bonus = min(DESIRE_BONUS_FACTOR * affinity, DESIRE_BONUS_CAP)
        return self.update(a_name, b_name, DIALOGUE_DELTA + bonus)

    def record_proximity_with_desire(
        self, a_name: str, a_desire: str, b_name: str, b_desire: str,
    ) -> float:
        """相遇(未对话)后调用: 基础亲和 + 欲望兼容加成(打折)。"""
        affinity = self.desire_affinity(a_desire, b_desire)
        bonus = min(DESIRE_BONUS_FACTOR * affinity * 0.5, DESIRE_BONUS_CAP * 0.5)
        return self.update(a_name, b_name, PROXIMITY_DELTA + bonus)

    # ---- MBTI 人格兼容加成 (Phase 17 Task 4) ----

    @staticmethod
    def mbti_compatibility_bonus(mbti_a: str, mbti_b: str) -> float:
        """计算 MBTI 人格兼容度带来的关系加成值。

        调用 personality_engine 的兼容矩阵, 返回 [0, MBTI_BONUS_CAP] 的加成。
        若任一 MBTI 类型为空, 返回 0。

        Args:
            mbti_a: agent A 的 MBTI 类型码 (如 "INTJ")
            mbti_b: agent B 的 MBTI 类型码 (如 "ENFP")

        Returns:
            MBTI 兼容加成值 (0 ~ MBTI_BONUS_CAP)
        """
        if not mbti_a or not mbti_b:
            return 0.0
        try:
            from .personality_engine import get_personality_engine
            engine = get_personality_engine()
            compat = engine.compatibility(mbti_a, mbti_b)
        except Exception:
            compat = 0.5  # 出错则默认中等兼容
        return min(MBTI_BONUS_FACTOR * compat, MBTI_BONUS_CAP)

    def record_dialogue_with_personality(
        self, a_name: str, a_desire: str, b_name: str, b_desire: str,
        mbti_a: str = "", mbti_b: str = "",
    ) -> float:
        """一次对话后调用: 基础亲和 + 欲望兼容加成 + MBTI 人格加成。

        Args:
            a_name: agent A 名称
            a_desire: agent A 的隐性欲望
            b_name: agent B 名称
            b_desire: agent B 的隐性欲望
            mbti_a: agent A 的 MBTI 类型 (可选)
            mbti_b: agent B 的 MBTI 类型 (可选)

        Returns:
            更新后的亲和度
        """
        desire_aff = self.desire_affinity(a_desire, b_desire)
        desire_bonus = min(DESIRE_BONUS_FACTOR * desire_aff, DESIRE_BONUS_CAP)
        mbti_bonus = self.mbti_compatibility_bonus(mbti_a, mbti_b)
        total_bonus = desire_bonus + mbti_bonus
        return self.update(a_name, b_name, DIALOGUE_DELTA + total_bonus)

    def record_proximity_with_personality(
        self, a_name: str, a_desire: str, b_name: str, b_desire: str,
        mbti_a: str = "", mbti_b: str = "",
    ) -> float:
        """相遇(未对话)后调用: 基础亲和 + 欲望加成(打折) + MBTI 加成(打折)。

        Returns:
            更新后的亲和度
        """
        desire_aff = self.desire_affinity(a_desire, b_desire)
        desire_bonus = min(DESIRE_BONUS_FACTOR * desire_aff * 0.5, DESIRE_BONUS_CAP * 0.5)
        mbti_bonus = self.mbti_compatibility_bonus(mbti_a, mbti_b) * 0.5
        total_bonus = desire_bonus + mbti_bonus
        return self.update(a_name, b_name, PROXIMITY_DELTA + total_bonus)


# ---- _ScoreProxy: 向后兼容 tracker._scores ----

class _ScoreProxy(dict):
    """代理对象,让 tracker._scores 像旧版 dict[tuple, float] 一样工作。

    支持:
    - tracker._scores[key] = value  (写入时存为 affinity)
    - tracker._scores.get(key, default)
    - tracker._scores.items()  (迭代)
    - tracker._scores.clear()
    - for k, v in tracker._scores.items()
    """

    def __init__(self, tracker: RelationshipTracker) -> None:
        self._tracker = tracker

    # 实现 dict 接口
    def __getitem__(self, key: tuple[str, str]) -> float:
        v = self._tracker._vectors.get(key)
        return v.affinity if v else 0.0

    def __setitem__(self, key: tuple[str, str], value: float) -> None:
        v = self._tracker._vectors.get(key)
        if v is None:
            v = RelationshipVector.neutral()
        v.affinity = value
        self._tracker._vectors[key] = v

    def __delitem__(self, key: tuple[str, str]) -> None:
        del self._tracker._vectors[key]

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, tuple):
            return False
        return key in self._tracker._vectors

    def __iter__(self):
        return iter(self._tracker._vectors)

    def __len__(self) -> int:
        return len(self._tracker._vectors)

    def get(self, key: tuple[str, str], default: float = 0.0) -> float:  # type: ignore[override]
        v = self._tracker._vectors.get(key)
        return v.affinity if v else default

    def items(self):  # type: ignore[override]
        for k, v in self._tracker._vectors.items():
            yield k, v.affinity

    def clear(self) -> None:
        self._tracker._vectors.clear()

    def keys(self):  # type: ignore[override]
        return self._tracker._vectors.keys()

    def values(self):  # type: ignore[override]
        for v in self._tracker._vectors.values():
            yield v.affinity


# ---- 进程级单例 ----
_tracker: RelationshipTracker | None = None


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
