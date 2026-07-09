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
    // 进化后 species 会变成 'champion_form' 等占位值,所以优先用中文名匹配,
    // 名字匹配不到时退回到 stage 匹配,保证进化后不会掉成 ❓。
    const NAME_EMOJI = {
        '亚古兽': '🦖',
        '加布兽': '🐺',
        '比丘兽': '🦅',
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
            const emoji = getDigimonEmoji(d.name, d.species, d.stage);

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

    /** 完整渲染 (实际绘制, 只在 rAF 回调里调用) */
    function renderNow() {
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

    // render() 可能在一帧内被多次触发 (轮询 / 点击 / 加载), 用 rAF 防抖:
    // 同一帧内的多次调用合并成一次绘制, 且绘制与浏览器刷新对齐。
    let rafPending = false;
    function render() {
        if (rafPending) return;
        rafPending = true;
        requestAnimationFrame(() => {
            rafPending = false;
            renderNow();
        });
    }

    // ══════════════════════════════════════════════
    //  状态栏
    // ══════════════════════════════════════════════

    function updateStatusBar() {
        const timeEl = document.getElementById('world-time');
        const countEl = document.getElementById('digimon-count');
        const battleEl = document.getElementById('battle-count');
        const phaseEl = document.getElementById('phase');

        if (timeEl) timeEl.textContent = '世界时间: ' + new Date().toLocaleTimeString('zh-CN');
        if (countEl) countEl.textContent = '数码兽: ' + state.digimon.length;
        if (battleEl) battleEl.textContent = '战斗: ' + battleCount24h;

        const connStatus = state.connected ? '🟢 在线' : '🔴 离线';
        if (phaseEl) phaseEl.textContent = `Phase 3 · ${connStatus}`;
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

    /** 拉取数码兽列表 (轻量)
     *  用 AbortController 防并发: 上一次请求还没回来就发下一次时,
     *  先取消旧请求, 避免慢响应堆积 / 旧数据覆盖新数据。 */
    let digimonAbort = null;
    async function fetchDigimon() {
        if (digimonAbort) digimonAbort.abort();
        const ctrl = new AbortController();
        digimonAbort = ctrl;
        try {
            const resp = await fetch(API_BASE + '/api/digimon', { cache: 'no-store', signal: ctrl.signal });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            const data = await resp.json();
            state.digimon = data.digimon || [];
            state.connected = true;
            state.error = null;
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
            <p class="dir-hint" id="detail-loading">加载详情中…</p>
        `;
        sb.classList.add('open');

        // 异步补全完整详情 (只在仍选中同一只时写回, 防止快速切换错位)
        loadSidebarDetail(d.name);
    }

    async function loadSidebarDetail(name) {
        let detail = null;
        let pairs = [];
        try {
            const [dResp, rResp] = await Promise.all([
                fetch(API_BASE + '/api/digimon/' + encodeURIComponent(name), { cache: 'no-store' }),
                fetch(API_BASE + '/api/relationships', { cache: 'no-store' }),
            ]);
            if (dResp.ok) detail = await dResp.json();
            if (rResp.ok) pairs = (await rResp.json()).pairs || [];
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

        const detailHtml = `
            <div class="hp-row">
                <span class="hp-label">HP</span>
                <span class="hp-bar"><span class="hp-fill" style="width:${hpPct}%"></span></span>
                <span class="hp-num">${hp}/${maxHp}</span>
            </div>
            <p class="meta">🏆 战斗胜利: ${detail.battle_victories || 0}</p>
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

    /** 全屏半透明 overlay: 进化通知,3 秒后消失 */
    function showEvolutionOverlay(name, oldStage, newStage) {
        // 防止重复弹出同一事件
        if (document.getElementById('evo-overlay')) return;

        const overlay = document.createElement('div');
        overlay.id = 'evo-overlay';
        overlay.className = 'evo-overlay';
        const newEmoji = getDigimonEmoji(name, null, newStage);
        overlay.textContent = `⚡ ${name} 进化了! ${oldStage} → ${newStage} ${newEmoji} ⚡`;

        const wrap = document.querySelector('.canvas-wrap');
        if (wrap) {
            wrap.appendChild(overlay);
        } else {
            document.body.appendChild(overlay);
        }

        setTimeout(() => {
            overlay.classList.add('fade-out');
            setTimeout(() => overlay.remove(), 400);
        }, 3000);
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
        relOk: true,    // GET /api/relationships 最近一次是否成功
        stateOk: true,  // GET /api/director/state 最近一次是否成功
        leaderboard: { battle: [], bond: [], badges: [] }, // 三维排行榜数据
        lbTab: 'battle', // 当前选中的排行榜 tab
        lbOk: true,     // GET /api/leaderboard 最近一次是否成功
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
        await Promise.all([fetchRelationships(), fetchDirectorState(), fetchLeaderboard()]);
        drawRelationshipGraph();
        renderFactions();
        renderDirectorEvents();
        renderLeaderboard();
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
                    description,
                    importance: 7,
                }),
            });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            if (status) status.textContent = '✅ 已注入';
            const input = document.getElementById('inject-input');
            if (input) input.value = '';
            await refreshDirector(); // 立刻反映到事件列表
        } catch (e) {
            if (status) status.textContent = '⚠️ 不可用: ' + e.message;
        } finally {
            if (btn) btn.disabled = false;
            setTimeout(() => { if (status) status.textContent = ''; }, 3000);
        }
    }

    /** POST 保存 / 加载世界状态 */
    async function saveWorld() {
        await worldPersist('/api/world/save', '💾 已保存');
    }
    async function loadWorld() {
        await worldPersist('/api/world/load', '📂 已加载');
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
        const shouldShow = window.innerWidth >= DIRECTOR_MIN_WIDTH;
        if (shouldShow === director.enabled) return;
        director.enabled = shouldShow;
        panel.classList.toggle('open', shouldShow);
        if (shouldShow) refreshDirector();
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
        // 6. 启动战斗轮询 (30s) — 进化 overlay + 战斗数
        startBattlePolling();
        // 7. 初始化导演面板 (仅宽屏显示, 30s 刷新)
        initDirector();
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
