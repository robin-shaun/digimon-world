/**
 * DIGIMON WORLD - 动画引擎单元测试 (Phase 13-②)
 *
 * 覆盖: FrameAnimator / TweenAnimator / DigimonAnimState / AnimManager
 *
 * 运行: node frontend/tests/test_animator.js
 * 浏览器: 直接打开 test-animator.html (自动运行, 显示结果)
 */

'use strict';

// ═══ Node.js shim: 模拟 browser window 对象 ═══
if (typeof window === 'undefined') {
    global.window = global;
}

// ═══ 加载 animator.js 源码 ═══
const fs = require('fs');
const path = require('path');
const animatorSrc = fs.readFileSync(path.join(__dirname, '..', 'animator.js'), 'utf-8');
eval(animatorSrc);

const ANIM = window.ANIM;
if (!ANIM) {
    console.error('FATAL: ANIM module failed to load');
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

function assertApprox(actual, expected, epsilon, msg) {
    const ok = Math.abs(actual - expected) <= epsilon;
    if (ok) {
        passed++;
    } else {
        failed++;
        failures.push(`${msg} (expected ${expected} ±${epsilon}, got ${actual})`);
        console.error(`  ❌ FAIL: ${msg} (expected ${expected} ±${epsilon}, got ${actual})`);
    }
}

function section(title) {
    console.log(`\n━━━ ${title} ━━━`);
}

// ═══════════════════════════════════════
//  Easing 函数测试
// ═══════════════════════════════════════

section('Easing');

assert(ANIM.Easing.linear(0) === 0, 'linear(0) = 0');
assert(ANIM.Easing.linear(1) === 1, 'linear(1) = 1');
assert(ANIM.Easing.linear(0.5) === 0.5, 'linear(0.5) = 0.5');

assert(ANIM.Easing.easeInQuad(0) === 0, 'easeInQuad(0) = 0');
assert(ANIM.Easing.easeInQuad(1) === 1, 'easeInQuad(1) = 1');
assert(ANIM.Easing.easeInQuad(0.5) === 0.25, 'easeInQuad(0.5) = 0.25');

assert(ANIM.Easing.easeOutQuad(0) === 0, 'easeOutQuad(0) = 0');
assert(ANIM.Easing.easeOutQuad(1) === 1, 'easeOutQuad(1) = 1');
assert(ANIM.Easing.easeOutQuad(0) === 0, 'easeOutQuad(0) = 0');
// easeOutQuad(0.5) = 0.5 * (2 - 0.5) = 0.5 * 1.5 = 0.75
assert(ANIM.Easing.easeOutQuad(0.5) === 0.75, 'easeOutQuad(0.5) = 0.75');

const breathe0 = ANIM.Easing.breathe(0);
assertApprox(breathe0, 0, 0.001, 'breathe(0) ≈ 0');

const breathe025 = ANIM.Easing.breathe(0.25);
assertApprox(breathe025, 1, 0.001, 'breathe(0.25) ≈ 1');

// ═══════════════════════════════════════
//  FrameAnimator 测试
// ═══════════════════════════════════════

section('FrameAnimator');

// 基本创建
const fa1 = new ANIM.FrameAnimator({ frames: 4, fps: 4, loop: true });
assert(fa1.frames === 4, 'FrameAnimator stores frames');
assert(fa1.fps === 4, 'FrameAnimator stores fps');
assert(fa1.loop === true, 'FrameAnimator stores loop');
assert(fa1.frame() === 0, 'FrameAnimator starts at frame 0');
assert(fa1.finished() === false, 'FrameAnimator not finished initially');

// 帧推进 — 250ms 在 4fps 下 = 1 帧
fa1.update(0.25);
assert(fa1.frame() === 1, 'after 0.25s → frame 1 (4fps)');

fa1.update(0.25);
assert(fa1.frame() === 2, 'after 0.5s → frame 2');

fa1.update(0.25);
assert(fa1.frame() === 3, 'after 0.75s → frame 3');

// 循环: 4fps × 4 frames = 1s 周期, 第 4 帧后应回到 0
fa1.update(0.25);
assert(fa1.frame() === 0, 'looping: frame 4 wraps to 0');
assert(fa1.finished() === false, 'looping anim never finishes');

// 不循环模式
const fa2 = new ANIM.FrameAnimator({ frames: 3, fps: 3, loop: false });
fa2.update(1.0); // 3 帧全过
assert(fa2.frame() === 2, 'non-loop: stays at last frame');
assert(fa2.finished() === true, 'non-loop: marks finished');

// 不循环不再推进
fa2.update(10);
assert(fa2.frame() === 2, 'non-loop: finished, no more updates');

// progress
const fa3 = new ANIM.FrameAnimator({ frames: 4, fps: 4, loop: true });
fa3.update(0.25);
assert(fa3.progress() === 1/3, 'progress: frame 1/3');

// reset
fa3.reset();
assert(fa3.frame() === 0, 'reset: frame back to 0');
assert(fa3.finished() === false, 'reset: finished cleared');

// ═══════════════════════════════════════
//  TweenAnimator 测试
// ═══════════════════════════════════════

section('TweenAnimator');

const tw1 = new ANIM.TweenAnimator({ duration: 1.0, easing: 'linear' });
assert(tw1.duration === 1.0, 'TweenAnimator stores duration');
assert(tw1.finished() === false, 'TweenAnimator not finished initially');
assertApprox(tw1.value(), 0, 0.001, 'TweenAnimator value at t=0');

tw1.update(0.3);
assertApprox(tw1.value(), 0.3, 0.001, 'linear tween at 0.3s');
assert(tw1.finished() === false, 'not finished at 0.3/1.0');

tw1.update(0.8); // total = 1.1, clamped to 1.0
assert(tw1.finished() === true, 'finished after duration');
assertApprox(tw1.value(), 1.0, 0.001, 'value clamped to 1.0');

// easeOutQuad
const tw2 = new ANIM.TweenAnimator({ duration: 0.5, easing: 'easeOutQuad' });
tw2.update(0.25); // t = 0.5
assertApprox(tw2.value(), 0.75, 0.001, 'easeOutQuad at half duration');

// yoyo 模式
const tw3 = new ANIM.TweenAnimator({ duration: 1.0, easing: 'linear', yoyo: true });
tw3.update(0.5); // t = 0.5 → yoyo → t' = 1.0 → linear(1) = 1
assertApprox(tw3.value(), 1.0, 0.001, 'yoyo: peak at t=0.5');

tw3.update(0.5); // t = 1.0 → yoyo → t' = 0.0 → linear(0) = 0
assertApprox(tw3.value(), 0.0, 0.001, 'yoyo: back to 0 at t=1.0');

// reset
tw3.reset();
assert(tw3.finished() === false, 'reset: finished cleared');
assertApprox(tw3.value(), 0, 0.001, 'reset: value back to 0');

// ═══════════════════════════════════════
//  DigimonAnimState 测试
// ═══════════════════════════════════════

section('DigimonAnimState');

const st = new ANIM.DigimonAnimState('testmon');
assert(st.name === 'testmon', 'DigimonAnimState stores name');

// 首次 setTarget → 瞬移 (无补间)
st.setTarget(100, 200);
assert(st.currentX === 100, 'first setTarget: currentX = targetX');
assert(st.currentY === 200, 'first setTarget: currentY = targetY');
assert(st.isMoving() === false, 'first setTarget: not moving (instant)');

// 第二次 setTarget (位置不同) → 启动补间
st.setTarget(200, 250);
assert(st.isMoving() === true, 'second setTarget: starts moving');
assert(st.fromX === 100, 'fromX preserved');
assert(st.fromY === 200, 'fromY preserved');

// 补间中途: update 0.1s 后检查插值
st.update(0.1);
assert(st.currentX > 100 && st.currentX < 200, 'interpolated X between from and target');
assert(st.currentY > 200 && st.currentY < 250, 'interpolated Y between from and target');

// moveAngle
const angle = st.moveAngle();
// from (100,200) to (200,250): dx=100, dy=50, angle ≈ atan2(50, 100) ≈ 0.4636
assertApprox(angle, 0.4636, 0.001, 'moveAngle correct');

// idleBounce: should be in range [-2, 2]
st.idleAnim.update(0.083); // advance idle anim a bit
const bounce = st.idleBounce();
assert(bounce >= -2 && bounce <= 2, `idleBounce in [-2,2], got ${bounce}`);

// idleScale: should be in range [0.97, 1.03]
const scale = st.idleScale();
assert(scale >= 0.97 && scale <= 1.03, `idleScale in [0.97,1.03], got ${scale}`);

// walkBounce: only when moving
const wb = st.walkBounce();
assert(wb >= 0 && wb <= 4, `walkBounce in [0,4], got ${wb}`);

// walkLean: only when moving
const wl = st.walkLean();
assert(wl >= -0.05 && wl <= 0.05, `walkLean in [-0.05,0.05], got ${wl}`);

// Complete the tween
st.update(1.0); // finish it
assert(st.isMoving() === false, 'after tween complete: not moving');
assert(st.currentX === 200, 'after tween: at targetX');
assert(st.currentY === 250, 'after tween: at targetY');

// walkBounce should be 0 when not moving
assert(st.walkBounce() === 0, 'walkBounce=0 when not moving');
assert(st.walkLean() === 0, 'walkLean=0 when not moving');

// 微小位移 (<1px) 不应触发补间
st.setTarget(200.5, 250.3);
assert(st.isMoving() === false, 'sub-pixel move: no tween');

// ═══════════════════════════════════════
//  AnimManager 测试
// ═══════════════════════════════════════

section('AnimManager');

const mgr = new ANIM.AnimManager();

// get 创建新状态
const agu = mgr.get('agumon');
assert(agu instanceof ANIM.DigimonAnimState, 'AnimManager.get creates DigimonAnimState');
assert(agu.name === 'agumon', 'created state has correct name');

// get 返回已存在的状态
const agu2 = mgr.get('agumon');
assert(agu === agu2, 'AnimManager.get returns same instance');

// 创建第二只
const gabu = mgr.get('gabumon');
assert(agu !== gabu, 'different digimon have different states');

// syncPositions
mgr.syncPositions([
    { name: 'agumon', position: { x: 50, y: 100 } },
    { name: 'gabumon', position: { x: 300, y: 400 } },
]);
// first sync: should instant-set (no previous position)
assert(agu.currentX === 50, 'syncPositions sets agumon X');
assert(gabu.currentX === 300, 'syncPositions sets gabumon X');

// second sync with new positions → should trigger move tween
mgr.syncPositions([
    { name: 'agumon', position: { x: 150, y: 200 } },
    { name: 'gabumon', position: { x: 350, y: 450 } },
]);
assert(agu.isMoving() === true, 're-sync triggers move tween');
assert(gabu.isMoving() === true, 're-sync triggers move tween');

// updateAll
mgr.updateAll(0.5);
assert(agu.currentX > 50 && agu.currentX <= 150, 'updateAll advances agumon');

// prune
mgr.syncPositions([{ name: 'agumon', position: { x: 500, y: 600 } }]);
mgr.prune(['agumon']);
assert(mgr.states['agumon'] !== undefined, 'prune keeps active digimon');
// gabumon should be removed since not in active list
assert(mgr.states['gabumon'] === undefined, 'prune removes inactive digimon');

// ═══════════════════════════════════════
//  边界情况测试
// ═══════════════════════════════════════

section('Edge cases');

// FrameAnimator with 1 frame
const faEdge = new ANIM.FrameAnimator({ frames: 1, fps: 10, loop: true });
faEdge.update(1);
assert(faEdge.frame() === 0, '1-frame anim: always frame 0');
assert(faEdge.progress() === 0, '1-frame: progress = 0');

// TweenAnimator with near-0 duration
const twEdge = new ANIM.TweenAnimator({ duration: 0.001 });
twEdge.update(0.001);
assert(twEdge.finished() === true, '0-duration tween: finished immediately');
assertApprox(twEdge.value(), 1, 0.001, '0-duration tween: value = 1');

// DigimonAnimState idleBounce when not initialized
const stFresh = new ANIM.DigimonAnimState('fresh');
// idleBounce should work even without setTarget
const fb = stFresh.idleBounce();
assert(fb >= -2 && fb <= 2, 'idleBounce works before setTarget');

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
