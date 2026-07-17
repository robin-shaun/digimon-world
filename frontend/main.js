/**
 * DIGIMON WORLD - 前端主入口 (Phase 13)
 *
 * 纯 canvas, 无第三方框架.
 * 集成动画引擎 (animator.js) + 精灵数据 (sprites.js) + TTS (tts.js).
 *
 * 功能:
 *   1. fetch /api/world + /api/digimon → 画地图 + 数码兽
 *   2. 轮询 /api/digimon 更新位置, 动画引擎平滑插值
 *   3. WebSocket 实时推送 + HTTP 降级轮询
 *   4. 点击数码兽 → 侧栏详情 + "戳一下" / TTS 发言
 *   5. 密度模式 (>15 只→圆点), 离屏缓存, 天气粒子
 *   6. API_BASE: Cloudflare 注入 > 同源 > localhost:8000
 */

(function () {
    'use strict';

    console.log('🐉 Digimon World Phase 1 initializing...');

    const canvas = document.getElementById('world-map');
    const ctx = canvas.getContext('2d');

    // ---- 世界常量 (Phase 15: 大世界地图) ----
    const WORLD_W = 4000;
    const WORLD_H = 3000;
    const VIEW_W = canvas.width;   // 1200 (视口宽度)
    const VIEW_H = canvas.height;  // 800  (视口高度)

    // ---- 相机状态 ----
    let cameraX = WORLD_W / 2;  // 视口中心在世界坐标中的 X
    let cameraY = WORLD_H / 2;  // 视口中心在世界坐标中的 Y
    let zoom = 1.0;             // 缩放 (0.5 ~ 2.0)
    const ZOOM_MIN = 0.5;
    const ZOOM_MAX = 2.0;

    // ---- 拖拽状态 ----
    let isDragging = false;
    let dragStartX = 0;
    let dragStartY = 0;
    let dragStartCamX = 0;
    let dragStartCamY = 0;

    // Phase 11: 密度模式阈值 — 超过此数只画圆点
    const DENSITY_MODE_THRESHOLD = 15;

    // Phase 11: hover 状态(用于密度模式下查看详情)
    let hoveredDigimon = null;

    // ---- API 配置 ----
    // 优先级: window.API_BASE (Workers 注入) > 自动检测
    const API_BASE = (() => {
        if (typeof window.API_BASE === 'string') return window.API_BASE;
        if (window.location.origin.includes('workers.dev')) return '';  // 同源反代
        return 'http://localhost:8000';
    })();

    /** fetch with timeout — prevents indefinite hanging on unresponsive backends */
    async function fetchWithTimeout(url, options = {}, timeoutMs = 10000) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeoutMs);
        try {
            const resp = await fetch(url, { ...options, signal: controller.signal });
            return resp;
        } finally {
            clearTimeout(timer);
        }
    }

    // ---- 数码兽 emoji 映射 ----
    // 进化后 species 会变成 'champion_form' 等占位值,所以优先用中文名匹配,
    // 名字匹配不到时退回到 stage 匹配,保证进化后不会掉成 ❓。
    const NAME_EMOJI = {
        '亚古兽': '🦖', '加布兽': '🐺', '比丘兽': '🦅', '甲虫兽': '🪲',
        '巴鲁兽': '🌿', '哥玛兽': '🦭', '巴达兽': '🦇', '迪路兽': '🐱',
        '小狗兽': '🐶', '艾力兽': '⚡',
        // Phase 11: 新增数码兽
        '妖狐兽': '🦊', '小妖兽': '😈', '多路兽': '🐉',
        '小恶魔兽': '🦇', '黑加布兽': '🐺',
        '齿轮兽': '⚙️', '守卫兽': '🤖', '时钟兽': '⏰', '坦克兽': '🔫', '溜溜球兽': '🔧',
        '恶魔兽': '👿', '邪龙兽': '🐲', '吸血魔兽': '🧛',
        '死神兽': '💀', '猛鬼兽': '👻',
        '安杜路兽': '🦾', '守卫兽S': '🛡️',
        '巫师兽': '🧙', '狮子兽': '🦁', '独角兽': '🦄',
    };
    const STAGE_EMOJI = {
        rookie: '🦖',
        champion: '⚔️',
        mega: '👑',
        baby_i: '🥚',
        baby_ii: '🐣',
    };
    function getDigimonEmoji(name, species, stage) {
        if (name && NAME_EMOJI[name]) return NAME_EMOJI[name];
        if (stage && STAGE_EMOJI[stage]) return STAGE_EMOJI[stage];
        return '❓';
    }

    // ---- 心情 emoji 映射 ----
    // 后端 mood 取值: calm/excited/tired/scared/curious (digimon_agent.py)。
    // 映射到 4 个表情: 开心 😊 / 平静 😐 / 生气(受惊) 😠 / 疲惫 😴。
    const MOOD_EMOJI = {
        excited: '😊',
        curious: '😊',
        calm: '😐',
        scared: '😠',
        angry: '😠',
        tired: '😴',
    };
    function getMoodEmoji(mood) {
        return MOOD_EMOJI[mood] || '😐';
    }

    // ---- 区域样式 (Phase 15: 区域标签已硬编码到世界地图中) ----
    // 后端两个 region 的 bounds 都是整块 (0,0,960,600) 且重叠,
    // 所以标签位置在前端按语义手动指定,避免堆在左上角。
    const REGION_STYLE = {
        file_island: { label: '#4ae8c4', labelAt: { x: 32, y: 740 } },
        infinity_mountain: { label: '#b68aff', labelAt: { x: 32, y: 40 } },
    };
    const DEFAULT_STYLE = { label: '#aabbcc', labelAt: { x: 32, y: 40 } };

    // ---- 状态 ----
    const state = {
        regions: [],          // [{id, name, description, bounds, pois}]
        digimon: [],          // [{name, species, stage, attribute, region_id, position:{x,y}, current_plan}]
        selectedName: null,
        keyboardFocusIndex: -1,  // Phase 13-②: 键盘导航焦点索引 (-1 = 无)
        connected: false,
        error: null,          // 后端不可达时的错误信息
        vitality: null,       // Phase 7: 世界活力分数 (0-100)
        // Phase 10: 环境状态
        env: {
            daynight: { period: 'day', icon: '\u2600\ufe0f', is_daytime: true },
            weather: { weather: 'sunny', icon: '\u2600\ufe0f', label: '\u6674' },
            ecology: { regions: {} },
            season: { season: 'spring', label: '\u6625' },
        },
    };

    let pollTimer = null;

    // Phase 13-②: 粒子特效系统 (进化火花 / 战斗爆裂 / 戳一下涟漪)
    const particles = window.PARTICLE ? new PARTICLE.ParticleSystem() : null;

    // Phase 15: 离屏缓存已移除 — 大世界地图直接渲染每帧
    // 天空渐变懒初始化
    let _skyGradDay = null;
    let _skyGradNight = null;
    function _ensureSkyGrads() {
        if (!_skyGradDay) {
            _skyGradDay = ctx.createLinearGradient(0, 0, 0, VIEW_H);
            _skyGradDay.addColorStop(0, '#0a1233');
            _skyGradDay.addColorStop(0.6, '#1e2a5a');
            _skyGradDay.addColorStop(1, '#3a1a4a');
            _skyGradNight = ctx.createLinearGradient(0, 0, 0, VIEW_H);
            _skyGradNight.addColorStop(0, '#020518');
            _skyGradNight.addColorStop(0.6, '#0a1535');
            _skyGradNight.addColorStop(1, '#15082a');
        }
    }

    // ══════════════════════════════════════════════
    //  绘 制
    // ══════════════════════════════════════════════

    function drawSky() {
        _ensureSkyGrads();
        const isNight = !state.env.daynight.is_daytime;
        ctx.fillStyle = isNight ? _skyGradNight : _skyGradDay;
        ctx.fillRect(0, 0, VIEW_W, VIEW_H);
    }

    function drawStars() {
        for (let i = 0; i < 60; i++) {
            const x = (i * 73 + 50) % VIEW_W;
            const y = ((i * 41) % (VIEW_H * 0.5)) + 10;
            const alpha = 0.2 + (i % 5) * 0.12;
            ctx.fillStyle = `rgba(200, 220, 255, ${alpha})`;
            ctx.beginPath();
            ctx.arc(x, y, 1, 0, Math.PI * 2);
            ctx.fill();
        }
    }

    /** Phase 10: 天气粒子特效 (雨滴/雾气) */
    function drawWeatherParticles() {
        const weather = state.env.weather.weather;

        if (weather === 'rainy' || weather === 'stormy') {
            // 雨滴: 半透明白色竖线 — 视口空间
            const intensity = weather === 'stormy' ? 80 : 40;
            const alpha = weather === 'stormy' ? 0.35 : 0.2;
            for (let i = 0; i < intensity; i++) {
                const x = ((i * 173 + Date.now() * 0.08 + i * 13) % (VIEW_W + 40)) - 20;
                const y = ((i * 97 + Date.now() * 0.15) % (VIEW_H + 20)) - 10;
                const len = 8 + (i % 12);
                ctx.strokeStyle = `rgba(180, 210, 255, ${alpha})`;
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(x, y);
                ctx.lineTo(x - 2, y + len);
                ctx.stroke();
            }
        }

        if (weather === 'foggy') {
            for (let i = 0; i < 25; i++) {
                const y = ((i * 89 + 40) % VIEW_H);
                const x = ((i * 137 + Date.now() * 0.03) % (VIEW_W + 100)) - 50;
                const w = 80 + (i * 37) % 160;
                const alpha = 0.04 + (i % 6) * 0.02;
                ctx.fillStyle = `rgba(200, 210, 230, ${alpha})`;
                ctx.beginPath();
                ctx.ellipse(x, y, w, 8 + (i % 10), 0, 0, Math.PI * 2);
                ctx.fill();
            }
        }
    }

    /** Phase 15: 大世界地图 — 4000x3000, 程序化渲染区块 */
    function drawWorldBackground() {
        // ---- 无尽海 (蓝色底色全覆盖) ----
        ctx.fillStyle = '#0a2a4a';
        ctx.fillRect(0, 0, WORLD_W, WORLD_H);

        // 海面纹理 (浅色波浪线)
        ctx.strokeStyle = 'rgba(20, 80, 140, 0.25)';
        ctx.lineWidth = 1;
        for (let y = 0; y < WORLD_H; y += 40) {
            ctx.beginPath();
            for (let x = 0; x < WORLD_W; x += 20) {
                const wy = y + Math.sin(x * 0.01 + y * 0.005) * 6;
                if (x === 0) ctx.moveTo(x, wy);
                else ctx.lineTo(x, wy);
            }
            ctx.stroke();
        }

        // ---- 服务器大陆 (棕色, 左上区域 200-3200, 200-2100) ----
        const continentGrad = ctx.createLinearGradient(200, 200, 200, 2100);
        continentGrad.addColorStop(0, '#5a4a2a');
        continentGrad.addColorStop(0.3, '#6b5b3a');
        continentGrad.addColorStop(0.7, '#4a3a1a');
        continentGrad.addColorStop(1, '#3a2a10');
        ctx.fillStyle = continentGrad;
        ctx.beginPath();
        ctx.moveTo(200, 200);
        ctx.lineTo(3200, 200);
        ctx.lineTo(3150, 500);
        ctx.lineTo(3300, 900);
        ctx.lineTo(3100, 1400);
        ctx.lineTo(2900, 1800);
        ctx.lineTo(2600, 2100);
        ctx.lineTo(400, 2050);
        ctx.lineTo(200, 1500);
        ctx.closePath();
        ctx.fill();

        // 大陆边缘描边
        ctx.strokeStyle = 'rgba(100, 80, 40, 0.6)';
        ctx.lineWidth = 3;
        ctx.stroke();

        // 大陆内部纹理 (随机浅色斑块)
        for (let i = 0; i < 30; i++) {
            const cx = 400 + ((i * 317 + 100) % 2600);
            const cy = 300 + ((i * 197 + 50) % 1700);
            ctx.fillStyle = `rgba(${80 + (i % 30)}, ${60 + (i % 25)}, ${20 + (i % 15)}, 0.15)`;
            ctx.beginPath();
            ctx.ellipse(cx, cy, 40 + (i % 80), 20 + (i % 40), i * 0.3, 0, Math.PI * 2);
            ctx.fill();
        }

        // ---- 螺旋山 (紫色, 3300-3950, 800-1500) ----
        // 山体
        const mtGrad = ctx.createLinearGradient(3625, 800, 3625, 1500);
        mtGrad.addColorStop(0, '#7c3aed');
        mtGrad.addColorStop(0.3, '#5b2d8e');
        mtGrad.addColorStop(0.7, '#3a1f5a');
        mtGrad.addColorStop(1, '#2a1540');
        ctx.fillStyle = mtGrad;
        ctx.beginPath();
        ctx.moveTo(3300, 1500);
        ctx.lineTo(3400, 1300);
        ctx.lineTo(3500, 1100);
        ctx.lineTo(3625, 800);
        ctx.lineTo(3750, 1100);
        ctx.lineTo(3850, 1300);
        ctx.lineTo(3950, 1500);
        ctx.closePath();
        ctx.fill();

        // 山顶光晕
        const peakGlow = ctx.createRadialGradient(3625, 800, 10, 3625, 800, 200);
        peakGlow.addColorStop(0, 'rgba(124, 58, 237, 0.7)');
        peakGlow.addColorStop(0.5, 'rgba(124, 58, 237, 0.2)');
        peakGlow.addColorStop(1, 'rgba(124, 58, 237, 0)');
        ctx.fillStyle = peakGlow;
        ctx.beginPath();
        ctx.arc(3625, 800, 200, 0, Math.PI * 2);
        ctx.fill();

        // 螺旋纹理
        ctx.strokeStyle = 'rgba(180, 130, 255, 0.35)';
        ctx.lineWidth = 2;
        ctx.beginPath();
        for (let a = 0; a < Math.PI * 6; a += 0.1) {
            const r = 10 + a * 18;
            const sx = 3625 + Math.cos(a) * r;
            const sy = 850 + Math.sin(a) * r;
            if (a === 0) ctx.moveTo(sx, sy);
            else ctx.lineTo(sx, sy);
        }
        ctx.stroke();

        // ---- 文件岛 (绿色/岛屿色, 右下 2900-3860, 2300-2900) ----
        const islandGrad = ctx.createLinearGradient(2900, 2300, 2900, 2900);
        islandGrad.addColorStop(0, '#2a6b3a');
        islandGrad.addColorStop(0.4, '#3a8b4a');
        islandGrad.addColorStop(0.8, '#1a4a2a');
        islandGrad.addColorStop(1, '#0a3a1a');
        ctx.fillStyle = islandGrad;
        ctx.beginPath();
        ctx.moveTo(2900, 2500);
        ctx.quadraticCurveTo(3000, 2300, 3200, 2350);
        ctx.quadraticCurveTo(3450, 2280, 3600, 2400);
        ctx.quadraticCurveTo(3860, 2350, 3800, 2600);
        ctx.quadraticCurveTo(3900, 2800, 3700, 2900);
        ctx.quadraticCurveTo(3500, 2950, 3300, 2880);
        ctx.quadraticCurveTo(3100, 2920, 2950, 2850);
        ctx.quadraticCurveTo(2880, 2700, 2900, 2500);
        ctx.fill();

        // 岛屿边缘
        ctx.strokeStyle = 'rgba(74, 180, 120, 0.7)';
        ctx.lineWidth = 3;
        ctx.stroke();

        // 沙滩环
        ctx.strokeStyle = 'rgba(200, 180, 120, 0.4)';
        ctx.lineWidth = 8;
        ctx.stroke();

        // 岛内树木点缀
        for (let i = 0; i < 20; i++) {
            const tx = 3000 + ((i * 257 + 50) % 750);
            const ty = 2400 + ((i * 163 + 30) % 450);
            ctx.fillStyle = 'rgba(30, 100, 30, 0.5)';
            ctx.beginPath();
            ctx.arc(tx, ty, 6 + (i % 8), 0, Math.PI * 2);
            ctx.fill();
            ctx.fillStyle = 'rgba(50, 140, 50, 0.4)';
            ctx.beginPath();
            ctx.arc(tx - 2, ty - 3, 4, 0, Math.PI * 2);
            ctx.fill();
        }

        // ---- 小型岛屿群 (世界各处) ----
        const smallIsles = [
            [500, 2400, 60], [700, 2600, 40], [1200, 2550, 50],
            [1800, 2400, 35], [2200, 2500, 45], [2600, 2600, 55],
            [150, 500, 30], [400, 300, 25], [1000, 400, 35],
            [3200, 2200, 35], [3700, 2100, 40],
        ];
        for (const [ix, iy, ir] of smallIsles) {
            ctx.fillStyle = '#1a4a3a';
            ctx.beginPath();
            ctx.ellipse(ix, iy, ir, ir * 0.55, 0.3, 0, Math.PI * 2);
            ctx.fill();
            ctx.strokeStyle = 'rgba(90, 160, 100, 0.4)';
            ctx.lineWidth = 1.5;
            ctx.stroke();
            // 小沙滩
            ctx.fillStyle = 'rgba(180, 150, 100, 0.3)';
            ctx.beginPath();
            ctx.arc(ix + ir * 0.3, iy + ir * 0.3, ir * 0.35, 0, Math.PI * 2);
            ctx.fill();
        }

        // ---- 区域名称标注 ----
        ctx.font = 'bold 24px monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';

        // 服务器大陆
        ctx.fillStyle = 'rgba(200, 170, 120, 0.7)';
        ctx.fillText('服务器大陆', 1700, 1100);
        ctx.font = '14px monospace';
        ctx.fillText('SERVER CONTINENT', 1700, 1130);

        // 螺旋山
        ctx.font = 'bold 20px monospace';
        ctx.fillStyle = 'rgba(200, 150, 255, 0.8)';
        ctx.fillText('螺旋山', 3625, 1000);
        ctx.font = '12px monospace';
        ctx.fillText('SPIRAL MOUNTAIN', 3625, 1025);

        // 文件岛
        ctx.font = 'bold 22px monospace';
        ctx.fillStyle = 'rgba(100, 220, 150, 0.75)';
        ctx.fillText('文件岛', 3400, 2580);
        ctx.font = '13px monospace';
        ctx.fillText('FILE ISLAND', 3400, 2610);

        // 无尽海标签 (散布)
        ctx.font = '13px monospace';
        ctx.fillStyle = 'rgba(80, 160, 220, 0.4)';
        ctx.fillText('∞ 无尽海', 200, 2800);
        ctx.fillText('ENDLESS SEA', 200, 2825);
        ctx.fillText('∞', 3800, 500);
        ctx.fillText('∞', 100, 1800);

        // 底部标题
        ctx.font = '18px monospace';
        ctx.fillStyle = 'rgba(255, 255, 255, 0.35)';
        ctx.fillText('— DIGITAL WORLD · FILE ISLAND —', WORLD_W / 2, WORLD_H - 30);

        // ---- POI 标记 (保留) ----
        drawPOIsTo(ctx);
    }

    /** 画 POI 标记 */
    function drawPOIsTo(c) {
        for (const region of state.regions) {
            if (!region.pois) continue;
            for (const [, poi] of Object.entries(region.pois)) {
                const { x, y, label } = poi;

                // 标记点
                c.fillStyle = 'rgba(255, 215, 0, 0.85)';
                c.beginPath();
                c.arc(x, y, 5, 0, Math.PI * 2);
                c.fill();

                // 旗子
                c.strokeStyle = 'rgba(255, 215, 0, 0.7)';
                c.lineWidth = 1;
                c.beginPath();
                c.moveTo(x, y);
                c.lineTo(x, y - 18);
                c.stroke();
                c.fillStyle = 'rgba(255, 215, 0, 0.8)';
                c.beginPath();
                c.moveTo(x, y - 18);
                c.lineTo(x + 12, y - 14);
                c.lineTo(x, y - 10);
                c.closePath();
                c.fill();

                // 标签
                c.fillStyle = 'rgba(255, 215, 0, 0.9)';
                c.font = '12px monospace';
                c.textAlign = 'left';
                c.fillText(label, x + 16, y - 8);
            }
        }
    }

    /** Phase 11: 画数码兽 — 支持密度模式(>15只→圆点, hover看详情)
     *  Phase 13-②: + walk cycle animation + proximity glow lines */
    function drawDigimon() {
        const count = state.digimon.length;
        const densityMode = count > DENSITY_MODE_THRESHOLD;

        // Phase 13-②: 近距离数码兽连线 — 距离 < 80px 时画半透明连线
        if (!densityMode && state.digimon.length >= 2) {
            for (let i = 0; i < state.digimon.length; i++) {
                const a = state.digimon[i];
                const aSt = window.ANIM ? ANIM.manager.get(a.name) : null;
                const ax = aSt ? aSt.renderX() : a.position.x;
                const ay = aSt ? aSt.renderY() : a.position.y;
                for (let j = i + 1; j < state.digimon.length; j++) {
                    const b = state.digimon[j];
                    const bSt = window.ANIM ? ANIM.manager.get(b.name) : null;
                    const bx = bSt ? bSt.renderX() : b.position.x;
                    const by = bSt ? bSt.renderY() : b.position.y;
                    const dx = bx - ax;
                    const dy2 = by - ay;
                    const dist = Math.sqrt(dx * dx + dy2 * dy2);
                    if (dist < 80) {
                        const alpha = Math.max(0, (1 - dist / 80) * 0.2);
                        ctx.strokeStyle = `rgba(255,215,0,${alpha.toFixed(2)})`;
                        ctx.lineWidth = 0.5;
                        ctx.setLineDash([3, 6]);
                        ctx.beginPath();
                        ctx.moveTo(ax, ay);
                        ctx.lineTo(bx, by);
                        ctx.stroke();
                        ctx.setLineDash([]);
                    }
                }
            }
        }

        for (const d of state.digimon) {
            // Phase 13-②: use interpolated position from animation engine
            const animSt = window.ANIM ? ANIM.manager.get(d.name) : null;
            const x = animSt ? animSt.renderX() : d.position.x;
            const y = animSt ? animSt.renderY() : d.position.y;
            const bounce = animSt ? animSt.idleBounce() : 0;
            const walkBounce = animSt ? animSt.walkBounce() : 0;  // Phase 13-②: walk cycle
            const walkLean = animSt ? animSt.walkLean() : 0;      // Phase 13-②: tilt during walk
            const idleScale = animSt ? animSt.idleScale() : 1.0;
            const isSelected = d.name === state.selectedName;
            const isHovered = d.name === hoveredDigimon;
            const emoji = getDigimonEmoji(d.name, d.species, d.stage);
            const nameShort = d.name.charAt(0); // 取名字首字

            if (densityMode) {
                // ═══ 密度模式: 只画小圆点 + 首字 ═══
                const dotSize = isSelected ? 7 : (isHovered ? 6 : 4);
                const dotAlpha = isSelected ? 1.0 : (isHovered ? 0.85 : 0.5);

                // 属性颜色: vaccine=蓝, data=绿, virus=红, free=紫
                const attrColors = { vaccine: '#4ae8c4', data: '#4ae84a', virus: '#e84a4a', free: '#b86aff' };
                const dotColor = attrColors[d.attribute] || '#aabbcc';
                const dy = y + bounce;  // Phase 13-②: idle bounce

                ctx.fillStyle = dotColor.replace(')', `, ${dotAlpha})`).replace('rgb', 'rgba');
                if (dotColor.startsWith('#')) {
                    ctx.globalAlpha = dotAlpha;
                    ctx.fillStyle = dotColor;
                }
                ctx.beginPath();
                ctx.arc(x, dy, dotSize, 0, Math.PI * 2);
                ctx.fill();
                ctx.globalAlpha = 1.0;

                // 选中/hover 时才画名字首字
                if (isSelected || isHovered) {
                    ctx.fillStyle = isSelected ? '#ffd700' : '#ffffff';
                    ctx.font = '10px monospace';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'bottom';
                    ctx.fillText(nameShort + ' ' + emoji, x, dy - 6);
                    ctx.textBaseline = 'alphabetic';
                }

                if (isSelected) {
                    ctx.strokeStyle = '#ffd700';
                    ctx.lineWidth = 2;
                    ctx.beginPath();
                    ctx.arc(x, dy, 10, 0, Math.PI * 2);
                    ctx.stroke();
                }

                // 键盘焦点: 青色虚线环 (区别于选中金环)
                const kfIdx = state.keyboardFocusIndex;
                if (!isSelected && kfIdx >= 0 && state.digimon[kfIdx] === d) {
                    const pulse = 0.6 + 0.4 * Math.sin(Date.now() * 0.005);
                    ctx.strokeStyle = `rgba(0, 212, 255, ${pulse.toFixed(2)})`;
                    ctx.lineWidth = 2;
                    ctx.setLineDash([4, 3]);
                    ctx.beginPath();
                    ctx.arc(x, dy, 11, 0, Math.PI * 2);
                    ctx.stroke();
                    ctx.setLineDash([]);
                }
                // Phase 15: 注入事件高亮 — 金色脉冲光环
                if (highlightDigimons.has(d.name)) {
                    const hPulse = 0.5 + 0.5 * Math.sin(Date.now() * 0.008);
                    ctx.strokeStyle = `rgba(255, 215, 0, ${hPulse.toFixed(2)})`;
                    ctx.lineWidth = 3;
                    ctx.beginPath();
                    ctx.arc(x, dy, dotSize + 8, 0, Math.PI * 2);
                    ctx.stroke();
                }
            } else {
                // ═══ 普通模式: 小emoji + 首字 + 精灵色光环 ═══
                // Phase 13-②: walk cycle bounce on top of idle bounce
                const dy = y + bounce + walkBounce;
                const spriteCfg = window.SPRITE_DATA ? SPRITE_DATA.getSpriteConfig(d.species || d.name) : null;
                const spriteColor = spriteCfg ? spriteCfg.color : '#00d4ff';
                const spriteAccent = spriteCfg ? spriteCfg.accent : '#00d4ff';

                // 精灵色光环 (Phase 13-②: 使用 sprites.js 颜色数据)
                const aura = ctx.createRadialGradient(x, dy, 3, x, dy, 18);
                aura.addColorStop(0, isSelected ? 'rgba(255, 215, 0, 0.8)' : spriteColor + 'cc');
                aura.addColorStop(0.5, spriteColor + '44');
                aura.addColorStop(1, 'rgba(0, 0, 0, 0)');
                ctx.fillStyle = aura;
                ctx.beginPath();
                ctx.arc(x, dy, 18, 0, Math.PI * 2);
                ctx.fill();

                // 精灵色细环
                ctx.strokeStyle = isSelected ? '#ffd700' : spriteAccent + '66';
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.arc(x, dy, 16, 0, Math.PI * 2);
                ctx.stroke();

                // Phase 13-②: 移动轨迹拖尾 — 运动时画 2 个渐隐残影
                if (animSt && animSt.isMoving()) {
                    const angle = animSt.moveAngle();
                    const cosA = Math.cos(angle);
                    const sinA = Math.sin(angle);
                    for (let i = 1; i <= 2; i++) {
                        const alpha = 0.18 - i * 0.06;
                        const tx = x - cosA * i * 10;
                        const ty = dy - sinA * i * 10;
                        ctx.fillStyle = spriteAccent + Math.round(alpha * 255).toString(16).padStart(2, '0');
                        ctx.beginPath();
                        ctx.arc(tx, ty, 6 - i, 0, Math.PI * 2);
                        ctx.fill();
                    }
                }

                // Emoji (with idle scale + walk lean + walk bounce)
                ctx.save();
                ctx.translate(x, dy);
                ctx.rotate(walkLean);  // Phase 13-②: tilt body during movement
                ctx.scale(idleScale, idleScale);
                ctx.font = '18px serif';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(emoji, 0, 0);
                ctx.restore();

                // 首字 + 心情
                ctx.fillStyle = isSelected ? '#ffd700' : '#ffffff';
                ctx.font = '10px monospace';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'bottom';
                ctx.fillText(nameShort + ' ' + getMoodEmoji(d.mood), x, dy - 14);

                if (isSelected) {
                    ctx.strokeStyle = '#ffd700';
                    ctx.lineWidth = 2;
                    ctx.beginPath();
                    ctx.arc(x, dy, 15, 0, Math.PI * 2);
                    ctx.stroke();
                }

                // 键盘焦点: 青色虚线环
                const kfIdx2 = state.keyboardFocusIndex;
                if (!isSelected && kfIdx2 >= 0 && state.digimon[kfIdx2] === d) {
                    const pulse2 = 0.6 + 0.4 * Math.sin(Date.now() * 0.005);
                    ctx.strokeStyle = `rgba(0, 212, 255, ${pulse2.toFixed(2)})`;
                    ctx.lineWidth = 2;
                    ctx.setLineDash([4, 3]);
                    ctx.beginPath();
                    ctx.arc(x, dy, 19, 0, Math.PI * 2);
                    ctx.stroke();
                    ctx.setLineDash([]);
                }
                // Phase 15: 注入事件高亮 — 金色脉冲光环 + 阴影
                if (highlightDigimons.has(d.name)) {
                    const hPulse2 = 0.5 + 0.5 * Math.sin(Date.now() * 0.008);
                    ctx.strokeStyle = `rgba(255, 215, 0, ${hPulse2.toFixed(2)})`;
                    ctx.lineWidth = 2.5;
                    ctx.shadowColor = 'rgba(255, 215, 0, 0.6)';
                    ctx.shadowBlur = 12;
                    ctx.beginPath();
                    ctx.arc(x, dy, 22, 0, Math.PI * 2);
                    ctx.stroke();
                    ctx.shadowBlur = 0;
                }
            }
        }
        ctx.textBaseline = 'alphabetic';
    }

    /** Phase 15: 标题已移至 drawWorldBackground 中 */

    /** 后端不可达时的 placeholder */
    function drawPlaceholder() {
        // 画自己的天空 (不依赖缓存, 离线也能看)
        const isNight = !state.env.daynight.is_daytime;
        _ensureSkyGrads();
        ctx.fillStyle = isNight ? _skyGradNight : _skyGradDay;
        ctx.fillRect(0, 0, VIEW_W, VIEW_H);

        // 星空
        for (let i = 0; i < 60; i++) {
            const x = (i * 73 + 50) % VIEW_W;
            const y = ((i * 41) % (VIEW_H * 0.5)) + 10;
            const alpha = 0.2 + (i % 5) * 0.12;
            ctx.fillStyle = `rgba(200, 220, 255, ${alpha})`;
            ctx.beginPath();
            ctx.arc(x, y, 1, 0, Math.PI * 2);
            ctx.fill();
        }

        // 大标题
        ctx.fillStyle = 'rgba(255, 255, 255, 0.7)';
        ctx.font = 'bold 28px monospace';
        ctx.textAlign = 'center';
        ctx.fillText('🐉 DIGIMON WORLD', VIEW_W / 2, VIEW_H / 2 - 40);

        // 提示信息
        ctx.fillStyle = 'rgba(255, 100, 100, 0.9)';
        ctx.font = '14px monospace';
        ctx.fillText('⚠ 无法连接后端', VIEW_W / 2, VIEW_H / 2 + 10);

        ctx.fillStyle = 'rgba(200, 200, 220, 0.7)';
        ctx.font = '12px monospace';
        ctx.fillText(`尝试连接: ${API_BASE || '(同源)'}`, VIEW_W / 2, VIEW_H / 2 + 40);
        ctx.fillText('请确认后端已启动: cd backend && uvicorn ...', VIEW_W / 2, VIEW_H / 2 + 62);
        ctx.fillText('或 python -m digimon_world.api.app', VIEW_W / 2, VIEW_H / 2 + 82);

        // 离线 placeholder 数码兽
        ctx.font = '36px serif';
        ctx.globalAlpha = 0.3;
        ctx.fillText('🦖   🐺   🦅', VIEW_W / 2, VIEW_H / 2 + 140);
        ctx.globalAlpha = 1.0;
    }

    /** Phase 15: 完整渲染 — 视口空间 + 世界空间 */
    function renderNow() {
        if (!state.connected && state.digimon.length === 0) {
            drawPlaceholder();
            return;
        }

        // ---- 1. 视口空间: 天空 + 星星 (始终覆盖全视口) ----
        drawSky();
        drawStars();

        // ---- 2. 世界空间: 地图 + 数码兽 (应用相机偏移) ----
        ctx.save();
        // 将视口中心映射到世界坐标 cameraX, cameraY
        ctx.translate(VIEW_W / 2, VIEW_H / 2);
        ctx.scale(zoom, zoom);
        ctx.translate(-cameraX, -cameraY);

        drawWorldBackground();

        // 动态内容: 数码兽位置
        pruneHighlights(typeof performance !== 'undefined' ? performance.now() : Date.now());
        drawDigimon();

        ctx.restore();

        // ---- 3. 视口空间: 天气粒子 + 粒子特效 ----
        drawWeatherParticles();

        // Phase 13-②: 粒子特效 (进化火花 / 战斗爆裂等)
        // 粒子在世界空间位置需要转换到视口
        if (particles) {
            ctx.save();
            ctx.translate(VIEW_W / 2, VIEW_H / 2);
            ctx.scale(zoom, zoom);
            ctx.translate(-cameraX, -cameraY);
            particles.draw(ctx);
            ctx.restore();
        }

        // ---- 4. 小地图 + 面板按钮 (视口空间) ----
        drawMinimap();
    }

    // render() 可能在一帧内被多次触发 (轮询 / 点击 / 加载), 用 rAF 防抖:
    // 同一帧内的多次调用合并成一次绘制, 且绘制与浏览器刷新对齐。
    let rafPending = false;
    // Phase 13-②: delta-time tracker for animation engine
    let lastFrameTime = performance.now();
    function render() {
        if (rafPending) return;
        rafPending = true;
        requestAnimationFrame((now) => {
            rafPending = false;
            const delta = Math.min((now - lastFrameTime) / 1000, 0.1); // cap at 100ms
            lastFrameTime = now;
            // Update animation engine before drawing
            if (window.ANIM) {
                ANIM.manager.updateAll(delta);
                // Phase 13-②: footstep SFX while digimon are moving
                if (window.SFX && state.digimon.length > 0) {
                    let anyMoving = false;
                    for (const d of state.digimon) {
                        const st = ANIM.manager.get(d.name);
                        if (st && st.isMoving()) {
                            anyMoving = true;
                            break;
                        }
                    }
                    if (anyMoving) SFX.play('footstep');
                }
            }
            // Phase 13-②: 粒子特效更新
            if (particles) particles.update(delta);
            renderNow();
        });
    }

    // ══════════════════════════════════════════════
    //  Phase 15: 视口拖拽
    // ══════════════════════════════════════════════

    canvas.addEventListener('mousedown', (ev) => {
        // 忽略小地图区域内的拖拽
        const rect = canvas.getBoundingClientRect();
        const mx = (ev.clientX - rect.left) * (VIEW_W / rect.width);
        const my = (ev.clientY - rect.top) * (VIEW_H / rect.height);
        if (isClickOnMinimap(mx, my)) {
            handleMinimapClick(mx, my);
            return;
        }
        isDragging = true;
        dragStartX = ev.clientX;
        dragStartY = ev.clientY;
        dragStartCamX = cameraX;
        dragStartCamY = cameraY;
        canvas.style.cursor = 'grabbing';
    });

    window.addEventListener('mousemove', (ev) => {
        if (!isDragging) return;
        const dx = (ev.clientX - dragStartX) / zoom;
        const dy = (ev.clientY - dragStartY) / zoom;
        cameraX = dragStartCamX - dx;
        cameraY = dragStartCamY - dy;
        // 限制相机在世界范围内
        clampCamera();
        render();
    });

    window.addEventListener('mouseup', () => {
        if (isDragging) {
            isDragging = false;
            canvas.style.cursor = '';
        }
    });

    canvas.addEventListener('wheel', (ev) => {
        ev.preventDefault();
        const rect = canvas.getBoundingClientRect();
        const mx = (ev.clientX - rect.left) * (VIEW_W / rect.width);
        const my = (ev.clientY - rect.top) * (VIEW_H / rect.height);

        // 缩放中心: 鼠标位置对应的世界坐标
        const worldBefore = screenToWorld(mx, my);

        // 调整缩放
        const delta = ev.deltaY > 0 ? -0.1 : 0.1;
        zoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, zoom + delta));

        // 缩放后保持鼠标指向的世界坐标不变
        const worldAfter = screenToWorld(mx, my);
        cameraX += worldBefore.x - worldAfter.x;
        cameraY += worldBefore.y - worldAfter.y;
        clampCamera();
        render();
    }, { passive: false });

    /** 限制相机不超出世界边界 */
    function clampCamera() {
        const halfVW = VIEW_W / zoom / 2;
        const halfVH = VIEW_H / zoom / 2;
        cameraX = Math.max(halfVW, Math.min(WORLD_W - halfVW, cameraX));
        cameraY = Math.max(halfVH, Math.min(WORLD_H - halfVH, cameraY));
    }

    // ══════════════════════════════════════════════
    //  Phase 15: 小地图
    // ══════════════════════════════════════════════

    const MINIMAP_W = 180;
    const MINIMAP_H = 135;
    const MINIMAP_MARGIN = 12;
    let minimapVisible = true;

    function isClickOnMinimap(mx, my) {
        if (!minimapVisible) return false;
        const mmX = VIEW_W - MINIMAP_W - MINIMAP_MARGIN;
        const mmY = VIEW_H - MINIMAP_H - MINIMAP_MARGIN - 40; // 40px for toggle button
        return mx >= mmX && mx <= mmX + MINIMAP_W && my >= mmY && my <= mmY + MINIMAP_H;
    }

    function handleMinimapClick(mx, my) {
        const mmX = VIEW_W - MINIMAP_W - MINIMAP_MARGIN;
        const mmY = VIEW_H - MINIMAP_H - MINIMAP_MARGIN - 40;
        // 点击在小地图内的位置 (0-1 比例)
        const rx = (mx - mmX) / MINIMAP_W;
        const ry = (my - mmY) / MINIMAP_H;
        // 跳转到对应世界坐标
        cameraX = rx * WORLD_W;
        cameraY = ry * WORLD_H;
        clampCamera();
        render();
    }

    function drawMinimap() {
        if (!minimapVisible) return;
        const mmX = VIEW_W - MINIMAP_W - MINIMAP_MARGIN;
        const mmY = VIEW_H - MINIMAP_H - MINIMAP_MARGIN - 40;

        // 半透明背景
        ctx.fillStyle = 'rgba(5, 10, 30, 0.75)';
        ctx.strokeStyle = 'rgba(0, 212, 255, 0.5)';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.roundRect(mmX, mmY, MINIMAP_W, MINIMAP_H, 6);
        ctx.fill();
        ctx.stroke();

        ctx.save();
        ctx.beginPath();
        ctx.roundRect(mmX, mmY, MINIMAP_W, MINIMAP_H, 6);
        ctx.clip();

        const scaleX = MINIMAP_W / WORLD_W;
        const scaleY = MINIMAP_H / WORLD_H;

        // ---- 无尽海 (蓝色底色) ----
        ctx.fillStyle = '#0a2a4a';
        ctx.fillRect(mmX, mmY, MINIMAP_W, MINIMAP_H);

        // ---- 服务器大陆 (棕色缩略) ----
        ctx.fillStyle = '#5a4a2a';
        ctx.beginPath();
        ctx.moveTo(mmX + 200 * scaleX, mmY + 200 * scaleY);
        ctx.lineTo(mmX + 3200 * scaleX, mmY + 200 * scaleY);
        ctx.lineTo(mmX + 2600 * scaleX, mmY + 2100 * scaleY);
        ctx.lineTo(mmX + 400 * scaleX, mmY + 2050 * scaleY);
        ctx.lineTo(mmX + 200 * scaleX, mmY + 1500 * scaleY);
        ctx.closePath();
        ctx.fill();

        // ---- 螺旋山 (紫色缩略) ----
        ctx.fillStyle = '#7c3aed';
        ctx.beginPath();
        ctx.moveTo(mmX + 3300 * scaleX, mmY + 1500 * scaleY);
        ctx.lineTo(mmX + 3625 * scaleX, mmY + 800 * scaleY);
        ctx.lineTo(mmX + 3950 * scaleX, mmY + 1500 * scaleY);
        ctx.closePath();
        ctx.fill();

        // ---- 文件岛 (绿色缩略) ----
        ctx.fillStyle = '#2a6b3a';
        ctx.beginPath();
        ctx.ellipse(mmX + 3400 * scaleX, mmY + 2600 * scaleY, 45, 30, 0, 0, Math.PI * 2);
        ctx.fill();

        // ---- 当前视口矩形 ----
        const halfVW = VIEW_W / zoom / 2;
        const halfVH = VIEW_H / zoom / 2;
        const vx = mmX + (cameraX - halfVW) * scaleX;
        const vy = mmY + (cameraY - halfVH) * scaleY;
        const vw = VIEW_W / zoom * scaleX;
        const vh = VIEW_H / zoom * scaleY;

        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 2;
        ctx.strokeRect(
            Math.max(mmX, vx),
            Math.max(mmY, vy),
            Math.min(MINIMAP_W, vw),
            Math.min(MINIMAP_H, vh)
        );

        // 中心十字
        const cx = mmX + cameraX * scaleX;
        const cy = mmY + cameraY * scaleY;
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
        ctx.lineWidth = 0.5;
        ctx.beginPath();
        ctx.moveTo(cx - 3, cy);
        ctx.lineTo(cx + 3, cy);
        ctx.moveTo(cx, cy - 3);
        ctx.lineTo(cx, cy + 3);
        ctx.stroke();

        ctx.restore();
    }

    // ══════════════════════════════════════════════
    //  Phase 15: 面板折叠切换
    // ══════════════════════════════════════════════

    let panelStatsVisible = false;
    let panelNarrativeVisible = false;
    let panelSidebarVisible = false;

    function initPanelToggles() {
        createToggleButton('toggle-stats', '📊', '左上', () => {
            panelStatsVisible = !panelStatsVisible;
            const bar = document.getElementById('status-bar');
            if (bar) bar.classList.toggle('panel-open', panelStatsVisible);
            updateToggleBtn('toggle-stats', panelStatsVisible);
        });

        createToggleButton('toggle-narrative', '📖', '右上', () => {
            panelNarrativeVisible = !panelNarrativeVisible;
            const panel = document.querySelector('.narrative-panel');
            if (panel) panel.classList.toggle('panel-open', panelNarrativeVisible);
            updateToggleBtn('toggle-narrative', panelNarrativeVisible);
        });

        createToggleButton('toggle-sidebar', '👥', '左下', () => {
            panelSidebarVisible = !panelSidebarVisible;
            const sb = document.getElementById('sidebar');
            if (sb) sb.classList.toggle('open', panelSidebarVisible);
            updateToggleBtn('toggle-sidebar', panelSidebarVisible);
        });

        createToggleButton('toggle-minimap', '🗺️', '右下', () => {
            minimapVisible = !minimapVisible;
            updateToggleBtn('toggle-minimap', minimapVisible);
            render();
        });

        // 小地图按钮放在小地图上方
        const mmBtn = document.getElementById('toggle-minimap');
        if (mmBtn) {
            mmBtn.style.bottom = (MINIMAP_H + MINIMAP_MARGIN + 52) + 'px';
        }
    }

    function createToggleButton(id, icon, position, onClick) {
        if (document.getElementById(id)) return;
        const btn = document.createElement('button');
        btn.id = id;
        btn.className = 'panel-toggle-btn';
        btn.textContent = icon;
        btn.title = '切换面板';
        btn.addEventListener('click', onClick);
        // 定位
        switch (position) {
            case '左上':
                btn.style.top = '8px';
                btn.style.left = '8px';
                break;
            case '右上':
                btn.style.top = '8px';
                btn.style.right = '8px';
                break;
            case '左下':
                btn.style.bottom = '8px';
                btn.style.left = '8px';
                break;
            case '右下':
                btn.style.right = '8px';
                // bottom set separately for minimap button
                btn.style.bottom = '48px';
                break;
        }
        document.body.appendChild(btn);
    }

    function updateToggleBtn(id, active) {
        const btn = document.getElementById(id);
        if (btn) btn.classList.toggle('active', active);
    }

    // ══════════════════════════════════════════════
    //  状态栏
    // ══════════════════════════════════════════════

    function updateStatusBar() {
        const timeEl = document.getElementById('world-time');
        const countEl = document.getElementById('digimon-count');
        const battleEl = document.getElementById('battle-count');
        const vitalityEl = document.getElementById('vitality-score');
        const phaseEl = document.getElementById('phase');

        // Phase 10: 环境图标
        const dnIcon = state.env.daynight.icon || '\u2600\ufe0f';
        const wxIcon = state.env.weather.icon || '\u2600\ufe0f';
        const snLabel = state.env.season.label || '\u6625';

        if (timeEl) timeEl.textContent = `\u4e16\u754c\u65f6\u95f4: ${dnIcon} ${new Date().toLocaleTimeString('zh-CN')}`;
        if (countEl) countEl.textContent = `\u6570\u7801\u517d: ${state.digimon.length}`;
        if (battleEl) battleEl.textContent = `\u6218\u6597: ${battleCount24h}`;
        if (vitalityEl) vitalityEl.textContent = `\u6d3b\u529b: ${state.vitality != null ? state.vitality.toFixed(0) : '--'}`;

        const connStatus = state.connected ? '\ud83d\udfe2 \u5728\u7ebf' : '\ud83d\udd34 \u79bb\u7ebf';
        // Phase 10: 状态栏显示天气+季节
        if (phaseEl) phaseEl.textContent = `${wxIcon} ${snLabel} · Phase 11 · ${connStatus}`;
    }

    // ══════════════════════════════════════════════
    //  API 通信
    // ══════════════════════════════════════════════

    /** 拉取地图数据 (regions + POIs) */
    async function fetchWorld() {
        try {
            const resp = await fetchWithTimeout(API_BASE + '/api/world', { cache: 'no-store' });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            const data = await resp.json();
            state.regions = data.regions || [];
            state.connected = true;
            state.error = null;
            // Phase 15: regions 变化 → 触发重渲染
            console.log('[api] /api/world OK, regions:', state.regions.length);
        } catch (err) {
            console.warn('[api] /api/world 不可达:', err.message);
            state.error = err.message;
            // regions 不清空 — 保留上次成功拉取的
        }
    }

    /** 拉取数码兽列表 (轻量)
     *  用 AbortController 防并发: 上一次请求还没回来就发下一次时,
     *  先取消旧请求, 避免慢响应堆积 / 旧数据覆盖新数据。 */
    let digimonAbort = null;
    async function fetchDigimon() {
        if (digimonAbort) digimonAbort.abort();
        const ctrl = new AbortController();
        digimonAbort = ctrl;
        try {
            const resp = await fetchWithTimeout(API_BASE + '/api/digimon', { cache: 'no-store', signal: ctrl.signal });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            const data = await resp.json();
            state.digimon = data.digimon || [];
            state.connected = true;
            state.error = null;
            // Phase 13-②: sync animation targets for smooth movement
            if (window.ANIM) {
                ANIM.manager.syncPositions(state.digimon);
                ANIM.manager.prune(state.digimon.map(function (d) { return d.name; }));
            }
        } catch (err) {
            if (err.name === 'AbortError') return;  // 被新请求主动取消, 不算失败
            console.warn('[api] /api/digimon 不可达:', err.message);
            state.connected = false;
            state.error = err.message;
        } finally {
            if (digimonAbort === ctrl) digimonAbort = null;
        }
    }

    // ══════════════════════════════════════════════
    //  交互: 点击选中数码兽
    // ══════════════════════════════════════════════

    /** Phase 15: 屏幕坐标 → 世界坐标 */
    function screenToWorld(sx, sy) {
        return {
            x: (sx - VIEW_W / 2) / zoom + cameraX,
            y: (sy - VIEW_H / 2) / zoom + cameraY,
        };
    }

    /** 判断世界坐标点是否在视口内 */
    function isInViewport(wx, wy, margin) {
        const halfW = VIEW_W / zoom / 2;
        const halfH = VIEW_H / zoom / 2;
        const m = margin || 0;
        return wx >= cameraX - halfW - m && wx <= cameraX + halfW + m &&
               wy >= cameraY - halfH - m && wy <= cameraY + halfH + m;
    }

    canvas.addEventListener('click', (ev) => {
        const rect = canvas.getBoundingClientRect();
        const mx = (ev.clientX - rect.left) * (VIEW_W / rect.width);
        const my = (ev.clientY - rect.top) * (VIEW_H / rect.height);

        // 检查是否点击了小地图 → 忽略
        if (isClickOnMinimap(mx, my)) return;

        const world = screenToWorld(mx, my);

        for (const d of state.digimon) {
            // Phase 13-②: use interpolated position for click hit-test
            const animSt = window.ANIM ? ANIM.manager.get(d.name) : null;
            const dx = world.x - (animSt ? animSt.renderX() : d.position.x);
            const dy = world.y - (animSt ? animSt.renderY() : d.position.y);
            const hitRadius = 22 / zoom; // 缩放感知的碰撞半径
            if (dx * dx + dy * dy < hitRadius * hitRadius) {
                state.selectedName = d.name;
                state.keyboardFocusIndex = state.digimon.indexOf(d);  // 同步键盘焦点
                showSidebar(d);
                // Phase 13-②: 戳一下涟漪粒子 + 音效
                const px = animSt ? animSt.renderX() : d.position.x;
                const py = animSt ? animSt.renderY() : d.position.y;
                if (particles) particles.poke(px, py);
                if (window.SFX) window.SFX.play('notify');
                render();
                return;
            }
        }
        // 点空白取消选中
        state.selectedName = null;
        state.keyboardFocusIndex = -1;
        hideSidebar();
        render();
    });

    // Phase 11: hover 支持 — 密度模式下鼠标悬停显示详情
    canvas.addEventListener('mousemove', (ev) => {
        const rect = canvas.getBoundingClientRect();
        const mx = (ev.clientX - rect.left) * (VIEW_W / rect.width);
        const my = (ev.clientY - rect.top) * (VIEW_H / rect.height);

        const world = screenToWorld(mx, my);

        const prevHovered = hoveredDigimon;
        hoveredDigimon = null;

        for (const d of state.digimon) {
            // Phase 15: use interpolated pos for hover
            const animSt = window.ANIM ? ANIM.manager.get(d.name) : null;
            const dx = world.x - (animSt ? animSt.renderX() : d.position.x);
            const dy = world.y - (animSt ? animSt.renderY() : d.position.y);
            const hoverRadius = 18 / zoom;
            if (dx * dx + dy * dy < hoverRadius * hoverRadius) {
                hoveredDigimon = d.name;
                break;
            }
        }

        if (hoveredDigimon !== prevHovered) {
            render();
        }
    });

    // Phase 12: 移动端触控支持 — touchstart 等效 click
    canvas.addEventListener('touchstart', (ev) => {
        if (ev.touches.length !== 1) return;  // 忽略多点触控
        ev.preventDefault();  // 防止双击缩放/滚动
        const rect = canvas.getBoundingClientRect();
        const mx = (ev.touches[0].clientX - rect.left) * (VIEW_W / rect.width);
        const my = (ev.touches[0].clientY - rect.top) * (VIEW_H / rect.height);

        if (isClickOnMinimap(mx, my)) return;

        const world = screenToWorld(mx, my);

        for (const d of state.digimon) {
            const dx = world.x - d.position.x;
            const dy = world.y - d.position.y;
            const hitRadius = 28 / zoom;  // 触控用更大的碰撞半径
            if (dx * dx + dy * dy < hitRadius * hitRadius) {
                state.selectedName = d.name;
                state.keyboardFocusIndex = state.digimon.indexOf(d);  // 同步键盘焦点
                showSidebar(d);
                render();
                return;
            }
        }
        state.selectedName = null;
        state.keyboardFocusIndex = -1;
        hideSidebar();
        render();
    }, { passive: false });

    // ══════════════════════════════════════════════
    //  键盘导航: 方向键选数码兽, Enter 打开侧栏, Esc 取消
    // ══════════════════════════════════════════════

    document.addEventListener('keydown', (ev) => {
        // 在输入框/按钮等聚焦时不拦截
        const tag = document.activeElement ? document.activeElement.tagName : '';
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || tag === 'BUTTON') return;

        const n = state.digimon.length;
        if (n === 0) return;

        if (ev.key === 'ArrowRight' || ev.key === 'ArrowDown' || (ev.key === 'Tab' && !ev.shiftKey)) {
            ev.preventDefault();
            state.keyboardFocusIndex = state.keyboardFocusIndex < 0 ? 0
                : (state.keyboardFocusIndex + 1) % n;
            state.selectedName = null;  // 仅焦点,不选中
            hideSidebar();
            render();
        } else if (ev.key === 'ArrowLeft' || ev.key === 'ArrowUp' || (ev.key === 'Tab' && ev.shiftKey)) {
            ev.preventDefault();
            state.keyboardFocusIndex = state.keyboardFocusIndex < 0 ? n - 1
                : (state.keyboardFocusIndex - 1 + n) % n;
            state.selectedName = null;
            hideSidebar();
            render();
        } else if (ev.key === 'Enter' || ev.key === ' ') {
            ev.preventDefault();
            if (state.keyboardFocusIndex >= 0 && state.keyboardFocusIndex < n) {
                const d = state.digimon[state.keyboardFocusIndex];
                state.selectedName = d.name;
                showSidebar(d);
                render();
            }
        } else if (ev.key === 'Escape') {
            state.selectedName = null;
            state.keyboardFocusIndex = -1;
            hideSidebar();
            render();
        }
    });

    // ══════════════════════════════════════════════
    //  侧栏
    // ══════════════════════════════════════════════

    /** 中文阶段名 */
    const STAGE_LABEL = {
        baby_i: '幼年期 I',
        baby_ii: '幼年期 II',
        rookie: '成长期',
        champion: '成熟期',
        ultimate: '完全体',
        mega: '究极体',
    };

    /**
     * 点击数码兽 → 先用轻量数据渲染骨架, 再拉完整详情补全。
     * 完整数据: GET /api/digimon/{name} (stage/HP/记忆/胜利数) + /api/relationships (关系)。
     */
    function showSidebar(d) {
        const sb = document.getElementById('sidebar');
        if (!sb) return;
        const emoji = getDigimonEmoji(d.name, d.species, d.stage);

        // 先渲染骨架 (轻量数据即时可见, 详情加载中)
        sb.innerHTML = `
            <h3>${emoji} ${escapeHtml(d.name)}</h3>
            <p class="meta">${escapeHtml(d.species || '')} · ${escapeHtml(STAGE_LABEL[d.stage] || d.stage || '')} · ${escapeHtml(d.attribute || '')}</p>
            <p class="meta">区域: ${escapeHtml(d.region_id || '未知')}</p>
            <p class="plan">📍 ${escapeHtml(d.current_plan || '暂无计划')}</p>
            <button class="poke tts-speak-btn" data-name="${escapeHtml(d.name)}" title="让数码兽说话">🔊 让我说话</button>
            <p class="dir-hint" id="detail-loading">加载详情中…</p>
        `;
        sb.classList.add('open');

        // 异步补全完整详情 (只在仍选中同一只时写回, 防止快速切换错位)
        loadSidebarDetail(d.name);
    }

    async function loadSidebarDetail(name) {
        let detail = null;
        let pairs = [];
        let achievements = [];
        let relationData = null;
        let personalityData = null;
        let memoryHealthData = null;
        let plansData = null;
        try {
            const [dResp, rResp, aResp, relResp, pResp, mhResp, plResp] = await Promise.all([
                fetch(API_BASE + '/api/digimon/' + encodeURIComponent(name), { cache: 'no-store' }),
                fetch(API_BASE + '/api/relationships', { cache: 'no-store' }),
                fetch(API_BASE + '/api/digimon/' + encodeURIComponent(name) + '/achievements', { cache: 'no-store' }),
                fetch(API_BASE + '/api/relations/' + encodeURIComponent(name), { cache: 'no-store' }),
                fetch(API_BASE + '/api/digimon/' + encodeURIComponent(name) + '/personality', { cache: 'no-store' }),
                fetch(API_BASE + '/api/digimon/' + encodeURIComponent(name) + '/memory-health', { cache: 'no-store' }),
                fetch(API_BASE + '/api/digimon/' + encodeURIComponent(name) + '/plans', { cache: 'no-store' }),
            ]);
            if (dResp.ok) detail = await dResp.json();
            if (rResp.ok) pairs = (await rResp.json()).pairs || [];
            if (aResp.ok) achievements = (await aResp.json()).achievements || [];
            if (relResp.ok) relationData = await relResp.json();
            if (pResp.ok) personalityData = await pResp.json();
            if (mhResp.ok) memoryHealthData = await mhResp.json();
            if (plResp.ok) plansData = await plResp.json();
        } catch (e) {
            console.warn('[sidebar] 详情加载失败:', e.message);
        }

        // 期间用户可能已切换选中 → 丢弃过期结果
        if (state.selectedName !== name) return;
        const loading = document.getElementById('detail-loading');
        if (loading) loading.remove();
        const sb = document.getElementById('sidebar');
        if (!sb || !detail) return;

        // HP 条
        const stats = detail.stats || {};
        const hp = stats.hp != null ? stats.hp : 0;
        const maxHp = stats.max_hp || 100;
        const hpPct = Math.max(0, Math.min(100, Math.round((hp / maxHp) * 100)));

        // 关系: 挑出与本兽相关的对, 按 |score| 降序
        const rels = pairs
            .filter((p) => p.a === name || p.b === name)
            .map((p) => ({ other: p.a === name ? p.b : p.a, score: p.score }))
            .sort((a, b) => Math.abs(b.score) - Math.abs(a.score));

        // 最近记忆: 最多 5 条 (最新在前), importance >= 7 高亮
        const mems = (detail.memory || []).slice(-5).reverse();

        // 成就图标映射
        const ACHIEVEMENT_ICONS = {
            first_dialogue: '💬',
            social_butterfly: '🦋',
            first_battle: '⚔️',
            '10_battles': '🏆',
            '50_battles': '👑',
            first_evolution: '🦖',
            '100ticks': '🕐',
            '500ticks': '⏳',
            explorer: '🗺️',
            breeder: '🥚',
        };

        const achievementsHtml = achievements.length === 0
            ? '<p class="dir-hint">暂无成就</p>'
            : '<div class="achieve-list">' + achievements.map((a) => {
                const icon = ACHIEVEMENT_ICONS[a.milestone] || '✨';
                return `<span class="achieve-badge" title="${escapeHtml(a.reason || '')}">${icon}</span>`;
            }).join('') + '</div>';

        const detailHtml = `
            <div class="hp-row">
                <span class="hp-label">HP</span>
                <span class="hp-bar"><span class="hp-fill" style="width:${hpPct}%"></span></span>
                <span class="hp-num">${hp}/${maxHp}</span>
            </div>
            <p class="meta">🏆 战斗胜利: ${detail.battle_victories || 0}</p>
            <div class="detail-block">
                <h4>🏅 成就 <span class="achieve-count">${achievements.length}/10</span></h4>
                ${achievementsHtml}
            </div>
            <div class="detail-block">
                <h4>关系</h4>
                ${rels.length === 0
                    ? '<p class="dir-hint">暂无关系</p>'
                    : '<ul class="rel-list">' + rels.map((r) => {
                        const cls = r.score > 0 ? 'rel-pos' : (r.score < 0 ? 'rel-neg' : 'rel-neutral');
                        const sign = r.score > 0 ? '+' : '';
                        return `<li><span class="rel-other">${escapeHtml(r.other)}</span>` +
                            `<span class="rel-score ${cls}">${sign}${r.score}</span></li>`;
                    }).join('') + '</ul>'}
            </div>
            <div class="detail-block">
                <h4>最近记忆</h4>
                ${mems.length === 0
                    ? '<p class="dir-hint">暂无记忆</p>'
                    : '<ul class="mem-list">' + mems.map((m) => {
                        const hot = (m.importance || 0) >= 7;
                        return `<li class="${hot ? 'mem-hot' : ''}">` +
                            `<span class="mem-imp">${m.importance || 0}</span>` +
                            `${escapeHtml(m.description || '')}</li>`;
                    }).join('') + '</ul>'}
            </div>
        `;
        sb.insertAdjacentHTML('beforeend', detailHtml);

        // Phase 16: 差序格局同心圆可视化
        if (relationData && relationData.circles) {
            sb.insertAdjacentHTML('beforeend',
                '<div class="detail-block">' +
                '<h4>🎯 关系圈层</h4>' +
                '<canvas class="relation-circle-canvas" width="300" height="300"></canvas>' +
                '</div>');
            const relCanvas = sb.querySelector('.relation-circle-canvas');
            if (relCanvas) drawRelationCircles(relCanvas, relationData);
        }

        // Phase 17: MBTI 人格雷达图
        if (personalityData) {
            sb.insertAdjacentHTML('beforeend',
                '<div class="detail-block">' +
                '<h4>🧠 MBTI 人格 · ' + escapeHtml(personalityData.type_code || '??') + '</h4>' +
                '<p class="meta">' + escapeHtml(personalityData.type_description || '') + '</p>' +
                '<canvas class="personality-radar-canvas" width="260" height="260"></canvas>' +
                '</div>');
            const prCanvas = sb.querySelector('.personality-radar-canvas');
            if (prCanvas) drawPersonalityRadar(prCanvas, personalityData);
        }

        // Phase 18: 记忆健康面板
        if (memoryHealthData && memoryHealthData.status !== 'not_initialized') {
            const total = memoryHealthData.total_memories || 0;
            const strong = memoryHealthData.strong_count || 0;
            const weak = memoryHealthData.weak_count || 0;
            const stale = memoryHealthData.stale_count || 0;
            const hlH = memoryHealthData.forgetting_half_life_hours || 0;
            const topWeak = memoryHealthData.top_weak || [];
            const rehearsal = memoryHealthData.rehearsal_history || [];

            sb.insertAdjacentHTML('beforeend',
                '<div class="detail-block">' +
                '<h4>🧠 记忆健康</h4>' +
                '<div class="memory-health-stats">' +
                '<span class="mh-stat mh-total">总计: ' + total + '</span>' +
                '<span class="mh-stat mh-strong">强: ' + strong + '</span>' +
                '<span class="mh-stat mh-weak">弱: ' + weak + '</span>' +
                '<span class="mh-stat mh-stale">过期: ' + stale + '</span>' +
                '<span class="mh-stat mh-halflife">半衰: ' + hlH.toFixed(1) + 'h</span>' +
                '</div>' +
                '<canvas class="memory-health-canvas" width="300" height="180"></canvas>' +
                '</div>');

            const mhCanvas = sb.querySelector('.memory-health-canvas');
            if (mhCanvas) drawMemoryHealth(mhCanvas, memoryHealthData);

            // 弱记忆列表
            if (topWeak.length > 0) {
                sb.insertAdjacentHTML('beforeend',
                    '<div class="detail-block">' +
                    '<h4>⚠️ 弱记忆 Top ' + Math.min(topWeak.length, 5) + '</h4>' +
                    '<ul class="mem-list">' + topWeak.slice(0, 5).map((m) => {
                        return '<li><span class="mem-imp weak">' + (m.strength != null ? m.strength.toFixed(2) : '?') + '</span>' +
                            escapeHtml(m.description || '').substring(0, 50) + '</li>';
                    }).join('') + '</ul>' +
                    '</div>');
            }

            // 复述历史
            if (rehearsal.length > 0) {
                sb.insertAdjacentHTML('beforeend',
                    '<div class="detail-block">' +
                    '<h4>🔄 复述历史</h4>' +
                    '<ul class="mem-list">' + rehearsal.slice(0, 3).map((r) => {
                        const desc = (r.description || '').substring(0, 40);
                        return '<li><span class="mem-imp">' + r.rehearsal_count + '×</span>' +
                            escapeHtml(desc) + '</li>';
                    }).join('') + '</ul>' +
                    '</div>');
            }
        }

        // ══════════════════════════════════════════════
        //  Phase 19: 计划持久化状态面板
        // ══════════════════════════════════════════════
        if (plansData) {
            const active = plansData.active_plan;
            const history = plansData.history || [];
            const STATUS_ICONS = { ACTIVE: '▶️', PAUSED: '⏸️', COMPLETED: '✅', ABANDONED: '❌', SUPERSEDED: '🔄' };
            const STATUS_LABELS = { ACTIVE: '进行中', PAUSED: '暂停', COMPLETED: '完成', ABANDONED: '放弃', SUPERSEDED: '替代' };

            const activeHtml = active
                ? '<div class="plan-active">' +
                  '<span class="plan-status-badge">' + (STATUS_ICONS[active.status] || '📍') + ' 当前计划</span>' +
                  '<p class="plan-text">' + escapeHtml(active.plan_text) + '</p>' +
                  '<div class="plan-meta">' +
                  '<span class="plan-imp">重要性: ' + (active.importance || '?') + '/10</span>' +
                  '<span class="plan-age">创建于 ' + (active.tick_created || '?') + ' tick</span>' +
                  (active.progress_note ? '<span class="plan-progress">进展: ' + escapeHtml(active.progress_note.substring(0, 60)) + '</span>' : '') +
                  '</div>' +
                  '</div>'
                : '<p class="dir-hint">暂无进行中的计划</p>';

            const historyItems = history.slice(0, 5).map((p) => {
                const icon = STATUS_ICONS[p.status] || '📋';
                const label = STATUS_LABELS[p.status] || p.status;
                return '<li class="plan-history-item">' +
                    '<span class="plan-h-icon">' + icon + '</span>' +
                    '<span class="plan-h-text">' + escapeHtml(p.plan_text.substring(0, 50)) + '</span>' +
                    '<span class="plan-h-status">' + label + '</span>' +
                    '</li>';
            }).join('');

            sb.insertAdjacentHTML('beforeend',
                '<div class="detail-block">' +
                '<h4>📋 计划记录 <span class="plan-count">' + (plansData.total_plans || 0) + '条</span></h4>' +
                activeHtml +
                (historyItems
                    ? '<h5 style="margin-top:10px;color:var(--text-secondary);font-size:12px;">📜 历史计划</h5>' +
                      '<ul class="plan-history-list">' + historyItems + '</ul>'
                    : '') +
                '</div>');
        }
    }

    function hideSidebar() {
        const sb = document.getElementById('sidebar');
        if (sb) sb.classList.remove('open');
    }

    // ══════════════════════════════════════════════
    //  Phase 18: 记忆健康 Ebbinghaus 遗忘曲线
    // ══════════════════════════════════════════════

    /**
     * 在 Canvas 上绘制 Ebbinghaus 遗忘曲线可视化。
     * 包含: 记忆强度分布条形图 + 遗忘曲线预测。
     */
    function drawMemoryHealth(canvas, data) {
        const c = canvas.getContext('2d');
        const w = canvas.width;   // 300
        const h = canvas.height;  // 180
        const pad = { top: 12, right: 16, bottom: 28, left: 40 };
        const pw = w - pad.left - pad.right;
        const ph = h - pad.top - pad.bottom;

        // 暗色背景
        c.fillStyle = 'rgba(10, 14, 39, 0.6)';
        c.fillRect(0, 0, w, h);

        const total = data.total_memories || 1;
        const strong = data.strong_count || 0;
        const weak = data.weak_count || 0;
        const stale = data.stale_count || 0;
        const hlSec = data.forgetting_half_life_seconds || data.forgetting_half_life_hours * 3600 || 3600;

        // ── 左侧: 堆叠条形图 (strong/weak/stale) ──
        const barX = pad.left;
        const barW = pw * 0.35;
        const barH = ph * 0.5;
        const barY = pad.top + ph * 0.15;

        // 分段
        const segs = [
            { count: strong, label: '强', color: '#00d4aa' },
            { count: weak, label: '弱', color: '#ffb347' },
            { count: stale, label: '过期', color: '#ff6b6b' },
        ];

        let segX = barX;
        for (const seg of segs) {
            const segW = total > 0 ? (seg.count / total) * barW : 0;
            if (segW > 1) {
                const grad = c.createLinearGradient(segX, barY, segX + segW, barY);
                grad.addColorStop(0, seg.color);
                grad.addColorStop(1, seg.color + '88');
                c.fillStyle = grad;
                c.fillRect(segX, barY, segW, barH);

                // 标签
                if (segW > 20) {
                    c.fillStyle = '#fff';
                    c.font = '9px "SF Mono", Consolas, monospace';
                    c.textAlign = 'center';
                    c.fillText(seg.count, segX + segW / 2, barY + barH / 2 + 3);
                }
            }
            segX += segW;
        }

        // 条形图标签
        c.fillStyle = '#888';
        c.font = '9px "SF Mono", Consolas, monospace';
        c.textAlign = 'center';
        c.fillText('记忆强度分布', barX + barW / 2, barY - 8);

        // ── 右侧: Ebbinghaus 遗忘曲线 R(t)=e^(-t/S) ──
        const curveX = pad.left + pw * 0.48;
        const curveW = pw * 0.52;
        const curveH = ph;
        const curveY = pad.top;

        // Y轴 (保留率 0-100%)
        c.strokeStyle = '#444';
        c.lineWidth = 0.5;
        for (let pct = 0; pct <= 100; pct += 20) {
            const y = curveY + curveH - (pct / 100) * curveH;
            c.beginPath();
            c.moveTo(curveX, y);
            c.lineTo(curveX + curveW, y);
            c.stroke();

            c.fillStyle = '#666';
            c.font = '8px "SF Mono", Consolas, monospace';
            c.textAlign = 'right';
            c.fillText(pct + '%', curveX - 5, y + 3);
        }

        // X轴 (时间, 0 → 2×半衰期)
        c.strokeStyle = '#444';
        c.beginPath();
        c.moveTo(curveX, curveY + curveH);
        c.lineTo(curveX + curveW, curveY + curveH);
        c.stroke();

        const maxT = hlSec * 2;  // 显示到 2× 半衰期
        const tSteps = 5;
        for (let i = 0; i <= tSteps; i++) {
            const t = (maxT / tSteps) * i;
            const x = curveX + (i / tSteps) * curveW;
            const label = t < 3600 ? (t / 60).toFixed(0) + 'min' : (t / 3600).toFixed(1) + 'h';

            c.fillStyle = '#666';
            c.font = '8px "SF Mono", Consolas, monospace';
            c.textAlign = 'center';
            c.fillText(label, x, curveY + curveH + 14);
        }

        // 绘制遗忘曲线
        c.strokeStyle = '#ff6b6b';
        c.lineWidth = 2;
        c.shadowColor = '#ff6b6b';
        c.shadowBlur = 6;
        c.beginPath();
        let firstPoint = true;
        const resolution = 80;
        for (let i = 0; i <= resolution; i++) {
            const t = (maxT / resolution) * i;
            const retention = Math.max(0, Math.exp(-t / hlSec));
            const x = curveX + (t / maxT) * curveW;
            const y = curveY + curveH - retention * curveH;

            if (firstPoint) {
                c.moveTo(x, y);
                firstPoint = false;
            } else {
                c.lineTo(x, y);
            }
        }
        c.stroke();
        c.shadowBlur = 0;

        // 半衰期标记线
        const hlRetention = Math.exp(-hlSec / hlSec);  // = 1/e ≈ 0.368
        const hlX = curveX + 0.5 * curveW;
        const hlY = curveY + curveH - hlRetention * curveH;
        c.strokeStyle = '#ffb347';
        c.lineWidth = 1;
        c.setLineDash([3, 3]);
        c.beginPath();
        c.moveTo(curveX, hlY);
        c.lineTo(curveX + curveW, hlY);
        c.stroke();
        c.setLineDash([]);

        // 半衰期标签
        c.fillStyle = '#ffb347';
        c.font = 'bold 9px "SF Mono", Consolas, monospace';
        c.textAlign = 'left';
        const hlLabel = hlSec < 3600 ? (hlSec / 60).toFixed(0) + 'min 半衰期' : (hlSec / 3600).toFixed(1) + 'h 半衰期';
        c.fillText(hlLabel, curveX + 3, hlY - 4);

        // 曲线标签
        c.fillStyle = '#ff6b6b';
        c.font = '9px "SF Mono", Consolas, monospace';
        c.textAlign = 'right';
        c.fillText('R(t)=e^(-t/S)', curveX + curveW, curveY + 12);

        // 图例色块
        const legendY = barY + barH + 16;
        const legendItems = [
            { color: '#00d4aa', label: '强(S>' + (data.strong_threshold || 0.5).toFixed(1) + ')' },
            { color: '#ffb347', label: '弱(S<' + (data.weak_threshold || 0.3).toFixed(1) + ')' },
            { color: '#ff6b6b', label: '过期(stale)' },
        ];
        let lx = barX;
        for (const item of legendItems) {
            c.fillStyle = item.color;
            c.fillRect(lx, legendY, 8, 8);
            c.fillStyle = '#888';
            c.font = '8px "SF Mono", Consolas, monospace';
            c.textAlign = 'left';
            c.fillText(item.label, lx + 11, legendY + 8);
            lx += c.measureText(item.label).width + 22;
        }
    }

    // ══════════════════════════════════════════════
    //  Phase 16: 差序格局同心圆可视化
    // ══════════════════════════════════════════════

    /**
     * 在 Canvas 上绘制 5 层同心圆差序格局图。
     * 从内到外: 亲密(intimate) → 亲近(close) → 熟人(acquaintance) → 外人(outsider) → 陌生人(stranger)。
     * 暖色(内圈) → 冷色(外圈)。
     */
    function drawRelationCircles(canvas, data) {
        const c = canvas.getContext('2d');
        const w = canvas.width;   // 300
        const h = canvas.height;  // 300
        const cx = w / 2;
        const cy = h / 2;

        // 暗色背景
        c.fillStyle = 'rgba(10, 14, 39, 0.6)';
        c.fillRect(0, 0, w, h);

        const layers = [
            { key: 'intimate',  label: '亲密',   radius: 30,  color: '#ff6b6b', dotColor: '#ff4444', alpha: 1.0 },
            { key: 'close',     label: '亲近',   radius: 58,  color: '#ffb347', dotColor: '#ff9500', alpha: 0.9 },
            { key: 'acquaintance', label: '熟人', radius: 86,  color: '#74b9ff', dotColor: '#4da6ff', alpha: 0.8 },
            { key: 'outsider',  label: '外人',   radius: 114, color: '#6c5ce7', dotColor: '#7c6cff', alpha: 0.65 },
            { key: 'stranger',  label: '陌生人',  radius: 142, color: '#636e72', dotColor: '#888888', alpha: 0.5 },
        ];

        // 绘制圆环 (从外到内画填充, 再从内到外画描边)
        for (let i = layers.length - 1; i >= 0; i--) {
            const layer = layers[i];
            const prevR = i > 0 ? layers[i - 1].radius : 10;  // 最内圈: 中心小圆

            // 圈层填充 (从上一圈边缘到本圈边缘)
            c.fillStyle = layer.color.replace(')', `, ${layer.alpha * 0.08})`).replace('rgb', 'rgba');
            if (layer.color.startsWith('#')) {
                const hex = layer.color;
                const r = parseInt(hex.slice(1, 3), 16);
                const g = parseInt(hex.slice(3, 5), 16);
                const b = parseInt(hex.slice(5, 7), 16);
                c.fillStyle = `rgba(${r}, ${g}, ${b}, ${(layer.alpha * 0.08).toFixed(2)})`;
            }
            c.beginPath();
            c.arc(cx, cy, layer.radius, 0, Math.PI * 2);
            c.arc(cx, cy, prevR, 0, Math.PI * 2, true);
            c.fill();

            // 圈层边界线
            c.strokeStyle = layer.color.replace(')', `, ${layer.alpha * 0.55})`).replace('rgb', 'rgba');
            if (layer.color.startsWith('#')) {
                const hex = layer.color;
                const r = parseInt(hex.slice(1, 3), 16);
                const g = parseInt(hex.slice(3, 5), 16);
                const b = parseInt(hex.slice(5, 7), 16);
                c.strokeStyle = `rgba(${r}, ${g}, ${b}, ${(layer.alpha * 0.55).toFixed(2)})`;
            }
            c.lineWidth = 1;
            c.beginPath();
            c.arc(cx, cy, layer.radius, 0, Math.PI * 2);
            c.stroke();
        }

        // 圈层标签 (右边缘标注)
        for (const layer of layers) {
            const labelAngle = 0.15;  // 标签角度位置
            const lx = cx + Math.cos(labelAngle) * layer.radius;
            const ly = cy + Math.sin(labelAngle) * layer.radius;
            c.fillStyle = layer.color;
            c.globalAlpha = 0.85;
            c.font = '9px monospace';
            c.textAlign = 'left';
            c.textBaseline = 'middle';
            c.fillText(layer.label, lx + 5, ly);
            c.globalAlpha = 1.0;
        }

        // 中心: 当前数码兽名字 + emoji
        const centerEmoji = getDigimonEmoji(data.name, '', '');
        // 中心圆背景
        const centerGrad = c.createRadialGradient(cx, cy, 2, cx, cy, 14);
        centerGrad.addColorStop(0, 'rgba(255, 215, 0, 0.25)');
        centerGrad.addColorStop(1, 'rgba(255, 215, 0, 0)');
        c.fillStyle = centerGrad;
        c.beginPath();
        c.arc(cx, cy, 14, 0, Math.PI * 2);
        c.fill();

        // 中心 emoji
        c.font = '16px serif';
        c.textAlign = 'center';
        c.textBaseline = 'middle';
        c.fillStyle = '#ffd700';
        c.fillText(centerEmoji, cx, cy - 8);

        // 中心名字 (截断过长的名字)
        const centerName = data.name.length > 4 ? data.name.slice(0, 4) : data.name;
        c.font = 'bold 10px monospace';
        c.fillStyle = '#ffd700';
        c.fillText(centerName, cx, cy + 10);

        // 散布各圈层的数码兽
        for (const layer of layers) {
            const members = data.circles[layer.key] || [];
            if (members.length === 0) continue;

            const innerR = layer.key === 'intimate' ? 14 : (layers[layers.indexOf(layer) - 1].radius + 3);
            const outerR = layer.radius - 4;
            const midR = (innerR + outerR) / 2;

            for (let i = 0; i < members.length && i < 12; i++) {
                // 使用 golden angle (137.5°) 让分布更均匀
                const angle = (i * 2.3999633 + layer.key.charCodeAt(0) * 0.5) % (Math.PI * 2);
                // 交错半径
                const r = (i % 3 === 0) ? innerR + 4 : (i % 3 === 1) ? midR : outerR - 2;
                const x = cx + Math.cos(angle) * r;
                const y = cy + Math.sin(angle) * r;

                // 圆点
                const dotR = layer.key === 'intimate' ? 4 : (layer.key === 'close' ? 3 : 2.5);
                c.fillStyle = layer.dotColor;
                c.globalAlpha = layer.alpha;
                c.beginPath();
                c.arc(x, y, dotR, 0, Math.PI * 2);
                c.fill();

                // 名字 (只在不拥挤时显示)
                if (members.length <= 8) {
                    c.fillStyle = layer.color;
                    c.globalAlpha = layer.alpha * 0.9;
                    c.font = '7px monospace';
                    c.textAlign = 'center';
                    c.textBaseline = 'bottom';
                    const shortName = members[i].name.length > 3 ? members[i].name.slice(0, 3) : members[i].name;
                    c.fillText(shortName, x, y - dotR - 1);
                }
            }

            // 圈子底部显示数量
            if (members.length > 8) {
                c.fillStyle = layer.color;
                c.globalAlpha = layer.alpha * 0.7;
                c.font = '7px monospace';
                c.textAlign = 'center';
                c.textBaseline = 'middle';
                const countX = cx + Math.cos(3.5) * (innerR + outerR) / 2;
                const countY = cy + Math.sin(3.5) * (innerR + outerR) / 2;
                c.fillText(`×${members.length}`, countX, countY);
            }
        }

    c.globalAlpha = 1.0;
    c.textBaseline = 'alphabetic';
    c.textAlign = 'left';
}

// ══════════════════════════════════════════════
//  Phase 17: MBTI 四维度人格雷达图
// ══════════════════════════════════════════════

        /**
         * 在 Canvas 上绘制 MBTI 四维度雷达图 + 演化轨迹。
         * 4 条轴 (45° 偏移钻石形): 右上=E/I, 左上=S/N, 左下=T/F, 右下=J/P。
         * 中心=0, 轴两端=±1, 多边形连接四点显示人格轮廓。
         */
        function drawPersonalityRadar(canvas, data) {
            const c = canvas.getContext('2d');
            const w = canvas.width;   // 260
            const h = canvas.height;  // 260
            const cx = w / 2;
            const cy = h / 2;

            c.clearRect(0, 0, w, h);

            // 暗色背景
            c.fillStyle = 'rgba(10, 14, 39, 0.55)';
            c.beginPath();
            c.roundRect(4, 4, w - 8, h - 8, 8);
            c.fill();

            // 四轴定义: 角度、正极标签、负极标签、维度 key
            const maxR = 105;  // 最大半径
            const axes = [
                { angle: -Math.PI / 4,  dim: 'ei', pos: 'E', neg: 'I', color: '#ff6b6b' },  // 右上
                { angle: -Math.PI * 3 / 4, dim: 'sn', pos: 'S', neg: 'N', color: '#ffb347' }, // 左上
                { angle: Math.PI * 3 / 4, dim: 'tf', pos: 'T', neg: 'F', color: '#74b9ff' },  // 左下
                { angle: Math.PI / 4,  dim: 'jp', pos: 'J', neg: 'P', color: '#6c5ce7' },     // 右下
            ];

            // 绘制参考圆环 (0.33, 0.66, 1.0)
            for (const ring of [1, 0.66, 0.33]) {
                const r = maxR * ring;
                c.strokeStyle = 'rgba(139, 149, 199, 0.18)';
                c.lineWidth = 0.5;
                c.beginPath();
                c.arc(cx, cy, r, 0, Math.PI * 2);
                c.stroke();
            }

            // 绘制轴线 + 正负极标签
            for (const ax of axes) {
                const ex = cx + Math.cos(ax.angle) * maxR;
                const ey = cy + Math.sin(ax.angle) * maxR;
                const exn = cx - Math.cos(ax.angle) * maxR;
                const eyn = cy - Math.sin(ax.angle) * maxR;

                // 轴线
                c.strokeStyle = 'rgba(139, 149, 199, 0.3)';
                c.lineWidth = 0.8;
                c.beginPath();
                c.moveTo(exn, eyn);
                c.lineTo(ex, ey);
                c.stroke();

                // 正极标签 (外侧)
                c.fillStyle = ax.color;
                c.font = 'bold 12px monospace';
                c.textAlign = 'center';
                c.textBaseline = 'middle';
                const lblX = cx + Math.cos(ax.angle) * (maxR + 16);
                const lblY = cy + Math.sin(ax.angle) * (maxR + 16);
                c.fillText(ax.pos, lblX, lblY);

                // 负极标签
                c.fillStyle = 'rgba(139, 149, 199, 0.6)';
                c.font = '11px monospace';
                const lblXn = cx - Math.cos(ax.angle) * (maxR + 16);
                const lblYn = cy - Math.sin(ax.angle) * (maxR + 16);
                c.fillText(ax.neg, lblXn, lblYn);
            }

            // 人格多边形: 取四维度值, 映射到坐标
            const points = axes.map((ax) => {
                const val = data[ax.dim] || 0;  // [-1, 1]
                const r = val * maxR;
                return {
                    x: cx + Math.cos(ax.angle) * r,
                    y: cy + Math.sin(ax.angle) * r,
                    color: ax.color,
                    dim: ax.dim,
                    val: val,
                };
            });

            // 填充多边形 (半透明, 渐变)
            const grad = c.createRadialGradient(cx, cy, 0, cx, cy, maxR);
            grad.addColorStop(0, 'rgba(0, 212, 255, 0.12)');
            grad.addColorStop(1, 'rgba(0, 212, 255, 0.03)');
            c.fillStyle = grad;
            c.beginPath();
            c.moveTo(points[0].x, points[0].y);
            for (let i = 1; i < points.length; i++) {
                c.lineTo(points[i].x, points[i].y);
            }
            c.closePath();
            c.fill();

            // 多边形描边
            c.strokeStyle = 'rgba(0, 212, 255, 0.7)';
            c.lineWidth = 2;
            c.stroke();

            // 四个顶点圆点
            for (const pt of points) {
                c.fillStyle = pt.color;
                c.globalAlpha = 0.9;
                c.beginPath();
                c.arc(pt.x, pt.y, 4, 0, Math.PI * 2);
                c.fill();

                // 顶点光晕
                const glow = c.createRadialGradient(pt.x, pt.y, 1, pt.x, pt.y, 10);
                glow.addColorStop(0, pt.color.replace(')', ', 0.4)').replace('rgb', 'rgba'));
                if (pt.color.startsWith('#')) {
                    const rr = parseInt(pt.color.slice(1, 3), 16);
                    const gg = parseInt(pt.color.slice(3, 5), 16);
                    const bb = parseInt(pt.color.slice(5, 7), 16);
                    c.fillStyle = `rgba(${rr}, ${gg}, ${bb}, 0.25)`;
                } else {
                    c.fillStyle = pt.color.replace(')', ', 0.25)').replace('rgb', 'rgba');
                }
                c.beginPath();
                c.arc(pt.x, pt.y, 10, 0, Math.PI * 2);
                c.fill();
                c.globalAlpha = 1.0;
            }

            // 中心点
            c.fillStyle = '#ffd700';
            c.beginPath();
            c.arc(cx, cy, 3, 0, Math.PI * 2);
            c.fill();

            // 维度标签 (小字, 在顶点旁偏移)
            const dimLabels = { ei: 'E/I', sn: 'S/N', tf: 'T/F', jp: 'J/P' };
            for (const pt of points) {
                c.fillStyle = 'rgba(224, 230, 255, 0.55)';
                c.font = '8px monospace';
                c.textAlign = 'center';
                c.textBaseline = 'bottom';
                const offX = pt.x - cx;
                const offY = pt.y - cy;
                const dist = Math.sqrt(offX * offX + offY * offY);
                if (dist > 8) {
                    const nx = offX / dist;
                    const ny = offY / dist;
                    c.fillText(
                        (pt.val >= 0 ? '+' : '') + pt.val.toFixed(1),
                        pt.x + nx * 8,
                        pt.y + ny * 8 - 3
                    );
                }
            }

            // 底部: 类型代码 + 强度百分比
            c.fillStyle = '#ffd700';
            c.font = 'bold 13px monospace';
            c.textAlign = 'center';
            c.textBaseline = 'top';
            const typeText = (data.type_code || '??') + '  ' +
                (data.is_clear ? '✓ 清晰' : '~ 模糊');
            c.fillText(typeText, cx, maxR + 36);

            // 演化轨迹: 最近 5 条历史用圆点标出方向
            const history = data.history || [];
            if (history.length > 0) {
                c.fillStyle = 'rgba(224, 230, 255, 0.5)';
                c.font = '9px monospace';
                c.textAlign = 'center';
                c.textBaseline = 'top';
                c.fillText('演化记录 (最近 ' + Math.min(5, history.length) + ' 条)', cx, maxR + 56);

                const recent = history.slice(-5);
                const dotStart = maxR + 72;
                for (let i = 0; i < recent.length; i++) {
                    const entry = recent[i];
                    const tickX = cx - 50 + i * 26;
                    const tickY = dotStart;

                    // 小圆点
                    c.fillStyle = 'rgba(0, 212, 255, 0.7)';
                    c.beginPath();
                    c.arc(tickX, tickY + 3, 3.5, 0, Math.PI * 2);
                    c.fill();

                    // 类型代码 (如果有变化用黄色标出)
                    if (i > 0 && entry.result_type !== recent[i - 1].result_type) {
                        c.fillStyle = '#ffd700';
                    } else {
                        c.fillStyle = 'rgba(224, 230, 255, 0.6)';
                    }
                    c.font = '7px monospace';
                    c.textAlign = 'center';
                    c.textBaseline = 'top';
                    c.fillText(entry.result_type || '', tickX, tickY + 10);
                }

                // 箭头连线从左到右
                if (recent.length > 1) {
                    c.strokeStyle = 'rgba(0, 212, 255, 0.25)';
                    c.lineWidth = 1;
                    c.beginPath();
                    c.moveTo(cx - 50 + 3.5, dotStart + 3);
                    c.lineTo(cx - 50 + (recent.length - 1) * 26 + 3.5, dotStart + 3);
                    c.stroke();
                }
            }

            c.globalAlpha = 1.0;
            c.textBaseline = 'alphabetic';
            c.textAlign = 'left';
        }

    // ══════════════════════════════════════════════
    //  轮询
    // ══════════════════════════════════════════════

    function startPolling() {
        if (pollTimer) return;
        pollTimer = setInterval(async () => {
            await fetchDigimon();
            render();
            updateStatusBar();
        }, 3000);
        console.log('[poll] 每 3s 轮询 /api/digimon');
    }

    // ══════════════════════════════════════════════
    //  战斗轮询 + 进化 Overlay
    // ══════════════════════════════════════════════

    let battleCount24h = 0;

    /** 每 30 秒拉最近战斗,检测进化事件 */
    function startBattlePolling() {
        async function poll() {
            try {
                const resp = await fetch(API_BASE + '/api/battle/recent?limit=3', { cache: 'no-store' });
                if (!resp.ok) return;
                const data = await resp.json();
                battleCount24h = data.count || 0;
                updateStatusBar();

                // 检查最近 3 场里有无进化
                const battles = data.battles || [];
                for (const b of battles) {
                    if (b.evolution && b.evolution.evolved) {
                        if (window.SFX) window.SFX.play('evolution');
                        showEvolutionOverlay(
                            b.winner,
                            b.evolution.old_stage,
                            b.evolution.new_stage
                        );
                        break; // 一次只弹一条
                    }
                }
            } catch (e) {
                // 静默失败,不影响主轮询
            }
        }
        poll();
        setInterval(poll, 30000);
    }

    /** 全屏进化动画 — 多阶段: 闪白入场 → 扫描线+粒子+图标脉冲 → 4.5 秒后淡出 */
    function showEvolutionOverlay(name, oldStage, newStage) {
        // 防止重复弹出同一事件
        if (document.getElementById('evo-overlay')) return;

        const overlay = document.createElement('div');
        overlay.id = 'evo-overlay';
        overlay.className = 'evo-overlay';

        const newEmoji = getDigimonEmoji(name, null, newStage);
        const stageLabel = STAGE_LABEL[newStage] || newStage;

        // 构建内层 HTML: 进化图标 + 文字
        overlay.innerHTML = `
            <span class="evo-icon">${newEmoji}</span>
            <div class="evo-text">
                <span class="evo-name">${escapeHtml(name)}</span>
                <span class="evo-stage">${escapeHtml(oldStage)} → ${escapeHtml(stageLabel)} ⚡</span>
            </div>
        `;

        // 添加飞升粒子 (8 个金色光点, 随机水平位置 + 随机延迟)
        for (let i = 0; i < 8; i++) {
            const sparkle = document.createElement('span');
            sparkle.className = 'evo-sparkle';
            sparkle.style.left = (10 + Math.random() * 80) + '%';
            sparkle.style.setProperty('--dur', (1.8 + Math.random() * 2.2).toFixed(2) + 's');
            sparkle.style.setProperty('--delay', (Math.random() * 1.5).toFixed(2) + 's');
            overlay.appendChild(sparkle);
        }

        const wrap = document.querySelector('.canvas-wrap');
        if (wrap) {
            wrap.appendChild(overlay);
        } else {
            document.body.appendChild(overlay);
        }

        // 4.5 秒后淡出, 0.5s 过渡后移除
        setTimeout(() => {
            overlay.classList.add('fade-out');
            setTimeout(() => overlay.remove(), 500);
        }, 4500);
    }

    // ══════════════════════════════════════════════
    //  Phase 4: 导演面板
    // ══════════════════════════════════════════════
    //
    // 右侧 200px 半透明 sidebar, 仅在屏幕宽度 > 768px 时显示。
    // - 关系图: 3 只数码兽互连, 连线颜色 = 好感度 (正=绿, 负=红, 0=灰)
    // - 派系列表 + 最近事件: 每 30s 刷新
    // - 导演操作: 注入事件 / 速度控制 (1x / 5x / 60x)

    const DIRECTOR_MIN_WIDTH = 769; // 严格大于 768px 才显示

    const DIRECTOR_REFRESH_MS = 10000; // 每 10s 自动拉一次

    const director = {
        pairs: [],      // [{a, b, score}]
        factions: [],   // [{faction_id, name, members}]
        events: [],     // 最近事件 (最新在后)
        ratio: null,    // 当前时间流速
        enabled: false, // 面板是否处于显示状态
        isMobile: false,// Phase 12: 当前是否移动端布局
        relOk: true,    // GET /api/relationships 最近一次是否成功
        stateOk: true,  // GET /api/director/state 最近一次是否成功
        leaderboard: { battle: [], bond: [], badges: [] }, // 三维排行榜数据
        lbTab: 'battle', // 当前选中的排行榜 tab
        lbOk: true,     // GET /api/leaderboard 最近一次是否成功
        injectedEvents: [], // Phase 15: 导演注入事件历史
    };

    // 排行榜每个维度的显示配置: 数值字段名 + 单位后缀
    const LB_METRIC = {
        battle: { field: 'victories', suffix: '胜' },
        bond: { field: 'bond', suffix: '' },
        badges: { field: 'badges', suffix: '枚' },
    };

    /** 好感度分数 → 连线颜色 (正=绿, 负=红, 0=灰), alpha 随强度增大 */
    function scoreToColor(score) {
        const mag = Math.min(Math.abs(score) / 10, 1);   // 归一到 [0,1]
        const alpha = (0.25 + mag * 0.65).toFixed(2);
        if (score > 0) return `rgba(74, 232, 196, ${alpha})`;  // 绿 = 友好
        if (score < 0) return `rgba(255, 92, 92, ${alpha})`;   // 红 = 敌对
        return 'rgba(139, 149, 199, 0.35)';                    // 灰 = 中立
    }

    /** 画关系图: 数码兽绕圆环排布, 两两连线, 颜色 = 好感度 */
    function drawRelationshipGraph() {
        const c = document.getElementById('relationship-graph');
        if (!c) return;
        const g = c.getContext('2d');
        const w = c.width;
        const h = c.height;
        g.clearRect(0, 0, w, h);

        // 参与者 = 当前世界里的数码兽名字 (兜底用关系对里出现的名字)
        let names = state.digimon.map((d) => d.name);
        if (names.length === 0) {
            const set = new Set();
            for (const p of director.pairs) { set.add(p.a); set.add(p.b); }
            names = [...set];
        }

        const hint = document.getElementById('rel-hint');
        if (names.length === 0) {
            if (hint) hint.textContent = '暂无数码兽';
            return;
        }

        // 圆环坐标
        const cx = w / 2;
        const cy = h / 2;
        const radius = Math.min(w, h) / 2 - 30;
        const pos = {};
        names.forEach((name, i) => {
            const ang = -Math.PI / 2 + (i / names.length) * Math.PI * 2;
            pos[name] = { x: cx + Math.cos(ang) * radius, y: cy + Math.sin(ang) * radius };
        });

        // 快速查分: "a\x00b" (排序后) → score
        const scoreOf = {};
        for (const p of director.pairs) {
            const key = [p.a, p.b].sort().join(' ');
            scoreOf[key] = p.score;
        }

        // 连线 (两两)
        for (let i = 0; i < names.length; i++) {
            for (let j = i + 1; j < names.length; j++) {
                const pa = pos[names[i]];
                const pb = pos[names[j]];
                const key = [names[i], names[j]].sort().join(' ');
                const score = scoreOf[key] || 0;
                // 线宽 = 关系强度: |score| 归一到 [0,1], 映射到 1~6px
                const mag = Math.min(Math.abs(score) / 10, 1);
                g.lineWidth = 1 + mag * 5;
                g.strokeStyle = scoreToColor(score);
                g.beginPath();
                g.moveTo(pa.x, pa.y);
                g.lineTo(pb.x, pb.y);
                g.stroke();
            }
        }
        g.lineWidth = 1;

        // 节点 + 名字
        for (const name of names) {
            const p = pos[name];
            g.fillStyle = '#00d4ff';
            g.beginPath();
            g.arc(p.x, p.y, 6, 0, Math.PI * 2);
            g.fill();

            g.fillStyle = '#e0e6ff';
            g.font = '10px monospace';
            g.textAlign = 'center';
            g.textBaseline = 'middle';
            // 名字放在节点朝外一侧
            const outX = p.x + (p.x - cx) * 0.28;
            const outY = p.y + (p.y - cy) * 0.28;
            g.fillText(name, outX, outY);
        }
        g.textBaseline = 'alphabetic';

        if (hint) {
            hint.textContent = `绿=友好 红=敌对 (${director.pairs.length} 对)`;
        }
    }

    /** 渲染派系列表 */
    function renderFactions() {
        const ul = document.getElementById('faction-list');
        if (!ul) return;
        if (director.factions.length === 0) {
            ul.innerHTML = '<li class="dir-hint">暂无派系</li>';
            return;
        }
        ul.innerHTML = director.factions.map((f) => {
            const members = (f.members || []).join('、') || '(空)';
            return `<li><span class="fac-name">${escapeHtml(f.name || f.faction_id)}</span><br>${escapeHtml(members)}</li>`;
        }).join('');
    }

    /** 渲染最近事件 (最新在前) */
    function renderDirectorEvents() {
        const ul = document.getElementById('director-events');
        if (!ul) return;
        if (director.events.length === 0) {
            ul.innerHTML = '<li class="dir-hint">暂无事件</li>';
            return;
        }
        const items = director.events.slice().reverse().slice(0, 5);
        ul.innerHTML = items.map((e) => {
            const isDirector = e.source === 'director';
            const desc = e.description || e.type || '(未知事件)';
            return `<li class="${isDirector ? 'director-src' : ''}">` +
                `<span class="evt-type">[${escapeHtml(e.type || '?')}]</span>` +
                `${escapeHtml(desc)}</li>`;
        }).join('');
    }

    /** Phase 15: 事件类型 → 图标映射 */
    const EVENT_TYPE_ICONS = {
        director_event: '📌',
        weather: '🌤️',
        disaster: '🌋',
        faction_create: '🏴',
        encounter: '👋',
        broadcast: '📢',
    };

    /** Phase 15: 拉取导演注入事件历史 */
    async function fetchInjectedEvents() {
        try {
            const resp = await fetch(API_BASE + '/api/director/injected-events?limit=10', { cache: 'no-store' });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            const data = await resp.json();
            director.injectedEvents = data.events || [];
        } catch (e) {
            console.warn('[director] /api/director/injected-events 不可达:', e.message);
            // 失败不清空旧数据
        }
    }

    /** Phase 15: 渲染事件历史列表 */
    function renderEventHistory() {
        const el = document.getElementById('event-history-list');
        if (!el) return;
        const list = director.injectedEvents;
        if (list.length === 0) {
            el.innerHTML = '<p class="dir-hint">暂无注入事件</p>';
            return;
        }
        // 截取最近10条
        const items = list.slice(0, 10);
        el.innerHTML = items.map((e) => {
            const icon = EVENT_TYPE_ICONS[e.type] || '📌';
            const desc = e.description || '(无描述)';
            // 格式化时间: ISO → HH:MM:SS
            let timeStr = '';
            if (e.at) {
                try {
                    const d = new Date(e.at);
                    timeStr = d.toLocaleTimeString('zh-CN', { hour12: false });
                } catch (_) {
                    timeStr = e.at.slice(11, 19) || e.at;
                }
            }
            return `<div class="eh-item">` +
                `<span class="eh-icon">${icon}</span>` +
                `<span class="eh-desc">${escapeHtml(desc)}</span>` +
                `<span class="eh-time">${timeStr}</span>` +
                `</div>`;
        }).join('');
    }

    /** Phase 15 Task 2: 刷新事件历史 (fetch + render) */
    async function refreshEventHistory() {
        await fetchInjectedEvents();
        renderEventHistory();
    }

    /** GET 排行榜三维数据 */
    async function fetchLeaderboard() {
        try {
            const resp = await fetch(API_BASE + '/api/leaderboard');
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            const data = await resp.json();
            director.leaderboard = {
                battle: data.battle || [],
                bond: data.bond || [],
                badges: data.badges || [],
            };
            director.lbOk = true;
        } catch (e) {
            console.warn('[director] /api/leaderboard 不可达:', e.message);
            director.lbOk = false;
        }
    }

    /** 渲染当前 tab 的排行榜 (前 3 名加奖牌) */
    function renderLeaderboard() {
        const ol = document.getElementById('leaderboard-list');
        if (!ol) return;
        const cfg = LB_METRIC[director.lbTab] || LB_METRIC.battle;
        const rows = director.leaderboard[director.lbTab] || [];
        if (rows.length === 0) {
            ol.innerHTML = '<li class="dir-hint">暂无数据</li>';
            return;
        }
        const medals = ['🥇', '🥈', '🥉'];
        ol.innerHTML = rows.map((r, i) => {
            const rank = medals[i] || `${i + 1}.`;
            const val = r[cfg.field] != null ? r[cfg.field] : 0;
            return `<li class="lb-row">` +
                `<span class="lb-rank">${rank}</span>` +
                `<span class="lb-name">${escapeHtml(r.name)}</span>` +
                `<span class="lb-val">${val}${cfg.suffix}</span></li>`;
        }).join('');
    }

    /** 简单 HTML 转义, 防止事件描述里的字符破坏 DOM */
    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    /** 高亮当前速度按钮 */
    function updateSpeedButtons() {
        const btns = document.querySelectorAll('.speed-btn');
        btns.forEach((b) => {
            const r = parseInt(b.dataset.ratio, 10);
            b.classList.toggle('active', r === director.ratio);
        });
        const st = document.getElementById('speed-status');
        if (st) st.textContent = director.ratio != null ? `当前: ${director.ratio}x` : '当前: --';
    }

    /** 拉关系对 */
    async function fetchRelationships() {
        try {
            const resp = await fetch(API_BASE + '/api/relationships', { cache: 'no-store' });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            const data = await resp.json();
            director.pairs = data.pairs || [];
            director.relOk = true;
        } catch (e) {
            console.warn('[director] /api/relationships 不可达:', e.message);
            director.relOk = false;
        }
    }

    /** 拉导演状态 (流速 / 世界时间 / 最近事件 / 派系) */
    async function fetchDirectorState() {
        try {
            const resp = await fetch(API_BASE + '/api/director/state', { cache: 'no-store' });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            const data = await resp.json();
            director.events = data.recent_events || [];
            director.factions = data.factions || [];
            if (typeof data.ratio === 'number') director.ratio = data.ratio;
            director.stateOk = true;
        } catch (e) {
            console.warn('[director] /api/director/state 不可达:', e.message);
            director.stateOk = false;
        }
    }

    /** 面板顶部连接状态: 任一接口挂掉就显示 '⚠️ 不可用' */
    function updateDirectorConn() {
        const el = document.getElementById('director-conn');
        if (!el) return;
        if (director.relOk && director.stateOk) {
            el.textContent = '🟢 数据实时';
            el.classList.remove('dir-down');
        } else {
            el.textContent = '⚠️ 不可用';
            el.classList.add('dir-down');
        }
    }

    /** 刷新整个导演面板 (数据 + 重绘)
     *  防并发: 10s 定时器与手动触发 (注入/加载) 可能重叠,
     *  上一次刷新未完成时直接跳过本次, 避免请求堆积。 */
    let directorRefreshing = false;
    async function refreshDirector() {
        if (!director.enabled || directorRefreshing) return;
        directorRefreshing = true;
        try {
            await refreshDirectorInner();
        } finally {
            directorRefreshing = false;
        }
    }
    async function refreshDirectorInner() {
        await Promise.all([fetchRelationships(), fetchDirectorState(), fetchLeaderboard(), fetchInjectedEvents()]);
        drawRelationshipGraph();
        renderFactions();
        renderDirectorEvents();
        renderLeaderboard();
        renderEventHistory();
        updateSpeedButtons();
        updateDirectorConn();
    }

    /** POST 设置速度 */
    async function setSpeed(ratio) {
        try {
            const resp = await fetch(API_BASE + '/api/director/speed', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ratio }),
            });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            const data = await resp.json();
            director.ratio = data.new_ratio;
            updateSpeedButtons();
        } catch (e) {
            console.warn('[director] 设置速度失败:', e.message);
            const st = document.getElementById('speed-status');
            if (st) st.textContent = '⚠️ 不可用';
        }
    }

    /** Type → region_id 映射: 通用事件=global, 其余=file_island */
    function getRegionId(type) {
        return type === 'director_event' ? 'global' : 'file_island';
    }

    // ══════════════════════════════════════════════
    //  Phase 15 Task 3: 注入结果高亮 + Toast 通知
    // ══════════════════════════════════════════════

    /** 高亮集合: name → 过期时间戳 (performance.now() + durationMs) */
    const highlightDigimons = new Map();

    /** 将数码兽名字加入高亮集合, durationMs 毫秒后自动移除 */
    function addDigimonHighlights(names, durationMs) {
        var expires = (typeof performance !== 'undefined' ? performance.now() : Date.now()) + durationMs;
        names.forEach(function (name) {
            highlightDigimons.set(name, expires);
        });
    }

    /** 清理过期的高亮条目 (在 drawDigimon 前调用) */
    function pruneHighlights(now) {
        highlightDigimons.forEach(function (expires, name) {
            if (now >= expires) highlightDigimons.delete(name);
        });
    }

    /** Task 3: 注入事件后的顶部 toast 通知 (显示受影响数码兽名字) */
    function showInjectToast(names) {
        var toast = document.createElement('div');
        toast.className = 'inject-toast';
        toast.textContent = '事件影响：' + names.join('、');
        toast.style.cssText =
            'position:fixed;top:16px;left:50%;transform:translateX(-50%);z-index:10000;' +
            'padding:10px 24px;border-radius:8px;background:rgba(255,215,0,0.92);color:#1a1a2e;' +
            'font:13px monospace;font-weight:bold;box-shadow:0 4px 20px rgba(255,215,0,0.4);' +
            'transition:opacity 400ms ease;pointer-events:none;';
        document.body.appendChild(toast);
        requestAnimationFrame(function () { toast.style.opacity = '1'; });
        setTimeout(function () {
            toast.style.opacity = '0';
            setTimeout(function () { toast.remove(); }, 400);
        }, 3000);
    }

    /** Task 3: 注入事件后的 impact_summary 通知 (复用 showNotification 系统) */
    function showInjectNotification(summary, count) {
        showNotification({
            type: 'director_event',
            description: '📌 已影响 ' + count + ' 只数码兽 — ' + summary,
            at: new Date().toISOString(),
        });
    }

    /** POST 注入事件. type 从下拉框读, description 从输入框读 */
    async function injectEvent(type, description) {
        const status = document.getElementById('inject-status');
        const btn = document.getElementById('inject-btn');
        if (btn) btn.disabled = true;
        try {
            const resp = await fetch(API_BASE + '/api/director/inject_event', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    type: type || 'director_event',
                    region_id: getRegionId(type),
                    description,
                    importance: 5,
                }),
            });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            const data = await resp.json();
            // Task 3: 提取受影响的数码兽名字 & impact_summary
            const affected = data.affected_agents || [];
            const affectedNames = Array.isArray(affected)
                ? affected.map(function (a) { return typeof a === 'string' ? a : (a.name || ''); }).filter(Boolean)
                : [];
            const impactSummary = data.impact_summary || '';
            if (status) {
                const n = affectedNames.length;
                status.textContent = n > 0 ? '✅ 已注入 (影响 ' + n + ' 只数码兽)' : '✅ 已注入';
            }
            const input = document.getElementById('inject-input');
            if (input) input.value = '';
            // Task 3: 高亮受影响的数码兽 (3s 金色光环)
            if (affectedNames.length > 0) {
                addDigimonHighlights(affectedNames, 3000);
                showInjectToast(affectedNames);
            }
            // Task 3: 弹出 impact_summary 通知
            if (impactSummary) {
                showInjectNotification(impactSummary, affectedNames.length);
            }
            await refreshEventHistory(); // 立刻反映到事件历史列表
        } catch (e) {
            if (status) status.textContent = '⚠️ 不可用: ' + e.message;
        } finally {
            if (btn) btn.disabled = false;
            setTimeout(function () { if (status) status.textContent = ''; }, 3000);
        }
    }

    /** POST 保存 / 加载世界状态 */
    async function saveWorld() {
        await worldPersist('/api/save', '💾 已保存');
    }
    async function loadWorld() {
        await worldPersist('/api/load', '📂 已加载');
        // 加载后世界可能整个换了 — 立刻拉一次数码兽 + 导演数据
        await fetchDigimon();
        render();
        await refreshDirector();
    }
    async function worldPersist(path, okText) {
        const status = document.getElementById('save-status');
        const saveBtn = document.getElementById('save-btn');
        const loadBtn = document.getElementById('load-btn');
        if (saveBtn) saveBtn.disabled = true;
        if (loadBtn) loadBtn.disabled = true;
        try {
            const resp = await fetch(API_BASE + path, { method: 'POST' });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            const data = await resp.json();
            if (status) {
                const n = typeof data.digimon_count === 'number' ? ` (${data.digimon_count})` : '';
                status.textContent = okText + n;
            }
        } catch (e) {
            if (status) status.textContent = '⚠️ 不可用: ' + e.message;
        } finally {
            if (saveBtn) saveBtn.disabled = false;
            if (loadBtn) loadBtn.disabled = false;
            setTimeout(() => { if (status) status.textContent = ''; }, 3000);
        }
    }

    /** 根据屏幕宽度决定是否显示导演面板 */
    function updateDirectorVisibility() {
        const panel = document.getElementById('director-panel');
        if (!panel) return;
        const isMobile = window.innerWidth < DIRECTOR_MIN_WIDTH;
        if (isMobile === director.isMobile) return;  // 无变化
        director.isMobile = isMobile;

        if (isMobile) {
            // 移动端: 面板变为底部抽屉, 加浮动按钮切换
            panel.classList.remove('open');
            ensureDirectorToggleBtn();
        } else {
            // 桌面端: 恢复固定右侧面板
            panel.classList.add('open');
            removeDirectorToggleBtn();
            refreshDirector();
        }
    }

    /** 移动端创建/获取导演面板浮动按钮 */
    function ensureDirectorToggleBtn() {
        if (document.getElementById('director-toggle-btn')) return;
        const btn = document.createElement('button');
        btn.id = 'director-toggle-btn';
        btn.className = 'director-toggle-btn';
        btn.textContent = '🎬';
        btn.title = '导演面板';
        btn.addEventListener('click', () => {
            const panel = document.getElementById('director-panel');
            if (!panel) return;
            const isOpen = panel.classList.contains('open');
            if (isOpen) {
                panel.classList.remove('open');
                btn.textContent = '🎬';
            } else {
                panel.classList.add('open');
                btn.textContent = '✕';
                refreshDirector();
            }
        });
        document.body.appendChild(btn);
        // 移动端显示浮动按钮
        btn.style.display = 'flex';
        btn.style.alignItems = 'center';
        btn.style.justifyContent = 'center';
    }

    function removeDirectorToggleBtn() {
        const btn = document.getElementById('director-toggle-btn');
        if (btn) btn.remove();
    }

    /** 绑定导演面板交互 + 启动 30s 刷新 */
    function initDirector() {
        // 速度按钮
        document.querySelectorAll('.speed-btn').forEach((b) => {
            b.addEventListener('click', () => setSpeed(parseInt(b.dataset.ratio, 10)));
        });
        // 注入事件: 下拉选 type + 输入框填描述
        const btn = document.getElementById('inject-btn');
        const input = document.getElementById('inject-input');
        const typeSel = document.getElementById('inject-type');
        const submit = () => {
            const desc = (input && input.value || '').trim();
            const type = (typeSel && typeSel.value) || 'director_event';
            if (desc) injectEvent(type, desc);
        };
        if (btn) btn.addEventListener('click', submit);
        if (input) {
            input.addEventListener('keydown', (ev) => {
                if (ev.key === 'Enter') submit();
            });
        }
        // Phase 15 Task 4: 选择不同事件类型时，动态切换 input placeholder
        if (typeSel && input) {
            var typePlaceholders = {
                'evolution_event': '描述进化触发条件…',
                'festival': '描述节日内容和影响…',
                'battle_event': '描述战斗双方和场景…',
                'director_event': '事件描述…',
                'weather': '描述天气变化…',
                'disaster': '描述灾害详情…',
                'faction_create': '描述新派系名称…',
                'encounter': '描述遭遇详情…',
            };
            typeSel.addEventListener('change', function () {
                input.placeholder = typePlaceholders[typeSel.value] || '事件描述…';
            });
        }
        // 保存 / 加载
        const saveBtn = document.getElementById('save-btn');
        const loadBtn = document.getElementById('load-btn');
        if (saveBtn) saveBtn.addEventListener('click', saveWorld);
        if (loadBtn) loadBtn.addEventListener('click', loadWorld);
        // 排行榜 tab 切换 (纯本地重绘, 不重新请求)
        document.querySelectorAll('.lb-tab').forEach((t) => {
            t.addEventListener('click', () => {
                director.lbTab = t.dataset.lb || 'battle';
                document.querySelectorAll('.lb-tab').forEach((b) => {
                    b.classList.toggle('active', b === t);
                });
                renderLeaderboard();
            });
        });
        // 屏宽变化 → 显隐
        window.addEventListener('resize', updateDirectorVisibility);
        updateDirectorVisibility();
        // 每 10s 自动刷新 (关系 + 导演状态)
        setInterval(refreshDirector, DIRECTOR_REFRESH_MS);
    }

    // ══════════════════════════════════════════════
    //  世界事件广播 (左下角系统消息)
    // ══════════════════════════════════════════════
    // 独立于导演面板: 面板仅宽屏显示且 10s 刷新, 通知则始终运行、
    // 每 3s 轮询 /api/director/state 的 recent_events, 只对战斗 / 进化 /
    // 剧情类事件弹出提示, 3 秒后自动渐隐消失。

    const NOTIFY_STYLE = {
        battle:         { icon: '⚔️', label: '战斗', color: '#ff6b6b' },
        battle_victory: { icon: '🏆', label: '战斗', color: '#ffd93d' },
        evolution:      { icon: '✨', label: '进化', color: '#4ae8c4' },
        story_event:    { icon: '📖', label: '剧情', color: '#b68aff' },
        director_event: { icon: '🎬', label: '导演事件', color: '#ffd700' },
        evolution_event: { icon: '✨', label: '进化事件', color: '#4ae8c4' },
        festival:       { icon: '🎉', label: '节日', color: '#ff9ff3' },
        battle_event:   { icon: '⚔️', label: '战斗', color: '#ff6b6b' },
    };
    const NOTIFY_POLL_MS = 3000;   // 轮询间隔
    const NOTIFY_TTL_MS = 3000;    // 每条通知停留时长
    const NOTIFY_FADE_MS = 500;    // 渐隐动画时长 (与 CSS transition 对应)

    const notify = {
        seen: new Set(),   // 已展示过的事件签名, 防重复弹
        seeded: false,     // 首次拉取只做基线, 不把历史事件一次性全弹出来
        stack: null,       // DOM 容器 (懒创建)
    };

    /** 事件签名: recent_events 没有稳定 id, 用 type+描述+时间+event_id 组合去重 */
    function eventKey(e) {
        return [e.type || '', e.description || '', e.at || '', e.event_id || ''].join('|');
    }

    /** 懒创建左下角通知容器 + 注入样式 (保持全部逻辑在 main.js 内) */
    function ensureNotifyStack() {
        if (notify.stack) return notify.stack;
        if (!document.getElementById('notify-style')) {
            const st = document.createElement('style');
            st.id = 'notify-style';
            st.textContent = `
#notify-stack {
    position: fixed; left: 16px; bottom: 16px; z-index: 9999;
    display: flex; flex-direction: column-reverse; gap: 8px;
    max-width: 320px; pointer-events: none;
}
.notify-card {
    display: flex; align-items: flex-start; gap: 8px;
    padding: 10px 12px; border-radius: 8px;
    background: rgba(12, 18, 40, 0.92);
    border-left: 3px solid #888;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.45);
    color: #e8edf7; font: 12px/1.4 monospace;
    opacity: 0; transform: translateX(-24px);
    transition: opacity ${NOTIFY_FADE_MS}ms ease, transform ${NOTIFY_FADE_MS}ms ease;
}
.notify-card.show { opacity: 1; transform: translateX(0); }
.notify-card.hide { opacity: 0; transform: translateX(-24px); }
.notify-icon { font-size: 16px; line-height: 1.2; flex: 0 0 auto; }
.notify-body { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.notify-label { font-weight: bold; font-size: 11px; letter-spacing: 1px; }
.notify-desc { color: #c7d2e8; word-break: break-word; }
`;
            document.head.appendChild(st);
        }
        const el = document.createElement('div');
        el.id = 'notify-stack';
        document.body.appendChild(el);
        notify.stack = el;
        return el;
    }

    /** 弹出一条系统消息, 3s 后渐隐移除 */
    function showNotification(e) {
        const cfg = NOTIFY_STYLE[e.type];
        if (!cfg) return;
        // 音效: 战斗类 → battle, 进化 → evolution, 其余 → notify
        if (window.SFX) {
            if (e.type === 'battle' || e.type === 'battle_victory') {
                window.SFX.play('battle');
            } else if (e.type === 'evolution') {
                window.SFX.play('evolution');
            } else {
                window.SFX.play('notify');
            }
        }
        // Phase 13-②: 粒子特效 — 进化金光 / 战斗火花
        if (particles && state.digimon.length > 0) {
            // 从事件描述中提取数码兽名字并定位
            const desc = e.description || '';
            for (const d of state.digimon) {
                if (desc.includes(d.name)) {
                    const animSt = window.ANIM ? ANIM.manager.get(d.name) : null;
                    const px = animSt ? animSt.renderX() : d.position.x;
                    const py = animSt ? animSt.renderY() : d.position.y;
                    if (e.type === 'evolution') {
                        particles.evolution(px, py);
                    } else if (e.type === 'battle' || e.type === 'battle_victory') {
                        particles.battle(px, py);
                    }
                }
            }
            // 如果没匹配到名字, 在视口中心世界坐标放一个
            if (particles.alive === 0) {
                if (e.type === 'evolution') particles.evolution(cameraX, cameraY);
                else if (e.type === 'battle' || e.type === 'battle_victory') particles.battle(cameraX, cameraY);
            }
        }
        const stack = ensureNotifyStack();
        const desc = e.description || (cfg.label + '事件');
        const card = document.createElement('div');
        card.className = 'notify-card';
        card.style.borderLeftColor = cfg.color;
        card.innerHTML =
            `<span class="notify-icon">${cfg.icon}</span>` +
            `<div class="notify-body">` +
            `<span class="notify-label" style="color:${cfg.color}">${cfg.label}</span>` +
            `<span class="notify-desc">${escapeHtml(desc)}</span></div>`;
        stack.appendChild(card);
        // 下一帧加 show, 触发进场过渡
        requestAnimationFrame(() => card.classList.add('show'));
        // 停留 → 渐隐 → 移除
        setTimeout(() => {
            card.classList.remove('show');
            card.classList.add('hide');
            setTimeout(() => card.remove(), NOTIFY_FADE_MS);
        }, NOTIFY_TTL_MS);
    }

    /** 轮询世界事件, 只对新出现的战斗/进化/剧情事件弹通知 */
    async function pollNotifications() {
        try {
            const resp = await fetch(API_BASE + '/api/director/state', { cache: 'no-store' });
            if (!resp.ok) return;
            const data = await resp.json();
            const events = data.recent_events || [];
            // 首次只记录基线, 避免刷新页面时把历史事件全弹出来
            if (!notify.seeded) {
                events.forEach((e) => notify.seen.add(eventKey(e)));
                notify.seeded = true;
                return;
            }
            for (const e of events) {
                const key = eventKey(e);
                if (notify.seen.has(key)) continue;
                notify.seen.add(key);
                showNotification(e);   // 非关注类型会被 showNotification 内部忽略
            }
            // seen 只需覆盖最近窗口, 防止无限增长
            if (notify.seen.size > 200) {
                notify.seen = new Set(events.map(eventKey));
            }
        } catch (err) {
            // 通知非关键功能, 后端不可达时静默
        }
    }

    /** 启动通知轮询 */
    function startNotifications() {
        pollNotifications();   // 立即拉一次做基线
        setInterval(pollNotifications, NOTIFY_POLL_MS);
        console.log('[notify] 世界事件广播已启动, 每 ' + (NOTIFY_POLL_MS / 1000) + 's 轮询');
    }

    const VITALITY_POLL_MS = 5000;  // Phase 7: 活力指标 5s 轮询
    const ENV_POLL_MS = 8000;      // Phase 10: 环境数据 8s 轮询

    async function pollVitality() {
        try {
            const resp = await fetchWithTimeout(API_BASE + '/api/world/vitality', { cache: 'no-store' });
            if (resp.ok) {
                const data = await resp.json();
                state.vitality = data.overall_vitality;
                updateStatusBar();
            }
        } catch (err) {
            // 静默 — 活力不是关键功能
        }
    }

    /** Phase 10: 拉取环境综合数据 (昼夜+天气+生态+季节) */
    async function fetchEnvironment() {
        try {
            const resp = await fetchWithTimeout(API_BASE + '/api/environment', { cache: 'no-store' });
            if (!resp.ok) return;
            const data = await resp.json();
            const prevIsDaytime = state.env.daynight.is_daytime;
            if (data.daynight) state.env.daynight = data.daynight;
            if (data.weather) state.env.weather = data.weather;
            if (data.ecology) state.env.ecology = data.ecology;
            if (data.season) state.env.season = data.season;
            // Phase 15: 昼夜切换 → 触发重渲染即可 (天空每帧重绘)
            if (state.env.daynight.is_daytime !== prevIsDaytime) { /* no-op, sky redrawn each frame */ }
        } catch (e) {
            // 静默失败
        }
    }

    // ══════════════════════════════════════════════
    //  启动
    // ══════════════════════════════════════════════

    async function start() {
        console.log('[start] API_BASE =', API_BASE || '(同源)');

        // 1. 拉地图
        await fetchWorld();
        // 2. 拉数码兽
        await fetchDigimon();
        // Phase 13-②: initialize animation positions (instant, no tween on first load)
        if (window.ANIM) {
            for (const d of state.digimon) {
                const st = ANIM.manager.get(d.name);
                st.setTarget(d.position.x, d.position.y);
            }
        }
        // 3. 首次渲染
        render();
        updateStatusBar();
        // 4. 启动轮询
        startPolling();
        // 5. 状态栏每秒刷新时间
        setInterval(updateStatusBar, 1000);
        // 6. 启动战斗轮询 (30s) — 进化 overlay + 战斗数
        startBattlePolling();
        // 7. 初始化导演面板 (仅宽屏显示, 30s 刷新)
        initDirector();
        // 8. 启动世界事件广播 (左下角系统消息, 始终运行)
        startNotifications();
        // 9. Phase 7: 世界活力指标 5s 轮询
        pollVitality();
        setInterval(pollVitality, VITALITY_POLL_MS);
        // 10. Phase 10: 环境数据 8s 轮询
        fetchEnvironment();
        setInterval(fetchEnvironment, ENV_POLL_MS);
        // 11. Phase 10: 天气粒子动画循环 (每 100ms 重新绘制粒子)
        setInterval(render, 100);
        // 12. Phase 13: TTS 语音按钮 (事件委托, sidebar 内动态渲染)
        setupTTSSpeakButton();
        // 13. Phase 14: 世界叙事轮询 (30s)
        fetchNarrative();
        setInterval(fetchNarrative, 30000);
        // 14. Phase 15: 面板折叠按钮
        initPanelToggles();
    }

    /** Phase 13: 绑定 sidebar 内的 TTS 按钮点击事件 (事件委托) */
    function setupTTSSpeakButton() {
        const sb = document.getElementById('sidebar');
        if (!sb) return;
        sb.addEventListener('click', (ev) => {
            const btn = ev.target.closest('.tts-speak-btn');
            if (!btn) return;
            const name = btn.dataset.name;
            if (name && window.TTS) {
                btn.textContent = '🔊 说话中…';
                btn.disabled = true;
                window.TTS.speak(name).finally(() => {
                    btn.textContent = '🔊 让我说话';
                    btn.disabled = false;
                });
            }
        });
    }

    /** Phase 14: 拉取最新世界叙事并更新面板 */
    async function fetchNarrative() {
        try {
            const resp = await fetchWithTimeout(API_BASE + '/api/narratives/latest', {}, 8000);
            if (!resp.ok) return;
            const data = await resp.json();
            const titleEl = document.querySelector('.narrative-title');
            const storyEl = document.querySelector('.narrative-story');
            const metaEl = document.querySelector('.narrative-meta');
            if (titleEl) titleEl.textContent = data.title || '世界叙事';
            if (storyEl) storyEl.textContent = data.story || '';
            if (metaEl) {
                const parts = [];
                if (data.tick) parts.push(`tick ${data.tick}`);
                if (data.evolution_count) parts.push(`${data.evolution_count}次进化`);
                if (data.battle_count) parts.push(`${data.battle_count}场战斗`);
                metaEl.textContent = parts.join(' · ') || '';
            }
        } catch (e) {
            // 叙事未生成时静默忽略
        }
    }

    start();

    // 暴露调试接口
    window.DigimonWorld = {
        version: '1.0.0',
        phase: 15,
        getState: () => state,
        refresh: async () => { await fetchDigimon(); render(); },
        getCamera: () => ({ cameraX, cameraY, zoom }),
        goTo: (wx, wy) => { cameraX = wx; cameraY = wy; render(); },
    };
})();
