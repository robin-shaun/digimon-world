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
from .dark_gears import DarkGearSystem, get_dark_gear_system
from .daynight import DayNightSystem, get_daynight_system
from .ecology import EcologySystem, get_ecology_system
from .environmental_events import EnvironmentalEventSystem, get_env_events_system
from .events import CHECK_INTERVAL_TICKS, StoryDirector
from .factions import FactionRegistry
from .festivals import FestivalSystem, get_festival_system
from .interactions import detect_proximity
from .landmarks import LandmarkSystem, get_landmark_system
from .relationships import RelationshipTracker, get_tracker
from .seasons import SeasonSystem, get_season_system
from .weather import WeatherSystem, get_weather_system
from .world_state import WorldState

logger = logging.getLogger(__name__)

# 一次 tick 默认推进多少现实秒
DEFAULT_TICK_SECONDS = 1.0

# 每隔多少 tick 自动持久化一次世界状态
SAVE_INTERVAL_TICKS = 100

# 相遇半径(像素): 距离小于此值才可能触发对话
DIALOGUE_RADIUS = 200                     # 相遇触发距离(px),10只数码兽需更宽范围
DIALOGUE_COOLDOWN_MINUTES = 10            # 对话冷却(世界分钟)

# ---- 显著性阈值(Phase 6) ----
# 事件分级: trivial(0-2) / routine(3-5) / significant(6-8) / critical(9-10)
# 只有 significance >= SIGNIFICANCE_LLM_THRESHOLD 的事件才触发 LLM 反思
SIGNIFICANCE_LLM_THRESHOLD = 4  # 阈值: routine(3-5)即可触发 LLM

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
        relationships: Optional[RelationshipTracker] = None,
        factions: Optional[FactionRegistry] = None,
        story_director: Optional[StoryDirector] = None,
        landmarks: Optional[LandmarkSystem] = None,
        festivals: Optional[FestivalSystem] = None,
        dark_gears: Optional[DarkGearSystem] = None,
        daynight: Optional[DayNightSystem] = None,
        weather: Optional[WeatherSystem] = None,
        ecology: Optional[EcologySystem] = None,
        env_events: Optional[EnvironmentalEventSystem] = None,
        season: Optional[SeasonSystem] = None,
        auto_save: bool = False,
        save_db_path: Optional[str] = None,
    ) -> None:
        self._world = world
        self._clock = clock
        self._on_event = on_event
        # 是否每 SAVE_INTERVAL_TICKS 自动持久化一次(默认关,测试/独立实例不落盘)
        self._auto_save = auto_save
        self._save_db_path = save_db_path
        # 对话生成器(可选): 有则在相遇时生成对话,无则跳过互动阶段
        self._dialogue = dialogue
        # 社交关系表: 默认用进程级单例,可注入独立实例(测试)
        self._relationships = relationships if relationships is not None else get_tracker()
        # 派系登记处: 每 tick 由关系表重算自动派系(无则新建独立实例)
        self._factions = factions if factions is not None else FactionRegistry()
        # 剧情导演: 每 CHECK_INTERVAL_TICKS 扫描一次触发条件(无则新建独立实例)
        self._story_director = story_director if story_director is not None else StoryDirector()
        # 地标系统: 每 tick 检测数码兽是否靠近地标并施加效果(无则用进程级单例)
        self._landmarks = landmarks if landmarks is not None else get_landmark_system()
        # 节日系统: 每 tick 检查是否跨入节日日(无则用进程级单例)
        self._festivals = festivals if festivals is not None else get_festival_system()
        # 治疗系统: 每 tick 让受伤数码兽自然回血(神殿附近加成)
        from ..agents.healing import get_healing_system
        self._healing = get_healing_system()
        # 黑色齿轮系统: Phase 8 — 每 tick 投放/清理齿轮(无则用进程级单例)
        self._dark_gears = dark_gears if dark_gears is not None else get_dark_gear_system()
        # 昼夜系统: Phase 10 — 每 tick 更新时段(无则用进程级单例)
        self._daynight = daynight if daynight is not None else get_daynight_system()
        # 天气系统: Phase 10 — 每 30 tick 切换天气(无则用进程级单例)
        self._weather = weather if weather is not None else get_weather_system()
        # 生态系统: Phase 10 — 每 tick 更新食物/植被(无则用进程级单例)
        self._ecology = ecology if ecology is not None else get_ecology_system()
        # 环境事件系统: Phase 10 — 检测暴风雨/干旱/火山(无则用进程级单例)
        self._env_events = env_events if env_events is not None else get_env_events_system()
        # 季节系统: Phase 10 — 每 tick 更新季节(无则用进程级单例)
        self._season = season if season is not None else get_season_system()
        self._tick_count = 0
        # 日记系统: 记录上一次 tick 的世界日期,用于检测跨天
        self._last_world_day: Optional[int] = None
        # Phase 6: 监控指标 — 跳过 LLM 的事件计数
        self.skipped_llm_events: int = 0

    @property
    def tick_count(self) -> int:
        """已执行 tick 次数(测试 / 调试用)。"""
        return self._tick_count

    @property
    def factions(self) -> FactionRegistry:
        """派系登记处(前端 / Director 视角读取)。"""
        return self._factions

    @property
    def story_director(self) -> StoryDirector:
        """剧情导演(前端 / Director 视角读取)。"""
        return self._story_director

    @property
    def landmarks(self) -> LandmarkSystem:
        """地标系统(前端 / Director 视角读取)。"""
        return self._landmarks

    @property
    def festivals(self) -> FestivalSystem:
        """节日系统(前端 / Director 视角读取)。"""
        return self._festivals

    @property
    def dark_gears(self) -> DarkGearSystem:
        """黑色齿轮系统(Phase 8 — 前端 / Director 视角读取)。"""
        return self._dark_gears

    @property
    def daynight(self) -> DayNightSystem:
        """昼夜系统(Phase 10)。"""
        return self._daynight

    @property
    def weather(self) -> WeatherSystem:
        """天气系统(Phase 10)。"""
        return self._weather

    @property
    def ecology(self) -> EcologySystem:
        """生态系统(Phase 10)。"""
        return self._ecology

    @property
    def env_events(self) -> EnvironmentalEventSystem:
        """环境事件系统(Phase 10)。"""
        return self._env_events

    @property
    def season(self) -> SeasonSystem:
        """季节系统(Phase 10)。"""
        return self._season

    async def tick_once(self, real_seconds: float = DEFAULT_TICK_SECONDS) -> list[dict[str, Any]]:
        """执行一次 tick: 推进时钟 + 所有 agent 并发 step。

        Returns:
            本 tick 产出的事件列表(每只 agent 一个)。
        """
        # 1. 时钟推进(同步)
        self._clock.tick(real_seconds=real_seconds)
        # 2. 日记阶段: 检测世界日期是否跨天,跨天则让所有 agent 写日记
        await self._maybe_write_diaries()
        # 3. 并发驱动所有 agent
        agents = self._world.all()
        if not agents:
            return []
        events = await asyncio.gather(
            *[self._step_agent(a) for a in agents],
            return_exceptions=False,
        )
        # 4. 写回世界事件日志 + 触发回调
        for ev in events:
            if isinstance(ev, dict):
                self._world.events.append(ev)
                if self._on_event is not None:
                    try:
                        await self._on_event(ev, self._world.get(ev.get("agent", "")) or agents[0])
                    except Exception as e:  # 回调失败不影响主循环
                        logger.warning("on_event callback failed: %s", e)
        # 4.5 地标阶段: 移动后检测是否靠近地标并施加效果
        landmark_effects = self._landmarks.process(self._world)
        for ev in landmark_effects:
            self._world.events.append(ev)
            # 让当事数码兽记住这次地标经历(中等重要性)
            target = self._world.get(ev.get("agent", ""))
            if target is not None:
                target.observe(ev)
        # 4.6 治疗阶段: 受伤数码兽自然回血(进化神殿附近 +5,否则 +1)
        heal_events = self._healing.process(self._world)
        for ev in heal_events:
            self._world.events.append(ev)
        # 4.7 黑色齿轮阶段: Phase 8 — 投放/清理齿轮,记录感染事件
        gear = self._dark_gears.process(self._tick_count, world=self._world)
        if gear is not None:
            event_g = {
                "type": "dark_gear_placed",
                "gear_id": gear.gear_id,
                "sub_region_id": gear.sub_region_id,
                "threat_level": self._dark_gears.threat_level,
                "at": str(self._clock.elapsed_minutes),
            }
            self._world.events.append(event_g)
            # 通知齿轮所在子区域内的所有 agent
            for agent in agents:
                sr = self._world.get_sub_region(agent)
                if sr is not None and sr.get("id") == gear.sub_region_id:
                    agent.observe({
                        "type": "dark_gear_infection",
                        "description": f"黑色齿轮 {gear.gear_id} 出现,感到一阵黑暗力量…",
                        "gear_id": gear.gear_id,
                    })
        # 5. 互动阶段: 相遇的数码兽触发对话
        await self._run_interactions(agents)
        # 6. 派系阶段: 从关系表重算自动派系(导演注入的派系保留)
        self._factions.form_factions(self._relationships)
        # 7. 剧情阶段: 每 CHECK_INTERVAL_TICKS 扫描一次全局剧情触发条件
        if self._tick_count % CHECK_INTERVAL_TICKS == 0:
            from .events import set_world_tick
            set_world_tick(self._tick_count)
            self._story_director.check_trigger(self._world, self._relationships)
            # Phase 8: 黑暗四天王效果 — 新触发的天王事件让所有数码兽恐惧+战斗倾向+
            if self._story_director.new_dark_master_events:
                for agent in agents:
                    agent.apply_dark_masters_effects()
        # 7.5 节日阶段: 检查是否跨入节日日,跨入则全员心情 / 关系增益
        festival = self._festivals.update_from_clock(
            self._clock.elapsed_minutes,
            world_state=self._world,
            tracker=self._relationships,
        )
        if festival is not None:
            # 让全体数码兽记住这场节日(中等重要性)
            for agent in agents:
                try:
                    agent.observe(festival)
                except Exception as e:
                    logger.warning("festival observe failed for %s: %s", agent.name, e)
        # 8. Phase 10 环境演化阶段:
        #    昼夜循环、天气切换、生态更新、环境事件检测
        await self._process_environment(agents)
        self._tick_count += 1
        # 8. 持久化阶段: 每 SAVE_INTERVAL_TICKS 全量落盘一次
        if self._auto_save and self._tick_count % SAVE_INTERVAL_TICKS == 0:
            await self._auto_save_world()
        return events

    async def _auto_save_world(self) -> None:
        """自动全量保存世界状态。失败只记 warning,不打断 tick 循环。"""
        # 局部 import 避免 world 包内的循环依赖
        from . import persistence

        try:
            if self._save_db_path is not None:
                await persistence.save(self._world, self._relationships, self._save_db_path)
            else:
                await persistence.save(self._world, self._relationships)
        except Exception as e:
            logger.warning("auto-save failed at tick %d: %s", self._tick_count, e)

    async def _maybe_write_diaries(self) -> None:
        """检测世界日期跨天,触发所有 agent 写日记。

        逻辑: 比较当前世界时间的 day-of-year 与上一次记录的。
        首次 tick 只记录不触发(避免启动时立刻写空日记)。
        """
        now = self._clock.now
        if now is None:
            return
        current_day = now.toordinal()

        if self._last_world_day is None:
            # 首次 tick: 只记录,不写日记
            self._last_world_day = current_day
            return

        if current_day > self._last_world_day:
            # 跨天了: 对昨天写日记
            from datetime import timedelta
            yesterday = now - timedelta(days=1)
            agents = self._world.all()
            for agent in agents:
                try:
                    agent.write_diary(yesterday)
                except Exception as e:
                    logger.warning("write_diary failed for %s: %s", agent.name, e)
            self._last_world_day = current_day

    async def _run_interactions(self, agents: list[DigimonAgent]) -> None:
        """检测相遇的数码兽并触发对话,写入双方记忆。

        触发条件(全部满足):
        - 同一 region
        - 欧氏距离 < DIALOGUE_RADIUS
        - 双方都在冷却窗口(DIALOGUE_COOLDOWN_MINUTES 世界分钟)之外

        隐性欲望(latent desire)影响:
        - 两方欲望兼容 → 关系增量更大(record_dialogue_with_desire)
        - 有"想交朋友"欲望的 agent 冷却更短(更容易发起对话)
        - 未挂 dialogue 生成器时直接跳过整个互动阶段。
        """
        if self._dialogue is None:
            return

        now = self._clock.now
        pairs = detect_proximity(agents, radius=DIALOGUE_RADIUS)
        for a, b in pairs:
            # 只在同一地区相遇
            if a.region_id != b.region_id:
                continue

            # 隐性欲望冷却减免: 有"想交朋友"类欲望的 agent 冷却窗口减半
            a_cooldown_minutes = DIALOGUE_COOLDOWN_MINUTES
            b_cooldown_minutes = DIALOGUE_COOLDOWN_MINUTES
            if a.latent_desire and ("交朋友" in a.latent_desire or "朋友" in a.latent_desire):
                a_cooldown_minutes = DIALOGUE_COOLDOWN_MINUTES // 2
            if b.latent_desire and ("交朋友" in b.latent_desire or "朋友" in b.latent_desire):
                b_cooldown_minutes = DIALOGUE_COOLDOWN_MINUTES // 2

            # 任一方仍在冷却期 → 不生成对话,但相遇本身也拉近一点关系(含欲望加成)
            if self._in_cooldown(a, now, a_cooldown_minutes) or self._in_cooldown(b, now, b_cooldown_minutes):
                self._relationships.record_proximity_with_desire(
                    a.name, a.latent_desire, b.name, b.latent_desire,
                )
                # Phase 6: 冷却中的相遇是 routine 事件,跳过 LLM
                self.skipped_llm_events += 1
                continue

            # Phase 6: 显著性阈值 — 评估事件上下文
            # proximity 相遇本身是 routine(5), >= SIGNIFICANCE_LLM_THRESHOLD(4)→触发 LLM 对话
            # 但如果双方有强烈的 desire 兼容(affinity >= 0.6),则提升为 significant
            event_context = {"type": "proximity", "agent": a.name, "importance": 5}
            sig = self._score_event_significance(event_context)
            desire_bonus = RelationshipTracker.desire_affinity(a.latent_desire, b.latent_desire)
            if desire_bonus >= 0.6:
                sig = max(sig, 7)  # 欲望兼容提升为 significant

            if sig < SIGNIFICANCE_LLM_THRESHOLD:
                # routine 事件: 仅记录亲近度,不调 LLM
                self._relationships.record_proximity_with_desire(
                    a.name, a.latent_desire, b.name, b.latent_desire,
                )
                self.skipped_llm_events += 1
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

            # 一次成功对话 → 双方关系变友好(含欲望兼容加成)
            self._relationships.record_dialogue_with_desire(
                a.name, a.latent_desire, b.name, b.latent_desire,
            )

            # 刷新双方冷却时间戳
            a.last_interaction_at = now
            b.last_interaction_at = now

    # ---- Phase 10: 环境演化处理 ----
    async def _process_environment(self, agents: list[DigimonAgent]) -> None:
        """每 tick 处理: 昼夜循环、天气切换、生态更新、环境事件检测。

        这些系统都是同步的,放在一个 async 方法里批量处理,
        不阻塞 agent step 的并发。
        """
        minutes = self._clock.elapsed_minutes

        # 8.1 昼夜循环
        self._daynight.update(minutes)

        # 8.2 天气切换
        self._weather.update(self._tick_count)

        # 8.3 季节更新
        self._season.update_from_clock(minutes)

        # 8.4 生态更新 + 饥饿效果
        eco_events = self._ecology.process(
            self._world,
            tick_count=self._tick_count,
            season=self._season.current.value,
            weather_value=self._weather.current.value,
        )
        for ev in eco_events:
            self._world.events.append(ev)

        # 8.5 环境事件检测(暴风雨/干旱/火山)
        env_evs = self._env_events.process(
            self._world,
            self._ecology,
            self._weather,
            self._tick_count,
        )
        for ev in env_evs:
            self._world.events.append(ev)
            # 重大环境事件让所有数码兽 observe
            for agent in agents:
                try:
                    agent.observe(ev)
                except Exception as e:
                    logger.warning("env_event observe failed for %s: %s", agent.name, e)

    @staticmethod
    def _score_event_significance(event: dict[str, Any]) -> int:
        """评估事件显著性: 0-10。

        分级:
        - critical (9-10): battle_victory, evolution, near_death, disaster
        - significant (6-8): first_meet, gift_received, threat, dialogue, faction_create
        - routine (3-5): moved, rested, observed, ate
        - trivial (0-2): proximity, step_error

        只有 significance >= SIGNIFICANCE_LLM_THRESHOLD(6) 的事件才触发 LLM 反思。
        """
        et = event.get("type", "")
        if et in {"battle_victory", "evolution", "near_death", "disaster"}:
            return 9
        if et in {"first_meet", "gift_received", "threat"}:
            return 7
        if et in {"dialogue", "faction_create", "festival"}:
            return 7
        if et in {"broadcast"}:
            imp = event.get("importance", 5)
            return max(6, min(10, int(imp)))
        if et in {"moved", "rested", "observed", "ate", "heal"}:
            return 4
        if et in {"proximity", "step_error"}:
            return 5  # proximity 提到 routine，让对话触发
        return 5  # 未知事件默认 routine

    def _in_cooldown(self, agent: DigimonAgent, now: Any, cooldown_minutes: float | None = None) -> bool:
        """判断 agent 是否仍在互动冷却窗口内。"""
        if agent.last_interaction_at is None or now is None:
            return False
        elapsed_minutes = (now - agent.last_interaction_at).total_seconds() / 60
        threshold = cooldown_minutes if cooldown_minutes is not None else DIALOGUE_COOLDOWN_MINUTES
        return elapsed_minutes < threshold

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