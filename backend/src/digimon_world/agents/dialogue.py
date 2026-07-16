"""
Dialogue - 数码兽对话生成器
============================

当两只数码兽靠得足够近(见 world.interactions.detect_proximity),
调用 LLM 生成一句符合数码兽人设的对话。

参考 Stanford Generative Agents 的 converse:他们让两个 persona 各自带着
记忆和当前情境去生成台词。这里简化为一次调用生成一句(不做多轮往返),
成本低、够热闹。

设计要点:
- 用 Haiku 4.5(便宜,对话不需要太聪明)
- async,不阻塞调度主循环
- LLM 失败 → 返回 fallback '... (沉默)',绝不抛异常打断 tick
- Phase 17: 注入 MBTI 人格影响对话语气
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from ..llm.client import ChatMessage, ChatRequest, LlmClient, LlmModel

if TYPE_CHECKING:
    from .digimon_agent import DigimonAgent

logger = logging.getLogger(__name__)

# LLM 失败时的兜底台词
FALLBACK_LINE = "... (沉默)"

# 取每只数码兽最近 N 条记忆作为对话素材
RECENT_MEMORY_COUNT = 3

# MBTI 类型 → 中文维度描述
_MBTI_LABELS: dict[str, str] = {
    "E": "外向", "I": "内向",
    "S": "感觉", "N": "直觉",
    "T": "思考", "F": "情感",
    "J": "判断", "P": "感知",
}

# 16 种 MBTI 类型 → 对话风格提示
_MBTI_STYLE: dict[str, str] = {
    "INTJ": "冷静策略、简洁直接",
    "INTP": "冷静分析、逻辑探索",
    "ENTJ": "果断指挥、战略主导",
    "ENTP": "活泼辩论、好奇探索",
    "INFJ": "深思熟虑、温和引导",
    "INFP": "内心丰富、理想主义",
    "ENFJ": "热情鼓舞、关注他人",
    "ENFP": "热情探索、创意表达",
    "ISTJ": "稳重务实、秩序优先",
    "ISFJ": "温和守护、细致关怀",
    "ESTJ": "果断务实、效率优先",
    "ESFJ": "热情关怀、和谐优先",
    "ISTP": "冷静实操、灵活应对",
    "ISFP": "温和艺术、感性体验",
    "ESTP": "大胆行动、冒险精神",
    "ESFP": "热情活力、感性表达",
}


def _build_mbti_tone_line(name: str, type_code: str) -> str:
    """根据 MBTI 类型生成对话语气提示。"""
    desc = "".join(_MBTI_LABELS.get(c, c) for c in type_code)
    style = _MBTI_STYLE.get(type_code, "")
    if style:
        return f"你的MBTI人格: {type_code}({desc})。说话风格: {style}。"
    return f"你的MBTI人格: {type_code}({desc})。"


class Dialogue:
    """对话生成器,接受 LlmClient,为一对相遇的数码兽生成一句对话。

    用法:
        dialogue = Dialogue(llm_client=client)
        line = await dialogue.generate_dialogue(agent_a, agent_b, context_events)
    """

    def __init__(self, llm_client: LlmClient) -> None:
        self._llm = llm_client

    @staticmethod
    def _recent_memory_text(agent: "DigimonAgent") -> str:
        """取 agent 最近几条记忆,拼成一行文本。无记忆返回 '无'。"""
        recent = agent.memory.entries[-RECENT_MEMORY_COUNT:]
        if not recent:
            return "无"
        return "; ".join(m.description for m in recent)

    async def generate_dialogue(
        self,
        agent_a: "DigimonAgent",
        agent_b: "DigimonAgent",
        context_events: list[dict[str, Any]] | None = None,
    ) -> str:
        """为相遇的 agent_a / agent_b 生成一句对话(由 agent_a 开口)。

        Args:
            agent_a: 开口说话的一方
            agent_b: 被搭话的一方
            context_events: 最近的世界事件(可选,给 LLM 更多情境)

        Returns:
            对话字符串。LLM 失败时返回 FALLBACK_LINE。
        """
        a_mem = self._recent_memory_text(agent_a)
        b_mem = self._recent_memory_text(agent_b)
        # 获取说话者的 MBTI 人格,注入对话语气提示
        mbti_tone_line = ""
        try:
            from ..world.personality_engine import get_personality_engine  # noqa: PLC0415
            engine = get_personality_engine()
            profile = engine.get(agent_a.name)
            if profile and profile.type_code:
                mbti_tone_line = _build_mbti_tone_line(agent_a.name, profile.type_code)
        except Exception:
            pass

        system_content = (
            f"你是{agent_a.name}，一只数码宝贝。"
            + (f"{mbti_tone_line} " if mbti_tone_line else "")
            + "只输出你口中说出的一句台词，不要旁白、不要选项、不要引号。"
        )

        prompt = (
            f"我是{agent_a.name}，遇到{agent_b.name}了。"
            f"我最近在：{a_mem}。{agent_b.name}最近在：{b_mem}。"
            f"我想对{agent_b.name}说一句话（简短、像数码宝贝动画里的台词）。"
        )

        try:
            req = ChatRequest(
                messages=[
                    ChatMessage(role="system", content=system_content),
                    ChatMessage(role="user", content=prompt),
                ],
                model=LlmModel.MINIMAX_TEXT_01,
                max_tokens=30,
                temperature=0.7,
            )
            resp = await self._llm.complete(req)
            line = resp.content.strip()
            if not line:
                return FALLBACK_LINE
            return line
        except Exception:
            logger.debug("Dialogue: LLM 调用失败,使用 fallback", exc_info=True)
            return FALLBACK_LINE
