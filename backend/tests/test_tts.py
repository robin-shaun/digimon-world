"""
TTS 模块测试 (Phase 13-①)

测试 TTS 声音配置、API 端点。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from digimon_world.api.app import app
from digimon_world import tts as tts_module


class TestVoiceProfiles:
    """测试声音配置。"""

    def test_all_digimon_have_profiles(self) -> None:
        """8 只初始数码兽都有声音配置。"""
        expected = [
            "agumon", "gabumon", "biyomon", "palmon",
            "gomamon", "tentomon", "patamon", "tailmon",
        ]
        for name in expected:
            profile = tts_module.get_voice_profile(name)
            assert "voice" in profile, f"{name} 缺少 voice"
            assert "pitch" in profile, f"{name} 缺少 pitch"
            assert "rate" in profile, f"{name} 缺少 rate"
            assert profile["voice"].startswith("zh-CN-"), \
                f"{name} 应使用中文语音, 实际: {profile['voice']}"

    def test_unknown_digimon_defaults(self) -> None:
        """未知数码兽使用默认声音。"""
        profile = tts_module.get_voice_profile("unknown_monster")
        assert profile == tts_module.DEFAULT_VOICE

    def test_case_insensitive_lookup(self) -> None:
        """大小写不敏感查找。"""
        profile1 = tts_module.get_voice_profile("Agumon")
        profile2 = tts_module.get_voice_profile("AGUMON")
        assert profile1 == profile2
        assert profile1["description"] == "少年音 · 热血"

    def test_greetings_exist_for_all(self) -> None:
        """每只数码兽都有至少一条问候语。"""
        for name in tts_module.DIGIMON_VOICE_PROFILES:
            greetings = tts_module.DIGIMON_GREETINGS.get(name, [])
            assert len(greetings) > 0, f"{name} 缺少问候语"

    def test_random_greeting_returns_string(self) -> None:
        """随机问候返回非空字符串。"""
        for name in tts_module.DIGIMON_VOICE_PROFILES:
            greeting = tts_module.get_random_greeting(name)
            assert isinstance(greeting, str)
            assert len(greeting) > 0


class TestTTSAPI:
    """测试 TTS API 端点 (使用 TestClient + mock)。"""

    # ---- helpers ----
    @staticmethod
    def _mock_speak(return_value=b"fake_audio", side_effect=None):
        """创建 speak_digimon 的 AsyncMock patcher。"""
        return patch.object(
            tts_module, "speak_digimon",
            new_callable=AsyncMock,
            return_value=return_value,
            side_effect=side_effect,
        )

    # ---- tests ----

    def test_list_voices(self) -> None:
        """GET /api/tts/voices 返回所有声音。"""
        client = TestClient(app)
        response = client.get("/api/tts/voices")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 8
        assert "agumon" in data["voices"]
        assert data["voices"]["agumon"]["description"] == "少年音 · 热血"

    def test_get_tts_no_text_uses_greeting(self) -> None:
        """GET /api/tts/{name} 无 text 参数时使用随机问候语。"""
        mock_audio = b"fake_wav_data_1234"
        with self._mock_speak(return_value=mock_audio):
            client = TestClient(app)
            response = client.get("/api/tts/agumon")
            assert response.status_code == 200
            assert response.headers["content-type"] == "audio/wav"
            assert response.content == mock_audio

    def test_get_tts_with_text(self) -> None:
        """GET /api/tts/{name}?text=xxx 传递指定文本。"""
        mock_audio = b"custom_tts_audio"
        with self._mock_speak(return_value=mock_audio) as mock_speak:
            client = TestClient(app)
            response = client.get("/api/tts/gabumon?text=你好世界")
            assert response.status_code == 200
            assert response.content == mock_audio
            mock_speak.assert_called_once_with("gabumon", "你好世界")

    def test_post_speak(self) -> None:
        """POST /api/tts/speak 正常流程。"""
        mock_audio = b"posted_tts_audio"
        with self._mock_speak(return_value=mock_audio) as mock_speak:
            client = TestClient(app)
            response = client.post(
                "/api/tts/speak",
                json={"name": "tailmon", "text": "黑暗势力正在逼近"},
            )
            assert response.status_code == 200
            assert response.content == mock_audio
            mock_speak.assert_called_once_with(
                "tailmon", "黑暗势力正在逼近"
            )

    def test_post_speak_empty_text_rejected(self) -> None:
        """空文本被拒绝。"""
        client = TestClient(app)
        response = client.post(
            "/api/tts/speak",
            json={"name": "agumon", "text": ""},
        )
        assert response.status_code == 422

    def test_tts_failure_returns_500(self) -> None:
        """TTS 生成失败时返回 500。"""
        with self._mock_speak(side_effect=RuntimeError("Edge TTS unavailable")):
            client = TestClient(app)
            # GET 端点
            response = client.get("/api/tts/agumon")
            assert response.status_code == 500
            # POST 端点
            response = client.post(
                "/api/tts/speak",
                json={"name": "agumon", "text": "test"},
            )
            assert response.status_code == 500

    def test_empty_audio_returns_500(self) -> None:
        """TTS 返回空音频时返回 500。"""
        with self._mock_speak(return_value=b""):
            client = TestClient(app)
            response = client.get("/api/tts/agumon")
            assert response.status_code == 500
