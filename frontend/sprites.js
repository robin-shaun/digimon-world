/**
 * DIGIMON WORLD - Procedural Anime Sprite System
 *
 * REPLACES all text-based pixel grids with Canvas 2D procedural drawing.
 * Each Digimon species gets a draw(ctx, size) function producing anime-style
 * characters: bold outlines, cel shading, expressive eyes, unique silhouette.
 *
 * Every shape has a matching stroke (outline). Eyes are BIG and expressive.
 * Bodies are round and cute (chibi/Q-version proportions).
 */

window.SPRITE_PIXEL = (function () {
    'use strict';

    // ── Constants ──────────────────────────────────────────────────
    const O  = '#1a1a2e';  // outline
    const W  = '#FFFFFF';  // white
    const B  = '#000000';  // black
    const H  = '#FFF8DC';  // highlight
    const LW = 3;            // default line width
    const SZ = 256;          // target canvas size

    // ── Image-based sprite loader (PNG pre-renders at 512×512) ──────

    const IMG_BASE = 'sprites/';          // path to PNG directory
    const IMG_SZ  = 512;                  // native PNG resolution

    const imageCache       = new Map();   // species → Image (loaded)
    const loadingPromises  = new Map();   // species → Promise<Image>

    /** Start async loading of a PNG sprite. Returns a Promise<Image>. */
    function loadImage(species) {
        if (imageCache.has(species)) return Promise.resolve(imageCache.get(species));
        if (loadingPromises.has(species)) return loadingPromises.get(species);

        const img = new Image();
        const promise = new Promise((resolve, reject) => {
            img.onload = () => {
                imageCache.set(species, img);
                loadingPromises.delete(species);
                resolve(img);
            };
            img.onerror = () => {
                loadingPromises.delete(species);
                reject(new Error('Failed to load ' + species));
            };
            img.src = IMG_BASE + species + '.png';
        });
        loadingPromises.set(species, promise);
        return promise;
    }

    /** Synchronous lookup: returns loaded Image or null. */
    function getLoadedImage(species) {
        const img = imageCache.get(species);
        if (img && img.complete && img.naturalWidth > 0 && img.naturalHeight > 0) {
            return img;
        }
        return null;
    }

    /** Kick off async preload for a single species. No-op if already loaded/loading. */
    function preloadImage(species) {
        if (!imageCache.has(species) && !loadingPromises.has(species)) {
            loadImage(species).catch(() => {});
        }
    }

    // ── Helper drawing functions ────────────────────────────────────

    /** Set common canvas state for crisp anime look */
    function prepCtx(ctx) {
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
        ctx.imageSmoothingEnabled = true;
    }

    /** Draw a filled AND stroked shape in one go */
    function fillStroke(ctx, fillStyle, strokeStyle, lw) {
        ctx.fillStyle = fillStyle;
        ctx.fill();
        ctx.strokeStyle = strokeStyle || O;
        ctx.lineWidth = lw || LW;
        ctx.stroke();
    }

    /**
     * Enhanced anime-style eye with species-specific shapes.
     * @param {CanvasRenderingContext2D} ctx
     * @param {number} cx - center x
     * @param {number} cy - center y
     * @param {string} irisColor
     * @param {number} eyeRadius
     * @param {number} pupilRadius
     * @param {Object} [opts] - shape:'round'|'narrow'|'slit'|'huge', gazeX,gazeY (0-1 offset), angle (radians)
     */
    function drawEye(ctx, cx, cy, irisColor, eyeRadius, pupilRadius, opts) {
        const er = eyeRadius || 8;
        const pr = pupilRadius || 3;
        const shape = (opts && opts.shape) || 'round';
        const gazeX = (opts && opts.gazeX) || 0;
        const gazeY = (opts && opts.gazeY) || 0;
        const angle = (opts && opts.angle) || 0;

        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(angle);

        // Determine eye shape ratios
        let sx = er, sy = er * 1.35;
        if (shape === 'narrow') { sx = er * 0.6; sy = er * 1.5; }
        else if (shape === 'slit') { sx = er * 0.5; sy = er * 1.4; }
        else if (shape === 'huge') { sx = er * 1.15; sy = er * 1.5; }

        // ── LAYER 1: Sclera (white oval) ──────────────────────────
        ctx.beginPath();
        ctx.ellipse(0, 0, sx, sy, 0, 0, Math.PI * 2);
        fillStroke(ctx, W, O, 2);

        // ── LAYER 2: Colored iris (slightly offset for gaze) ──────
        const irisX = gazeX * er * 0.25;
        const irisY = 1 + gazeY * er * 0.25;
        ctx.beginPath();
        if (shape === 'slit') {
            // Vertical slit iris
            ctx.ellipse(irisX, irisY, er * 0.35, er * 0.65, 0, 0, Math.PI * 2);
        } else {
            ctx.arc(irisX, irisY, er * 0.7, 0, Math.PI * 2);
        }
        fillStroke(ctx, irisColor, O, 1.5);

        // ── LAYER 3: Black pupil ──────────────────────────────────
        ctx.beginPath();
        if (shape === 'slit') {
            ctx.ellipse(irisX, irisY, pr * 0.5, pr * 1.1, 0, 0, Math.PI * 2);
        } else {
            ctx.arc(irisX, irisY, pr, 0, Math.PI * 2);
        }
        ctx.fillStyle = B;
        ctx.fill();

        // ── LAYER 4a: Main white highlight (top-right of pupil) ───
        ctx.fillStyle = W;
        ctx.beginPath();
        ctx.arc(irisX - pr * 0.6, irisY - pr * 0.6, pr * 0.5, 0, Math.PI * 2);
        ctx.fill();

        // ── LAYER 4b: Secondary highlight (bottom-left, wet-eye) ──
        ctx.beginPath();
        ctx.arc(irisX + pr * 0.55, irisY + pr * 0.35, pr * 0.2, 0, Math.PI * 2);
        ctx.fill();

        // ── LAYER 5: Eyelid arc (top lid line for expression) ─────
        ctx.strokeStyle = O;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.ellipse(0, -sy * 0.15, sx * 1.05, sy * 0.4, 0, Math.PI * 1.05, Math.PI * 1.95);
        ctx.stroke();

        ctx.restore();
    }

    /**
     * Draw a body with vertical gradient shading (light top → dark bottom).
     */
    function drawBodyGradient(ctx, x, y, rx, ry, colorTop, colorBottom, rotation) {
        const grad = ctx.createLinearGradient(x, y - ry, x, y + ry);
        grad.addColorStop(0, colorTop);
        grad.addColorStop(1, colorBottom);
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.ellipse(x, y, rx, ry, rotation || 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = O;
        ctx.lineWidth = 3;
        ctx.stroke();
    }

    /**
     * Draw enhanced shadow blob with gradient.
     */
    function shadowBlobGrad(ctx, cx, cy, rx, ry) {
        ctx.save();
        const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.max(rx, ry));
        grad.addColorStop(0, 'rgba(0,0,0,0.35)');
        grad.addColorStop(1, 'rgba(0,0,0,0.05)');
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.ellipse(cx + 4, cy + 4, rx, ry, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
    }

    /** Draw rounded body shadow underneath a shape */
    function shadowBlob(ctx, cx, cy, rx, ry) {
        ctx.save();
        ctx.globalAlpha = 0.3;
        ctx.fillStyle = 'rgba(0,0,0,0.25)';
        ctx.beginPath();
        ctx.ellipse(cx + 4, cy + 4, rx, ry, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
    }

    /* ═══════════════════════════════════════════════════════
       SPECIES DRAWING FUNCTIONS
       Each: unique silhouette, 2+ shade levels, bold outlines,
       anime eyes, shadows. Draw order: back to front.
       ═══════════════════════════════════════════════════════ */

    function drawAgumon(ctx, s) {
        prepCtx(ctx);

        // ── POSE: weight on right leg, head tilted left ──
        ctx.save();
        ctx.translate(-2 * s, 0);
        const bodyCx = 64, bodyCy = 80;

        // Shadow
        shadowBlobGrad(ctx, (bodyCx + 2) * s, 118 * s, 24 * s, 10 * s);

        // TAIL — thick curved shape behind body
        ctx.fillStyle = '#E07000';
        ctx.beginPath();
        ctx.moveTo(40 * s, 85 * s);
        ctx.bezierCurveTo(15 * s, 75 * s, 8 * s, 95 * s, 18 * s, 108 * s);
        ctx.bezierCurveTo(28 * s, 118 * s, 42 * s, 100 * s, 40 * s, 85 * s);
        ctx.fill();
        ctx.strokeStyle = O; ctx.lineWidth = 2.5 * s; ctx.stroke();

        // LEGS — short cylinders (weight shift: left leg slightly higher)
        ctx.fillStyle = '#FF8C00';
        ctx.beginPath();
        ctx.roundRect(48 * s, 98 * s, 14 * s, 18 * s, 5 * s);
        ctx.fill();
        ctx.strokeStyle = O; ctx.lineWidth = 2.5 * s; ctx.stroke();
        // Left foot claw (3 toes)
        ctx.fillStyle = '#E06040';
        ctx.beginPath();
        ctx.roundRect(44 * s, 113 * s, 22 * s, 7 * s, 3 * s);
        ctx.fill();
        ctx.strokeStyle = O; ctx.lineWidth = 2 * s; ctx.stroke();
        // Toe claws
        ctx.fillStyle = '#FFE4B5';
        for (let t = 0; t < 3; t++) {
            ctx.beginPath();
            ctx.arc((46 + t * 7) * s, 118 * s, 2.5 * s, 0, Math.PI * 2);
            ctx.fill();
            ctx.strokeStyle = O; ctx.lineWidth = 1.5 * s; ctx.stroke();
        }

        // Right leg
        ctx.fillStyle = '#CC6600';
        ctx.beginPath();
        ctx.roundRect(66 * s, 100 * s, 14 * s, 18 * s, 5 * s);
        ctx.fill();
        ctx.strokeStyle = O; ctx.lineWidth = 2.5 * s; ctx.stroke();
        ctx.fillStyle = '#E06040';
        ctx.beginPath();
        ctx.roundRect(62 * s, 115 * s, 22 * s, 7 * s, 3 * s);
        ctx.fill();
        ctx.strokeStyle = O; ctx.lineWidth = 2 * s; ctx.stroke();
        ctx.fillStyle = '#FFE4B5';
        for (let t = 0; t < 3; t++) {
            ctx.beginPath();
            ctx.arc((64 + t * 7) * s, 120 * s, 2.5 * s, 0, Math.PI * 2);
            ctx.fill();
            ctx.strokeStyle = O; ctx.lineWidth = 1.5 * s; ctx.stroke();
        }

        // BODY — round orange torso with gradient
        drawBodyGradient(ctx, bodyCx * s, bodyCy * s, 26 * s, 30 * s, '#FFAA33', '#E06800');

        // BELLY — lighter yellow oval
        ctx.fillStyle = '#FFD700';
        ctx.beginPath();
        ctx.ellipse(bodyCx * s, (bodyCy + 4) * s, 19 * s, 21 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FFD700', O, 2 * s);

        // Belly center line
        ctx.strokeStyle = '#E0A800';
        ctx.lineWidth = 1.5 * s;
        ctx.beginPath();
        ctx.moveTo(bodyCx * s, 68 * s);
        ctx.lineTo(bodyCx * s, 100 * s);
        ctx.stroke();

        // ARMS — asymmetrical (right arm raised for dynamic pose)
        // Left arm (lower)
        ctx.fillStyle = '#FF8C00';
        ctx.beginPath();
        ctx.roundRect(36 * s, 72 * s, 12 * s, 26 * s, 5 * s);
        ctx.fill();
        ctx.strokeStyle = O; ctx.lineWidth = 2.5 * s; ctx.stroke();
        // 3 red claws on left hand
        ctx.fillStyle = '#FF4444';
        for (let c = 0; c < 3; c++) {
            ctx.beginPath();
            ctx.arc((34 + c * 6) * s, 96 * s, 2.5 * s, 0, Math.PI * 2);
            ctx.fill();
            ctx.strokeStyle = O; ctx.lineWidth = 1.5 * s; ctx.stroke();
        }

        // Right arm (raised higher)
        ctx.fillStyle = '#CC6600';
        ctx.beginPath();
        ctx.roundRect(80 * s, 66 * s, 12 * s, 26 * s, 5 * s);
        ctx.fill();
        ctx.strokeStyle = O; ctx.lineWidth = 2.5 * s; ctx.stroke();
        // 3 red claws on right hand
        ctx.fillStyle = '#FF4444';
        for (let c = 0; c < 3; c++) {
            ctx.beginPath();
            ctx.arc((78 + c * 6) * s, 90 * s, 2.5 * s, 0, Math.PI * 2);
            ctx.fill();
            ctx.strokeStyle = O; ctx.lineWidth = 1.5 * s; ctx.stroke();
        }

        // ── HEAD (tilted ~5° left) ──
        ctx.save();
        ctx.translate(bodyCx * s, 43 * s);
        ctx.rotate(-0.08);

        // Head circle with gradient
        const headGrad = ctx.createLinearGradient(0, -23 * s, 0, 23 * s);
        headGrad.addColorStop(0, '#FFAA33');
        headGrad.addColorStop(1, '#FF8C00');
        ctx.fillStyle = headGrad;
        ctx.beginPath();
        ctx.arc(0, 0, 23 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#FFAA33', O, 2.5 * s);

        // SNOUT — lighter area around mouth
        ctx.fillStyle = '#FFB347';
        ctx.beginPath();
        ctx.ellipse(0, 9 * s, 15 * s, 10 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FFB347', O, 2 * s);

        // NOSTRILS
        ctx.fillStyle = O;
        ctx.beginPath();
        ctx.arc(-5 * s, 9 * s, 1.5 * s, 0, Math.PI * 2);
        ctx.fill();
        ctx.beginPath();
        ctx.arc(5 * s, 9 * s, 1.5 * s, 0, Math.PI * 2);
        ctx.fill();

        // MOUTH — wide happy curve
        ctx.strokeStyle = O;
        ctx.lineWidth = 2 * s;
        ctx.beginPath();
        ctx.arc(0, 10 * s, 8 * s, 0.2, Math.PI - 0.2);
        ctx.stroke();
        // Fangs
        ctx.fillStyle = W;
        ctx.beginPath();
        ctx.moveTo(-5 * s, 14 * s);
        ctx.lineTo(-7 * s, 18 * s);
        ctx.lineTo(-3 * s, 16 * s);
        ctx.fill();
        ctx.strokeStyle = O; ctx.lineWidth = 1 * s; ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(5 * s, 14 * s);
        ctx.lineTo(7 * s, 18 * s);
        ctx.lineTo(3 * s, 16 * s);
        ctx.fill();
        ctx.stroke();

        // EYES — big round friendly green, looking slightly right
        drawEye(ctx, -11 * s, -7 * s, '#44FF44', 8 * s, 3.2 * s, { shape: 'round', gazeX: 0.3 });
        drawEye(ctx, 11 * s, -7 * s, '#44FF44', 8 * s, 3.2 * s, { shape: 'round', gazeX: 0.3 });

        // HORNS — red triangles on top
        ctx.fillStyle = '#FF6600';
        ctx.beginPath();
        ctx.moveTo(-19 * s, -13 * s);
        ctx.lineTo(-22 * s, -32 * s);
        ctx.lineTo(-12 * s, -16 * s);
        ctx.closePath();
        fillStroke(ctx, '#FF6600', O, 2.5 * s);

        ctx.beginPath();
        ctx.moveTo(14 * s, -13 * s);
        ctx.lineTo(21 * s, -32 * s);
        ctx.lineTo(8 * s, -16 * s);
        ctx.closePath();
        fillStroke(ctx, '#FF6600', O, 2.5 * s);

        // CHEEK blush
        ctx.fillStyle = 'rgba(255,100,80,0.3)';
        ctx.beginPath();
        ctx.ellipse(-20 * s, 5 * s, 6 * s, 4 * s, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.beginPath();
        ctx.ellipse(20 * s, 5 * s, 6 * s, 4 * s, 0, 0, Math.PI * 2);
        ctx.fill();

        ctx.restore(); // head rotation
        ctx.restore(); // pose offset
    }

    function drawGabumon(ctx, s) {
        prepCtx(ctx);

        // ── POSE: leaning forward, head tilted ──
        ctx.save();
        ctx.translate(1 * s, 0);
        const bCx = 64, bCy = 78;

        shadowBlobGrad(ctx, (bCx - 1) * s, 118 * s, 24 * s, 10 * s);

        // LEGS
        ctx.fillStyle = '#E8E8F0';
        ctx.beginPath();
        ctx.roundRect(48 * s, 98 * s, 14 * s, 20 * s, 4 * s);
        fillStroke(ctx, '#E8E8F0', O, 2.5 * s);
        ctx.fillStyle = '#B0B0C0';
        ctx.beginPath();
        ctx.roundRect(46 * s, 112 * s, 18 * s, 6 * s, 2 * s);
        fillStroke(ctx, '#B0B0C0', O, 2 * s);

        ctx.fillStyle = '#D0D0D8';
        ctx.beginPath();
        ctx.roundRect(66 * s, 100 * s, 14 * s, 20 * s, 4 * s);
        fillStroke(ctx, '#D0D0D8', O, 2.5 * s);
        ctx.fillStyle = '#B0B0C0';
        ctx.beginPath();
        ctx.roundRect(64 * s, 114 * s, 18 * s, 6 * s, 2 * s);
        fillStroke(ctx, '#B0B0C0', O, 2 * s);

        // TAIL
        ctx.fillStyle = '#4A6FA5';
        ctx.beginPath();
        ctx.moveTo(42 * s, 78 * s);
        ctx.bezierCurveTo(18 * s, 65 * s, 5 * s, 100 * s, 22 * s, 110 * s);
        ctx.bezierCurveTo(35 * s, 115 * s, 48 * s, 90 * s, 42 * s, 78 * s);
        fillStroke(ctx, '#4A6FA5', O, 2.5 * s);

        // BODY — light blue/cream reptilian body with gradient
        drawBodyGradient(ctx, bCx * s, bCy * s, 24 * s, 28 * s, '#F0F0F8', '#D8D8E8');

        // WOLF PELT — blue pelt wrapping over the body
        const peltGrad = ctx.createLinearGradient(38 * s, 40 * s, 38 * s, 105 * s);
        peltGrad.addColorStop(0, '#5A80B5');
        peltGrad.addColorStop(1, '#3A5A8A');
        ctx.fillStyle = peltGrad;
        ctx.beginPath();
        ctx.moveTo(38 * s, 40 * s);
        ctx.bezierCurveTo(28 * s, 55 * s, 30 * s, 95 * s, 42 * s, 105 * s);
        ctx.lineTo(86 * s, 105 * s);
        ctx.bezierCurveTo(98 * s, 95 * s, 100 * s, 55 * s, 90 * s, 40 * s);
        ctx.closePath();
        fillStroke(ctx, '#5A80B5', O, 2.5 * s);

        // PELT STRIPES — darker blue vertical lines
        ctx.strokeStyle = '#3A5A8A';
        ctx.lineWidth = 2.5 * s;
        for (let i = 0; i < 4; i++) {
            const x = 48 * s + i * 10 * s;
            ctx.beginPath();
            ctx.moveTo(x, 62 * s);
            ctx.lineTo(x, 95 * s);
            ctx.stroke();
        }

        // ARMS (asymmetrical)
        ctx.fillStyle = '#E8E8F0';
        ctx.beginPath();
        ctx.roundRect(34 * s, 70 * s, 12 * s, 22 * s, 4 * s);
        fillStroke(ctx, '#E8E8F0', O, 2.5 * s);
        ctx.fillStyle = '#B0B0C0';
        ctx.beginPath();
        ctx.roundRect(32 * s, 88 * s, 16 * s, 6 * s, 2 * s);
        fillStroke(ctx, '#B0B0C0', O, 2 * s);

        ctx.fillStyle = '#D0D0D8';
        ctx.beginPath();
        ctx.roundRect(81 * s, 66 * s, 12 * s, 22 * s, 4 * s);
        fillStroke(ctx, '#D0D0D8', O, 2.5 * s);
        ctx.fillStyle = '#B0B0C0';
        ctx.beginPath();
        ctx.roundRect(79 * s, 84 * s, 16 * s, 6 * s, 2 * s);
        fillStroke(ctx, '#B0B0C0', O, 2 * s);

        // ── HEAD (tilted ~5° right) ──
        ctx.save();
        ctx.translate(bCx * s, 42 * s);
        ctx.rotate(0.06);

        // Head round
        ctx.fillStyle = '#E8E8F0';
        ctx.beginPath();
        ctx.arc(0, 0, 21 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#E8E8F0', O, 2.5 * s);

        // SNOUT
        ctx.fillStyle = '#D8D8E0';
        ctx.beginPath();
        ctx.ellipse(0, 10 * s, 13 * s, 9 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#D8D8E0', O, 2 * s);

        // NOSE
        ctx.fillStyle = O;
        ctx.beginPath();
        ctx.arc(0, 6 * s, 2 * s, 0, Math.PI * 2);
        ctx.fill();

        // MOUTH
        ctx.strokeStyle = O;
        ctx.lineWidth = 1.5 * s;
        ctx.beginPath();
        ctx.arc(0, 12 * s, 5 * s, 0.2, Math.PI - 0.2);
        ctx.stroke();

        // EYES — slightly angled cool red eyes
        drawEye(ctx, -12 * s, -5 * s, '#FF5555', 7.5 * s, 3 * s, { shape: 'round', angle: -0.1, gazeX: 0.3 });
        drawEye(ctx, 12 * s, -5 * s, '#FF5555', 7.5 * s, 3 * s, { shape: 'round', angle: 0.1, gazeX: 0.3 });

        // HORN — gold on forehead
        ctx.fillStyle = '#FFDD44';
        ctx.beginPath();
        ctx.moveTo(-6 * s, -10 * s);
        ctx.lineTo(0, -30 * s);
        ctx.lineTo(6 * s, -10 * s);
        ctx.closePath();
        fillStroke(ctx, '#FFDD44', O, 2.5 * s);

        // PELT HOOD — wraps around head top
        ctx.fillStyle = '#4A6FA5';
        ctx.beginPath();
        ctx.arc(0, -2 * s, 23 * s, Math.PI + 0.4, -0.4);
        ctx.fill();
        ctx.strokeStyle = O; ctx.lineWidth = 2.5 * s; ctx.stroke();

        ctx.restore(); // head
        ctx.restore(); // pose
    }

    function drawBiyomon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 116 * s, 17 * s, 8 * s);

        // LEGS
        ctx.fillStyle = '#FF69B4';
        ctx.beginPath();
        ctx.roundRect(52 * s, 98 * s, 10 * s, 18 * s, 3 * s);
        fillStroke(ctx, '#FF69B4', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(66 * s, 98 * s, 10 * s, 18 * s, 3 * s);
        fillStroke(ctx, '#FF69B4', O, 2.5 * s);

        // FEET
        ctx.fillStyle = '#FF8C00';
        ctx.beginPath();
        ctx.roundRect(49 * s, 112 * s, 14 * s, 5 * s, 2 * s);
        fillStroke(ctx, '#FF8C00', O, 2 * s);
        ctx.beginPath();
        ctx.roundRect(63 * s, 112 * s, 14 * s, 5 * s, 2 * s);
        fillStroke(ctx, '#FF8C00', O, 2 * s);

        // WINGS — big pink bird wings
        ctx.fillStyle = '#FF69B4';
        ctx.beginPath();
        ctx.moveTo(38 * s, 55 * s);
        ctx.bezierCurveTo(5 * s, 40 * s, 2 * s, 85 * s, 35 * s, 90 * s);
        ctx.closePath();
        fillStroke(ctx, '#FF69B4', O, 2.5 * s);
        // Wing feather detail
        ctx.strokeStyle = '#FF1493';
        ctx.lineWidth = 1.5 * s;
        ctx.beginPath();
        ctx.moveTo(36 * s, 58 * s);
        ctx.quadraticCurveTo(15 * s, 65 * s, 20 * s, 82 * s);
        ctx.stroke();

        ctx.fillStyle = '#FFB6C1';
        ctx.beginPath();
        ctx.moveTo(90 * s, 55 * s);
        ctx.bezierCurveTo(123 * s, 40 * s, 126 * s, 85 * s, 93 * s, 90 * s);
        ctx.closePath();
        fillStroke(ctx, '#FFB6C1', O, 2.5 * s);
        ctx.strokeStyle = '#FF1493';
        ctx.beginPath();
        ctx.moveTo(92 * s, 58 * s);
        ctx.quadraticCurveTo(113 * s, 65 * s, 108 * s, 82 * s);
        ctx.stroke();

        // BODY
        ctx.fillStyle = '#FF69B4';
        ctx.beginPath();
        ctx.ellipse(64 * s, 76 * s, 22 * s, 28 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FF69B4', O, 2.5 * s);

        // BELLY
        ctx.fillStyle = '#FFB6C1';
        ctx.beginPath();
        ctx.ellipse(64 * s, 80 * s, 16 * s, 18 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FFB6C1', O, 2 * s);

        // HEAD
        ctx.fillStyle = '#FF69B4';
        ctx.beginPath();
        ctx.arc(64 * s, 42 * s, 20 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#FF69B4', O, 2.5 * s);

        // HEAD FEATHERS — crest on top
        ctx.fillStyle = '#FFB6C1';
        ctx.beginPath();
        ctx.moveTo(52 * s, 28 * s);
        ctx.quadraticCurveTo(55 * s, 8 * s, 60 * s, 14 * s);
        ctx.quadraticCurveTo(64 * s, 4 * s, 68 * s, 14 * s);
        ctx.quadraticCurveTo(73 * s, 8 * s, 76 * s, 28 * s);
        ctx.closePath();
        fillStroke(ctx, '#FFB6C1', O, 2 * s);

        // BEAK
        ctx.fillStyle = '#FF8C00';
        ctx.beginPath();
        ctx.moveTo(56 * s, 46 * s);
        ctx.lineTo(64 * s, 56 * s);
        ctx.lineTo(72 * s, 46 * s);
        ctx.closePath();
        fillStroke(ctx, '#FF8C00', O, 2.5 * s);

        // EYES — sky blue, big and round
        drawEye(ctx, 52 * s, 40 * s, '#87CEEB', 7 * s, 3 * s, { shape: 'huge', gazeX: 0.3 });
        drawEye(ctx, 76 * s, 40 * s, '#87CEEB', 7 * s, 3 * s, { shape: 'huge', gazeX: 0.3 });
    }

    function drawTentomon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 118 * s, 20 * s, 8 * s);

        // LEGS — insect legs
        for (let i = 0; i < 2; i++) {
            const lx = 48 * s + i * 18 * s;
            ctx.fillStyle = '#6B2A6B';
            ctx.beginPath();
            ctx.moveTo(lx, 100 * s);
            ctx.lineTo(lx - 4 * s, 118 * s);
            ctx.lineTo(lx + 12 * s, 118 * s);
            ctx.lineTo(lx + 8 * s, 100 * s);
            ctx.closePath();
            fillStroke(ctx, '#6B2A6B', O, 2 * s);
        }

        // BODY — beetle shell
        const bodyGrad = ctx.createLinearGradient(40 * s, 60 * s, 88 * s, 60 * s);
        bodyGrad.addColorStop(0, '#6B2A6B');
        bodyGrad.addColorStop(0.5, '#8B3A8B');
        bodyGrad.addColorStop(1, '#6B2A6B');
        ctx.fillStyle = bodyGrad;
        ctx.beginPath();
        ctx.ellipse(64 * s, 76 * s, 28 * s, 24 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#8B3A8B', O, 2.5 * s);

        // SHELL LINE
        ctx.strokeStyle = '#4B1A4B';
        ctx.lineWidth = 2 * s;
        ctx.beginPath();
        ctx.moveTo(64 * s, 55 * s);
        ctx.lineTo(64 * s, 96 * s);
        ctx.stroke();

        // SHELL DOTS
        ctx.fillStyle = '#A050A0';
        for (let row = 0; row < 2; row++) {
            for (let col = 0; col < 2; col++) {
                const dx = col === 0 ? 52 * s : 76 * s;
                const dy = 68 * s + row * 10 * s;
                ctx.beginPath();
                ctx.arc(dx, dy, 3 * s, 0, Math.PI * 2);
                ctx.fill();
                ctx.strokeStyle = O; ctx.lineWidth = 1.5 * s; ctx.stroke();
            }
        }

        // ARMS
        ctx.fillStyle = '#6B2A6B';
        ctx.beginPath();
        ctx.roundRect(34 * s, 68 * s, 10 * s, 16 * s, 3 * s);
        fillStroke(ctx, '#6B2A6B', O, 2 * s);
        ctx.beginPath();
        ctx.roundRect(84 * s, 68 * s, 10 * s, 16 * s, 3 * s);
        fillStroke(ctx, '#6B2A6B', O, 2 * s);

        // HEAD
        ctx.fillStyle = '#8B3A8B';
        ctx.beginPath();
        ctx.arc(64 * s, 42 * s, 18 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#8B3A8B', O, 2.5 * s);

        // COMPOUND EYES — red glossy
        ctx.fillStyle = '#FF0000';
        ctx.beginPath();
        ctx.ellipse(52 * s, 42 * s, 9 * s, 11 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FF0000', O, 2.5 * s);
        ctx.fillStyle = W;
        ctx.beginPath();
        ctx.arc(50 * s, 39 * s, 2.5 * s, 0, Math.PI * 2);
        ctx.fill();

        ctx.beginPath();
        ctx.ellipse(76 * s, 42 * s, 9 * s, 11 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FF0000', O, 2.5 * s);
        ctx.fillStyle = W;
        ctx.beginPath();
        ctx.arc(78 * s, 39 * s, 2.5 * s, 0, Math.PI * 2);
        ctx.fill();

        // ANTENNA
        ctx.strokeStyle = O;
        ctx.lineWidth = 2 * s;
        ctx.beginPath();
        ctx.moveTo(50 * s, 28 * s);
        ctx.quadraticCurveTo(40 * s, 10 * s, 32 * s, 16 * s);
        ctx.stroke();
        ctx.fillStyle = '#DDAAFF';
        ctx.beginPath();
        ctx.arc(32 * s, 16 * s, 3 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#DDAAFF', O, 1.5 * s);

        ctx.beginPath();
        ctx.moveTo(78 * s, 28 * s);
        ctx.quadraticCurveTo(88 * s, 10 * s, 96 * s, 16 * s);
        ctx.stroke();
        ctx.fillStyle = '#DDAAFF';
        ctx.beginPath();
        ctx.arc(96 * s, 16 * s, 3 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#DDAAFF', O, 1.5 * s);
    }

    function drawPalmon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 118 * s, 16 * s, 7 * s);

        // LEGS — root-like
        ctx.fillStyle = '#2E8B57';
        ctx.beginPath();
        ctx.roundRect(54 * s, 100 * s, 8 * s, 16 * s, 3 * s);
        fillStroke(ctx, '#2E8B57', O, 2 * s);
        ctx.beginPath();
        ctx.roundRect(66 * s, 100 * s, 8 * s, 16 * s, 3 * s);
        fillStroke(ctx, '#2E8B57', O, 2 * s);

        // BODY
        ctx.fillStyle = '#3CB371';
        ctx.beginPath();
        ctx.ellipse(64 * s, 78 * s, 20 * s, 26 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#3CB371', O, 2.5 * s);

        // BELLY
        ctx.fillStyle = '#90EE90';
        ctx.beginPath();
        ctx.ellipse(64 * s, 82 * s, 14 * s, 16 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#90EE90', O, 2 * s);

        // LEAF ARMS
        ctx.fillStyle = '#3CB371';
        ctx.beginPath();
        ctx.moveTo(34 * s, 66 * s);
        ctx.bezierCurveTo(15 * s, 55 * s, 10 * s, 78 * s, 25 * s, 88 * s);
        ctx.lineTo(40 * s, 85 * s);
        ctx.closePath();
        fillStroke(ctx, '#3CB371', O, 2 * s);

        ctx.beginPath();
        ctx.moveTo(94 * s, 66 * s);
        ctx.bezierCurveTo(113 * s, 55 * s, 118 * s, 78 * s, 103 * s, 88 * s);
        ctx.lineTo(88 * s, 85 * s);
        ctx.closePath();
        fillStroke(ctx, '#3CB371', O, 2 * s);

        // HEAD
        ctx.fillStyle = '#3CB371';
        ctx.beginPath();
        ctx.arc(64 * s, 44 * s, 18 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#3CB371', O, 2.5 * s);

        // HEAD LEAVES / PETALS
        const petalColors = ['#FF69B4', '#FF1493', '#FFB6C1'];
        for (let i = 0; i < 5; i++) {
            const angle = (i / 5) * Math.PI * 2 - Math.PI / 2;
            const px = 64 * s + Math.cos(angle) * 14 * s;
            const py = 36 * s + Math.sin(angle) * 14 * s;
            ctx.fillStyle = petalColors[i % 3];
            ctx.beginPath();
            ctx.ellipse(px, py, 8 * s, 5 * s, angle, 0, Math.PI * 2);
            fillStroke(ctx, petalColors[i % 3], O, 1.5 * s);
        }

        // FACE
        ctx.fillStyle = '#90EE90';
        ctx.beginPath();
        ctx.arc(64 * s, 46 * s, 12 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#90EE90', O, 1.5 * s);

        // MOUTH
        ctx.strokeStyle = O;
        ctx.lineWidth = 1.5 * s;
        ctx.beginPath();
        ctx.arc(64 * s, 51 * s, 4 * s, 0.1, Math.PI - 0.1);
        ctx.stroke();

        // EYES — round green, gentle gaze
        drawEye(ctx, 54 * s, 42 * s, '#2E8B57', 6 * s, 2.5 * s, { shape: 'round', gazeX: 0.3 });
        drawEye(ctx, 74 * s, 42 * s, '#2E8B57', 6 * s, 2.5 * s, { shape: 'round', gazeX: 0.3 });
    }

    function drawGomamon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 118 * s, 22 * s, 9 * s);

        // TAIL fins
        ctx.fillStyle = '#C0C0E0';
        ctx.beginPath();
        ctx.moveTo(88 * s, 92 * s);
        ctx.bezierCurveTo(108 * s, 85 * s, 115 * s, 105 * s, 98 * s, 112 * s);
        ctx.lineTo(88 * s, 100 * s);
        ctx.closePath();
        fillStroke(ctx, '#C0C0E0', O, 2 * s);

        // BODY — seal shape
        ctx.fillStyle = '#F0F0FF';
        ctx.beginPath();
        ctx.ellipse(64 * s, 80 * s, 26 * s, 24 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#F0F0FF', O, 2.5 * s);

        // PURPLE MARKINGS on body
        ctx.strokeStyle = '#6B3A8B';
        ctx.lineWidth = 3 * s;
        ctx.setLineDash([]);
        for (let i = 0; i < 3; i++) {
            const my = 68 * s + i * 10 * s;
            ctx.beginPath();
            ctx.moveTo(60 * s, my);
            ctx.quadraticCurveTo(64 * s, my - 3 * s, 68 * s, my);
            ctx.stroke();
        }

        // FRONT FLIPPERS
        ctx.fillStyle = '#E0E0F0';
        ctx.beginPath();
        ctx.roundRect(30 * s, 72 * s, 18 * s, 10 * s, 4 * s);
        fillStroke(ctx, '#E0E0F0', O, 2 * s);
        ctx.beginPath();
        ctx.roundRect(80 * s, 72 * s, 18 * s, 10 * s, 4 * s);
        fillStroke(ctx, '#E0E0F0', O, 2 * s);

        // BACK FLIPPERS
        ctx.fillStyle = '#D0D0E0';
        ctx.beginPath();
        ctx.roundRect(44 * s, 102 * s, 14 * s, 8 * s, 3 * s);
        fillStroke(ctx, '#D0D0E0', O, 2 * s);
        ctx.beginPath();
        ctx.roundRect(70 * s, 102 * s, 14 * s, 8 * s, 3 * s);
        fillStroke(ctx, '#D0D0E0', O, 2 * s);

        // HEAD
        ctx.fillStyle = '#F0F0FF';
        ctx.beginPath();
        ctx.arc(64 * s, 48 * s, 22 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#F0F0FF', O, 2.5 * s);

        // MOHAWK — orange
        ctx.fillStyle = '#FF6600';
        ctx.beginPath();
        ctx.moveTo(58 * s, 30 * s);
        ctx.quadraticCurveTo(64 * s, 8 * s, 70 * s, 30 * s);
        ctx.closePath();
        fillStroke(ctx, '#FF6600', O, 2.5 * s);
        // More mohawk spikes
        ctx.beginPath();
        ctx.moveTo(52 * s, 34 * s);
        ctx.quadraticCurveTo(48 * s, 16 * s, 56 * s, 28 * s);
        ctx.closePath();
        fillStroke(ctx, '#FF6600', O, 2 * s);
        ctx.beginPath();
        ctx.moveTo(76 * s, 34 * s);
        ctx.quadraticCurveTo(80 * s, 16 * s, 72 * s, 28 * s);
        ctx.closePath();
        fillStroke(ctx, '#FF6600', O, 2 * s);

        // FACE
        ctx.fillStyle = '#E8E8F8';
        ctx.beginPath();
        ctx.ellipse(64 * s, 52 * s, 14 * s, 10 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#E8E8F8', O, 2 * s);

        // NOSE
        ctx.fillStyle = '#FF6666';
        ctx.beginPath();
        ctx.arc(64 * s, 50 * s, 2.5 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#FF6666', O, 1.5 * s);

        // MOUTH
        ctx.strokeStyle = O;
        ctx.lineWidth = 1.5 * s;
        ctx.beginPath();
        ctx.arc(64 * s, 56 * s, 5 * s, 0.2, Math.PI - 0.2);
        ctx.stroke();

        // WHISKERS
        ctx.strokeStyle = O;
        ctx.lineWidth = 1.5 * s;
        for (let side = -1; side <= 1; side += 2) {
            const wx = 64 * s + side * 12 * s;
            ctx.beginPath();
            ctx.moveTo(wx, 52 * s);
            ctx.lineTo(wx + side * 8 * s, 48 * s);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(wx, 54 * s);
            ctx.lineTo(wx + side * 8 * s, 56 * s);
            ctx.stroke();
        }

        // EYES — round blue, curious
        drawEye(ctx, 52 * s, 45 * s, '#4169E1', 7 * s, 3 * s, { shape: 'round', gazeX: 0.3 });
        drawEye(ctx, 76 * s, 45 * s, '#4169E1', 7 * s, 3 * s, { shape: 'round', gazeX: 0.3 });
    }

    function drawPatamon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 116 * s, 16 * s, 7 * s);

        // FEET
        ctx.fillStyle = '#FFA07A';
        ctx.beginPath();
        ctx.roundRect(52 * s, 104 * s, 10 * s, 12 * s, 3 * s);
        fillStroke(ctx, '#FFA07A', O, 2 * s);
        ctx.beginPath();
        ctx.roundRect(66 * s, 104 * s, 10 * s, 12 * s, 3 * s);
        fillStroke(ctx, '#FFA07A', O, 2 * s);

        // BODY
        ctx.fillStyle = '#FFDAB9';
        ctx.beginPath();
        ctx.ellipse(64 * s, 80 * s, 20 * s, 28 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FFDAB9', O, 2.5 * s);

        // BELLY
        ctx.fillStyle = '#FFE4B5';
        ctx.beginPath();
        ctx.ellipse(64 * s, 84 * s, 14 * s, 16 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FFE4B5', O, 2 * s);

        // WINGS — big wing ears
        ctx.fillStyle = '#FFDAB9';
        for (let side = -1; side <= 1; side += 2) {
            const wx = 64 * s + side * 28 * s;
            ctx.beginPath();
            ctx.moveTo(64 * s + side * 10 * s, 30 * s);
            ctx.bezierCurveTo(
                wx - side * 5 * s, 10 * s,
                wx + side * 5 * s, 55 * s,
                wx + side * 8 * s, 75 * s
            );
            ctx.bezierCurveTo(
                wx + side * 2 * s, 70 * s,
                64 * s + side * 4 * s, 50 * s,
                64 * s + side * 6 * s, 38 * s
            );
            ctx.closePath();
            fillStroke(ctx, '#FFDAB9', O, 2.5 * s);

            // Wing inner lines
            ctx.strokeStyle = '#DEB887';
            ctx.lineWidth = 1.5 * s;
            ctx.beginPath();
            ctx.moveTo(64 * s + side * 8 * s, 35 * s);
            ctx.quadraticCurveTo(wx, 40 * s, wx + side * 3 * s, 60 * s);
            ctx.stroke();
        }

        // HEAD
        ctx.fillStyle = '#FFDAB9';
        ctx.beginPath();
        ctx.arc(64 * s, 48 * s, 18 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#FFDAB9', O, 2.5 * s);

        // FACE
        ctx.fillStyle = '#FFE4B5';
        ctx.beginPath();
        ctx.ellipse(64 * s, 52 * s, 12 * s, 9 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FFE4B5', O, 1.5 * s);

        // MOUTH
        ctx.strokeStyle = O;
        ctx.lineWidth = 1.5 * s;
        ctx.beginPath();
        ctx.arc(64 * s, 55 * s, 4 * s, 0.1, Math.PI - 0.1);
        ctx.stroke();

        // EYES — huge innocent sky blue, Patamon's trademark big eyes
        drawEye(ctx, 54 * s, 46 * s, '#87CEEB', 7.5 * s, 3.2 * s, { shape: 'huge', gazeX: 0.3 });
        drawEye(ctx, 74 * s, 46 * s, '#87CEEB', 7.5 * s, 3.2 * s, { shape: 'huge', gazeX: 0.3 });

        // CHEEK BLUSH
        ctx.fillStyle = 'rgba(255,100,80,0.25)';
        ctx.beginPath();
        ctx.ellipse(48 * s, 54 * s, 4 * s, 3 * s, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.beginPath();
        ctx.ellipse(80 * s, 54 * s, 4 * s, 3 * s, 0, 0, Math.PI * 2);
        ctx.fill();
    }

    function drawTailmon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 116 * s, 17 * s, 7 * s);

        // TAIL — long curvy tail
        ctx.strokeStyle = '#F5F5DC';
        ctx.lineWidth = 8 * s;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(74 * s, 95 * s);
        ctx.bezierCurveTo(95 * s, 100 * s, 110 * s, 80 * s, 105 * s, 60 * s);
        ctx.stroke();
        ctx.strokeStyle = O;
        ctx.lineWidth = 10 * s;
        ctx.stroke();
        ctx.strokeStyle = '#F5F5DC';
        ctx.lineWidth = 8 * s;
        ctx.stroke();

        // Tail rings
        ctx.strokeStyle = '#FFD700';
        ctx.lineWidth = 2.5 * s;
        ctx.beginPath();
        ctx.arc(90 * s, 88 * s, 6 * s, 0, Math.PI * 2);
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(100 * s, 75 * s, 5 * s, 0, Math.PI * 2);
        ctx.stroke();

        // LEGS
        ctx.fillStyle = '#F5F5DC';
        ctx.beginPath();
        ctx.roundRect(50 * s, 98 * s, 12 * s, 16 * s, 4 * s);
        fillStroke(ctx, '#F5F5DC', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(66 * s, 98 * s, 12 * s, 16 * s, 4 * s);
        fillStroke(ctx, '#F5F5DC', O, 2.5 * s);

        // PAWS
        ctx.fillStyle = '#FFE4E1';
        ctx.beginPath();
        ctx.roundRect(48 * s, 110 * s, 16 * s, 5 * s, 2 * s);
        fillStroke(ctx, '#FFE4E1', O, 2 * s);
        ctx.beginPath();
        ctx.roundRect(64 * s, 110 * s, 16 * s, 5 * s, 2 * s);
        fillStroke(ctx, '#FFE4E1', O, 2 * s);

        // BODY
        ctx.fillStyle = '#F5F5DC';
        ctx.beginPath();
        ctx.ellipse(64 * s, 80 * s, 20 * s, 24 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#F5F5DC', O, 2.5 * s);

        // ARMS
        ctx.fillStyle = '#F5F5DC';
        ctx.beginPath();
        ctx.roundRect(36 * s, 72 * s, 10 * s, 18 * s, 4 * s);
        fillStroke(ctx, '#F5F5DC', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(82 * s, 72 * s, 10 * s, 18 * s, 4 * s);
        fillStroke(ctx, '#F5F5DC', O, 2.5 * s);

        // GLOVES — rings on arms
        ctx.strokeStyle = '#FFD700';
        ctx.lineWidth = 2 * s;
        ctx.beginPath();
        ctx.arc(41 * s, 78 * s, 6 * s, 0, Math.PI * 2);
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(87 * s, 78 * s, 6 * s, 0, Math.PI * 2);
        ctx.stroke();

        // HEAD
        ctx.fillStyle = '#F5F5DC';
        ctx.beginPath();
        ctx.arc(64 * s, 48 * s, 18 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#F5F5DC', O, 2.5 * s);

        // CAT EARS
        for (let side = -1; side <= 1; side += 2) {
            const ex = 64 * s + side * 14 * s;
            ctx.fillStyle = '#F5F5DC';
            ctx.beginPath();
            ctx.moveTo(ex - side * 5 * s, 38 * s);
            ctx.lineTo(ex, 18 * s);
            ctx.lineTo(ex + side * 8 * s, 38 * s);
            ctx.closePath();
            fillStroke(ctx, '#F5F5DC', O, 2.5 * s);

            // Inner ear
            ctx.fillStyle = '#FFE4E1';
            ctx.beginPath();
            ctx.moveTo(ex - side * 3 * s, 36 * s);
            ctx.lineTo(ex, 22 * s);
            ctx.lineTo(ex + side * 5 * s, 36 * s);
            ctx.closePath();
            ctx.fill();
            ctx.strokeStyle = O; ctx.lineWidth = 1.5 * s; ctx.stroke();
        }

        // FACE
        ctx.fillStyle = '#FFE4E1';
        ctx.beginPath();
        ctx.ellipse(64 * s, 53 * s, 11 * s, 9 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FFE4E1', O, 1.5 * s);

        // NOSE
        ctx.fillStyle = '#FFA07A';
        ctx.beginPath();
        ctx.arc(64 * s, 50 * s, 2 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#FFA07A', O, 1.5 * s);

        // MOUTH
        ctx.strokeStyle = O;
        ctx.lineWidth = 1.5 * s;
        ctx.beginPath();
        ctx.moveTo(61 * s, 56 * s);
        ctx.quadraticCurveTo(64 * s, 59 * s, 67 * s, 56 * s);
        ctx.stroke();

        // EYES — cat-slit pupils! angled slightly for feline look
        drawEye(ctx, 53 * s, 46 * s, '#4169E1', 7 * s, 2.5 * s, { shape: 'slit', gazeX: 0.4 });
        drawEye(ctx, 75 * s, 46 * s, '#4169E1', 7 * s, 2.5 * s, { shape: 'slit', gazeX: 0.4 });
    }

    function drawPlotmon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 116 * s, 16 * s, 7 * s);

        // TAIL
        ctx.fillStyle = '#FFE4C4';
        ctx.beginPath();
        ctx.moveTo(78 * s, 95 * s);
        ctx.quadraticCurveTo(100 * s, 90 * s, 95 * s, 78 * s);
        ctx.quadraticCurveTo(88 * s, 85 * s, 82 * s, 88 * s);
        ctx.closePath();
        fillStroke(ctx, '#FFE4C4', O, 2 * s);

        // LEGS
        ctx.fillStyle = '#FFE4C4';
        ctx.beginPath();
        ctx.roundRect(50 * s, 100 * s, 12 * s, 14 * s, 4 * s);
        fillStroke(ctx, '#FFE4C4', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(66 * s, 100 * s, 12 * s, 14 * s, 4 * s);
        fillStroke(ctx, '#FFE4C4', O, 2.5 * s);

        // BODY — puppy body
        ctx.fillStyle = '#FFE4C4';
        ctx.beginPath();
        ctx.ellipse(64 * s, 80 * s, 20 * s, 24 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FFE4C4', O, 2.5 * s);

        // BELLY
        ctx.fillStyle = '#FFDEAD';
        ctx.beginPath();
        ctx.ellipse(64 * s, 84 * s, 14 * s, 15 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FFDEAD', O, 2 * s);

        // HEAD
        ctx.fillStyle = '#FFE4C4';
        ctx.beginPath();
        ctx.arc(64 * s, 48 * s, 19 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#FFE4C4', O, 2.5 * s);

        // FLOPPY EARS
        for (let side = -1; side <= 1; side += 2) {
            const ex = 64 * s + side * 16 * s;
            ctx.fillStyle = '#DEB887';
            ctx.beginPath();
            ctx.moveTo(ex, 38 * s);
            ctx.bezierCurveTo(
                ex - side * 8 * s, 28 * s,
                ex - side * 4 * s, 68 * s,
                ex + side * 2 * s, 62 * s
            );
            ctx.bezierCurveTo(ex + side * 1 * s, 52 * s, ex, 46 * s, ex, 38 * s);
            ctx.closePath();
            fillStroke(ctx, '#DEB887', O, 2 * s);
        }

        // FACE
        ctx.fillStyle = '#FFDEAD';
        ctx.beginPath();
        ctx.ellipse(64 * s, 53 * s, 11 * s, 9 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FFDEAD', O, 1.5 * s);

        // NOSE
        ctx.fillStyle = O;
        ctx.beginPath();
        ctx.arc(64 * s, 50 * s, 2.5 * s, 0, Math.PI * 2);
        fillStroke(ctx, O, O, 1 * s);

        // MOUTH
        ctx.strokeStyle = O;
        ctx.lineWidth = 1.5 * s;
        ctx.beginPath();
        ctx.arc(64 * s, 54 * s, 4 * s, 0.1, Math.PI - 0.1);
        ctx.stroke();

        // EYES — puppy-dog round blue
        drawEye(ctx, 52 * s, 44 * s, '#4169E1', 7 * s, 3 * s, { shape: 'round', gazeX: 0.3 });
        drawEye(ctx, 76 * s, 44 * s, '#4169E1', 7 * s, 3 * s, { shape: 'round', gazeX: 0.3 });

        // CHEEKS
        ctx.fillStyle = 'rgba(255,100,100,0.25)';
        ctx.beginPath();
        ctx.ellipse(46 * s, 52 * s, 5 * s, 3 * s, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.beginPath();
        ctx.ellipse(82 * s, 52 * s, 5 * s, 3 * s, 0, 0, Math.PI * 2);
        ctx.fill();
    }

    function drawElecmon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 118 * s, 18 * s, 7 * s);

        // TAIL
        ctx.strokeStyle = '#FF3333';
        ctx.lineWidth = 6 * s;
        ctx.beginPath();
        ctx.moveTo(80 * s, 90 * s);
        ctx.bezierCurveTo(100 * s, 88 * s, 115 * s, 70 * s, 108 * s, 55 * s);
        ctx.stroke();
        ctx.strokeStyle = O;
        ctx.lineWidth = 8 * s;
        ctx.stroke();
        ctx.strokeStyle = '#FF3333';
        ctx.lineWidth = 6 * s;
        ctx.stroke();

        // Tail lightning bolt tip
        ctx.fillStyle = '#FFD700';
        ctx.beginPath();
        ctx.moveTo(108 * s, 55 * s);
        ctx.lineTo(102 * s, 48 * s);
        ctx.lineTo(112 * s, 45 * s);
        ctx.lineTo(106 * s, 38 * s);
        ctx.lineTo(116 * s, 42 * s);
        ctx.closePath();
        fillStroke(ctx, '#FFD700', O, 2 * s);

        // LEGS
        ctx.fillStyle = '#FF3333';
        ctx.beginPath();
        ctx.roundRect(50 * s, 98 * s, 12 * s, 18 * s, 4 * s);
        fillStroke(ctx, '#FF3333', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(66 * s, 98 * s, 12 * s, 18 * s, 4 * s);
        fillStroke(ctx, '#FF3333', O, 2.5 * s);

        // BODY
        const bodyGrad = ctx.createLinearGradient(40 * s, 70 * s, 88 * s, 70 * s);
        bodyGrad.addColorStop(0, '#CC0000');
        bodyGrad.addColorStop(0.5, '#FF3333');
        bodyGrad.addColorStop(1, '#CC0000');
        ctx.fillStyle = bodyGrad;
        ctx.beginPath();
        ctx.ellipse(64 * s, 78 * s, 22 * s, 26 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FF3333', O, 2.5 * s);

        // LIGHTNING BELT — gold zigzag on belly
        ctx.strokeStyle = '#FFD700';
        ctx.lineWidth = 2.5 * s;
        ctx.beginPath();
        ctx.moveTo(50 * s, 78 * s);
        ctx.lineTo(58 * s, 72 * s);
        ctx.lineTo(54 * s, 78 * s);
        ctx.lineTo(62 * s, 72 * s);
        ctx.lineTo(58 * s, 78 * s);
        ctx.lineTo(66 * s, 72 * s);
        ctx.lineTo(62 * s, 78 * s);
        ctx.lineTo(71 * s, 72 * s);
        ctx.lineTo(67 * s, 78 * s);
        ctx.lineTo(78 * s, 72 * s);
        ctx.stroke();

        // ARMS
        ctx.fillStyle = '#FF3333';
        ctx.beginPath();
        ctx.roundRect(34 * s, 68 * s, 10 * s, 20 * s, 4 * s);
        fillStroke(ctx, '#FF3333', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(84 * s, 68 * s, 10 * s, 20 * s, 4 * s);
        fillStroke(ctx, '#FF3333', O, 2.5 * s);

        // HEAD
        ctx.fillStyle = '#FF3333';
        ctx.beginPath();
        ctx.arc(64 * s, 44 * s, 19 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#FF3333', O, 2.5 * s);

        // SPIKY HAIR / EARS
        for (let i = 0; i < 5; i++) {
            const angle = (i / 5) * Math.PI * -1 + Math.PI * 0.6;
            const sx = 64 * s + Math.cos(angle) * 16 * s;
            const sy = 44 * s + Math.sin(angle) * 16 * s;
            const tx = 64 * s + Math.cos(angle) * 30 * s;
            const ty = 44 * s + Math.sin(angle) * 30 * s;
            ctx.fillStyle = '#FF3333';
            ctx.beginPath();
            ctx.moveTo(sx, sy);
            ctx.lineTo(tx, ty);
            ctx.lineTo(sx + Math.cos(angle + 0.3) * 8 * s, sy + Math.sin(angle + 0.3) * 8 * s);
            ctx.closePath();
            fillStroke(ctx, '#FF3333', O, 2 * s);
        }

        // FACE
        ctx.fillStyle = '#FF6644';
        ctx.beginPath();
        ctx.ellipse(64 * s, 48 * s, 12 * s, 9 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FF6644', O, 1.5 * s);

        // MOUTH — sharp grin
        ctx.strokeStyle = O;
        ctx.lineWidth = 2 * s;
        ctx.beginPath();
        ctx.moveTo(55 * s, 52 * s);
        ctx.quadraticCurveTo(64 * s, 58 * s, 73 * s, 52 * s);
        ctx.stroke();

        // FANGS
        ctx.fillStyle = W;
        ctx.beginPath();
        ctx.moveTo(57 * s, 53 * s);
        ctx.lineTo(54 * s, 49 * s);
        ctx.lineTo(59 * s, 53 * s);
        ctx.fill();
        ctx.strokeStyle = O; ctx.lineWidth = 1 * s; ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(71 * s, 53 * s);
        ctx.lineTo(74 * s, 49 * s);
        ctx.lineTo(69 * s, 53 * s);
        ctx.fill();
        ctx.stroke();

        // EYES — fierce gold, narrow angry
        drawEye(ctx, 52 * s, 40 * s, '#FFD700', 7 * s, 3 * s, { shape: 'narrow', angle: -0.15 });
        drawEye(ctx, 76 * s, 40 * s, '#FFD700', 7 * s, 3 * s, { shape: 'narrow', angle: 0.15 });
    }

    function drawTsunomon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 116 * s, 16 * s, 7 * s);

        // BODY — round blob
        ctx.fillStyle = '#E6E6FA';
        ctx.beginPath();
        ctx.ellipse(64 * s, 82 * s, 20 * s, 24 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#E6E6FA', O, 2.5 * s);

        // BELLY
        ctx.fillStyle = '#D8BFD8';
        ctx.beginPath();
        ctx.ellipse(64 * s, 86 * s, 14 * s, 15 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#D8BFD8', O, 2 * s);

        // FEET nubs
        ctx.fillStyle = '#DDA0DD';
        ctx.beginPath();
        ctx.roundRect(52 * s, 100 * s, 10 * s, 14 * s, 5 * s);
        fillStroke(ctx, '#DDA0DD', O, 2 * s);
        ctx.beginPath();
        ctx.roundRect(66 * s, 100 * s, 10 * s, 14 * s, 5 * s);
        fillStroke(ctx, '#DDA0DD', O, 2 * s);

        // HEAD — connected at top
        ctx.fillStyle = '#E6E6FA';
        ctx.beginPath();
        ctx.arc(64 * s, 50 * s, 18 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#E6E6FA', O, 2.5 * s);

        // UNICORN HORN
        ctx.fillStyle = '#9370DB';
        ctx.beginPath();
        ctx.moveTo(58 * s, 38 * s);
        ctx.lineTo(64 * s, 8 * s);
        ctx.lineTo(70 * s, 38 * s);
        ctx.closePath();
        fillStroke(ctx, '#9370DB', O, 2.5 * s);

        // Horn spiral lines
        ctx.strokeStyle = '#BA55D3';
        ctx.lineWidth = 1.5 * s;
        ctx.beginPath();
        ctx.moveTo(60 * s, 28 * s);
        ctx.lineTo(68 * s, 28 * s);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(61 * s, 22 * s);
        ctx.lineTo(67 * s, 22 * s);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(62 * s, 16 * s);
        ctx.lineTo(66 * s, 16 * s);
        ctx.stroke();

        // FACE
        ctx.fillStyle = '#D8BFD8';
        ctx.beginPath();
        ctx.ellipse(64 * s, 54 * s, 12 * s, 9 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#D8BFD8', O, 1.5 * s);

        // MOUTH
        ctx.strokeStyle = O;
        ctx.lineWidth = 1.5 * s;
        ctx.beginPath();
        ctx.arc(64 * s, 56 * s, 4 * s, 0.1, Math.PI - 0.1);
        ctx.stroke();

        // EYES — big cute eyes, looking up
        drawEye(ctx, 53 * s, 48 * s, '#9370DB', 7.5 * s, 3 * s, { shape: 'huge', gazeY: -0.3 });
        drawEye(ctx, 75 * s, 48 * s, '#9370DB', 7.5 * s, 3 * s, { shape: 'huge', gazeY: -0.3 });

        // CHEEKS
        ctx.fillStyle = 'rgba(180,100,255,0.25)';
        ctx.beginPath();
        ctx.ellipse(47 * s, 55 * s, 4 * s, 3 * s, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.beginPath();
        ctx.ellipse(81 * s, 55 * s, 4 * s, 3 * s, 0, 0, Math.PI * 2);
        ctx.fill();
    }

    /* ── Data-type Digimon ── */

    function drawHagurumon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 116 * s, 24 * s, 8 * s);

        // OUTER GEAR RING
        ctx.strokeStyle = '#808080';
        ctx.lineWidth = 6 * s;
        ctx.beginPath();
        ctx.arc(64 * s, 72 * s, 26 * s, 0, Math.PI * 2);
        ctx.stroke();

        // Gear teeth
        for (let i = 0; i < 8; i++) {
            const angle = (i / 8) * Math.PI * 2;
            const tx = 64 * s + Math.cos(angle) * 26 * s;
            const ty = 72 * s + Math.sin(angle) * 26 * s;
            ctx.fillStyle = '#B0B0B0';
            ctx.beginPath();
            ctx.moveTo(tx, ty);
            ctx.lineTo(tx + Math.cos(angle) * 10 * s, ty + Math.sin(angle) * 10 * s);
            ctx.lineTo(tx + Math.cos(angle + 0.15) * 5 * s, ty + Math.sin(angle + 0.15) * 5 * s);
            ctx.closePath();
            fillStroke(ctx, '#B0B0B0', O, 2 * s);
        }

        // MAIN BODY — circle
        const gearGrad = ctx.createRadialGradient(58 * s, 68 * s, 5 * s, 64 * s, 72 * s, 22 * s);
        gearGrad.addColorStop(0, '#D0D0D0');
        gearGrad.addColorStop(1, '#808080');
        ctx.fillStyle = gearGrad;
        ctx.beginPath();
        ctx.arc(64 * s, 72 * s, 22 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#B0B0B0', O, 2.5 * s);

        // INNER RING
        ctx.strokeStyle = '#606060';
        ctx.lineWidth = 2 * s;
        ctx.beginPath();
        ctx.arc(64 * s, 72 * s, 14 * s, 0, Math.PI * 2);
        ctx.stroke();

        // CENTER HUB
        ctx.fillStyle = '#606060';
        ctx.beginPath();
        ctx.arc(64 * s, 72 * s, 6 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#606060', O, 2 * s);

        // EYE — single large
        ctx.fillStyle = W;
        ctx.beginPath();
        ctx.arc(64 * s, 62 * s, 8 * s, 0, Math.PI * 2);
        fillStroke(ctx, W, O, 2 * s);
        ctx.fillStyle = '#FFD700';
        ctx.beginPath();
        ctx.arc(64 * s, 63 * s, 5 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#FFD700', O, 1.5 * s);
        ctx.fillStyle = O;
        ctx.beginPath();
        ctx.arc(64 * s, 63 * s, 2.5 * s, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = W;
        ctx.beginPath();
        ctx.arc(63 * s, 61 * s, 1 * s, 0, Math.PI * 2);
        ctx.fill();

        // BOLTS
        for (let i = 0; i < 4; i++) {
            const angle = (i / 4) * Math.PI * 2 + 0.3;
            const bx = 64 * s + Math.cos(angle) * 18 * s;
            const by = 72 * s + Math.sin(angle) * 18 * s;
            ctx.fillStyle = '#D0D0D0';
            ctx.beginPath();
            ctx.arc(bx, by, 3 * s, 0, Math.PI * 2);
            fillStroke(ctx, '#D0D0D0', O, 1.5 * s);
        }
    }

    function drawGuardromon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 118 * s, 22 * s, 8 * s);

        // LEGS — mechanical
        ctx.fillStyle = '#4682B4';
        ctx.beginPath();
        ctx.roundRect(46 * s, 98 * s, 14 * s, 18 * s, 3 * s);
        fillStroke(ctx, '#4682B4', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(68 * s, 98 * s, 14 * s, 18 * s, 3 * s);
        fillStroke(ctx, '#4682B4', O, 2.5 * s);

        // FEET
        ctx.fillStyle = '#2E5A7A';
        ctx.beginPath();
        ctx.roundRect(42 * s, 112 * s, 20 * s, 6 * s, 2 * s);
        fillStroke(ctx, '#2E5A7A', O, 2 * s);
        ctx.beginPath();
        ctx.roundRect(64 * s, 112 * s, 20 * s, 6 * s, 2 * s);
        fillStroke(ctx, '#2E5A7A', O, 2 * s);

        // BODY — rectangular robot torso
        ctx.fillStyle = '#4682B4';
        ctx.beginPath();
        ctx.roundRect(40 * s, 56 * s, 48 * s, 46 * s, 8 * s);
        fillStroke(ctx, '#4682B4', O, 2.5 * s);

        // CHEST ARMOR PLATE
        ctx.fillStyle = '#5A9AC4';
        ctx.beginPath();
        ctx.roundRect(48 * s, 66 * s, 32 * s, 28 * s, 5 * s);
        fillStroke(ctx, '#5A9AC4', O, 2 * s);

        // CHEST LIGHT
        ctx.fillStyle = '#FF0000';
        ctx.beginPath();
        ctx.arc(64 * s, 74 * s, 5 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#FF0000', O, 2 * s);
        ctx.fillStyle = W;
        ctx.beginPath();
        ctx.arc(63 * s, 72 * s, 1.5 * s, 0, Math.PI * 2);
        ctx.fill();

        // ARMS — mechanical
        ctx.fillStyle = '#4682B4';
        ctx.beginPath();
        ctx.roundRect(28 * s, 60 * s, 14 * s, 32 * s, 5 * s);
        fillStroke(ctx, '#4682B4', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(86 * s, 60 * s, 14 * s, 32 * s, 5 * s);
        fillStroke(ctx, '#4682B4', O, 2.5 * s);

        // HANDS
        ctx.fillStyle = '#2E5A7A';
        ctx.beginPath();
        ctx.arc(35 * s, 94 * s, 6 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#2E5A7A', O, 2 * s);
        ctx.beginPath();
        ctx.arc(93 * s, 94 * s, 6 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#2E5A7A', O, 2 * s);

        // HEAD — dome
        ctx.fillStyle = '#4682B4';
        ctx.beginPath();
        ctx.arc(64 * s, 40 * s, 20 * s, Math.PI, 0);
        ctx.lineTo(84 * s, 40 * s);
        ctx.lineTo(44 * s, 40 * s);
        ctx.closePath();
        fillStroke(ctx, '#4682B4', O, 2.5 * s);

        // SENSOR EYE — red bar
        ctx.fillStyle = '#FF0000';
        ctx.beginPath();
        ctx.roundRect(54 * s, 35 * s, 20 * s, 8 * s, 4 * s);
        fillStroke(ctx, '#FF0000', O, 2 * s);
        ctx.fillStyle = W;
        ctx.beginPath();
        ctx.arc(60 * s, 39 * s, 2 * s, 0, Math.PI * 2);
        ctx.fill();
    }

    function drawAndromon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 120 * s, 24 * s, 8 * s);

        // LEGS
        ctx.fillStyle = '#4169E1';
        ctx.beginPath();
        ctx.roundRect(46 * s, 96 * s, 16 * s, 22 * s, 4 * s);
        fillStroke(ctx, '#4169E1', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(66 * s, 96 * s, 16 * s, 22 * s, 4 * s);
        fillStroke(ctx, '#4169E1', O, 2.5 * s);

        // FEET
        ctx.fillStyle = '#1a3a7a';
        ctx.beginPath();
        ctx.roundRect(42 * s, 114 * s, 22 * s, 8 * s, 3 * s);
        fillStroke(ctx, '#1a3a7a', O, 2 * s);
        ctx.beginPath();
        ctx.roundRect(62 * s, 114 * s, 22 * s, 8 * s, 3 * s);
        fillStroke(ctx, '#1a3a7a', O, 2 * s);

        // BODY — larger cyborg torso
        ctx.fillStyle = '#4169E1';
        ctx.beginPath();
        ctx.roundRect(36 * s, 52 * s, 56 * s, 50 * s, 10 * s);
        fillStroke(ctx, '#4169E1', O, 2.5 * s);

        // CHEST CANNONS
        ctx.fillStyle = '#2a5aC0';
        ctx.beginPath();
        ctx.arc(52 * s, 70 * s, 8 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#2a5aC0', O, 2 * s);
        ctx.beginPath();
        ctx.arc(76 * s, 70 * s, 8 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#2a5aC0', O, 2 * s);

        // SHOULDER PADS
        ctx.fillStyle = '#1a3a7a';
        ctx.beginPath();
        ctx.ellipse(36 * s, 60 * s, 12 * s, 16 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#1a3a7a', O, 2.5 * s);
        ctx.beginPath();
        ctx.ellipse(92 * s, 60 * s, 12 * s, 16 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#1a3a7a', O, 2.5 * s);

        // ARMS
        ctx.fillStyle = '#5A7AFF';
        ctx.beginPath();
        ctx.roundRect(26 * s, 62 * s, 12 * s, 28 * s, 4 * s);
        fillStroke(ctx, '#5A7AFF', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(90 * s, 62 * s, 12 * s, 28 * s, 4 * s);
        fillStroke(ctx, '#5A7AFF', O, 2.5 * s);

        // HANDS — cannon-like
        ctx.fillStyle = '#1a3a7a';
        ctx.beginPath();
        ctx.arc(32 * s, 92 * s, 7 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#1a3a7a', O, 2 * s);
        ctx.beginPath();
        ctx.arc(96 * s, 92 * s, 7 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#1a3a7a', O, 2 * s);

        // HEAD — cyborg helmet
        ctx.fillStyle = '#4169E1';
        ctx.beginPath();
        ctx.ellipse(64 * s, 38 * s, 22 * s, 18 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#4169E1', O, 2.5 * s);

        // VISOR — red glow
        ctx.fillStyle = '#FF0000';
        ctx.beginPath();
        ctx.roundRect(48 * s, 35 * s, 32 * s, 8 * s, 4 * s);
        fillStroke(ctx, '#FF0000', O, 2 * s);

        // VISOR GLOW
        ctx.fillStyle = W;
        ctx.beginPath();
        ctx.arc(56 * s, 39 * s, 2 * s, 0, Math.PI * 2);
        ctx.fill();
        ctx.beginPath();
        ctx.arc(72 * s, 39 * s, 2 * s, 0, Math.PI * 2);
        ctx.fill();

        // HEAD CREST
        ctx.fillStyle = '#2a5aC0';
        ctx.beginPath();
        ctx.moveTo(50 * s, 24 * s);
        ctx.lineTo(64 * s, 10 * s);
        ctx.lineTo(78 * s, 24 * s);
        ctx.closePath();
        fillStroke(ctx, '#2a5aC0', O, 2 * s);

        // MOUTH GRILL
        ctx.strokeStyle = '#1a3a7a';
        ctx.lineWidth = 1.5 * s;
        for (let i = 0; i < 3; i++) {
            const mx = 57 * s + i * 5 * s;
            ctx.beginPath();
            ctx.moveTo(mx, 48 * s);
            ctx.lineTo(mx, 52 * s);
            ctx.stroke();
        }
    }

    /* ── Virus-type Digimon ── */

    function drawDevimon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 118 * s, 20 * s, 6 * s);

        // BAT WINGS — large demon wings
        ctx.fillStyle = '#191970';
        for (let side = -1; side <= 1; side += 2) {
            const wx = 64 * s + side * 18 * s;
            ctx.beginPath();
            ctx.moveTo(wx, 35 * s);
            ctx.bezierCurveTo(
                wx - side * 30 * s, 5 * s,
                wx - side * 35 * s, 70 * s,
                wx - side * 12 * s, 85 * s
            );
            ctx.lineTo(wx + side * 2 * s, 70 * s);
            ctx.closePath();
            fillStroke(ctx, '#191970', O, 2.5 * s);

            // Wing ribs
            ctx.strokeStyle = '#4a00a0';
            ctx.lineWidth = 1.5 * s;
            ctx.beginPath();
            ctx.moveTo(wx, 40 * s);
            ctx.quadraticCurveTo(wx - side * 22 * s, 45 * s, wx - side * 15 * s, 65 * s);
            ctx.stroke();
        }

        // LEGS
        ctx.fillStyle = '#191970';
        ctx.beginPath();
        ctx.roundRect(50 * s, 96 * s, 12 * s, 20 * s, 3 * s);
        fillStroke(ctx, '#191970', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(66 * s, 96 * s, 12 * s, 20 * s, 3 * s);
        fillStroke(ctx, '#191970', O, 2.5 * s);

        // BODY
        ctx.fillStyle = '#191970';
        ctx.beginPath();
        ctx.ellipse(64 * s, 78 * s, 22 * s, 26 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#191970', O, 2.5 * s);

        // BELT / MARKINGS
        ctx.strokeStyle = '#DC143C';
        ctx.lineWidth = 2.5 * s;
        ctx.beginPath();
        ctx.moveTo(44 * s, 85 * s);
        ctx.lineTo(84 * s, 85 * s);
        ctx.stroke();

        // ARMS — muscular
        ctx.fillStyle = '#191970';
        ctx.beginPath();
        ctx.roundRect(30 * s, 62 * s, 14 * s, 30 * s, 5 * s);
        fillStroke(ctx, '#191970', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(84 * s, 62 * s, 14 * s, 30 * s, 5 * s);
        fillStroke(ctx, '#191970', O, 2.5 * s);

        // CLAWS
        ctx.fillStyle = '#DC143C';
        for (let side = -1; side <= 1; side += 2) {
            const cx = 37 * s + side * 54 * s;
            ctx.beginPath();
            ctx.moveTo(cx - 5 * s, 92 * s);
            ctx.lineTo(cx - 6 * s, 102 * s);
            ctx.lineTo(cx, 96 * s);
            ctx.lineTo(cx + 6 * s, 102 * s);
            ctx.lineTo(cx + 5 * s, 92 * s);
            ctx.closePath();
            fillStroke(ctx, '#DC143C', O, 2 * s);
        }

        // HEAD
        ctx.fillStyle = '#191970';
        ctx.beginPath();
        ctx.arc(64 * s, 44 * s, 20 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#191970', O, 2.5 * s);

        // HORNS
        ctx.fillStyle = '#2a2a8a';
        for (let side = -1; side <= 1; side += 2) {
            ctx.beginPath();
            ctx.moveTo(64 * s + side * 12 * s, 32 * s);
            ctx.lineTo(64 * s + side * 20 * s, 8 * s);
            ctx.lineTo(64 * s + side * 16 * s, 32 * s);
            ctx.closePath();
            fillStroke(ctx, '#2a2a8a', O, 2.5 * s);
        }

        // EVIL EYES — narrow sinister blood red, NO highlights (menacing)
        // Left eye
        ctx.fillStyle = W;
        ctx.beginPath();
        ctx.ellipse(52 * s, 42 * s, 6 * s, 10 * s, -0.15, 0, Math.PI * 2);
        fillStroke(ctx, W, O, 2 * s);
        ctx.fillStyle = '#FF0000';
        ctx.beginPath();
        ctx.ellipse(51 * s, 43 * s, 4.5 * s, 7 * s, -0.1, 0, Math.PI * 2);
        fillStroke(ctx, '#FF0000', O, 1.5 * s);
        ctx.fillStyle = '#4a00a0';
        ctx.beginPath();
        ctx.ellipse(51 * s, 43 * s, 2.5 * s, 4 * s, -0.1, 0, Math.PI * 2);
        ctx.fill();
        // Single small red highlight
        ctx.fillStyle = '#FF6666';
        ctx.beginPath();
        ctx.arc(50 * s, 40 * s, 1 * s, 0, Math.PI * 2);
        ctx.fill();

        // Right eye
        ctx.fillStyle = W;
        ctx.beginPath();
        ctx.ellipse(76 * s, 42 * s, 6 * s, 10 * s, 0.15, 0, Math.PI * 2);
        fillStroke(ctx, W, O, 2 * s);
        ctx.fillStyle = '#FF0000';
        ctx.beginPath();
        ctx.ellipse(77 * s, 43 * s, 4.5 * s, 7 * s, 0.1, 0, Math.PI * 2);
        fillStroke(ctx, '#FF0000', O, 1.5 * s);
        ctx.fillStyle = '#4a00a0';
        ctx.beginPath();
        ctx.ellipse(77 * s, 43 * s, 2.5 * s, 4 * s, 0.1, 0, Math.PI * 2);
        ctx.fill();
        // Single small red highlight
        ctx.fillStyle = '#FF6666';
        ctx.beginPath();
        ctx.arc(78 * s, 40 * s, 1 * s, 0, Math.PI * 2);
        ctx.fill();

        // MOUTH — wicked grin
        ctx.strokeStyle = O;
        ctx.lineWidth = 2 * s;
        ctx.beginPath();
        ctx.moveTo(52 * s, 54 * s);
        ctx.quadraticCurveTo(64 * s, 62 * s, 76 * s, 54 * s);
        ctx.stroke();

        // FANGS
        ctx.fillStyle = W;
        ctx.beginPath();
        ctx.moveTo(54 * s, 56 * s);
        ctx.lineTo(50 * s, 52 * s);
        ctx.lineTo(56 * s, 54 * s);
        ctx.fill();
        ctx.strokeStyle = O; ctx.lineWidth = 1 * s; ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(74 * s, 56 * s);
        ctx.lineTo(78 * s, 52 * s);
        ctx.lineTo(72 * s, 54 * s);
        ctx.fill();
        ctx.stroke();

        // EMBLEM on chest
        ctx.fillStyle = '#DC143C';
        ctx.beginPath();
        ctx.moveTo(64 * s, 68 * s);
        ctx.quadraticCurveTo(56 * s, 75 * s, 64 * s, 82 * s);
        ctx.quadraticCurveTo(72 * s, 75 * s, 64 * s, 68 * s);
        ctx.closePath();
        fillStroke(ctx, '#DC143C', O, 1.5 * s);
    }

    function drawOgremon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 118 * s, 20 * s, 8 * s);

        // LEGS
        ctx.fillStyle = '#556B2F';
        ctx.beginPath();
        ctx.roundRect(48 * s, 96 * s, 14 * s, 22 * s, 4 * s);
        fillStroke(ctx, '#556B2F', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(66 * s, 96 * s, 14 * s, 22 * s, 4 * s);
        fillStroke(ctx, '#556B2F', O, 2.5 * s);

        // FEET
        ctx.fillStyle = '#3a4a1a';
        ctx.beginPath();
        ctx.roundRect(44 * s, 114 * s, 20 * s, 6 * s, 2 * s);
        fillStroke(ctx, '#3a4a1a', O, 2 * s);
        ctx.beginPath();
        ctx.roundRect(62 * s, 114 * s, 20 * s, 6 * s, 2 * s);
        fillStroke(ctx, '#3a4a1a', O, 2 * s);

        // BODY — muscular green with gradient
        const ogrGrad = ctx.createLinearGradient(40 * s, 48 * s, 88 * s, 104 * s);
        ogrGrad.addColorStop(0, '#6B8B3F');
        ogrGrad.addColorStop(1, '#3A4A1A');
        ctx.fillStyle = ogrGrad;
        ctx.beginPath();
        ctx.ellipse(64 * s, 76 * s, 24 * s, 28 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#556B2F', O, 2.5 * s);

        // BELT
        ctx.strokeStyle = '#8B4513';
        ctx.lineWidth = 4 * s;
        ctx.beginPath();
        ctx.moveTo(42 * s, 88 * s);
        ctx.lineTo(86 * s, 88 * s);
        ctx.stroke();

        // MUSCLE CHEST LINES
        ctx.strokeStyle = '#3a4a1a';
        ctx.lineWidth = 2 * s;
        ctx.beginPath();
        ctx.moveTo(64 * s, 68 * s);
        ctx.quadraticCurveTo(54 * s, 78 * s, 58 * s, 86 * s);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(64 * s, 68 * s);
        ctx.quadraticCurveTo(74 * s, 78 * s, 70 * s, 86 * s);
        ctx.stroke();

        // ARMS — muscular
        ctx.fillStyle = '#556B2F';
        ctx.beginPath();
        ctx.roundRect(30 * s, 62 * s, 16 * s, 32 * s, 6 * s);
        fillStroke(ctx, '#556B2F', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(82 * s, 62 * s, 16 * s, 32 * s, 6 * s);
        fillStroke(ctx, '#556B2F', O, 2.5 * s);

        // BONE CLUB — left hand
        ctx.fillStyle = '#FFE4C4';
        ctx.beginPath();
        ctx.roundRect(22 * s, 88 * s, 20 * s, 8 * s, 4 * s);
        fillStroke(ctx, '#FFE4C4', O, 2 * s);

        // HEAD — ogre
        ctx.fillStyle = '#556B2F';
        ctx.beginPath();
        ctx.arc(64 * s, 44 * s, 20 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#556B2F', O, 2.5 * s);

        // HORN — brown
        ctx.fillStyle = '#8B4513';
        ctx.beginPath();
        ctx.moveTo(58 * s, 28 * s);
        ctx.lineTo(64 * s, 5 * s);
        ctx.lineTo(70 * s, 28 * s);
        ctx.closePath();
        fillStroke(ctx, '#8B4513', O, 2.5 * s);

        // HAIR — wild spikes
        ctx.fillStyle = '#FF6600';
        for (let i = 0; i < 4; i++) {
            const angle = -Math.PI / 2 + (i - 1.5) * 0.4;
            const hx = 64 * s + Math.cos(angle) * 18 * s;
            const hy = 44 * s + Math.sin(angle) * 18 * s;
            ctx.beginPath();
            ctx.moveTo(hx, hy);
            ctx.lineTo(hx + Math.cos(angle) * 15 * s, hy + Math.sin(angle) * 15 * s);
            ctx.lineTo(hx + Math.cos(angle + 0.2) * 6 * s, hy + Math.sin(angle + 0.2) * 6 * s);
            ctx.closePath();
            fillStroke(ctx, '#FF6600', O, 2 * s);
        }

        // FACE
        ctx.fillStyle = '#6B8B3F';
        ctx.beginPath();
        ctx.ellipse(64 * s, 50 * s, 12 * s, 10 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#6B8B3F', O, 2 * s);

        // ANGRY EYES
        ctx.fillStyle = W;
        ctx.beginPath();
        ctx.ellipse(52 * s, 43 * s, 6 * s, 7 * s, -0.2, 0, Math.PI * 2);
        fillStroke(ctx, W, O, 2 * s);
        ctx.fillStyle = '#FF0000';
        ctx.beginPath();
        ctx.arc(52 * s, 44 * s, 3.5 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#FF0000', O, 1.5 * s);
        ctx.fillStyle = O;
        ctx.beginPath();
        ctx.arc(52 * s, 44 * s, 1.8 * s, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = W;
        ctx.beginPath();
        ctx.ellipse(76 * s, 43 * s, 6 * s, 7 * s, 0.2, 0, Math.PI * 2);
        fillStroke(ctx, W, O, 2 * s);
        ctx.fillStyle = '#FF0000';
        ctx.beginPath();
        ctx.arc(76 * s, 44 * s, 3.5 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#FF0000', O, 1.5 * s);
        ctx.fillStyle = O;
        ctx.beginPath();
        ctx.arc(76 * s, 44 * s, 1.8 * s, 0, Math.PI * 2);
        ctx.fill();

        // MOUTH
        ctx.strokeStyle = O;
        ctx.lineWidth = 2 * s;
        ctx.beginPath();
        ctx.moveTo(55 * s, 55 * s);
        ctx.quadraticCurveTo(64 * s, 62 * s, 73 * s, 55 * s);
        ctx.stroke();
    }

    function drawLeomon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 118 * s, 22 * s, 8 * s);

        // LEGS
        ctx.fillStyle = '#DAA520';
        ctx.beginPath();
        ctx.roundRect(48 * s, 96 * s, 14 * s, 22 * s, 4 * s);
        fillStroke(ctx, '#DAA520', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(66 * s, 96 * s, 14 * s, 22 * s, 4 * s);
        fillStroke(ctx, '#DAA520', O, 2.5 * s);

        // BOOTS
        ctx.fillStyle = '#8B6914';
        ctx.beginPath();
        ctx.roundRect(44 * s, 112 * s, 20 * s, 8 * s, 3 * s);
        fillStroke(ctx, '#8B6914', O, 2 * s);
        ctx.beginPath();
        ctx.roundRect(62 * s, 112 * s, 20 * s, 8 * s, 3 * s);
        fillStroke(ctx, '#8B6914', O, 2 * s);

        // TAIL
        ctx.fillStyle = '#DAA520';
        ctx.beginPath();
        ctx.moveTo(86 * s, 90 * s);
        ctx.bezierCurveTo(105 * s, 88 * s, 112 * s, 72 * s, 102 * s, 65 * s);
        ctx.fill();
        ctx.strokeStyle = O; ctx.lineWidth = 2.5 * s; ctx.stroke();

        // BODY — golden lion body with gradient
        const leoGrad = ctx.createLinearGradient(40 * s, 52 * s, 88 * s, 104 * s);
        leoGrad.addColorStop(0, '#FFCC44');
        leoGrad.addColorStop(1, '#B8860B');
        ctx.fillStyle = leoGrad;
        ctx.beginPath();
        ctx.ellipse(64 * s, 78 * s, 24 * s, 26 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#DAA520', O, 2.5 * s);

        // BELT
        ctx.fillStyle = '#8B6914';
        ctx.beginPath();
        ctx.roundRect(42 * s, 84 * s, 44 * s, 6 * s, 3 * s);
        fillStroke(ctx, '#8B6914', O, 2 * s);
        ctx.fillStyle = '#FFD700';
        ctx.beginPath();
        ctx.arc(64 * s, 87 * s, 4 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#FFD700', O, 1.5 * s);

        // ARMS
        ctx.fillStyle = '#DAA520';
        ctx.beginPath();
        ctx.roundRect(30 * s, 62 * s, 16 * s, 30 * s, 5 * s);
        fillStroke(ctx, '#DAA520', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(82 * s, 62 * s, 16 * s, 30 * s, 5 * s);
        fillStroke(ctx, '#DAA520', O, 2.5 * s);

        // FISTS
        ctx.fillStyle = '#B8860B';
        ctx.beginPath();
        ctx.arc(38 * s, 94 * s, 7 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#B8860B', O, 2 * s);
        ctx.beginPath();
        ctx.arc(90 * s, 94 * s, 7 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#B8860B', O, 2 * s);

        // MANE — glorious mane
        for (let i = 0; i < 8; i++) {
            const angle = (i / 8) * Math.PI * 2;
            const mx = 64 * s + Math.cos(angle) * 16 * s;
            const my = 44 * s + Math.sin(angle) * 16 * s;
            const lx = 64 * s + Math.cos(angle) * 28 * s;
            const ly = 44 * s + Math.sin(angle) * 28 * s;
            ctx.fillStyle = '#FFA500';
            ctx.beginPath();
            ctx.moveTo(mx, my);
            ctx.lineTo(lx, ly);
            ctx.lineTo(mx + Math.cos(angle + 0.15) * 10 * s, my + Math.sin(angle + 0.15) * 10 * s);
            ctx.closePath();
            fillStroke(ctx, '#FFA500', O, 2 * s);
        }

        // HEAD
        ctx.fillStyle = '#DAA520';
        ctx.beginPath();
        ctx.arc(64 * s, 44 * s, 18 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#DAA520', O, 2.5 * s);

        // FACE
        ctx.fillStyle = '#FFD700';
        ctx.beginPath();
        ctx.ellipse(64 * s, 49 * s, 11 * s, 9 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FFD700', O, 1.5 * s);

        // NOSE
        ctx.fillStyle = '#8B6914';
        ctx.beginPath();
        ctx.arc(64 * s, 47 * s, 2.5 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#8B6914', O, 1.5 * s);

        // MOUTH
        ctx.strokeStyle = O;
        ctx.lineWidth = 2 * s;
        ctx.beginPath();
        ctx.moveTo(56 * s, 53 * s);
        ctx.quadraticCurveTo(64 * s, 58 * s, 72 * s, 53 * s);
        ctx.stroke();

        // EYES — fierce noble gold
        drawEye(ctx, 52 * s, 42 * s, '#FFD700', 7 * s, 3 * s, { shape: 'narrow', gazeX: 0.3 });
        drawEye(ctx, 76 * s, 42 * s, '#FFD700', 7 * s, 3 * s, { shape: 'narrow', gazeX: 0.3 });
    }

    /* ── Champion/Ultimate/Mega ── */

    function drawGreymon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 120 * s, 26 * s, 10 * s);

        // TAIL
        ctx.fillStyle = '#FF8C00';
        ctx.beginPath();
        ctx.moveTo(38 * s, 90 * s);
        ctx.bezierCurveTo(10 * s, 82 * s, 0 * s, 105 * s, 15 * s, 115 * s);
        ctx.lineTo(38 * s, 100 * s);
        ctx.closePath();
        fillStroke(ctx, '#FF8C00', O, 2.5 * s);

        // LEGS — large
        ctx.fillStyle = '#FF8C00';
        ctx.beginPath();
        ctx.roundRect(44 * s, 96 * s, 16 * s, 24 * s, 5 * s);
        fillStroke(ctx, '#FF8C00', O, 2.5 * s);
        ctx.fillStyle = '#CC6600';
        ctx.beginPath();
        ctx.roundRect(68 * s, 96 * s, 16 * s, 24 * s, 5 * s);
        fillStroke(ctx, '#CC6600', O, 2.5 * s);

        // FEET — big claws
        ctx.fillStyle = '#FFE4B5';
        ctx.beginPath();
        ctx.roundRect(40 * s, 115 * s, 22 * s, 7 * s, 3 * s);
        fillStroke(ctx, '#FFE4B5', O, 2 * s);
        ctx.beginPath();
        ctx.roundRect(64 * s, 115 * s, 22 * s, 7 * s, 3 * s);
        fillStroke(ctx, '#FFE4B5', O, 2 * s);

        // BODY — bigger with gradient
        const bodyGradG = ctx.createLinearGradient(40 * s, 46 * s, 88 * s, 110 * s);
        bodyGradG.addColorStop(0, '#FFAA33');
        bodyGradG.addColorStop(0.6, '#FF8C00');
        bodyGradG.addColorStop(1, '#CC6600');
        ctx.fillStyle = bodyGradG;
        ctx.beginPath();
        ctx.ellipse(64 * s, 78 * s, 28 * s, 32 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FF8C00', O, 2.5 * s);

        // BELLY
        ctx.fillStyle = '#FFD700';
        ctx.beginPath();
        ctx.ellipse(64 * s, 82 * s, 20 * s, 22 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FFD700', O, 2 * s);

        // BLUE STRIPES on body
        ctx.strokeStyle = '#1E90FF';
        ctx.lineWidth = 3 * s;
        for (let i = 0; i < 4; i++) {
            ctx.beginPath();
            ctx.moveTo(42 * s, 68 * s + i * 6 * s);
            ctx.quadraticCurveTo(64 * s, 62 * s + i * 6 * s, 86 * s, 68 * s + i * 6 * s);
            ctx.stroke();
        }

        // ARMS — muscular
        ctx.fillStyle = '#FF8C00';
        ctx.beginPath();
        ctx.roundRect(28 * s, 64 * s, 14 * s, 28 * s, 5 * s);
        fillStroke(ctx, '#FF8C00', O, 2.5 * s);
        ctx.fillStyle = '#CC6600';
        ctx.beginPath();
        ctx.roundRect(86 * s, 64 * s, 14 * s, 28 * s, 5 * s);
        fillStroke(ctx, '#CC6600', O, 2.5 * s);

        // CLAWS on hands
        ctx.fillStyle = '#FFE4B5';
        ctx.beginPath();
        ctx.roundRect(24 * s, 88 * s, 20 * s, 7 * s, 2 * s);
        fillStroke(ctx, '#FFE4B5', O, 2 * s);
        ctx.beginPath();
        ctx.roundRect(82 * s, 88 * s, 20 * s, 7 * s, 2 * s);
        fillStroke(ctx, '#FFE4B5', O, 2 * s);

        // HEAD — large with helmet crest, gradient
        const headGradG = ctx.createLinearGradient(64 * s, 20 * s, 64 * s, 64 * s);
        headGradG.addColorStop(0, '#FFAA33');
        headGradG.addColorStop(1, '#FF8C00');
        ctx.fillStyle = headGradG;
        ctx.beginPath();
        ctx.arc(64 * s, 42 * s, 22 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#FFAA33', O, 2.5 * s);

        // HELMET — brown crest
        ctx.fillStyle = '#8B4513';
        ctx.beginPath();
        ctx.moveTo(44 * s, 36 * s);
        ctx.lineTo(64 * s, 4 * s);
        ctx.lineTo(84 * s, 36 * s);
        ctx.closePath();
        fillStroke(ctx, '#8B4513', O, 2.5 * s);

        // Blue stripes on helmet
        ctx.strokeStyle = '#1E90FF';
        ctx.lineWidth = 2.5 * s;
        ctx.beginPath();
        ctx.moveTo(52 * s, 28 * s);
        ctx.lineTo(76 * s, 28 * s);
        ctx.stroke();

        // SNOUT
        ctx.fillStyle = '#FFB347';
        ctx.beginPath();
        ctx.ellipse(64 * s, 54 * s, 14 * s, 10 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FFB347', O, 2 * s);

        // MOUTH
        ctx.strokeStyle = O;
        ctx.lineWidth = 2 * s;
        ctx.beginPath();
        ctx.arc(64 * s, 56 * s, 7 * s, 0.2, Math.PI - 0.2);
        ctx.stroke();

        // FANGS
        ctx.fillStyle = W;
        ctx.beginPath();
        ctx.moveTo(58 * s, 58 * s);
        ctx.lineTo(55 * s, 63 * s);
        ctx.lineTo(61 * s, 59 * s);
        ctx.fill();
        ctx.strokeStyle = O; ctx.lineWidth = 1 * s; ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(70 * s, 58 * s);
        ctx.lineTo(73 * s, 63 * s);
        ctx.lineTo(67 * s, 59 * s);
        ctx.fill();
        ctx.stroke();

        // EYES — fierce green, angled
        drawEye(ctx, 52 * s, 40 * s, '#44FF44', 7.5 * s, 3 * s, { shape: 'round', angle: -0.12 });
        drawEye(ctx, 76 * s, 40 * s, '#44FF44', 7.5 * s, 3 * s, { shape: 'round', angle: 0.12 });

        // ANGRY EYEBROWS
        ctx.strokeStyle = '#8B4513';
        ctx.lineWidth = 3 * s;
        ctx.beginPath();
        ctx.moveTo(44 * s, 33 * s);
        ctx.lineTo(60 * s, 36 * s);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(84 * s, 33 * s);
        ctx.lineTo(68 * s, 36 * s);
        ctx.stroke();
    }

    function drawGarurumon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 118 * s, 22 * s, 8 * s);

        // TAIL
        ctx.fillStyle = '#4A6FA5';
        ctx.beginPath();
        ctx.moveTo(86 * s, 90 * s);
        ctx.bezierCurveTo(110 * s, 85 * s, 120 * s, 70 * s, 108 * s, 60 * s);
        ctx.fill();
        ctx.strokeStyle = O; ctx.lineWidth = 2.5 * s; ctx.stroke();

        // LEGS — quadruped stance
        ctx.fillStyle = '#4A6FA5';
        ctx.beginPath();
        ctx.roundRect(44 * s, 96 * s, 16 * s, 20 * s, 5 * s);
        fillStroke(ctx, '#4A6FA5', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(68 * s, 96 * s, 16 * s, 20 * s, 5 * s);
        fillStroke(ctx, '#4A6FA5', O, 2.5 * s);

        // PAWS
        ctx.fillStyle = '#E8E8F0';
        ctx.beginPath();
        ctx.roundRect(40 * s, 112 * s, 20 * s, 6 * s, 2 * s);
        fillStroke(ctx, '#E8E8F0', O, 2 * s);
        ctx.beginPath();
        ctx.roundRect(64 * s, 112 * s, 20 * s, 6 * s, 2 * s);
        fillStroke(ctx, '#E8E8F0', O, 2 * s);

        // BODY — elongated wolf with gradient
        const garGrad = ctx.createLinearGradient(40 * s, 58 * s, 88 * s, 102 * s);
        garGrad.addColorStop(0, '#5A80B5');
        garGrad.addColorStop(1, '#3A5A8A');
        ctx.fillStyle = garGrad;
        ctx.beginPath();
        ctx.ellipse(64 * s, 80 * s, 28 * s, 22 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#4A6FA5', O, 2.5 * s);

        // WHITE STRIPES on body
        ctx.strokeStyle = '#E8E8F0';
        ctx.lineWidth = 2.5 * s;
        ctx.setLineDash([4 * s, 6 * s]);
        ctx.beginPath();
        ctx.moveTo(44 * s, 78 * s);
        ctx.lineTo(84 * s, 78 * s);
        ctx.stroke();
        ctx.setLineDash([]);

        // FRONT LEGS
        ctx.fillStyle = '#4A6FA5';
        ctx.beginPath();
        ctx.roundRect(30 * s, 70 * s, 14 * s, 24 * s, 4 * s);
        fillStroke(ctx, '#4A6FA5', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(84 * s, 70 * s, 14 * s, 24 * s, 4 * s);
        fillStroke(ctx, '#4A6FA5', O, 2.5 * s);

        // HEAD — wolf head
        ctx.fillStyle = '#4A6FA5';
        ctx.beginPath();
        ctx.ellipse(64 * s, 48 * s, 22 * s, 18 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#4A6FA5', O, 2.5 * s);

        // SNOUT
        ctx.fillStyle = '#E8E8F0';
        ctx.beginPath();
        ctx.ellipse(64 * s, 56 * s, 14 * s, 9 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#E8E8F0', O, 2 * s);

        // NOSE
        ctx.fillStyle = O;
        ctx.beginPath();
        ctx.arc(64 * s, 54 * s, 2.5 * s, 0, Math.PI * 2);
        fillStroke(ctx, O, O, 1 * s);

        // MOUTH
        ctx.strokeStyle = O;
        ctx.lineWidth = 2 * s;
        ctx.beginPath();
        ctx.arc(64 * s, 58 * s, 5 * s, 0.2, Math.PI - 0.2);
        ctx.stroke();

        // EARS — triangular
        for (let side = -1; side <= 1; side += 2) {
            ctx.fillStyle = '#4A6FA5';
            ctx.beginPath();
            ctx.moveTo(64 * s + side * 12 * s, 36 * s);
            ctx.lineTo(64 * s + side * 22 * s, 14 * s);
            ctx.lineTo(64 * s + side * 22 * s, 38 * s);
            ctx.closePath();
            fillStroke(ctx, '#4A6FA5', O, 2.5 * s);
        }

        // EYES — piercing ice blue wolf, narrow
        drawEye(ctx, 52 * s, 46 * s, '#5BB5FF', 7 * s, 3 * s, { shape: 'narrow', gazeX: 0.4 });
        drawEye(ctx, 76 * s, 46 * s, '#5BB5FF', 7 * s, 3 * s, { shape: 'narrow', gazeX: 0.4 });
    }

    function drawKabuterimon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 118 * s, 22 * s, 8 * s);

        // LEGS — insect legs
        for (let i = 0; i < 2; i++) {
            const lx = 48 * s + i * 16 * s;
            ctx.strokeStyle = '#4B0082';
            ctx.lineWidth = 4 * s;
            ctx.beginPath();
            ctx.moveTo(lx, 96 * s);
            ctx.lineTo(lx - 4 * s, 116 * s);
            ctx.stroke();
            ctx.strokeStyle = O;
            ctx.lineWidth = 6 * s;
            ctx.stroke();
            ctx.strokeStyle = '#4B0082';
            ctx.lineWidth = 4 * s;
            ctx.stroke();

            ctx.beginPath();
            ctx.moveTo(lx + 8 * s, 96 * s);
            ctx.lineTo(lx + 12 * s, 116 * s);
            ctx.stroke();
            ctx.strokeStyle = O;
            ctx.lineWidth = 6 * s;
            ctx.stroke();
            ctx.strokeStyle = '#4B0082';
            ctx.lineWidth = 4 * s;
            ctx.stroke();
        }

        // BODY — large beetle shell
        ctx.fillStyle = '#4B0082';
        ctx.beginPath();
        ctx.ellipse(64 * s, 76 * s, 30 * s, 22 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#4B0082', O, 2.5 * s);

        // SHELL LINES
        ctx.strokeStyle = '#9370DB';
        ctx.lineWidth = 2 * s;
        ctx.beginPath();
        ctx.moveTo(64 * s, 56 * s);
        ctx.lineTo(64 * s, 96 * s);
        ctx.stroke();

        // WINGS SHELL DETAIL
        ctx.fillStyle = '#6B2AAB';
        ctx.beginPath();
        ctx.ellipse(48 * s, 76 * s, 14 * s, 18 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#6B2AAB', O, 1.5 * s);
        ctx.beginPath();
        ctx.ellipse(80 * s, 76 * s, 14 * s, 18 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#6B2AAB', O, 1.5 * s);

        // ARMS
        ctx.fillStyle = '#4B0082';
        ctx.beginPath();
        ctx.roundRect(32 * s, 66 * s, 12 * s, 22 * s, 4 * s);
        fillStroke(ctx, '#4B0082', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(84 * s, 66 * s, 12 * s, 22 * s, 4 * s);
        fillStroke(ctx, '#4B0082', O, 2.5 * s);

        // HEAD
        ctx.fillStyle = '#4B0082';
        ctx.beginPath();
        ctx.ellipse(64 * s, 44 * s, 20 * s, 16 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#4B0082', O, 2.5 * s);

        // BIG HORN
        ctx.fillStyle = '#9370DB';
        ctx.beginPath();
        ctx.moveTo(56 * s, 34 * s);
        ctx.lineTo(64 * s, 2 * s);
        ctx.lineTo(72 * s, 34 * s);
        ctx.closePath();
        fillStroke(ctx, '#9370DB', O, 2.5 * s);

        // COMPOUND EYES — red
        ctx.fillStyle = '#FF0000';
        ctx.beginPath();
        ctx.ellipse(50 * s, 44 * s, 7 * s, 9 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FF0000', O, 2 * s);
        ctx.fillStyle = W;
        ctx.beginPath();
        ctx.arc(48 * s, 42 * s, 2 * s, 0, Math.PI * 2);
        ctx.fill();

        ctx.beginPath();
        ctx.ellipse(78 * s, 44 * s, 7 * s, 9 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FF0000', O, 2 * s);
        ctx.fillStyle = W;
        ctx.beginPath();
        ctx.arc(80 * s, 42 * s, 2 * s, 0, Math.PI * 2);
        ctx.fill();
    }

    function drawTogemon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 118 * s, 20 * s, 8 * s);

        // BODY — green cactus
        ctx.fillStyle = '#32CD32';
        ctx.beginPath();
        ctx.ellipse(64 * s, 78 * s, 22 * s, 30 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#32CD32', O, 2.5 * s);

        // CACTUS SPINES
        ctx.strokeStyle = '#1a7a1a';
        ctx.lineWidth = 1.5 * s;
        for (let i = 0; i < 10; i++) {
            const angle = (i / 10) * Math.PI * 2;
            const cx = 64 * s + Math.cos(angle) * 22 * s;
            const cy = 78 * s + Math.sin(angle) * 30 * s;
            ctx.beginPath();
            ctx.moveTo(cx, cy);
            ctx.lineTo(cx + Math.cos(angle) * 5 * s, cy + Math.sin(angle) * 5 * s);
            ctx.stroke();
        }

        // LEGS
        ctx.fillStyle = '#32CD32';
        ctx.beginPath();
        ctx.roundRect(50 * s, 100 * s, 12 * s, 16 * s, 3 * s);
        fillStroke(ctx, '#32CD32', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(66 * s, 100 * s, 12 * s, 16 * s, 3 * s);
        fillStroke(ctx, '#32CD32', O, 2.5 * s);

        // BOXING GLOVES — red
        ctx.fillStyle = '#FF6347';
        ctx.beginPath();
        ctx.arc(36 * s, 84 * s, 12 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#FF6347', O, 2.5 * s);
        ctx.beginPath();
        ctx.arc(92 * s, 84 * s, 12 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#FF6347', O, 2.5 * s);

        // GLOVE THUMB
        ctx.fillStyle = '#FF4500';
        ctx.beginPath();
        ctx.arc(30 * s, 78 * s, 5 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#FF4500', O, 1.5 * s);
        ctx.beginPath();
        ctx.arc(98 * s, 78 * s, 5 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#FF4500', O, 1.5 * s);

        // HEAD
        ctx.fillStyle = '#32CD32';
        ctx.beginPath();
        ctx.arc(64 * s, 44 * s, 18 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#32CD32', O, 2.5 * s);

        // FLOWER on head
        ctx.fillStyle = '#FF6347';
        for (let i = 0; i < 6; i++) {
            const angle = (i / 6) * Math.PI * 2;
            const px = 64 * s + Math.cos(angle) * 10 * s;
            const py = 36 * s + Math.sin(angle) * 10 * s;
            ctx.beginPath();
            ctx.ellipse(px, py, 7 * s, 4 * s, angle + Math.PI / 2, 0, Math.PI * 2);
            fillStroke(ctx, '#FF6347', O, 1.5 * s);
        }
        // Flower center
        ctx.fillStyle = '#FFD700';
        ctx.beginPath();
        ctx.arc(64 * s, 36 * s, 5 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#FFD700', O, 1.5 * s);

        // FACE
        ctx.fillStyle = '#90EE90';
        ctx.beginPath();
        ctx.ellipse(64 * s, 48 * s, 10 * s, 8 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#90EE90', O, 1.5 * s);

        // MOUTH
        ctx.strokeStyle = O;
        ctx.lineWidth = 1.5 * s;
        ctx.beginPath();
        ctx.arc(64 * s, 50 * s, 3 * s, 0.1, Math.PI - 0.1);
        ctx.stroke();

        // EYES — round dark green
        drawEye(ctx, 54 * s, 44 * s, '#1a7a1a', 6 * s, 2.5 * s, { shape: 'round', gazeX: 0.3 });
        drawEye(ctx, 74 * s, 44 * s, '#1a7a1a', 6 * s, 2.5 * s, { shape: 'round', gazeX: 0.3 });
    }

    function drawAngemon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 118 * s, 16 * s, 6 * s);

        // WINGS — 6 wings, 3 per side
        for (let side = -1; side <= 1; side += 2) {
            for (let w = 0; w < 3; w++) {
                const wx = 64 * s + side * (12 * s + w * 4 * s);
                const wy = 38 * s + w * 8 * s;
                ctx.fillStyle = '#FFFFFF';
                ctx.beginPath();
                ctx.moveTo(wx, wy);
                ctx.bezierCurveTo(
                    wx - side * 25 * s + w * 4 * s, wy - 15 * s,
                    wx - side * 30 * s + w * 5 * s, wy + 25 * s,
                    wx - side * 10 * s, wy + 20 * s
                );
                ctx.lineTo(wx, wy + 5 * s);
                ctx.closePath();
                fillStroke(ctx, '#FFFFFF', O, 2 * s);
            }
        }

        // LEGS
        ctx.fillStyle = '#F5F5F5';
        ctx.beginPath();
        ctx.roundRect(54 * s, 98 * s, 8 * s, 18 * s, 3 * s);
        fillStroke(ctx, '#F5F5F5', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(66 * s, 98 * s, 8 * s, 18 * s, 3 * s);
        fillStroke(ctx, '#F5F5F5', O, 2.5 * s);

        // BODY — white/silver with holy gradient
        const angGrad = ctx.createLinearGradient(46 * s, 56 * s, 82 * s, 104 * s);
        angGrad.addColorStop(0, '#FFFFFF');
        angGrad.addColorStop(1, '#E0E0E8');
        ctx.fillStyle = angGrad;
        ctx.beginPath();
        ctx.ellipse(64 * s, 80 * s, 18 * s, 24 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#F5F5F5', O, 2.5 * s);

        // CHEST ARMOR
        ctx.fillStyle = '#D0D0D0';
        ctx.beginPath();
        ctx.roundRect(52 * s, 72 * s, 24 * s, 12 * s, 4 * s);
        fillStroke(ctx, '#D0D0D0', O, 2 * s);

        // BELT
        ctx.fillStyle = '#FFD700';
        ctx.beginPath();
        ctx.roundRect(52 * s, 88 * s, 24 * s, 4 * s, 2 * s);
        fillStroke(ctx, '#FFD700', O, 1.5 * s);

        // ARMS
        ctx.fillStyle = '#F5F5F5';
        ctx.beginPath();
        ctx.roundRect(40 * s, 72 * s, 8 * s, 18 * s, 3 * s);
        fillStroke(ctx, '#F5F5F5', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(80 * s, 72 * s, 8 * s, 18 * s, 3 * s);
        fillStroke(ctx, '#F5F5F5', O, 2.5 * s);

        // HEAD
        ctx.fillStyle = '#F5F5F5';
        ctx.beginPath();
        ctx.arc(64 * s, 44 * s, 16 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#F5F5F5', O, 2.5 * s);

        // HELMET
        ctx.fillStyle = '#D0D0D0';
        ctx.beginPath();
        ctx.arc(64 * s, 42 * s, 17 * s, Math.PI + 0.5, -0.5);
        ctx.fill();
        ctx.strokeStyle = O; ctx.lineWidth = 2.5 * s; ctx.stroke();

        // HOLY RING — gold halo
        ctx.strokeStyle = '#FFD700';
        ctx.lineWidth = 2.5 * s;
        ctx.beginPath();
        ctx.arc(64 * s, 20 * s, 8 * s, 0, Math.PI * 2);
        ctx.stroke();

        // FACE
        ctx.fillStyle = '#FFFFFF';
        ctx.beginPath();
        ctx.ellipse(64 * s, 48 * s, 9 * s, 8 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FFFFFF', O, 1.5 * s);

        // MOUTH
        ctx.strokeStyle = O;
        ctx.lineWidth = 1.5 * s;
        ctx.beginPath();
        ctx.arc(64 * s, 50 * s, 3 * s, 0.1, Math.PI - 0.1);
        ctx.stroke();

        // EYES — serene blue, noble gaze
        drawEye(ctx, 55 * s, 44 * s, '#87CEEB', 5.5 * s, 2.5 * s, { shape: 'round', gazeX: 0.3 });
        drawEye(ctx, 73 * s, 44 * s, '#87CEEB', 5.5 * s, 2.5 * s, { shape: 'round', gazeX: 0.3 });
    }

    function drawBirdramon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 118 * s, 22 * s, 8 * s);

        // LEGS — bird talons
        ctx.fillStyle = '#FF6347';
        ctx.beginPath();
        ctx.roundRect(52 * s, 100 * s, 10 * s, 16 * s, 3 * s);
        fillStroke(ctx, '#FF6347', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(66 * s, 100 * s, 10 * s, 16 * s, 3 * s);
        fillStroke(ctx, '#FF6347', O, 2.5 * s);

        // TALONS
        for (let i = 0; i < 2; i++) {
            const tx = 58 * s + i * 12 * s;
            ctx.fillStyle = '#FFD700';
            ctx.beginPath();
            ctx.moveTo(tx - 4 * s, 116 * s);
            ctx.lineTo(tx - 5 * s, 108 * s);
            ctx.lineTo(tx, 114 * s);
            ctx.lineTo(tx + 5 * s, 108 * s);
            ctx.lineTo(tx + 4 * s, 116 * s);
            ctx.closePath();
            fillStroke(ctx, '#FFD700', O, 1.5 * s);
        }

        // BODY — flame gradient
        const birGrad = ctx.createLinearGradient(40 * s, 54 * s, 88 * s, 106 * s);
        birGrad.addColorStop(0, '#FF8040');
        birGrad.addColorStop(1, '#CC3300');
        ctx.fillStyle = birGrad;
        ctx.beginPath();
        ctx.ellipse(64 * s, 80 * s, 24 * s, 26 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FF6347', O, 2.5 * s);

        // FLAME MARKINGS
        ctx.strokeStyle = '#FFD700';
        ctx.lineWidth = 2.5 * s;
        ctx.beginPath();
        ctx.moveTo(48 * s, 74 * s);
        ctx.quadraticCurveTo(64 * s, 68 * s, 80 * s, 74 * s);
        ctx.quadraticCurveTo(64 * s, 78 * s, 48 * s, 74 * s);
        ctx.stroke();

        // WINGS — large flaming wings
        ctx.fillStyle = '#FF6347';
        for (let side = -1; side <= 1; side += 2) {
            ctx.beginPath();
            ctx.moveTo(64 * s + side * 12 * s, 55 * s);
            ctx.bezierCurveTo(
                64 * s + side * 45 * s, 30 * s,
                64 * s + side * 50 * s, 95 * s,
                64 * s + side * 15 * s, 90 * s
            );
            ctx.closePath();
            fillStroke(ctx, '#FF6347', O, 2.5 * s);

            // Wing flame pattern
            ctx.strokeStyle = '#FF4500';
            ctx.lineWidth = 2 * s;
            ctx.beginPath();
            ctx.moveTo(64 * s + side * 18 * s, 60 * s);
            ctx.quadraticCurveTo(64 * s + side * 35 * s, 65 * s, 64 * s + side * 20 * s, 80 * s);
            ctx.stroke();
        }

        // HEAD
        ctx.fillStyle = '#FF6347';
        ctx.beginPath();
        ctx.arc(64 * s, 44 * s, 18 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#FF6347', O, 2.5 * s);

        // CREST
        ctx.fillStyle = '#FFD700';
        ctx.beginPath();
        ctx.moveTo(56 * s, 32 * s);
        ctx.quadraticCurveTo(64 * s, 8 * s, 72 * s, 32 * s);
        ctx.closePath();
        fillStroke(ctx, '#FFD700', O, 2.5 * s);

        // BEAK
        ctx.fillStyle = '#FFD700';
        ctx.beginPath();
        ctx.moveTo(54 * s, 46 * s);
        ctx.lineTo(64 * s, 56 * s);
        ctx.lineTo(74 * s, 46 * s);
        ctx.closePath();
        fillStroke(ctx, '#FFD700', O, 2 * s);

        // EYES — fiery gold
        drawEye(ctx, 52 * s, 42 * s, '#FFD700', 6.5 * s, 3 * s, { shape: 'narrow', gazeX: 0.4 });
        drawEye(ctx, 76 * s, 42 * s, '#FFD700', 6.5 * s, 3 * s, { shape: 'narrow', gazeX: 0.4 });
    }

    function drawGarudamon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 120 * s, 24 * s, 8 * s);

        // LEGS
        ctx.fillStyle = '#FFD700';
        ctx.beginPath();
        ctx.roundRect(48 * s, 98 * s, 14 * s, 20 * s, 4 * s);
        fillStroke(ctx, '#FFD700', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(66 * s, 98 * s, 14 * s, 20 * s, 4 * s);
        fillStroke(ctx, '#FFD700', O, 2.5 * s);

        // GIANT WINGS
        ctx.fillStyle = '#FFD700';
        for (let side = -1; side <= 1; side += 2) {
            ctx.beginPath();
            ctx.moveTo(64 * s + side * 14 * s, 45 * s);
            ctx.bezierCurveTo(
                64 * s + side * 48 * s, 15 * s,
                64 * s + side * 52 * s, 100 * s,
                64 * s + side * 16 * s, 95 * s
            );
            ctx.closePath();
            fillStroke(ctx, '#FFD700', O, 2.5 * s);

            // Wing feather detail
            ctx.strokeStyle = '#FFA500';
            ctx.lineWidth = 2 * s;
            ctx.beginPath();
            ctx.moveTo(64 * s + side * 20 * s, 52 * s);
            ctx.quadraticCurveTo(64 * s + side * 40 * s, 62 * s, 64 * s + side * 22 * s, 80 * s);
            ctx.stroke();
        }

        // BODY
        ctx.fillStyle = '#FFD700';
        ctx.beginPath();
        ctx.ellipse(64 * s, 78 * s, 26 * s, 28 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FFD700', O, 2.5 * s);

        // CHEST ARMOR
        ctx.fillStyle = '#FFA500';
        ctx.beginPath();
        ctx.roundRect(48 * s, 68 * s, 32 * s, 20 * s, 6 * s);
        fillStroke(ctx, '#FFA500', O, 2.5 * s);

        // HEAD CREST — phoenix-like
        ctx.fillStyle = '#FFD700';
        ctx.beginPath();
        ctx.moveTo(52 * s, 34 * s);
        ctx.quadraticCurveTo(64 * s, 4 * s, 76 * s, 34 * s);
        ctx.closePath();
        fillStroke(ctx, '#FFD700', O, 2.5 * s);

        // HEAD FEATHERS
        ctx.fillStyle = '#FF6347';
        ctx.beginPath();
        ctx.moveTo(54 * s, 30 * s);
        ctx.quadraticCurveTo(50 * s, 12 * s, 58 * s, 20 * s);
        ctx.quadraticCurveTo(60 * s, 14 * s, 62 * s, 22 * s);
        ctx.closePath();
        fillStroke(ctx, '#FF6347', O, 2 * s);

        // HEAD
        ctx.fillStyle = '#FFD700';
        ctx.beginPath();
        ctx.arc(64 * s, 42 * s, 18 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#FFD700', O, 2.5 * s);

        // BEAK
        ctx.fillStyle = '#FF6347';
        ctx.beginPath();
        ctx.moveTo(54 * s, 44 * s);
        ctx.lineTo(64 * s, 54 * s);
        ctx.lineTo(74 * s, 44 * s);
        ctx.closePath();
        fillStroke(ctx, '#FF6347', O, 2 * s);

        // EYES — fierce red-orange, sharp angled
        drawEye(ctx, 52 * s, 40 * s, '#FF6347', 7 * s, 3 * s, { shape: 'narrow', angle: -0.1 });
        drawEye(ctx, 76 * s, 40 * s, '#FF6347', 7 * s, 3 * s, { shape: 'narrow', angle: 0.1 });

        // ARMS
        ctx.fillStyle = '#FFD700';
        ctx.beginPath();
        ctx.roundRect(32 * s, 64 * s, 14 * s, 28 * s, 5 * s);
        fillStroke(ctx, '#FFD700', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(82 * s, 64 * s, 14 * s, 28 * s, 5 * s);
        fillStroke(ctx, '#FFD700', O, 2.5 * s);
    }

    function drawMetalGreymon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 120 * s, 26 * s, 10 * s);

        // TAIL — mechanical
        ctx.fillStyle = '#B0B0B0';
        ctx.beginPath();
        ctx.moveTo(36 * s, 88 * s);
        ctx.bezierCurveTo(8 * s, 78 * s, 0 * s, 108 * s, 18 * s, 118 * s);
        ctx.lineTo(38 * s, 100 * s);
        ctx.closePath();
        fillStroke(ctx, '#B0B0B0', O, 2.5 * s);

        // LEGS — mechanical
        ctx.fillStyle = '#B0B0B0';
        ctx.beginPath();
        ctx.roundRect(44 * s, 96 * s, 16 * s, 24 * s, 4 * s);
        fillStroke(ctx, '#B0B0B0', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(68 * s, 96 * s, 16 * s, 24 * s, 4 * s);
        fillStroke(ctx, '#B0B0B0', O, 2.5 * s);

        // BODY — orange with metal armor, gradient
        const metaGrad = ctx.createLinearGradient(38 * s, 48 * s, 90 * s, 108 * s);
        metaGrad.addColorStop(0, '#FFAA33');
        metaGrad.addColorStop(0.5, '#FF8C00');
        metaGrad.addColorStop(1, '#CC6600');
        ctx.fillStyle = metaGrad;
        ctx.beginPath();
        ctx.ellipse(64 * s, 78 * s, 26 * s, 30 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FF8C00', O, 2.5 * s);

        // METAL CHEST ARMOR
        ctx.fillStyle = '#B0B0B0';
        ctx.beginPath();
        ctx.roundRect(44 * s, 68 * s, 40 * s, 22 * s, 6 * s);
        fillStroke(ctx, '#B0B0B0', O, 2.5 * s);

        // CHEST CANNONS
        ctx.fillStyle = '#606060';
        ctx.beginPath();
        ctx.arc(52 * s, 76 * s, 6 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#606060', O, 2 * s);
        ctx.beginPath();
        ctx.arc(76 * s, 76 * s, 6 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#606060', O, 2 * s);

        // METAL ARM — left
        ctx.fillStyle = '#B0B0B0';
        ctx.beginPath();
        ctx.roundRect(28 * s, 64 * s, 14 * s, 30 * s, 4 * s);
        fillStroke(ctx, '#B0B0B0', O, 2.5 * s);

        // CANNON HAND
        ctx.fillStyle = '#606060';
        ctx.beginPath();
        ctx.roundRect(24 * s, 88 * s, 22 * s, 10 * s, 4 * s);
        fillStroke(ctx, '#606060', O, 2 * s);

        // RIGHT ARM — flesh
        ctx.fillStyle = '#FF8C00';
        ctx.beginPath();
        ctx.roundRect(86 * s, 64 * s, 14 * s, 30 * s, 5 * s);
        fillStroke(ctx, '#FF8C00', O, 2.5 * s);
        ctx.fillStyle = '#CC6600';
        ctx.beginPath();
        ctx.roundRect(84 * s, 88 * s, 18 * s, 8 * s, 3 * s);
        fillStroke(ctx, '#CC6600', O, 2 * s);

        // HEAD — helmet
        ctx.fillStyle = '#FF8C00';
        ctx.beginPath();
        ctx.arc(64 * s, 42 * s, 20 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#FF8C00', O, 2.5 * s);

        // METAL HELMET
        ctx.fillStyle = '#B0B0B0';
        ctx.beginPath();
        ctx.moveTo(44 * s, 36 * s);
        ctx.lineTo(64 * s, 6 * s);
        ctx.lineTo(84 * s, 36 * s);
        ctx.closePath();
        fillStroke(ctx, '#B0B0B0', O, 2.5 * s);

        // BLUE EYE SENSOR
        ctx.fillStyle = '#1E90FF';
        ctx.beginPath();
        ctx.ellipse(64 * s, 36 * s, 6 * s, 4 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#1E90FF', O, 2 * s);

        // SNOUT
        ctx.fillStyle = '#FFB347';
        ctx.beginPath();
        ctx.ellipse(64 * s, 52 * s, 12 * s, 8 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FFB347', O, 2 * s);

        // MOUTH
        ctx.strokeStyle = O;
        ctx.lineWidth = 2 * s;
        ctx.beginPath();
        ctx.arc(64 * s, 55 * s, 5 * s, 0.2, Math.PI - 0.2);
        ctx.stroke();

        // MISSILE WINGS
        ctx.fillStyle = '#A0A0A0';
        ctx.beginPath();
        ctx.moveTo(40 * s, 56 * s);
        ctx.lineTo(18 * s, 42 * s);
        ctx.lineTo(24 * s, 62 * s);
        ctx.closePath();
        fillStroke(ctx, '#A0A0A0', O, 2 * s);
        ctx.beginPath();
        ctx.moveTo(88 * s, 56 * s);
        ctx.lineTo(110 * s, 42 * s);
        ctx.lineTo(104 * s, 62 * s);
        ctx.closePath();
        fillStroke(ctx, '#A0A0A0', O, 2 * s);
    }

    function drawWeregarurumon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 120 * s, 22 * s, 8 * s);

        // LEGS — muscular wolfman
        ctx.fillStyle = '#4A6FA5';
        ctx.beginPath();
        ctx.roundRect(48 * s, 94 * s, 14 * s, 24 * s, 4 * s);
        fillStroke(ctx, '#4A6FA5', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(66 * s, 94 * s, 14 * s, 24 * s, 4 * s);
        fillStroke(ctx, '#4A6FA5', O, 2.5 * s);

        // BOOTS
        ctx.fillStyle = '#2A4A7A';
        ctx.beginPath();
        ctx.roundRect(44 * s, 112 * s, 20 * s, 8 * s, 3 * s);
        fillStroke(ctx, '#2A4A7A', O, 2 * s);
        ctx.beginPath();
        ctx.roundRect(62 * s, 112 * s, 20 * s, 8 * s, 3 * s);
        fillStroke(ctx, '#2A4A7A', O, 2 * s);

        // TAIL
        ctx.fillStyle = '#4A6FA5';
        ctx.beginPath();
        ctx.moveTo(86 * s, 88 * s);
        ctx.bezierCurveTo(108 * s, 84 * s, 118 * s, 68 * s, 105 * s, 62 * s);
        ctx.fill();
        ctx.strokeStyle = O; ctx.lineWidth = 2.5 * s; ctx.stroke();

        // BODY — werewolf with gradient
        const wereGrad = ctx.createLinearGradient(40 * s, 48 * s, 88 * s, 104 * s);
        wereGrad.addColorStop(0, '#5A80B5');
        wereGrad.addColorStop(1, '#3A5A8A');
        ctx.fillStyle = wereGrad;
        ctx.beginPath();
        ctx.ellipse(64 * s, 76 * s, 24 * s, 28 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#4A6FA5', O, 2.5 * s);

        // BELT
        ctx.fillStyle = '#2A4A7A';
        ctx.beginPath();
        ctx.roundRect(44 * s, 86 * s, 40 * s, 5 * s, 2 * s);
        fillStroke(ctx, '#2A4A7A', O, 2 * s);

        // BODY STRIPES
        ctx.strokeStyle = '#E8E8F0';
        ctx.lineWidth = 2 * s;
        for (let i = 0; i < 3; i++) {
            ctx.beginPath();
            ctx.moveTo(52 * s, 68 * s + i * 6 * s);
            ctx.quadraticCurveTo(64 * s, 64 * s + i * 6 * s, 76 * s, 68 * s + i * 6 * s);
            ctx.stroke();
        }

        // ARMS
        ctx.fillStyle = '#4A6FA5';
        ctx.beginPath();
        ctx.roundRect(28 * s, 62 * s, 16 * s, 32 * s, 5 * s);
        fillStroke(ctx, '#4A6FA5', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(84 * s, 62 * s, 16 * s, 32 * s, 5 * s);
        fillStroke(ctx, '#4A6FA5', O, 2.5 * s);

        // METAL CLAWS
        ctx.fillStyle = '#C0C0C0';
        for (let side = -1; side <= 1; side += 2) {
            const cx = 36 * s + side * 56 * s;
            ctx.beginPath();
            ctx.moveTo(cx - 6 * s, 94 * s);
            ctx.lineTo(cx - 4 * s, 104 * s);
            ctx.lineTo(cx, 96 * s);
            ctx.lineTo(cx + 4 * s, 104 * s);
            ctx.lineTo(cx + 6 * s, 94 * s);
            ctx.closePath();
            fillStroke(ctx, '#C0C0C0', O, 2 * s);
        }

        // HEAD
        ctx.fillStyle = '#4A6FA5';
        ctx.beginPath();
        ctx.arc(64 * s, 44 * s, 20 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#4A6FA5', O, 2.5 * s);

        // SNOUT
        ctx.fillStyle = '#E8E8F0';
        ctx.beginPath();
        ctx.ellipse(64 * s, 52 * s, 12 * s, 8 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#E8E8F0', O, 2 * s);

        // NOSE
        ctx.fillStyle = O;
        ctx.beginPath();
        ctx.arc(64 * s, 50 * s, 2 * s, 0, Math.PI * 2);
        ctx.fill();

        // MOUTH
        ctx.strokeStyle = O;
        ctx.lineWidth = 2 * s;
        ctx.beginPath();
        ctx.arc(64 * s, 54 * s, 4 * s, 0.1, Math.PI - 0.1);
        ctx.stroke();

        // EARS
        for (let side = -1; side <= 1; side += 2) {
            ctx.fillStyle = '#4A6FA5';
            ctx.beginPath();
            ctx.moveTo(64 * s + side * 12 * s, 32 * s);
            ctx.lineTo(64 * s + side * 22 * s, 12 * s);
            ctx.lineTo(64 * s + side * 20 * s, 34 * s);
            ctx.closePath();
            fillStroke(ctx, '#4A6FA5', O, 2.5 * s);
        }

        // EYES — mechanical red, looking right
        drawEye(ctx, 52 * s, 42 * s, '#FF4444', 7 * s, 3 * s, { shape: 'round', gazeX: 0.4 });
        drawEye(ctx, 76 * s, 42 * s, '#FF4444', 7 * s, 3 * s, { shape: 'round', gazeX: 0.4 });
    }

    function drawAtlurKabuterimon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 120 * s, 26 * s, 9 * s);

        // LEGS
        for (let i = 0; i < 2; i++) {
            const lx = 46 * s + i * 20 * s;
            ctx.strokeStyle = '#FF0000';
            ctx.lineWidth = 4 * s;
            ctx.beginPath();
            ctx.moveTo(lx, 98 * s);
            ctx.lineTo(lx - 5 * s, 118 * s);
            ctx.stroke();
            ctx.strokeStyle = O; ctx.lineWidth = 6 * s; ctx.stroke();
            ctx.strokeStyle = '#FF0000'; ctx.lineWidth = 4 * s; ctx.stroke();

            ctx.beginPath();
            ctx.moveTo(lx + 8 * s, 98 * s);
            ctx.lineTo(lx + 12 * s, 118 * s);
            ctx.stroke();
            ctx.strokeStyle = O; ctx.lineWidth = 6 * s; ctx.stroke();
            ctx.strokeStyle = '#FF0000'; ctx.lineWidth = 4 * s; ctx.stroke();
        }

        // BODY — giant red beetle
        const bodyGrad = ctx.createLinearGradient(34 * s, 70 * s, 94 * s, 70 * s);
        bodyGrad.addColorStop(0, '#CC0000');
        bodyGrad.addColorStop(0.5, '#FF0000');
        bodyGrad.addColorStop(1, '#CC0000');
        ctx.fillStyle = bodyGrad;
        ctx.beginPath();
        ctx.ellipse(64 * s, 76 * s, 32 * s, 22 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FF0000', O, 2.5 * s);

        // SHELL DIVISION
        ctx.strokeStyle = '#8B0000';
        ctx.lineWidth = 3 * s;
        ctx.beginPath();
        ctx.moveTo(64 * s, 56 * s);
        ctx.lineTo(64 * s, 96 * s);
        ctx.stroke();

        // SHELL DOTS
        ctx.fillStyle = '#FFD700';
        for (let r = 0; r < 2; r++) {
            for (let c = 0; c < 2; c++) {
                const dx = c === 0 ? 48 * s : 80 * s;
                const dy = 70 * s + r * 10 * s;
                ctx.beginPath();
                ctx.arc(dx, dy, 4 * s, 0, Math.PI * 2);
                ctx.fill();
                ctx.strokeStyle = O; ctx.lineWidth = 2 * s; ctx.stroke();
            }
        }

        // GIANT HORN
        ctx.fillStyle = '#FFD700';
        ctx.beginPath();
        ctx.moveTo(50 * s, 58 * s);
        ctx.lineTo(64 * s, 4 * s);
        ctx.lineTo(78 * s, 58 * s);
        ctx.closePath();
        fillStroke(ctx, '#FFD700', O, 2.5 * s);

        // SECONDARY HORNS
        ctx.fillStyle = '#FFA500';
        ctx.beginPath();
        ctx.moveTo(42 * s, 56 * s);
        ctx.lineTo(28 * s, 30 * s);
        ctx.lineTo(52 * s, 52 * s);
        ctx.closePath();
        fillStroke(ctx, '#FFA500', O, 2 * s);
        ctx.beginPath();
        ctx.moveTo(86 * s, 56 * s);
        ctx.lineTo(100 * s, 30 * s);
        ctx.lineTo(76 * s, 52 * s);
        ctx.closePath();
        fillStroke(ctx, '#FFA500', O, 2 * s);

        // HEAD
        ctx.fillStyle = '#FF0000';
        ctx.beginPath();
        ctx.arc(64 * s, 52 * s, 16 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#FF0000', O, 2.5 * s);

        // COMPOUND EYES
        ctx.fillStyle = '#FFD700';
        ctx.beginPath();
        ctx.ellipse(50 * s, 50 * s, 8 * s, 10 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FFD700', O, 2.5 * s);
        ctx.fillStyle = W;
        ctx.beginPath();
        ctx.arc(48 * s, 48 * s, 2.5 * s, 0, Math.PI * 2);
        ctx.fill();

        ctx.beginPath();
        ctx.ellipse(78 * s, 50 * s, 8 * s, 10 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FFD700', O, 2.5 * s);
        ctx.fillStyle = W;
        ctx.beginPath();
        ctx.arc(80 * s, 48 * s, 2.5 * s, 0, Math.PI * 2);
        ctx.fill();

        // ARMS
        ctx.fillStyle = '#FF0000';
        ctx.beginPath();
        ctx.roundRect(28 * s, 66 * s, 14 * s, 22 * s, 5 * s);
        fillStroke(ctx, '#FF0000', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(86 * s, 66 * s, 14 * s, 22 * s, 5 * s);
        fillStroke(ctx, '#FF0000', O, 2.5 * s);
    }

    function drawSeadramon(ctx, s) {
        prepCtx(ctx);

        // LONG BODY — serpentine curves
        ctx.strokeStyle = '#00CED1';
        ctx.lineWidth = 14 * s;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(64 * s, 60 * s);
        ctx.bezierCurveTo(64 * s, 75 * s, 50 * s, 85 * s, 64 * s, 100 * s);
        ctx.bezierCurveTo(78 * s, 112 * s, 50 * s, 118 * s, 60 * s, 122 * s);
        ctx.stroke();
        ctx.strokeStyle = O;
        ctx.lineWidth = 17 * s;
        ctx.stroke();
        ctx.strokeStyle = '#00CED1';
        ctx.lineWidth = 14 * s;
        ctx.stroke();

        // BELLY STRIPE
        ctx.strokeStyle = '#E0FFFF';
        ctx.lineWidth = 4 * s;
        ctx.beginPath();
        ctx.moveTo(64 * s, 60 * s);
        ctx.bezierCurveTo(64 * s, 75 * s, 50 * s, 85 * s, 64 * s, 100 * s);
        ctx.bezierCurveTo(78 * s, 112 * s, 50 * s, 118 * s, 60 * s, 122 * s);
        ctx.stroke();

        // BODY SEGMENTS
        ctx.strokeStyle = '#008B8B';
        ctx.lineWidth = 2 * s;
        for (let i = 0; i < 5; i++) {
            const t = 0.2 + i * 0.15;
            const bx = 64 * s * (1 - t) * (1 - t) * (1 - t) + 3 * 64 * s * t * (1 - t) * (1 - t) +
                       3 * 50 * s * t * t * (1 - t) + 60 * s * t * t * t;
            const by = 60 * s * (1 - t) * (1 - t) * (1 - t) + 3 * 75 * s * t * (1 - t) * (1 - t) +
                       3 * 85 * s * t * t * (1 - t) + 122 * s * t * t * t;
            ctx.beginPath();
            ctx.arc(bx, by, 9 * s, 0, Math.PI * 2);
            ctx.stroke();
        }

        // HEAD
        ctx.fillStyle = '#00CED1';
        ctx.beginPath();
        ctx.ellipse(64 * s, 48 * s, 16 * s, 14 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#00CED1', O, 2.5 * s);

        // CREST / FIN
        ctx.fillStyle = '#48D1CC';
        ctx.beginPath();
        ctx.moveTo(54 * s, 40 * s);
        ctx.quadraticCurveTo(64 * s, 18 * s, 74 * s, 40 * s);
        ctx.closePath();
        fillStroke(ctx, '#48D1CC', O, 2 * s);

        // EYES — wolf blue, narrow piercing
        drawEye(ctx, 52 * s, 46 * s, '#5BB5FF', 6.5 * s, 3 * s, { shape: 'narrow', gazeX: 0.4 });
        drawEye(ctx, 76 * s, 46 * s, '#5BB5FF', 6.5 * s, 3 * s, { shape: 'narrow', gazeX: 0.4 });

        // MOUTH
        ctx.strokeStyle = O;
        ctx.lineWidth = 1.5 * s;
        ctx.beginPath();
        ctx.arc(64 * s, 53 * s, 4 * s, 0.2, Math.PI - 0.2);
        ctx.stroke();
    }

    function drawWhamon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 116 * s, 30 * s, 10 * s);

        // BODY — massive whale
        const whaleGrad = ctx.createLinearGradient(34 * s, 60 * s, 94 * s, 60 * s);
        whaleGrad.addColorStop(0, '#2A4A7A');
        whaleGrad.addColorStop(0.5, '#4A6FA5');
        whaleGrad.addColorStop(1, '#2A4A7A');
        ctx.fillStyle = whaleGrad;
        ctx.beginPath();
        ctx.ellipse(64 * s, 78 * s, 34 * s, 24 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#4A6FA5', O, 2.5 * s);

        // BELLY
        ctx.fillStyle = '#87CEEB';
        ctx.beginPath();
        ctx.ellipse(64 * s, 84 * s, 26 * s, 14 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#87CEEB', O, 2 * s);

        // BELLY GROOVES
        ctx.strokeStyle = '#6A8FC5';
        ctx.lineWidth = 1.5 * s;
        for (let i = 0; i < 5; i++) {
            const gy = 78 * s + i * 3 * s;
            ctx.beginPath();
            ctx.moveTo(42 * s, gy);
            ctx.quadraticCurveTo(52 * s, gy - 2 * s, 64 * s, gy);
            ctx.quadraticCurveTo(76 * s, gy - 2 * s, 86 * s, gy);
            ctx.stroke();
        }

        // TAIL
        ctx.fillStyle = '#4A6FA5';
        ctx.beginPath();
        ctx.moveTo(88 * s, 84 * s);
        ctx.bezierCurveTo(110 * s, 82 * s, 118 * s, 94 * s, 105 * s, 100 * s);
        ctx.quadraticCurveTo(98 * s, 96 * s, 90 * s, 90 * s);
        ctx.closePath();
        fillStroke(ctx, '#4A6FA5', O, 2.5 * s);

        // BLOWHOLE — water spout
        ctx.strokeStyle = '#87CEEB';
        ctx.lineWidth = 3 * s;
        ctx.beginPath();
        ctx.moveTo(44 * s, 70 * s);
        ctx.quadraticCurveTo(38 * s, 45 * s, 46 * s, 30 * s);
        ctx.stroke();
        ctx.fillStyle = '#87CEEB';
        ctx.beginPath();
        ctx.arc(46 * s, 30 * s, 5 * s, 0, Math.PI * 2);
        ctx.fill();

        // HEAD — from front
        ctx.fillStyle = '#4A6FA5';
        ctx.beginPath();
        ctx.ellipse(42 * s, 72 * s, 16 * s, 18 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#4A6FA5', O, 2.5 * s);

        // EYE
        ctx.fillStyle = W;
        ctx.beginPath();
        ctx.arc(36 * s, 68 * s, 6 * s, 0, Math.PI * 2);
        fillStroke(ctx, W, O, 2 * s);
        ctx.fillStyle = '#87CEEB';
        ctx.beginPath();
        ctx.arc(36 * s, 68 * s, 3.5 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#87CEEB', O, 1.5 * s);
        ctx.fillStyle = O;
        ctx.beginPath();
        ctx.arc(36 * s, 68 * s, 2 * s, 0, Math.PI * 2);
        ctx.fill();

        // PECTORAL FINS
        ctx.fillStyle = '#4A6FA5';
        ctx.beginPath();
        ctx.moveTo(50 * s, 90 * s);
        ctx.bezierCurveTo(40 * s, 100 * s, 20 * s, 102 * s, 28 * s, 108 * s);
        ctx.quadraticCurveTo(38 * s, 100 * s, 52 * s, 93 * s);
        ctx.closePath();
        fillStroke(ctx, '#4A6FA5', O, 2 * s);
    }

    function drawIkkakumon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 118 * s, 24 * s, 9 * s);

        // TAIL
        ctx.fillStyle = '#F5F5F5';
        ctx.beginPath();
        ctx.moveTo(88 * s, 90 * s);
        ctx.bezierCurveTo(110 * s, 86 * s, 116 * s, 108 * s, 100 * s, 114 * s);
        ctx.lineTo(88 * s, 100 * s);
        ctx.closePath();
        fillStroke(ctx, '#F5F5F5', O, 2.5 * s);

        // BACK FLIPPERS
        ctx.fillStyle = '#D0D0D0';
        ctx.beginPath();
        ctx.roundRect(42 * s, 102 * s, 16 * s, 8 * s, 4 * s);
        fillStroke(ctx, '#D0D0D0', O, 2 * s);
        ctx.beginPath();
        ctx.roundRect(70 * s, 102 * s, 16 * s, 8 * s, 4 * s);
        fillStroke(ctx, '#D0D0D0', O, 2 * s);

        // BODY — walrus shape
        ctx.fillStyle = '#F5F5F5';
        ctx.beginPath();
        ctx.ellipse(64 * s, 82 * s, 28 * s, 24 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#F5F5F5', O, 2.5 * s);

        // FRONT FLIPPERS
        ctx.fillStyle = '#E8E8F0';
        ctx.beginPath();
        ctx.roundRect(28 * s, 72 * s, 20 * s, 12 * s, 5 * s);
        fillStroke(ctx, '#E8E8F0', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(80 * s, 72 * s, 20 * s, 12 * s, 5 * s);
        fillStroke(ctx, '#E8E8F0', O, 2.5 * s);

        // HEAD
        ctx.fillStyle = '#F5F5F5';
        ctx.beginPath();
        ctx.arc(64 * s, 50 * s, 22 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#F5F5F5', O, 2.5 * s);

        // HORN — narwhal-like
        ctx.fillStyle = '#FF6600';
        ctx.beginPath();
        ctx.moveTo(58 * s, 38 * s);
        ctx.lineTo(64 * s, 4 * s);
        ctx.lineTo(70 * s, 38 * s);
        ctx.closePath();
        fillStroke(ctx, '#FF6600', O, 2.5 * s);

        // TUSKS
        ctx.fillStyle = W;
        ctx.beginPath();
        ctx.moveTo(50 * s, 56 * s);
        ctx.lineTo(42 * s, 66 * s);
        ctx.lineTo(54 * s, 58 * s);
        ctx.closePath();
        fillStroke(ctx, W, O, 2 * s);
        ctx.beginPath();
        ctx.moveTo(78 * s, 56 * s);
        ctx.lineTo(86 * s, 66 * s);
        ctx.lineTo(74 * s, 58 * s);
        ctx.closePath();
        fillStroke(ctx, W, O, 2 * s);

        // FACE
        ctx.fillStyle = '#E8E8F0';
        ctx.beginPath();
        ctx.ellipse(64 * s, 54 * s, 14 * s, 10 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#E8E8F0', O, 2 * s);

        // NOSE
        ctx.fillStyle = '#FF6666';
        ctx.beginPath();
        ctx.arc(64 * s, 52 * s, 3 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#FF6666', O, 1.5 * s);

        // MOUTH
        ctx.strokeStyle = O;
        ctx.lineWidth = 2 * s;
        ctx.beginPath();
        ctx.arc(64 * s, 57 * s, 5 * s, 0.1, Math.PI - 0.1);
        ctx.stroke();

        // EYES — round blue, friendly walrus gaze
        drawEye(ctx, 49 * s, 46 * s, '#4169E1', 7 * s, 3 * s, { shape: 'round', gazeX: 0.3 });
        drawEye(ctx, 79 * s, 46 * s, '#4169E1', 7 * s, 3 * s, { shape: 'round', gazeX: 0.3 });
    }

    /* ── Additional species ── */

    function drawBakemon(ctx, s) {
        prepCtx(ctx);

        // GHOSTLY TRAIL
        ctx.fillStyle = 'rgba(169,169,169,0.3)';
        ctx.beginPath();
        ctx.moveTo(34 * s, 110 * s);
        ctx.bezierCurveTo(20 * s, 90 * s, 30 * s, 70 * s, 44 * s, 85 * s);
        ctx.bezierCurveTo(40 * s, 75 * s, 50 * s, 65 * s, 56 * s, 80 * s);
        ctx.bezierCurveTo(54 * s, 60 * s, 70 * s, 55 * s, 72 * s, 70 * s);
        ctx.lineTo(80 * s, 55 * s);
        ctx.lineTo(88 * s, 75 * s);
        ctx.lineTo(98 * s, 60 * s);
        ctx.lineTo(94 * s, 85 * s);
        ctx.lineTo(104 * s, 80 * s);
        ctx.lineTo(100 * s, 100 * s);
        ctx.lineTo(64 * s, 110 * s);
        ctx.closePath();
        ctx.fill();
        ctx.strokeStyle = '#A9A9A9';
        ctx.lineWidth = 2 * s;
        ctx.setLineDash([3 * s, 3 * s]);
        ctx.stroke();
        ctx.setLineDash([]);

        // MAIN BODY — ghost sheet
        ctx.fillStyle = '#A9A9A9';
        ctx.beginPath();
        ctx.moveTo(42 * s, 55 * s);
        ctx.bezierCurveTo(34 * s, 70 * s, 30 * s, 100 * s, 44 * s, 108 * s);
        ctx.lineTo(84 * s, 108 * s);
        ctx.bezierCurveTo(98 * s, 100 * s, 94 * s, 70 * s, 86 * s, 55 * s);
        ctx.closePath();
        fillStroke(ctx, '#A9A9A9', O, 2.5 * s);

        // HEAD — ghost face
        ctx.fillStyle = '#D3D3D3';
        ctx.beginPath();
        ctx.arc(64 * s, 52 * s, 18 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#D3D3D3', O, 2.5 * s);

        // EYES — hollow black
        ctx.fillStyle = O;
        ctx.beginPath();
        ctx.ellipse(52 * s, 48 * s, 7 * s, 9 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, O, O, 2 * s);
        ctx.beginPath();
        ctx.ellipse(76 * s, 48 * s, 7 * s, 9 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, O, O, 2 * s);

        // EYE HIGHLIGHTS
        ctx.fillStyle = W;
        ctx.beginPath();
        ctx.arc(50 * s, 45 * s, 2 * s, 0, Math.PI * 2);
        ctx.fill();
        ctx.beginPath();
        ctx.arc(74 * s, 45 * s, 2 * s, 0, Math.PI * 2);
        ctx.fill();

        // MOUTH — gaping
        ctx.fillStyle = O;
        ctx.beginPath();
        ctx.ellipse(64 * s, 60 * s, 8 * s, 6 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, O, O, 2 * s);

        // ARMS — wispy
        ctx.fillStyle = '#A9A9A9';
        ctx.beginPath();
        ctx.moveTo(42 * s, 65 * s);
        ctx.bezierCurveTo(20 * s, 60 * s, 10 * s, 85 * s, 28 * s, 88 * s);
        ctx.bezierCurveTo(20 * s, 78 * s, 30 * s, 68 * s, 40 * s, 72 * s);
        ctx.closePath();
        fillStroke(ctx, '#A9A9A9', O, 2 * s);

        ctx.beginPath();
        ctx.moveTo(86 * s, 65 * s);
        ctx.bezierCurveTo(108 * s, 60 * s, 118 * s, 85 * s, 100 * s, 88 * s);
        ctx.bezierCurveTo(108 * s, 78 * s, 98 * s, 68 * s, 88 * s, 72 * s);
        ctx.closePath();
        fillStroke(ctx, '#A9A9A9', O, 2 * s);
    }

    function drawFantomon(ctx, s) {
        prepCtx(ctx);

        // CLOAK / ROBE
        ctx.fillStyle = '#483D8B';
        ctx.beginPath();
        ctx.moveTo(40 * s, 40 * s);
        ctx.bezierCurveTo(30 * s, 60 * s, 26 * s, 95 * s, 34 * s, 110 * s);
        ctx.lineTo(94 * s, 110 * s);
        ctx.bezierCurveTo(102 * s, 95 * s, 98 * s, 60 * s, 88 * s, 40 * s);
        ctx.closePath();
        fillStroke(ctx, '#483D8B', O, 2.5 * s);

        // CLOAK SHADOW FOLD
        ctx.strokeStyle = '#9370DB';
        ctx.lineWidth = 2 * s;
        ctx.beginPath();
        ctx.moveTo(54 * s, 45 * s);
        ctx.bezierCurveTo(48 * s, 70 * s, 48 * s, 100 * s, 52 * s, 108 * s);
        ctx.stroke();

        // SKULL FACE — inside hood
        ctx.fillStyle = '#F5F5DC';
        ctx.beginPath();
        ctx.arc(64 * s, 54 * s, 16 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#F5F5DC', O, 2.5 * s);

        // SKULL EYES
        ctx.fillStyle = O;
        ctx.beginPath();
        ctx.ellipse(55 * s, 50 * s, 6 * s, 7 * s, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.beginPath();
        ctx.ellipse(73 * s, 50 * s, 6 * s, 7 * s, 0, 0, Math.PI * 2);
        ctx.fill();

        // RED EYE GLOW
        ctx.fillStyle = '#DC143C';
        ctx.beginPath();
        ctx.arc(55 * s, 50 * s, 3 * s, 0, Math.PI * 2);
        ctx.fill();
        ctx.beginPath();
        ctx.arc(73 * s, 50 * s, 3 * s, 0, Math.PI * 2);
        ctx.fill();

        // SKULL NOSE
        ctx.fillStyle = O;
        ctx.beginPath();
        ctx.moveTo(61 * s, 52 * s);
        ctx.lineTo(67 * s, 52 * s);
        ctx.lineTo(64 * s, 57 * s);
        ctx.closePath();
        ctx.fill();

        // SKULL MOUTH
        ctx.strokeStyle = O;
        ctx.lineWidth = 1.5 * s;
        ctx.beginPath();
        ctx.moveTo(56 * s, 60 * s);
        ctx.lineTo(64 * s, 62 * s);
        ctx.lineTo(72 * s, 60 * s);
        ctx.stroke();

        // SCYTHE
        ctx.strokeStyle = '#C0C0C0';
        ctx.lineWidth = 3 * s;
        ctx.beginPath();
        ctx.moveTo(94 * s, 60 * s);
        ctx.lineTo(112 * s, 18 * s);
        ctx.stroke();
        ctx.strokeStyle = O;
        ctx.lineWidth = 5 * s;
        ctx.stroke();
        ctx.strokeStyle = '#C0C0C0';
        ctx.lineWidth = 3 * s;
        ctx.stroke();

        // SCYTHE BLADE
        ctx.fillStyle = '#C0C0C0';
        ctx.beginPath();
        ctx.moveTo(112 * s, 18 * s);
        ctx.bezierCurveTo(105 * s, 5 * s, 120 * s, 2 * s, 125 * s, 10 * s);
        ctx.bezierCurveTo(128 * s, 18 * s, 118 * s, 22 * s, 112 * s, 18 * s);
        ctx.closePath();
        fillStroke(ctx, '#C0C0C0', O, 2 * s);

        // HOOD
        ctx.fillStyle = '#483D8B';
        ctx.beginPath();
        ctx.arc(64 * s, 48 * s, 20 * s, Math.PI + 0.5, -0.5);
        ctx.fill();
        ctx.strokeStyle = O; ctx.lineWidth = 2.5 * s; ctx.stroke();
    }

    function drawDevidramon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 120 * s, 24 * s, 9 * s);

        // LEGS
        ctx.fillStyle = '#800020';
        ctx.beginPath();
        ctx.roundRect(46 * s, 96 * s, 16 * s, 22 * s, 4 * s);
        fillStroke(ctx, '#800020', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(66 * s, 96 * s, 16 * s, 22 * s, 4 * s);
        fillStroke(ctx, '#800020', O, 2.5 * s);

        // CLAWS
        for (let i = 0; i < 2; i++) {
            const cx = 58 * s + i * 12 * s;
            ctx.fillStyle = '#FF4500';
            ctx.beginPath();
            ctx.moveTo(cx - 5 * s, 118 * s);
            ctx.lineTo(cx - 2 * s, 110 * s);
            ctx.lineTo(cx, 116 * s);
            ctx.lineTo(cx + 2 * s, 110 * s);
            ctx.lineTo(cx + 5 * s, 118 * s);
            ctx.closePath();
            fillStroke(ctx, '#FF4500', O, 1.5 * s);
        }

        // BODY — demon dragon
        ctx.fillStyle = '#800020';
        ctx.beginPath();
        ctx.ellipse(64 * s, 76 * s, 26 * s, 30 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#800020', O, 2.5 * s);

        // CHEST MARKINGS
        ctx.strokeStyle = '#FF4500';
        ctx.lineWidth = 2 * s;
        ctx.beginPath();
        ctx.moveTo(52 * s, 68 * s);
        ctx.quadraticCurveTo(64 * s, 84 * s, 76 * s, 68 * s);
        ctx.stroke();

        // WINGS — demon
        ctx.fillStyle = '#800020';
        for (let side = -1; side <= 1; side += 2) {
            ctx.beginPath();
            ctx.moveTo(64 * s + side * 16 * s, 55 * s);
            ctx.bezierCurveTo(
                64 * s + side * 42 * s, 30 * s,
                64 * s + side * 48 * s, 90 * s,
                64 * s + side * 14 * s, 88 * s
            );
            ctx.closePath();
            fillStroke(ctx, '#800020', O, 2.5 * s);

            // Wing ribs
            ctx.strokeStyle = '#FF4500';
            ctx.lineWidth = 1.5 * s;
            ctx.beginPath();
            ctx.moveTo(64 * s + side * 20 * s, 58 * s);
            ctx.quadraticCurveTo(64 * s + side * 35 * s, 62 * s, 64 * s + side * 22 * s, 78 * s);
            ctx.stroke();
        }

        // ARMS
        ctx.fillStyle = '#800020';
        ctx.beginPath();
        ctx.roundRect(30 * s, 64 * s, 14 * s, 28 * s, 5 * s);
        fillStroke(ctx, '#800020', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(84 * s, 64 * s, 14 * s, 28 * s, 5 * s);
        fillStroke(ctx, '#800020', O, 2.5 * s);

        // HEAD
        ctx.fillStyle = '#800020';
        ctx.beginPath();
        ctx.arc(64 * s, 44 * s, 20 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#800020', O, 2.5 * s);

        // HORNS — multiple demon horns
        for (let side = -1; side <= 1; side += 2) {
            ctx.fillStyle = '#4a0000';
            ctx.beginPath();
            ctx.moveTo(64 * s + side * 12 * s, 30 * s);
            ctx.lineTo(64 * s + side * 24 * s, 6 * s);
            ctx.lineTo(64 * s + side * 20 * s, 30 * s);
            ctx.closePath();
            fillStroke(ctx, '#4a0000', O, 2.5 * s);
        }

        // EVIL EYES — multiple
        ctx.fillStyle = '#FF0000';
        ctx.beginPath();
        ctx.ellipse(50 * s, 40 * s, 6 * s, 7 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FF0000', O, 2 * s);
        ctx.beginPath();
        ctx.ellipse(70 * s, 38 * s, 6 * s, 7 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FF0000', O, 2 * s);
        ctx.beginPath();
        ctx.ellipse(78 * s, 42 * s, 6 * s, 7 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FF0000', O, 2 * s);

        // MOUTH
        ctx.strokeStyle = O;
        ctx.lineWidth = 2 * s;
        ctx.beginPath();
        ctx.moveTo(48 * s, 54 * s);
        ctx.quadraticCurveTo(64 * s, 64 * s, 80 * s, 54 * s);
        ctx.stroke();
    }

    function drawClockmon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 118 * s, 22 * s, 8 * s);

        // LEGS — clock legs
        ctx.fillStyle = '#8B7355';
        ctx.beginPath();
        ctx.roundRect(52 * s, 98 * s, 8 * s, 18 * s, 2 * s);
        fillStroke(ctx, '#8B7355', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(68 * s, 98 * s, 8 * s, 18 * s, 2 * s);
        fillStroke(ctx, '#8B7355', O, 2.5 * s);

        // BODY — clock body
        const clockGrad = ctx.createRadialGradient(60 * s, 68 * s, 5 * s, 64 * s, 72 * s, 24 * s);
        clockGrad.addColorStop(0, '#DAA520');
        clockGrad.addColorStop(1, '#8B7355');
        ctx.fillStyle = clockGrad;
        ctx.beginPath();
        ctx.arc(64 * s, 72 * s, 24 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#8B7355', O, 2.5 * s);

        // CLOCK FACE
        ctx.fillStyle = '#FFF8DC';
        ctx.beginPath();
        ctx.arc(64 * s, 72 * s, 18 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#FFF8DC', O, 2 * s);

        // HOUR MARKERS
        ctx.fillStyle = '#8B7355';
        for (let i = 0; i < 12; i++) {
            const angle = (i / 12) * Math.PI * 2 - Math.PI / 2;
            const mx = 64 * s + Math.cos(angle) * 14 * s;
            const my = 72 * s + Math.sin(angle) * 14 * s;
            ctx.beginPath();
            ctx.arc(mx, my, 1.5 * s, 0, Math.PI * 2);
            ctx.fill();
        }

        // CLOCK HANDS
        ctx.strokeStyle = O;
        ctx.lineWidth = 2 * s;
        ctx.beginPath();
        ctx.moveTo(64 * s, 72 * s);
        ctx.lineTo(64 * s, 58 * s);
        ctx.stroke();
        ctx.lineWidth = 1.5 * s;
        ctx.beginPath();
        ctx.moveTo(64 * s, 72 * s);
        ctx.lineTo(76 * s, 72 * s);
        ctx.stroke();

        // CENTER PIN
        ctx.fillStyle = O;
        ctx.beginPath();
        ctx.arc(64 * s, 72 * s, 2.5 * s, 0, Math.PI * 2);
        ctx.fill();

        // HANDS — mechanical
        ctx.fillStyle = '#8B7355';
        ctx.beginPath();
        ctx.roundRect(32 * s, 62 * s, 14 * s, 20 * s, 4 * s);
        fillStroke(ctx, '#8B7355', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(82 * s, 62 * s, 14 * s, 20 * s, 4 * s);
        fillStroke(ctx, '#8B7355', O, 2.5 * s);

        // EYES — dials
        ctx.fillStyle = W;
        ctx.beginPath();
        ctx.arc(54 * s, 56 * s, 7 * s, 0, Math.PI * 2);
        fillStroke(ctx, W, O, 2 * s);
        ctx.fillStyle = O;
        ctx.beginPath();
        ctx.arc(54 * s, 56 * s, 3 * s, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = W;
        ctx.beginPath();
        ctx.arc(74 * s, 56 * s, 7 * s, 0, Math.PI * 2);
        fillStroke(ctx, W, O, 2 * s);
        ctx.fillStyle = O;
        ctx.beginPath();
        ctx.arc(74 * s, 56 * s, 3 * s, 0, Math.PI * 2);
        ctx.fill();

        // TOP BELL
        ctx.fillStyle = '#DAA520';
        ctx.beginPath();
        ctx.moveTo(56 * s, 50 * s);
        ctx.lineTo(60 * s, 38 * s);
        ctx.lineTo(68 * s, 38 * s);
        ctx.lineTo(72 * s, 50 * s);
        ctx.closePath();
        fillStroke(ctx, '#DAA520', O, 2 * s);
    }

    function drawTankmon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 118 * s, 24 * s, 8 * s);

        // TREADS
        ctx.fillStyle = '#556B2F';
        ctx.beginPath();
        ctx.roundRect(38 * s, 100 * s, 52 * s, 16 * s, 4 * s);
        fillStroke(ctx, '#556B2F', O, 2.5 * s);

        // TREAD DETAIL
        ctx.strokeStyle = '#3a4a1a';
        ctx.lineWidth = 2 * s;
        for (let i = 0; i < 6; i++) {
            const tx = 44 * s + i * 8 * s;
            ctx.beginPath();
            ctx.moveTo(tx, 100 * s);
            ctx.lineTo(tx, 116 * s);
            ctx.stroke();
        }

        // BODY — tank hull
        ctx.fillStyle = '#556B2F';
        ctx.beginPath();
        ctx.roundRect(42 * s, 68 * s, 44 * s, 36 * s, 6 * s);
        fillStroke(ctx, '#556B2F', O, 2.5 * s);

        // CANNON
        ctx.fillStyle = '#3a4a1a';
        ctx.beginPath();
        ctx.roundRect(82 * s, 60 * s, 22 * s, 10 * s, 3 * s);
        fillStroke(ctx, '#3a4a1a', O, 2.5 * s);
        // Cannon barrel
        ctx.fillStyle = '#2a3a0a';
        ctx.beginPath();
        ctx.roundRect(100 * s, 62 * s, 14 * s, 6 * s, 2 * s);
        fillStroke(ctx, '#2a3a0a', O, 2 * s);

        // HEAD / TURRET
        ctx.fillStyle = '#556B2F';
        ctx.beginPath();
        ctx.arc(64 * s, 56 * s, 16 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#556B2F', O, 2.5 * s);

        // SCOPE / EYE
        ctx.fillStyle = '#FF0000';
        ctx.beginPath();
        ctx.ellipse(64 * s, 52 * s, 6 * s, 4 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FF0000', O, 2 * s);
        ctx.fillStyle = W;
        ctx.beginPath();
        ctx.arc(62 * s, 51 * s, 1.5 * s, 0, Math.PI * 2);
        ctx.fill();

        // WHEELS
        for (let i = 0; i < 3; i++) {
            const wx = 48 * s + i * 16 * s;
            ctx.fillStyle = '#3a4a1a';
            ctx.beginPath();
            ctx.arc(wx, 108 * s, 6 * s, 0, Math.PI * 2);
            fillStroke(ctx, '#3a4a1a', O, 2 * s);
            ctx.fillStyle = '#1a2a0a';
            ctx.beginPath();
            ctx.arc(wx, 108 * s, 3 * s, 0, Math.PI * 2);
            ctx.fill();
        }
    }

    function drawKokuwamon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 118 * s, 16 * s, 6 * s);

        // LEGS — wire-like
        for (let i = 0; i < 2; i++) {
            const lx = 56 * s + i * 8 * s;
            ctx.strokeStyle = '#00CED1';
            ctx.lineWidth = 3 * s;
            ctx.beginPath();
            ctx.moveTo(lx, 98 * s);
            ctx.lineTo(lx - 3 * s, 114 * s);
            ctx.stroke();
            ctx.strokeStyle = O;
            ctx.lineWidth = 5 * s;
            ctx.stroke();
            ctx.strokeStyle = '#00CED1';
            ctx.lineWidth = 3 * s;
            ctx.stroke();
        }

        // BODY — small machine
        ctx.fillStyle = '#87CEEB';
        ctx.beginPath();
        ctx.roundRect(46 * s, 68 * s, 36 * s, 34 * s, 5 * s);
        fillStroke(ctx, '#87CEEB', O, 2.5 * s);

        // CHEST PANEL
        ctx.fillStyle = '#00CED1';
        ctx.beginPath();
        ctx.roundRect(52 * s, 74 * s, 24 * s, 16 * s, 3 * s);
        fillStroke(ctx, '#00CED1', O, 1.5 * s);

        // BUTTON LIGHTS
        ctx.fillStyle = '#FF0000';
        ctx.beginPath();
        ctx.arc(60 * s, 80 * s, 2 * s, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#FFD700';
        ctx.beginPath();
        ctx.arc(68 * s, 80 * s, 2 * s, 0, Math.PI * 2);
        ctx.fill();

        // ARMS — pincers
        ctx.fillStyle = '#87CEEB';
        ctx.beginPath();
        ctx.roundRect(32 * s, 72 * s, 16 * s, 8 * s, 3 * s);
        fillStroke(ctx, '#87CEEB', O, 2 * s);
        ctx.beginPath();
        ctx.roundRect(80 * s, 72 * s, 16 * s, 8 * s, 3 * s);
        fillStroke(ctx, '#87CEEB', O, 2 * s);

        // HEAD
        ctx.fillStyle = '#87CEEB';
        ctx.beginPath();
        ctx.roundRect(54 * s, 52 * s, 20 * s, 18 * s, 5 * s);
        fillStroke(ctx, '#87CEEB', O, 2.5 * s);

        // ANTENNA
        ctx.strokeStyle = '#00CED1';
        ctx.lineWidth = 2 * s;
        ctx.beginPath();
        ctx.moveTo(58 * s, 52 * s);
        ctx.lineTo(52 * s, 38 * s);
        ctx.stroke();
        ctx.strokeStyle = O;
        ctx.lineWidth = 3 * s;
        ctx.stroke();
        ctx.strokeStyle = '#00CED1';
        ctx.lineWidth = 2 * s;
        ctx.stroke();

        ctx.beginPath();
        ctx.moveTo(70 * s, 52 * s);
        ctx.lineTo(76 * s, 38 * s);
        ctx.stroke();
        ctx.strokeStyle = O;
        ctx.lineWidth = 3 * s;
        ctx.stroke();
        ctx.strokeStyle = '#00CED1';
        ctx.lineWidth = 2 * s;
        ctx.stroke();

        // EYE — single sensor
        ctx.fillStyle = '#FF0000';
        ctx.beginPath();
        ctx.arc(64 * s, 57 * s, 4 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#FF0000', O, 1.5 * s);
        ctx.fillStyle = W;
        ctx.beginPath();
        ctx.arc(63 * s, 56 * s, 1 * s, 0, Math.PI * 2);
        ctx.fill();
    }

    function drawPicodevimon(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 116 * s, 14 * s, 5 * s);

        // WINGS — tiny bat wings
        ctx.fillStyle = '#4B0082';
        for (let side = -1; side <= 1; side += 2) {
            ctx.beginPath();
            ctx.moveTo(64 * s + side * 8 * s, 45 * s);
            ctx.bezierCurveTo(
                64 * s + side * 22 * s, 30 * s,
                64 * s + side * 25 * s, 65 * s,
                64 * s + side * 10 * s, 60 * s
            );
            ctx.closePath();
            fillStroke(ctx, '#4B0082', O, 2 * s);
        }

        // BODY — tiny imp
        ctx.fillStyle = '#4B0082';
        ctx.beginPath();
        ctx.ellipse(64 * s, 78 * s, 16 * s, 20 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#4B0082', O, 2.5 * s);

        // LEGS — tiny
        ctx.fillStyle = '#4B0082';
        ctx.beginPath();
        ctx.roundRect(56 * s, 96 * s, 6 * s, 14 * s, 3 * s);
        fillStroke(ctx, '#4B0082', O, 2 * s);
        ctx.beginPath();
        ctx.roundRect(66 * s, 96 * s, 6 * s, 14 * s, 3 * s);
        fillStroke(ctx, '#4B0082', O, 2 * s);

        // HEAD
        ctx.fillStyle = '#4B0082';
        ctx.beginPath();
        ctx.arc(64 * s, 52 * s, 15 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#4B0082', O, 2.5 * s);

        // BADGE on forehead
        ctx.fillStyle = '#FF0000';
        ctx.beginPath();
        ctx.moveTo(60 * s, 40 * s);
        ctx.quadraticCurveTo(64 * s, 36 * s, 68 * s, 40 * s);
        ctx.closePath();
        fillStroke(ctx, '#FF0000', O, 1.5 * s);

        // EVIL EYES
        ctx.fillStyle = '#FF0000';
        ctx.beginPath();
        ctx.ellipse(55 * s, 50 * s, 5 * s, 6 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FF0000', O, 2 * s);
        ctx.fillStyle = O;
        ctx.beginPath();
        ctx.arc(55 * s, 50 * s, 2 * s, 0, Math.PI * 2);
        ctx.fill();

        ctx.beginPath();
        ctx.ellipse(73 * s, 50 * s, 5 * s, 6 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#FF0000', O, 2 * s);
        ctx.fillStyle = O;
        ctx.beginPath();
        ctx.arc(73 * s, 50 * s, 2 * s, 0, Math.PI * 2);
        ctx.fill();

        // MOUTH — wicked grin
        ctx.strokeStyle = O;
        ctx.lineWidth = 1.5 * s;
        ctx.beginPath();
        ctx.moveTo(57 * s, 58 * s);
        ctx.quadraticCurveTo(64 * s, 63 * s, 71 * s, 58 * s);
        ctx.stroke();

        // FANGS
        ctx.fillStyle = W;
        ctx.beginPath();
        ctx.moveTo(58 * s, 59 * s);
        ctx.lineTo(56 * s, 56 * s);
        ctx.lineTo(60 * s, 58 * s);
        ctx.fill();
        ctx.strokeStyle = O; ctx.lineWidth = 0.8 * s; ctx.stroke();
    }

    /* ── Default fallback ── */

    function drawDefault(ctx, s) {
        prepCtx(ctx);
        shadowBlob(ctx, 64 * s, 116 * s, 18 * s, 7 * s);

        // LEGS
        ctx.fillStyle = '#AABBCC';
        ctx.beginPath();
        ctx.roundRect(52 * s, 98 * s, 10 * s, 16 * s, 3 * s);
        fillStroke(ctx, '#AABBCC', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(66 * s, 98 * s, 10 * s, 16 * s, 3 * s);
        fillStroke(ctx, '#AABBCC', O, 2.5 * s);

        // BODY
        ctx.fillStyle = '#AABBCC';
        ctx.beginPath();
        ctx.ellipse(64 * s, 78 * s, 20 * s, 24 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#AABBCC', O, 2.5 * s);

        // BELLY
        ctx.fillStyle = '#CCDDEE';
        ctx.beginPath();
        ctx.ellipse(64 * s, 82 * s, 14 * s, 15 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#CCDDEE', O, 2 * s);

        // ARMS
        ctx.fillStyle = '#AABBCC';
        ctx.beginPath();
        ctx.roundRect(36 * s, 70 * s, 10 * s, 18 * s, 4 * s);
        fillStroke(ctx, '#AABBCC', O, 2.5 * s);
        ctx.beginPath();
        ctx.roundRect(82 * s, 70 * s, 10 * s, 18 * s, 4 * s);
        fillStroke(ctx, '#AABBCC', O, 2.5 * s);

        // HEAD
        ctx.fillStyle = '#AABBCC';
        ctx.beginPath();
        ctx.arc(64 * s, 48 * s, 18 * s, 0, Math.PI * 2);
        fillStroke(ctx, '#AABBCC', O, 2.5 * s);

        // FACE
        ctx.fillStyle = '#CCDDEE';
        ctx.beginPath();
        ctx.ellipse(64 * s, 52 * s, 10 * s, 8 * s, 0, 0, Math.PI * 2);
        fillStroke(ctx, '#CCDDEE', O, 1.5 * s);

        // MOUTH
        ctx.strokeStyle = O;
        ctx.lineWidth = 1.5 * s;
        ctx.beginPath();
        ctx.arc(64 * s, 54 * s, 3 * s, 0.1, Math.PI - 0.1);
        ctx.stroke();

        // EYES — generic
        drawEye(ctx, 54 * s, 46 * s, '#667788', 6 * s, 2.5 * s, { shape: 'round', gazeX: 0.3 });
        drawEye(ctx, 74 * s, 46 * s, '#667788', 6 * s, 2.5 * s, { shape: 'round', gazeX: 0.3 });

        // QUESTION MARK
        ctx.strokeStyle = '#FFD700';
        ctx.lineWidth = 2.5 * s;
        ctx.beginPath();
        ctx.arc(64 * s, 24 * s, 4 * s, Math.PI * 0.2, Math.PI * 1.1);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(67 * s, 28 * s);
        ctx.lineTo(64 * s, 36 * s);
        ctx.stroke();
        ctx.fillStyle = '#FFD700';
        ctx.beginPath();
        ctx.arc(64 * s, 39 * s, 1.5 * s, 0, Math.PI * 2);
        ctx.fill();
    }

    // ── Registry: species name → draw function ──────────────────────

    const DRAW_FUNCS = {
        agumon:          drawAgumon,
        gabumon:         drawGabumon,
        biyomon:         drawBiyomon,
        tentomon:        drawTentomon,
        palmon:          drawPalmon,
        gomamon:         drawGomamon,
        patamon:         drawPatamon,
        tailmon:         drawTailmon,
        plotmon:         drawPlotmon,
        elecmon:         drawElecmon,
        tsunomon:        drawTsunomon,
        hagurumon:       drawHagurumon,
        guardromon:      drawGuardromon,
        andromon:        drawAndromon,
        devimon:         drawDevimon,
        ogremon:         drawOgremon,
        leomon:          drawLeomon,
        greymon:         drawGreymon,
        garurumon:       drawGarurumon,
        kabuterimon:     drawKabuterimon,
        togemon:         drawTogemon,
        angemon:         drawAngemon,
        birdramon:       drawBirdramon,
        garudamon:       drawGarudamon,
        metalgreymon:    drawMetalGreymon,
        weregarurumon:   drawWeregarurumon,
        atlurkabuterimon: drawAtlurKabuterimon,
        seadramon:       drawSeadramon,
        whamon:          drawWhamon,
        ikkakumon:       drawIkkakumon,
        bakemon:         drawBakemon,
        fantomon:        drawFantomon,
        devidramon:      drawDevidramon,
        clockmon:        drawClockmon,
        tankmon:         drawTankmon,
        kokuwamon:       drawKokuwamon,
        picodevimon:     drawPicodevimon,
        _default:        drawDefault,
    };

    // ── Sprite cache ─────────────────────────────────────────────────

    const spriteCache = new Map();

    /**
     * Render a species to a 256×256 offscreen canvas.
     *
     * Strategy (in order of preference):
     *   1. If the PNG image is already loaded → render from 512×512 image (HQ).
     *   2. If the PNG is not loaded yet → kick off async load, fall back to
     *      procedural DRAW_FUNCS (instant, always available).  When the PNG
     *      arrives, the cache entry is invalidated so the next call picks it up.
     *   3. If PNG fails to load → DRAW_FUNCS forever (graceful degradation).
     *
     * @param {string} species - species name
     * @param {string|number|null} frame - ignored (procedural sprites are frame-agnostic)
     * @returns {HTMLCanvasElement}
     */
    function getSprite(species, frame) {
        let key = (species || '_default').toLowerCase().replace(/[\s\-]/g, '_');
        // Normalize: try flat version too (e.g. metal_greymon → metalgreymon)
        if (!DRAW_FUNCS[key]) {
            const keyFlat = key.replace(/_/g, '');
            if (DRAW_FUNCS[keyFlat]) key = keyFlat;
        }
        if (!DRAW_FUNCS[key]) key = '_default';

        // Frame suffix (idle1, idle2, walk1, walk2) — for caching key only.
        const frameKey = frame || 'default';
        const cacheKey = key + '::' + frameKey;

        if (spriteCache.has(cacheKey)) return spriteCache.get(cacheKey);

        // ── Try PNG image first ──────────────────────────────────────
        const img = getLoadedImage(key);
        if (img) {
            // Render the 512×512 PNG scaled down to SZ (256)
            const offscreen = document.createElement('canvas');
            offscreen.width = SZ;
            offscreen.height = SZ;
            const ctx = offscreen.getContext('2d');
            ctx.imageSmoothingEnabled = true;
            ctx.imageSmoothingQuality = 'high';
            ctx.drawImage(img, 0, 0, IMG_SZ, IMG_SZ, 0, 0, SZ, SZ);
            spriteCache.set(cacheKey, offscreen);
            return offscreen;
        }

        // ── PNG not ready — kick off async load (fire-and-forget) ────
        if (key !== '_default') {
            preloadImage(key);
            // Listen for load: when image arrives, clear cache so next
            // getSprite call renders the HQ version.
            if (!imageCache.has(key)) {
                loadImage(key).then(() => {
                    // Invalidate all frame variants for this species
                    for (const ck of spriteCache.keys()) {
                        if (ck.startsWith(key + '::')) spriteCache.delete(ck);
                    }
                }).catch(() => { /* will keep using procedural fallback */ });
            }
        }

        // ── Fallback: procedural draw function ───────────────────────
        const offscreen = document.createElement('canvas');
        offscreen.width = SZ;
        offscreen.height = SZ;
        const ctx = offscreen.getContext('2d');

        ctx.clearRect(0, 0, SZ, SZ);

        // Scale: the draw functions use 128×128 coordinate system
        const s = SZ / 128;
        DRAW_FUNCS[key](ctx, s);

        spriteCache.set(cacheKey, offscreen);
        return offscreen;
    }

    /** Batch preload all known species (procedural + kick off image loads). */
    function preloadAll() {
        for (const key of Object.keys(DRAW_FUNCS)) {
            if (key === '_default') continue;
            getSprite(key, null);              // procedural render (instant)
            preloadImage(key);                 // kick off PNG load (async)
        }
    }

    /** Clear sprite cache (does NOT clear image cache — PNGs are permanent). */
    function clearCache() {
        spriteCache.clear();
    }

    // Return public API — backward compatible
    return { getSprite, preloadAll, clearCache, DRAW_FUNCS };

})();

/**
 * DIGIMON WORLD - Sprite Configuration Data
 *
 * Color configs, accent colors, and display sizes for each species.
 * Used by main.js for rendering digimon indicators and status.
 */
window.SPRITE_DATA = (function () {
    'use strict';

    // Helper: create action config with defaults
    function _act(frames, fps, loop) { return { frames, fps, loop }; }

    const configs = {
        agumon:        { color: '#FF8C00', accent: '#FFD700', size: 36, actions: { idle: _act(4,3,true), walk: _act(6,8,true), attack: _act(5,12,false), evolve: _act(8,3,false) } },
        gabumon:       { color: '#4A6FA5', accent: '#E8E8F0', size: 36, actions: { idle: _act(4,3,true), walk: _act(6,7,true), attack: _act(4,10,false), evolve: _act(8,3,false) } },
        biyomon:       { color: '#FF69B4', accent: '#FFB6C1', size: 32, actions: { idle: _act(4,4,true), walk: _act(4,8,true), attack: _act(4,12,false), evolve: _act(8,3,false) } },
        tentomon:      { color: '#8B3A8B', accent: '#FF0000', size: 32, actions: { idle: _act(4,3,true), walk: _act(6,6,true), attack: _act(4,10,false), evolve: _act(8,3,false) } },
        palmon:        { color: '#3CB371', accent: '#FF69B4', size: 36, actions: { idle: _act(4,3,true), walk: _act(6,6,true), attack: _act(4,10,false), evolve: _act(8,3,false) } },
        gomamon:       { color: '#F0F0FF', accent: '#FF6600', size: 34, actions: { idle: _act(4,3,true), walk: _act(4,7,true), attack: _act(4,10,false), evolve: _act(8,3,false) } },
        patamon:       { color: '#FFDAB9', accent: '#FFE4B5', size: 56, actions: { idle: _act(4,4,true), walk: _act(4,7,true), attack: _act(4,12,false), evolve: _act(8,3,false) } },
        tailmon:       { color: '#F5F5DC', accent: '#FFE4E1', size: 32, actions: { idle: _act(4,3,true), walk: _act(6,7,true), attack: _act(4,12,false), evolve: _act(8,3,false) } },
        plotmon:       { color: '#FFE4C4', accent: '#FFDEAD', size: 60, actions: { idle: _act(4,4,true), walk: _act(6,7,true), attack: _act(4,10,false), evolve: _act(8,3,false) } },
        elecmon:       { color: '#FF3333', accent: '#FFD700', size: 32, actions: { idle: _act(4,4,true), walk: _act(6,9,true), attack: _act(4,12,false), evolve: _act(8,3,false) } },
        tsunomon:      { color: '#E6E6FA', accent: '#DDA0DD', size: 60, actions: { idle: _act(4,3,true), walk: _act(4,6,true), attack: _act(4,8,false), evolve: _act(8,3,false) } },
        hagurumon:     { color: '#C0C0C0', accent: '#708090', size: 56, actions: { idle: _act(4,3,true), walk: _act(4,5,true), attack: _act(4,10,false), evolve: _act(8,3,false) } },
        guardromon:    { color: '#4682B4', accent: '#B0C4DE', size: 40, actions: { idle: _act(4,2,true), walk: _act(4,5,true), attack: _act(4,8,false), evolve: _act(8,3,false) } },
        andromon:      { color: '#4169E1', accent: '#1E90FF', size: 44, actions: { idle: _act(4,2,true), walk: _act(4,5,true), attack: _act(6,10,false), evolve: _act(8,3,false) } },
        clockmon:      { color: '#8B7355', accent: '#DAA520', size: 36, actions: { idle: _act(4,3,true), walk: _act(4,5,true), attack: _act(4,8,false), evolve: _act(8,3,false) } },
        tankmon:       { color: '#556B2F', accent: '#8B8B00', size: 40, actions: { idle: _act(4,2,true), walk: _act(6,6,true), attack: _act(6,10,false), evolve: _act(8,3,false) } },
        kokuwamon:     { color: '#87CEEB', accent: '#00CED1', size: 60, actions: { idle: _act(4,3,true), walk: _act(4,6,true), attack: _act(4,10,false), evolve: _act(8,3,false) } },
        picodevimon:   { color: '#4B0082', accent: '#8B008B', size: 52, actions: { idle: _act(4,4,true), walk: _act(4,7,true), attack: _act(4,12,false), evolve: _act(8,3,false) } },
        blackgabumon:  { color: '#2F4F4F', accent: '#A9A9A9', size: 36, actions: { idle: _act(4,3,true), walk: _act(6,7,true), attack: _act(4,10,false), evolve: _act(8,3,false) } },
        devimon:       { color: '#191970', accent: '#DC143C', size: 48, actions: { idle: _act(4,3,true), walk: _act(4,6,true), attack: _act(6,10,false), evolve: _act(10,3,false) } },
        devidramon:    { color: '#800020', accent: '#FF4500', size: 44, actions: { idle: _act(4,3,true), walk: _act(4,6,true), attack: _act(6,10,false), evolve: _act(10,3,false) } },
        vamdemon:      { color: '#2C003E', accent: '#8B0000', size: 52, actions: { idle: _act(4,3,true), walk: _act(4,5,true), attack: _act(6,12,false), evolve: _act(12,3,false) } },
        fantomon:      { color: '#483D8B', accent: '#9370DB', size: 40, actions: { idle: _act(4,3,true), walk: _act(4,5,true), attack: _act(4,10,false), evolve: _act(8,3,false) } },
        bakemon:       { color: '#A9A9A9', accent: '#D3D3D3', size: 34, actions: { idle: _act(4,3,true), walk: _act(4,6,true), attack: _act(4,8,false), evolve: _act(8,3,false) } },
        renamon:       { color: '#FFD700', accent: '#FFA500', size: 36, actions: { idle: _act(4,4,true), walk: _act(6,8,true), attack: _act(6,14,false), evolve: _act(10,3,false) } },
        impmon:        { color: '#800080', accent: '#FF6347', size: 32, actions: { idle: _act(4,4,true), walk: _act(6,8,true), attack: _act(6,12,false), evolve: _act(8,3,false) } },
        dorumon:       { color: '#4682B4', accent: '#87CEFA', size: 34, actions: { idle: _act(4,3,true), walk: _act(6,7,true), attack: _act(4,10,false), evolve: _act(8,3,false) } },
        wizarmon:      { color: '#6A0DAD', accent: '#00CED1', size: 40, actions: { idle: _act(4,3,true), walk: _act(4,6,true), attack: _act(6,12,false), evolve: _act(10,3,false) } },
        leomon:        { color: '#DAA520', accent: '#FF8C00', size: 48, actions: { idle: _act(4,3,true), walk: _act(6,7,true), attack: _act(6,10,false), evolve: _act(10,3,false) } },
        greymon:       { color: '#FF8C00', accent: '#1E90FF', size: 48, actions: { idle: _act(4,3,true), walk: _act(6,7,true), attack: _act(6,10,false), evolve: _act(10,3,false) } },
        garurumon:     { color: '#4A6FA5', accent: '#B0D0FF', size: 48, actions: { idle: _act(4,3,true), walk: _act(6,8,true), attack: _act(6,10,false), evolve: _act(10,3,false) } },
        kabuterimon:   { color: '#4B0082', accent: '#9370DB', size: 44, actions: { idle: _act(4,3,true), walk: _act(4,6,true), attack: _act(4,10,false), evolve: _act(10,3,false) } },
        togemon:       { color: '#32CD32', accent: '#90EE90', size: 44, actions: { idle: _act(4,3,true), walk: _act(4,6,true), attack: _act(4,10,false), evolve: _act(10,3,false) } },
        angemon:       { color: '#F5F5F5', accent: '#FFD700', size: 48, actions: { idle: _act(4,3,true), walk: _act(4,6,true), attack: _act(6,10,false), evolve: _act(10,3,false) } },
        birdramon:     { color: '#FF6347', accent: '#FF4500', size: 52, actions: { idle: _act(4,3,true), walk: _act(4,6,true), attack: _act(6,10,false), evolve: _act(10,3,false) } },
        garudamon:     { color: '#FFD700', accent: '#FF6347', size: 56, actions: { idle: _act(4,3,true), walk: _act(4,6,true), attack: _act(6,10,false), evolve: _act(12,3,false) } },
        metalgreymon:  { color: '#FF8C00', accent: '#B0B0B0', size: 56, actions: { idle: _act(4,3,true), walk: _act(6,7,true), attack: _act(6,10,false), evolve: _act(12,3,false) } },
        weregarurumon: { color: '#4A6FA5', accent: '#C0C0C0', size: 52, actions: { idle: _act(4,3,true), walk: _act(6,8,true), attack: _act(6,10,false), evolve: _act(10,3,false) } },
        atlurkabuterimon: { color: '#FF0000', accent: '#FFD700', size: 56, actions: { idle: _act(4,3,true), walk: _act(4,6,true), attack: _act(6,10,false), evolve: _act(12,3,false) } },
        seadramon:     { color: '#00CED1', accent: '#48D1CC', size: 44, actions: { idle: _act(4,3,true), walk: _act(4,6,true), attack: _act(4,10,false), evolve: _act(10,3,false) } },
        whamon:        { color: '#4A6FA5', accent: '#87CEEB', size: 60, actions: { idle: _act(4,2,true), walk: _act(4,4,true), attack: _act(4,8,false), evolve: _act(10,3,false) } },
        ikkakumon:     { color: '#F5F5F5', accent: '#FF6600', size: 44, actions: { idle: _act(4,3,true), walk: _act(4,6,true), attack: _act(4,10,false), evolve: _act(10,3,false) } },
        ogremon:       { color: '#556B2F', accent: '#FF6600', size: 48, actions: { idle: _act(4,3,true), walk: _act(6,7,true), attack: _act(6,10,false), evolve: _act(10,3,false) } },
    };

    const DEFAULT = { color: '#AABBCC', accent: '#CCDDEE', size: 32, actions: { idle: _act(4,3,true), walk: _act(4,6,true), attack: _act(4,8,false), evolve: _act(8,3,false) } };

    function getSpriteConfig(name) {
        const key = (name || '').toLowerCase().replace(/[\s\-]/g, '_');
        return configs[key] || DEFAULT;
    }

    function getActionConfig(name, action) {
        const cfg = getSpriteConfig(name);
        const actions = cfg.actions || {};
        return actions[action] || actions.idle || { frames: 1, fps: 1, loop: true };
    }

    return { getSpriteConfig, getActionConfig, DEFAULT };
})();
