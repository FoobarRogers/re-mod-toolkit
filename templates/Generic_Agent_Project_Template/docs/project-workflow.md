# Project Workflow

> 由首次建项的 GLM / Main Agent 基于真实仓库、现有文档、工具、产物和用户要求填充。不要凭模板想象不存在的流程。

## 1. Goal & Product Boundary

- 项目解决什么问题：
- 正式交付物：
- 明确不在默认范围的技术路线 / 资产 / 服务：
- 用户数据 / 外部环境不可被自动修改的边界：

## 2. Baseline & Sources of Truth

- 已验收 baseline：
- 源码 / 资源 / schema / API 的权威来源：
- 项目事实索引：
- 原始 evidence 位置：
- 哪些资料只作为历史线索，不可直接当当前事实：

## 3. Project Layout & Tools

- 关键目录：
- 构建 / 解析 / 验证工具：
- 临时工作区与不得提交内容：
- 外部环境 / 连接器 / CI：

## 4. Domain Workflow

按本项目实际工作拆阶段。例如：输入确认 → 调查 → candidate → validation → handoff。

每个阶段只写：输入、最高价值证据、允许的修改、进入下一阶段的 Gate。

## 5. Diagnostic Routing

把**领域特有的症状 → 证据层 / 资源层 / 模块**写在这里；不要复制通用 Failure Brake。

| 症状 / 任务 | 先检查 | 关键 discriminator | 证据位置 |
| --- | --- | --- | --- |
|  |  |  |  |

## 6. Validation Matrix

区分 offline / runtime / user acceptance。每个测试说明 oracle 真正证明什么，以及不能证明什么。

| 目标 | Baseline | Candidate | 判据 | Validation level |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

## 7. Packaging / Deployment / Release

- candidate 命名：
- 包结构：
- 部署 / 刷新 / 回退：
- CI / release gate：
- 禁止夹带内容：

## 8. Evidence Persistence

指定本项目如何保存：

- 长期事实；
- 每轮 adaptation / investigation；
- 原始大日志 / dump / 二进制证据；
- handoff。

不要让 compact summary 成为唯一证据库。

## 9. Project-specific Anti-patterns

只记录已经有证据证明“会浪费时间 / 导致错误”的项目特有路线；通用规则留在 Discipline。
