"""
FastAPI App - 数码世界后端 HTTP 接口
====================================

Phase 1-11 接口:
- GET  /                      — 健康检查 + 元信息
- GET  /api/digimon           — 数码兽列表
- GET  /api/digimon/{name}    — 单只数码兽详情
- GET  /api/digimon/{name}/position — 单只数码兽位置
- POST /api/digimon/{name}/move — 移动数码兽 (body: {dx, dy})
- GET  /api/world             — 整个世界快照(给前端用)
- WS   /ws/world              — 世界状态实时推送
- POST /api/battle/start      — 战斗引擎
- GET  /api/vitality          — 世界活力指标
- GET  /api/emergence         — 涌现指标 (Phase 11)
- GET  /api/multiverse        — 多元宇宙管理 (Phase 9+)
- POST /api/multiverse/migrate — 批量跨世界迁移 (Phase 12)
- POST /api/multiverse/auto-migrate — 自动跨世界迁移 (Phase 12)

Phase 13 新增 (多模态):
- GET  /api/tts/{name}        — 数码兽 TTS 语音 (wav)
- POST /api/tts/speak         — 让数码兽说指定文本
- GET  /api/tts/voices        — 可用数码兽声音列表

详细设计: docs/DESIGN.md 第 7 节
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import __version__
from .pokedex import router as pokedex_router
from ..agents.achievements import AchievementSystem
from ..agents.badges import BadgeSystem
from ..agents.dialogue import Dialogue
from ..agents.evolution import EvolutionSystem
from ..agents.healing import get_healing_system
from ..battle import BattleEngine, BattleResult, spar
from ..llm.client import get_client
from .. import tts as tts_module
from ..world import (
    WorldClock,
    WorldScheduler,
    compute_vitality,
    get_dark_gear_system,
    get_daynight_system,
    get_director,
    get_ecology_system,
    get_landmark_system,
    get_multiverse,
    get_narrator,
    get_registry,
    get_snapshot_manager,
    get_timeline_system,
    get_tracker,
    get_weather_system,
    get_world,
    persistence,
)

logger = logging.getLogger("digimon.api")

# ---- Pydantic models ----
class Position(BaseModel):
    x: int
    y: int


class MoveRequest(BaseModel):
    dx: int = Field(..., ge=-200, le=200, description="X 方向位移(像素)")
    dy: int = Field(..., ge=-200, le=200, description="Y 方向位移(像素)")


class MoveResponse(BaseModel):
    name: str
    position: Position


# ---- Phase 4: 观察者/导演 API ----
class InjectEventRequest(BaseModel):
    """导演往世界里注入一个事件(如天灾、访客、剧情触发)。"""

    type: str
    region_id: str | None = None
    description: str
    importance: int = 5
    # type == 'faction_create' 时: 派系 id + 成员(逗号分隔)
    faction_id: str | None = None
    members: str | None = None
    # Phase 5 多元宇宙:
    # type == 'world_create' 时: 新世界 id(不给则自动生成)
    # type == 'digital_gate' 时: agent + from_world + to_world 决定跨世界迁移
    world_id: str | None = None
    agent: str | None = None
    from_world: str | None = None
    to_world: str | None = None


class SpeedRequest(BaseModel):
    """调整世界时间流速(现实 1 秒 = 世界 ratio 分钟)。"""

    ratio: int


class BroadcastRequest(BaseModel):
    """导演向全服所有数码兽发布一条广播通知。"""

    message: str = Field(..., min_length=1, description="广播内容")


# ---- Phase 13: TTS 配音 API 模型 ----
class SpeakRequest(BaseModel):
    """让指定数码兽说出一段文本。"""

    name: str = Field(..., min_length=1, description="数码兽名称 (如 agumon)")
    text: str = Field(..., min_length=1, max_length=500, description="要说的话")


# ---- Phase 3: 战斗 API 模型 ----
class BattleStartRequest(BaseModel):
    """发起一场 A vs B 战斗。"""

    attacker: str = Field(..., description="先手方名字")
    defender: str = Field(..., description="后手方名字")
    use_llm: bool = Field(default=False, description="是否用 LLM 决策动作")


class BattleStartResponse(BaseModel):
    """战斗结果 + 触发的进化事件。"""

    result: dict[str, Any]
    evolution: Optional[dict[str, Any]] = None
    event_id: int


class SparRequest(BaseModel):
    """发起一场 A vs B 友好切磋。"""

    attacker: str = Field(..., description="发起方名字")
    defender: str = Field(..., description="陪练方名字")


class HealRequest(BaseModel):
    """使用治疗道具让数码兽立即回满 HP。"""

    item_name: str = Field(default="治疗道具", description="治疗道具名(仅用于事件展示)")


# ---- Lifespan (replaces deprecated on_event) ----


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """启动/关闭时管理后台任务(调度器/广播器)。"""
    # startup
    world = get_world()
    _app.state.broadcaster = asyncio.create_task(_position_broadcaster())

    clock = WorldClock(real_to_world_ratio=world.real_to_world_ratio)
    dialogue = Dialogue(llm_client=get_client())
    scheduler = WorldScheduler(
        world=world,
        clock=clock,
        dialogue=dialogue,
        relationships=get_tracker(),
        factions=get_registry(),
        story_director=get_director(),
        auto_save=True,
    )
    _app.state.world_clock = clock
    _app.state.scheduler = scheduler
    _app.state.scheduler_task = asyncio.create_task(scheduler.run_forever())

    yield  # app runs here

    # shutdown
    for attr in ("broadcaster", "scheduler_task"):
        task: Optional[asyncio.Task] = getattr(_app.state, attr, None)
        if task is not None:
            task.cancel()


# ---- App ----
app = FastAPI(
    title="DIGIMON WORLD API",
    description="数码宝贝虚拟世界后端 (Phase 11)",
    version=__version__,
    lifespan=lifespan,
)

# 开发期 CORS 全开(前端可能在 8080 端口)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 数码兽图鉴 (静态资料库) 路由
app.include_router(pokedex_router)


# ---- Routes ----
@app.get("/")
def root() -> dict[str, Any]:
    """健康检查 + 元信息。"""
    world = get_world()
    return {
        "name": "DIGIMON WORLD",
        "version": __version__,
        "phase": 12,
        "status": "ok",
        "digimon_count": world.count(),
        "chosen_children_count": len(_chosen_children),
        "regions": list(world.regions.keys()),
    }


@app.get("/api/digimon")
def list_digimon() -> dict[str, Any]:
    """所有数码兽的精简列表(给前端用,只返回关键字段)。"""
    world = get_world()
    return {
        "count": world.count(),
        "digimon": [
            {
                "name": a.name,
                "species": a.species,
                "stage": a.stage.value,
                "attribute": a.attribute.value,
                "region_id": a.region_id,
                "position": {"x": a.location[0], "y": a.location[1]},
                "current_plan": a.current_plan,
                "mood": a.mood,
            }
            for a in world.all()
        ],
    }


@app.get("/api/digimon/{name}")
def get_digimon(name: str) -> dict[str, Any]:
    """单只数码兽的完整数据(序列化字典)。"""
    world = get_world()
    agent = world.get(name)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Digimon '{name}' not found")
    return agent.to_dict()


@app.get("/api/digimon/{name}/position")
def get_position(name: str) -> Position:
    world = get_world()
    agent = world.get(name)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Digimon '{name}' not found")
    return Position(x=agent.location[0], y=agent.location[1])


@app.post("/api/digimon/{name}/move", response_model=MoveResponse)
def move_digimon(name: str, req: MoveRequest) -> MoveResponse:
    world = get_world()
    new_pos = world.move(name, req.dx, req.dy)
    if new_pos is None:
        raise HTTPException(status_code=404, detail=f"Digimon '{name}' not found or region missing")
    return MoveResponse(name=name, position=Position(x=new_pos[0], y=new_pos[1]))


@app.post("/api/digimon/{name}/heal")
def heal_digimon(name: str, req: HealRequest) -> dict[str, Any]:
    """使用治疗道具让数码兽立即回满 HP。

    自然回血(每 tick +1,神殿附近 +5)由 scheduler 自动处理;
    本接口是「手动嗑一颗治疗道具直接回满」的即时操作。
    """
    world = get_world()
    agent = world.get(name)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Digimon '{name}' not found")
    event = get_healing_system().heal_with_item(agent, item_name=req.item_name)
    # 让数码兽记住这次治疗(接入自身记忆流)
    agent.observe(event)
    world.events.append(event)
    return {
        "name": name,
        "hp": agent.stats.hp,
        "max_hp": agent.stats.max_hp,
        "event": event,
    }


@app.get("/api/world")
def get_world_snapshot() -> dict[str, Any]:
    """整个世界快照(前端 canvas 渲染用)。"""
    return get_world().to_dict()


# ---- Phase 7: 因果链 & 世界活力 API ----
@app.get("/api/causality/{event_id}")
def get_causality_chain(event_id: int) -> dict[str, Any]:
    """回溯任意事件的完整因果链。

    从指定 event_id 向上追溯 cause_event_id,直到根因。
    返回 {event, chain, root_cause, depth}。
    """
    world = get_world()
    return world.build_causality_chain(event_id)


@app.get("/api/world/vitality")
def get_world_vitality() -> dict[str, Any]:
    """世界活力指标: entropy / social_density / event_diversity / interaction_rate / mood_variance。

    综合活力分数 (0-100),前端 stats 面板展示。
    """
    world = get_world()
    vitality = compute_vitality(world)
    return vitality.to_dict()


@app.get("/api/emergence")
def get_emergence_metrics() -> dict[str, Any]:
    """涌现指标: 社交网络分析 + 行为多样性 + 情绪传染 + 涌现事件。

    Phase 11 科研级端点，用于量化「世界是否涌现复杂结构」。
    """
    world = get_world()
    from ..world.emergence_metrics import compute_emergence_metrics
    snapshot = compute_emergence_metrics(world)
    return snapshot.to_dict()


@app.post("/api/world/save")
async def save_world() -> dict[str, Any]:
    """手动全量保存世界状态到 SQLite(data/world.db)。"""
    world = get_world()
    await persistence.save(world, get_tracker())
    return {"status": "saved", "digimon_count": world.count()}


@app.post("/api/world/load")
async def load_world() -> dict[str, Any]:
    """手动从 SQLite 全量恢复世界状态。库不存在则 loaded=False。"""
    world = get_world()
    loaded = await persistence.load(world, get_tracker())
    return {"status": "loaded" if loaded else "no_data", "digimon_count": world.count()}


# ---- Phase 13⑤: 世界快照存档 API ----
class SnapshotCreateRequest(BaseModel):
    """创建快照时可选的备注。"""
    note: str = ""


@app.get("/api/snapshots")
async def list_snapshots() -> dict[str, Any]:
    """列出所有快照(按时间降序)。"""
    mgr = get_snapshot_manager()
    snapshots = await mgr.list()
    return {"count": len(snapshots), "snapshots": snapshots}


@app.post("/api/snapshots")
async def create_snapshot(req: SnapshotCreateRequest = SnapshotCreateRequest()) -> dict[str, Any]:
    """手动创建世界快照。"""
    world = get_world()
    scheduler: Optional[WorldScheduler] = getattr(app.state, "scheduler", None)
    tick = scheduler.tick_count if scheduler is not None else 0

    mgr = get_snapshot_manager()
    snapshot_id = await mgr.create(
        world_db_path=persistence.DEFAULT_DB_PATH,
        world_tick=tick,
        digimon_count=world.count(),
        note=req.note or "",
    )
    if snapshot_id is None:
        return {"status": "error", "detail": "snapshot create failed (check world.db exists)"}

    return {"status": "created", "snapshot_id": snapshot_id, "tick": tick}


@app.post("/api/snapshots/{snapshot_id}/restore")
async def restore_snapshot(snapshot_id: str) -> dict[str, Any]:
    """从指定快照回滚世界状态。

    注意: 回滚后内存里的 world_state 不会自动更新。
    需要手动调用 POST /api/world/load 加载回滚后的 world.db。
    """
    mgr = get_snapshot_manager()
    ok = await mgr.restore(snapshot_id, persistence.DEFAULT_DB_PATH)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Snapshot '{snapshot_id}' not found or restore failed")

    # 自动重新加载到内存
    world = get_world()
    await persistence.load(world, get_tracker())
    return {"status": "restored", "snapshot_id": snapshot_id, "digimon_count": world.count()}


@app.get("/api/scheduler/status")
def get_scheduler_status() -> dict[str, Any]:
    """调度器运行状态(前端调试用)。

    返回 running / tick_count / current_world_time。
    调度器尚未启动(如未走 startup)时返回 running=False 的兜底值。
    """
    scheduler: Optional[WorldScheduler] = getattr(app.state, "scheduler", None)
    task: Optional[asyncio.Task] = getattr(app.state, "scheduler_task", None)
    clock: Optional[WorldClock] = getattr(app.state, "world_clock", None)

    running = task is not None and not task.done()
    return {
        "running": running,
        "tick_count": scheduler.tick_count if scheduler is not None else 0,
        "current_world_time": clock.format_clock() if clock is not None else None,
    }


# ---- Phase 14: 世界叙事 API ----
@app.get("/api/narratives")
def get_narratives(limit: int = 10) -> dict[str, Any]:
    """获取最近 N 条世界叙事条目。

    Args:
        limit: 返回条数 (默认 10)。

    Returns:
        {count: 总篇数, entries: [最近 limit 篇]}。
    """
    n = get_narrator()
    journal = n.journal[-max(1, limit):]
    return {"count": n.narration_count, "entries": journal}


@app.get("/api/narratives/latest")
def get_latest_narrative() -> dict[str, Any]:
    """获取最新一篇世界叙事。

    Returns:
        最新叙事条目 dict。

    Raises:
        404: 尚未生成任何叙事。
    """
    n = get_narrator()
    if not n.journal:
        raise HTTPException(status_code=404, detail="No narratives yet — 世界故事正在酝酿中…")
    return n.journal[-1]


@app.get("/api/digimon/{name}/memories")
def get_digimon_memories(name: str) -> dict[str, Any]:
    """某只数码兽最近 10 条记忆(前端调试用)。"""
    world = get_world()
    agent = world.get(name)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Digimon '{name}' not found")
    recent = agent.memory.entries[-10:]
    return {
        "name": name,
        "count": len(recent),
        "memories": [m.to_dict() for m in recent],
    }


# ---- Phase 4: 观察者/导演接口 ----
@app.post("/api/director/inject_event")
def director_inject_event(req: InjectEventRequest) -> dict[str, Any]:
    """导演注入一条世界事件。

    直接 append 到 world_state.events,返回该事件的序号(id)。
    """
    world = get_world()
    event = {
        "type": req.type,
        "region_id": req.region_id,
        "description": req.description,
        "importance": req.importance,
        "source": "director",
        "at": datetime.now().isoformat(),
    }
    world.events.append(event)

    # type == 'faction_create' → 顺手在派系登记处凭空造一个命名派系。
    # 成员从 members 字段读(逗号分隔),派系 id / name 从 faction_id / description 读。
    if req.type == "faction_create":
        registry = get_registry()
        members = [m.strip() for m in (req.members or "").split(",") if m.strip()]
        faction_id = req.faction_id or f"faction_director_{len(registry.all_factions())}"
        faction = registry.inject_faction(
            faction_id=faction_id,
            members=members,
            name=req.description or faction_id,
        )
        event["faction_id"] = faction.faction_id
        event["members"] = sorted(faction.members)

    # ---- 查找受影响的数码兽，生成 affected_agents 和 impact_summary ----
    event_region = req.region_id
    agents = world.all()

    # 筛选同区域的数码兽；无 region_id 或 "global" 则影响全部
    if event_region and event_region != "global":
        affected = [a for a in agents if a.region_id == event_region]
    else:
        affected = agents

    reactions = ["惊讶", "好奇", "警惕", "兴奋", "紧张", "观望"]
    affected_agents = [
        {"name": a.name, "reaction": random.choice(reactions)}
        for a in affected
    ]

    if affected_agents:
        region_hint = f"（{event_region}）" if event_region and event_region != "global" else ""
        impact_summary = f"{req.description}{region_hint}，{len(affected_agents)}只数码兽受到影响"
    else:
        impact_summary = req.description

    # id 用当前列表长度 - 1 (即刚 append 的索引)
    return {
        "id": len(world.events) - 1,
        "type": req.type,
        "description": req.description,
        "affected_agents": affected_agents,
        "impact_summary": impact_summary,
    }


@app.post("/api/broadcast")
def broadcast_message(req: BroadcastRequest) -> dict[str, Any]:
    """导演发布全服广播: 所有数码兽收到通知(写入各自 memory)。

    用于全服公告、剧情推进、节日通知等场景。
    返回收到广播的数码兽数量。
    """
    world = get_world()
    agents = world.all()
    event = {
        "type": "broadcast",
        "message": req.message,
        "source": "director",
        "at": datetime.now().isoformat(),
    }
    # 每只数码兽写一条记忆
    for agent in agents:
        agent.observe(event)
    # 同时记录为世界事件
    world.events.append(event)
    return {
        "delivered": len(agents),
        "message": req.message,
        "event_id": len(world.events) - 1,
    }


@app.post("/api/director/speed")
def director_speed(req: SpeedRequest) -> dict[str, Any]:
    """调整世界时间流速,返回旧/新 ratio。"""
    world = get_world()
    old_ratio = world.real_to_world_ratio
    world.real_to_world_ratio = req.ratio
    return {"old_ratio": old_ratio, "new_ratio": req.ratio}


@app.get("/api/director/state")
def director_state() -> dict[str, Any]:
    """导演视角状态: 当前流速 / 世界时间 / 最近 10 条事件 / 派系列表 / 环境数据。"""
    world = get_world()
    clock: Optional[WorldClock] = getattr(app.state, "world_clock", None)
    return {
        "ratio": world.real_to_world_ratio,
        "current_world_time": clock.format_clock() if clock is not None else None,
        "recent_events": world.events[-10:],
        "factions": [f.to_dict() for f in get_registry().all_factions()],
        "daynight": get_daynight_system().to_dict(),
        "weather": get_weather_system().to_dict(),
        "ecology": get_ecology_system().to_dict(),
    }


@app.get("/api/director/injected-events")
def get_injected_events(limit: int = 10) -> dict[str, Any]:
    """返回最近 N 条来源为 'director' 的世界事件。

    Args:
        limit: 返回条数 (默认 10)。

    Returns:
        {count: 总导演事件数, events: [最近 limit 条, 最新在前]}。
    """
    world = get_world()
    injected = [
        {
            "id": idx,
            "type": e.get("type", ""),
            "description": e.get("description", ""),
            "at": e.get("at", ""),
            "importance": e.get("importance", 0),
            "region_id": e.get("region_id"),
        }
        for idx, e in enumerate(world.events)
        if e.get("source") == "director"
    ]
    recent = injected[-max(1, limit):]
    return {"count": len(injected), "events": list(reversed(recent))}


# ---- Phase 3: 战斗 API ----

# 内存里的战斗历史(轻量,只存最近 20 场,够前端调试 / Director 视角看)
_BATTLE_HISTORY: list[dict[str, Any]] = []
_BATTLE_HISTORY_MAX: int = 20


def _result_to_dict(result: BattleResult) -> dict[str, Any]:
    """BattleResult → API 友好的字典。"""
    return {
        "winner": result.winner_name,
        "rounds": result.rounds,
        "final_hp": result.final_hp,
    }


@app.post("/api/battle/start", response_model=BattleStartResponse)
async def start_battle(req: BattleStartRequest) -> BattleStartResponse:
    """发起一场战斗,跑完一轮,赢家 battle_victories+1。

    流程:
    1. 取两只数码兽(404 if not found)
    2. 跑 BattleEngine (脚本式 / LLM 决策)
    3. 赢家 +1 victory + 写 battle_victory 记忆 (importance=9)
    4. 调用 EvolutionSystem.check_and_evolve() 检查进化
    5. 写一条世界事件 (source="battle") → 返回 event id
    6. 把战斗结果放进 _BATTLE_HISTORY
    """
    world = get_world()
    a = world.get(req.attacker)
    b = world.get(req.defender)
    if a is None:
        raise HTTPException(status_code=404, detail=f"Digimon '{req.attacker}' not found")
    if b is None:
        raise HTTPException(status_code=404, detail=f"Digimon '{req.defender}' not found")
    if a.name == b.name:
        raise HTTPException(status_code=400, detail="Cannot battle yourself")

    engine = BattleEngine()
    llm_client = get_client() if req.use_llm else None
    result = await engine.run_battle(a, b, llm_client=llm_client)

    # 赢家 +1 victory, 写记忆, 触发进化
    evo_result_dict: Optional[dict[str, Any]] = None
    if result.winner_name is not None:
        winner = world.get(result.winner_name)
        if winner is not None:
            winner.battle_victories += 1
            winner.observe(
                {
                    "type": "battle_victory",
                    "opponent": result.winner_name and (
                        a.name if winner.name == a.name else b.name
                    ),
                    "rounds": result.rounds,
                }
            )
            # 检查进化 (bond 从 memory 流里自动累加)
            evo = EvolutionSystem()
            bond = evo.compute_bond(winner)
            evo_r = evo.check_and_evolve(
                winner, battle_victories=winner.battle_victories, bond=bond
            )
            if evo_r.evolved:
                evo_result_dict = evo_r.to_dict()

    # 战斗后自动调整社交关系: 双方变敌对, 输方对赢方生出敬畏
    if result.winner_name is not None:
        loser_name = b.name if result.winner_name == a.name else a.name
        get_tracker().record_battle(winner=result.winner_name, loser=loser_name)

    # 写世界事件
    event = {
        "type": "battle",
        "attacker": a.name,
        "defender": b.name,
        "winner": result.winner_name,
        "rounds": result.rounds,
        "use_llm": req.use_llm,
        "evolution": evo_result_dict,
        "at": datetime.now().isoformat(),
    }

    # 黑色齿轮交互: 战斗发生在感染子区域时,自动尝试摧毁齿轮 (Phase 8)
    dgs = get_dark_gear_system()
    for agent in (a, b):
        sr = world.get_sub_region(agent)
        if sr and dgs.is_sub_region_infected(sr["id"]):
            stage_multiplier = {
                "FRESH": 0.5, "IN_TRAINING": 0.75, "ROOKIE": 1.0,
                "CHAMPION": 1.5, "ULTIMATE": 2.0, "MEGA": 3.0,
            }.get(agent.stage.value, 1.0) if agent.stage else 1.0
            gear_destroyed, gear_msg = dgs.try_destroy_gear(
                sr["id"], damage_multiplier=stage_multiplier
            )
            if gear_destroyed:
                event["gear_destroyed"] = True
                event["gear_destroyed_by"] = agent.name
                event["gear_msg"] = gear_msg
                # 摧毁齿轮的数码兽也获得记忆
                agent.observe({
                    "type": "gear_destroyed",
                    "description": f"在战斗中摧毁了{sr['name']}的黑色齿轮! {gear_msg}",
                    "sub_region_id": sr["id"],
                })
    world.events.append(event)
    event_id = len(world.events) - 1

    # 加入战斗历史(只保留最近 N 场)
    history_entry = {
        "event_id": event_id,
        "attacker": a.name,
        "defender": b.name,
        "winner": result.winner_name,
        "rounds": result.rounds,
        "evolution": evo_result_dict,
        "at": event["at"],
    }
    _BATTLE_HISTORY.append(history_entry)
    if len(_BATTLE_HISTORY) > _BATTLE_HISTORY_MAX:
        del _BATTLE_HISTORY[: len(_BATTLE_HISTORY) - _BATTLE_HISTORY_MAX]

    return BattleStartResponse(
        result=_result_to_dict(result),
        evolution=evo_result_dict,
        event_id=event_id,
    )


@app.get("/api/battle/recent")
def recent_battles(limit: int = 10) -> dict[str, Any]:
    """最近 N 场战斗记录 (给 Director 观察者视角用)。"""
    n = max(1, min(limit, _BATTLE_HISTORY_MAX))
    return {
        "count": len(_BATTLE_HISTORY),
        "battles": _BATTLE_HISTORY[-n:][::-1],  # 最新在前
    }


@app.get("/api/digimon/{name}/battle_victories")
def get_battle_victories(name: str) -> dict[str, Any]:
    """某只数码兽的战斗胜利累计(前端调试用)。"""
    world = get_world()
    agent = world.get(name)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Digimon '{name}' not found")
    return {"name": name, "battle_victories": agent.battle_victories}


@app.post("/api/battle/spar")
def start_spar(req: SparRequest) -> dict[str, Any]:
    """发起一场友好切磋(不计胜负、不改社交关系)。

    与 /api/battle/start 的区别:
    - 无胜者、不加 battle_victories、不触发进化、不改社交关系
    - 双方各自 happiness +5、experience +2
    """
    world = get_world()
    a = world.get(req.attacker)
    b = world.get(req.defender)
    if a is None:
        raise HTTPException(status_code=404, detail=f"Digimon '{req.attacker}' not found")
    if b is None:
        raise HTTPException(status_code=404, detail=f"Digimon '{req.defender}' not found")
    if a.name == b.name:
        raise HTTPException(status_code=400, detail="Cannot spar with yourself")

    result = spar(a, b)
    return result.to_dict()


# ---- Phase 4: 社交关系 API ----
@app.get("/api/relationships")
def get_relationships() -> dict[str, Any]:
    """所有数码兽两两关系对: {pairs: [{a, b, score}, ...]}。

    正数=友好, 负数=敌对, 0=中立。给前端画派系图 / Director 观察阵营用。
    """
    pairs = get_tracker().all_pairs()
    return {"count": len(pairs), "pairs": pairs}


# ---- 排行榜 API ----
@app.get("/api/leaderboard")
def get_leaderboard(
    type: str = "battle",
    top: int = 10,
) -> dict[str, Any]:
    """数码兽排行榜: 按 type 维度返回降序 Top-N。

    type:
        battle  — 按战斗胜利数排名
        bond    — 按羁绊值(bond)排名
        badges  — 按徽章数排名
        all     — 返回全部三个维度(兼容旧版)

    返回 JSON: {"type": "battle", "leaders": [{"name": "亚古兽", "score": 5, "detail": "..."}]}
    """
    world = get_world()
    evo = EvolutionSystem()
    badge_system = BadgeSystem(world=world, tracker=get_tracker())
    n = max(1, min(top, 50))
    agents = world.all()

    # 如果请求 all,返回旧格式兼容
    if type == "all":
        battle = sorted(
            ({"name": a.name, "victories": a.battle_victories} for a in agents),
            key=lambda x: x["victories"],
            reverse=True,
        )
        bond = sorted(
            ({"name": a.name, "bond": evo.compute_bond(a)} for a in agents),
            key=lambda x: x["bond"],
            reverse=True,
        )
        badges = sorted(
            ({"name": a.name, "badges": len(badge_system.evaluate(a))} for a in agents),
            key=lambda x: x["badges"],
            reverse=True,
        )
        return {
            "battle": battle[:n],
            "bond": bond[:n],
            "badges": badges[:n],
        }

    # 单维度排行榜
    leaders: list[dict[str, Any]] = []
    if type == "battle":
        leaders = sorted(
            ({"name": a.name, "score": a.battle_victories, "detail": f"{a.battle_victories} 胜"} for a in agents),
            key=lambda x: x["score"],
            reverse=True,
        )
    elif type == "bond":
        # 计算关系总和: 该 agent 与其他所有 agent 的关系值之和
        tracker = get_tracker()
        for agent in agents:
            total_bond = sum(
                tracker.get_relationship(agent.name, other.name)
                for other in agents
                if other.name != agent.name
            )
            leaders.append({"name": agent.name, "score": round(total_bond, 1), "detail": f"关系总和 {total_bond:.1f}"})
        leaders.sort(key=lambda x: x["score"], reverse=True)
    elif type == "badges":
        leaders = sorted(
            ({"name": a.name, "score": len(badge_system.evaluate(a)), "detail": f"{len(badge_system.evaluate(a))} 枚徽章"} for a in agents),
            key=lambda x: x["score"],
            reverse=True,
        )
    else:
        # 未知 type 回退到 battle
        leaders = sorted(
            ({"name": a.name, "score": a.battle_victories, "detail": f"{a.battle_victories} 胜"} for a in agents),
            key=lambda x: x["score"],
            reverse=True,
        )

    return {
        "type": type,
        "leaders": leaders[:n],
    }


# ---- 天气 API ----
@app.get("/api/weather")
def get_weather() -> dict[str, Any]:
    """当前天气状态(天气类型 + 行为系数)。"""
    return get_weather_system().to_dict()


# ---- Phase 10: 环境演化 API ----
@app.get("/api/daynight")
def get_daynight() -> dict[str, Any]:
    """当前昼夜状态(时段 + 行为系数)。"""
    return get_daynight_system().to_dict()


@app.get("/api/ecology")
def get_ecology() -> dict[str, Any]:
    """当前生态状态(各区域食物量 + 植被覆盖率)。"""
    return get_ecology_system().to_dict()


@app.get("/api/environment")
def get_environment() -> dict[str, Any]:
    """环境综合快照: 昼夜 + 天气 + 生态 + 季节。"""
    daynight = get_daynight_system()
    weather = get_weather_system()
    ecology = get_ecology_system()
    from ..world import get_season_system
    season = get_season_system()
    return {
        "daynight": daynight.to_dict(),
        "weather": weather.to_dict(),
        "ecology": ecology.to_dict(),
        "season": season.to_dict(),
    }


# ---- 徽章 API ----
@app.get("/api/digimon/{name}/badges")
def get_digimon_badges(name: str) -> dict[str, Any]:
    """某只数码兽已获得的徽章列表(实时计算)。"""
    world = get_world()
    agent = world.get(name)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Digimon '{name}' not found")
    badge_system = BadgeSystem(world=world, tracker=get_tracker())
    badges = badge_system.evaluate(agent)
    return {
        "name": name,
        "count": len(badges),
        "badges": badges,
    }


# ---- 里程碑/成就 API ----
@app.get("/api/digimon/{name}/achievements")
def get_digimon_achievements(name: str) -> dict[str, Any]:
    """某只数码兽已达成的里程碑列表(实时计算)。"""
    world = get_world()
    agent = world.get(name)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Digimon '{name}' not found")
    achievement_system = AchievementSystem()
    achievements = achievement_system.evaluate(agent)
    return {
        "name": name,
        "count": len(achievements),
        "achievements": achievements,
    }


# ---- 世界事件时间线 API ----
@app.get("/api/timeline")
def get_timeline(limit: int = 50) -> dict[str, Any]:
    """世界大事记时间线: 从事件流里过滤出重大事件(进化/战斗/天灾/节日/剧情
    /跨世界之门/初遇/叙事告警),格式化后最新在前返回。

    limit 会夹到 [1, 200]。返回 {count, total_events, events:[...]}。
    """
    return get_timeline_system().to_dict(get_world(), limit=limit)


# ---- 地标 API ----
@app.get("/api/landmarks")
def get_landmarks() -> dict[str, Any]:
    """各地标状态(坐标 + 效果 + 当前附近的数码兽)。"""
    return get_landmark_system().status(get_world())


# ---- 日记 API ----
@app.get("/api/digimon/{name}/diary")
def get_digimon_diary(name: str) -> dict[str, Any]:
    """某只数码兽最近 7 天日记(memory_type='diary',最新在前)。"""
    world = get_world()
    agent = world.get(name)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Digimon '{name}' not found")
    entries = agent.get_diary(limit=7)
    return {
        "name": name,
        "count": len(entries),
        "entries": entries,
    }


# ---- 黑色齿轮 API (Phase 8) ----


@app.get("/api/dark-gears")
def get_dark_gears() -> dict[str, Any]:
    """黑色齿轮系统状态: 活动齿轮列表 / 感染区域 / 威胁等级。

    Phase 8: 数码宝贝原作复刻 — 恶魔兽投放的黑色齿轮。
    前端可据此在地图上渲染齿轮图标和感染区域高亮。
    """
    dgs = get_dark_gear_system()
    return dgs.to_dict()


@app.post("/api/dark-gears/attack")
def attack_dark_gear(
    agent_name: str, sub_region_id: str
) -> dict[str, Any]:
    """数码兽在所在子区域内攻击黑色齿轮。

    每次攻击造成 GEAR_DAMAGE_PER_BATTLE(20) 基础伤害,
    数码兽进化阶段越高(如 MEGA)伤害倍率越高。

    Args:
        agent_name: 攻击的数码兽名字
        sub_region_id: 数码兽当前所在的子区域 ID

    Returns:
        {destroyed, message, gear_status}
    """
    world = get_world()
    agent = world.get(agent_name)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Digimon '{agent_name}' not found")

    # 根据进化阶段计算伤害倍率
    stage_multiplier = {
        "FRESH": 0.5,
        "IN_TRAINING": 0.75,
        "ROOKIE": 1.0,
        "CHAMPION": 1.5,
        "ULTIMATE": 2.0,
        "MEGA": 3.0,
    }.get(agent.stage.value, 1.0)

    dgs = get_dark_gear_system()
    destroyed, msg = dgs.try_destroy_gear(sub_region_id, damage_multiplier=stage_multiplier)

    # 攻击齿轮也被视为战斗行动(引擎无关,直接计数)
    if destroyed:
        msg += f" {agent_name} 以{agent.stage.value}之力摧毁了齿轮!经验获得大增幅 🌟"

    return {
        "agent": agent_name,
        "stage": agent.stage.value,
        "sub_region_id": sub_region_id,
        "destroyed": destroyed,
        "message": msg,
        "gear_status": dgs.to_dict(),
    }


# ---- Phase 9: 多元宇宙 API ----


class CreateWorldRequest(BaseModel):
    """创建平行世界请求。"""

    world_id: str | None = None
    seasons: bool = True  # 是否启用季节系统
    seed_digimon: bool = False  # 是否注入默认数码兽(默认空世界)


class OpenGateRequest(BaseModel):
    """数码之门跨世界迁移请求。"""

    agent_name: str = Field(..., description="要迁移的数码兽名字")
    from_world: str = Field(..., description="源世界 id")
    to_world: str = Field(..., description="目标世界 id")


class MigrateBatchRequest(BaseModel):
    """批量数码之门迁移请求(Phase 12)。"""

    agent_names: list[str] = Field(..., min_length=1, max_length=100, description="要迁移的数码兽名字列表")
    from_world: str = Field(..., description="源世界 id")
    to_world: str = Field(..., description="目标世界 id")


class AutoMigrateRequest(BaseModel):
    """自动跨世界迁移请求(Phase 12)。"""

    max_per_pair: int = Field(default=3, ge=1, le=20, description="每对世界最大迁移数码兽数")


@app.get("/api/multiverse")
def get_multiverse_overview() -> dict[str, Any]:
    """多元宇宙概览: 所有世界列表、agent 数、事件数。"""
    mv = get_multiverse()
    return mv.to_dict()


@app.get("/api/multiverse/stats")
def get_multiverse_stats() -> dict[str, Any]:
    """多元宇宙聚合统计: 世界数、总 agent 数、总事件数、各世界摘要。

    相比 /api/multiverse 的轻量概览,此端点额外包含:
    - total_agents: 所有世界的 agent 总和
    - total_events: 所有世界的事件总和
    - region_count: 各世界的地区数
    """
    mv = get_multiverse()
    return mv.stats()


@app.post("/api/multiverse/create")
def create_world(req: CreateWorldRequest) -> dict[str, Any]:
    """创建一个新的平行世界,返回新世界 ID 和状态。"""
    mv = get_multiverse()
    world = mv.create_world(
        world_id=req.world_id,
        seasons_enabled=req.seasons,
        seed_agents=req.seed_digimon,
    )
    return {
        "world_id": world.world_id,
        "agent_count": world.count(),
        "event_count": len(world.events),
        "seasons_enabled": world.seasons_enabled,
        "total_worlds": mv.count(),
    }


@app.get("/api/multiverse/{world_id}")
def get_world_detail(world_id: str) -> dict[str, Any]:
    """获取指定世界的详细信息(agents, events, regions, seasons_enabled)。"""
    mv = get_multiverse()
    world = mv.get_world(world_id)
    if world is None:
        raise HTTPException(status_code=404, detail=f"World '{world_id}' not found")
    return {
        "world_id": world_id,
        "seasons_enabled": world.seasons_enabled,
        "agent_count": world.count(),
        "event_count": len(world.events),
        "region_count": len(world.regions),
        "agent_names": [a.name for a in world.all()],
        "recent_events": world.events[-20:] if world.events else [],
    }


@app.post("/api/multiverse/gate")
def open_digital_gate(req: OpenGateRequest) -> dict[str, Any]:
    """打开数码之门,将一只数码兽从一个世界迁移到另一个。"""
    mv = get_multiverse()
    agent = mv.open_gate(
        agent_name=req.agent_name,
        from_world_id=req.from_world,
        to_world_id=req.to_world,
    )
    if agent is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Gate failed: check that worlds '{req.from_world}' and "
                f"'{req.to_world}' exist and agent '{req.agent_name}' is "
                f"in '{req.from_world}'"
            ),
        )
    return {
        "agent": agent.name,
        "from_world": req.from_world,
        "to_world": req.to_world,
        "message": f"{agent.name} 穿过了数码之门,从 {req.from_world} 到达 {req.to_world}! 🌌",
    }


@app.post("/api/multiverse/migrate")
def migrate_digimon_batch(req: MigrateBatchRequest) -> dict[str, Any]:
    """批量数码之门: 一次迁移多只数码兽跨世界(Phase 12)。

    部分 agent 不存在不会导致整批失败,
    返回 migrated / failed 两个列表。
    """
    mv = get_multiverse()
    result = mv.migrate_batch(
        agent_names=req.agent_names,
        from_world_id=req.from_world,
        to_world_id=req.to_world,
    )
    return {
        "from_world": req.from_world,
        "to_world": req.to_world,
        **result,
        "message": (
            f"批量迁移完成: {len(result['migrated'])}/{req.agent_names} "
            f"成功从 {req.from_world} 到达 {req.to_world} 🌌"
            if result["migrated"]
            else f"批量迁移失败: 所有 {len(req.agent_names)} 只数码兽无法迁移"
        ),
    }


@app.post("/api/multiverse/auto-migrate")
def trigger_auto_migrate(req: AutoMigrateRequest | None = None) -> dict[str, Any]:
    """触发自动跨世界迁移(Phase 12)。

    在非 prime 世界之间随机迁移数码兽,模拟自然跨世界流动。
    可选参数 max_per_pair 控制每对世界最多迁移几只。
    """
    mv = get_multiverse()
    max_pp = req.max_per_pair if req is not None else 3
    results = mv.auto_migrate(max_per_pair=max_pp)
    total_moved = sum(r["count"] for r in results)
    return {
        "pairs": len(results),
        "total_migrated": total_moved,
        "details": results,
        "message": (
            f"自动迁移完成: {total_moved} 只数码兽在 {len(results)} 对世界间流动 🌌"
            if results
            else "无可用非 prime 世界对(需要至少 2 个非 prime 世界)"
        ),
    }


@app.delete("/api/multiverse/{world_id}")
def delete_world(world_id: str) -> dict[str, Any]:
    """删除一个平行世界(主宇宙不可删除)。

    被删除世界的数码兽和事件一同销毁。
    如果有数码兽之前通过数码之门迁移到了其他世界,它们不受影响。
    """
    mv = get_multiverse()
    if world_id == "prime":
        raise HTTPException(
            status_code=400,
            detail="Cannot delete the prime world (主宇宙)",
        )
    removed = mv.remove_world(world_id)
    if not removed:
        raise HTTPException(
            status_code=404,
            detail=f"World '{world_id}' not found",
        )
    return {
        "world_id": world_id,
        "deleted": True,
        "total_worlds": mv.count(),
    }


@app.get("/api/multiverse/{world_id}/events")
def get_world_events(
    world_id: str,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """获取指定世界的事件列表(最新在前,支持分页)。

    Args:
        world_id: 世界 ID
        limit: 返回条数(1~200,默认 50)
        offset: 偏移量(跳过前 N 条)
    """
    mv = get_multiverse()
    world = mv.get_world(world_id)
    if world is None:
        raise HTTPException(
            status_code=404,
            detail=f"World '{world_id}' not found",
        )
    limit = max(1, min(limit, 200))
    total = len(world.events)
    # 事件按时间倒序(最新在前)
    events = list(reversed(world.events))
    start = min(offset, total)
    end = min(start + limit, total)
    return {
        "world_id": world_id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "events": events[start:end],
    }


@app.post("/api/multiverse/{world_id}/seed")
def seed_world(world_id: str) -> dict[str, Any]:
    """向已有世界注入默认数码兽(不影响现有数码兽)。

    注入默认的 10 只数码兽: 亚古兽/加布兽/比丘兽/甲虫兽/巴鲁兽/
    哥玛兽/巴达兽/迪路兽/小狗兽/艾力兽。

    如果世界不存在返回 404。
    可对同一世界多次调用(每次追加 10 只)。
    """
    mv = get_multiverse()
    added = mv.seed_world(world_id)
    if added == -1:
        raise HTTPException(
            status_code=404,
            detail=f"World '{world_id}' not found",
        )
    world = mv.get_world(world_id)
    return {
        "world_id": world_id,
        "added": added,
        "total_agents": world.count() if world else 0,
    }


@app.get("/api/multiverse/{world_id}/digimon")
def list_world_digimon(world_id: str) -> dict[str, Any]:
    """列出指定世界所有数码兽的精简列表(前端友好)。

    与 GET /api/digimon 格式相同,但作用域限定到指定世界。
    """
    mv = get_multiverse()
    world = mv.get_world(world_id)
    if world is None:
        raise HTTPException(
            status_code=404,
            detail=f"World '{world_id}' not found",
        )
    return {
        "world_id": world_id,
        "count": world.count(),
        "digimon": [
            {
                "name": a.name,
                "species": a.species,
                "stage": a.stage.value,
                "attribute": a.attribute.value,
                "region_id": a.region_id,
                "position": {"x": a.location[0], "y": a.location[1]},
                "current_plan": a.current_plan,
                "mood": a.mood,
            }
            for a in world.all()
        ],
    }


# ---- Phase 12: 被选召的孩子 API ----


# 内存存储(后续持久化到 SQLite)
_chosen_children: dict[str, "ChosenChildAgent"] = {}


class CreateChosenChildRequest(BaseModel):
    """创建被选召的孩子。"""

    name: str = Field(..., min_length=1, max_length=20, description="孩子名字")
    crest: str = Field(default="courage", description="徽章类型")
    partner_name: str | None = Field(default=None, description="搭档数码兽名字")


class MoveChosenChildRequest(BaseModel):
    """移动被选召的孩子。"""

    dx: int = Field(..., ge=-200, le=200, description="X 方向位移(像素)")
    dy: int = Field(..., ge=-200, le=200, description="Y 方向位移(像素)")


class SetPartnerRequest(BaseModel):
    """绑定搭档数码兽。"""

    partner_name: str = Field(..., description="搭档数码兽名字")


from ..agents.chosen_child import ChosenChildAgent, Crest  # noqa: E402


@app.post("/api/chosen-children", status_code=201)
def create_chosen_child(req: CreateChosenChildRequest) -> dict[str, Any]:
    """创建一个被选召的孩子。"""
    if req.name in _chosen_children:
        raise HTTPException(status_code=409, detail=f"Chosen child '{req.name}' already exists")

    try:
        crest = Crest(req.crest)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid crest '{req.crest}'. Valid: {[c.value for c in Crest]}")

    child = ChosenChildAgent(
        name=req.name,
        partner_name=req.partner_name,
        crest=crest,
    )
    _chosen_children[req.name] = child
    return child.to_dict()


@app.get("/api/chosen-children")
def list_chosen_children() -> dict[str, Any]:
    """列出所有被选召的孩子。"""
    return {
        "count": len(_chosen_children),
        "children": [c.to_dict() for c in _chosen_children.values()],
    }


@app.get("/api/chosen-children/{name}")
def get_chosen_child(name: str) -> dict[str, Any]:
    """获取指定被选召孩子的详情。"""
    child = _chosen_children.get(name)
    if child is None:
        raise HTTPException(status_code=404, detail=f"Chosen child '{name}' not found")
    child.touch()
    return child.to_dict()


@app.post("/api/chosen-children/{name}/move")
def move_chosen_child(name: str, req: MoveChosenChildRequest) -> dict[str, Any]:
    """移动被选召的孩子。"""
    child = _chosen_children.get(name)
    if child is None:
        raise HTTPException(status_code=404, detail=f"Chosen child '{name}' not found")
    new_pos = child.move(req.dx, req.dy)
    return {
        "name": name,
        "position": {"x": new_pos[0], "y": new_pos[1]},
    }


@app.post("/api/chosen-children/{name}/partner")
def set_chosen_child_partner(name: str, req: SetPartnerRequest) -> dict[str, Any]:
    """绑定/更换被选召孩子的搭档数码兽。"""
    child = _chosen_children.get(name)
    if child is None:
        raise HTTPException(status_code=404, detail=f"Chosen child '{name}' not found")

    # 验证搭档数码兽存在
    world = get_world()
    partner = world.get(req.partner_name)
    if partner is None:
        raise HTTPException(
            status_code=404,
            detail=f"Partner digimon '{req.partner_name}' not found in world",
        )

    child.set_partner(req.partner_name)
    return child.to_dict()


@app.delete("/api/chosen-children/{name}")
def delete_chosen_child(name: str) -> dict[str, Any]:
    """删除一个被选召的孩子。"""
    if name not in _chosen_children:
        raise HTTPException(status_code=404, detail=f"Chosen child '{name}' not found")
    del _chosen_children[name]
    return {"name": name, "deleted": True}


# ---- Phase 13③: 性能监控端点 ----
@app.get("/api/health/perf")
def health_perf() -> dict[str, Any]:
    """返回运行时性能指标: 进程内存、DB 大小、活跃连接数等。"""
    import sys

    # 进程内存 (Linux only)
    mem_bytes = 0
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF)
        mem_bytes = usage.ru_maxrss * 1024  # Linux: ru_maxrss is in KB
    except (ImportError, AttributeError):
        try:
            # Fallback: /proc/self/status
            with open("/proc/self/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        mem_bytes = int(line.split()[1]) * 1024
                        break
        except Exception:
            mem_bytes = 0

    # DB 文件大小
    from ..world.persistence import DEFAULT_DB_PATH
    db_path = DEFAULT_DB_PATH
    db_size_bytes = os.path.getsize(db_path) if os.path.exists(db_path) else 0

    # 世界状态统计
    world = get_world()
    agent_count = world.count()
    memory_count = sum(len(a.memory.entries) for a in world.all())
    event_count = len(world.events)

    # Python 进程信息
    return {
        "pid": os.getpid(),
        "python_version": sys.version,
        "uptime_seconds": time.time() - _START_TIME,
        "memory": {
            "rss_mb": round(mem_bytes / (1024 * 1024), 2),
            "rss_bytes": mem_bytes,
        },
        "database": {
            "path": db_path,
            "size_mb": round(db_size_bytes / (1024 * 1024), 2),
            "size_bytes": db_size_bytes,
        },
        "world": {
            "agent_count": agent_count,
            "total_memories": memory_count,
            "event_count": event_count,
            "ws_connections": len(manager.active),
            "clock_tick": (
                getattr(app.state, "scheduler", None)
                and getattr(app.state.scheduler, "tick_count", 0) or 0
            ),
        },
    }


# 启动时间戳 (用于 uptime 计算)
_START_TIME: float = time.time()


# ---- WebSocket(Phase 1: 占位,周期性广播位置) ----
class ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in self.active:
            try:
                await ws.send_text(json.dumps(message, ensure_ascii=False))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


# ---- Phase 13: TTS 配音 API ----
@app.get("/api/tts/voices")
async def list_tts_voices() -> dict[str, Any]:
    """列出所有支持 TTS 配音的数码兽及其声音配置。"""
    voices = {}
    for name, profile in tts_module.DIGIMON_VOICE_PROFILES.items():
        voices[name] = {
            "voice": profile["voice"],
            "pitch": profile["pitch"],
            "rate": profile["rate"],
            "description": profile["description"],
            "greetings": tts_module.DIGIMON_GREETINGS.get(name, []),
        }
    return {"count": len(voices), "voices": voices}


@app.get("/api/tts/{name}")
async def get_digimon_tts(name: str, text: str | None = None) -> Response:
    """获取指定数码兽的 TTS 语音 (wav 格式)。

    如果未指定 text, 则使用该数码兽的随机问候语。
    例如: GET /api/tts/agumon?text=你好我是亚古兽
    """
    if not text:
        text = tts_module.get_random_greeting(name)
    if not text:
        raise HTTPException(status_code=400, detail="无法生成问候语, 请提供 text 参数")

    try:
        audio = await tts_module.speak_digimon(name, text)
        if not audio:
            raise HTTPException(status_code=500, detail="TTS 生成失败 (空音频)")
        return Response(content=audio, media_type="audio/wav")
    except Exception as e:
        logger.error(f"TTS 端点异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"TTS 生成失败: {e}")


@app.post("/api/tts/speak")
async def speak_digimon_api(req: SpeakRequest) -> Response:
    """POST 方式让数码兽说话, 返回 wav 音频。"""

    try:
        audio = await tts_module.speak_digimon(req.name, req.text)
        if not audio:
            raise HTTPException(status_code=500, detail="TTS 生成失败 (空音频)")
        return Response(content=audio, media_type="audio/wav")
    except Exception as e:
        logger.error(f"TTS speak 端点异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"TTS 生成失败: {e}")


async def _position_broadcaster() -> None:
    """后台任务: 每秒广播一次世界位置(Phase 1 占位)。"""
    while True:
        await asyncio.sleep(1.0)
        if not manager.active:
            continue
        world = get_world()
        payload = {
            "type": "positions",
            "digimon": [
                {
                    "name": a.name,
                    "position": {"x": a.location[0], "y": a.location[1]},
                    "region_id": a.region_id,
                }
                for a in world.all()
            ],
            "chosen_children": [
                {
                    "name": c.name,
                    "position": {"x": c.location[0], "y": c.location[1]},
                    "region_id": c.region_id,
                    "partner_name": c.partner_name,
                }
                for c in _chosen_children.values()
            ],
        }
        await manager.broadcast(payload)


@app.websocket("/ws/world")
async def ws_world(ws: WebSocket) -> None:
    await manager.connect(ws)
    try:
        # 推一份初始快照
        world = get_world()
        await ws.send_text(json.dumps(
            {"type": "snapshot", "world": world.to_dict()},
            ensure_ascii=False,
        ))
        # 保持连接(接收客户端心跳 / 命令)
        while True:
            msg = await ws.receive_text()
            # Phase 1: 简单 echo,Phase 2 解析 client 指令
            await ws.send_text(json.dumps({"type": "echo", "received": msg}))
    except WebSocketDisconnect:
        manager.disconnect(ws)
