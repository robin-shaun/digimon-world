# digimon-world Hour-Push 任务 (2026-07-07 22:00 派发)

## 上下文
- 仓库: ~/projects/digimon-world (当前 commit b2fad0d)
- Phase 0 + Phase 1 已闭环(8/8 + 8/8)。Phase 2 是当前阶段。
- 部署: https://digimon-world.robin-shaun.workers.dev/ 跑通
- 主 API key (sk-Vz5QSw3POWmZXjbiOlRW8ExRS2kmz9Y9N8kTTqu05TQsdcDo) 已确认能跑通(probe haiku 返回正常)
- 备用 key: 等用户今晚 22:00 问完再说

## 本次推送目标
推进 Phase 2 第一项:**MemoryStream 写入 + 重要性评分 + 检索**

按 ROADMAP Phase 2 顺序做:
1. 先实现 `MemoryStream` (写入、重要性评分、检索)
2. 写对应单元测试
3. pytest 全过
4. 跑通后 commit,推 Gitee
5. 如果额度用尽(429 3 次)→ 报告并停下,不要切备用 key,等下次 cron 决定

## 工作风格
- 先看 backend/src/digimon_world/memory/ 现有结构, 再写
- 复用 Phase 1 的 `WorldState` 单例思路
- 每个文件不超过 200 行
- 中文注释、英文代码
- 不破坏现有 25 个测试

## 时间预算
4 小时内必须停(无论完没完成),让位给明天的 cron
