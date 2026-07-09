/**
 * DIGIMON WORLD - 音效系统 (Web Audio API)
 *
 * 纯程序化合成, 无外部音频文件依赖。
 * 三种音效:
 *   - battle:    碰撞声 (噪声 burst + 低频 thud)
 *   - evolution: 升调音 (正弦扫频 + 泛音)
 *   - notify:    叮咚   (双音阶短音)
 *
 * 用法:
 *   SFX.play('battle')
 *   SFX.play('evolution')
 *   SFX.play('notify')
 *   SFX.mute()  / SFX.unmute()  / SFX.toggle()
 */

window.SFX = (function () {
    'use strict';

    let ctx = null;       // AudioContext (懒初始化, 需要用户手势)
    let muted = false;
    let initialized = false;

    /** 确保 AudioContext 已创建 (首次播放时或用户交互后调用) */
    function ensureCtx() {
        if (ctx) return ctx;
        try {
            ctx = new (window.AudioContext || window.webkitAudioContext)();
            initialized = true;
        } catch (e) {
            console.warn('[sfx] Web Audio API 不可用:', e);
        }
        return ctx;
    }

    /** 恢复被浏览器挂起的 AudioContext */
    function resume() {
        if (ctx && ctx.state === 'suspended') {
            ctx.resume();
        }
    }

    // ---- 音效合成 ----

    /** 碰撞声: 短促噪声 burst + 低频 thud */
    function playBattle() {
        const c = ensureCtx();
        if (!c) return;
        const now = c.currentTime;

        // 噪声 burst (80ms)
        const bufLen = Math.floor(c.sampleRate * 0.08);
        const buf = c.createBuffer(1, bufLen, c.sampleRate);
        const data = buf.getChannelData(0);
        for (let i = 0; i < bufLen; i++) {
            data[i] = (Math.random() * 2 - 1) * (1 - i / bufLen);  // 线性衰减
        }
        const noise = c.createBufferSource();
        noise.buffer = buf;

        const noiseGain = c.createGain();
        noiseGain.gain.setValueAtTime(0.35, now);
        noiseGain.gain.exponentialRampToValueAtTime(0.01, now + 0.08);

        const noiseFilter = c.createBiquadFilter();
        noiseFilter.type = 'bandpass';
        noiseFilter.frequency.value = 1200;
        noiseFilter.Q.value = 1.5;

        noise.connect(noiseFilter);
        noiseFilter.connect(noiseGain);
        noiseGain.connect(c.destination);
        noise.start(now);
        noise.stop(now + 0.08);

        // 低频 thud (120ms)
        const osc = c.createOscillator();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(120, now);
        osc.frequency.exponentialRampToValueAtTime(40, now + 0.12);

        const thudGain = c.createGain();
        thudGain.gain.setValueAtTime(0.5, now);
        thudGain.gain.exponentialRampToValueAtTime(0.01, now + 0.12);

        osc.connect(thudGain);
        thudGain.connect(c.destination);
        osc.start(now);
        osc.stop(now + 0.12);
    }

    /** 升调音: 正弦波从 C4 扫到 C6 + 泛音光辉感 */
    function playEvolution() {
        const c = ensureCtx();
        if (!c) return;
        const now = c.currentTime;
        const dur = 0.6;

        // 主音 (C4 → C6 扫频)
        const osc1 = c.createOscillator();
        osc1.type = 'sine';
        osc1.frequency.setValueAtTime(261.6, now);           // C4
        osc1.frequency.exponentialRampToValueAtTime(1046.5, now + dur);  // C6

        const gain1 = c.createGain();
        gain1.gain.setValueAtTime(0.3, now);
        gain1.gain.setValueAtTime(0.3, now + dur * 0.7);
        gain1.gain.exponentialRampToValueAtTime(0.01, now + dur);

        osc1.connect(gain1);
        gain1.connect(c.destination);
        osc1.start(now);
        osc1.stop(now + dur);

        // 泛音 (高八度, 延迟 100ms 进入)
        const osc2 = c.createOscillator();
        osc2.type = 'triangle';
        osc2.frequency.setValueAtTime(523.2, now + 0.1);     // C5
        osc2.frequency.exponentialRampToValueAtTime(2093, now + dur); // C7

        const gain2 = c.createGain();
        gain2.gain.setValueAtTime(0.0001, now);
        gain2.gain.linearRampToValueAtTime(0.15, now + 0.1);
        gain2.gain.setValueAtTime(0.15, now + dur * 0.6);
        gain2.gain.exponentialRampToValueAtTime(0.01, now + dur);

        osc2.connect(gain2);
        gain2.connect(c.destination);
        osc2.start(now);
        osc2.stop(now + dur);

        // 闪光颗粒感 (短 noise shimmer)
        const shimBuf = c.createBuffer(1, Math.floor(c.sampleRate * 0.3), c.sampleRate);
        const shimData = shimBuf.getChannelData(0);
        for (let i = 0; i < shimData.length; i++) {
            shimData[i] = (Math.random() * 2 - 1) * 0.5;
        }
        const shim = c.createBufferSource();
        shim.buffer = shimBuf;

        const shimFilter = c.createBiquadFilter();
        shimFilter.type = 'highpass';
        shimFilter.frequency.value = 4000;

        const shimGain = c.createGain();
        shimGain.gain.setValueAtTime(0.0001, now);
        shimGain.gain.linearRampToValueAtTime(0.08, now + 0.15);
        shimGain.gain.exponentialRampToValueAtTime(0.01, now + dur);

        shim.connect(shimFilter);
        shimFilter.connect(shimGain);
        shimGain.connect(c.destination);
        shim.start(now);
        shim.stop(now + dur);
    }

    /** 叮咚: 双音阶短音 (E5 → G5) */
    function playNotify() {
        const c = ensureCtx();
        if (!c) return;
        const now = c.currentTime;

        // 叮 (E5, 120ms)
        const osc1 = c.createOscillator();
        osc1.type = 'sine';
        osc1.frequency.value = 659.25;  // E5
        const g1 = c.createGain();
        g1.gain.setValueAtTime(0.25, now);
        g1.gain.exponentialRampToValueAtTime(0.01, now + 0.12);
        osc1.connect(g1);
        g1.connect(c.destination);
        osc1.start(now);
        osc1.stop(now + 0.12);

        // 咚 (G5, 延迟 100ms, 150ms)
        const osc2 = c.createOscillator();
        osc2.type = 'sine';
        osc2.frequency.value = 783.99;  // G5
        const g2 = c.createGain();
        g2.gain.setValueAtTime(0.0001, now);
        g2.gain.linearRampToValueAtTime(0.25, now + 0.1);
        g2.gain.exponentialRampToValueAtTime(0.01, now + 0.25);
        osc2.connect(g2);
        g2.connect(c.destination);
        osc2.start(now);
        osc2.stop(now + 0.25);
    }

    // ---- 路由 ----
    const SOUNDS = {
        battle: playBattle,
        evolution: playEvolution,
        notify: playNotify,
    };

    function play(name) {
        if (muted) return;
        resume();
        const fn = SOUNDS[name];
        if (fn) fn();
    }

    // ---- 静音控制 ----
    function mute() { muted = true; }
    function unmute() { muted = false; resume(); }
    function toggle() { muted = !muted; return !muted; }
    function isMuted() { return muted; }

    // 首次用户交互时解锁 AudioContext (浏览器自动播放策略)
    function unlockOnInteraction() {
        const unlock = () => {
            ensureCtx();
            resume();
            document.removeEventListener('click', unlock);
            document.removeEventListener('keydown', unlock);
        };
        document.addEventListener('click', unlock, { once: true });
        document.addEventListener('keydown', unlock, { once: true });
    }
    unlockOnInteraction();

    return { play, mute, unmute, toggle, isMuted };
})();
