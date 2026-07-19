"""
战斗 LLM 决策 (BattleAI)
=======================

给战斗引擎提供「本回合做什么」的决策:attack / defend / flee。

设计:
- 用 HAIKU 模型(短文本、快、便宜),战斗决策是高频调用
- prompt 只喂当前双方态势(species / attribute / 双方 HP 百分比)
- 失败 fallback 到 'attack',保证战斗永远能推进(不因 LLM 挂了而卡死)
"""

from __future__ import annotations

import logging

from ..agents.digimon_agent import DigimonAgent
from ..llm.client import ChatMessage, ChatRequest, LlmClient, LlmModel

logger = logging.getLogger(__name__)

# 合法动作集合;LLM 返回值需落在这里,否则 fallback
VALID_ACTIONS: frozenset[str] = frozenset({"attack", "defend", "flee"})

# 决策失败时的兜底动作
FALLBACK_ACTION: str = "attack"


def _build_mbti_strategy(profile) -> str:
    """根据 MBTI 人格档案生成战斗策略提示。"""
    hints: list[str] = []
    # EI 维度: E=主动攻击, I=防守反击
    if profile.ei >= 0.2:
        hints.append("倾向主动攻击")
    elif profile.ei <= -0.2:
        hints.append("倾向防守反击")
    # TF 维度: T=理性计算, F=凭直觉
    if profile.tf >= 0.2:
        hints.append("偏好理性计算伤害和防御时机")
    elif profile.tf <= -0.2:
        hints.append("容易凭直觉冲锋或提前撤退")
    # JP 维度: J=果断, P=灵活试探
    if profile.jp >= 0.2:
        hints.append("果断决策，不犹豫")
    elif profile.jp <= -0.2:
        hints.append("灵活应变，倾向试探")
    if hints:
        return f"你的战斗风格({profile.type_code}): " + "、".join(hints) + "。"
    return ""


async def decide_action(
    client: LlmClient,
    actor: DigimonAgent,
    opponent: DigimonAgent,
    hp_pct_self: float,
    hp_pct_opp: float,
) -> str:
    """让 actor 用 LLM 决定本回合动作。

    Args:
        client: LLM 客户端(满足 LlmClient 协议)
        actor: 决策方
        opponent: 对手
        hp_pct_self: actor 当前 HP 百分比(0.0-1.0)
        hp_pct_opp: opponent 当前 HP 百分比(0.0-1.0)

    Returns:
        'attack' / 'defend' / 'flee' 之一;任何异常都兜底为 'attack'。
    """
    # 获取 MBTI 战斗策略提示
    mbti_hint = ""
    try:
        from ..world.personality_engine import get_personality_engine
        engine = get_personality_engine()
        profile = engine.get(actor.name)
        if profile and profile.type_code:
            mbti_hint = _build_mbti_strategy(profile)
    except Exception:
        pass

    prompt = (
        f"你是{actor.name}({actor.species}, 属性 {actor.attribute.value}). "
        f"对手是{opponent.name}({opponent.species}). "
        f"你 HP {hp_pct_self:.0%}, 对手 HP {hp_pct_opp:.0%}. "
        f"{mbti_hint + ' ' if mbti_hint else ''}"
        f"请决定一个动作: attack / defend / flee. 简短回复, 一个词."
    )

    try:
        req = ChatRequest(
            messages=[ChatMessage(role="user", content=prompt)],
            model=LlmModel.MINIMAX_M3,
            max_tokens=16,
            temperature=0.7,
        )
        resp = await client.complete(req)
        action = _normalize(resp.content)
        if action is not None:
            return action
        logger.warning("LLM 决策返回无法识别的动作 %r,兜底为 %s", resp.content, FALLBACK_ACTION)
    except Exception as e:  # 网络 / 解析 / 任何异常都不该让战斗卡死
        logger.warning("LLM 决策失败(%s),兜底为 %s", e, FALLBACK_ACTION)

    return FALLBACK_ACTION


def _normalize(raw: str) -> str | None:
    """把 LLM 的自由文本回复归一到合法动作;无法匹配返回 None。"""
    text = raw.strip().lower()
    # 先精确命中
    if text in VALID_ACTIONS:
        return text
    # 再做包含匹配(应对 "我选择 attack。" 这类啰嗦回复)
    for act in VALID_ACTIONS:
        if act in text:
            return act
    return None
