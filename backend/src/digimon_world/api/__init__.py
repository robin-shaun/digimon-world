"""API 层: FastAPI 接口,给前端和外部调用。

Phase 0: 骨架,只暴露健康检查
Phase 1: 提供 digimon 状态查询 + 移动 + WebSocket 推送
Phase 2: 接入 LLM agent 循环

详细设计: docs/DESIGN.md 第 7 节
"""

from .app import app

__all__ = ["app"]
