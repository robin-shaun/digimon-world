/**
 * DIGIMON WORLD - 粒子特效系统 (Phase 13-②)
 *
 * 轻量 canvas 粒子引擎, 用于进化火花 / 战斗爆裂 / 戳一下涟漪。
 * 无外部依赖, 完全程序化。
 *
 * 用法:
 *   const ps = new ParticleSystem();
 *   ps.burst(x, y, { color: '#ffd700', count: 20, life: 0.8 });
 *   // 在渲染循环中:
 *   ps.update(deltaSeconds);
 *   ps.draw(ctx);
 *
 * 预设:
 *   ps.evolution(x, y)    — 进化金光
 *   ps.battle(x, y)       — 战斗碰撞火花
 *   ps.poke(x, y)         — 戳一下涟漪
 *   ps.heal(x, y)         — 治愈绿光
 */

window.PARTICLE = (function () {
    'use strict';

    /** 单个粒子 */
    function Particle(opts) {
        this.x = opts.x || 0;
        this.y = opts.y || 0;
        this.vx = opts.vx || 0;
        this.vy = opts.vy || 0;
        this.life = opts.life || 1.0;
        this.maxLife = opts.life || 1.0;
        this.color = opts.color || '#ffffff';
        this.size = opts.size || 3;
        this.gravity = opts.gravity || 0;
        this.friction = opts.friction || 0.98;
        this._dead = false;
    }

    Particle.prototype = {
        update: function (dt) {
            this.life -= dt / this.maxLife;
            if (this.life <= 0) {
                this._dead = true;
                return;
            }
            this.vy += this.gravity * dt;
            this.vx *= this.friction;
            this.vy *= this.friction;
            this.x += this.vx * dt;
            this.y += this.vy * dt;
        },
        alpha: function () {
            // ease-out: particles fade slowly at first, quickly at end
            return Math.max(0, Math.min(1, this.life));
        },
        draw: function (ctx) {
            const a = this.alpha();
            if (a <= 0.01) return;
            ctx.globalAlpha = a;
            ctx.fillStyle = this.color;
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.size * (0.4 + a * 0.6), 0, Math.PI * 2);
            ctx.fill();
            ctx.globalAlpha = 1.0;
        },
    };

    /** 预设配置 */
    const PRESETS = {
        evolution: {
            color: '#ffd700',
            accent: '#ffaa00',
            count: 30,
            life: 1.2,
            size: 4,
            spread: 80,
            gravity: 60,
        },
        battle: {
            color: '#ff4444',
            accent: '#ff8844',
            count: 15,
            life: 0.5,
            size: 3,
            spread: 60,
            gravity: 30,
        },
        poke: {
            color: '#ffffff',
            accent: '#aaddff',
            count: 8,
            life: 0.6,
            size: 2,
            spread: 30,
            gravity: 0,
        },
        heal: {
            color: '#44ff88',
            accent: '#88ffbb',
            count: 20,
            life: 1.0,
            size: 3,
            spread: 50,
            gravity: -20,
        },
    };

    /**
     * 粒子系统
     */
    function ParticleSystem() {
        this._particles = [];
        this._alive = 0;
    }

    ParticleSystem.prototype = {
        /** 发射粒子 burst */
        burst: function (x, y, opts) {
            const cfg = Object.assign({}, opts);
            const count = cfg.count != null ? cfg.count : 10;
            const spread = cfg.spread || 50;
            const life = cfg.life || 0.8;
            const size = cfg.size || 3;
            const gravity = cfg.gravity || 0;
            const colors = cfg.accent ? [cfg.color, cfg.accent] : [cfg.color];

            for (let i = 0; i < count; i++) {
                const angle = Math.random() * Math.PI * 2;
                const speed = (0.3 + Math.random() * 0.7) * spread;
                const color = colors[Math.floor(Math.random() * colors.length)];
                const p = new Particle({
                    x: x,
                    y: y,
                    vx: Math.cos(angle) * speed,
                    vy: Math.sin(angle) * speed - spread * 0.2, // slight upward bias
                    life: life * (0.6 + Math.random() * 0.4),
                    color: color,
                    size: size * (0.5 + Math.random()),
                    gravity: gravity,
                    friction: 0.96 + Math.random() * 0.03,
                });
                this._particles.push(p);
            }
            this._alive = this._particles.length;
        },

        /** 预设: 进化金光 */
        evolution: function (x, y) {
            this.burst(x, y, PRESETS.evolution);
        },

        /** 预设: 战斗火花 */
        battle: function (x, y) {
            this.burst(x, y, PRESETS.battle);
        },

        /** 预设: 戳一下涟漪 */
        poke: function (x, y) {
            this.burst(x, y, PRESETS.poke);
        },

        /** 预设: 治愈绿光 */
        heal: function (x, y) {
            this.burst(x, y, PRESETS.heal);
        },

        /** 每帧更新 (dt 单位: 秒) */
        update: function (dt) {
            let alive = 0;
            for (let i = this._particles.length - 1; i >= 0; i--) {
                const p = this._particles[i];
                p.update(dt);
                if (p._dead) {
                    // swap-remove for perf
                    const last = this._particles[this._particles.length - 1];
                    if (i !== this._particles.length - 1) {
                        this._particles[i] = last;
                    }
                    this._particles.pop();
                } else {
                    alive++;
                }
            }
            this._alive = alive;
        },

        /** 绘制所有粒子 */
        draw: function (ctx) {
            for (const p of this._particles) {
                p.draw(ctx);
            }
        },

        /** 活跃粒子数 */
        get alive() {
            return this._alive;
        },

        /** 清空所有粒子 */
        clear: function () {
            this._particles.length = 0;
            this._alive = 0;
        },

        /** 获取粒子列表 (测试用) */
        _debugParticles: function () {
            return this._particles.slice();
        },
    };

    return {
        Particle: Particle,
        ParticleSystem: ParticleSystem,
        PRESETS: PRESETS,
    };
})();
