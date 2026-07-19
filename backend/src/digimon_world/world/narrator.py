"""NarratorSystem - 世界叙事引擎。每 N tick 收集重大事件 → LLM 写故事摘要。

设计要点:
- 单例模式 (get_narrator / reset_narrator)，与其他世界系统一致。
- 每 narration_interval tick 从 TimelineSystem 收集重大事件。
- 调用 MiniMax Text-01 (支持角色扮演) 生成故事摘要。
- LLM 失败时优雅降级，不崩溃。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .timeline import TimelineSystem
    from .world_state import WorldState

logger = logging.getLogger(__name__)


class NarratorSystem:
    """世界叙事引擎: 每 N tick 收集重大事件 → LLM 写故事摘要。"""

    def __init__(self, interval: int = 100) -> None:
        self.journal: list[dict[str, Any]] = []
        self.narration_interval = interval
        self._tick_counter: int = 0
        self._last_narrated_at: int = 0

    @property
    def narration_count(self) -> int:
        """已生成的叙事篇数。"""
        return len(self.journal)

    def tick(
        self,
        world: WorldState | None,
        timeline_system: TimelineSystem | None,
    ) -> dict[str, Any] | None:
        """每次世界 tick 调用。到达叙事间隔时收集事件并生成叙事。

        Args:
            world: 世界状态 (可为 None,测试时跳过)。
            timeline_system: 时间线系统,用于过滤重大事件。

        Returns:
            生成的叙事 dict 或 None (未到间隔 / 无事件 / 降级)。
        """
        self._tick_counter += 1
        if self._tick_counter - self._last_narrated_at < self.narration_interval:
            return None
        # 避免在 world 为 None 时崩溃 (测试/初始化阶段)
        self._last_narrated_at = self._tick_counter
        if world is None or timeline_system is None:
            logger.debug(
                "Narrator: world=%s timeline=%s → skip",
                world, timeline_system,
            )
            return None
        # 收集重大事件
        timeline_entries = timeline_system.build(world, limit=30)
        if not timeline_entries:
            logger.debug("Narrator: no significant events at tick %d", self._tick_counter)
            return None
        # 构建叙事上下文
        context = self._collect_context(world, timeline_entries)
        # 生成叙事 (LLM 调用在子类或异步版本中处理)
        narrative = self._compose(context)
        if narrative:
            self.journal.append(narrative)
        return narrative

    def _collect_context(
        self,
        world: WorldState,
        timeline_entries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """从时间线条目中收集叙事上下文。

        统计各类型事件数量，按重要性排序。
        """
        events = list(timeline_entries)
        evolution_count = sum(1 for e in events if e["type"] == "evolution")
        battle_count = sum(1 for e in events if e["type"] == "battle")
        story_events = [e for e in events if e["type"] == "story_event"]
        first_meets = [e for e in events if e["type"] == "first_meet"]
        disaster_count = sum(1 for e in events if e["type"] == "disaster")

        # 按重要性排序
        sorted_events = sorted(
            events,
            key=lambda e: e.get("importance", 5),
            reverse=True,
        )

        return {
            "tick": self._tick_counter,
            "agent_count": world.count(),
            "events": sorted_events[:20],
            "evolution_count": evolution_count,
            "battle_count": battle_count,
            "disaster_count": disaster_count,
            "story_events": story_events,
            "first_meets": first_meets,
        }

    def _compose(self, context: dict[str, Any]) -> dict[str, Any]:
        """将上下文合成为一条叙事条目 (同步版本,不调 LLM)。

        Task 3 会扩展为 async 版本调用 MiniMax Text-01。
        """
        events_count = len(context.get("events", []))
        return {
            "tick": context.get("tick", self._tick_counter),
            "title": f"数码世界·第{context['tick']}刻",
            "story": f"在这片数字世界中,{context['agent_count']}只数码兽经历着它们的冒险。"
                    f"{context['evolution_count']}次进化,{context['battle_count']}场战斗,"
                    f"故事还在继续……",
            "events_count": events_count,
            "evolution_count": context.get("evolution_count", 0),
            "battle_count": context.get("battle_count", 0),
            "disaster_count": context.get("disaster_count", 0),
        }

    async def _compose_async(self, context: dict[str, Any]) -> dict[str, Any]:
        """异步版本: 用 MiniMax Text-01 生成故事摘要。

        构建 prompt → 调 LLM → 解析标题和摘要。
        LLM 失败时回退到同步版本。
        """
        try:
            from ..llm.client import (
                ChatMessage,
                ChatRequest,
                LlmModel,
                get_client,
            )

            # 构建事件列表
            event_lines: list[str] = []
            for e in context.get("events", [])[:10]:
                icon = e.get("icon", "•")
                etype = e.get("type", "unknown")
                title = e.get("title", str(e.get("event", {}).get("description", "")))[:80]
                event_lines.append(f"- {icon} [{etype}] {title}")

            events_text = "\n".join(event_lines) if event_lines else "世界平静如常"

            prompt = (
                f"你是数码世界的说书人。根据以下事件,写一段2-3句话的世界故事摘要,像动画旁白一样生动。\n\n"
                f"世界状态: {context['agent_count']}只数码兽\n"
                f"进化: {context['evolution_count']}次, "
                f"战斗: {context['battle_count']}场, "
                f"灾害: {context.get('disaster_count', 0)}次\n\n"
                f"今日大事:\n{events_text}\n\n"
                f"请用中文回复,格式:\n"
                f"标题: <15字以内的故事标题>\n"
                f"摘要: <2-3句叙事>"
            )

            client = get_client()
            req = ChatRequest(
                messages=[
                    ChatMessage(
                        role="system",
                        content="你是数码世界的叙事者,用动画旁白风格讲述世界故事。",
                    ),
                    ChatMessage(role="user", content=prompt),
                ],
                model=LlmModel.MINIMAX_TEXT_01,
                max_tokens=256,
                temperature=0.8,
            )
            resp = await client.complete(req)
            content = resp.content.strip()

            # 解析标题和摘要
            title = "数码世界的一天"
            story = content
            for line in content.split("\n"):
                line_stripped = line.strip()
                if line_stripped.startswith("标题"):
                    title = line_stripped.split(":", 1)[-1].strip() or title
                elif line_stripped.startswith("摘要"):
                    story = line_stripped.split(":", 1)[-1].strip() or story

            return {
                "tick": context.get("tick", self._tick_counter),
                "title": title[:30],
                "story": story[:500],
                "events_count": len(context.get("events", [])),
                "evolution_count": context.get("evolution_count", 0),
                "battle_count": context.get("battle_count", 0),
                "disaster_count": context.get("disaster_count", 0),
            }
        except Exception as e:
            logger.warning("Narrator LLM call failed, falling back: %s", e)
            return self._compose(context)

    async def tick_async(
        self,
        world: WorldState | None,
        timeline_system: TimelineSystem | None,
    ) -> dict[str, Any] | None:
        """异步 tick: 在调度器中使用,支持 LLM 调用。

        与 tick() 逻辑相同,但 _compose 用异步版本。
        """
        self._tick_counter += 1
        if self._tick_counter - self._last_narrated_at < self.narration_interval:
            return None
        self._last_narrated_at = self._tick_counter
        if world is None or timeline_system is None:
            logger.debug(
                "Narrator: world=%s timeline=%s → skip async",
                world, timeline_system,
            )
            return None
        timeline_entries = timeline_system.build(world, limit=30)
        if not timeline_entries:
            logger.debug(
                "Narrator: no significant events at tick %d (async)",
                self._tick_counter,
            )
            return None
        context = self._collect_context(world, timeline_entries)
        narrative = await self._compose_async(context)
        if narrative:
            self.journal.append(narrative)
        return narrative


# ---- 进程级单例 ----
_narrator: NarratorSystem | None = None


def get_narrator() -> NarratorSystem:
    """获取 (或延迟初始化) 叙事系统单例。"""
    global _narrator
    if _narrator is None:
        _narrator = NarratorSystem()
    return _narrator


def reset_narrator() -> None:
    """重置叙事系统 (测试用)。"""
    global _narrator
    _narrator = None
