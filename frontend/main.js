/**
 * DIGIMON WORLD - 前端 Phase 1
 *
 * 1. 加载后端 /api/world 快照,获取数码兽位置
 * 2. 渲染地图(沿用 Phase 0 画法,加 POI 标签)
 * 3. 脚本驱动亚古兽在文件岛随机走动
 * 4. 每 2 秒从后端 GET /api/digimon 重新拉位置(模拟 WebSocket 简单轮询)
 * 5. 鼠标点击数码兽 → 弹出侧栏
 *
 * Phase 1 完成标志: 真实亚古兽在文件岛移动 ✓
 * Phase 2+: 改成 WebSocket 推送 + LLM 决策路径
 */

(function () {
    'use strict';

    console.log('🐉 Digimon World Phase 1 initializing...');
    console.log('   Frontend talks to FastAPI backend (Phase 1)');

    const canvas = document.getElementById('world-map');
    const ctx = canvas.getContext('2d');
    const W = canvas.width;
    const H = canvas.height;

    const API_BASE = window.location.origin.includes('workers.dev')
        ? ''                          // 同源 (Cloudflare Pages + Workers 反代场景)
        : 'http://127.0.0.1:8000';    // 本地开发时连后端 8000

    // ---- 状态 ----
    const state = {
        digimon: [],          // [{name, position, ...}]
        regions: [],          // [{id, name, bounds, pois}]
        selectedName: null,
        lastFetch: 0,
        connected: false,
    };

    // ---- 画地图 ----
    function drawSky() {
        const skyGrad = ctx.createLinearGradient(0, 0, 0, H);
        skyGrad.addColorStop(0, '#0a1233');
        skyGrad.addColorStop(0.6, '#1e2a5a');
        skyGrad.addColorStop(1, '#3a1a4a');
        ctx.fillStyle = skyGrad;
        ctx.fillRect(0, 0, W, H);
    }

    function drawMountains() {
        ctx.fillStyle = '#1a1f3a';
        ctx.beginPath();
        ctx.moveTo(0, H * 0.7);
        for (let x = 0; x <= W; x += 40) {
            const y = H * 0.6 + Math.sin(x * 0.015) * 30 + Math.sin(x * 0.03) * 15;
            ctx.lineTo(x, y);
        }
        ctx.lineTo(W, H);
        ctx.lineTo(0, H);
        ctx.closePath();
        ctx.fill();
    }

    function drawInfinityMountain() {
        ctx.fillStyle = '#2a1f4a';
        ctx.beginPath();
        ctx.moveTo(W * 0.35, H * 0.55);
        ctx.lineTo(W * 0.5, H * 0.2);
        ctx.lineTo(W * 0.65, H * 0.55);
        ctx.closePath();
        ctx.fill();
        const peakGrad = ctx.createRadialGradient(W * 0.5, H * 0.2, 5, W * 0.5, H * 0.2, 80);
        peakGrad.addColorStop(0, 'rgba(124, 58, 237, 0.6)');
        peakGrad.addColorStop(1, 'rgba(124, 58, 237, 0)');
        ctx.fillStyle = peakGrad;
        ctx.fillRect(0, 0, W, H);
    }

    function drawIslands() {
        ctx.fillStyle = '#0e3a3a';
        ctx.beginPath();
        ctx.ellipse(W * 0.78, H * 0.78, 100, 50, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#3a3a1a';
        ctx.beginPath();
        ctx.ellipse(W * 0.18, H * 0.78, 70, 35, 0, 0, Math.PI * 2);
        ctx.fill();
    }

    function drawDataFragments() {
        for (let i = 0; i < 30; i++) {
            const x = (i * 73 + 50) % W;
            const y = ((i * 41) % (H * 0.6)) + 20;
            ctx.fillStyle = `rgba(0, 212, 255, ${0.2 + (i % 5) * 0.1})`;
            ctx.fillRect(x, y, 2, 2);
        }
    }

    function drawPOIs() {
        if (!state.regions) return;
        for (const region of state.regions) {
            for (const [pid, poi] of Object.entries(region.pois || {})) {
                // POI 来自后端:{x, y, label}
                const x = poi.x;
                const y = poi.y;
                // 旗子
                ctx.fillStyle = 'rgba(255, 215, 0, 0.85)';
                ctx.beginPath();
                ctx.moveTo(x, y);
                ctx.lineTo(x, y - 14);
                ctx.lineTo(x + 8, y - 11);
                ctx.lineTo(x, y - 8);
                ctx.closePath();
                ctx.fill();
                // 标签
                ctx.fillStyle = 'rgba(255, 215, 0, 0.9)';
                ctx.font = '11px monospace';
                ctx.textAlign = 'left';
                ctx.fillText(poi.label, x + 10, y - 6);
            }
        }
    }

    function drawDigimon() {
        for (const d of state.digimon) {
            const x = d.position.x;
            const y = d.position.y;
            const isSelected = d.name === state.selectedName;

            // 光晕
            const aura = ctx.createRadialGradient(x, y, 3, x, y, 22);
            aura.addColorStop(0, isSelected ? 'rgba(255, 215, 0, 0.9)' : 'rgba(0, 212, 255, 0.7)');
            aura.addColorStop(1, 'rgba(0, 212, 255, 0)');
            ctx.fillStyle = aura;
            ctx.beginPath();
            ctx.arc(x, y, 22, 0, Math.PI * 2);
            ctx.fill();

            // 数码兽身体(简单圆形)
            ctx.fillStyle = isSelected ? '#ffd700' : '#00d4ff';
            ctx.beginPath();
            ctx.arc(x, y, 9, 0, Math.PI * 2);
            ctx.fill();

            // 眼睛
            ctx.fillStyle = '#0a0e27';
            ctx.beginPath();
            ctx.arc(x - 3, y - 2, 1.5, 0, Math.PI * 2);
            ctx.arc(x + 3, y - 2, 1.5, 0, Math.PI * 2);
            ctx.fill();

            // 名字标签
            ctx.fillStyle = '#fff';
            ctx.font = '12px monospace';
            ctx.textAlign = 'center';
            ctx.fillText(d.name, x, y - 14);
        }
    }

    function drawTitle() {
        ctx.fillStyle = 'rgba(255, 255, 255, 0.5)';
        ctx.font = '14px monospace';
        ctx.textAlign = 'center';
        ctx.fillText('— DIGITAL WORLD · FILE ISLAND —', W / 2, H - 16);
    }

    function render() {
        drawSky();
        drawMountains();
        drawInfinityMountain();
        drawIslands();
        drawDataFragments();
        drawPOIs();
        drawDigimon();
        drawTitle();
    }

    // ---- 状态栏 ----
    function updateStatusBar() {
        document.getElementById('world-time').textContent =
            '世界时间: ' + new Date().toLocaleTimeString('zh-CN');
        document.getElementById('digimon-count').textContent =
            '数码兽: ' + state.digimon.length;
        document.getElementById('phase').textContent =
            'Phase: 1 (地图+移动) · ' + (state.connected ? '🟢 后端已连' : '🔴 离线');
    }

    // ---- API 通信 ----
    async function fetchSnapshot() {
        try {
            const r = await fetch(API_BASE + '/api/world', { cache: 'no-store' });
            if (!r.ok) throw new Error('HTTP ' + r.status);
            const data = await r.json();
            state.regions = data.regions;
            state.digimon = data.agents.map((a) => ({
                name: a.name,
                species: a.species,
                stage: a.stage,
                attribute: a.attribute,
                region_id: a.region_id,
                position: a.location,                 // backend 用 "location":[x,y]
                current_plan: a.current_plan,
            }));
            state.connected = true;
            state.lastFetch = Date.now();
        } catch (err) {
            console.warn('[fetch] 后端不可达,使用本地模拟:', err.message);
            state.connected = false;
            // 后端挂了 → 本地假数据
            if (state.digimon.length === 0) {
                state.digimon = [
                    { name: '亚古兽(离线)', position: { x: 200, y: 400 }, species: 'agumon' },
                    { name: '加布兽(离线)', position: { x: 700, y: 350 }, species: 'gabumon' },
                ];
            }
        }
    }

    // 鼠标点击:点击数码兽选中
    canvas.addEventListener('click', (ev) => {
        const rect = canvas.getBoundingClientRect();
        const x = (ev.clientX - rect.left) * (W / rect.width);
        const y = (ev.clientY - rect.top) * (H / rect.height);
        for (const d of state.digimon) {
            const dx = x - d.position.x;
            const dy = y - d.position.y;
            if (dx * dx + dy * dy < 18 * 18) {
                state.selectedName = d.name;
                showSidebar(d);
                return;
            }
        }
        // 点空白 → 取消选中
        state.selectedName = null;
        hideSidebar();
    });

    // ---- 侧栏 ----
    function showSidebar(d) {
        const sb = document.getElementById('sidebar');
        if (!sb) return;
        sb.innerHTML = `
            <h3>${d.name}</h3>
            <p class="meta">${d.species || ''} · ${d.stage || ''} · ${d.attribute || ''}</p>
            <p class="meta">区域: ${d.region_id || '未知'}</p>
            <p class="meta">坐标: (${d.position.x}, ${d.position.y})</p>
            <p class="plan">📍 ${d.current_plan || '暂无计划'}</p>
            <button id="btn-poke" class="poke">戳一下</button>
        `;
        sb.classList.add('open');
        document.getElementById('btn-poke').addEventListener('click', () => pokeDigimon(d));
    }

    function hideSidebar() {
        const sb = document.getElementById('sidebar');
        if (sb) sb.classList.remove('open');
    }

    async function pokeDigimon(d) {
        // 朝鼠标方向戳一下 (让数码兽挪动)
        try {
            const r = await fetch(API_BASE + `/api/digimon/${encodeURIComponent(d.name)}/move`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ dx: Math.floor(Math.random() * 60) - 30, dy: Math.floor(Math.random() * 40) - 20 }),
            });
            if (r.ok) {
                const data = await r.json();
                d.position = data.position;
                render();
            }
        } catch (err) {
            console.warn('[poke] 后端不可达:', err.message);
        }
    }

    // ---- 脚本驱动: 亚古兽自动闲逛(Phase 1 demo) ----
    let wanderTimer = 0;
    async function wanderLoop() {
        wanderTimer += 1;
        // 每 3 秒尝试移动亚古兽
        if (wanderTimer % 3 === 0) {
            const dx = Math.floor(Math.random() * 41) - 20;  // [-20, 20]
            const dy = Math.floor(Math.random() * 21) - 10;  // [-10, 10]
            try {
                await fetch(API_BASE + '/api/digimon/' + encodeURIComponent('亚古兽') + '/move', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ dx, dy }),
                });
            } catch (_) { /* 后端不可达就静默 */ }
        }
    }

    // ---- 启动 ----
    async function start() {
        await fetchSnapshot();
        render();
        updateStatusBar();
        // 每 2s 拉一次后端位置
        setInterval(async () => {
            await fetchSnapshot();
            await wanderLoop();
            render();
            updateStatusBar();
        }, 2000);
        setInterval(updateStatusBar, 1000);
    }

    start();

    // 暴露 API
    window.DigimonWorld = {
        version: '0.2.0',
        phase: 1,
        ready: true,
        getState: () => state,
        poke: pokeDigimon,
    };
})();
