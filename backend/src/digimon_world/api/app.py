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
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .. import __version__
from ..agents.dialogue import Dialogue
from ..llm.client import get_client
from ..world import WorldClock, WorldScheduler, WorldState, get_world


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


# ---- App ----
app = FastAPI(
    title="DIGIMON WORLD API",
    description="数码宝贝虚拟世界后端 (Phase 1)",
    version=__version__,
)

# 开发期 CORS 全开(前端可能在 8080 端口)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.get("/api/world")
def get_world_snapshot() -> dict[str, Any]:
    """整个世界快照(前端 canvas 渲染用)。"""
    return get_world().to_dict()


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


@app.on_event("startup")
async def _startup() -> None:
    # 触发单例创建 + 启动广播任务
    world = get_world()
    app.state.broadcaster = asyncio.create_task(_position_broadcaster())

    # 启动世界调度器: 用 WorldClock 周期性驱动所有 agent 自主生活。
    # 相遇时通过 Dialogue(Haiku 4.5)生成对话。
    clock = WorldClock(real_to_world_ratio=world.real_to_world_ratio)
    dialogue = Dialogue(llm_client=get_client())
    scheduler = WorldScheduler(world=world, clock=clock, dialogue=dialogue)
    app.state.world_clock = clock
    app.state.scheduler = scheduler
    app.state.scheduler_task = asyncio.create_task(scheduler.run_forever())


@app.on_event("shutdown")
async def _shutdown() -> None:
    for attr in ("broadcaster", "scheduler_task"):
        task: Optional[asyncio.Task] = getattr(app.state, attr, None)
        if task is not None:
            task.cancel()


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
