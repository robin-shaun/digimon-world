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
import random
from collections.abc import Awaitable, Callable
from typing import Any

from ..agents.dialogue import Dialogue
from ..agents.digimon_agent import DigimonAgent
from ..economy import get_energy_economy
from .affect_propagation import AffectPropagationEngine
from .clock import WorldClock
from .cooperation_thresholds import get_circle_between, get_interaction_modifier
from .dark_gears import DarkGearSystem, get_dark_gear_system
from .daynight import DayNightSystem, get_daynight_system
from .ecology import EcologySystem, get_ecology_system
from .environmental_events import EnvironmentalEventSystem, get_env_events_system
from .events import CHECK_INTERVAL_TICKS, StoryDirector
from .factions import FactionRegistry, get_registry
from .festivals import FestivalSystem, get_festival_system
from .interactions import detect_proximity
from .landmarks import LandmarkSystem, get_landmark_system
from .narrator import get_narrator
from .personality_dynamics import (
    _SHIFT_DRIFT_THRESHOLD,  # noqa: F401
    get_personality_dynamics_engine,
    reset_personality_dynamics_engine,  # noqa: F401
)
from .personality_engine import get_personality_engine
from .relational_circle import RelationalCircle
from .relationships import RelationshipTracker, get_tracker
from .seasons import SeasonSystem, get_season_system
from .shared_conventions import get_convention_pool
from .thinking_cost import RECOVER_SOCIAL
from .weather import WeatherSystem, get_weather_system
from .world_state import WorldState

logger = logging.getLogger(__name__)

# 一次 tick 默认推进多少现实秒
DEFAULT_TICK_SECONDS = 1.0

# 每隔多少 tick 自动持久化一次世界状态
SAVE_INTERVAL_TICKS = 100

# Phase 13⑤: 每隔多少 tick 创建一次快照 (0 = 禁用)
SNAPSHOT_INTERVAL_TICKS = 500

# 相遇半径(像素): 距离小于此值才可能触发对话
DIALOGUE_RADIUS = 200                     # 相遇触发距离(px),10只数码兽需更宽范围
DIALOGUE_COOLDOWN_MINUTES = 10            # 对话冷却(世界分钟)

# 人格动力学步进间隔（每多少 tick 检测一次重大人格转变）
PERSONALITY_DYNAMICS_INTERVAL = 50

# Phase 11: LLM 调用批量化 — 降低每 tick 的 LLM 调用密度
# 30 只数码兽,每 tick 全调 LLM 不可行
THINK_ROUND_INTERVAL = 20                 # 反思轮次: 每 20 tick 才收集需要反思的 agent
PLAN_CACHE_TICKS = 60                     # 计划缓存: 生成后缓存 60 tick 不再重复调用
DIALOGUE_TRIGGER_PROB = 0.1               # 对话触发概率: 距离<200 + 双方未冷却时,仅 10%
MOVE_LLM_TICKS = 20                       # 移动决策: 每 20 tick 才调 LLM planner 一次(中间用向量+噪声)

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
        on_event: EventCallback | None = None,
        dialogue: Dialogue | None = None,
        relationships: RelationshipTracker | None = None,
        factions: FactionRegistry | None = None,
        story_director: StoryDirector | None = None,
        landmarks: LandmarkSystem | None = None,
        festivals: FestivalSystem | None = None,
        dark_gears: DarkGearSystem | None = None,
        daynight: DayNightSystem | None = None,
        weather: WeatherSystem | None = None,
        ecology: EcologySystem | None = None,
        env_events: EnvironmentalEventSystem | None = None,
        season: SeasonSystem | None = None,
        auto_save: bool = False,
        save_db_path: str | None = None,
        dialogue_prob: float = DIALOGUE_TRIGGER_PROB,
    ) -> None:
        self._world = world
        self._clock = clock
        self._on_event = on_event
        # 是否每 SAVE_INTERVAL_TICKS 自动持久化一次(默认关,测试/独立实例不落盘)
        self._auto_save = auto_save
        self._save_db_path = save_db_path
        self._dialogue_prob = dialogue_prob  # Phase 11: 对话触发概率(可注入,测试用1.0)
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
        # Phase 16: 情感传播引擎 — 检测情绪剧变并按关系距离传播
        self._affect_engine = AffectPropagationEngine()
        # Phase 17: 人格引擎 — 每 tick 根据事件类型演化数码兽人格
        self._personality = get_personality_engine()
        # 日记系统: 记录上一次 tick 的世界日期,用于检测跨天
        self._last_world_day: int | None = None
        # Phase 6: 监控指标 — 跳过 LLM 的事件计数
        self.skipped_llm_events: int = 0
        # Phase 11: LLM 批量化 — 计划缓存 + 思考轮次
        # _plan_cache: agent_name → (plan, cached_at_tick)
        self._plan_cache: dict[str, tuple[str, int]] = {}
        self._last_think_round: int = -THINK_ROUND_INTERVAL  # 首次 tick 即触发
        # Phase 11 监控: 跳过 LLM 的计划/反思/对话次数
        self.skipped_plan_calls: int = 0
        self.skipped_reflect_calls: int = 0
        self.skipped_dialogue_probs: int = 0

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
        # 2.5 Phase 16: 情感传播 — 在 step 之前快照所有 agent 的 mood_state
        self._affect_engine.snapshot_moods(self._world)
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
        # 4.4 Phase 11: 批量思考轮次 — 收集需要反思的 agent 一起调 LLM
        await self._batch_reflect(agents)
        # 4.45 Phase 16: 情感传播 — 检测情绪剧变并按关系距离传播
        await self._propagate_affect(agents)
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
        # 7.6 Phase 30: 孵化阶段 — 推进所有数码蛋的孵化进度
        try:
            from .egg_incubation import get_hatchery
            hatchery = get_hatchery()
            season_str = self._season.current.value if self._season else None
            newly_hatched = hatchery.tick(self._tick_count, season=season_str)
            for result in newly_hatched:
                event = {
                    "type": "egg_hatched",
                    "egg_id": result.egg_id,
                    "parent_a": result.parent_a,
                    "parent_b": result.parent_b,
                    "child_species": result.child_species,
                    "tick": result.tick_hatched,
                    "at": self._clock.now.isoformat() if self._clock.now else None,
                }
                self._world.events.append(event)
                logger.info(
                    "Hatchery: egg %s hatched! → %s (parents: %s + %s)",
                    result.egg_id, result.child_species, result.parent_a, result.parent_b,
                )
        except Exception as e:
            logger.debug("Hatchery step failed: %s", e)
        # 8. Phase 10 环境演化阶段:
        #    昼夜循环、天气切换、生态更新、环境事件检测
        await self._process_environment(agents)
        # 9. Phase 14 世界叙事阶段:
        #    每 N tick 收集重大事件 → LLM 生成故事摘要
        await self._process_narrative()
        # 9.5 Phase 17 人格演化阶段:
        #    根据本 tick 发生的事件类型,推动数码兽人格维度漂移
        self._process_personality_events(agents)
        # 9.6 Phase 22 共享惯例检测阶段:
        #    扫描 agent 记忆，检测涌现的共享惯例，衰减已有惯例
        convention_report = get_convention_pool().tick(agents)
        if convention_report.get("new_this_tick", 0) > 0:
            logger.info(
                "Convention tick: +%d new, %d active",
                convention_report["new_this_tick"],
                convention_report["active"],
            )
        # 9.7 Phase 24 能量经济阶段:
        #    债务衰败、绝望救济（低能量 agent 获得回报）、唤醒休眠朋友
        economy_events = get_energy_economy().step(self._tick_count)
        if economy_events:
            logger.info(
                "Energy economy tick: %d events (relief=%d, awaken=%d)",
                len(economy_events),
                sum(1 for e in economy_events if e["type"] == "reciprocal_relief"),
                sum(1 for e in economy_events if e["type"] == "awaken"),
            )
        # 9.8 Phase 26 人格动力学阶段:
        #    每 N tick 执行稳定性计算 + 重大人格转变检测
        #    显著 shift 广播为世界事件
        if self._tick_count % PERSONALITY_DYNAMICS_INTERVAL == 0:
            try:
                dynamics = get_personality_dynamics_engine()
                new_shifts = dynamics.step(self._tick_count)
                for shift in new_shifts:
                    # 世界事件广播
                    event = {
                        "type": "personality_shift",
                        "agent": shift.agent_name,
                        "old_type": shift.old_type,
                        "new_type": shift.new_type,
                        "drift_distance": shift.drift_distance,
                        "description": shift.description,
                        "tick": self._tick_count,
                        "at": self._clock.now.isoformat() if self._clock.now else None,
                    }
                    self._world.events.append(event)
                    # 让当事 agent 记忆这次重大人格转变
                    target = self._world.get(shift.agent_name)
                    if target is not None:
                        target.observe({
                            "type": "personality_shift",
                            "description": (
                                f"我的性格发生了重大转变：从 {shift.old_type} "
                                f"变为 {shift.new_type}"
                            ),
                            "importance": 9,
                        })
                    logger.info(
                        "PersonalityDynamics Step: tick=%d %s → world event broadcast",
                        self._tick_count, shift.agent_name,
                    )
            except Exception as e:
                logger.debug("Personality dynamics step failed: %s", e)
        # 9.85 Phase 27 知识经济阶段:
        #    每 tick 传播知识 + 检查是否有 agent 有资格发明新技能
        try:
            from ..economy.knowledge_economy import get_knowledge_pool
            pool = get_knowledge_pool()
            spread_count = pool.propagate(self._tick_count)
            new_skills = pool.check_inventions(agents, self._tick_count)
            if new_skills:
                for skill in new_skills:
                    event = {
                        "type": "knowledge_invention",
                        "agent": skill.inventor_id,
                        "skill_name": skill.name,
                        "domain": skill.domain,
                        "power": skill.power,
                        "tick": self._tick_count,
                        "at": self._clock.now.isoformat() if self._clock.now else None,
                    }
                    self._world.events.append(event)
                logger.info(
                    "KnowledgePool: %d inventions @ tick %d (spread=%d)",
                    len(new_skills), self._tick_count, spread_count,
                )
            elif spread_count > 0:
                logger.info("KnowledgePool: %d spreads @ tick %d", spread_count, self._tick_count)
        except Exception as e:
            logger.debug("Knowledge economy step failed: %s", e)
        # 9.87 Phase 28a: 自我模型 — 每个 agent 自我评估
        try:
            from .self_model import get_self_model_registry
            sm_registry = get_self_model_registry()
            for agent in agents:
                # 构建 world context
                # 使用 all_pairs() 计算关系数（agent 在 'a' 或 'b' 位置）和友谊等级
                all_pairs = self._relationships.all_pairs()
                rel_count = sum(1 for p in all_pairs if p['a'] == agent.name or p['b'] == agent.name)
                friendship_levels = [
                    p['vector']['affinity']
                    for p in all_pairs
                    if (p['a'] == agent.name or p['b'] == agent.name)
                ]
                ctx: dict[str, Any] = {
                    "battle_victories": getattr(agent, 'battle_victories', 0),
                    "attack": agent.stats.attack if hasattr(agent, 'stats') else 0,
                    "defense": agent.stats.defense if hasattr(agent, 'stats') else 0,
                    "evolution_stage": agent.stage.value if hasattr(agent, 'stage') else "rookie",
                    "relationship_count": rel_count,
                    "dialogue_count": 0,  # dialogue tracking not yet implemented per-agent
                    "friendship_levels": friendship_levels,
                    "regions_visited": 0,  # regions_visited tracking not yet implemented
                    "distance_traveled": 0.0,  # distance tracking not yet implemented
                    "skills_count": len(getattr(agent, 'skills', [])),
                    "inventions_count": getattr(agent, 'invention_count', 0),
                    "knowledge_citations": getattr(agent, 'knowledge_citations', 0),
                }
                sm_registry.step(
                    agent_name=agent.name,
                    agent_context=ctx,
                    tick=self._tick_count,
                )
        except Exception as e:
            logger.debug("Self model step failed: %s", e)
        # 9.875 Phase 28b: Theory of Mind — 更新 agent 间心智模型
        try:
            from .theory_of_mind import get_theory_of_mind_registry
            tom_registry = get_theory_of_mind_registry()
            # 使用对话阶段检测到的 proximity pairs
            pairs = detect_proximity(agents, radius=DIALOGUE_RADIUS)
            for a, b in pairs:
                if a.region_id != b.region_id:
                    continue
                # 构建观察数据
                obs_a = {
                    "action_type": "proximity",
                    "intensity": 0.3,
                }
                obs_b = {
                    "action_type": "proximity",
                    "intensity": 0.3,
                }
                tom_registry.step(a.name, b.name, obs_a, self._tick_count)
                tom_registry.step(b.name, a.name, obs_b, self._tick_count)
        except Exception as e:
            logger.debug("Theory of mind step failed: %s", e)
        # 9.88 Phase 28c: 叙事一致性检查
        try:
            from .narrative_coherence import get_coherence_engine
            coherence = get_coherence_engine()
            if coherence.should_check(self._tick_count):
                # 收集 pairs_data: [(a, b, a→b_affinity, b→a_affinity, a→b_rivalry, b→a_rivalry), ...]
                pairs_data: list[tuple[str, str, float, float, float, float]] = []
                agent_names = [a.name for a in agents]
                for i, ai in enumerate(agents):
                    for aj in agents[i+1:]:
                        rel_ab = self._relationships.get_vector(ai.name, aj.name)
                        rel_ba = self._relationships.get_vector(aj.name, ai.name)
                        pairs_data.append((
                            ai.name, aj.name,
                            rel_ab.affinity, rel_ba.affinity,
                            rel_ab.rivalry, rel_ba.rivalry,
                        ))
                report = coherence.check(
                    tick=self._tick_count,
                    agent_names=agent_names,
                    pairs_data=pairs_data,
                    events=self._world.events[-200:] if self._world.events else None,
                    agent_positions=None,
                )
                if report.warnings:
                    logger.warning(
                        "NarrativeCoherence: score=%.3f warnings=%d",
                        report.global_score, len(report.warnings),
                    )
        except Exception as e:
            logger.debug("Narrative coherence check failed: %s", e)
        # 9.89 Phase 29: 世界年鉴 — epoch 边界生成章节
        try:
            from .world_almanac import get_almanac

            almanac = get_almanac()
            # 统计本 epoch 的有效事件数
            epoch_events = [
                e for e in self._world.events
                if e.get("tick", -1) > almanac._last_archived_tick
            ]
            if almanac.should_generate(self._tick_count, len(epoch_events)):
                # 构建 digimon 数据快照
                digimon_data: list[dict[str, Any]] = []
                for agent in agents:
                    d: dict[str, Any] = {
                        "name": agent.name,
                        "energy": {
                            "current": getattr(agent, "energy", 100),
                        },
                        "personality": {
                            "mbti": getattr(agent, "mbti_type", "UNKN"),
                        },
                        "region_id": agent.region_id,
                        "evolution": {
                            "stage": agent.stage.value if hasattr(agent, "stage") else "rookie",
                        },
                        "battle_victories": getattr(agent, "battle_victories", 0),
                        "memory_count": (
                            len(getattr(agent, "memory_stream", type("M", (), {"memories": []})()).memories)
                        ),
                        "knowledge_invented": getattr(agent, "invention_count", 0),
                        "energy_donated": 0.0,
                        "evolution_score": 0,
                        "knowledge_citations": getattr(agent, "knowledge_citations", 0),
                    }
                    digimon_data.append(d)

                # 构建 snapshot_data
                snapshot_data: dict[str, Any] = {
                    "total_knowledge_items": 0,
                    "total_conventions": 0,
                    "faction_count": 0,
                    "avg_coherence_score": 0.0,
                }
                try:
                    from ..economy.knowledge_economy import get_knowledge_pool

                    pool = get_knowledge_pool()
                    snapshot_data["total_knowledge_items"] = len(pool.items) if hasattr(pool, "items") else 0
                except Exception:
                    pass
                try:
                    # Use top-level import to avoid shadowing
                    cp = get_convention_pool()
                    snapshot_data["total_conventions"] = len(cp.active) if hasattr(cp, "active") else 0
                except Exception:
                    pass
                try:
                    registry = get_registry()
                    snapshot_data["faction_count"] = len(registry.all_factions())
                except Exception:
                    pass
                try:
                    from .narrative_coherence import get_coherence_engine

                    ce = get_coherence_engine()
                    snapshot_data["avg_coherence_score"] = (
                        ce.last_score if hasattr(ce, "last_score") else 0.0
                    )
                except Exception:
                    pass

                chapter = almanac.generate_chapter(
                    tick=self._tick_count,
                    world_time=self._clock.now.isoformat() if self._clock.now else f"Day {self._tick_count//1440}",
                    snapshot_data=snapshot_data,
                    events=self._world.events,
                    digimon_data=digimon_data,
                )
                almanac.archive(chapter)
                # 广播为世界事件
                almanac_event = {
                    "type": "almanac_chapter",
                    "description": f"年鉴第 {chapter.epoch} 章已归档 (tick {chapter.tick_start}-{chapter.tick_end})",
                    "tick": self._tick_count,
                    "at": self._clock.now.isoformat() if self._clock.now else None,
                    "significance": 5,
                    "epoch": chapter.epoch,
                    "event_count": chapter.event_count,
                }
                self._world.events.append(almanac_event)
                logger.info(
                    "WorldAlmanac: Chapter %d archived (%d ticks, %d events)",
                    chapter.epoch,
                    chapter.tick_end - chapter.tick_start,
                    chapter.event_count,
                )
        except Exception as e:
            logger.debug("WorldAlmanac step failed: %s", e)
        # 9.9 Phase 25 上下文质量检测阶段:
        #    对每只 agent 生成 ContextQualitySnapshot，诊断问题，
        #    低健康分数的 agent 自动触发优化建议
        from .context_quality import get_health_monitor, get_optimizer
        monitor = get_health_monitor()
        optimizer = get_optimizer()
        critical_count = 0
        for agent in agents:
            snap = monitor.snapshot(agent, self._tick_count)
            issues = monitor.diagnose(snap)
            if snap.composite_health < 30.0:
                critical_count += 1
                actions = optimizer.recommend(snap, issues)
                # Log optimization recommendations (no auto-execution)
                for action in actions[:3]:
                    logger.info(
                        "ContextOptimizer: agent=%s action=%s priority=%d "
                        "target=%s improvement=%.1f",
                        agent.name, action.action_type, action.priority,
                        action.target_system, action.estimated_improvement,
                    )
        if critical_count > 0:
            logger.warning(
                "ContextQuality: %d/%d agents in critical context health",
                critical_count, len(agents),
            )
        self._tick_count += 1
        # 8. 持久化阶段: 每 SAVE_INTERVAL_TICKS 全量落盘一次
        if self._auto_save and self._tick_count % SAVE_INTERVAL_TICKS == 0:
            await self._auto_save_world()
            # Phase 13⑤: 每次 save 之后也创建快照 (每 SNAPSHOT_INTERVAL_TICKS)
            if SNAPSHOT_INTERVAL_TICKS > 0 and self._tick_count % SNAPSHOT_INTERVAL_TICKS == 0:
                await self._auto_snapshot_world()
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

    async def _auto_snapshot_world(self) -> None:
        """自动创建世界快照。失败只记 warning,不打断 tick 循环。"""
        try:
            from .persistence import DEFAULT_DB_PATH
            from .snapshots import get_snapshot_manager

            db_path = self._save_db_path or DEFAULT_DB_PATH
            mgr = get_snapshot_manager()
            await mgr.create(
                world_db_path=db_path,
                world_tick=self._tick_count,
                digimon_count=self._world.count(),
                note="auto",
            )
        except Exception as e:
            logger.warning("auto-snapshot failed at tick %d: %s", self._tick_count, e)

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

            # Phase 17: 获取双方 MBTI 类型用于人格兼容加成
            mbti_a = self._personality.get_or_create(a.name).type_code
            mbti_b = self._personality.get_or_create(b.name).type_code

            # 隐性欲望冷却减免: 有"想交朋友"类欲望的 agent 冷却窗口减半
            a_cooldown_minutes = DIALOGUE_COOLDOWN_MINUTES
            b_cooldown_minutes = DIALOGUE_COOLDOWN_MINUTES
            if a.latent_desire and ("交朋友" in a.latent_desire or "朋友" in a.latent_desire):
                a_cooldown_minutes = DIALOGUE_COOLDOWN_MINUTES // 2
            if b.latent_desire and ("交朋友" in b.latent_desire or "朋友" in b.latent_desire):
                b_cooldown_minutes = DIALOGUE_COOLDOWN_MINUTES // 2

            # 任一方仍在冷却期 → 不生成对话,但相遇本身也拉近一点关系(含欲望+MBTI加成)
            if self._in_cooldown(a, now, a_cooldown_minutes) or self._in_cooldown(b, now, b_cooldown_minutes):
                self._relationships.record_proximity_with_personality(
                    a.name, a.latent_desire, b.name, b.latent_desire,
                    mbti_a=mbti_a, mbti_b=mbti_b,
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
                # routine 事件: 仅记录亲近度,不调 LLM (含欲望+MBTI加成)
                self._relationships.record_proximity_with_personality(
                    a.name, a.latent_desire, b.name, b.latent_desire,
                    mbti_a=mbti_a, mbti_b=mbti_b,
                )
                self.skipped_llm_events += 1
                continue

            # Phase 11: 对话降频 — 即使满足所有条件,也只有配置概率真正触发对话
            # Phase 16: 用关系距离调节对话触发概率 (仅在非强制触发模式下)
            if self._dialogue_prob >= 1.0:
                effective_prob = 1.0  # 测试/强制模式: 始终触发
            else:
                rel_mod = get_interaction_modifier(a.name, b.name, self._relationships, "dialogue")
                effective_prob = min(1.0, self._dialogue_prob * rel_mod)
            if random.random() > effective_prob:
                self._relationships.record_proximity_with_personality(
                    a.name, a.latent_desire, b.name, b.latent_desire,
                    mbti_a=mbti_a, mbti_b=mbti_b,
                )
                self.skipped_dialogue_probs += 1
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

            # 一次成功对话 → 双方关系变友好(含欲望兼容+MBTI人格兼容加成)
            self._relationships.record_dialogue_with_personality(
                a.name, a.latent_desire, b.name, b.latent_desire,
                mbti_a=mbti_a, mbti_b=mbti_b,
            )

            # Phase 26: 记录对话互动的人格影响力（双向）
            try:
                dynamics = get_personality_dynamics_engine()
                dynamics.record_interaction(
                    influencer=a.name, influenced=b.name,
                    interaction_type="dialogue", magnitude=0.5,
                    tick=self._tick_count,
                )
                dynamics.record_interaction(
                    influencer=b.name, influenced=a.name,
                    interaction_type="dialogue", magnitude=0.5,
                    tick=self._tick_count,
                )
            except Exception:
                pass

            # 刷新双方冷却时间戳
            a.last_interaction_at = now
            b.last_interaction_at = now

            # Phase 23: 社交互动恢复认知能量
            a.cognitive_energy.recover(RECOVER_SOCIAL, "social_dialogue")
            b.cognitive_energy.recover(RECOVER_SOCIAL, "social_dialogue")

        # Phase 16: 战斗触发 — 对每对邻近 agent 独立检查, 与对话解耦
        # 仅在正常模式(非测试强制触发)下启用
        if self._dialogue_prob < 1.0:
            for a, b in pairs:
                if a.region_id != b.region_id:
                    continue
                # 战斗触发不与冷却绑定(战斗冲动 vs 对话倾向是独立系统)
                battle_mod = get_interaction_modifier(a.name, b.name, self._relationships, "battle")
                # 基础战斗概率 2%, 乘关系乘数
                base_battle_prob = 0.02
                effective_battle_prob = min(0.50, base_battle_prob * battle_mod)
                if random.random() < effective_battle_prob:
                    circle = get_circle_between(a.name, b.name, self._relationships)
                    try:
                        from ..battle.sparring import spar
                        spar(a, b)  # 不计返回值, 效果已在 agent 上生效
                        # 写入世界事件
                        self._world.events.append({
                            "type": "spar",
                            "attacker": a.name,
                            "defender": b.name,
                            "circle": circle.label_cn(),
                            "battle_mod": round(battle_mod, 2),
                            "at": self._clock.now.isoformat() if self._clock.now is not None else None,
                        })
                        # 敌对战斗后关系进一步恶化
                        if circle == RelationalCircle.HOSTILE:
                            self._relationships.record_battle(winner=a.name, loser=b.name)
                        # Phase 26: 战斗也影响人格（胜利方更果断，失败方更内向）
                        try:
                            dynamics = get_personality_dynamics_engine()
                            dynamics.record_interaction(
                                influencer=a.name, influenced=b.name,
                                interaction_type="battle", magnitude=0.7,
                                tick=self._tick_count,
                            )
                            dynamics.record_interaction(
                                influencer=b.name, influenced=a.name,
                                interaction_type="battle", magnitude=0.3,
                                tick=self._tick_count,
                            )
                        except Exception:
                            pass
                        # Phase 23: 战斗互动也恢复少量认知能量（激烈活动刺激思维）
                        a.cognitive_energy.recover(RECOVER_SOCIAL, "social_spar")
                        b.cognitive_energy.recover(RECOVER_SOCIAL, "social_spar")
                    except Exception as e:
                        logger.warning("spar trigger failed for %s / %s: %s", a.name, b.name, e)

        # Phase 16: 合作倾向 — intimate/close 圈层 agent 互相靠近
        # 仅在正常模式(非测试强制触发)下启用
        if self._dialogue_prob < 1.0:
            self._apply_cooperation_nudge(agents)

    # ---- Phase 16: 合作倾向处理 ----
    def _apply_cooperation_nudge(self, agents: list[DigimonAgent]) -> None:
        """对 intimate/close 圈层的 agent 对施加互相靠近的微调。

        在每个 tick 的互动阶段之后, 亲密圈层的 agent 会被轻微吸引向彼此,
        模拟协同行动倾向。步长为此处定义的 COOP_NUDGE_STEP。
        """
        COOP_NUDGE_STEP = 3  # noqa: N806 合作吸引步长(像素), 远小于普通移动步长
        pairs = detect_proximity(agents, radius=DIALOGUE_RADIUS)
        for a, b in pairs:
            if a.region_id != b.region_id:
                continue
            coop_mod = get_interaction_modifier(a.name, b.name, self._relationships, "cooperation")
            if coop_mod <= 1.0:
                continue  # 仅 intimate(1.5x) / close(1.3x) 有效
            # coop_mod > 1.0 → 互相靠近
            ax, ay = a.location
            bx, by = b.location
            import math
            dx = bx - ax
            dy = by - ay
            dist = math.sqrt(dx * dx + dy * dy) or 1.0
            step = COOP_NUDGE_STEP * (coop_mod - 1.0)  # 亲密越高吸引越强
            nx = dx / dist * step
            ny = dy / dist * step
            # a 向 b 靠近
            a.location = (max(0, int(ax + nx)), max(0, int(ay + ny)))
            # b 向 a 靠近
            b.location = (max(0, int(bx - nx)), max(0, int(by - ny)))

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

    # ---- Phase 14: 世界叙事处理 ----
    async def _process_narrative(self) -> None:
        """每 tick 调用,由 NarratorSystem 内部决定是否到叙事间隔。

        失败时优雅降级,不影响世界循环。
        """
        try:
            from .timeline import get_timeline_system

            narrator = get_narrator()
            timeline = get_timeline_system()
            await narrator.tick_async(self._world, timeline)
        except Exception as e:
            logger.warning("Narrator tick_async failed: %s", e)

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

    # ---- Phase 17: 人格演化 ----

    def _process_personality_events(self, agents: list[DigimonAgent]) -> None:
        """每 tick 根据最近事件推动数码兽人格维度漂移。

        扫描本 tick 产生的世界事件，将事件类型映射为人格影响向量，
        逐个 agent 演化其 MBTI 人格维度。

        人格演化不阻塞世界循环，失败静默降级。
        """
        try:
            # 取本 tick 新增的事件 (粗略策略: 最近 50 条)
            recent_events = self._world.events[-50:] if len(self._world.events) > 50 else self._world.events
            if not recent_events:
                return

            # 事件类型 → 人格事件映射
            event_to_personality: dict[str, str] = {
                "battle_victory": "battle_win",
                "battle_defeat": "battle_loss",
                "battle_draw": "battle_draw",
                "dialogue": "social_friendly",
                "dialogue_conflict": "social_conflict",
                "friendship_formed": "social_friendly",
                "faction_create": "social_friendly",
                "discovery": "explore_discovery",
                "landmark_discovered": "explore_discovery",
                "moved": "explore_discovery",
                "threat": "social_conflict",
                "near_death": "injury",
                "evolution": "evolution",
                "save_other": "save_other",
                "festival": "social_friendly",
                "dark_gear_infection": "social_conflict",
            }

            # 收集每个 agent 应该触发的事件
            agent_personality_events: dict[str, list[str]] = {}
            for event in recent_events:
                p_event = event_to_personality.get(event.get("type", ""))
                if p_event is None:
                    continue

                # 找出受影响的 agent(s)
                agent_name = event.get("agent", "")
                if agent_name:
                    agent_personality_events.setdefault(agent_name, []).append(p_event)

                # "target" / "listener" 也受影响
                for key in ("target", "listener"):
                    target_name = event.get(key, "")
                    if target_name:
                        agent_personality_events.setdefault(target_name, []).append(p_event)

            # 为每个 agent 应用人格事件
            for agent in agents:
                p_events = agent_personality_events.get(agent.name, [])
                if not p_events:
                    # 没有显著事件 → 微量回归均值 (让极端人格缓慢漂回)
                    # 不给 alone_time 事件，只靠回归均值自然衰减
                    continue

                for p_event in p_events:
                    multiplier = 1.0
                    # 重大事件加倍影响
                    if p_event in ("evolution", "save_other", "near_death"):
                        multiplier = 2.0
                    self._personality.apply_event(
                        agent.name,
                        p_event,
                        multiplier=multiplier,
                        description=f"tick #{self._tick_count}",
                    )

        except Exception as e:
            logger.debug("Personality evolution tick failed: %s", e)

    def _in_cooldown(self, agent: DigimonAgent, now: Any, cooldown_minutes: float | None = None) -> bool:
        """判断 agent 是否仍在互动冷却窗口内。"""
        if agent.last_interaction_at is None or now is None:
            return False
        elapsed_minutes = (now - agent.last_interaction_at).total_seconds() / 60
        threshold = cooldown_minutes if cooldown_minutes is not None else DIALOGUE_COOLDOWN_MINUTES
        return elapsed_minutes < threshold

    async def _step_agent(self, agent: DigimonAgent) -> dict[str, Any]:
        """调用单个 agent.step(),捕获异常不让一只炸了拖死整个 tick。

        Phase 11 优化 + 扩容 30→100:
        - 计划缓存: 60 tick 内从缓存取,不调 LLM planner
        - 思考轮次: 每 20 tick 才批量触发 reflect
        - 移动: 每 MOVE_LLM_TICKS 才调 LLM planner,中间用简单向量+噪声
        - LLM 节流: 每 tick 只让 N=总数/5 只 agent 调 LLM,其余用缓存(随机错开)
        """
        try:
            # Phase 11: 计划缓存 — 缓存未过期则跳过 LLM planner 调用
            cache_entry = self._plan_cache.get(agent.name)
            if cache_entry is not None:
                cached_plan, cached_at = cache_entry
                if self._tick_count - cached_at < PLAN_CACHE_TICKS:
                    # 直接用缓存计划,跳过 LLM planner
                    agent.current_plan = cached_plan
                    self.skipped_plan_calls += 1
                    return await self._step_with_cached_plan(agent)
                else:
                    # 缓存过期,移除
                    del self._plan_cache[agent.name]

            # Phase 11: 移动决策降频 — 非 plan-refresh tick 用简单向量+噪声
            if self._tick_count % MOVE_LLM_TICKS != 0:
                # 降频模式: 用已有的 current_plan 做向量移动(不调 LLM)
                self.skipped_plan_calls += 1
                return await self._step_with_cached_plan(agent)

            # 扩容优化: LLM 节流 — 每 tick 只让 N=总数/5 只 agent 调 LLM
            # 用 (agent.name hash + tick 轮次) 确定性错开,保证各 agent 轮流获得 LLM 配额
            agents = self._world.all()
            total_agents = len(agents)
            if total_agents > 5:
                n_llm_quota = max(1, total_agents // 5)
                tick_round = self._tick_count // MOVE_LLM_TICKS
                slot = (hash(agent.name) + tick_round) % total_agents
                if slot >= n_llm_quota:
                    self.skipped_plan_calls += 1
                    return await self._step_with_cached_plan(agent)

            # 正常路径: 调 LLM step (包含 plan + act)
            result = await agent.step(self._world.regions, tick_index=self._tick_count)
            # 缓存新生成的计划
            if agent.current_plan:
                self._plan_cache[agent.name] = (agent.current_plan, self._tick_count)
            return result
        except Exception as e:
            logger.exception("agent.step failed for %s: %s", agent.name, e)
            return {
                "type": "step_error",
                "agent": agent.name,
                "error": str(e),
            }

    async def _step_with_cached_plan(self, agent: DigimonAgent) -> dict[str, Any]:
        """用已缓存的计划做简单移动(向量+噪声),不调 LLM。

        适合: 计划缓存生效期 / 移动降频 tick。
        逻辑: 对 current_plan 做关键词解析 → 方向位移;无方向则随机一步。
        不经过 agent.step(),因此单独应用每 tick 能量消耗。
        """
        try:
            # Phase 23: 对缓存路径应用认知能量消耗
            agent.apply_tick_energy()
            return agent.act(self._world.regions)
        except Exception as e:
            logger.exception("agent.act (cached) failed for %s: %s", agent.name, e)
            return {
                "type": "step_error",
                "agent": agent.name,
                "error": str(e),
            }

    async def _batch_reflect(self, agents: list[DigimonAgent]) -> None:
        """Phase 11: 批量思考轮次 — 收集需要反思的 agent 一起调 LLM。

        只在思考轮次 tick (每 THINK_ROUND_INTERVAL) 调用。
        并发执行所有 agent.reflect_if_needed()。
        """
        if self._tick_count - self._last_think_round < THINK_ROUND_INTERVAL:
            return
        self._last_think_round = self._tick_count

        reflect_tasks = []
        for agent in agents:
            if agent.reflector is not None and agent.memory.should_reflect():
                reflect_tasks.append(agent.reflect_if_needed(self._tick_count))
            else:
                self.skipped_reflect_calls += 1

        if reflect_tasks:
            results = await asyncio.gather(*reflect_tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    logger.warning("batch reflect failed: %s", r)

    async def _propagate_affect(self, agents: list[DigimonAgent]) -> None:
        """Phase 16: 情感传播 — 检测情绪剧变并按关系距离传播。

        当某只数码兽的 CPM mood_state 任一维度变化超过阈值时,
        将其情感按差序格局的圈层距离衰减后传播给其他数码兽。
        """
        changed = self._affect_engine.detect_changes(self._world)
        if not changed:
            return

        for agent_name, delta in changed:
            source = self._world.get(agent_name)
            if source is None:
                continue
            affect = self._affect_engine.mood_to_affect(source)
            result = self._affect_engine.propagate(
                agent_name, affect, self._world, tracker=self._relationships,
            )
            if result:
                affected_names = [r["name"] for r in result]
                logger.debug(
                    "affect propagation: %s → %s (delta joy=%.2f sadness=%.2f anger=%.2f fear=%.2f)",
                    agent_name, affected_names,
                    delta.get("joy", 0), delta.get("sadness", 0),
                    delta.get("anger", 0), delta.get("fear", 0),
                )
                # 将传播事件写入世界日志
                self._world.events.append({
                    "type": "affect_propagation",
                    "source": agent_name,
                    "affected": affected_names,
                    "delta": delta,
                    "at": str(self._clock.elapsed_minutes),
                })

    async def run_forever(
        self,
        tick_seconds: float = DEFAULT_TICK_SECONDS,
        stop_on: Callable[[], bool] | None = None,
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
