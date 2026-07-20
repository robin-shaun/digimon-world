/**
 * DIGIMON WORLD - 世界年鉴面板 (Phase 29 Task 3)
 *
 * 从 /api/almanac 轮询 WorldAlmanac，展示:
 * - 当前世界快照 (数码兽数、能量、知识、派系、一致性)
 * - 已归档章节时间线 (可点击展开详情)
 * - 章节详情: 精选事件、趋势报告、名人堂
 * 纯 JS, 无依赖, 与 economy.js / knowledge.js 风格一致。
 */
(function () {
    'use strict';

    // ---- API 配置 ----
    const API_BASE = (() => {
        if (typeof window.API_BASE === 'string') return window.API_BASE;
        if (window.location.origin.includes('workers.dev')) return '';
        return 'http://localhost:8000';
    })();

    const POLL_INTERVAL = 15000;  // 15 秒轮询
    const MAX_EVENTS = 8;
    const MAX_HALL = 3;

    // ---- 注入样式 ----
    const STYLE_ID = 'almanac-panel-styles';

    function injectStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement('style');
        style.id = STYLE_ID;
        style.textContent = `
            .alm-snapshot-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 3px 6px;
                margin-bottom: 8px;
                font-size: 11px;
            }
            .alm-stat-item {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 2px 4px;
                background: rgba(128,128,128,0.08);
                border-radius: 3px;
            }
            .alm-stat-label { opacity: 0.7; }
            .alm-stat-value {
                font-weight: 600;
                font-variant-numeric: tabular-nums;
            }
            .alm-stat-value.pos { color: #4ade80; }
            .alm-stat-value.neg { color: #f87171; }
            .alm-subhead {
                font-size: 11px;
                font-weight: 700;
                margin: 6px 0 4px;
                opacity: 0.85;
            }
            .alm-chapter-item {
                cursor: pointer;
                padding: 4px 6px;
                margin: 0 0 3px;
                background: rgba(128,128,128,0.06);
                border-radius: 3px;
                font-size: 11px;
                transition: background 0.15s;
            }
            .alm-chapter-item:hover {
                background: rgba(128,128,128,0.14);
            }
            .alm-chapter-item.active {
                background: rgba(99,102,241,0.18);
                border-left: 2px solid #6366f1;
            }
            .alm-chapter-epoch {
                font-weight: 700;
                color: #818cf8;
                margin-right: 4px;
            }
            .alm-chapter-range {
                opacity: 0.6;
                font-size: 10px;
            }
            .alm-chapter-summary {
                display: block;
                margin-top: 2px;
                opacity: 0.8;
                font-size: 10px;
                line-height: 1.3;
            }
            .alm-detail-section {
                margin-bottom: 6px;
            }
            .alm-event-item {
                padding: 2px 4px;
                margin: 1px 0;
                font-size: 10px;
                border-bottom: 1px solid rgba(128,128,128,0.1);
                display: flex;
                justify-content: space-between;
            }
            .alm-event-type {
                background: rgba(99,102,241,0.2);
                padding: 1px 4px;
                border-radius: 2px;
                font-size: 9px;
                margin-right: 4px;
                white-space: nowrap;
            }
            .alm-event-title {
                flex: 1;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .alm-event-sig {
                opacity: 0.5;
                font-size: 9px;
                margin-left: 4px;
                white-space: nowrap;
            }
            .alm-trend-item {
                display: flex;
                justify-content: space-between;
                font-size: 10px;
                padding: 1px 4px;
            }
            .alm-trend-label { opacity: 0.7; }
            .alm-hall-entry {
                display: flex;
                justify-content: space-between;
                align-items: center;
                font-size: 10px;
                padding: 1px 4px;
                border-bottom: 1px solid rgba(128,128,128,0.08);
            }
            .alm-hall-rank {
                font-weight: 700;
                color: #f59e0b;
                margin-right: 4px;
                min-width: 14px;
            }
            .alm-hall-name {
                flex: 1;
            }
            .alm-hall-value {
                font-variant-numeric: tabular-nums;
                opacity: 0.8;
                margin-left: 4px;
            }
            .alm-empty {
                color: rgba(128,128,128,0.5);
                font-size: 10px;
                text-align: center;
                padding: 8px 0;
            }
        `;
        document.head.appendChild(style);
    }

    // ---- 渲染 ----

    /** 渲染当前快照统计 */
    function renderSnapshot(snap) {
        if (!snap) {
            document.getElementById('almanac-snapshot').innerHTML = '<p class="alm-empty">等待世界启动…</p>';
            return;
        }
        const fmt = (v, suffix = '') => v !== undefined ? v + suffix : '--';
        const html = `
            <div class="alm-snapshot-grid">
                <div class="alm-stat-item"><span class="alm-stat-label">数码兽</span><span class="alm-stat-value">${fmt(snap.total_digimon)}</span></div>
                <div class="alm-stat-item"><span class="alm-stat-label">活跃/休眠</span><span class="alm-stat-value">${snap.active_digimon}/${snap.dormant_digimon}</span></div>
                <div class="alm-stat-item"><span class="alm-stat-label">平均能量</span><span class="alm-stat-value">${snap.avg_energy.toFixed(1)}</span></div>
                <div class="alm-stat-item"><span class="alm-stat-label">知识条目</span><span class="alm-stat-value">${fmt(snap.total_knowledge_items)}</span></div>
                <div class="alm-stat-item"><span class="alm-stat-label">共享惯例</span><span class="alm-stat-value">${fmt(snap.total_conventions)}</span></div>
                <div class="alm-stat-item"><span class="alm-stat-label">派系</span><span class="alm-stat-value">${fmt(snap.faction_count)}</span></div>
                <div class="alm-stat-item"><span class="alm-stat-label">叙事一致性</span><span class="alm-stat-value">${snap.avg_coherence_score.toFixed(2)}</span></div>
                <div class="alm-stat-item"><span class="alm-stat-label">世界时间</span><span class="alm-stat-value">${snap.world_time || '--'}</span></div>
            </div>
        `;
        document.getElementById('almanac-snapshot').innerHTML = html;
    }

    /** 渲染章节时间线 */
    function renderChapterList(chapters, currentEpoch) {
        const el = document.getElementById('almanac-chapters');
        if (!chapters || chapters.length === 0) {
            el.innerHTML = '<p class="alm-empty">暂无归档章节<br>(每100 tick自动生成)</p>';
            return;
        }
        el.innerHTML = chapters.map(ch => {
            const activeClass = (ch.epoch === currentEpoch) ? ' active' : '';
            return `
                <div class="alm-chapter-item${activeClass}" data-epoch="${ch.epoch}">
                    <span class="alm-chapter-epoch">#${ch.epoch}</span>
                    <span class="alm-chapter-range">${ch.world_time_start} → ${ch.world_time_end}</span>
                    <span class="alm-chapter-summary">${esc(ch.narrative_summary || ch.event_count + ' events')}</span>
                </div>`;
        }).join('\n');
    }

    /** 渲染章节详情 */
    function renderChapterDetail(chapter) {
        if (!chapter) {
            document.getElementById('almanac-detail').innerHTML = '<p class="alm-empty">点击章节查看详情</p>';
            return;
        }

        let html = '';

        // -- 精选事件 --
        if (chapter.top_events && chapter.top_events.length > 0) {
            html += '<div class="alm-subhead">🎯 精选事件</div>';
            html += chapter.top_events.slice(0, MAX_EVENTS).map(e => `
                <div class="alm-event-item">
                    <span class="alm-event-type">${esc(e.event_type)}</span>
                    <span class="alm-event-title" title="${esc(e.description)}">${esc(e.title)}</span>
                    <span class="alm-event-sig">${e.significance.toFixed(1)}</span>
                </div>`).join('');
        }

        // -- 趋势报告 --
        if (chapter.trends) {
            const t = chapter.trends;
            const trends = [
                { label: '知识增长', from: t.knowledge_growth?.from, to: t.knowledge_growth?.to, delta: t.knowledge_growth?.delta },
                { label: '平均能量', from: t.energy_trend?.from?.toFixed?.(1), to: t.energy_trend?.to?.toFixed?.(1), delta: t.energy_trend?.delta },
                { label: '派系变化', from: t.faction_changes?.from, to: t.faction_changes?.to, delta: t.faction_changes?.delta },
                { label: '人口变化', from: t.population_change?.from, to: t.population_change?.to, delta: t.population_change?.delta },
                { label: '一致性', from: t.coherence_trend?.from?.toFixed?.(2), to: t.coherence_trend?.to?.toFixed?.(2), delta: t.coherence_trend?.delta },
            ];

            html += '<div class="alm-subhead">📈 趋势 (vs 上章)</div>';
            html += trends.map(tr => {
                const delta = tr.delta !== undefined ? tr.delta : 0;
                const cls = delta > 0 ? 'pos' : delta < 0 ? 'neg' : '';
                const sign = delta > 0 ? '+' : '';
                return `<div class="alm-trend-item">
                    <span class="alm-trend-label">${tr.label}</span>
                    <span>${tr.from ?? '--'} → ${tr.to ?? '--'} <span class="alm-stat-value ${cls}">${sign}${delta}</span></span>
                </div>`;
            }).join('');

            // 人格漂移
            if (t.personality_shifts && t.personality_shifts.length > 0) {
                html += '<div class="alm-subhead">🧬 人格漂移</div>';
                html += t.personality_shifts.map(s =>
                    `<div class="alm-trend-item">
                        <span class="alm-trend-label">${esc(s.mbti)}</span>
                        <span>${s.from} → ${s.to} <span class="alm-stat-value ${s.delta > 0 ? 'pos' : 'neg'}">${s.delta > 0 ? '+' : ''}${s.delta}</span></span>
                    </div>`
                ).join('');
            }
        }

        // -- 名人堂 --
        if (chapter.hall_of_fame) {
            const h = chapter.hall_of_fame;
            const halls = [
                { label: '⚔️ 战士', key: 'top_fighters' },
                { label: '💡 发明家', key: 'top_inventors' },
                { label: '💬 社交', key: 'top_socializers' },
            ];
            const hasData = halls.some(hh => h[hh.key] && h[hh.key].length > 0);
            if (hasData) {
                html += '<div class="alm-subhead">🏆 名人堂</div>';
                halls.forEach(hh => {
                    const entries = h[hh.key];
                    if (!entries || entries.length === 0) return;
                    html += entries.slice(0, MAX_HALL).map((e, i) => `
                        <div class="alm-hall-entry">
                            <span class="alm-hall-rank">#${i + 1}</span>
                            <span class="alm-hall-name">${esc(e.name)}</span>
                            <span class="alm-hall-value">${e.value}</span>
                        </div>`).join('');
                });
            }
        }

        if (!html) {
            html = '<p class="alm-empty">此章节暂无详细数据</p>';
        }

        document.getElementById('almanac-detail').innerHTML = html;
    }

    function esc(s) {
        if (!s) return '';
        const div = document.createElement('div');
        div.textContent = String(s);
        return div.innerHTML;
    }

    // ---- 章节点击交互 ----
    let _chapters = [];
    let _selectedEpoch = null;

    function setupChapterClicks() {
        const container = document.getElementById('almanac-chapters');
        container.addEventListener('click', function (e) {
            const item = e.target.closest('.alm-chapter-item');
            if (!item) return;
            const epoch = parseInt(item.dataset.epoch, 10);
            if (isNaN(epoch)) return;

            // Toggle or select
            if (_selectedEpoch === epoch) {
                _selectedEpoch = null;
                document.getElementById('almanac-detail').innerHTML = '<p class="alm-empty">点击章节查看详情</p>';
            } else {
                _selectedEpoch = epoch;
                loadChapterDetail(epoch);
            }

            // Update active class
            container.querySelectorAll('.alm-chapter-item').forEach(el => {
                const ep = parseInt(el.dataset.epoch, 10);
                el.classList.toggle('active', ep === _selectedEpoch);
            });
        });
    }

    async function loadChapterDetail(epoch) {
        try {
            const resp = await fetch(`${API_BASE}/api/almanac/${epoch}`);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const chapter = await resp.json();
            renderChapterDetail(chapter);
        } catch (err) {
            document.getElementById('almanac-detail').innerHTML =
                `<p class="alm-empty">加载失败: ${esc(err.message)}</p>`;
        }
    }

    // ---- 轮询 ----
    async function poll() {
        try {
            const resp = await fetch(`${API_BASE}/api/almanac/`);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();

            // 快照
            if (data.current_snapshot) {
                renderSnapshot(data.current_snapshot);
            }

            // 章节列表
            _chapters = data.chapters || [];
            const latestChapter = _chapters.length > 0 ? _chapters[_chapters.length - 1] : null;
            renderChapterList(_chapters, _selectedEpoch);

            // 如果之前有选中的章节，刷新详情
            if (_selectedEpoch !== null) {
                await loadChapterDetail(_selectedEpoch);
            }

            // 自动选择最新章节（首次加载时）
            if (_selectedEpoch === null && latestChapter) {
                _selectedEpoch = latestChapter.epoch;
                await loadChapterDetail(_selectedEpoch);
                // 更新 active 样式
                document.querySelectorAll('.alm-chapter-item').forEach(el => {
                    const ep = parseInt(el.dataset.epoch, 10);
                    el.classList.toggle('active', ep === _selectedEpoch);
                });
            }
        } catch (err) {
            console.warn('[almanac] poll error:', err.message);
            document.getElementById('almanac-snapshot').innerHTML =
                '<p class="alm-empty">后端未就绪</p>';
        }
    }

    // ---- 初始化 ----
    function init() {
        injectStyles();
        setupChapterClicks();
        poll();
        setInterval(poll, POLL_INTERVAL);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
