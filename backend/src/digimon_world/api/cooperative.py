"""
协作任务 API — Phase 31
========================

提供协作任务的管理接口:
- GET  /api/cooperative-tasks            — 所有活跃任务
- GET  /api/cooperative-tasks/{task_id}  — 单个任务详情
- POST /api/cooperative-tasks/generate   — 触发任务生成
- POST /api/cooperative-tasks/{task_id}/contribute — 提交贡献

与 world/cooperative_tasks.py 中的 CooperativeTaskRegistry 单例集成。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..world.cooperative_tasks import (
    TaskGenerationEngine,
    get_cooperative_registry,
)
from ..world.world_state import get_world

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cooperative-tasks", tags=["cooperative"])


# ── 请求模型 ──


class ContributeRequest(BaseModel):
    """贡献请求体。"""

    agent_name: str = Field(..., min_length=1, description="贡献者名字")
    amount: float = Field(..., gt=0, description="贡献值 (>0)")


class GenerateRequest(BaseModel):
    """任务生成请求体。"""

    tick_count: int = Field(default=0, ge=0, description="当前世界 tick")
    max_tasks: int = Field(default=1, ge=1, le=5, description="最多生成任务数")


# ── 端点 ──


@router.get("")
async def list_cooperative_tasks() -> dict[str, Any]:
    """获取所有活跃的协作任务。

    Returns:
        { "count": int, "tasks": [CooperativeTask.to_dict(), ...] }
    """
    registry = get_cooperative_registry()
    active = registry.get_active_tasks()
    return {
        "count": len(active),
        "tasks": [t.to_dict() for t in active],
    }


@router.get("/all")
async def list_all_tasks() -> dict[str, Any]:
    """获取所有任务（包括已完成的）。

    Returns:
        { "count": int, "tasks": [CooperativeTask.to_dict(), ...] }
    """
    registry = get_cooperative_registry()
    all_tasks = registry.get_all_tasks()
    return {
        "count": len(all_tasks),
        "tasks": [t.to_dict() for t in all_tasks],
    }


@router.get("/{task_id}")
async def get_task(task_id: str) -> dict[str, Any]:
    """获取单个任务详情。

    Args:
        task_id: 任务 ID。

    Returns:
        任务的完整序列化字典。
    """
    registry = get_cooperative_registry()
    task = registry.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务 '{task_id}' 不存在")
    return task.to_dict()


@router.post("/generate")
async def generate_tasks(req: GenerateRequest = GenerateRequest()) -> dict[str, Any]:
    """触发协作任务生成。

    使用 TaskGenerationEngine 扫描世界状态，
    生成最多 max_tasks 个新任务并注册到全局注册表。

    Args:
        req: 生成参数（tick_count, max_tasks）。

    Returns:
        { "generated": int, "tasks": [...] }
    """
    world = get_world()
    agents = world.all()

    if len(agents) < 2:
        return {"generated": 0, "tasks": [], "message": "数码兽数量不足，无法生成协作任务"}

    engine = TaskGenerationEngine()
    registry = get_cooperative_registry()

    generated = 0
    generated_tasks = []

    for _ in range(req.max_tasks):
        task = engine.generate_random_task(world, agents, req.tick_count)
        if task is None:
            continue

        # 注册到全局注册表
        existing = registry.get_task(task.task_id)
        if existing is None:
            registry.add_task(task)
            generated += 1
            generated_tasks.append(task.to_dict())

    logger.info("生成了 %d 个协作任务", generated)
    return {"generated": generated, "tasks": generated_tasks}


@router.post("/{task_id}/contribute")
async def contribute_to_task(task_id: str, req: ContributeRequest) -> dict[str, Any]:
    """向任务提交贡献。

    Args:
        task_id: 任务 ID。
        req: 贡献者名字和贡献值。

    Returns:
        贡献结果和任务进度。
    """
    registry = get_cooperative_registry()

    # 先检查任务是否存在
    task = registry.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务 '{task_id}' 不存在")

    # 确保参与者已加入
    if req.agent_name not in task.current_participants:
        registry.join_task(task_id, req.agent_name)

    success = registry.contribute(task_id, req.agent_name, req.amount)
    if not success:
        raise HTTPException(status_code=400, detail="贡献失败，请检查任务状态")

    # 检查完成
    result = registry.check_completion(task_id)

    return {
        "task_id": task_id,
        "agent_name": req.agent_name,
        "contributed": req.amount,
        "contribution_total": task.individual_contributions.get(req.agent_name, 0.0),
        "status": task.status,
        "progress": result,
    }
