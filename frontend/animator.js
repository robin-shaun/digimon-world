/**
 * DIGIMON WORLD - 动画引擎 (Phase 13-②)
 *
 * 提供:
 *   1. 帧动画 (FrameAnimator) — 按固定 FPS 循环帧索引
 *   2. 补间动画 (TweenAnimator) — 平滑插值 (位置/缩放/透明度)
 *   3. Easing 函数库
 *
 * 与现有渲染管道集成:
 *   - 数码兽位置使用 TweenAnimator 平滑过渡 (不再瞬移)
 *   - 待机时使用 FrameAnimator 驱动 idle 呼吸/弹跳
 *   - 后续可扩展为真实 sprite sheet 帧动画
 */

window.ANIM = (function () {
    'use strict';

    // ═══════════════════════════════════════════
    // Easing 函数 (Penner easing, simplified)
    // ═══════════════════════════════════════════

    const Easing = {
        linear: function (t) { return t; },
        easeInQuad: function (t) { return t * t; },
        easeOutQuad: function (t) { return t * (2 - t); },
        easeInOutQuad: function (t) { return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t; },
        easeOutElastic: function (t) {
            if (t === 0 || t === 1) return t;
            return Math.pow(2, -10 * t) * Math.sin((t - 1) * (2 * Math.PI) / 0.3) + 1;
        },
        /** 正弦波 (用于呼吸动画) */
        breathe: function (t) {
            return Math.sin(t * Math.PI * 2);
        },
    };

    // ═══════════════════════════════════════════
    // FrameAnimator — 帧动画
    // ═══════════════════════════════════════════

    /**
     * @param {object} opts
     * @param {number} opts.frames  总帧数
     * @param {number} opts.fps     帧率
     * @param {boolean} opts.loop   是否循环
     */
    function FrameAnimator(opts) {
        this.frames = opts.frames || 1;
        this.fps = opts.fps || 3;
        this.loop = opts.loop !== false;
        this._frame = 0;
        this._elapsed = 0;
        this._finished = false;
    }

    FrameAnimator.prototype = {
        /** 每帧调用, delta 为秒 */
        update: function (delta) {
            if (this._finished) return;
            this._elapsed += delta;
            var frameDuration = 1 / this.fps;
            while (this._elapsed >= frameDuration) {
                this._elapsed -= frameDuration;
                this._frame++;
                if (this._frame >= this.frames) {
                    if (this.loop) {
                        this._frame = 0;
                    } else {
                        this._frame = this.frames - 1;
                        this._finished = true;
                        break;
                    }
                }
            }
        },

        /** 当前帧索引 (0-based) */
        frame: function () { return this._frame; },

        /** 归一化进度 0..1 (用于混合/插值) */
        progress: function () {
            return this.frames <= 1 ? 0 : this._frame / (this.frames - 1);
        },

        finished: function () { return this._finished; },

        reset: function () {
            this._frame = 0;
            this._elapsed = 0;
            this._finished = false;
        },
    };

    // ═══════════════════════════════════════════
    // TweenAnimator — 补间动画
    // ═══════════════════════════════════════════

    /**
     * @param {object} opts
     * @param {number} opts.duration  持续时间 (秒)
     * @param {string} [opts.easing]  缓动函数名 (默认 'easeOutQuad')
     * @param {boolean} [opts.yoyo]   是否往返 (默认 false)
     */
    function TweenAnimator(opts) {
        this.duration = opts.duration || 0.5;
        this.easing = Easing[opts.easing] || Easing.easeOutQuad;
        this.yoyo = !!opts.yoyo;
        this._elapsed = 0;
        this._finished = false;
    }

    TweenAnimator.prototype = {
        update: function (delta) {
            if (this._finished) return;
            this._elapsed += delta;
            if (this._elapsed >= this.duration) {
                this._elapsed = this.duration;
                this._finished = true;
            }
        },

        /** 当前归一化值 0..1, 对 yoyo 模式 0→1→0 */
        value: function () {
            var t = this.duration > 0 ? this._elapsed / this.duration : 1;
            t = Math.max(0, Math.min(1, t));
            if (this.yoyo) {
                // 0→1→0: 前半段 0→1, 后半段 1→0
                if (t < 0.5) {
                    t = t * 2;  // 0..1
                } else {
                    t = (1 - t) * 2;  // 1..0
                }
            }
            return this.easing(t);
        },

        finished: function () { return this._finished; },

        reset: function () {
            this._elapsed = 0;
            this._finished = false;
        },
    };

    // ═══════════════════════════════════════════
    // DigimonAnimState — 单只数码兽动画状态
    // ═══════════════════════════════════════════

    /**
     * 管理一只数码兽的所有动画状态:
     *   - idleAnim:   待机帧动画 (驱动呼吸弹跳的 phase)
     *   - moveTween:  移动到新位置时的补间
     *   - targetX/Y:  移动目标位置
     *   - fromX/Y:    移动起始位置
     */
    function DigimonAnimState(name) {
        this.name = name;
        this.idleAnim = new FrameAnimator({ frames: 120, fps: 12, loop: true }); // 10s 呼吸周期
        this.moveTween = null;
        this.targetX = 0;
        this.targetY = 0;
        this.fromX = 0;
        this.fromY = 0;
        this.currentX = 0;
        this.currentY = 0;
        this._initialized = false;
    }

    DigimonAnimState.prototype = {
        /**
         * 设置目标位置。如果当前位置未初始化, 直接瞬移;
         * 否则启动补间动画。
         */
        setTarget: function (x, y) {
            if (!this._initialized) {
                this.currentX = x;
                this.currentY = y;
                this.targetX = x;
                this.targetY = y;
                this._initialized = true;
                return;
            }

            // 如果位置变化超过 1px, 启动补间
            var dx = x - this.targetX;
            var dy = y - this.targetY;
            if (Math.abs(dx) > 1 || Math.abs(dy) > 1) {
                this.fromX = this.currentX;
                this.fromY = this.currentY;
                this.targetX = x;
                this.targetY = y;
                // 移动距离决定补间时长: 50px ~ 0.3s, 200px ~ 0.8s
                var dist = Math.sqrt(dx * dx + dy * dy);
                var duration = Math.min(0.8, Math.max(0.2, dist / 300));
                this.moveTween = new TweenAnimator({ duration: duration, easing: 'easeOutQuad' });
            }
        },

        /** 每帧更新, delta 为秒 */
        update: function (delta) {
            this.idleAnim.update(delta);

            if (this.moveTween) {
                this.moveTween.update(delta);
                var t = this.moveTween.value();
                this.currentX = this.fromX + (this.targetX - this.fromX) * t;
                this.currentY = this.fromY + (this.targetY - this.fromY) * t;

                if (this.moveTween.finished()) {
                    this.currentX = this.targetX;
                    this.currentY = this.targetY;
                    this.moveTween = null;
                }
            }
        },

        /** 获取 idle 呼吸偏移 (像素) — 用于渲染时微调 Y 坐标 */
        idleBounce: function () {
            // 使用正弦波, 幅度 2px, 周期约 0.83s
            return Easing.breathe(this.idleAnim.progress()) * 2;
        },

        /** 获取 idle 缩放系数 — 1.0 ± 0.03 */
        idleScale: function () {
            return 1.0 + Easing.breathe(this.idleAnim.progress() * 0.7) * 0.03;
        },

        /** 是否正在移动中 */
        isMoving: function () {
            return this.moveTween !== null && !this.moveTween.finished();
        },

        /** 渲染位置 (插值后) */
        renderX: function () { return this.currentX; },
        renderY: function () { return this.currentY; },
    };

    // ═══════════════════════════════════════════
    // AnimManager — 全局动画管理器
    // ═══════════════════════════════════════════

    function AnimManager() {
        /** @type {Object<string, DigimonAnimState>} */
        this.states = {};
    }

    AnimManager.prototype = {
        /** 获取或创建某只数码兽的动画状态 */
        get: function (name) {
            if (!this.states[name]) {
                this.states[name] = new DigimonAnimState(name);
            }
            return this.states[name];
        },

        /** 更新所有动画 (每帧调用) */
        updateAll: function (delta) {
            var states = this.states;
            for (var k in states) {
                if (Object.prototype.hasOwnProperty.call(states, k)) {
                    states[k].update(delta);
                }
            }
        },

        /** 批量同步目标位置 (从 API 数据) */
        syncPositions: function (digimonList) {
            for (var i = 0; i < digimonList.length; i++) {
                var d = digimonList[i];
                var st = this.get(d.name);
                st.setTarget(d.position.x, d.position.y);
            }
        },

        /** 清理已不存在的数码兽 */
        prune: function (activeNames) {
            var nameSet = {};
            for (var i = 0; i < activeNames.length; i++) {
                nameSet[activeNames[i]] = true;
            }
            var states = this.states;
            for (var k in states) {
                if (Object.prototype.hasOwnProperty.call(states, k) && !nameSet[k]) {
                    delete states[k];
                }
            }
        },
    };

    // 单例
    var animManager = new AnimManager();

    return {
        Easing: Easing,
        FrameAnimator: FrameAnimator,
        TweenAnimator: TweenAnimator,
        DigimonAnimState: DigimonAnimState,
        manager: animManager,
    };
})();
