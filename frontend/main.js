/**
 * DIGIMON WORLD - 前端 Phase 1
 *
 * 1. 启动时 fetch GET /api/world → 画地图(regions + POIs)
 * 2. fetch GET /api/digimon → 画 3 只数码兽(emoji + 名字)
 * 3. 每 3 秒轮询 GET /api/digimon 更新位置
 * 4. 后端不可达时显示 placeholder + 提示
 * 5. API_BASE: Cloudflare 部署时通过 window.API_BASE 注入; 本地默认 http://localhost:8000
 *
 * 纯 canvas, 无第三方框架
 */

(function () {
    'use strict';

    console.log('🐉 Digimon World Phase 1 initializing...');

    const canvas = document.getElementById('world-map');
    const ctx = canvas.getContext('2d');
    const W = canvas.width;   // 960
    const H = canvas.height;  // 600

    // ---- API 配置 ----
    // 优先级: window.API_BASE (Workers 注入) > 自动检测
    const API_BASE = (() => {
        if (typeof window.API_BASE === 'string') return window.API_BASE;
        if (window.location.origin.includes('workers.dev')) return '';  // 同源反代
        return 'http://localhost:8000';
    })();

    // ---- 数码兽 emoji 映射 ----
    const SPECIES_EMOJI = {
        agumon: '🦖',
        gabumon: '🐺',
        biyomon: '🦅',
    };

    // ---- 区域样式 ----
    // 后端两个 region 的 bounds 都是整块 (0,0,960,600) 且重叠,
    // 所以标签位置在前端按语义手动指定,避免堆在左上角。
    const REGION_STYLE = {
        file_island: { label: '#4ae8c4', labelAt: { x: 24, y: 560 } },
        infinity_mountain: { label: '#b68aff', labelAt: { x: 24, y: 30 } },
    };
    const DEFAULT_STYLE = { label: '#aabbcc', labelAt: { x: 24, y: 30 } };

    // ---- 状态 ----
    const state = {
        regions: [],          // [{id, name, description, bounds, pois}]
        digimon: [],          // [{name, species, stage, attribute, region_id, position:{x,y}, current_plan}]
        selectedName: null,
        connected: false,
        error: null,          // 后端不可达时的错误信息
    };

    let pollTimer = null;

    // ══════════════════════════════════════════════
    //  绘 制
    // ══════════════════════════════════════════════

    function drawSky() {
        const grad = ctx.createLinearGradient(0, 0, 0, H);
        grad.addColorStop(0, '#0a1233');
        grad.addColorStop(0.6, '#1e2a5a');
        grad.addColorStop(1, '#3a1a4a');
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, W, H);
    }

    function drawStars() {
        // 简单伪随机星空
        for (let i = 0; i < 40; i++) {
            const x = (i * 73 + 50) % W;
            const y = ((i * 41) % (H * 0.55)) + 10;
            const alpha = 0.2 + (i % 5) * 0.12;
            ctx.fillStyle = `rgba(200, 220, 255, ${alpha})`;
            ctx.beginPath();
            ctx.arc(x, y, 1, 0, Math.PI * 2);
            ctx.fill();
        }
    }

    /** 根据后端 regions 数据画地图 */
    function drawRegions() {
        // 先画通用场景元素(两个 region bounds 相同, 都覆盖全 canvas)
        // 无限山
        ctx.fillStyle = '#2a1f4a';
        ctx.beginPath();
        ctx.moveTo(W * 0.35, H * 0.55);
        ctx.lineTo(W * 0.5, H * 0.15);
        ctx.lineTo(W * 0.65, H * 0.55);
        ctx.closePath();
        ctx.fill();

        // 山顶光晕
        const peakGrad = ctx.createRadialGradient(W * 0.5, H * 0.15, 5, W * 0.5, H * 0.15, 80);
        peakGrad.addColorStop(0, 'rgba(124, 58, 237, 0.5)');
        peakGrad.addColorStop(1, 'rgba(124, 58, 237, 0)');
        ctx.fillStyle = peakGrad;
        ctx.beginPath();
        ctx.arc(W * 0.5, H * 0.15, 80, 0, Math.PI * 2);
        ctx.fill();

        // 远山
        ctx.fillStyle = '#1a1f3a';
        ctx.beginPath();
        ctx.moveTo(0, H * 0.6);
        for (let x = 0; x <= W; x += 40) {
            const y = H * 0.55 + Math.sin(x * 0.012) * 25 + Math.sin(x * 0.025) * 12;
            ctx.lineTo(x, y);
        }
        ctx.lineTo(W, H * 0.75);
        ctx.lineTo(0, H * 0.75);
        ctx.closePath();
        ctx.fill();

        // 海面
        ctx.fillStyle = '#0a2a4a';
        ctx.fillRect(0, H * 0.75, W, H * 0.25);

        // 岛屿地面
        ctx.fillStyle = '#1a4a3a';
        ctx.beginPath();
        ctx.ellipse(W * 0.5, H * 0.78, W * 0.42, 60, 0, 0, Math.PI * 2);
        ctx.fill();

        // 沙滩
        ctx.fillStyle = '#5a4a2a';
        ctx.beginPath();
        ctx.ellipse(W * 0.2, H * 0.8, 80, 25, -0.2, 0, Math.PI * 2);
        ctx.fill();

        // 区域名称标签
        for (const region of state.regions) {
            const style = REGION_STYLE[region.id] || DEFAULT_STYLE;
            ctx.fillStyle = style.label;
            ctx.font = 'bold 13px monospace';
            ctx.textAlign = 'left';
            ctx.globalAlpha = 0.7;
            ctx.fillText(region.name, style.labelAt.x, style.labelAt.y);
            ctx.globalAlpha = 1.0;
        }
    }

    /** 画 POI 标记 */
    function drawPOIs() {
        for (const region of state.regions) {
            if (!region.pois) continue;
            for (const [, poi] of Object.entries(region.pois)) {
                const { x, y, label } = poi;

                // 标记点
                ctx.fillStyle = 'rgba(255, 215, 0, 0.85)';
                ctx.beginPath();
                ctx.arc(x, y, 4, 0, Math.PI * 2);
                ctx.fill();

                // 旗子
                ctx.strokeStyle = 'rgba(255, 215, 0, 0.7)';
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(x, y);
                ctx.lineTo(x, y - 16);
                ctx.stroke();
                ctx.fillStyle = 'rgba(255, 215, 0, 0.8)';
                ctx.beginPath();
                ctx.moveTo(x, y - 16);
                ctx.lineTo(x + 10, y - 13);
                ctx.lineTo(x, y - 10);
                ctx.closePath();
                ctx.fill();

                // 标签文字
                ctx.fillStyle = 'rgba(255, 215, 0, 0.9)';
                ctx.font = '11px monospace';
                ctx.textAlign = 'left';
                ctx.fillText(label, x + 14, y - 8);
            }
        }
    }

    /** 画数码兽 */
    function drawDigimon() {
        for (const d of state.digimon) {
            const { x, y } = d.position;
            const isSelected = d.name === state.selectedName;
            const emoji = SPECIES_EMOJI[d.species] || '❓';

            // 光晕
            const aura = ctx.createRadialGradient(x, y, 4, x, y, 24);
            aura.addColorStop(0, isSelected ? 'rgba(255, 215, 0, 0.8)' : 'rgba(0, 212, 255, 0.5)');
            aura.addColorStop(1, 'rgba(0, 0, 0, 0)');
            ctx.fillStyle = aura;
            ctx.beginPath();
            ctx.arc(x, y, 24, 0, Math.PI * 2);
            ctx.fill();

            // Emoji
            ctx.font = '24px serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(emoji, x, y);

            // 名字
            ctx.fillStyle = isSelected ? '#ffd700' : '#ffffff';
            ctx.font = '12px monospace';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'bottom';
            ctx.fillText(d.name, x, y - 18);

            // 选中时画圈
            if (isSelected) {
                ctx.strokeStyle = '#ffd700';
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.arc(x, y, 20, 0, Math.PI * 2);
                ctx.stroke();
            }
        }
        // 重置 baseline
        ctx.textBaseline = 'alphabetic';
    }

    /** 画标题 */
    function drawTitle() {
        ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
        ctx.font = '13px monospace';
        ctx.textAlign = 'center';
        ctx.fillText('— DIGITAL WORLD · FILE ISLAND —', W / 2, H - 14);
    }

    /** 后端不可达时的 placeholder */
    function drawPlaceholder() {
        drawSky();
        drawStars();

        // 大标题
        ctx.fillStyle = 'rgba(255, 255, 255, 0.7)';
        ctx.font = 'bold 28px monospace';
        ctx.textAlign = 'center';
        ctx.fillText('🐉 DIGIMON WORLD', W / 2, H / 2 - 40);

        // 提示信息
        ctx.fillStyle = 'rgba(255, 100, 100, 0.9)';
        ctx.font = '14px monospace';
        ctx.fillText('⚠ 无法连接后端', W / 2, H / 2 + 10);

        ctx.fillStyle = 'rgba(200, 200, 220, 0.7)';
        ctx.font = '12px monospace';
        ctx.fillText(`尝试连接: ${API_BASE || '(同源)'}`, W / 2, H / 2 + 40);
        ctx.fillText('请确认后端已启动: cd backend && uvicorn ...', W / 2, H / 2 + 62);
        ctx.fillText('或 python -m digimon_world.api.app', W / 2, H / 2 + 82);

        // 离线 placeholder 数码兽
        ctx.font = '36px serif';
        ctx.globalAlpha = 0.3;
        ctx.fillText('🦖   🐺   🦅', W / 2, H / 2 + 140);
        ctx.globalAlpha = 1.0;
    }

    /** 完整渲染 */
    function render() {
        if (!state.connected && state.digimon.length === 0) {
            drawPlaceholder();
            return;
        }
        drawSky();
        drawStars();
        drawRegions();
        drawPOIs();
        drawDigimon();
        drawTitle();
    }

    // ══════════════════════════════════════════════
    //  状态栏
    // ══════════════════════════════════════════════

    function updateStatusBar() {
        const timeEl = document.getElementById('world-time');
        const countEl = document.getElementById('digimon-count');
        const phaseEl = document.getElementById('phase');

        if (timeEl) timeEl.textContent = '世界时间: ' + new Date().toLocaleTimeString('zh-CN');
        if (countEl) countEl.textContent = '数码兽: ' + state.digimon.length;

        const connStatus = state.connected ? '🟢 在线' : '🔴 离线';
        if (phaseEl) phaseEl.textContent = `Phase 1 · ${connStatus}`;
    }

    // ══════════════════════════════════════════════
    //  API 通信
    // ══════════════════════════════════════════════

    /** 拉取地图数据 (regions + POIs) */
    async function fetchWorld() {
        try {
            const resp = await fetch(API_BASE + '/api/world', { cache: 'no-store' });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            const data = await resp.json();
            state.regions = data.regions || [];
            state.connected = true;
            state.error = null;
            console.log('[api] /api/world OK, regions:', state.regions.length);
        } catch (err) {
            console.warn('[api] /api/world 不可达:', err.message);
            state.error = err.message;
            // regions 不清空 — 保留上次成功拉取的
        }
    }

    /** 拉取数码兽列表 (轻量) */
    async function fetchDigimon() {
        try {
            const resp = await fetch(API_BASE + '/api/digimon', { cache: 'no-store' });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            const data = await resp.json();
            state.digimon = data.digimon || [];
            state.connected = true;
            state.error = null;
        } catch (err) {
            console.warn('[api] /api/digimon 不可达:', err.message);
            state.connected = false;
            state.error = err.message;
        }
    }

    // ══════════════════════════════════════════════
    //  交互: 点击选中数码兽
    // ══════════════════════════════════════════════

    canvas.addEventListener('click', (ev) => {
        const rect = canvas.getBoundingClientRect();
        const mx = (ev.clientX - rect.left) * (W / rect.width);
        const my = (ev.clientY - rect.top) * (H / rect.height);

        for (const d of state.digimon) {
            const dx = mx - d.position.x;
            const dy = my - d.position.y;
            if (dx * dx + dy * dy < 22 * 22) {
                state.selectedName = d.name;
                showSidebar(d);
                render();
                return;
            }
        }
        // 点空白取消选中
        state.selectedName = null;
        hideSidebar();
        render();
    });

    // ══════════════════════════════════════════════
    //  侧栏
    // ══════════════════════════════════════════════

    function showSidebar(d) {
        const sb = document.getElementById('sidebar');
        if (!sb) return;
        const emoji = SPECIES_EMOJI[d.species] || '❓';
        sb.innerHTML = `
            <h3>${emoji} ${d.name}</h3>
            <p class="meta">${d.species || ''} · ${d.stage || ''} · ${d.attribute || ''}</p>
            <p class="meta">区域: ${d.region_id || '未知'}</p>
            <p class="meta">坐标: (${d.position.x}, ${d.position.y})</p>
            <p class="plan">📍 ${d.current_plan || '暂无计划'}</p>
        `;
        sb.classList.add('open');
    }

    function hideSidebar() {
        const sb = document.getElementById('sidebar');
        if (sb) sb.classList.remove('open');
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
    //  启动
    // ══════════════════════════════════════════════

    async function start() {
        console.log('[start] API_BASE =', API_BASE || '(同源)');

        // 1. 拉地图
        await fetchWorld();
        // 2. 拉数码兽
        await fetchDigimon();
        // 3. 首次渲染
        render();
        updateStatusBar();
        // 4. 启动轮询
        startPolling();
        // 5. 状态栏每秒刷新时间
        setInterval(updateStatusBar, 1000);
    }

    start();

    // 暴露调试接口
    window.DigimonWorld = {
        version: '1.0.0',
        phase: 1,
        getState: () => state,
        refresh: async () => { await fetchDigimon(); render(); },
    };
})();
