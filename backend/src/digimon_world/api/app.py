"""
FastAPI App - 数码世界后端 HTTP 接口
====================================

Phase 1 接口:
- GET  /                      — 健康检查 + 元信息
- GET  /api/digimon           — 数码兽列表
- GET  /api/digimon/{name}    — 单只数码兽详情
- GET  /api/digimon/{name}/position — 单只数码兽位置
- POST /api/digimon/{name}/move — 移动数码兽 (body: {dx, dy})
- GET  /api/world             — 整个世界快照(给前端用)
- WS   /ws/world              — 世界状态实时推送 (Phase 1 占位)

详细设计: docs/DESIGN.md 第 7 节
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .. import __version__
from .pokedex import router as pokedex_router
from ..agents.achievements import AchievementSystem
from ..agents.badges import Badge, BadgeSystem
from ..agents.dialogue import Dialogue
from ..agents.evolution import EvolutionSystem
from ..agents.healing import get_healing_system
from ..battle import BattleEngine, BattleResult, spar
from ..llm.client import get_client
from ..world import (
    WorldClock,
    WorldScheduler,
    WorldState,
    get_director,
    get_festival_system,
    get_landmark_system,
    get_multiverse,
    get_registry,
    get_timeline_system,
    get_tracker,
    get_weather_system,
    get_world,
    persistence,
)


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
    description="数码宝贝虚拟世界后端 (Phase 1)",
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
        "phase": 1,
        "status": "ok",
        "digimon_count": world.count(),
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

    # id 用当前列表长度 - 1 (即刚 append 的索引)
    return {
        "id": len(world.events) - 1,
        "type": req.type,
        "description": req.description,
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
    """导演视角状态: 当前流速 / 世界时间 / 最近 10 条事件 / 派系列表。"""
    world = get_world()
    clock: Optional[WorldClock] = getattr(app.state, "world_clock", None)
    return {
        "ratio": world.real_to_world_ratio,
        "current_world_time": clock.format_clock() if clock is not None else None,
        "recent_events": world.events[-10:],
        "factions": [f.to_dict() for f in get_registry().all_factions()],
    }


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
def get_leaderboard(top: int = 10) -> dict[str, Any]:
    """数码兽排行榜: 战斗胜利 / 羁绊值 / 徽章数三个维度。

    每个维度返回降序 Top-N: {name, <metric>}。给导演面板排行榜 tab 用。
    """
    world = get_world()
    evo = EvolutionSystem()
    badge_system = BadgeSystem(world=world, tracker=get_tracker())
    n = max(1, min(top, 50))

    agents = world.all()
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


# ---- 天气 API ----
@app.get("/api/weather")
def get_weather() -> dict[str, Any]:
    """当前天气状态(天气类型 + 行为系数)。"""
    return get_weather_system().to_dict()


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
