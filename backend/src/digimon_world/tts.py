"""
数码兽 TTS 配音模块 (Phase 13-①)
===============================

使用 Microsoft Edge TTS (免费, 无需 API Key) 为每只数码兽生成独特声线。

数码兽 → 声音配置:
- 亚古兽 (Agumon)       → 少年音, 热血
- 加布兽 (Gabumon)      → 温和, 略低沉
- 比丘兽 (Biyomon)      → 少女音, 活泼
- 巴鲁兽 (Palmon)       → 女性, 温柔
- 哥玛兽 (Gomamon)      → 少年音, 顽皮
- 甲虫兽 (Tentomon)     → 电子音, 理性
- 巴达兽 (Patamon)      → 童声, 天真
- 迪路兽 (Tailmon)      → 女性, 成熟

API:
    GET  /api/tts/{name}         — 获取数码兽语音 (wav)
    POST /api/tts/speak          — 让数码兽说指定文本
"""

from __future__ import annotations

import asyncio
import io
import logging
from typing import Optional

logger = logging.getLogger("digimon.tts")


# ---- 数码兽声音配置 ----
# 使用 Microsoft Edge TTS 的 zh-CN / ja-JP 语音
# 中文在线语音参考: https://learn.microsoft.com/zh-cn/azure/ai-services/speech-service/language-support

DIGIMON_VOICE_PROFILES: dict[str, dict[str, str]] = {
    "agumon": {
        "voice": "zh-CN-YunxiNeural",      # 少年声, 热情
        "pitch": "+5Hz",                     # 略高, 显活泼
        "rate": "+10%",                      # 语速略快
        "description": "少年音 · 热血",
    },
    "gabumon": {
        "voice": "zh-CN-YunyangNeural",     # 温和男声
        "pitch": "-3Hz",
        "rate": "+0%",
        "description": "温和 · 略低沉",
    },
    "biyomon": {
        "voice": "zh-CN-XiaoxiaoNeural",    # 少女音
        "pitch": "+8Hz",
        "rate": "+15%",
        "description": "少女音 · 活泼",
    },
    "palmon": {
        "voice": "zh-CN-XiaoyiNeural",      # 温柔女声
        "pitch": "+2Hz",
        "rate": "+5%",
        "description": "女性 · 温柔",
    },
    "gomamon": {
        "voice": "zh-CN-YunxiNeural",       # 少年声 (复用, pitch 区别)
        "pitch": "+10Hz",
        "rate": "+12%",
        "description": "少年音 · 顽皮",
    },
    "tentomon": {
        "voice": "zh-CN-YunyangNeural",     # 男声, 偏冷
        "pitch": "-5Hz",
        "rate": "-5%",
        "description": "电子音 · 理性",
    },
    "patamon": {
        "voice": "zh-CN-XiaoxiaoNeural",    # 少女/童声
        "pitch": "+15Hz",
        "rate": "+10%",
        "description": "童声 · 天真",
    },
    "tailmon": {
        "voice": "zh-CN-XiaoyiNeural",      # 成熟女声
        "pitch": "+0Hz",
        "rate": "+0%",
        "description": "女性 · 成熟",
    },
}

# 默认声音 (未知数码兽使用)
DEFAULT_VOICE = {
    "voice": "zh-CN-YunxiNeural",
    "pitch": "+0Hz",
    "rate": "+0%",
    "description": "默认",
}


def get_voice_profile(name: str) -> dict[str, str]:
    """获取数码兽的声音配置, 未知则返回默认。"""
    key = name.lower().replace(" ", "_").replace("-", "_")
    return DIGIMON_VOICE_PROFILES.get(key, DEFAULT_VOICE)


async def generate_tts(text: str, voice: str = "zh-CN-YunxiNeural",
                        pitch: str = "+0Hz", rate: str = "+0%") -> bytes:
    """使用 Edge TTS 生成语音, 返回 WAV 字节。

    Args:
        text: 要朗读的文本
        voice: Microsoft Edge TTS 语音名称
        pitch: 音高调整, 如 "+5Hz" 或 "-3Hz"
        rate: 语速调整, 如 "+10%" 或 "-5%"

    Returns:
        WAV 格式的音频数据
    """
    import edge_tts

    try:
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            pitch=pitch,
            rate=rate,
        )
        # 收集所有音频块
        chunks: list[bytes] = []
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                data = chunk.get("data")
                if data:
                    chunks.append(data)

        if not chunks:
            logger.warning(f"TTS 生成空音频: text={text[:50]}...")
            return b""

        return b"".join(chunks)
    except Exception as e:
        logger.error(f"TTS 生成失败: {e}", exc_info=True)
        raise


async def speak_digimon(name: str, text: str) -> bytes:
    """让指定数码兽说话, 使用其专属声线。

    Args:
        name: 数码兽名称 (如 "agumon")
        text: 要说的文本

    Returns:
        WAV 音频数据
    """
    profile = get_voice_profile(name)
    logger.info(
        f"🎤 {name} 说话 [{profile['description']}]: {text[:80]}..."
    )
    return await generate_tts(
        text=text,
        voice=profile["voice"],
        pitch=profile["pitch"],
        rate=profile["rate"],
    )


# ---- 预设对话文本 (用于快速演示) ----

DIGIMON_GREETINGS: dict[str, list[str]] = {
    "agumon": [
        "我是亚古兽！要一起冒险吗？",
        "肚子有点饿了…有吃的吗？",
        "太一在哪里？我感觉到他的气息了！",
    ],
    "gabumon": [
        "我是加布兽，请多关照。",
        "阿和，我会一直陪着你的。",
        "冷静分析，才能找到最好的策略。",
    ],
    "biyomon": [
        "我是比丘兽！今天天气真好呀~",
        "素娜，快来看这个！",
        "飞起来的感觉最棒了！",
    ],
    "palmon": [
        "我是巴鲁兽，花香真好闻~",
        "美美，要开心哦！",
        "这片森林是我的家。",
    ],
    "gomamon": [
        "我是哥玛兽！来游泳吧！",
        "阿丈，别太紧张啦~",
        "大海在呼唤我！",
    ],
    "tentomon": [
        "我是甲虫兽，正在分析数据。",
        "光子郎，我发现了一个 bug！",
        "根据我的计算，胜率是 78.3%。",
    ],
    "patamon": [
        "我是巴达兽！好想飞得更高~",
        "阿武，我们要永远在一起！",
        "进化之光，赐予我力量！",
    ],
    "tailmon": [
        "我是迪路兽，保持警惕。",
        "黑暗势力正在逼近…",
        "嘉儿，我感受到了危险。",
    ],
}


def get_random_greeting(name: str) -> str:
    """获取随机问候语。"""
    import random
    key = name.lower().replace(" ", "_").replace("-", "_")
    greetings = DIGIMON_GREETINGS.get(key, [f"我是{name}！你好！"])
    return random.choice(greetings)
