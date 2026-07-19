# Phase 27: 动画级别视觉升级 — 原著动画片品质

> **For Hermes:** 用 delegate_task goal 模式逐 Task 实现。每个 Task 完成后 commit+push+验证。

**Goal:** 将数码宝贝世界视觉从"H5轻量页游"升级到"数码宝贝大冒险01 动画级别"品质

**Architecture:** 
- 精灵图引擎从 16×16×3px(48px) 升级到 32×32×4px(128px)，新增动画帧系统（idle/walk/attack）
- 世界渲染重构：Canvas 分层（背景层→地形层→精灵层→特效层→UI层）
- 新增后处理：柔光、色温、天气粒子升级
- 主角8只 + 代表性数码兽重绘，其余保持兼容

**Tech Stack:** Canvas 2D API, pixel art pipeline (sprites.js), procedural terrain

---

## 当前状态 vs 目标

| 维度 | 当前 | 目标 |
|------|------|------|
| 精灵尺寸 | 48×48 (16×16 grid, 3px cell) | 128×128 (32×32 grid, 4px cell) |
| 颜色槽 | 10 色 | 16 色 + outline |
| 动画帧 | 1帧(静态) | 3态(idle 2帧 / walk 2帧 / attack 1帧) |
| 世界渲染 | 单一Canvas，简单色块 | 5层Composite: 天空→地形→精灵→特效→UI |
| 特效 | 雨滴粒子 | 雨滴+花瓣+光晕+战斗火花 |
| 后处理 | 无 | 柔光混合 + 昼夜色温 |

---

## Task 1: 精灵引擎升级 (128×128 核心)

**目标:** 升级像素精灵图渲染管线，支持 32×32 网格、16 色、动画帧、轮廓线

**实现:**

### 1.1 网格从 16×16 → 32×32
```javascript
// sprites.js 中
const CELL = 4;          // px per cell (曾 3)
const GRID = 32;         // grid size (曾 16)
const SPRITE_SIZE = 128; // GRID × CELL = 128
```

### 1.2 颜色槽从 10 → 16
```
0=透明  1=主体色  2=副色  3=高光1  4=阴影1  5=轮廓
6=眼白  7=瞳孔    8=特征1 9=特征2 10=特征3 11=高光2
12=阴影2 13=皮肤  14=衣物1 15=衣物2
```

### 1.3 新增轮廓线渲染
精灵图生成后，在边缘画 1-2px 黑色轮廓（cel-shading 风格）:
```javascript
function addOutline(canvas) {
    const ctx = canvas.getContext('2d');
    const imgData = ctx.getImageData(0, 0, 128, 128);
    // 检测非透明像素边缘 → 黑色描边
    // outline pass: 对每个透明像素检查相邻8方向是否有非透明
}
```

### 1.4 动画帧支持
精灵定义从单 grid 变为 `{idle: [grid, grid2], walk: [grid, grid2], attack: [grid]}`:
```javascript
const SPRITES = {
    agumon: {
        colors: [...],  // 16色
        frames: {
            idle: [grid1, grid2],   // 呼吸动画(2帧交替)
            walk: [grid3, grid4],   // 走路(2帧循环)
            attack: [grid5],        // 攻击(1帧定格)
        }
    }
};
```

### 1.5 向后兼容
- 旧的 48×48 精灵定义保持不变，新增 `_PREMIUM` 后缀的高清版
- `getSprite(species)` → 自动检测是否有 128×128 版本
- 没有高清版的 fallback 到 48px → 放大到 128×128 渲染（像素放大）

**文件:** `frontend/sprites.js`

---

## Task 2: 主角8只高精度重绘

**目标:** 用 32×32 网格 + 16 色调色板，重绘动画风格数码兽

### 2.1 选角 (8只核心)
亚古兽 Agumon、加布兽 Gabumon、比丘兽 Piyomon、巴鲁兽 Palmon、
甲虫兽 Tentomon、哥玛兽 Gomamon、巴达兽 Patamon、迪路兽 Tailmon

### 2.2 美术标准
- **轮廓线**: 1-2px 黑色边缘 (cel-shading)
- **光影**: 至少3层明暗 (high/mid/shadow)
- **眼睛**: 日式动画大眼风格 (3×4 格区域, 渐变瞳孔)
- **比例**: 头身比 1:2 (Q版动画风格)
- **pose**: 每个物种独特站立姿势，而非统一 T-pose

### 2.3 动画帧
每只2帧 idle (呼吸起伏): 主体上下 ±1px + 眼睛 blink
每只2帧 walk: 腿交替 + 手臂摆动

### 2.4 示例: 亚古兽 Agumon 128×128
```
32×32 网格定义（每字符 = 颜色索引 0-F）:
- 头部直径 ~12格(48px) — 比48版大一倍
- 黄色主体(#FF8C00) + 浅黄腹部(#FFD700) + 绿色眼睛
- 尖角 ~6格高, 尾 ~10格长
- idle帧2: 身体上移1格, 眼睛半闭
- walk帧1: 右腿前, walk帧2: 左腿前
```

**文件:** `frontend/sprites.js`

---

## Task 3: 世界渲染重构 (分层Canvas)

**目标:** 世界背景从单一Canvas改为5层复合渲染，提升画面层次感

### 3.1 Canvas 分层架构
```html
<!-- index.html -->
<div id="world-container">
  <canvas id="layer-sky"></canvas>      <!-- 天空渐变 + 星星/云 -->
  <canvas id="layer-terrain"></canvas>  <!-- 地形: 海/大陆/山/岛 -->
  <canvas id="layer-sprites"></canvas>  <!-- 数码兽精灵图 -->
  <canvas id="layer-effects"></canvas>  <!-- 粒子特效: 天气/战斗 -->
  <canvas id="layer-ui"></canvas>       <!-- 名字标签/对话气泡 -->
</div>
```

### 3.2 地形纹理增强
- **海洋**: 多层蓝色渐变 + 波浪纹理(canvas pattern) + 阳光反射
- **大陆**: 草地纹理(随机绿色噪点) + 道路/河流线条
- **山地**: 岩石纹理 + 雪顶渐变
- **森林**: 树冠圆点集群 + 树干

### 3.3 实现
```javascript
// 地形预渲染(缓存到 offscreen canvas, 只在 zoom/pan 变化时重绘)
function renderTerrain(offscreenCtx) {
    // 海: 径向渐变 深海(#0a2a4a) → 浅海(#1a5a8a)
    // 波动画: sin() 偏移扰动
    // 大陆: fillStyle pattern (草地纹理)
    // 山: 三角 + gradient + 雪顶
    // 文件岛: bezierCurve 曲线岛 + 沙滩环 + 棕榈树
}
```

**文件:** `frontend/main.js`, `frontend/index.html`, `frontend/style.css`

---

## Task 4: 特效系统升级

**目标:** 新增动画级粒子特效

### 4.1 天气粒子升级
- **雨**: 斜线雨滴(更密), 落地 splash 圆圈
- **雪**: 飘落雪花(随机大小/速度/摇摆)
- **花瓣**: 樱花瓣(粉色椭圆形, 旋转下落)
- **雾**: 半透明白色 overlay + 飘动

### 4.2 战斗特效
- **火花**: 攻击命中时橙色闪烁粒子 burst
- **冲击波**: 环形扩散 (透明度衰减)

### 4.3 环境特效
- **水面波纹**: sin() 驱动, 阳光下闪烁
- **萤火虫**: 夜间随机出现黄色光点
- **进化光柱**: 进化时垂直光束 + 粒子螺旋上升

```javascript
// effects.js (新文件)
window.Effects = {
    particles: [],  // {x, y, vx, vy, life, type, color}
    
    update(dt) {
        for (let p of this.particles) {
            p.life -= dt;
            p.x += p.vx * dt;
            p.y += p.vy * dt;
        }
        this.particles = this.particles.filter(p => p.life > 0);
    },
    
    spawn(x, y, type) { /* burst pattern per type */ },
    draw(ctx) { /* render all active particles */ },
};
```

**文件:** `frontend/effects.js` (新), `frontend/main.js`

---

## Task 5: 后处理 + UI 美化

**目标:** 画面后处理 + UI 动画片风格

### 5.1 柔光混合
渲染完成后，在顶部叠加一层径向渐变(中心透明→边缘暗角):
```javascript
function applyVignette(ctx, w, h) {
    const grad = ctx.createRadialGradient(w/2, h/2, w*0.3, w/2, h/2, w*0.7);
    grad.addColorStop(0, 'rgba(0,0,0,0)');
    grad.addColorStop(1, 'rgba(0,0,0,0.15)');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, w, h);
}
```

### 5.2 昼夜色温
- 白天 (06-18): 暖色调 (+10% 黄色)
- 黄昏 (18-20): 橙色调 overlay
- 夜晚 (20-06): 蓝色调 + 星星增强

### 5.3 UI 动画风
- 标题改用日文字体风格 (CSS text-shadow 模拟)
- 面板半透明毛玻璃 (backdrop-filter: blur)
- 数字跳动动画 (countUp)
- 按钮 hover 发光效果

**文件:** `frontend/main.js`, `frontend/style.css`, `frontend/index.html`

---

## Task 6: 验证 + 录屏演示

**验证清单:**
1. `browser_navigate` → 等待加载 → `browser_vision` 截图对比
2. 检查所有 100 只数码兽正常渲染（新精灵 + 旧 fallback）
3. 拖拽/缩放流畅不卡顿
4. 天气特效正常（雨/雪/花瓣）
5. 昼夜色温变化
6. `browser_console` 无报错

**录屏:** `scripts/record_webpage.py` 录制 30s 演示

---

## 风险与注意事项

| 风险 | 缓解 |
|------|------|
| 128×128 精灵重绘 8 只工作量巨大 | 分阶段: 先画2只验证 → 确认效果 → 再铺开 |
| 5层 Canvas 可能影响性能 | 地形/天空层用离屏缓存，只在 zoom/pan 变化时重绘 |
| 16 色精灵定义复杂 | 提供辅助脚本生成空白模板 |
| 旧精灵兼容 | `_PREMIUM` 后缀区分，无高清版的自动放大渲染 |

---

## 执行顺序

```
Task 1 (引擎) → Task 2 (2只样板) → 验证效果 → 肖昆确认 →
Task 2 (剩余6只) → Task 3 (世界层) → Task 4 (特效) →
Task 5 (后处理) → Task 6 (录屏汇报)
```
