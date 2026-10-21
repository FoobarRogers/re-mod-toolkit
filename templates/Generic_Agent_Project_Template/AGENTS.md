# Project Agent Rules

> 通用工程项目骨架。建立具体项目时，只在本文件保留项目身份、硬门禁和路由；详细领域方法拆入 `docs/project-workflow.md` 或项目事实文档。

## 1. 项目身份

- 项目名称：`<PROJECT>`
- 技术 / 资产类型：`<LANGUAGE / PLATFORM / ASSET / SERVICE>`
- 主要源码 / 资源入口：`<PATHS>`
- 已验收 baseline：`<VERSION / COMMIT / BINARY / DATASET>`
- 明确禁止或默认不采用的技术路线：`<BOUNDARIES>`

## 2. 语言与阶段可观察性

- 本项目所有 Main Agent、Review Agent 和其它子 Agent 的用户可见输出统一使用中文。
  用户可见的分析摘要、计划、阶段进度、Review 结果、异常说明和下一步动作均使用中文。
- 代码、路径、命令、标识符、API 名称和日志原文保持原样。
- 阶段汇报避免冗长的过程性推演；优先报告可核查事实、判断依据、当前结论和下一步动作。
- 创建子 Agent 时，明确要求其最终报告使用中文。
- 长任务应保持阶段可观察性：在完成调查、准备进入修改、完成修改准备验证、
  改变主要假设、扩大修改范围、准备独立 Review 或进入发布阶段时，
  用简短中文说明当前状态和下一步。
- 不要求逐个工具调用汇报，也不要为了等待用户输入而无故暂停正常工作。
- 用户通过 harness 插入新指令或停止任务时，以最新用户指令为准。

## 3. 授权与工程门禁

- 普通 `test` / `fix` / 适配只授权工作区修改、调查、本地验证和 candidate 构建。
- 只有用户明确授权时才执行远程 push、合并 `main`、tag、Release 或其它不可逆外部动作。
- 项目特有的安全 / 数据 / 兼容 / 部署硬门禁在这里列**短规则**；方法和长流程放入 `docs/project-workflow.md`。
- 工程决策、Failure Brake、Action Closure 与证据落盘遵守 SessionStart hook 注入的全局 DeepSeek Discipline。

## 4. Agent / Review 路由

- 本节 Review Agent / Command 与 Discipline hook 由 `re-mod-toolkit` 插件提供；使用本模板建项前需先安装并启用该插件（安装方式见插件仓库 README）。
- DeepSeek 作为 Main Agent 时，遵守 SessionStart hook 注入的全局 DeepSeek Discipline 与 DeepSeek Role（hook 按模型一并注入，无需自主读取）。
- **DeepSeek Role 仅适用于 DeepSeek Main Agent。**
- GLM / Zhipu 作为 Main Agent 时，不得读取、继承、模拟或应用 `deepseek-role.md` 中的角色设定；按本项目通用规则和当前任务直接工作。
- DeepSeek 作为 Review Agent 或其它只读子 Agent 时，不应用 DeepSeek Main Agent Role；仅遵守对应子 Agent / Review 提示词。
- 任何 Main Agent 发起独立复审前，先读取 `docs/review-protocol.md`，按固定 ReviewPacket 契约提交；不得改写成开放式调查、修复或递归复审任务。
- DeepSeek 为 Main Agent → Review Agent 使用 `re-mod-toolkit:glm-review`。
- GLM 为 Main Agent → Review Agent 使用 `re-mod-toolkit:deepseek-review`。
- Review Agent 不得再次调用 Review Agent；复审完成后控制权返回原 Main Agent，由原 Main Agent 裁决。


## 5. 项目资料路由

- 当前执行流程与领域方法：`docs/project-workflow.md`。
- 会话开始自检：先读 `docs/session-handoff.md` 再开始工作（一次性小任务可跳过；任务依赖既有进度时必须先读）。
- Discipline 与 Role 注入：由 `re-mod-toolkit` 插件的 SessionStart hook 按当前模型自动注入对应内容（DeepSeek → `deepseek-discipline.md` + `deepseek-role.md`，GLM → `GLM-discipline.md`）；注入缺失或内容可疑时，到已安装插件目录的 `hooks/discipline-router/`（或 GitHub 仓库 `FoobarRogers/re-mod-toolkit`）读取对应文件作保底（DeepSeek 需同时补读 discipline 与 role）。
- 版本 / candidate / release：`docs/version-workflow.md`。
- 大数据 / 工具输出：`docs/token-discipline.md`。
- 项目长期事实索引：`<由领域决定，例如 native-map.md / slot-map.md / api-notes.md / schema.md>`。
- 项目专项文档只在当前任务需要时读取，不全量加载整个 docs 目录。

## 6. 本地 Windows 工具链（仅 DLL / 原生编译时适用）

- **适用条件** —— 只有 mod 涉及 DLL / 原生代码编译时，才检查并使用本节工具链；纯 Lua、资源替换与动画任务跳过本节。
- **MSVC（首选）** —— Visual Studio 2022 Build Tools，CMake generator 为 `"Visual Studio 17 2022"`，架构为 `-A x64`。需要 MSVC 验证时，不得以 MinGW PASS 代替。本机缺失时建议用户安装 MSVC（安装指引见插件发布帖）。
- **LLVM-MinGW（fallback）** —— 用户不便安装 MSVC 时，可由 Agent 自动下载安装 LLVM-MinGW 并设置环境变量 `LLVM_MINGW` 指向该工具链；不得改用其他 MinGW。
- **构建隔离** —— MSVC 与 LLVM-MinGW 必须分别使用独立 build 目录与 CMake cache，例如 `build-msvc/` 与 `build-mingw/`；不得跨工具链复用已配置的构建目录。

## 7. 收尾

- 完成用户要求范围内的实现与必要验证，不因存在可选优化而停在半成品。
- Decision-changing evidence 按全局 DeepSeek Discipline 的 Persistence Gate 及时写入事实索引 / evidence；handoff 只保存恢复当前工作的短摘要。
- handoff 写作纪律：只写“本次应操作 + 决策级结论”，每条 ≤2 行；过程记录与历史研究写入 `docs/history/`（append-only）或对应主题文档，不进 handoff。
- handoff 体积红线：handoff 本体 ≤10,000 字符；接近上限时收尾第一动作是整理归档。

**原则：AGENTS 只保留身份、硬门禁和路由；领域流程、诊断、测试矩阵与项目事实进入 docs。**
