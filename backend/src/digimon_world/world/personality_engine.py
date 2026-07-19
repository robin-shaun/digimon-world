"""
人格引擎 (Personality Engine) — 基于荣格心理学 MBTI 的动态人格系统
==================================================================

受 GitHub trending 项目 `evolving_personality` (agent-topia, 1,199⭐) 启发，
为每只数码兽赋予 MBTI 四维度动态人格，人格随经历漂移并影响行为。

MBTI 四维度:
  E/I — 外倾/内倾 (Extraversion / Introversion)
  S/N — 感觉/直觉 (Sensing / Intuition)
  T/F — 思考/情感 (Thinking / Feeling)
  J/P — 判断/感知 (Judging / Perceiving)

每维度是连续值 [-1.0, 1.0]，正值=第一极，负值=第二极。
人格类型由四维度符号组合 (如 INTJ, ENFP)。

动态演化:
  - 战斗胜利 → +E, +T (更外向、更理性)
  - 社交成功 → +E, +F (更外向、更感性)
  - 探索发现 → +N, +P (更直觉、更灵活)
  - 长期独处 → -E, -J (更内向、更随性)
  - 进化 → 维度微调 (向物种典型方向漂移)

兼容矩阵: 基于传统 MBTI 伴侣兼容理论，某些类型配对有天然亲和度。
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ---- 维度枚举 ----

class MbtiDimension(Enum):
    """MBTI 四维度。"""
    EI = "ei"  # Extraversion / Introversion
    SN = "sn"  # Sensing / Intuition
    TF = "tf"  # Thinking / Feeling
    JP = "jp"  # Judging / Perceiving

    def positive_label(self) -> str:
        _pos = {"ei": "E 外倾", "sn": "S 感觉", "tf": "T 思考", "jp": "J 判断"}
        return _pos[self.value]

    def negative_label(self) -> str:
        _neg = {"ei": "I 内倾", "sn": "N 直觉", "tf": "F 情感", "jp": "P 感知"}
        return _neg[self.value]

    def letter(self, value: float) -> str:
        """给定连续值，返回 MBTI 字母 (正值=第一极)。"""
        return self.positive_label()[0] if value >= 0 else self.negative_label()[0]


# ---- 人格档案 ----

@dataclass
class PersonalityProfile:
    """数码兽人格档案 — 四维连续值 + 类型 + 演化历史。"""

    # 四维连续值 [-1.0, 1.0]
    ei: float = 0.0  # + = E 外倾, - = I 内倾
    sn: float = 0.0  # + = S 感觉, - = N 直觉
    tf: float = 0.0  # + = T 思考, - = F 情感
    jp: float = 0.0  # + = J 判断, - = P 感知

    # 人格类型字符串 (如 "INTJ", "ENFP")
    type_code: str = ""

    # 各维度强度 [0, 1] (绝对值)
    ei_strength: float = 0.0
    sn_strength: float = 0.0
    tf_strength: float = 0.0
    jp_strength: float = 0.0

    # 演化历史
    history: list[dict[str, Any]] = field(default_factory=list)

    # 元数据
    created_at: str = ""
    updated_at: str = ""
    evolution_count: int = 0

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at
        self._recompute()

    def _recompute(self) -> None:
        """重新计算类型代码和强度。"""
        self.type_code = (
            MbtiDimension.EI.letter(self.ei)
            + MbtiDimension.SN.letter(self.sn)
            + MbtiDimension.TF.letter(self.tf)
            + MbtiDimension.JP.letter(self.jp)
        )
        self.ei_strength = abs(self.ei)
        self.sn_strength = abs(self.sn)
        self.tf_strength = abs(self.tf)
        self.jp_strength = abs(self.jp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ei": round(self.ei, 4),
            "sn": round(self.sn, 4),
            "tf": round(self.tf, 4),
            "jp": round(self.jp, 4),
            "type_code": self.type_code,
            "strengths": {
                "ei": round(self.ei_strength, 4),
                "sn": round(self.sn_strength, 4),
                "tf": round(self.tf_strength, 4),
                "jp": round(self.jp_strength, 4),
            },
            "history": self.history[-10:],  # 最近10条
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "evolution_count": self.evolution_count,
        }

    def dominant_dimension(self) -> str:
        """返回最强的维度名。"""
        strengths = {
            "ei": self.ei_strength,
            "sn": self.sn_strength,
            "tf": self.tf_strength,
            "jp": self.jp_strength,
        }
        return max(strengths, key=lambda k: strengths[k])

    def is_clear_type(self) -> bool:
        """判断是否为清晰类型 (所有维度强度 > 0.3)。"""
        return all(
            s > 0.3
            for s in [self.ei_strength, self.sn_strength, self.tf_strength, self.jp_strength]
        )


# ---- 人格兼容矩阵 ----

# MBTI 兼容度矩阵: 基于传统 MBTI 伴侣兼容理论
# 兼容度高 = 互补或相似但不冲突的类型配对
# 值范围 [0, 1]: 1 = 最佳兼容, 0 = 天然冲突
MBTI_COMPATIBILITY: dict[str, dict[str, float]] = {
    # ENFP - 外向直觉情感感知 (热情探索者)
    "ENFP": {"INTJ": 1.0, "INFJ": 0.9, "ENFJ": 0.8, "ENTJ": 0.7, "INFP": 0.7,
             "ENTP": 0.7, "ENFP": 0.7, "INTP": 0.5, "ISFP": 0.5, "ESFP": 0.5,
             "ISTJ": 0.3, "ESTJ": 0.3, "ISFJ": 0.3, "ESFJ": 0.3, "ESTP": 0.2, "ISTP": 0.2},
    # INTJ - 内向直觉思考判断 (战略大师)
    "INTJ": {"ENFP": 1.0, "ENTP": 1.0, "INTP": 0.8, "INFJ": 0.8, "ENTJ": 0.8,
             "INTJ": 0.7, "ISTJ": 0.5, "ESTJ": 0.5, "ISTP": 0.5, "INFP": 0.5,
             "ENFJ": 0.4, "ISFP": 0.3, "ESFP": 0.3, "ISFJ": 0.2, "ESFJ": 0.2, "ESTP": 0.2},
    # INTP - 内向直觉思考感知 (逻辑学家)
    "INTP": {"ENTJ": 1.0, "ESTJ": 0.9, "INTJ": 0.8, "ENTP": 0.8, "INTP": 0.7,
             "ISTJ": 0.7, "INFJ": 0.6, "ENFJ": 0.5, "ISTP": 0.5, "ESTP": 0.5,
             "ENFP": 0.5, "INFP": 0.4, "ISFJ": 0.3, "ESFJ": 0.3, "ISFP": 0.2, "ESFP": 0.2},
    # INFJ - 内向直觉情感判断 (提倡者)
    "INFJ": {"ENFP": 0.9, "ENTP": 0.9, "INTJ": 0.8, "ENFJ": 0.8, "INFP": 0.8,
             "INFJ": 0.7, "INTP": 0.6, "ISFP": 0.5, "ESFP": 0.5, "ENTJ": 0.5,
             "ISTJ": 0.3, "ESTJ": 0.3, "ISFJ": 0.3, "ESFJ": 0.3, "ISTP": 0.2, "ESTP": 0.2},
    # ENTP - 外向直觉思考感知 (辩论家)
    "ENTP": {"INTJ": 1.0, "INFJ": 0.9, "INTP": 0.8, "ENTJ": 0.8, "ENTP": 0.7,
             "ENFP": 0.7, "ENFJ": 0.7, "INFP": 0.7, "ESTJ": 0.5, "ISTJ": 0.5,
             "ESTP": 0.4, "ISTP": 0.4, "ISFJ": 0.3, "ESFJ": 0.3, "ISFP": 0.2, "ESFP": 0.2},
    # ENTJ - 外向直觉思考判断 (指挥官)
    "ENTJ": {"INTP": 1.0, "INFP": 1.0, "INTJ": 0.8, "ENTP": 0.8, "ESTP": 0.7,
             "ENTJ": 0.7, "ISTP": 0.6, "ISTJ": 0.5, "ENFJ": 0.5, "ENFP": 0.5,
             "ESTJ": 0.4, "INFJ": 0.4, "ISFP": 0.3, "ESFP": 0.3, "ISFJ": 0.2, "ESFJ": 0.2},
    # ISTJ - 内向感觉思考判断 (物流师)
    "ISTJ": {"ESFP": 1.0, "ESTP": 0.9, "ISFJ": 0.8, "ESTJ": 0.8, "ISTJ": 0.7,
             "ISFP": 0.7, "ESFJ": 0.6, "INTP": 0.5, "ENTP": 0.5, "INTJ": 0.5,
             "ENTJ": 0.4, "ENFP": 0.4, "INFP": 0.3, "ENFJ": 0.3, "INFJ": 0.2, "ISTP": 0.2},
    # ISFJ - 内向感觉情感判断 (守护者)
    "ISFJ": {"ESFP": 1.0, "ESTP": 0.9, "ISTJ": 0.8, "ESTJ": 0.8, "ISFJ": 0.7,
             "ISFP": 0.7, "ESFJ": 0.6, "INFP": 0.5, "ENFP": 0.5, "ENFJ": 0.5,
             "INFJ": 0.4, "INTP": 0.3, "ENTP": 0.3, "INTJ": 0.2, "ENTJ": 0.2, "ISTP": 0.2},
}

# 默认回退兼容度 (不在矩阵中的配对)
_DEFAULT_COMPATIBILITY = 0.5


# ---- 演化引擎 ----

class PersonalityEvolutionEngine:
    """人格动态演化引擎。

    处理战斗、社交、探索、进化等事件对 MBTI 四维度的影响。
    维度变化有惯性 (防止剧烈震荡) 和回归均值 (防止极端化)。
    """

    # 各事件类型的维度影响向量 (delta)
    EVENT_IMPACTS: dict[str, dict[str, float]] = {  # noqa: RUF012
        "battle_win":         {"ei": +0.03, "sn": +0.01, "tf": +0.04, "jp": +0.02},
        "battle_loss":        {"ei": -0.02, "sn": +0.01, "tf": +0.02, "jp": -0.01},
        "battle_draw":        {"ei": +0.01, "sn": +0.00, "tf": +0.01, "jp": +0.00},
        "social_friendly":    {"ei": +0.03, "sn": -0.01, "tf": -0.03, "jp": +0.01},
        "social_conflict":    {"ei": -0.01, "sn": +0.01, "tf": +0.02, "jp": -0.02},
        "explore_discovery":  {"ei": -0.01, "sn": -0.03, "tf": +0.01, "jp": -0.03},
        "alone_time":         {"ei": -0.04, "sn": +0.01, "tf": +0.01, "jp": -0.02},
        "evolution":          {"ei": +0.02, "sn": +0.02, "tf": +0.02, "jp": +0.02},
        "narrative_moment":   {"ei": +0.01, "sn": -0.02, "tf": -0.02, "jp": +0.01},
        "injury":             {"ei": -0.02, "sn": +0.00, "tf": +0.01, "jp": +0.01},
        "save_other":         {"ei": +0.04, "sn": -0.01, "tf": -0.04, "jp": +0.02},
    }

    def __init__(
        self,
        evolution_rate: float = 1.0,
        regression_strength: float = 0.001,
        max_abs_dimension: float = 1.0,
    ):
        """
        Args:
            evolution_rate: 全局演化速率乘数 (默认 1.0)
            regression_strength: 回归均值强度 (防止极端化，0=无回归)
            max_abs_dimension: 维度值上限 (默认 1.0)
        """
        self.evolution_rate = evolution_rate
        self.regression_strength = regression_strength
        self.max_abs_dimension = max_abs_dimension
        self._profiles: dict[str, PersonalityProfile] = {}

    # ---- CRUD ----

    def get(self, agent_name: str) -> PersonalityProfile | None:
        return self._profiles.get(agent_name)

    def get_or_create(self, agent_name: str) -> PersonalityProfile:
        if agent_name not in self._profiles:
            profile = self._random_initial_profile()
            self._profiles[agent_name] = profile
            logger.info("PersonalityEngine: 为 %s 初始化人格 %s", agent_name, profile.type_code)
        return self._profiles[agent_name]

    def set(self, agent_name: str, profile: PersonalityProfile) -> None:
        """手动设置人格档案（如从持久化恢复）。"""
        self._profiles[agent_name] = profile

    def list_all(self) -> list[tuple[str, PersonalityProfile]]:
        return list(self._profiles.items())

    def reset(self) -> None:
        self._profiles.clear()

    # ---- 演化 ----

    def apply_event(
        self,
        agent_name: str,
        event_type: str,
        *,
        multiplier: float = 1.0,
        description: str = "",
    ) -> PersonalityProfile:
        """对 agent 应用事件影响，返回更新后的人格档案。

        Args:
            agent_name: 数码兽名称
            event_type: 事件类型 (见 EVENT_IMPACTS 的 key)
            multiplier: 影响乘数 (如重大事件可设为 2.0)
            description: 事件描述 (记录到演化历史)

        Returns:
            更新后的人格档案
        """
        profile = self.get_or_create(agent_name)
        impacts = self.EVENT_IMPACTS.get(event_type)
        if impacts is None:
            logger.warning("PersonalityEngine: 未知事件类型 '%s'，跳过", event_type)
            return profile

        # 施加维度变化
        dims = ["ei", "sn", "tf", "jp"]
        for dim in dims:
            delta = impacts.get(dim, 0.0) * multiplier * self.evolution_rate
            setattr(profile, dim, self._clamp(getattr(profile, dim) + delta))

        # 回归均值
        for dim in dims:
            current = getattr(profile, dim)
            regression = -current * self.regression_strength * self.evolution_rate
            setattr(profile, dim, self._clamp(current + regression))

        # 记录历史
        profile.history.append({
            "event": event_type,
            "desc": description,
            "multiplier": multiplier,
            "result_type": profile.type_code,
            "result_ei": round(profile.ei, 4),
            "result_sn": round(profile.sn, 4),
            "result_tf": round(profile.tf, 4),
            "result_jp": round(profile.jp, 4),
            "time": datetime.now().isoformat(),
        })

        # 裁剪历史
        if len(profile.history) > 100:
            profile.history = profile.history[-100:]

        profile.evolution_count += 1
        profile.updated_at = datetime.now().isoformat()
        profile._recompute()

        logger.debug(
            "PersonalityEngine: %s 经历 '%s' → %s (EI=%.2f SN=%.2f TF=%.2f JP=%.2f)",
            agent_name, event_type, profile.type_code,
            profile.ei, profile.sn, profile.tf, profile.jp,
        )
        return profile

    # ---- 兼容性 ----

    def compatibility(self, type_a: str, type_b: str) -> float:
        """计算两种 MBTI 类型的兼容度 [0, 1]."""
        if type_a == type_b:
            return 0.7  # 同类型: 中等兼容 (能互相理解但缺乏互补)
        row = MBTI_COMPATIBILITY.get(type_a, {})
        return row.get(type_b, _DEFAULT_COMPATIBILITY)

    def agent_compatibility(self, name_a: str, name_b: str) -> float:
        """计算两只数码兽的人格兼容度。"""
        p_a = self.get(name_a)
        p_b = self.get(name_b)
        if p_a is None or p_b is None:
            return _DEFAULT_COMPATIBILITY
        return self.compatibility(p_a.type_code, p_b.type_code)

    # ---- 内部 ----

    def _random_initial_profile(self) -> PersonalityProfile:
        """随机生成初始人格档案。"""
        # 使用正态分布，大多数值在 [-0.7, 0.7] 之间
        def _random_dim() -> float:
            return self._clamp(random.gauss(0.0, 0.4))

        profile = PersonalityProfile(
            ei=_random_dim(),
            sn=_random_dim(),
            tf=_random_dim(),
            jp=_random_dim(),
        )
        profile._recompute()
        return profile

    def _clamp(self, value: float) -> float:
        """将维度值限制在 [-max, max] 范围内。"""
        return max(-self.max_abs_dimension, min(self.max_abs_dimension, value))


# ---- 全局单例 ----

_engine: PersonalityEvolutionEngine | None = None


def get_personality_engine() -> PersonalityEvolutionEngine:
    """获取全局人格引擎单例。"""
    global _engine
    if _engine is None:
        _engine = PersonalityEvolutionEngine()
    return _engine


def reset_personality_engine() -> None:
    """重置全局人格引擎。"""
    global _engine
    _engine = None
