/**
 * DIGIMON WORLD - 知识经济面板 (Phase 27 Task 4)
 *
 * 从 /api/knowledge + /api/knowledge/hot 轮询 KnowledgePool，
 * 展示热门知识、科技树解锁进度、各领域发明统计。
 * 纯 JS, 无依赖, 与 culture.js / economy.js 风格一致。
 */
(function () {
    'use strict';

    // ---- API 配置 ----
    const API_BASE = (() => {
        if (typeof window.API_BASE === 'string') return window.API_BASE;
        if (window.location.origin.includes('workers.dev')) return '';
        return 'http://localhost:8000';
    })();

    const POLL_INTERVAL = 12000;  // 12 秒轮询
    const MAX_HOT = 8;

    // ---- 注入样式 ----
    const STYLE_ID = 'knowledge-panel-styles';

    function injectStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement('style');
        style.id = STYLE_ID;
        style.textContent = `
            .kn-stats-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 4px 8px;
                margin-bottom: 8px;
                font-size: 11px;
            }
            .kn-stat-item {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 2px 5px;
                background: rgba(128,128,128,0.08);
                border-radius: 3px;
            }
            .kn-stat-label { opacity: 0.7; }
            .kn-stat-value {
                font-weight: 600;
                font-variant-numeric: tabular-nums;
            }
            .kn-subhead {
                font-size: 11px;
                font-weight: 600;
                opacity: 0.8;
                margin: 8px 0 4px;
                letter-spacing: 0.3px;
            }
            .kn-hot-list {
                list-style: none;
                margin: 0;
                padding: 0;
                max-height: 220px;
                overflow-y: auto;
            }
            .kn-hot-item {
                padding: 5px 0;
                border-bottom: 1px solid rgba(255,255,255,0.06);
                font-size: 11px;
                display: flex;
                align-items: center;
                gap: 6px;
            }
            .kn-hot-item:last-child { border-bottom: none; }
            .kn-hot-icon { font-size: 14px; flex-shrink: 0; }
            .kn-hot-info { flex: 1; min-width: 0; }
            .kn-hot-name { font-weight: 600; word-break: break-all; }
            .kn-hot-meta { font-size: 10px; opacity: 0.6; display: flex; gap: 8px; }
            .kn-hot-cites {
                font-size: 10px;
                font-weight: 700;
                flex-shrink: 0;
                min-width: 32px;
                text-align: right;
            }
            .kn-tech-tree {
                margin-top: 6px;
            }
            .kn-domain-bar {
                display: flex;
                align-items: center;
                gap: 6px;
                padding: 3px 0;
                font-size: 11px;
            }
            .kn-domain-icon {
                width: 20px;
                text-align: center;
                flex-shrink: 0;
            }
            .kn-domain-name {
                width: 42px;
                flex-shrink: 0;
                opacity: 0.75;
            }
            .kn-domain-track {
                flex: 1;
                height: 6px;
                background: rgba(255,255,255,0.08);
                border-radius: 3px;
                overflow: hidden;
            }
            .kn-domain-fill {
                height: 100%;
                border-radius: 3px;
                transition: width 0.6s;
            }
            .kn-domain-count {
                font-size: 10px;
                min-width: 28px;
                text-align: right;
                opacity: 0.7;
                font-variant-numeric: tabular-nums;
            }
            .kn-domain-locked { opacity: 0.35; }
            .kn-no-data {
                text-align: center;
                padding: 12px 0;
                font-size: 11px;
                opacity: 0.5;
            }
        `;
        document.head.appendChild(style);
    }

    // ---- 领域图标与颜色 ----
    const DOMAIN_CONFIG = {
        battle:      { icon: '⚔️', color: '#ff6b6b', label: '战斗' },
        survival:    { icon: '🛡️', color: '#45b7d1', label: '生存' },
        social:      { icon: '💬', color: '#f9ca24', label: '社交' },
        exploration: { icon: '🗺️', color: '#6ab04c', label: '探索' },
        crafting:    { icon: '🔨', color: '#be2edd', label: '制造' },
    };

    // ---- DOM 引用 ----
    let statsEl = null;
    let hotListEl = null;
    let techTreeEl = null;

    function getContainers() {
        statsEl = document.getElementById('knowledge-stats');
        hotListEl = document.getElementById('knowledge-hot-list');
        techTreeEl = document.getElementById('knowledge-tech-tree');
    }

    // ---- 主轮询 ----
    async function poll() {
        getContainers();
        if (!statsEl && !hotListEl && !techTreeEl) return;  // 面板未挂载

        try {
            const [knResp, hotResp] = await Promise.all([
                fetch(API_BASE + '/api/knowledge', { cache: 'no-store' }),
                fetch(API_BASE + '/api/knowledge/hot?limit=' + MAX_HOT, { cache: 'no-store' }),
            ]);

            if (knResp.ok) {
                const kn = await knResp.json();
                renderStats(kn);
                renderTechTree(kn);
            }
            if (hotResp.ok) {
                const hot = await hotResp.json();
                renderHotList(hot);
            }
        } catch (_) {
            // 后端未启动, 静默忽略
        }
    }

    // ---- 统计网格 ----
    function renderStats(kn) {
        if (!statsEl) return;
        const s = kn.stats || {};
        const hotCount = s.hot_count != null ? s.hot_count : 0;
        const hotColor = hotCount > 0 ? '#ffb347' : 'var(--text-secondary, #888)';

        statsEl.innerHTML =
            '<div class="kn-stat-item">' +
            '<span class="kn-stat-label">📚 知识条目</span>' +
            '<span class="kn-stat-value">' + (s.total_knowledge || 0) + '</span>' +
            '</div>' +
            '<div class="kn-stat-item">' +
            '<span class="kn-stat-label">⭐ 技能</span>' +
            '<span class="kn-stat-value">' + (s.total_skills || 0) + '</span>' +
            '</div>' +
            '<div class="kn-stat-item">' +
            '<span class="kn-stat-label">🔥 热门</span>' +
            '<span class="kn-stat-value" style="color:' + hotColor + '">' + hotCount + '</span>' +
            '</div>' +
            '<div class="kn-stat-item">' +
            '<span class="kn-stat-label">👥 知者</span>' +
            '<span class="kn-stat-value">' + (s.total_agents_with_knowledge || 0) + '</span>' +
            '</div>';
    }

    // ---- 热门知识列表 ----
    function renderHotList(hot) {
        if (!hotListEl) return;
        const items = hot.hot || [];
        if (items.length === 0) {
            hotListEl.innerHTML = '<li class="kn-no-data">暂无热门知识 — 数码兽们还在学习中…</li>';
            return;
        }

        let html = '';
        for (let i = 0; i < items.length; i++) {
            const item = items[i];
            const dc = DOMAIN_CONFIG[item.domain] || { icon: '📌', color: '#888' };
            const citeColor = item.citation_count >= 5 ? '#ff6b6b' :
                (item.citation_count >= 3 ? '#ffb347' : 'var(--text-secondary, #888)');

            html += '<li class="kn-hot-item">' +
                '<span class="kn-hot-icon" title="' + dc.label + '">' + dc.icon + '</span>' +
                '<span class="kn-hot-info">' +
                '<span class="kn-hot-name">' + escapeHtml(item.name || '?') + '</span>' +
                '<span class="kn-hot-meta">' +
                '<span>' + dc.label + '</span>' +
                '<span>👤 ' + escapeHtml(item.inventor_id || '?') + '</span>' +
                '</span>' +
                '</span>' +
                '<span class="kn-hot-cites" style="color:' + citeColor + '">' +
                '📖' + (item.citation_count || 0) +
                '</span>' +
                '</li>';
        }
        hotListEl.innerHTML = html;
    }

    // ---- 科技树进度 ----
    function renderTechTree(kn) {
        if (!techTreeEl) return;
        const tt = (kn.stats && kn.stats.tech_tree) || {};
        const byDomain = tt.by_domain || {};
        const totalNodes = tt.total_nodes || 0;
        const unlockedNodes = tt.unlocked_nodes || 0;
        const unlockPct = tt.unlock_percentage || 0;

        // 预先获取 nodes 信息来计算每个 domain 的 total
        const nodes = (kn.tech_tree && kn.tech_tree.nodes) || {};
        const domainTotals = {};
        for (const nid of Object.keys(nodes)) {
            const nd = nodes[nid];
            const dom = nd.domain || 'unknown';
            domainTotals[dom] = (domainTotals[dom] || 0) + 1;
        }

        const domains = ['battle', 'survival', 'social', 'exploration', 'crafting'];

        let html = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">' +
            '<span style="font-size:11px;opacity:0.7;">科技树: ' + unlockedNodes + '/' + totalNodes + ' 解锁 (' + unlockPct + '%)</span>' +
            '</div>';

        for (let i = 0; i < domains.length; i++) {
            const dom = domains[i];
            const dc = DOMAIN_CONFIG[dom] || { icon: '📌', color: '#888', label: dom };
            const unlocked = byDomain[dom] || 0;
            const total = domainTotals[dom] || 2;  // fallback 2
            const pct = total > 0 ? Math.round(unlocked / total * 100) : 0;
            const isLocked = unlocked === 0;

            html += '<div class="kn-domain-bar' + (isLocked ? ' kn-domain-locked' : '') + '">' +
                '<span class="kn-domain-icon">' + dc.icon + '</span>' +
                '<span class="kn-domain-name">' + dc.label + '</span>' +
                '<div class="kn-domain-track">' +
                '<div class="kn-domain-fill" style="width:' + pct + '%;background:' + dc.color + ';"></div>' +
                '</div>' +
                '<span class="kn-domain-count">' + unlocked + '/' + total + '</span>' +
                '</div>';
        }

        techTreeEl.innerHTML = html;
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    // ---- 初始化 ----
    function init() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', boot);
        } else {
            boot();
        }
    }

    function boot() {
        injectStyles();
        getContainers();
        if (statsEl || hotListEl || techTreeEl) {
            poll();  // 立即首次拉取
            setInterval(poll, POLL_INTERVAL);
        } else {
            // DOM 还没渲染（director panel 可能延迟初始化），再试一次
            setTimeout(boot, 2000);
        }
    }

    init();
})();
