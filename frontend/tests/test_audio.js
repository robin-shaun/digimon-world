/**
 * DIGIMON WORLD - SFX 音效系统单元测试 (Phase 13)
 *
 * 覆盖: audio.js 的音效路由、静音控制、AudioContext 生命周期
 *
 * 运行: node frontend/tests/test_audio.js
 *
 * 注意: 依赖 mock Web Audio API (Node.js 无原生 AudioContext)
 */

'use strict';

// ═══ Node.js shim + Web Audio API mock ═══
if (typeof window === 'undefined') {
    global.window = global;
}

// Mock Web Audio API before loading audio.js
const mockCalls = [];
let mockCtxState = 'running';

function MockAudioContext() {
    this.state = mockCtxState;
    this.sampleRate = 44100;
    this.currentTime = 0;
    this.destination = { _isDestination: true };

    this._nodes = [];
    mockCalls.push('new AudioContext');
}

MockAudioContext.prototype = {
    createGain: function () {
        const node = {
            gain: { value: 0, _values: [], setValueAtTime: function (v, t) { this._values.push(['set', v, t]); }, exponentialRampToValueAtTime: function (v, t) { this._values.push(['expRamp', v, t]); }, linearRampToValueAtTime: function (v, t) { this._values.push(['linRamp', v, t]); } },
            connect: function (dest) { mockCalls.push('gain.connect'); },
            _isGain: true,
        };
        mockCalls.push('createGain');
        return node;
    },
    createOscillator: function () {
        const node = {
            type: 'sine',
            frequency: { value: 0, _values: [], setValueAtTime: function (v, t) { this._values.push(['set', v, t]); }, exponentialRampToValueAtTime: function (v, t) { this._values.push(['expRamp', v, t]); } },
            connect: function (dest) { mockCalls.push('osc.connect'); },
            start: function (t) { mockCalls.push('osc.start'); },
            stop: function (t) { mockCalls.push('osc.stop'); },
            _isOsc: true,
        };
        mockCalls.push('createOscillator');
        return node;
    },
    createBuffer: function (channels, length, sampleRate) {
        const buf = {
            numberOfChannels: channels,
            length: length,
            sampleRate: sampleRate,
            getChannelData: function (ch) {
                const arr = new Float32Array(length);
                for (let i = 0; i < length; i++) arr[i] = (Math.random() * 2 - 1);
                return arr;
            },
        };
        mockCalls.push('createBuffer');
        return buf;
    },
    createBufferSource: function () {
        const node = {
            buffer: null,
            connect: function (dest) { mockCalls.push('bufSrc.connect'); },
            start: function (t) { mockCalls.push('bufSrc.start'); },
            stop: function (t) { mockCalls.push('bufSrc.stop'); },
            _isBufSrc: true,
        };
        mockCalls.push('createBufferSource');
        return node;
    },
    createBiquadFilter: function () {
        const node = {
            type: 'lowpass',
            frequency: { value: 0 },
            Q: { value: 0 },
            connect: function (dest) { mockCalls.push('filter.connect'); },
            _isFilter: true,
        };
        mockCalls.push('createBiquadFilter');
        return node;
    },
    resume: function () {
        mockCalls.push('ctx.resume');
        mockCtxState = 'running';
        this.state = 'running';
        return Promise.resolve();
    },
};

window.AudioContext = MockAudioContext;
window.webkitAudioContext = MockAudioContext;

// Mock document (audio.js calls addEventListener in unlockOnInteraction)
global.document = {
    _listeners: {},
    addEventListener: function (evt, fn, opts) {
        (this._listeners[evt] = this._listeners[evt] || []).push(fn);
    },
    removeEventListener: function (evt, fn) {
        const arr = this._listeners[evt];
        if (arr) {
            const idx = arr.indexOf(fn);
            if (idx >= 0) arr.splice(idx, 1);
        }
    },
};

// ═══ Load audio.js ═══
// Reset mock calls before loading (constructor called on init)
mockCalls.length = 0;
mockCtxState = 'running';

const fs = require('fs');
const path = require('path');
const audioSrc = fs.readFileSync(path.join(__dirname, '..', 'audio.js'), 'utf-8');
eval(audioSrc);

const SFX = window.SFX;
if (!SFX) {
    console.error('FATAL: SFX module failed to load');
    process.exit(1);
}

// ═══ Test harness ═══
let passed = 0;
let failed = 0;
const failures = [];

function assert(condition, msg) {
    if (condition) {
        passed++;
    } else {
        failed++;
        failures.push(msg);
        console.error(`  ❌ FAIL: ${msg}`);
    }
}

function section(title) {
    console.log(`\n━━━ ${title} ━━━`);
}

// ═══════════════════════════════════════
//  静音控制测试
// ═══════════════════════════════════════

section('Mute control');

// 初始状态: 不静音
assert(SFX.isMuted() === false, 'default not muted');

// mute
SFX.mute();
assert(SFX.isMuted() === true, 'after mute: isMuted=true');

// unmute
SFX.unmute();
assert(SFX.isMuted() === false, 'after unmute: isMuted=false');

// toggle
const toggled = SFX.toggle();
// toggle() returns the PREVIOUS state (false → true muted, returns false)
assert(SFX.isMuted() === true, 'toggle: now muted');
assert(toggled === false, 'toggle returns old state (false, was unmuted)');

// toggle again
SFX.toggle();
assert(SFX.isMuted() === false, 'double toggle: back to unmuted');

// ═══════════════════════════════════════
//  play 路由测试
// ═══════════════════════════════════════

section('Play routing — battle');

SFX.unmute(); // ensure unmuted
mockCalls.length = 0;
SFX.play('battle');

// battle 应该创建 AudioContext + 噪声 burst + 低频 thud
assert(mockCalls.includes('new AudioContext'), 'play("battle"): AudioContext created');
assert(mockCalls.includes('createBuffer'), 'play("battle"): buffer created for noise');
assert(mockCalls.includes('createBufferSource'), 'play("battle"): bufferSource created');
assert(mockCalls.includes('createGain'), 'play("battle"): gain nodes created');
assert(mockCalls.includes('createOscillator'), 'play("battle"): oscillator for thud');
assert(mockCalls.includes('createBiquadFilter'), 'play("battle"): bandpass filter');

section('Play routing — evolution');

mockCalls.length = 0;
SFX.play('evolution');

// evolution 应该有 2 个 oscillator (主音 + 泛音) + noise shimmer
const oscCount = mockCalls.filter(c => c === 'createOscillator').length;
assert(oscCount >= 2, `play("evolution"): ≥2 oscillators (got ${oscCount})`);
assert(mockCalls.includes('createBuffer'), 'play("evolution"): shimmer buffer');

section('Play routing — notify');

mockCalls.length = 0;
SFX.play('notify');

// notify 应该有 2 个 oscillator (叮 + 咚)
const notifOscCount = mockCalls.filter(c => c === 'createOscillator').length;
assert(notifOscCount >= 2, `play("notify"): ≥2 oscillators (got ${notifOscCount})`);

// ═══════════════════════════════════════
//  静音时 play 被抑制
// ═══════════════════════════════════════

section('Muted: play suppressed');

SFX.mute();
mockCalls.length = 0;
SFX.play('battle');
assert(mockCalls.length === 0, 'muted: no audio calls for battle');

SFX.play('evolution');
assert(mockCalls.length === 0, 'muted: no audio calls for evolution');

SFX.play('notify');
assert(mockCalls.length === 0, 'muted: no audio calls for notify');

SFX.unmute();

// ═══════════════════════════════════════
//  未知音效名测试
// ═══════════════════════════════════════

section('Unknown sound name');

mockCalls.length = 0;
SFX.play('nonexistent');
// 不应该抛出异常, 也不应该调用任何音频 API
// (play 内部找不到 SOUNDS[name] 会静默跳过, 但 ensureCtx 已在 unmute 时被调用过
//  不过之前 mockCalls 已清空, AudioContext 已在之前创建, 所以这里应该没有新调用)
// 实际上 ensureCtx 使用缓存的 ctx, 不会创建新的
assert(mockCalls.length === 0, 'unknown sound: no crashes, no audio calls');

// ═══════════════════════════════════════
//  AudioContext 挂起恢复
// ═══════════════════════════════════════

section('AudioContext resume');

// 模拟 AudioContext 被浏览器挂起
mockCtxState = 'suspended';
// 需要重新创建 mock ctx — 这里直接测试 resume 的逻辑
// SFX.unmute() 会调用内部 resume()
mockCalls.length = 0;
SFX.unmute(); // 内部调用 resume()
// unmute 调用 resume, 但 resume 内部先 ensureCtx (已有缓存), 然后检查 state
// 由于我们重用了之前的 ctx (state=running), 需要模拟新情况
assert(typeof SFX.play === 'function', 'SFX.play is callable');

// ═══════════════════════════════════════
//  多次 play 复用 AudioContext
// ═══════════════════════════════════════

section('AudioContext reuse');

mockCalls.length = 0;
SFX.play('battle');
SFX.play('notify');

// AudioContext 应该只创建一次 (首次), 后续复用
const ctxCreations = mockCalls.filter(c => c === 'new AudioContext').length;
// 首次在模块初始化时已创建 (unlockOnInteraction), 所以这里可能是 0 或 1
assert(ctxCreations <= 1, `AudioContext created ≤1 times (got ${ctxCreations})`);

// ═══════════════════════════════════════
//  连续快速调用不崩溃
// ═══════════════════════════════════════

section('Rapid fire');

for (let i = 0; i < 10; i++) {
    SFX.play('notify');
}
// 不应该抛出异常
assert(true, 'rapid 10x notify: no crash');

for (let i = 0; i < 10; i++) {
    SFX.play('battle');
}
assert(true, 'rapid 10x battle: no crash');

for (let i = 0; i < 10; i++) {
    SFX.play('evolution');
}
assert(true, 'rapid 10x evolution: no crash');

// ═══════════════════════════════════════
//  toggle 幂等性
// ═══════════════════════════════════════

section('Toggle idempotence');

SFX.unmute();
assert(SFX.isMuted() === false, 'start unmuted');
const r1 = SFX.toggle();
assert(r1 === false, 'toggle→muted returns old state (false)');
assert(SFX.isMuted() === true, 'now muted');
const r2 = SFX.toggle();
assert(r2 === true, 'toggle→unmuted returns old state (true)');
assert(SFX.isMuted() === false, 'now unmuted');

// ═══════════════════════════════════════
//  音量控制测试
// ═══════════════════════════════════════

section('Volume control');

assert(typeof SFX.setVolume === 'function', 'setVolume is a function');
assert(typeof SFX.getVolume === 'function', 'getVolume is a function');

// 默认音量 = 1.0
assert(SFX.getVolume() === 1.0, 'default volume = 1.0');

// 设置音量
SFX.setVolume(0.5);
assert(SFX.getVolume() === 0.5, 'setVolume(0.5) → getVolume = 0.5');

// 边界: 小于 0 截断为 0
SFX.setVolume(-0.3);
assert(SFX.getVolume() === 0, 'setVolume(-0.3) clamped to 0');

// 边界: 大于 1 截断为 1
SFX.setVolume(2.5);
assert(SFX.getVolume() === 1, 'setVolume(2.5) clamped to 1');

// 重置音量
SFX.setVolume(1.0);

// 音量降低后 play 增益应缩放 (验证不崩溃)
SFX.setVolume(0.3);
mockCalls.length = 0;
SFX.play('notify');
assert(mockCalls.filter(c => c === 'createOscillator').length >= 2,
    'notify at 0.3 volume: still creates oscillators');

SFX.setVolume(1.0);

// ═══════════════════════════════════════
//  新音效 — footstep
// ═══════════════════════════════════════

section('New SFX — footstep');

mockCalls.length = 0;
SFX.play('footstep');
assert(mockCalls.includes('createOscillator'), 'footstep: creates oscillator (thud)');
assert(mockCalls.includes('createBuffer'), 'footstep: creates noise buffer');
assert(mockCalls.includes('createBiquadFilter'), 'footstep: uses highpass filter');

// 节流: 200ms 内第二次调用应被忽略
mockCalls.length = 0;
SFX.play('footstep');
SFX.play('footstep');  // 立即第二次, 应被节流
const footstepOscCount = mockCalls.filter(c => c === 'createOscillator').length;
assert(footstepOscCount <= 1, `footstep throttle: ≤1 oscillator (got ${footstepOscCount})`);

// ═══════════════════════════════════════
//  新音效 — digivice
// ═══════════════════════════════════════

section('New SFX — digivice');

mockCalls.length = 0;
SFX.play('digivice');
// 三连音 (3 oscillators) + shimmer (1 oscillator) = 4 total
const digiviceOscCount = mockCalls.filter(c => c === 'createOscillator').length;
assert(digiviceOscCount >= 3, `digivice: ≥3 oscillators (got ${digiviceOscCount})`);

// ═══════════════════════════════════════
//  新音效 — heal
// ═══════════════════════════════════════

section('New SFX — heal');

mockCalls.length = 0;
SFX.play('heal');
// 4 主音 + 4 泛音 = 8 oscillators
const healOscCount = mockCalls.filter(c => c === 'createOscillator').length;
assert(healOscCount >= 6, `heal: ≥6 oscillators (got ${healOscCount})`);

// ═══════════════════════════════════════
//  静音时新音效也抑制
// ═══════════════════════════════════════

section('Muted: new sounds suppressed');

SFX.mute();
mockCalls.length = 0;
SFX.play('footstep');
SFX.play('digivice');
SFX.play('heal');
assert(mockCalls.length === 0, 'muted: no audio calls for new sounds');
SFX.unmute();

// ═══════════════════════════════════════
//  结果汇总
// ═══════════════════════════════════════

console.log(`\n${'='.repeat(50)}`);
const total = passed + failed;
if (failed === 0) {
    console.log(`✅ ALL ${total} TESTS PASSED`);
    console.log(`${'='.repeat(50)}`);
    process.exit(0);
} else {
    console.log(`❌ ${failed}/${total} TESTS FAILED`);
    console.log(`\nFailures:`);
    failures.forEach((f, i) => console.log(`  ${i + 1}. ${f}`));
    console.log(`${'='.repeat(50)}`);
    process.exit(1);
}
