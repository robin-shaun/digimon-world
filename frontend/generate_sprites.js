#!/usr/bin/env node
/**
 * generate_sprites.js — Render all procedural Digimon sprites to 512×512 PNGs.
 *
 * Uses the existing DRAW_FUNCS from sprites.js with the Node.js 'canvas'
 * package, producing high-res PNGs for the image-based sprite system.
 *
 * Usage:
 *   cd frontend && node generate_sprites.js
 *
 * Output:
 *   frontend/sprites/agumon.png, gabumon.png, ... (37+ files at 512×512)
 */

const { createCanvas } = require('canvas');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

// ── Output directory ──────────────────────────────────────────────────
const OUT_DIR = path.join(__dirname, 'sprites');
if (!fs.existsSync(OUT_DIR)) {
    fs.mkdirSync(OUT_DIR, { recursive: true });
}

// ── Render size ───────────────────────────────────────────────────────
const SIZE = 512;
const SCALE = SIZE / 128; // draw functions use a 128×128 coordinate system

// ── Load sprites.js into a Node.js context ────────────────────────────
//
// sprites.js is an IIFE that assigns to `window.SPRITE_PIXEL`.  We provide
// a Node-compatible mock so the draw functions are accessible.
function loadSpriteModule() {
    const srcPath = path.join(__dirname, 'sprites.js');
    let src = fs.readFileSync(srcPath, 'utf-8');

    // -- Patch CanvasRenderingContext2D.roundRect ------------------------
    // The canvas npm package's CanvasRenderingContext2D does not implement
    // roundRect (it's a recent browser API).  Polyfill it.
    const roundRectPolyfill = `
if (typeof CanvasRenderingContext2D !== 'undefined' && !CanvasRenderingContext2D.prototype.roundRect) {
    CanvasRenderingContext2D.prototype.roundRect = function(x, y, w, h, radii) {
        let r = typeof radii === 'number' ? radii : (radii && radii[0]) || 0;
        if (typeof r === 'undefined') r = 0;
        this.beginPath();
        this.moveTo(x + r, y);
        this.lineTo(x + w - r, y);
        this.arcTo(x + w, y, x + w, y + r, r);
        this.lineTo(x + w, y + h - r);
        this.arcTo(x + w, y + h, x + w - r, y + h, r);
        this.lineTo(x + r, y + h);
        this.arcTo(x, y + h, x, y + h - r, r);
        this.lineTo(x, y + r);
        this.arcTo(x, y, x + r, y, r);
        this.closePath();
    };
}
`;

    // -- Mock browser globals -------------------------------------------
    const sandbox = {
        // Minimal document mock to satisfy document.createElement('canvas')
        document: {
            createElement(tag) {
                if (tag === 'canvas') {
                    // Return a real node-canvas — draw functions render into it
                    return createCanvas(SIZE, SIZE);
                }
                return {};
            },
        },
        window: {},
        console: console,
        CanvasRenderingContext2D: require('canvas').CanvasRenderingContext2D,
    };
    sandbox.window = sandbox; // window === global-ish

    const context = vm.createContext(sandbox);

    // Run the polyfill in the sandbox
    vm.runInContext(roundRectPolyfill, context);

    // Run sprites.js in the sandbox
    vm.runInContext(src, context);

    return sandbox.window.SPRITE_PIXEL;
}

// ── Render each species ───────────────────────────────────────────────

const SPRITE_PIXEL = loadSpriteModule();

if (!SPRITE_PIXEL || !SPRITE_PIXEL.DRAW_FUNCS) {
    console.error('ERROR: Failed to load DRAW_FUNCS from sprites.js');
    console.error('SPRITE_PIXEL keys:', SPRITE_PIXEL ? Object.keys(SPRITE_PIXEL) : 'null');
    process.exit(1);
}

const DRAW_FUNCS = SPRITE_PIXEL.DRAW_FUNCS;
const speciesList = Object.keys(DRAW_FUNCS).filter(k => k !== '_default');

console.log(`Found ${speciesList.length} species to render at ${SIZE}×${SIZE}`);
console.log('');

let generated = 0;
let errors = 0;

for (const species of speciesList) {
    const drawFn = DRAW_FUNCS[species];
    if (typeof drawFn !== 'function') {
        console.error(`  SKIP ${species}: not a function`);
        errors++;
        continue;
    }

    const canvas = createCanvas(SIZE, SIZE);
    const ctx = canvas.getContext('2d');

    try {
        drawFn(ctx, SCALE);
        const buffer = canvas.toBuffer('image/png');
        const outPath = path.join(OUT_DIR, `${species}.png`);
        fs.writeFileSync(outPath, buffer);
        console.log(`  ✓ ${species}.png`);
        generated++;
    } catch (err) {
        console.error(`  ✗ ${species}: ${err.message}`);
        errors++;
    }
}

console.log('');
console.log(`Done. Generated ${generated} PNGs, ${errors} errors.`);
console.log(`Output: ${OUT_DIR}/`);

process.exit(errors > 0 ? 1 : 0);
