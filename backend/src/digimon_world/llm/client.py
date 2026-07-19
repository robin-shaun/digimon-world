"""LLM 中转客户端实现。

提供:
- LlmClient: Protocol,所有 client 必须实现 complete()
- HttpLlmClient: httpx 实现,连中转 API
- FakeLlmClient: 测试用,返回预设回复
- get_client() / set_client(): 进程级单例,方便在测试里替换

Phase 2 第一版: 接口骨架。真实中转 URL 留环境变量配置,默认不调。
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class LlmModel(str, Enum):
    """模型分层。"""

    # Anthropic (中转)
    OPUS = "opus-4.8"      # 反思 / 计划 / 战斗决策
    HAIKU = "haiku-4.5"    # 观察 / 短文本

    # MiniMax
    MINIMAX_M1 = "minimax-m1"   # 主力模型 (计划/反思/战斗)
    MINIMAX_M3 = "minimax-m3"   # 轻量模型 (观察/短文本)
    MINIMAX_TEXT_01 = "MiniMax-Text-01"  # 对话生成 (支持角色扮演)


class LlmError(RuntimeError):
    """调用 LLM 失败(网络 / 4xx / 5xx / 429 / 解析失败)。"""


@dataclass
class ChatMessage:
    """一条对话消息。"""

    role: str  # "system" | "user" | "assistant"
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class ChatRequest:
    """一次完整调用请求。"""

    messages: list[ChatMessage]
    model: LlmModel = LlmModel.MINIMAX_M3
    max_tokens: int = 512
    temperature: float = 0.7
    # 可选: 透传给中转的元数据(trace id 等)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatResponse:
    """一次调用的结果。"""

    content: str
    model: LlmModel
    # 原始字节 / 状态,排错用
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class LlmClient(Protocol):
    """任何 LLM 客户端都满足这个协议。"""

    async def complete(self, req: ChatRequest) -> ChatResponse: ...


# ---- Fake client (测试用) ----

class FakeLlmClient:
    """测试用 LLM 客户端,按 (model, prompt 关键字) 返回预设回复。

    用法:
        fake = FakeLlmClient()
        fake.set_reply(LlmModel.HAIKU, contains="亚古兽", reply="在沙滩上")
        set_client(fake)
        ...
    """

    def __init__(self, default_reply: str = "OK") -> None:
        self._default = default_reply
        # list of (model, predicate, reply)
        self._rules: list[tuple[LlmModel, Any, str]] = []
        self.calls: list[ChatRequest] = []  # 记录每次调用,断言用

    def set_reply(
        self,
        model: LlmModel,
        contains: str | None = None,
        reply: str = "OK",
    ) -> None:
        """预设一条规则: 指定模型,prompt 包含 contains 时返回 reply。"""
        pred = (lambda prompt: contains in prompt) if contains else (lambda _: True)
        self._rules.append((model, pred, reply))

    async def complete(self, req: ChatRequest) -> ChatResponse:
        self.calls.append(req)
        prompt = "\n".join(m.content for m in req.messages)
        for model, pred, reply in self._rules:
            if model == req.model and pred(prompt):
                return ChatResponse(content=reply, model=req.model, raw={"fake": True})
        return ChatResponse(content=self._default, model=req.model, raw={"fake": True})


# ---- HTTP client (真实中转) ----

class HttpLlmClient:
    """httpx 直连中转 API。

    中转 URL 走环境变量:
      DIGIMON_LLM_BASE_URL  (默认: 中转提供的 base)
      DIGIMON_LLM_API_KEY   (默认: None,必填)

    中转请求 / 响应格式假设 OpenAI Chat Completions 兼容(中转最常见形式)。
    如果中转格式不同,只需替换 _build_payload / _parse_response。
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self.base_url = (base_url or os.environ.get("DIGIMON_LLM_BASE_URL", "")).rstrip("/")
        self.api_key = api_key or os.environ.get("DIGIMON_LLM_API_KEY", "")
        self.timeout = timeout
        self.max_retries = max_retries
        if not self.base_url or not self.api_key:
            # 不在构造时 raise,允许先 set 再用;complete() 时再判
            pass

    def _build_payload(self, req: ChatRequest) -> dict[str, Any]:
        return {
            "model": req.model.value,
            "messages": [m.to_dict() for m in req.messages],
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
        }

    def _parse_response(self, data: dict[str, Any], req: ChatRequest) -> ChatResponse:
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LlmError(f"无法解析 LLM 响应: {data}") from e
        return ChatResponse(content=content, model=req.model, raw=data)

    async def complete(self, req: ChatRequest) -> ChatResponse:
        if not self.base_url or not self.api_key:
            raise LlmError("HttpLlmClient 缺少 base_url 或 api_key(设环境变量)")

        import httpx  # 延迟导入,允许测试时不必装 httpx(虽然 pyproject 已列)

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = self._build_payload(req)

        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as cli:
                    r = await cli.post(url, json=payload, headers=headers)
                # 2xx
                if 200 <= r.status_code < 300:
                    return self._parse_response(r.json(), req)
                # 4xx 客户端错误(除 429 限流)→ 不重试,直接抛
                if 400 <= r.status_code < 500 and r.status_code != 429:
                    raise LlmError(f"中转返回 {r.status_code}(客户端错误,不重试): {r.text[:200]}")
                # 429 / 5xx → 重试
                raise LlmError(f"中转返回 {r.status_code}: {r.text[:200]}")
            except (httpx.HTTPError, LlmError) as e:
                last_err = e
                # 客户端错误(非 429)→ 已是终态,直接退出循环外 raise
                if isinstance(e, LlmError) and "客户端错误" in str(e):
                    break
                if attempt < self.max_retries:
                    # 指数退避: 0.5s, 1s, 2s
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    continue
                break
        raise LlmError(f"调用 LLM 失败(已重试 {self.max_retries} 次)") from last_err


# ---- MiniMax client ----


class MiniMaxClient:
    """MiniMax API 直连客户端。

    API 文档: https://platform.minimax.chat
    端点: POST https://api.minimax.chat/v1/text/chatcompletion_v2
    """

    BASE_URL = "https://api.minimax.chat/v1/text/chatcompletion_v2"

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 45.0,
        max_retries: int = 3,
    ) -> None:
        self.api_key = api_key or os.environ.get("MINIMAX_API_KEY", "")
        self.timeout = timeout
        self.max_retries = max_retries

    def _build_payload(self, req: ChatRequest) -> dict[str, Any]:
        return {
            "model": req.model.value,
            "messages": [m.to_dict() for m in req.messages],
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
        }

    def _parse_response(self, data: dict[str, Any], req: ChatRequest) -> ChatResponse:
        status = data.get("base_resp", {}).get("status_code", -1)
        if status != 0:
            msg = data.get("base_resp", {}).get("status_msg", "unknown")
            raise LlmError(f"MiniMax 返回错误 {status}: {msg}")
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LlmError(f"无法解析 MiniMax 响应: {data}") from e
        return ChatResponse(content=content, model=req.model, raw=data)

    async def complete(self, req: ChatRequest) -> ChatResponse:
        if not self.api_key:
            raise LlmError("MiniMaxClient 缺少 api_key")

        import httpx

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = self._build_payload(req)

        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as cli:
                    r = await cli.post(self.BASE_URL, json=payload, headers=headers)
                if 200 <= r.status_code < 300:
                    return self._parse_response(r.json(), req)
                if r.status_code == 429:
                    raise LlmError(f"MiniMax 限流 429: {r.text[:200]}")
                if 400 <= r.status_code < 500:
                    raise LlmError(f"MiniMax 客户端错误 {r.status_code}: {r.text[:200]}")
                raise LlmError(f"MiniMax 返回 {r.status_code}: {r.text[:200]}")
            except (httpx.HTTPError, LlmError) as e:
                last_err = e
                if isinstance(e, LlmError) and "客户端错误" in str(e):
                    break
                if attempt < self.max_retries:
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    continue
                break
        raise LlmError(f"MiniMax 调用失败(已重试 {self.max_retries} 次)") from last_err

_client: LlmClient | None = None


def get_client() -> LlmClient:
    """获取 LLM 客户端单例。

    优先顺序:
    1. 显式 set_client() 的实例(测试注入)
    2. MINIMAX_API_KEY 已设 → MiniMaxClient (M3)
    3. DIGIMON_LLM_API_KEY + DIGIMON_LLM_BASE_URL → HttpLlmClient
    4. 兜底: FakeLlmClient
    """
    global _client
    if _client is not None:
        return _client
    if os.environ.get("MINIMAX_API_KEY"):
        _client = MiniMaxClient()
    elif os.environ.get("DIGIMON_LLM_API_KEY") and os.environ.get("DIGIMON_LLM_BASE_URL"):
        _client = HttpLlmClient()
    else:
        _client = FakeLlmClient(default_reply="[offline] LLM 未配置")
    return _client


def set_client(client: LlmClient) -> None:
    """替换单例(测试 / 切换中转用)。"""
    global _client
    _client = client


async def complete(
    messages: list[ChatMessage],
    model: LlmModel = LlmModel.MINIMAX_M3,
    max_tokens: int = 512,
    temperature: float = 0.7,
) -> ChatResponse:
    """便捷函数: 用单例 client 跑一次。"""
    req = ChatRequest(
        messages=messages,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return await get_client().complete(req)
