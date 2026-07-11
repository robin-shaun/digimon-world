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

        prompt = (
            f"我是{agent_a.name}，遇到{agent_b.name}了。"
            f"我最近在：{a_mem}。{agent_b.name}最近在：{b_mem}。"
            f"我想对{agent_b.name}说一句话（简短、像数码宝贝动画里的台词）。"
        )

        try:
            req = ChatRequest(
                messages=[
                    ChatMessage(
                        role="system",
                        content=f"你是一只数码宝贝，名字叫{agent_a.name}（{agent_a.species}）。你生活在数码世界，性格鲜明。说话简短直接，像动画角色。",
                    ),
                    ChatMessage(role="user", content=prompt),
                ],
                model=LlmModel.MINIMAX_TEXT_01,
                max_tokens=60,
                temperature=0.9,
            )
            resp = await self._llm.complete(req)
            line = resp.content.strip()
            if not line:
                return FALLBACK_LINE
            return line
        except Exception:
            logger.debug("Dialogue: LLM 调用失败,使用 fallback", exc_info=True)
            return FALLBACK_LINE
