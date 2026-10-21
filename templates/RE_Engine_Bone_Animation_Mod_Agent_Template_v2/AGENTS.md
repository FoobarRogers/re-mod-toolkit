# 项目约定：RE Engine 骨骼动画 Mod

## 1. 项目身份与基线

- 本项目以 MOT / MOTLIST 骨骼动画资产为主（替换、重建、烘焙、过渡重接），可辅以 REFramework Lua 探针 / 播放器。
- 动手前明确：游戏 / 版本、目标 motlist 与覆盖关系、已实机验收 baseline、Loader 组合与生效路径。
- 项目实机验证过的速度档、循环族、过渡链和骨骼承载语义优先于通用经验与旧教程。
- 不引入 mesh、材质、PFB 等非动画原生资源修改，除非用户明确改变技术路线。

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
  
## 3. 动画与授权硬门禁

- MOT 二进制只能通过已验证工具修改；保留来源、参数和可回退 baseline，记录 SHA256。
- 同一根骨的所有曲线必须采用一致策略；键数 / 布局不兼容时重建 blob，不做混合式就地修改。
- MOT 头部语义字段默认不动；位移承载（Root / 骨盆）和 IK 世界语义以项目实测事实为准。
- 覆盖同一 motlist 的包只能启用一个；Mod Manager 部署和游戏内实测由用户手工完成，脚本不得操作用户游戏 / Manager 目录。
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
| MOT / 骨骼曲线、重计时、过渡 / 循环、IK、根运动、槽位身份 | `$animation-bake-tuning` |
| REFramework Lua、autorun 探针 / 播放器、部署边界 | `$reframework-lua-development` |
| REFramework 平台 API | `$reframework-api-reference` |
| 游戏运行日志、hook 未命中、重复报错 | `$mod-debugging` |
| 截图、录屏、动画与姿态验收 | `$mod-visual-validation` |
| test / fix / main / release / add-on 状态 | `$mod-version-workflow` |
| 增量包、完整包、Release 包、add-on | `$mod-package` |
| 改 Skill 本身 | `$skill-creator`（仅改 Skill 时） |

## 6. 项目资料路由

- 项目领域执行、candidate 与打包细节：`docs/project-workflow.md`。
- `docs/animation-pipeline.md`：MOT/MOTLIST 结构、修改方式、烘焙、验收与运行时症状路由。
- `docs/slot-map.md`：动作 / 槽位画像与复现命令，是动画事实索引；定案后优先更新这里或项目的 `established-conclusions.md`。
- `docs/project-layout.md`：项目实际使用的 provider / tools / patch / release 布局；不同项目可修改。
- 大型 motlist、dump、探针 JSON、逐帧数据与日志按 `docs/token-discipline.md` 过滤。
- 会话开始自检：先读 `docs/session-handoff.md` 再开始工作（一次性小任务可跳过；任务依赖既有进度时必须先读）。
- Discipline 与 Role 注入：由 `re-mod-toolkit` 插件的 SessionStart hook 按当前模型自动注入对应内容（DeepSeek → `deepseek-discipline.md` + `deepseek-role.md`，GLM → `GLM-discipline.md`）；注入缺失或内容可疑时，到已安装插件目录的 `hooks/discipline-router/`（或 GitHub 仓库 `FoobarRogers/re-mod-toolkit`）读取对应文件作保底（DeepSeek 需同时补读 discipline 与 role）。

## 7. 本地 Windows 工具链（仅 DLL / 原生编译时适用）

- **适用条件** —— 只有 mod 涉及 DLL / 原生代码编译时，才检查并使用本节工具链；纯 Lua、资源替换与动画任务跳过本节。
- **MSVC（首选）** —— Visual Studio 2022 Build Tools，CMake generator 为 `"Visual Studio 17 2022"`，架构为 `-A x64`。需要 MSVC 验证时，不得以 MinGW PASS 代替。本机缺失时建议用户安装 MSVC（安装指引见插件发布帖）。
- **LLVM-MinGW（fallback）** —— 用户不便安装 MSVC 时，可由 Agent 自动下载安装 LLVM-MinGW 并设置环境变量 `LLVM_MINGW` 指向该工具链；不得改用其他 MinGW。
- **构建隔离** —— MSVC 与 LLVM-MinGW 必须分别使用独立 build 目录与 CMake cache，例如 `build-msvc/` 与 `build-mingw/`；不得跨工具链复用已配置的构建目录。

## 8. 收尾

- 交付时说明变更槽位、修改文件、离线 / 实机验证方式和回退 baseline。
- 关键槽位事实、失败反证和运行时读数按 Persistence Gate 及时写入事实索引 / evidence；handoff 只保留恢复当前工作所需摘要。
- handoff 写作纪律：只写“本次应操作 + 决策级结论”，每条 ≤2 行；过程记录与历史研究写入 `docs/history/`（append-only）或对应主题文档，不进 handoff。
- handoff 体积红线：handoff 本体 ≤10,000 字符；接近上限时收尾第一动作是整理归档。

**原则：AGENTS 只保留项目边界、动画硬门禁和路由；烘焙、诊断与交付方法进入 docs / Skills。**
