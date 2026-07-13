/**
 * DIGIMON WORLD - TTS 语音模块 (Phase 13)
 *
 * 调用后端 /api/tts 端点生成数码兽语音并播放。
 *
 * 用法:
 *   TTS.speak('agumon')              // 默认问候语
 *   TTS.speak('agumon', '你好世界')  // 自定义文本
 *   TTS.getVoices()                  // 获取可用声音列表
 *
 * 依赖: 后端 FastAPI /api/tts 端点 (Phase 13 新增)
 */

window.TTS = (function () {
    'use strict';

    let audioElement = null;
    let loading = false;

    /** 获取或创建 audio 元素 */
    function getAudio() {
        if (!audioElement) {
            audioElement = new Audio();
            audioElement.preload = 'auto';
        }
        return audioElement;
    }

    /**
     * 让数码兽说话
     * @param {string} name   数码兽名称 (如 'agumon')
     * @param {string} [text] 可选, 自定义文本; 不传则使用默认问候语
     * @returns {Promise<void>}
     */
    async function speak(name, text) {
        if (loading) {
            console.warn('[tts] 正在加载中, 请稍后再试');
            return;
        }
        loading = true;

        try {
            let url = (window.API_BASE || '') + '/api/tts/' + encodeURIComponent(name);
            if (text) {
                url += '?text=' + encodeURIComponent(text);
            }

            console.log('[tts] 请求语音:', url);
            const resp = await fetch(url, { cache: 'no-store' });
            if (!resp.ok) {
                const errText = await resp.text().catch(() => '未知错误');
                throw new Error(`HTTP ${resp.status}: ${errText}`);
            }

            const blob = await resp.blob();
            const objectUrl = URL.createObjectURL(blob);

            const audio = getAudio();
            // 停止当前播放
            audio.pause();
            audio.currentTime = 0;

            audio.src = objectUrl;
            audio.onended = () => {
                URL.revokeObjectURL(objectUrl);
            };
            audio.onerror = (e) => {
                console.error('[tts] 播放失败:', e);
                URL.revokeObjectURL(objectUrl);
            };

            await audio.play();
            console.log('[tts] 播放完成:', name);
        } catch (e) {
            console.error('[tts] 语音请求失败:', e.message);
            // 降级: 如果后端不可用, 尝试使用浏览器内置 TTS
            fallbackBrowserTTS(name, text);
        } finally {
            loading = false;
        }
    }

    /**
     * 降级方案: 使用浏览器内置 SpeechSynthesis API
     */
    function fallbackBrowserTTS(name, text) {
        if (!window.speechSynthesis) {
            console.warn('[tts] 浏览器不支持语音合成');
            return;
        }

        const msg = text || (name + '向你打招呼！');
        const utterance = new SpeechSynthesisUtterance(msg);
        utterance.lang = 'zh-CN';
        utterance.rate = 1.0;
        utterance.pitch = 1.0;

        // 根据不同数码兽调整参数
        const pitchMap = {
            agumon: 1.1, gabumon: 0.95, biyomon: 1.2, palmon: 1.05,
            gomamon: 1.15, tentomon: 0.9, patamon: 1.3, tailmon: 1.0,
        };
        utterance.pitch = pitchMap[name.toLowerCase()] || 1.0;

        window.speechSynthesis.speak(utterance);
    }

    /**
     * 获取可用数码兽声音列表 (查询后端)
     * @returns {Promise<Object>} { count, voices: { name: { description, greetings } } }
     */
    async function getVoices() {
        try {
            const url = (window.API_BASE || '') + '/api/tts/voices';
            const resp = await fetch(url, { cache: 'no-store' });
            if (!resp.ok) return { count: 0, voices: {} };
            return await resp.json();
        } catch (e) {
            console.warn('[tts] 获取声音列表失败:', e.message);
            return { count: 0, voices: {} };
        }
    }

    /** 检查 TTS 服务是否可用 */
    async function isAvailable() {
        try {
            const voices = await getVoices();
            return voices.count > 0;
        } catch {
            return false;
        }
    }

    return { speak, getVoices, isAvailable };
})();
