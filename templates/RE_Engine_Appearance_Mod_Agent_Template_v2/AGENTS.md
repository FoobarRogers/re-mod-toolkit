# 项目约定：RE Engine 外观 Mod

## 1. 项目身份与基线

- 本项目可能包含 mesh、bone、MDF、texture、PFB、动画资源以及可选 REFramework Lua。
- 修改前明确：游戏 / 资源版本、已实机验收 baseline、目标角色 / 装备 ID、加载器组合与实际生效路径。
- LuaBone 与 Armor Variant Manager 都是可选系统；只有项目实际使用且证据指向相应层级时才读取其专项资料。

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

## 3. 资源与授权硬门禁

- 资源路径、文件名、目录层级和版本后缀属于加载契约，不因整理目录随意修改。
- `.mesh.*`、`.mdf2.*`、`.pfb.*`、`.motlist.*` 等二进制资源只能通过已验证工具修改；保留来源、参数、可回退 baseline，必要时记录 SHA256。
- 多资源层同时变化时，只有构成不可分割引用链才一起修改，并明确说明依赖关系；否则按最小实验拆分。
- Mod Manager 部署和游戏内实测由用户手工完成；不得直接操作用户游戏目录。
- 普通 `test` / `fix` 只授权工作区修改、验证和测试包；`/promote-main`、`/release` 或同等明确指令分别授权晋升与正式发布。
- 工程决策、Failure Brake、Action Closure 与证据落盘遵守 SessionStart hook 注入的全局 DeepSeek Discipline，本文件不重复其阈值。

## 4. Agent / Review 路由

- 本节 Review Agent / Command、§5 的 Skills 与 Discipline hook 均由 `re-mod-toolkit` 插件提供；使用本模板建项前需先安装并启用该插件（安装方式见插件仓库 README）。
- DeepSeek 作为 Main Agent 时，遵守 SessionStart hook 注入的全局 DeepSeek Discipline 与 DeepSeek Role（hook 按模型一并注入，无需自主读取）。
- **DeepSeek Role 仅适用于 DeepSeek Main Agent。**
- GLM / Zhipu 作为 Main Agent 时，不得读取、继承、模拟或应用 `deepseek-role.md` 中的角色设定；按本项目通用规则和当前任务直接工作。
- DeepSeek 作为 Review Agent 或其它只读子 Agent 时，不应用 DeepSeek Main Agent Role；仅遵守对应子 Agent / Review 提示词。
- 任何 Main Agent 发起独立复审前，先读取 `docs/review-protocol.md`，按固定 ReviewPacket 契约提交；不得改写成开放式调查、修复或递归复审任务。
- DeepSeek 为 Main Agent → Review Agent 使用 `re-mod-toolkit:glm-review`。
- GLM 为 Main Agent → Review Agent 使用 `re-mod-toolkit:deepseek-review`。
- Review Agent 不得再次调用 Review Agent；复审完成后控制权返回原 Main Agent，由原 Main Agent 裁决。


## 5. Skill 路由

| 任务 | 必用 Skill |
| --- | --- |
| mesh、骨骼、权重、物理、材质、贴图、PFB、路径、加载器或缓存 | `$reengine-asset-diagnosis` |
| REFramework Lua、autorun 探针 / 播放器、部署边界 | `$reframework-lua-development` |
| REFramework 平台 API | `$reframework-api-reference` |
| 游戏运行日志、hook 未命中、重复报错 | `$mod-debugging` |
| 截图、录屏、动画与姿态验收 | `$mod-visual-validation` |
| test / fix / main / release / add-on 状态 | `$mod-version-workflow` |
| 增量包、完整包、Release 包、add-on | `$mod-package` |
| 改 Skill 本身 | `$skill-creator`（仅改 Skill 时） |

## 6. 项目资料路由

- 项目领域执行、candidate 与打包细节：`docs/project-workflow.md`。
- 会话开始自检：先读 `docs/session-handoff.md` 再开始工作（一次性小任务可跳过；任务依赖既有进度时必须先读）。
- Discipline 与 Role 注入：由 `re-mod-toolkit` 插件的 SessionStart hook 按当前模型自动注入对应内容（DeepSeek → `deepseek-discipline.md` + `deepseek-role.md`，GLM → `GLM-discipline.md`）；注入缺失或内容可疑时，到已安装插件目录的 `hooks/discipline-router/`（或 GitHub 仓库 `FoobarRogers/re-mod-toolkit`）读取对应文件作保底（DeepSeek 需同时补读 discipline 与 role）。
- 资源层级、症状路由、Diff、缓存 / Loader 诊断：`docs/asset-workflow.md`。
- 材质 / 贴图：`docs/material-texture.md`；PFB：`docs/pfb-workflow.md`。
- 只有证据指向运行时骨骼映射或 Transform 应用时读取 `docs/luabone-integration.md`。
- 只有项目已组件化并实际使用 AVM 时读取 `docs/avm-json.md`；修改 AVM Lua 本体属于 Lua 开发，组合预设属于项目配置，两者不得混淆。
- 大型资源清单、解析结果、日志和 JSON 按 `docs/token-discipline.md` 过滤，不完整载入主上下文。
- 项目路径、引用链、ID 映射和已验证视觉结论应进入项目事实文档，而不是长期留在 handoff。

## 7. 本地 Windows 工具链（仅 DLL / 原生编译时适用）

- **适用条件** —— 只有 mod 涉及 DLL / 原生代码编译时，才检查并使用本节工具链；纯 Lua、资源替换与动画任务跳过本节。
- **MSVC（首选）** —— Visual Studio 2022 Build Tools，CMake generator 为 `"Visual Studio 17 2022"`，架构为 `-A x64`。需要 MSVC 验证时，不得以 MinGW PASS 代替。本机缺失时建议用户安装 MSVC（安装指引见插件发布帖）。
- **LLVM-MinGW（fallback）** —— 用户不便安装 MSVC 时，可由 Agent 自动下载安装 LLVM-MinGW 并设置环境变量 `LLVM_MINGW` 指向该工具链；不得改用其他 MinGW。
- **构建隔离** —— MSVC 与 LLVM-MinGW 必须分别使用独立 build 目录与 CMake cache，例如 `build-msvc/` 与 `build-mingw/`；不得跨工具链复用已配置的构建目录。

## 8. 收尾

- 交付时说明变更层级、修改文件、加载 / 刷新方法、验证条件和回退 baseline。
- 关键事实一旦改变后续决策，按 Persistence Gate 及时写回项目事实 / evidence；handoff 只保留恢复当前工作所需摘要。
- handoff 写作纪律：只写“本次应操作 + 决策级结论”，每条 ≤2 行；过程记录与历史研究写入 `docs/history/`（append-only）或对应主题文档，不进 handoff。
- handoff 体积红线：handoff 本体 ≤10,000 字符；接近上限时收尾第一动作是整理归档。

**原则：AGENTS 只保留项目边界、资源硬门禁和路由；领域诊断与交付方法进入 docs / Skills。**
