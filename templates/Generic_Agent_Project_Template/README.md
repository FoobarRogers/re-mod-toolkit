# Generic Agent Project Template

用于非 REFramework / RE Engine 项目的通用 Agent 项目骨架，随 `re-mod-toolkit` 插件分发。

## 依赖

本模板使用的 Discipline 注入 hook、复审 Agent（`glm-review` / `deepseek-review`）与手动
Command 由 `re-mod-toolkit` 插件提供。使用前先安装并启用该插件，安装方式见插件仓库
README（https://github.com/FoobarRogers/re-mod-toolkit）。

## 建项方式

1. 复制本目录为新的项目根目录（也可以在装有插件的环境里用 `/new-mod-project` 让 Agent 引导建项）。
2. 让 Agent 先只读真实项目：仓库结构、README、现有 workflow、构建 / 测试入口、历史 candidate 与用户约束。
3. Agent 填充根目录 `AGENTS.md` 的**项目身份、硬门禁、资料路由**（`<PROJECT>` 等占位符全部落地）。
4. 详细领域方法、诊断路由、验证矩阵、打包 / 发布规则拆入 `docs/project-workflow.md`，不要继续塞进 AGENTS。
5. 若项目存在高价值长期事实，按领域创建事实索引，例如 `native-map.md`、`slot-map.md`、`api-notes.md`、`schema.md`；不要强制所有项目用同一文件名。
6. 项目需要增加规则时优先写 project workflow，而不是复制 / 改写 Discipline。Discipline 全文由插件 SessionStart hook 按模型注入，项目与模板均**不放**副本，本模板 docs/ 内没有该文件；需要原文时读已安装插件目录 `hooks/discipline-router/` 下的对应文件。

## Review

DeepSeek 和 GLM 都可以做 Main Agent。自动复审统一读取 `docs/review-protocol.md`：DeepSeek Main 使用 `re-mod-toolkit:glm-review`，GLM Main 使用 `re-mod-toolkit:deepseek-review`；Reviewer 不递归调用 Reviewer。
