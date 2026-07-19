"""LLM 中转客户端(Phase 2)。

为数码兽 agent 提供"调用 LLM"的统一接口,支持分层:
- opus 4.8: 反思 / 计划生成 / 战斗决策(高质量)
- haiku 4.5: 快速观察 / 短文本生成(低成本)

设计原则:
1. 接口与实现分离:LlmClient 是 Protocol,任何满足协议的实例都可用
2. 默认 client 用 httpx 调中转 API(配置从环境变量读)
3. 测试时用 FakeLlmClient 注入确定性回复(避免依赖网络/额度)

详细设计: docs/DESIGN.md 第 6 节
"""
from .client import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    FakeLlmClient,
    HttpLlmClient,
    LlmClient,
    LlmError,
    LlmModel,
    complete,
    get_client,
    set_client,
)

__all__ = [
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "FakeLlmClient",
    "HttpLlmClient",
    "LlmClient",
    "LlmError",
    "LlmModel",
    "complete",
    "get_client",
    "set_client",
]
