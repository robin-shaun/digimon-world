"""
Planner - 计划生成器
====================

参考 Stanford Generative Agents (Park et al., 2023) 的 planning 机制:
根据 agent 的记忆、反思和当前世界状态,生成下一段具体行动计划。

设计要点:
- 简化版: 直接生成 1-2 句计划字符串,不分层
- 用 Haiku 4.5 (便宜,计划不需要太聪明)
- async,不阻塞 agent 主循环
- LLM 失败 → 返回 fallback 字符串,不抛异常
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..llm.client import ChatMessage, ChatRequest, LlmClient, LlmModel

if TYPE_CHECKING:
    from .digimon_agent import DigimonAgent

logger = logging.getLogger(__name__)

FALLBACK_PLAN = "在附近闲逛, 保持警觉"


class Planner:
    """计划生成器,接受 LlmClient,根据 agent 状态生成下一段行动计划。

    用法:
        planner = Planner(llm_client=client)
        plan = await planner.plan(agent, world_state_snapshot={...})
    """

    # 取最近 N 条记忆作为计划素材
    RECENT_MEMORY_COUNT = 10
    # 取最近 N 条反思
    RECENT_REFLECTION_COUNT = 3

    def __init__(self, llm_client: LlmClient) -> None:
        self._llm = llm_client

    async def plan(
        self, agent: DigimonAgent, world_state_snapshot: dict
    ) -> str:
        """根据 agent 记忆、反思和世界状态,生成下一段计划(1-2 句)。

        Returns:
            计划字符串。LLM 失败时返回 fallback。
        """
        # 取最近记忆
        recent_memories = agent.memory.entries[-self.RECENT_MEMORY_COUNT:]
        memories_text = "\n".join(
            f"- {m.description}" for m in recent_memories
        ) if recent_memories else "无"

        # 取最近反思(memory_type == 'reflection')
        reflections = [
            m for m in agent.memory.entries if m.memory_type == "reflection"
        ][-self.RECENT_REFLECTION_COUNT:]
        reflections_text = "\n".join(
            f"- {m.description}" for m in reflections
        ) if reflections else "无"

        # 隐性渴望: 反思时浮现的内心目标,非空时注入 prompt 影响行动倾向。
        # 强烈度越高越应主导计划,这里把强烈度也一并透传给 LLM 参考。
        desire_line = ""
        if agent.latent_desire:
            desire_line = (
                f"你的内心渴望: {agent.latent_desire} "
                f"(强烈度 {agent.desire_strength:.1f})\n"
            )

        # 个性特征: 影响行动倾向
        personality_line = ""
        personality_summary = agent.get_personality_summary()
        if personality_summary:
            personality_line = personality_summary + "\n"
        # 获取 MBTI 人格类型,注入规划 prompt
        try:
            from ..world.personality_engine import get_personality_engine
            engine = get_personality_engine()
            profile = engine.get(agent.name)
            if profile and profile.type_code:
                mbti_type = profile.type_code
                ei_label = "外向" if mbti_type[0] == "E" else "内向"
                jp_label = "计划" if mbti_type[3] == "J" else "灵活"
                personality_line += f"你的MBTI人格: {mbti_type}，倾向以{ei_label}{jp_label}方式行动\n"
        except Exception:
            pass

        # 构造 prompt
        prompt = (
            f"你是{agent.name}({agent.species}), "
            f"当前在{agent.region_id}。\n"
            f"你的状态: HP={agent.stats.hp}/100, "
            f"EP={agent.stats.ep}/50, "
            f"心情={agent.mood}\n"
            f"{desire_line}"
            f"{personality_line}"
            f"最近记忆:\n{memories_text}\n"
            f"最近的反思:\n{reflections_text}\n"
            f"当前世界: {world_state_snapshot}\n"
            f"请根据你的性格特点生成下一段计划 (1-2 句, 中文, 具体行动)."
        )

        try:
            req = ChatRequest(
                messages=[
                    ChatMessage(
                        role="system",
                        content="你是数码兽的行动计划生成器。只输出计划本身,不要加解释。",
                    ),
                    ChatMessage(role="user", content=prompt),
                ],
                model=LlmModel.MINIMAX_M3,
                max_tokens=100,
                temperature=0.7,
            )
            resp = await self._llm.complete(req)
            plan_text = resp.content.strip()
            if not plan_text:
                return FALLBACK_PLAN
            return plan_text
        except Exception:
            logger.debug("Planner: LLM 调用失败,使用 fallback", exc_info=True)
            return FALLBACK_PLAN
