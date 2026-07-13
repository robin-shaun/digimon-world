/**
 * DIGIMON WORLD - 精灵动画数据 (Phase 13-②)
 *
 * 为每只数码兽定义动画帧数据。当前使用程序化帧(无外部图片),
 * 后续替换为真实 sprite sheet 时只需修改此文件的帧坐标即可。
 *
 * 动作类型:
 *   idle    — 待机动画 (呼吸/摇摆)
 *   walk    — 行走动画
 *   attack  — 攻击动画
 *   evolve  — 进化动画
 *
 * 帧格式: { x, y, w, h } — sprite sheet 上的裁剪区域 (目前仅用作元数据)
 */

window.SPRITE_DATA = (function () {
    'use strict';

    /**
     * 数码兽通用动画配置
     * key: 数码兽名 (小写)
     * value: { actions: { actionName: { frames: number, fps: number, loop: bool } } }
     */
    const configs = {
        agumon: {
            color: '#FF8C00',    // 橙色
            accent: '#FFD700',   // 金色
            size: 18,
            actions: {
                idle:    { frames: 4, fps: 3,  loop: true },
                walk:    { frames: 6, fps: 8,  loop: true },
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },
        gabumon: {
            color: '#4A90D9',    // 蓝色
            accent: '#87CEEB',
            size: 18,
            actions: {
                idle:    { frames: 4, fps: 3,  loop: true },
                walk:    { frames: 6, fps: 8,  loop: true },
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },
        biyomon: {
            color: '#FF69B4',    // 粉色
            accent: '#FFB6C1',
            size: 16,
            actions: {
                idle:    { frames: 4, fps: 3,  loop: true },
                walk:    { frames: 6, fps: 8,  loop: true },
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },
        palmon: {
            color: '#32CD32',    // 绿色
            accent: '#90EE90',
            size: 18,
            actions: {
                idle:    { frames: 4, fps: 3,  loop: true },
                walk:    { frames: 6, fps: 8,  loop: true },
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },
        gomamon: {
            color: '#FFFFFF',    // 白色
            accent: '#E0E0FF',
            size: 17,
            actions: {
                idle:    { frames: 4, fps: 3,  loop: true },
                walk:    { frames: 6, fps: 8,  loop: true },
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },
        tentomon: {
            color: '#8B4513',    // 棕色
            accent: '#D2691E',
            size: 16,
            actions: {
                idle:    { frames: 4, fps: 3,  loop: true },
                walk:    { frames: 6, fps: 8,  loop: true },
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },
        patamon: {
            color: '#FFDAB9',    // 浅橙
            accent: '#FFE4B5',
            size: 14,
            actions: {
                idle:    { frames: 4, fps: 4,  loop: true },  // 巴达兽更活泼
                walk:    { frames: 6, fps: 8,  loop: true },
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },
        tailmon: {
            color: '#F5F5DC',    // 米色
            accent: '#FFE4E1',
            size: 16,
            actions: {
                idle:    { frames: 4, fps: 3,  loop: true },
                walk:    { frames: 6, fps: 8,  loop: true },
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },
    };

    /** 默认配置 (未知数码兽) */
    const DEFAULT = {
        color: '#AABBCC',
        accent: '#CCDDEE',
        size: 16,
        actions: {
            idle:    { frames: 4, fps: 3,  loop: true },
            walk:    { frames: 6, fps: 8,  loop: true },
        },
    };

    /**
     * 获取数码兽精灵配置
     * @param {string} name 数码兽名称
     * @returns {object} 精灵配置 { color, accent, size, actions }
     */
    function getSpriteConfig(name) {
        const key = (name || '').toLowerCase().replace(/[\s-]/g, '_');
        return configs[key] || DEFAULT;
    }

    /**
     * 获取指定动作的动画参数
     * @param {string} name 数码兽名称
     * @param {string} action 动作名 (idle/walk/attack/evolve)
     * @returns {{ frames: number, fps: number, loop: boolean }}
     */
    function getActionConfig(name, action) {
        const cfg = getSpriteConfig(name);
        return cfg.actions[action] || cfg.actions.idle || { frames: 1, fps: 1, loop: true };
    }

    return { getSpriteConfig, getActionConfig, DEFAULT };
})();
