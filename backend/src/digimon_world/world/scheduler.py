"""
WorldScheduler - 世界调度器
============================

按 WorldClock 周期性地调用每个 agent 的 step(),让数码兽自主生活。

设计要点:
- 同步接口 + asyncio 异步 step() → 用 asyncio.gather 并发驱动
- 可注入 tick_interval / on_event 回调(用于广播 / 持久化 / 测试)
- 不引入新依赖,只用标准库 + 现有 agent 接口

典型用法:

    clock = WorldClock(real_to_world_ratio=60)
    world = get_world()
    sched = WorldScheduler(world=world, clock=clock)
    await sched.tick_once()           # 推进一步(测试)
    sched.run_forever(tick_seconds=1) # 后台任务(async for)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Optional

from ..agents.digimon_agent import DigimonAgent
from ..agents.dialogue import Dialogue
from .clock import WorldClock
from .interactions import detect_proximity
from .world_state import WorldState

logger = logging.getLogger(__name__)

# 一次 tick 默认推进多少现实秒
DEFAULT_TICK_SECONDS = 1.0

# 相遇半径(像素): 距离小于此值才可能触发对话
DIALOGUE_RADIUS = 100

# 互动冷却(世界分钟): 同一对数码兽在此窗口内最多互动一次
DIALOGUE_COOLDOWN_MINUTES = 30

# 事件回调签名: async def cb(event: dict, agent: DigimonAgent) -> None
EventCallback = Callable[[dict[str, Any], DigimonAgent], Awaitable[None]]


class WorldScheduler:
    """世界调度器: 周期性驱动所有 agent 走一步。"""

    def __init__(
        self,
        world: WorldState,
        clock: WorldClock,
        on_event: Optional[EventCallback] = None,
        dialogue: Optional[Dialogue] = None,
    ) -> None:
        self._world = world
        self._clock = clock
        self._on_event = on_event
        # 对话生成器(可选): 有则在相遇时生成对话,无则跳过互动阶段
        self._dialogue = dialogue
        self._tick_count = 0

    @property
    def tick_count(self) -> int:
        """已执行 tick 次数(测试 / 调试用)。"""
        return self._tick_count

    async def tick_once(self, real_seconds: float = DEFAULT_TICK_SECONDS) -> list[dict[str, Any]]:
        """执行一次 tick: 推进时钟 + 所有 agent 并发 step。

        Returns:
            本 tick 产出的事件列表(每只 agent 一个)。
        """
        # 1. 时钟推进(同步)
        self._clock.tick(real_seconds=real_seconds)
        # 2. 并发驱动所有 agent
        agents = self._world.all()
        if not agents:
            return []
        events = await asyncio.gather(
            *[self._step_agent(a) for a in agents],
            return_exceptions=False,
        )
        # 3. 写回世界事件日志 + 触发回调
        for ev in events:
            if isinstance(ev, dict):
                self._world.events.append(ev)
                if self._on_event is not None:
                    try:
                        await self._on_event(ev, self._world.get(ev.get("agent", "")) or agents[0])
                    except Exception as e:  # 回调失败不影响主循环
                        logger.warning("on_event callback failed: %s", e)
        # 4. 互动阶段: 相遇的数码兽触发对话
        await self._run_interactions(agents)
        self._tick_count += 1
        return events

    async def _run_interactions(self, agents: list[DigimonAgent]) -> None:
        """检测相遇的数码兽并触发对话,写入双方记忆。

        触发条件(全部满足):
        - 同一 region
        - 欧氏距离 < DIALOGUE_RADIUS
        - 双方都在冷却窗口(DIALOGUE_COOLDOWN_MINUTES 世界分钟)之外

        未挂 dialogue 生成器时直接跳过整个互动阶段。
        """
        if self._dialogue is None:
            return

        now = self._clock.now
        pairs = detect_proximity(agents, radius=DIALOGUE_RADIUS)
        for a, b in pairs:
            # 只在同一地区相遇
            if a.region_id != b.region_id:
                continue
            # 任一方仍在冷却期 → 跳过
            if self._in_cooldown(a, now) or self._in_cooldown(b, now):
                continue

            try:
                line = await self._dialogue.generate_dialogue(a, b, self._world.events[-5:])
            except Exception as e:  # 生成器内部已兜底,这里再保一层
                logger.warning("dialogue generation failed for %s / %s: %s", a.name, b.name, e)
                continue

            # 写入双方记忆(first_meet 级别的重要事件)
            a.observe({"type": "first_meet", "description": f"遇到{b.name},对它说:{line}"})
            b.observe({"type": "first_meet", "description": f"{a.name}对我说:{line}"})

            # 记录互动事件到世界日志
            self._world.events.append({
                "type": "dialogue",
                "speaker": a.name,
                "listener": b.name,
                "line": line,
                "at": now.isoformat() if now is not None else None,
            })

            # 刷新双方冷却时间戳
            a.last_interaction_at = now
            b.last_interaction_at = now

    def _in_cooldown(self, agent: DigimonAgent, now: Any) -> bool:
        """判断 agent 是否仍在互动冷却窗口内。"""
        if agent.last_interaction_at is None or now is None:
            return False
        elapsed_minutes = (now - agent.last_interaction_at).total_seconds() / 60
        return elapsed_minutes < DIALOGUE_COOLDOWN_MINUTES

    async def _step_agent(self, agent: DigimonAgent) -> dict[str, Any]:
        """调用单个 agent.step(),捕获异常不让一只炸了拖死整个 tick。"""
        try:
            return await agent.step(self._world.regions)
        except Exception as e:
            logger.exception("agent.step failed for %s: %s", agent.name, e)
            return {
                "type": "step_error",
                "agent": agent.name,
                "error": str(e),
            }

    async def run_forever(
        self,
        tick_seconds: float = DEFAULT_TICK_SECONDS,
        stop_on: Optional[Callable[[], bool]] = None,
    ) -> None:
        """无限循环跑 tick,直到 stop_on() 返回 True 或被外部 cancel。

        Args:
            tick_seconds: 每次 tick 间隔(现实秒)
            stop_on: 可选停止条件,返回 True 时跳出(测试用)
        """
        try:
            while True:
                if stop_on is not None and stop_on():
                    return
                await self.tick_once(real_seconds=tick_seconds)
                await asyncio.sleep(tick_seconds)
        except asyncio.CancelledError:
            logger.info("WorldScheduler cancelled, exiting run_forever")
            raise