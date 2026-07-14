/**
 * DIGIMON WORLD - 音效系统 (Web Audio API)
 *
 * 纯程序化合成, 无外部音频文件依赖。
 * 音效列表:
 *   - battle:    碰撞声 (噪声 burst + 低频 thud)
 *   - evolution: 升调音 (正弦扫频 + 泛音 + 闪光颗粒)
 *   - notify:    叮咚   (双音阶短音 E5→G5)
 *   - footstep:  脚步声 (短促低频脉冲)
 *   - digivice:  神圣计划激活 (三连升调琶音)
 *   - heal:      治愈音 (柔和竖琴风琶音)
 *
 * 用法:
 *   SFX.play('battle')
 *   SFX.play('evolution')
 *   SFX.play('footstep')
 *   SFX.mute()  / SFX.unmute()  / SFX.toggle()
 *   SFX.setVolume(0.5)  / SFX.getVolume()
 */

window.SFX = (function () {
    'use strict';

    let ctx = null;       // AudioContext (懒初始化, 需要用户手势)
    let muted = false;
    let volume = 1.0;     // 主音量 0.0~1.0
    let initialized = false;
    let _footstepThrottle = -1000;  // 步声音效节流 (ms since last play), 初始负值让首次立即播放

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
        const v = volume;

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
        noiseGain.gain.setValueAtTime(0.35 * v, now);
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
        thudGain.gain.setValueAtTime(0.5 * v, now);
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
        const v = volume;

        // 主音 (C4 → C6 扫频)
        const osc1 = c.createOscillator();
        osc1.type = 'sine';
        osc1.frequency.setValueAtTime(261.6, now);           // C4
        osc1.frequency.exponentialRampToValueAtTime(1046.5, now + dur);  // C6

        const gain1 = c.createGain();
        gain1.gain.setValueAtTime(0.3 * v, now);
        gain1.gain.setValueAtTime(0.3 * v, now + dur * 0.7);
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
        gain2.gain.linearRampToValueAtTime(0.15 * v, now + 0.1);
        gain2.gain.setValueAtTime(0.15 * v, now + dur * 0.6);
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
        shimGain.gain.linearRampToValueAtTime(0.08 * v, now + 0.15);
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
        const v = volume;

        // 叮 (E5, 120ms)
        const osc1 = c.createOscillator();
        osc1.type = 'sine';
        osc1.frequency.value = 659.25;  // E5
        const g1 = c.createGain();
        g1.gain.setValueAtTime(0.25 * v, now);
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
        g2.gain.linearRampToValueAtTime(0.25 * v, now + 0.1);
        g2.gain.exponentialRampToValueAtTime(0.01, now + 0.25);
        osc2.connect(g2);
        g2.connect(c.destination);
        osc2.start(now);
        osc2.stop(now + 0.25);
    }

    /** 脚步声: 短促低频脉冲 (50ms), 模拟踩地 */
    function playFootstep() {
        const c = ensureCtx();
        if (!c) return;
        const now = c.currentTime;
        const v = volume;

        // 低频 thud
        const osc = c.createOscillator();
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(80, now);
        osc.frequency.exponentialRampToValueAtTime(30, now + 0.05);

        const gain = c.createGain();
        gain.gain.setValueAtTime(0.15 * v, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.05);

        osc.connect(gain);
        gain.connect(c.destination);
        osc.start(now);
        osc.stop(now + 0.05);

        // 轻微高频噪声 (地面质感)
        const bufLen = Math.floor(c.sampleRate * 0.04);
        const buf = c.createBuffer(1, bufLen, c.sampleRate);
        const data = buf.getChannelData(0);
        for (let i = 0; i < bufLen; i++) {
            data[i] = (Math.random() * 2 - 1) * 0.3 * (1 - i / bufLen);
        }
        const noise = c.createBufferSource();
        noise.buffer = buf;

        const noiseFilter = c.createBiquadFilter();
        noiseFilter.type = 'highpass';
        noiseFilter.frequency.value = 2000;

        const noiseGain = c.createGain();
        noiseGain.gain.setValueAtTime(0.06 * v, now);
        noiseGain.gain.exponentialRampToValueAtTime(0.001, now + 0.04);

        noise.connect(noiseFilter);
        noiseFilter.connect(noiseGain);
        noiseGain.connect(c.destination);
        noise.start(now);
        noise.stop(now + 0.04);
    }

    /** 神圣计划激活: 三连升调琶音 (C5→E5→G5, 每个 80ms) */
    function playDigivice() {
        const c = ensureCtx();
        if (!c) return;
        const now = c.currentTime;
        const v = volume;
        const notes = [523.25, 659.25, 783.99];  // C5, E5, G5

        notes.forEach(function (freq, i) {
            const t = now + i * 0.08;
            const osc = c.createOscillator();
            osc.type = 'sine';
            osc.frequency.value = freq;

            const gain = c.createGain();
            gain.gain.setValueAtTime(0.0001, t);
            gain.gain.linearRampToValueAtTime(0.2 * v, t + 0.01);
            gain.gain.setValueAtTime(0.2 * v, t + 0.05);
            gain.gain.exponentialRampToValueAtTime(0.001, t + 0.1);

            osc.connect(gain);
            gain.connect(c.destination);
            osc.start(t);
            osc.stop(t + 0.1);
        });

        // 泛音闪亮 (高八度, 延迟 150ms)
        const shimmerOsc = c.createOscillator();
        shimmerOsc.type = 'triangle';
        shimmerOsc.frequency.setValueAtTime(1046.5, now + 0.15);  // C6
        shimmerOsc.frequency.exponentialRampToValueAtTime(1568, now + 0.35);  // G6

        const shimGain = c.createGain();
        shimGain.gain.setValueAtTime(0.0001, now);
        shimGain.gain.linearRampToValueAtTime(0.12 * v, now + 0.16);
        shimGain.gain.exponentialRampToValueAtTime(0.001, now + 0.4);

        shimmerOsc.connect(shimGain);
        shimGain.connect(c.destination);
        shimmerOsc.start(now);
        shimmerOsc.stop(now + 0.4);
    }

    /** 治愈音: 柔和竖琴风上行琶音 (C4→E4→G4→C5, 各 100ms, 轻柔) */
    function playHeal() {
        const c = ensureCtx();
        if (!c) return;
        const now = c.currentTime;
        const v = volume;
        const notes = [261.63, 329.63, 392.00, 523.25];  // C4, E4, G4, C5

        notes.forEach(function (freq, i) {
            const t = now + i * 0.1;
            const osc = c.createOscillator();
            osc.type = 'sine';
            osc.frequency.value = freq;

            const gain = c.createGain();
            gain.gain.setValueAtTime(0.0001, t);
            gain.gain.linearRampToValueAtTime(0.18 * v, t + 0.02);
            gain.gain.exponentialRampToValueAtTime(0.001, t + 0.15);

            osc.connect(gain);
            gain.connect(c.destination);
            osc.start(t);
            osc.stop(t + 0.15);
        });

        // 柔和泛音叠层 (高八度, 音量更低)
        notes.forEach(function (freq, i) {
            const t = now + i * 0.1 + 0.03;
            const osc = c.createOscillator();
            osc.type = 'triangle';
            osc.frequency.value = freq * 2;

            const gain = c.createGain();
            gain.gain.setValueAtTime(0.0001, t);
            gain.gain.linearRampToValueAtTime(0.06 * v, t + 0.02);
            gain.gain.exponentialRampToValueAtTime(0.001, t + 0.12);

            osc.connect(gain);
            gain.connect(c.destination);
            osc.start(t);
            osc.stop(t + 0.12);
        });
    }

    // ---- 路由 ----
    const SOUNDS = {
        battle: playBattle,
        evolution: playEvolution,
        notify: playNotify,
        footstep: playFootstep,
        digivice: playDigivice,
        heal: playHeal,
    };

    /**
     * 播放音效 (带脚步声节流: 最少间隔 200ms)
     * @param {string} name - battle|evolution|notify|footstep|digivice|heal
     */
    function play(name) {
        if (muted) return;
        resume();
        // footstep 节流: 避免高频调用 (每帧都 isMoving → 60fps 触发)
        if (name === 'footstep') {
            const now = performance.now();
            if (now - _footstepThrottle < 200) return;  // 200ms cooldown
            _footstepThrottle = now;
        }
        const fn = SOUNDS[name];
        if (fn) fn();
    }

    // ---- 音量控制 ----
    /** @param {number} v - 0.0 ~ 1.0 */
    function setVolume(v) {
        volume = Math.max(0, Math.min(1, v));
    }
    function getVolume() {
        return volume;
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

    return { play, mute, unmute, toggle, isMuted, setVolume, getVolume };
})();
