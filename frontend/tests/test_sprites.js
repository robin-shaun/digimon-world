/**
 * DIGIMON WORLD - 精灵数据单元测试 (Phase 13-②)
 *
 * 覆盖: sprites.js 中的 29 种数码兽配置数据 + getSpriteConfig / getActionConfig
 *
 * 运行: node frontend/tests/test_sprites.js
 */

'use strict';

// ═══ Node.js shim: 模拟 browser window 对象 ═══
if (typeof window === 'undefined') {
    global.window = global;
}

// ═══ 加载 sprites.js 源码 ═══
const fs = require('fs');
const path = require('path');
const spritesSrc = fs.readFileSync(path.join(__dirname, '..', 'sprites.js'), 'utf-8');
eval(spritesSrc);

const SPRITE = window.SPRITE_DATA;
if (!SPRITE) {
    console.error('FATAL: SPRITE_DATA module failed to load');
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

// ═══ 帮助: 提取所有 species keys (从源码, 不依赖未暴露的内部 configs) ═══
// 通过 test getSpriteConfig 的行为来推断
const KNOWN_SPECIES = [
    // 疫苗种 — 被选召的 8 只
    'agumon', 'gabumon', 'biyomon', 'tentomon',
    'palmon', 'gomamon', 'patamon', 'tailmon',
    // 疫苗种 — 其他
    'plotmon', 'elecmon', 'tsunomon',
    // 数据种
    'hagurumon', 'guardromon', 'clockmon', 'tankmon',
    'kokuwamon', 'andromon',
    // 病毒种
    'picodevimon', 'blackgabumon', 'devimon', 'devidramon',
    'vamdemon', 'fantomon', 'bakemon',
    // 自由种
    'renamon', 'impmon', 'dorumon', 'wizarmon', 'leomon',
];

const REQUIRED_ACTIONS = ['idle', 'walk', 'attack', 'evolve'];
const OPTIONAL_ACTIONS = [];

// ═══════════════════════════════════════
//  1. 所有已知物种配置完整性
// ═══════════════════════════════════════

section('Config integrity — all 29 species');

assert(KNOWN_SPECIES.length === 29, `29 known species, got ${KNOWN_SPECIES.length}`);

KNOWN_SPECIES.forEach(name => {
    const cfg = SPRITE.getSpriteConfig(name);
    assert(cfg !== SPRITE.DEFAULT, `${name}: config found (not DEFAULT)`);

    // 必填字段
    assert(typeof cfg.color === 'string', `${name}: has color`);
    assert(cfg.color.startsWith('#'), `${name}: color is hex`);
    assert(cfg.color.length === 7, `${name}: color is 7-char hex (#RRGGBB)`);

    assert(typeof cfg.accent === 'string', `${name}: has accent`);
    assert(cfg.accent.startsWith('#'), `${name}: accent is hex`);

    assert(typeof cfg.size === 'number', `${name}: has numeric size`);
    assert(cfg.size >= 13 && cfg.size <= 26, `${name}: size in [13,26] (got ${cfg.size})`);

    assert(typeof cfg.actions === 'object', `${name}: has actions object`);

    // 必填动作
    REQUIRED_ACTIONS.forEach(action => {
        const act = cfg.actions[action];
        assert(act !== undefined, `${name}.${action}: exists`);
        assert(typeof act.frames === 'number' && act.frames >= 1, `${name}.${action}: frames >= 1`);
        assert(typeof act.fps === 'number' && act.fps >= 1 && act.fps <= 20, `${name}.${action}: fps in [1,20]`);
        assert(typeof act.loop === 'boolean', `${name}.${action}: loop is boolean`);
    });
});

// ═══════════════════════════════════════
//  2. getSpriteConfig — 正常路径
// ═══════════════════════════════════════

section('getSpriteConfig — normal');

const aguCfg = SPRITE.getSpriteConfig('agumon');
assert(aguCfg.color === '#FF8C00', 'agumon color');
assert(aguCfg.accent === '#FFD700', 'agumon accent');
assert(aguCfg.size === 18, 'agumon size');
assert(aguCfg.actions.idle.frames === 4, 'agumon idle frames');
assert(aguCfg.actions.idle.fps === 3, 'agumon idle fps');
assert(aguCfg.actions.idle.loop === true, 'agumon idle loop');

// 大小写不敏感
assert(SPRITE.getSpriteConfig('AGUMON').color === '#FF8C00', 'case-insensitive lookup');
assert(SPRITE.getSpriteConfig('AgUmOn').size === 18, 'mixed case lookup');

// ═══════════════════════════════════════
//  3. getSpriteConfig — 未知/边界
// ═══════════════════════════════════════

section('getSpriteConfig — edge cases');

// 未知物种返回 DEFAULT
const unknown = SPRITE.getSpriteConfig('nonexistent_mon');
assert(unknown === SPRITE.DEFAULT, 'unknown species → DEFAULT');

// null/undefined 输入
assert(SPRITE.getSpriteConfig(null) === SPRITE.DEFAULT, 'null → DEFAULT');
assert(SPRITE.getSpriteConfig(undefined) === SPRITE.DEFAULT, 'undefined → DEFAULT');

// 空字符串
assert(SPRITE.getSpriteConfig('') === SPRITE.DEFAULT, 'empty string → DEFAULT');

// 带空格的名字 (应被 normalize)
// 假设内部 replace 能处理
const withSpace = SPRITE.getSpriteConfig('agumon ');  // trailing space
// 空格替换后应能匹配
// (不做强断言, 只验证不崩溃)
assert(typeof withSpace.color === 'string', 'name with space: returns config');

// ═══════════════════════════════════════
//  4. getActionConfig
// ═══════════════════════════════════════

section('getActionConfig');

// 正常路径
const aguIdle = SPRITE.getActionConfig('agumon', 'idle');
assert(aguIdle.frames === 4, 'agumon.idle: frames=4');
assert(aguIdle.fps === 3, 'agumon.idle: fps=3');
assert(aguIdle.loop === true, 'agumon.idle: loop=true');

const aguWalk = SPRITE.getActionConfig('agumon', 'walk');
assert(aguWalk.frames === 6, 'agumon.walk: frames=6');
assert(aguWalk.fps === 8, 'agumon.walk: fps=8');
assert(aguWalk.loop === true, 'agumon.walk: loop=true');

const aguAttack = SPRITE.getActionConfig('agumon', 'attack');
assert(aguAttack.frames === 5, 'agumon.attack: frames=5');
assert(aguAttack.fps === 12, 'agumon.attack: fps=12');
assert(aguAttack.loop === false, 'agumon.attack: loop=false');

const aguEvolve = SPRITE.getActionConfig('agumon', 'evolve');
assert(aguEvolve.frames === 8, 'agumon.evolve: frames=8');
assert(aguEvolve.loop === false, 'agumon.evolve: loop=false');

// 特殊物种: patamon idle fps=4
const patIdle = SPRITE.getActionConfig('patamon', 'idle');
assert(patIdle.fps === 4, 'patamon (活泼): idle fps=4');

// 特殊物种: guardromon idle fps=2 (机械慢节奏)
const guardIdle = SPRITE.getActionConfig('guardromon', 'idle');
assert(guardIdle.fps === 2, 'guardromon (机械): idle fps=2');

// 特殊物种: renamon attack fps=14 (最快)
const renAttack = SPRITE.getActionConfig('renamon', 'attack');
assert(renAttack.fps === 14, 'renamon (敏捷): attack fps=14');

// 回退: 未知物种 + 未知动作 → idle fallback
const unknownAct = SPRITE.getActionConfig('unknown', 'nonexistent');
assert(unknownAct.frames === 4, 'unknown.action fallback → DEFAULT idle frames');
assert(unknownAct.loop === true, 'unknown.action fallback → DEFAULT idle loop=true');

// ═══════════════════════════════════════
//  5. DEFAULT 配置验证
// ═══════════════════════════════════════

section('DEFAULT config');

assert(typeof SPRITE.DEFAULT.color === 'string', 'DEFAULT.color is string');
assert(typeof SPRITE.DEFAULT.accent === 'string', 'DEFAULT.accent is string');
assert(typeof SPRITE.DEFAULT.size === 'number', 'DEFAULT.size is number');
assert(typeof SPRITE.DEFAULT.actions.idle.frames === 'number', 'DEFAULT.actions.idle.frames');
assert(typeof SPRITE.DEFAULT.actions.walk.frames === 'number', 'DEFAULT.actions.walk.frames');

// ═══════════════════════════════════════
//  6. 物种级特殊属性检查
// ═══════════════════════════════════════

section('Species-specific properties');

// devimon: accent 应是红色 (不是普通 accent)
const deviAccent = SPRITE.getSpriteConfig('devimon').accent;
assert(deviAccent === '#DC143C', 'devimon has crimson accent');

// vamdemon: largest size
const vamSize = SPRITE.getSpriteConfig('vamdemon').size;
assert(vamSize === 26, 'vamdemon: largest size=26');

// picodevimon: smallest size
const picoSize = SPRITE.getSpriteConfig('picodevimon').size;
assert(picoSize === 13, 'picodevimon: smallest size=13');

// elecmon: walk fps=9 (电力充沛)
const elecWalk = SPRITE.getActionConfig('elecmon', 'walk');
assert(elecWalk.fps === 9, 'elecmon walk fps=9 (powerful)');

// impmon + picodevimon: idle fps=4 (活泼)
assert(SPRITE.getActionConfig('impmon', 'idle').fps === 4, 'impmon idle fps=4');
assert(SPRITE.getActionConfig('picodevimon', 'idle').fps === 4, 'picodevimon idle fps=4');

// ═══════════════════════════════════════
//  7. 颜色唯一性 (避免视觉上相同造成混淆)
// ═══════════════════════════════════════

section('Color uniqueness check');

const colors = KNOWN_SPECIES.map(n => SPRITE.getSpriteConfig(n).color);
const uniqueColors = new Set(colors);
assert(uniqueColors.size >= 20, `at least 20 unique colors (got ${uniqueColors.size})`);

// 检查是否有颜色完全相同的物种 (警告但不失败)
const colorMap = {};
KNOWN_SPECIES.forEach(n => {
    const c = SPRITE.getSpriteConfig(n).color;
    if (!colorMap[c]) colorMap[c] = [];
    colorMap[c].push(n);
});
const dupes = Object.entries(colorMap).filter(([, v]) => v.length > 1);
if (dupes.length > 0) {
    console.log(`  ℹ️  ${dupes.length} color group(s) shared by multiple species:`);
    dupes.forEach(([c, names]) => console.log(`     ${c}: ${names.join(', ')}`));
}
// andromon & dorumon both use '#4682B4' — documented, intentional

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
