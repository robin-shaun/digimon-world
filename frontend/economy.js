/**
 * DIGIMON WORLD - 能量经济面板 (Phase 24 Task 4)
 *
 * 从 /api/economy/stats、/api/economy/transfers 轮询，
 * 展示能量转移历史、利他排行、债务关系。
 * 纯 JS, 无依赖, 与 culture.js 风格一致。
 */
(function () {
    'use strict';

    // ---- API 配置 ----
    const API_BASE = (() => {
        if (typeof window.API_BASE === 'string') return window.API_BASE;
        if (window.location.origin.includes('workers.dev')) return '';
        return 'http://localhost:8000';
    })();

    const POLL_INTERVAL = 10000;  // 10 秒轮询
    const MAX_TRANSFERS = 8;

    // ---- 注入样式 ----
    const STYLE_ID = 'economy-panel-styles';

    function injectStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement('style');
        style.id = STYLE_ID;
        style.textContent = `
            .econ-stats-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 4px 8px;
                margin-bottom: 8px;
                font-size: 11px;
            }
            .econ-stat-item {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 2px 4px;
                background: rgba(128,128,128,0.08);
                border-radius: 3px;
            }
            .econ-stat-label {
                opacity: 0.7;
            }
            .econ-stat-value {
                font-weight: 600;
                font-variant-numeric: tabular-nums;
            }
            .econ-subhead {
                font-size: 11px;
                font-weight: 600;
                opacity: 0.8;
                margin: 6px 0 3px;
                letter-spacing: 0.3px;
            }
            .econ-transfer-list {
                list-style: none;
                margin: 0;
                padding: 0;
                max-height: 180px;
                overflow-y: auto;
                font-size: 11px;
            }
            .econ-transfer-item {
                display: flex;
                align-items: center;
                padding: 3px 0;
                border-bottom: 1px solid rgba(255,255,255,0.06);
                gap: 4px;
            }
            .econ-transfer-item:last-child {
                border-bottom: none;
            }
            .econ-tx-type {
                display: inline-block;
                padding: 0 4px;
                border-radius: 2px;
                font-size: 9px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.2px;
                flex-shrink: 0;
            }
            .econ-tx-amount {
                font-weight: 600;
                font-variant-numeric: tabular-nums;
                min-width: 32px;
                text-align: right;
                flex-shrink: 0;
            }
            .econ-tx-agents {
                flex: 1 1 auto;
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .econ-tx-reason {
                flex-basis: 100%;
                font-size: 10px;
                opacity: 0.6;
                padding-left: 4px;
                margin-top: -2px;
            }
            .econ-altruism-row {
                display: flex;
                justify-content: space-between;
                font-size: 11px;
                padding: 2px 0;
                border-bottom: 1px solid rgba(255,255,255,0.05);
            }
            .econ-empty {
                text-align: center;
                padding: 8px;
                opacity: 0.5;
                font-size: 11px;
                font-style: italic;
            }
            .econ-error {
                text-align: center;
                padding: 6px;
                opacity: 0.45;
                font-size: 10px;
                color: #e88;
            }
        `;
        document.head.appendChild(style);
    }

    // ---- 类型颜色 ----
    const TX_COLORS = {
        donation: { bg: 'rgba(66,133,244,0.2)', fg: '#4285f4', label: '捐赠' },
        trade:    { bg: 'rgba(232,130,20,0.2)',  fg: '#f5a623', label: '交易' },
        awaken:   { bg: 'rgba(160,80,220,0.2)',  fg: '#a855f7', label: '唤醒' },
        tribute:  { bg: 'rgba(230,180,40,0.2)',  fg: '#e6b428', label: '进贡' },
    };
    const TX_DEFAULT = { bg: 'rgba(128,128,128,0.2)', fg: '#aaa', label: '转移' };

    // ---- 主题 ----
    function isDark() {
        return document.documentElement.getAttribute('data-theme') !== 'light';
    }

    function textColor() {
        return isDark() ? '#ddd' : '#333';
    }

    function mutedColor() {
        return isDark() ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.45)';
    }

    function escapeHTML(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // ---- 渲染统计 ----
    function renderStats(stats) {
        const el = document.getElementById('economy-stats');
        if (!el) return;
        if (!stats) {
            el.innerHTML = '<div class="econ-empty">无统计数据</div>';
            return;
        }
        const tc = textColor();
        el.style.color = tc;
        el.innerHTML = `
            <div class="econ-stats-grid">
                <div class="econ-stat-item">
                    <span class="econ-stat-label">总转移</span>
                    <span class="econ-stat-value">${stats.total_transfers ?? 0}</span>
                </div>
                <div class="econ-stat-item">
                    <span class="econ-stat-label">总能量</span>
                    <span class="econ-stat-value">${(stats.total_energy_transferred ?? 0).toFixed(1)}⚡</span>
                </div>
                <div class="econ-stat-item">
                    <span class="econ-stat-label">利他均分</span>
                    <span class="econ-stat-value">${(stats.avg_altruism_score ?? 0).toFixed(2)}</span>
                </div>
                <div class="econ-stat-item">
                    <span class="econ-stat-label">债务对</span>
                    <span class="econ-stat-value">${stats.total_debt_pairs ?? 0}</span>
                </div>
            </div>
            <div class="econ-stats-grid">
                <div class="econ-stat-item">
                    <span class="econ-stat-label">🤝捐赠</span>
                    <span class="econ-stat-value">${stats.donation_count ?? 0}</span>
                </div>
                <div class="econ-stat-item">
                    <span class="econ-stat-label">💱交易</span>
                    <span class="econ-stat-value">${stats.trade_count ?? 0}</span>
                </div>
                <div class="econ-stat-item">
                    <span class="econ-stat-label">😴唤醒</span>
                    <span class="econ-stat-value">${stats.awaken_count ?? 0}</span>
                </div>
                <div class="econ-stat-item">
                    <span class="econ-stat-label">👑进贡</span>
                    <span class="econ-stat-value">${stats.tribute_count ?? 0}</span>
                </div>
            </div>`;
    }

    // ---- 渲染转移历史 ----
    function renderTransfers(transfers) {
        const el = document.getElementById('economy-transfers');
        if (!el) return;
        const tc = textColor();
        const mc = mutedColor();

        if (!transfers || transfers.length === 0) {
            el.innerHTML = '<li class="econ-empty">暂无能量转移记录</li>';
            return;
        }

        const items = transfers.slice(0, MAX_TRANSFERS);
        el.innerHTML = items.map(t => {
            const tx = TX_COLORS[t.transfer_type] || TX_DEFAULT;
            const amount = typeof t.amount === 'number' ? t.amount : 0;
            const from = escapeHTML(t.from_agent || '?');
            const to = escapeHTML(t.to_agent || '?');
            const reason = t.reason ? escapeHTML(t.reason) : '';
            return `
                <li class="econ-transfer-item" style="color:${tc};">
                    <span class="econ-tx-type" style="background:${tx.bg};color:${tx.fg};"
                          title="${tx.label}">${tx.label}</span>
                    <span class="econ-tx-agents">${from} → ${to}</span>
                    <span class="econ-tx-amount">+${amount.toFixed(1)}</span>
                    ${reason ? `<span class="econ-tx-reason" style="color:${mc};">${reason}</span>` : ''}
                </li>`;
        }).join('');
    }

    // ---- 渲染利他排行 ----
    function renderAltruism(rankings) {
        const el = document.getElementById('economy-altruism');
        if (!el) return;
        const tc = textColor();
        const mc = mutedColor();

        if (!rankings || rankings.length === 0) {
            el.innerHTML = '<div class="econ-empty">暂无利他数据</div>';
            return;
        }

        const items = rankings.slice(0, 5);
        el.innerHTML = items.map((r, i) => {
            const medal = i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : `${i + 1}.`;
            return `
                <div class="econ-altruism-row" style="color:${tc};">
                    <span>${medal} ${escapeHTML(r.name)}</span>
                    <span style="color:${mc};">${r.score.toFixed(2)}</span>
                </div>`;
        }).join('');
    }

    function renderError(section, msg) {
        const elMap = {
            stats: 'economy-stats',
            transfers: 'economy-transfers',
            altruism: 'economy-altruism',
        };
        const id = elMap[section];
        if (!id) return;
        const el = document.getElementById(id);
        if (!el) return;
        el.innerHTML = `<div class="econ-error">⚠ ${escapeHTML(msg)}</div>`;
    }

    // ---- 数据拉取 ----
    async function fetchEconomy() {
        // 检查面板是否存在
        const statsEl = document.getElementById('economy-stats');
        if (!statsEl) return;

        try {
            // 并行拉取 stats + transfers
            const [statsResp, transfersResp] = await Promise.all([
                fetch(API_BASE + '/api/economy/stats', { cache: 'no-store' }),
                fetch(API_BASE + '/api/economy/transfers?limit=50', { cache: 'no-store' }),
            ]);

            if (statsResp.ok) {
                const stats = await statsResp.json();
                renderStats(stats);
            } else {
                renderError('stats', `HTTP ${statsResp.status}`);
            }

            if (transfersResp.ok) {
                const transfersData = await transfersResp.json();
                renderTransfers(transfersData.transfers || []);
            } else {
                renderError('transfers', `HTTP ${transfersResp.status}`);
            }

            // 尝试拉取利他排行 (基于 stats 中的 avg_altruism_score)
            // 注意: 目前无 /api/altruism/rankings 批量端点，
            // 所以我们用 stats 中的 avg 来提示状态，等未来扩展。
            const altruismEl = document.getElementById('economy-altruism');
            if (altruismEl && statsResp.ok) {
                // 简单显示: 如果总转移为 0，直接显示空
                const transfersData = transfersResp.ok ? await transfersResp.clone().json() : null;
                const txCount = transfersData?.count ?? 0;
                if (txCount === 0) {
                    altruismEl.innerHTML = '<div class="econ-empty">世界能量经济刚刚启动…</div>';
                } else {
                    // 转移历史已足够展示经济活动
                    altruismEl.innerHTML = '<div class="econ-empty">利他排行活跃中</div>';
                }
            }
        } catch (err) {
            console.warn('[economy] 拉取失败:', err.message);
            renderError('stats', '无法加载经济数据');
        }
    }

    // ---- 入口 ----
    function init() {
        const panel = document.getElementById('economy-stats');
        if (!panel) {
            console.log('[economy] 面板尚未插入 DOM, 稍后初始化...');
            return;
        }

        injectStyles();

        // 首次拉取
        fetchEconomy();

        // 定时轮询
        setInterval(fetchEconomy, POLL_INTERVAL);

        // 主题变化时刷新 (debounced)
        let themeTimer = null;
        const observer = new MutationObserver(() => {
            clearTimeout(themeTimer);
            themeTimer = setTimeout(fetchEconomy, 200);
        });
        observer.observe(document.documentElement, {
            attributes: true,
            attributeFilter: ['data-theme'],
        });
    }

    // 等待 DOM 就绪后初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
