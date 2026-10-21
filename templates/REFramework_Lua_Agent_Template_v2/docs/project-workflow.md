# REFramework Lua Project Workflow

> 通用授权与 candidate 状态遵守 `version-workflow.md`；本文件只保存 Lua 项目的领域流程与验收要求。

## 1. Baseline

开工确认：游戏版本、REFramework stable/nightly 基线、主 Lua、配置路径、日志路径、已验收 candidate，以及已验证 API / 对象链事实。

## 2. Change Type

- `test`：未验证 Hook、新 API 路线、较大结构调整或兼容性试验；允许失败，但必须保留可复用结论。
- `fix`：根因已有证据、改动范围明确、存在直接验证 oracle 的 bugfix。
- 新功能：独立 feature / candidate；不要顺带重构无关模块。

每个 candidate 至少记录 baseline、changed files、机制、测试步骤、预期结果、实际 validation level 和回退方式。

## 3. Runtime Validation

按项目实际功能选最小覆盖，但发布前至少考虑：

- Lua 语法 / 加载无错误；
- REFramework 正常启动；
- Reset Script 不重复注册 Hook 或叠加状态；
- 标题 → 读档 → 据点 / 任务 → 切图 → 返回等会触发对象重建的路径；
- 配置旧版可读取，或有明确迁移 / 安全回退；
- 高频日志默认不过量；
- UI / 版本显示与项目要求一致。

诊断路由、日志与生命周期见 `runtime-and-hooks.md`。

## 4. Packaging / Release

项目若已有打包脚本，以脚本和实际安装结构为准。正式包只包含运行所需 Lua / 配置模板 / 说明，不夹带 tmp、原始 dump、调试 evidence 或本地测试桩。

失败 test 不覆盖或伪装成新 baseline；把真正改变后续决策的反证写入项目事实 / evidence，并在 handoff 中只保留指针。
