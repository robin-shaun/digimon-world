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
     * key: 数码兽物种名 (英语, 如 agumon / gabumon)
     * value: { actions: { actionName: { frames: number, fps: number, loop: bool } } }
     */
    const configs = {
        // ═══ 疫苗种 (Vaccine) — 8 只被选召的数码兽 ═══
        agumon: {
            color: '#FF8C00',    // 橙色 — 勇气
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
            color: '#4A90D9',    // 蓝色 — 友情
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
            color: '#FF69B4',    // 粉色 — 爱心
            accent: '#FFB6C1',
            size: 16,
            actions: {
                idle:    { frames: 4, fps: 3,  loop: true },
                walk:    { frames: 6, fps: 8,  loop: true },
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },
        tentomon: {
            color: '#8B4513',    // 棕色 — 知识
            accent: '#D2691E',
            size: 16,
            actions: {
                idle:    { frames: 4, fps: 3,  loop: true },
                walk:    { frames: 6, fps: 8,  loop: true },
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },
        palmon: {
            color: '#32CD32',    // 绿色 — 纯真
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
            color: '#FFFFFF',    // 白色 — 诚实
            accent: '#E0E0FF',
            size: 17,
            actions: {
                idle:    { frames: 4, fps: 3,  loop: true },
                walk:    { frames: 6, fps: 8,  loop: true },
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },
        patamon: {
            color: '#FFDAB9',    // 浅橙 — 希望
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
            color: '#F5F5DC',    // 米色 — 光明
            accent: '#FFE4E1',
            size: 16,
            actions: {
                idle:    { frames: 4, fps: 3,  loop: true },
                walk:    { frames: 6, fps: 8,  loop: true },
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },

        // ═══ 疫苗种 — 其他 ═══
        plotmon: {
            color: '#FFE4C4',    // 奶油色 — 小狗兽
            accent: '#FFDEAD',
            size: 15,
            actions: {
                idle:    { frames: 4, fps: 3,  loop: true },
                walk:    { frames: 6, fps: 8,  loop: true },
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },
        elecmon: {
            color: '#00BFFF',    // 电蓝色 — 艾力兽
            accent: '#FFD700',   // 金色闪电
            size: 16,
            actions: {
                idle:    { frames: 4, fps: 3,  loop: true },
                walk:    { frames: 6, fps: 9,  loop: true },  // 电力充沛, 移动快
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },
        tsunomon: {
            color: '#E6E6FA',    // 薰衣草白 — 独角兽
            accent: '#DDA0DD',
            size: 15,
            actions: {
                idle:    { frames: 4, fps: 3,  loop: true },
                walk:    { frames: 6, fps: 7,  loop: true },
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },

        // ═══ 数据种 (Data) ═══
        hagurumon: {
            color: '#C0C0C0',    // 银色 — 齿轮兽
            accent: '#708090',
            size: 14,
            actions: {
                idle:    { frames: 4, fps: 3,  loop: true },
                walk:    { frames: 6, fps: 6,  loop: true },  // 齿轮滚动
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },
        guardromon: {
            color: '#4682B4',    // 钢蓝 — 守卫兽
            accent: '#B0C4DE',
            size: 20,
            actions: {
                idle:    { frames: 4, fps: 2,  loop: true },  // 机械感, 慢节奏
                walk:    { frames: 6, fps: 6,  loop: true },
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },
        clockmon: {
            color: '#8B7355',    // 古铜色 — 时钟兽
            accent: '#DAA520',
            size: 18,
            actions: {
                idle:    { frames: 4, fps: 2,  loop: true },
                walk:    { frames: 6, fps: 5,  loop: true },  // 时间齿轮慢转
                attack:  { frames: 5, fps: 10, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },
        tankmon: {
            color: '#556B2F',    // 军绿 — 坦克兽
            accent: '#8B8B00',
            size: 20,
            actions: {
                idle:    { frames: 4, fps: 2,  loop: true },
                walk:    { frames: 6, fps: 6,  loop: true },
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },
        kokuwamon: {
            color: '#87CEEB',    // 天蓝 — 溜溜球兽
            accent: '#00CED1',
            size: 15,
            actions: {
                idle:    { frames: 4, fps: 3,  loop: true },
                walk:    { frames: 6, fps: 8,  loop: true },
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },
        andromon: {
            color: '#4169E1',    // 皇家蓝 — 安杜路兽
            accent: '#1E90FF',
            size: 22,
            actions: {
                idle:    { frames: 4, fps: 2,  loop: true },  // 完全体, 稳重
                walk:    { frames: 6, fps: 5,  loop: true },
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },

        // ═══ 病毒种 (Virus) ═══
        picodevimon: {
            color: '#4B0082',    // 靛蓝 — 小恶魔兽
            accent: '#8B008B',
            size: 13,
            actions: {
                idle:    { frames: 4, fps: 4,  loop: true },  // 活泼好动
                walk:    { frames: 6, fps: 9,  loop: true },
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },
        blackgabumon: {
            color: '#2F4F4F',    // 暗灰蓝 — 黑加布兽
            accent: '#A9A9A9',
            size: 18,
            actions: {
                idle:    { frames: 4, fps: 3,  loop: true },
                walk:    { frames: 6, fps: 8,  loop: true },
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },
        devimon: {
            color: '#191970',    // 午夜蓝 — 恶魔兽 (成熟期)
            accent: '#DC143C',   // 血红 accent
            size: 24,
            actions: {
                idle:    { frames: 4, fps: 2,  loop: true },
                walk:    { frames: 6, fps: 5,  loop: true },
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },
        devidramon: {
            color: '#800020',    // 酒红 — 邪龙兽
            accent: '#FF4500',
            size: 22,
            actions: {
                idle:    { frames: 4, fps: 2,  loop: true },
                walk:    { frames: 6, fps: 5,  loop: true },
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },
        vamdemon: {
            color: '#2C003E',    // 深紫 — 吸血魔兽 (完全体)
            accent: '#8B0000',
            size: 26,
            actions: {
                idle:    { frames: 4, fps: 2,  loop: true },
                walk:    { frames: 6, fps: 4,  loop: true },
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },
        fantomon: {
            color: '#483D8B',    // 暗灰紫 — 死神兽
            accent: '#9370DB',
            size: 20,
            actions: {
                idle:    { frames: 4, fps: 2,  loop: true },
                walk:    { frames: 6, fps: 6,  loop: true },
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },
        bakemon: {
            color: '#A9A9A9',    // 暗灰 — 猛鬼兽
            accent: '#D3D3D3',
            size: 17,
            actions: {
                idle:    { frames: 4, fps: 3,  loop: true },
                walk:    { frames: 6, fps: 7,  loop: true },  // 飘浮感
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },

        // ═══ 自由种 (Free) ═══
        renamon: {
            color: '#FFD700',    // 金色 — 妖狐兽
            accent: '#FFA500',
            size: 18,
            actions: {
                idle:    { frames: 4, fps: 3,  loop: true },
                walk:    { frames: 6, fps: 9,  loop: true },  // 忍者般敏捷
                attack:  { frames: 5, fps: 14, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },
        impmon: {
            color: '#800080',    // 紫色 — 小妖兽
            accent: '#FF6347',
            size: 16,
            actions: {
                idle:    { frames: 4, fps: 4,  loop: true },  // 顽皮活跃
                walk:    { frames: 6, fps: 9,  loop: true },
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },
        dorumon: {
            color: '#5B9BD5',    // 天蓝 — 多路兽 (与守卫兽区分)
            accent: '#87CEFA',
            size: 17,
            actions: {
                idle:    { frames: 4, fps: 3,  loop: true },
                walk:    { frames: 6, fps: 8,  loop: true },
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },
        wizarmon: {
            color: '#6A0DAD',    // 深紫 — 巫师兽
            accent: '#00CED1',   // 魔法青色
            size: 20,
            actions: {
                idle:    { frames: 4, fps: 2,  loop: true },
                walk:    { frames: 6, fps: 6,  loop: true },
                attack:  { frames: 5, fps: 12, loop: false },
                evolve:  { frames: 8, fps: 6,  loop: false },
            },
        },
        leomon: {
            color: '#DAA520',    // 金褐色 — 狮子兽 (成熟期)
            accent: '#FF8C00',
            size: 24,
            actions: {
                idle:    { frames: 4, fps: 2,  loop: true },
                walk:    { frames: 6, fps: 6,  loop: true },
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
     * @param {string} name 数码兽物种名 (英语, 如 'agumon')
     * @returns {object} 精灵配置 { color, accent, size, actions }
     */
    function getSpriteConfig(name) {
        const key = (name || '').toLowerCase().replace(/[\s-]/g, '_');
        return configs[key] || DEFAULT;
    }

    /**
     * 获取指定动作的动画参数
     * @param {string} name 数码兽物种名
     * @param {string} action 动作名 (idle/walk/attack/evolve)
     * @returns {{ frames: number, fps: number, loop: boolean }}
     */
    function getActionConfig(name, action) {
        const cfg = getSpriteConfig(name);
        return cfg.actions[action] || cfg.actions.idle || { frames: 1, fps: 1, loop: true };
    }

    return { getSpriteConfig, getActionConfig, DEFAULT };
})();
