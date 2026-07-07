/**
 * DIGIMON WORLD - 前端占位
 *
 * Phase 0: 画一个最简的世界地图(用代码生成,不用图片资源)
 * Phase 1: 接入后端,显示真实 agent 位置
 * Phase 4: 接入观察者 UI(导演面板)
 */

(function () {
    'use strict';

    console.log('🐉 Digimon World initializing...');
    console.log('   Phase 0: 项目骨架,等待后端接入');

    const canvas = document.getElementById('world-map');
    const ctx = canvas.getContext('2d');
    const W = canvas.width;
    const H = canvas.height;

    // ---- 画一张占位的「数码世界」地图 ----
    function drawWorld() {
        // 背景: 渐变天空
        const skyGrad = ctx.createLinearGradient(0, 0, 0, H);
        skyGrad.addColorStop(0, '#0a1233');
        skyGrad.addColorStop(0.6, '#1e2a5a');
        skyGrad.addColorStop(1, '#3a1a4a');
        ctx.fillStyle = skyGrad;
        ctx.fillRect(0, 0, W, H);

        // 远山轮廓
        ctx.fillStyle = '#1a1f3a';
        ctx.beginPath();
        ctx.moveTo(0, H * 0.7);
        for (let x = 0; x <= W; x += 40) {
            const y = H * 0.6 + Math.sin(x * 0.015) * 30 + Math.sin(x * 0.03) * 15;
            ctx.lineTo(x, y);
        }
        ctx.lineTo(W, H);
        ctx.lineTo(0, H);
        ctx.closePath();
        ctx.fill();

        // 无限山(中央高耸)
        ctx.fillStyle = '#2a1f4a';
        ctx.beginPath();
        ctx.moveTo(W * 0.35, H * 0.55);
        ctx.lineTo(W * 0.5, H * 0.2);
        ctx.lineTo(W * 0.65, H * 0.55);
        ctx.closePath();
        ctx.fill();
        // 山顶发光
        const peakGrad = ctx.createRadialGradient(W * 0.5, H * 0.2, 5, W * 0.5, H * 0.2, 80);
        peakGrad.addColorStop(0, 'rgba(124, 58, 237, 0.6)');
        peakGrad.addColorStop(1, 'rgba(124, 58, 237, 0)');
        ctx.fillStyle = peakGrad;
        ctx.fillRect(0, 0, W, H);

        // 文件岛(右下)
        ctx.fillStyle = '#0e3a3a';
        ctx.beginPath();
        ctx.ellipse(W * 0.78, H * 0.78, 100, 50, 0, 0, Math.PI * 2);
        ctx.fill();

        // 启程海滩(左下)
        ctx.fillStyle = '#3a3a1a';
        ctx.beginPath();
        ctx.ellipse(W * 0.18, H * 0.78, 70, 35, 0, 0, Math.PI * 2);
        ctx.fill();

        // 一些飘浮的「数据碎片」
        for (let i = 0; i < 30; i++) {
            const x = (i * 73 + 50) % W;
            const y = ((i * 41) % (H * 0.6)) + 20;
            ctx.fillStyle = `rgba(0, 212, 255, ${0.2 + (i % 5) * 0.1})`;
            ctx.fillRect(x, y, 2, 2);
        }

        // 标题
        ctx.fillStyle = 'rgba(255, 255, 255, 0.5)';
        ctx.font = '14px monospace';
        ctx.textAlign = 'center';
        ctx.fillText('— DIGITAL WORLD —', W / 2, H - 16);
    }

    // ---- 状态栏更新 ----
    function updateStatus() {
        const now = new Date();
        document.getElementById('world-time').textContent =
            '世界时间: ' + now.toLocaleTimeString('zh-CN');
    }

    // 启动
    drawWorld();
    updateStatus();
    setInterval(updateStatus, 1000);

    // 暴露一个简单 API 供后端联调
    window.DigimonWorld = {
        version: '0.1.0',
        phase: 0,
        ready: true,
    };
})();
