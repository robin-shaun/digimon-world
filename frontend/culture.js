/**
 * DIGIMON WORLD - 共享文化面板 (Phase 22 Task 3)
 *
 * 从 /api/conventions 轮询 ConventionPool, 展示共享惯例.
 * 纯 JS, 无依赖, 与 main.js 风格一致.
 */

(function () {
    'use strict';

    // ---- API 配置 (复用 main.js 的逻辑) ----
    const API_BASE = (() => {
        if (typeof window.API_BASE === 'string') return window.API_BASE;
        if (window.location.origin.includes('workers.dev')) return '';
        return 'http://localhost:8000';
    })();

    const POLL_INTERVAL = 8000;  // 8 秒轮询
    const MAX_ITEMS = 10;

    // ---- 注入样式 (追加到 head, 不修改 style.css) ----
    const STYLE_ID = 'culture-panel-styles';

    function injectStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement('style');
        style.id = STYLE_ID;
        style.textContent = `
            /* 文化面板容器 */
            .culture-list {
                list-style: none;
                margin: 0;
                padding: 0;
                max-height: 360px;
                overflow-y: auto;
            }
            .culture-item {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                padding: 6px 0;
                border-bottom: 1px solid var(--border-subtle, rgba(255,255,255,0.08));
                font-size: 12px;
                gap: 4px;
            }
            .culture-item:last-child {
                border-bottom: none;
            }
            .culture-term {
                flex: 1 1 auto;
                min-width: 80px;
                font-weight: 600;
                word-break: break-all;
            }
            .culture-tag {
                display: inline-block;
                padding: 1px 6px;
                border-radius: 3px;
                font-size: 10px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.3px;
            }
            .culture-adoption {
                font-size: 11px;
                opacity: 0.85;
                min-width: 32px;
                text-align: right;
            }
            .culture-strength-bar-wrap {
                width: 100%;
                flex-basis: 100%;
                margin-top: 2px;
            }
            .culture-strength-bar {
                height: 4px;
                border-radius: 2px;
                background: rgba(128,128,128,0.2);
                overflow: hidden;
            }
            .culture-strength-fill {
                height: 100%;
                border-radius: 2px;
                transition: width 0.5s ease;
            }
            .culture-empty {
                text-align: center;
                padding: 16px 8px;
                opacity: 0.65;
                font-size: 13px;
                font-style: italic;
            }
            .culture-error {
                text-align: center;
                padding: 12px 8px;
                opacity: 0.55;
                font-size: 12px;
                color: #e88;
            }
        `;
        document.head.appendChild(style);
    }

    // ---- 分类标签配置 ----
    const CATEGORY_COLORS = {
        term:    { bg: 'rgba(66,133,244,0.2)', fg: '#4285f4', label: '术语' },
        behavior:{ bg: 'rgba(232,130,20,0.2)',  fg: '#f5a623', label: '行为' },
        ritual:  { bg: 'rgba(160,80,220,0.2)',  fg: '#a855f7', label: '仪式' },
    };

    // 默认颜色 (未知分类)
    const DEFAULT_CAT = { bg: 'rgba(128,128,128,0.2)', fg: '#aaa', label: '其他' };

    // ---- 强度渐变色 (绿→黄→红) ----
    function strengthGradient(strength) {
        // strength: 0..1
        const t = Math.max(0, Math.min(1, strength));
        if (t < 0.5) {
            // 绿(0) → 黄(0.5)
            const r = Math.round(255 * t * 2);        // 0→255
            return `rgb(${r}, 220, 40)`;
        } else {
            // 黄(0.5) → 红(1.0)
            const g = Math.round(220 * (1 - (t - 0.5) * 2));  // 220→0
            return `rgb(255, ${g}, 40)`;
        }
    }

    // ---- 主题感知 ----
    function isDark() {
        return document.documentElement.getAttribute('data-theme') !== 'light';
    }

    function textColor() {
        return isDark() ? '#ddd' : '#333';
    }

    function mutedColor() {
        return isDark() ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.45)';
    }

    // ---- 渲染 ----
    /** @param {Array} conventions */
    function renderCulture(conventions) {
        const listEl = document.getElementById('culture-list');
        if (!listEl) return;

        if (!conventions || conventions.length === 0) {
            listEl.innerHTML = '<li class="culture-empty">世界文化正在孕育中…</li>';
            return;
        }

        const tc = textColor();
        const mc = mutedColor();
        const isDarkTheme = isDark();

        const items = conventions.slice(0, MAX_ITEMS);
        listEl.innerHTML = items.map(c => {
            const cat = CATEGORY_COLORS[c.category] || DEFAULT_CAT;
            const strength = typeof c.strength === 'number' ? c.strength : 0;
            const gradient = strengthGradient(strength);
            const strengthPct = Math.round(strength * 100);

            // Dark 主题下 label 暗色文本; light 下也一样保持可读
            return `
                <li class="culture-item" style="color:${tc};">
                    <span class="culture-term">${escapeHTML(c.term)}</span>
                    <span class="culture-tag" style="background:${cat.bg};color:${cat.fg};">
                        ${cat.label}
                    </span>
                    <span class="culture-adoption" style="color:${mc};" title="采纳数">
                        👥${c.adoption_count ?? 0}
                    </span>
                    <div class="culture-strength-bar-wrap" title="强度: ${strengthPct}%">
                        <div class="culture-strength-bar">
                            <div class="culture-strength-fill"
                                 style="width:${strengthPct}%;background:${gradient};">
                            </div>
                        </div>
                    </div>
                </li>`;
        }).join('');
    }

    function escapeHTML(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function renderError(msg) {
        const listEl = document.getElementById('culture-list');
        if (!listEl) return;
        listEl.innerHTML = `<li class="culture-error">⚠ ${escapeHTML(msg)}</li>`;
    }

    // ---- 数据拉取 ----
    async function fetchConventions() {
        const listEl = document.getElementById('culture-list');
        if (!listEl) return;  // 面板未渲染, 跳过

        try {
            const resp = await fetch(API_BASE + '/api/conventions?sort_by=adoption_count', {
                cache: 'no-store',
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            renderCulture(data);
        } catch (err) {
            console.warn('[culture] 拉取惯例失败:', err.message);
            renderError('无法加载文化数据');
        }
    }

    // ---- 入口 ----
    function init() {
        const panel = document.getElementById('culture-list');
        if (!panel) {
            // DOM 可能还没就绪, 稍后重试
            console.log('[culture] culture-list 尚未插入 DOM, 稍后初始化...');
            return;
        }

        injectStyles();

        // 首次拉取
        fetchConventions();

        // 定时轮询
        setInterval(fetchConventions, POLL_INTERVAL);

        // 主题变化时重新渲染 (debounced)
        let themeTimer = null;
        const observer = new MutationObserver(() => {
            clearTimeout(themeTimer);
            themeTimer = setTimeout(fetchConventions, 200);
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
