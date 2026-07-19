"""LLM 客户端测试。

覆盖:
- ChatMessage / ChatRequest / ChatResponse 序列化
- FakeLlmClient: 默认 / 规则匹配 / 调用记录
- HttpLlmClient: 缺配置报错 / 4xx 5xx 429 / 解析失败 / 成功路径(用 respx mock httpx)
- 单例 get_client / set_client 切换
- 便捷 complete() 走单例
"""
from __future__ import annotations

import httpx
import pytest

from digimon_world.llm import (
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

# ---- 数据类 ----

def test_chat_message_to_dict() -> None:
    m = ChatMessage(role="user", content="hi")
    assert m.to_dict() == {"role": "user", "content": "hi"}


def test_chat_request_defaults() -> None:
    req = ChatRequest(messages=[ChatMessage("user", "x")])
    assert req.model == LlmModel.MINIMAX_M3
    assert req.max_tokens == 512
    assert req.temperature == 0.7
    assert req.extra == {}


def test_chat_response_raw_default() -> None:
    r = ChatResponse(content="c", model=LlmModel.OPUS)
    assert r.raw == {}


# ---- FakeLlmClient ----

@pytest.mark.asyncio
async def test_fake_default_reply() -> None:
    fake = FakeLlmClient(default_reply="DEFAULT")
    req = ChatRequest(messages=[ChatMessage("user", "anything")], model=LlmModel.MINIMAX_M3)
    resp = await fake.complete(req)
    assert resp.content == "DEFAULT"
    assert resp.model == LlmModel.MINIMAX_M3
    assert resp.raw == {"fake": True}
    assert fake.calls == [req]


@pytest.mark.asyncio
async def test_fake_rule_match_on_contains() -> None:
    fake = FakeLlmClient()
    fake.set_reply(LlmModel.OPUS, contains="亚古兽", reply="在沙滩上")
    req = ChatRequest(
        messages=[ChatMessage("user", "亚古兽在哪?")],
        model=LlmModel.OPUS,
    )
    resp = await fake.complete(req)
    assert resp.content == "在沙滩上"


@pytest.mark.asyncio
async def test_fake_rule_only_matches_correct_model() -> None:
    fake = FakeLlmClient(default_reply="fallback")
    fake.set_reply(LlmModel.OPUS, contains="x", reply="opus-only")
    # 同样 prompt 用 HAIKU 调,不应命中
    resp = await fake.complete(ChatRequest(
        messages=[ChatMessage("user", "x y z")],
        model=LlmModel.MINIMAX_M3,
    ))
    assert resp.content == "fallback"


@pytest.mark.asyncio
async def test_fake_rule_priority_last_set_wins() -> None:
    fake = FakeLlmClient()
    fake.set_reply(LlmModel.MINIMAX_M3, contains="hi", reply="first")
    fake.set_reply(LlmModel.MINIMAX_M3, contains="hi", reply="second")
    resp = await fake.complete(ChatRequest(
        messages=[ChatMessage("user", "hi")],
        model=LlmModel.MINIMAX_M3,
    ))
    # 正向遍历,先注册先命中
    assert resp.content == "first"


def test_fake_satisfies_protocol() -> None:
    """FakeLlmClient 必须能被当作 LlmClient 用(鸭子类型 / Protocol)。"""
    fake: LlmClient = FakeLlmClient()
    assert isinstance(fake, LlmClient)


# ---- HttpLlmClient 错误路径(不依赖网络) ----

@pytest.mark.asyncio
async def test_http_client_missing_config_raises() -> None:
    cli = HttpLlmClient(base_url="", api_key="")
    req = ChatRequest(messages=[ChatMessage("user", "x")])
    with pytest.raises(LlmError, match="缺少 base_url"):
        await cli.complete(req)


def test_http_client_build_payload_shape() -> None:
    cli = HttpLlmClient(base_url="http://x", api_key="k")
    req = ChatRequest(
        messages=[ChatMessage("system", "sys"), ChatMessage("user", "u")],
        model=LlmModel.OPUS,
        max_tokens=128,
        temperature=0.3,
    )
    payload = cli._build_payload(req)
    assert payload["model"] == "opus-4.8"
    assert payload["max_tokens"] == 128
    assert payload["temperature"] == 0.3
    assert payload["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u"},
    ]


def test_http_client_parse_response_happy() -> None:
    cli = HttpLlmClient(base_url="http://x", api_key="k")
    req = ChatRequest(messages=[ChatMessage("user", "x")], model=LlmModel.MINIMAX_M3)
    data = {
        "choices": [{"message": {"content": "hello"}}],
        "usage": {"total_tokens": 5},
    }
    resp = cli._parse_response(data, req)
    assert resp.content == "hello"
    assert resp.model == LlmModel.MINIMAX_M3
    assert resp.raw == data


def test_http_client_parse_response_raises_on_malformed() -> None:
    cli = HttpLlmClient(base_url="http://x", api_key="k")
    req = ChatRequest(messages=[ChatMessage("user", "x")])
    with pytest.raises(LlmError, match="无法解析"):
        cli._parse_response({"choices": []}, req)
    with pytest.raises(LlmError):
        cli._parse_response({}, req)


# ---- HttpLlmClient 真实 HTTP 路径(用 httpx.MockTransport) ----

@pytest.mark.asyncio
async def test_http_client_success_via_mock_transport() -> None:
    """用 httpx.MockTransport 模拟中转,验证完整成功路径。"""
    cli = HttpLlmClient(base_url="http://mock", api_key="k", max_retries=0)
    req = ChatRequest(messages=[ChatMessage("user", "x")], model=LlmModel.MINIMAX_M3)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/chat/completions"
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    transport = httpx.MockTransport(handler)
    # 临时替换 httpx.AsyncClient 的 transport
    orig_init = httpx.AsyncClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        orig_init(self, *args, **kwargs)

    httpx.AsyncClient.__init__ = patched_init  # type: ignore[assignment]
    try:
        resp = await cli.complete(req)
    finally:
        httpx.AsyncClient.__init__ = orig_init  # type: ignore[assignment]
    assert resp.content == "ok"


@pytest.mark.asyncio
async def test_http_client_retries_on_500_then_succeeds() -> None:
    cli = HttpLlmClient(base_url="http://mock", api_key="k", max_retries=2)
    req = ChatRequest(messages=[ChatMessage("user", "x")], model=LlmModel.MINIMAX_M3)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(503, text="server error")
        return httpx.Response(200, json={"choices": [{"message": {"content": "after-retry"}}]})

    transport = httpx.MockTransport(handler)
    orig_init = httpx.AsyncClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        orig_init(self, *args, **kwargs)

    httpx.AsyncClient.__init__ = patched_init  # type: ignore[assignment]
    try:
        resp = await cli.complete(req)
    finally:
        httpx.AsyncClient.__init__ = orig_init  # type: ignore[assignment]
    assert resp.content == "after-retry"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_http_client_4xx_raises_without_retry() -> None:
    """4xx 客户端错误,不应该重试。"""
    cli = HttpLlmClient(base_url="http://mock", api_key="k", max_retries=3)
    req = ChatRequest(messages=[ChatMessage("user", "x")], model=LlmModel.MINIMAX_M3)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, text="bad request")

    transport = httpx.MockTransport(handler)
    orig_init = httpx.AsyncClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        orig_init(self, *args, **kwargs)

    httpx.AsyncClient.__init__ = patched_init  # type: ignore[assignment]
    try:
        with pytest.raises(LlmError) as exc_info:
            await cli.complete(req)
    finally:
        httpx.AsyncClient.__init__ = orig_init  # type: ignore[assignment]
    # 外层是通用包装,内层 __cause__ 包含 "客户端错误" 和状态码
    assert "客户端错误" in str(exc_info.value.__cause__)
    assert calls["n"] == 1  # 没重试


def test_set_client_overrides_singleton() -> None:
    fake = FakeLlmClient(default_reply="manual-set")
    set_client(fake)
    assert get_client() is fake


def test_get_client_returns_http_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.setenv("DIGIMON_LLM_API_KEY", "test-key")
    monkeypatch.setenv("DIGIMON_LLM_BASE_URL", "http://x")
    set_client(None)  # type: ignore[arg-type]
    cli = get_client()
    assert isinstance(cli, HttpLlmClient)


# ---- complete() 便捷函数 ----

@pytest.mark.asyncio
async def test_complete_uses_singleton() -> None:
    fake = FakeLlmClient(default_reply="via-singleton")
    set_client(fake)
    resp = await complete([ChatMessage("user", "x")], model=LlmModel.OPUS)
    assert resp.content == "via-singleton"
    assert resp.model == LlmModel.OPUS
    assert len(fake.calls) == 1
