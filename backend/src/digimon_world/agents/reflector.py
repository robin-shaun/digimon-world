"""
Reflector - 反思生成器
======================

参考 Stanford Generative Agents (Park et al., 2023) 的 reflection 机制:
当 MemoryStream.importance_sum 超过阈值时,调用 LLM 生成高级抽象反思,
写回 memory_stream 作为 memory_type='reflection' 的记忆。

设计要点:
- 用 Haiku 4.5 (成本低,反思不需要太聪明)
- async,不阻塞 agent 主循环
- LLM 失败 / JSON 解析失败 → 静默返回 None,不抛异常
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from ..llm.client import ChatMessage, ChatRequest, ChatResponse, LlmClient, LlmModel

if TYPE_CHECKING:
    from .digimon_agent import DigimonAgent

logger = logging.getLogger(__name__)


@dataclass
class Reflection:
    """一次反思的结果。

    除高级抽象文本外,还携带本轮反思浮现出的"隐性渴望"
    (latent desire) —— 一句 10 字以内的内心独白,以及它的强烈度
    (0-1)。同一次 reflect() 产出的多条 Reflection 共享同一个 desire。
    """

    text: str
    generated_at: datetime
    source_memories: list[int] = field(default_factory=list)
    desire: str = ""
    desire_strength: float = 0.0


class Reflector:
    """反思生成器,接受 LlmClient,从 agent 的记忆中提取高级抽象。

    用法:
        reflector = Reflector(llm_client=client)
        reflection = await reflector.reflect(agent)
    """

    # 取最近 N 条记忆作为反思素材
    RECENT_MEMORY_COUNT = 20

    def __init__(self, llm_client: LlmClient) -> None:
        self._llm = llm_client

    async def reflect(self, agent: "DigimonAgent") -> list[Reflection] | None:
        """从 agent 最近记忆生成 1-3 条高级抽象反思。

        Returns:
            反思列表,或 None(LLM 失败 / 解析失败 / 无记忆时）
        """
        # 无记忆 → 不调 LLM
        if not agent.memory.entries:
            return None

        # 取最近 N 条
        recent = agent.memory.entries[-self.RECENT_MEMORY_COUNT:]
        source_ids = [m.node_id for m in recent if m.node_id is not None]

        # 构造 prompt
        memories_text = "\n".join(
            f"- [{m.memory_type}] {m.description}" for m in recent
        )
        # 加入当前情绪状态
        mood_context = ""
        if agent.mood_state:
            mood_dims = ", ".join(
                f"{dim}={val:.2f}" for dim, val in sorted(agent.mood_state.items())
            )
            mood_context = f"\n当前情绪状态: {{{mood_dims}}}"
        prompt = (
            f"基于以下{agent.name}的最近记忆,生成 1-3 条高级抽象反思。\n"
            f"记忆列表:\n{memories_text}{mood_context}\n\n"
            f"请也生成一句内心渴望(10字以内, 如 想变强/想交朋友/想探索远方),"
            f"以及它的强烈度(0-1 之间的小数)。\n"
            f'请输出 JSON: {{"reflections": ["反思1", "反思2"], '
            f'"desire": "想变强", "desire_strength": 0.7}}'
        )

        try:
            req = ChatRequest(
                messages=[
                    ChatMessage(role="system", content="你是数码兽的内心独白生成器。"),
                    ChatMessage(role="user", content=prompt),
                ],
                model=LlmModel.MINIMAX_M3,
                max_tokens=512,
                temperature=0.7,
            )
            resp: ChatResponse = await self._llm.complete(req)
            reflections = self._parse_response(resp.content, source_ids)
        except Exception:
            logger.debug("Reflector: LLM 调用或解析失败,静默跳过", exc_info=True)
            return None

        if not reflections:
            return None

        # 写回 agent.memory
        for ref in reflections:
            agent.memory.add(
                event=ref.text,
                importance=8,
                memory_type="reflection",
            )

        return reflections

    def _parse_response(
        self, content: str, source_ids: list[int]
    ) -> list[Reflection]:
        """解析 LLM 返回的 JSON,容错处理。"""
        # 尝试提取 JSON（LLM 可能在 JSON 前后加文字）
        start = content.find("{")
        end = content.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError(f"无法在 LLM 输出中找到 JSON: {content[:100]}")

        data = json.loads(content[start:end])
        texts = data.get("reflections", [])

        if not isinstance(texts, list):
            raise ValueError(f"reflections 字段不是 list: {type(texts)}")

        # 隐性渴望: 可缺省(旧 prompt / 简单回复),缺省时用空串 + 0.0
        desire = str(data.get("desire", "") or "").strip()
        desire_strength = self._coerce_strength(data.get("desire_strength", 0.0))

        now = datetime.utcnow()
        return [
            Reflection(
                text=str(t),
                generated_at=now,
                source_memories=source_ids,
                desire=desire,
                desire_strength=desire_strength,
            )
            for t in texts
            if t  # 跳过空字符串
        ]

    @staticmethod
    def _coerce_strength(value: object) -> float:
        """把 LLM 返回的 desire_strength 夹紧到 [0, 1];无法解析则 0.0。"""
        try:
            return max(0.0, min(1.0, float(value)))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.0
