/**
 * DIGIMON WORLD - 粒子特效系统单元测试 (Phase 13-②)
 *
 * 覆盖: Particle / ParticleSystem / 预设 burst
 *
 * 运行: node frontend/tests/test_particles.js
 */

'use strict';

// ═══ Node.js shim: 模拟 browser window 对象 ═══
if (typeof window === 'undefined') {
    global.window = global;
}

// ═══ 加载 particles.js 源码 ═══
const fs = require('fs');
const path = require('path');
const particlesSrc = fs.readFileSync(path.join(__dirname, '..', 'particles.js'), 'utf-8');
eval(particlesSrc);

const PARTICLE = window.PARTICLE;
if (!PARTICLE) {
    console.error('FATAL: PARTICLE module failed to load');
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

// ═══════════════════════════════════════════
//  Particle 单元测试
// ═══════════════════════════════════════════

console.log('━━━ Particle ━━━');

(function () {
    const p = new PARTICLE.Particle({
        x: 100,
        y: 200,
        vx: 50,
        vy: -30,
        life: 1.0,
        color: '#ff0000',
        size: 4,
        gravity: 98,
        friction: 0.95,
    });

    assert(p.x === 100, 'Particle initial x');
    assert(p.y === 200, 'Particle initial y');
    assert(p.vx === 50, 'Particle initial vx');
    assert(p.vy === -30, 'Particle initial vy');
    assert(p.life === 1.0, 'Particle initial life');
    assert(p.maxLife === 1.0, 'Particle maxLife matches life');
    assert(p.color === '#ff0000', 'Particle color');
    assert(p.size === 4, 'Particle size');
    assert(p.gravity === 98, 'Particle gravity');
    assert(p.friction === 0.95, 'Particle friction');
    assert(p._dead === false, 'Particle not dead initially');
    assert(p.alpha() === 1.0, 'Particle alpha() = 1.0 at full life');
})();

(function () {
    // Update: particle should move and life should decrease
    const p = new PARTICLE.Particle({
        x: 0, y: 0,
        vx: 100, vy: 0,
        life: 1.0,
        gravity: 0,
        friction: 1.0,
    });
    p.update(0.1);
    assertApprox(p.x, 10, 0.1, 'Particle moves in x after 0.1s');
    assert(p.y === 0, 'Particle y unchanged with no vy/gravity');
    assertApprox(p.life, 0.9, 0.01, 'Particle life decreases by dt/maxLife');
    assert(p._dead === false, 'Particle still alive after partial life');
})();

(function () {
    // Gravity affects vy
    const p = new PARTICLE.Particle({
        x: 0, y: 0,
        vx: 0, vy: 0,
        life: 1.0,
        gravity: 100,
        friction: 1.0,
    });
    p.update(0.5);
    assert(p.vy > 0, 'Gravity makes vy positive');
    assertApprox(p.y, 25, 1.0, 'Particle falls with gravity');  // vy=50 after 0.5s, Δy=50*0.5=25
})();

(function () {
    // Particle dies when life runs out
    const p = new PARTICLE.Particle({
        x: 0, y: 0,
        vx: 0, vy: 0,
        life: 0.1,
    });
    p.update(0.2); // dt > life
    assert(p._dead === true, 'Particle dies when life exhausted');
    // life goes below 0
    assert(p.life < 0, 'Particle life goes negative when dead');
})();

(function () {
    // alpha() fades to 0
    const p = new PARTICLE.Particle({
        x: 0, y: 0, vx: 0, vy: 0,
        life: 1.0,
    });
    assert(p.alpha() === 1.0, 'Alpha at full life');
    p.update(0.5);
    assertApprox(p.alpha(), 0.5, 0.01, 'Alpha at half life');
    p.update(0.5);
    assert(p.alpha() <= 0.01 || p._dead, 'Alpha near 0 at end of life');
})();

// ═══════════════════════════════════════════
//  ParticleSystem 单元测试
// ═══════════════════════════════════════════

console.log('━━━ ParticleSystem ━━━');

(function () {
    const ps = new PARTICLE.ParticleSystem();
    assert(ps.alive === 0, 'New ParticleSystem has 0 particles');
    assert(Array.isArray(ps._debugParticles()), '_debugParticles returns array');
    assert(ps._debugParticles().length === 0, '_debugParticles empty initially');
})();

(function () {
    // burst creates particles
    const ps = new PARTICLE.ParticleSystem();
    ps.burst(100, 100, { count: 10 });
    assert(ps.alive === 10, 'burst(10) creates 10 particles');
    const pts = ps._debugParticles();
    assert(pts.length === 10, '_debugParticles length matches');
    // All particles should be near (100, 100)
    for (const p of pts) {
        assert(p.x === 100, 'Particle spawned at burst x');
        assert(p.y === 100, 'Particle spawned at burst y');
    }
})();

(function () {
    // burst with custom config
    const ps = new PARTICLE.ParticleSystem();
    ps.burst(50, 60, { color: '#00ff00', accent: '#008800', count: 5, life: 2.0, size: 5, spread: 100, gravity: 50 });
    assert(ps.alive === 5, 'Custom burst count');
    const pts = ps._debugParticles();
    // Check colors are either main or accent
    for (const p of pts) {
        const ok = p.color === '#00ff00' || p.color === '#008800';
        assert(ok, `Particle color is main or accent (got ${p.color})`);
    }
})();

(function () {
    // update removes dead particles
    const ps = new PARTICLE.ParticleSystem();
    ps.burst(0, 0, { count: 5, life: 0.1 });
    assert(ps.alive === 5, '5 alive after burst');
    // Update enough to kill all
    ps.update(0.2);
    assert(ps.alive === 0, 'All particles dead after life exhausted');
    assert(ps._debugParticles().length === 0, 'Array emptied after all dead');
})();

(function () {
    // update with partial death
    const ps = new PARTICLE.ParticleSystem();
    ps.burst(0, 0, { count: 10, life: 1.0 });
    ps.update(0.5);
    // Some should still be alive (life varies 0.6-1.0)
    assert(ps.alive > 0, 'Some particles alive after half-life');
    assert(ps.alive <= 10, 'No more than burst count alive');
})();

(function () {
    // clear empties everything
    const ps = new PARTICLE.ParticleSystem();
    ps.burst(0, 0, { count: 20 });
    assert(ps.alive === 20, '20 alive before clear');
    ps.clear();
    assert(ps.alive === 0, '0 alive after clear');
    assert(ps._debugParticles().length === 0, 'Array empty after clear');
})();

(function () {
    // draw should not throw (mock ctx)
    const ps = new PARTICLE.ParticleSystem();
    ps.burst(100, 100, { count: 3, life: 1.0 });
    const mockCtx = {
        _calls: [],
        beginPath: function () { this._calls.push('beginPath'); },
        arc: function (x, y, r, s, e, ccw) { this._calls.push('arc'); },
        fill: function () { this._calls.push('fill'); },
    };
    // draw should work without throwing
    let threw = false;
    try {
        ps.draw(mockCtx);
    } catch (e) {
        threw = true;
        console.error('draw threw:', e);
    }
    assert(!threw, 'draw() does not throw');
    assert(mockCtx._calls.length > 0, 'draw() makes canvas calls');
})();

// ═══════════════════════════════════════════
//  预设方法
// ═══════════════════════════════════════════

console.log('━━━ Presets ━━━');

(function () {
    const ps = new PARTICLE.ParticleSystem();
    ps.evolution(200, 300);
    assert(ps.alive === 30, 'evolution() spawns 30 particles');
    ps.clear();
})();

(function () {
    const ps = new PARTICLE.ParticleSystem();
    ps.battle(200, 300);
    assert(ps.alive === 15, 'battle() spawns 15 particles');
    ps.clear();
})();

(function () {
    const ps = new PARTICLE.ParticleSystem();
    ps.poke(200, 300);
    assert(ps.alive === 8, 'poke() spawns 8 particles');
    ps.clear();
})();

(function () {
    const ps = new PARTICLE.ParticleSystem();
    ps.heal(200, 300);
    assert(ps.alive === 20, 'heal() spawns 20 particles');
    ps.clear();
})();

// ═══════════════════════════════════════════
//  PRESETS 常量
// ═══════════════════════════════════════════

console.log('━━━ PRESETS ━━━');

(function () {
    const presets = PARTICLE.PRESETS;
    assert(typeof presets === 'object', 'PRESETS is an object');
    assert(presets.evolution !== undefined, 'PRESETS.evolution exists');
    assert(presets.battle !== undefined, 'PRESETS.battle exists');
    assert(presets.poke !== undefined, 'PRESETS.poke exists');
    assert(presets.heal !== undefined, 'PRESETS.heal exists');

    assert(presets.evolution.color === '#ffd700', 'evolution color is gold');
    assert(presets.battle.color === '#ff4444', 'battle color is red');
    assert(presets.poke.color === '#ffffff', 'poke color is white');
    assert(presets.heal.color === '#44ff88', 'heal color is green');

    assert(presets.evolution.count === 30, 'evolution count');
    assert(presets.battle.count === 15, 'battle count');
    assert(presets.poke.count === 8, 'poke count');
    assert(presets.heal.count === 20, 'heal count');
})();

// ═══════════════════════════════════════════
//  边界情况
// ═══════════════════════════════════════════

console.log('━━━ Edge cases ━━━');

(function () {
    // burst with 0 count
    const ps = new PARTICLE.ParticleSystem();
    ps.burst(0, 0, { count: 0 });
    assert(ps.alive === 0, 'burst(0) creates no particles');
})();

(function () {
    // burst with negative life → dies immediately
    const ps = new PARTICLE.ParticleSystem();
    ps.burst(0, 0, { count: 5, life: 0.001 });
    ps.update(0.01);
    assert(ps.alive === 0, 'Particles with tiny life die quickly');
})();

(function () {
    // large burst
    const ps = new PARTICLE.ParticleSystem();
    ps.burst(0, 0, { count: 1000 });
    assert(ps.alive === 1000, 'Large burst (1000) works');
    ps.clear();
})();

(function () {
    // multiple bursts accumulate
    const ps = new PARTICLE.ParticleSystem();
    ps.burst(0, 0, { count: 5, life: 10 });
    ps.burst(0, 0, { count: 5, life: 10 });
    assert(ps.alive === 10, 'Multiple bursts accumulate');
    ps.clear();
})();

(function () {
    // draw empty system
    const ps = new PARTICLE.ParticleSystem();
    const mockCtx = {
        _calls: [],
        beginPath: function () { this._calls.push('beginPath'); },
        arc: function () { this._calls.push('arc'); },
        fill: function () { this._calls.push('fill'); },
    };
    let threw = false;
    try { ps.draw(mockCtx); } catch (e) { threw = true; }
    assert(!threw, 'draw() on empty system does not throw');
    assert(mockCtx._calls.length === 0, 'draw() on empty system makes no calls');
})();

// ═══════════════════════════════════════════
//  结果
// ═══════════════════════════════════════════

console.log('');
console.log('='.repeat(50));
if (failed === 0) {
    console.log(`✅ ALL ${passed} TESTS PASSED`);
} else {
    console.log(`❌ ${failed} FAILED, ${passed} PASSED`);
    console.log('Failures:');
    failures.forEach((f) => console.log('  - ' + f));
}
console.log('='.repeat(50));

process.exit(failed > 0 ? 1 : 0);
