# Changelog

## 0.3.12 (2026-11-14)

落盘分位规范（治"落盘及时但回读难辨"：agent 光看文件名分不清类型与归属）：

- `hooks/discipline-router/GLM-discipline.md` + `hooks/discipline-router/
  deepseek-discipline.md`：§10 增补落盘分位条款——现行主题文档留 `docs/` 根；
  已确定内容（裁决、调查结论、原始证据）进 `docs/evidence/`；传递文件（提案、
  专项交接、handoff 切片）进 `docs/history/`；发出待回复的复审材料进
  `docs/review/`（命名 `review-for-{对象}`），收到回复或已有更强结论后移入
  `docs/archive/`——review 不是已确定内容，不进 evidence 防误导；文件名
  `{类型前缀}-{中文短主题}-{YYYY-MM-DD}`（verdict/investigation/proposal/
  handover/review/evidence），ls 后无需读内容即可分辨类型与状态。
- `templates/*/AGENTS.md` ×4：项目资料路由节增补同款落盘分位条目，新项目开箱
  即用。
- 注入回归 ALL PASS（DeepSeek 9,181 / GLM 5,503 / prepend 缺失降级 7,894 字
  符，预算 20000 内）；中文文件名工具链兼容实测（ls/Read/grep/glob）。

## 0.3.11 (2026-11-09)

skill 用词增补 5 处（源自 1.3 fix3→fix4 取证线开发提案，经 GPT 复审裁决修订与
deepseek-review SUPPORTED 定稿）+ GLM 派单语义定稿：

- `skills/reframework-lua-development/SKILL.md`：Verify behavior 段新增窄域单
  次故障注入模式——注入 error() 只测 Lua 异常路径，并声明不重现的故障条件（原
  生对象销毁、原生部分状态损坏、重入、原生故障）；注入本体不包 pcall（否则异
  常到不了被测边界），诊断辅助单独保护；默认关闭、显式触发、交付前移除。
- `skills/mod-debugging/SKILL.md`：打点纪律细化四条（过滤后写盘、pcall 保护参
  数求值且不为补全记录回查活对象、xpcall 消息处理器在栈展开前捕获原始栈、整
  块移除标记）；新增静默崩溃四层取证模式（生命周期迹 / 首错黑匣 / framework
  log / OS 崩溃记录，按证据缺口选层）与两个归因陷阱（faulting module 不解除
  mod 嫌疑；未终止进程的异常不必然产生自动崩溃报告，无 WER 记录不证明无异常）；
  description 限定 mod-related 取证触发（465→725/1024）。
- `skills/mod-package/SKILL.md`：交付报告新增玩家反馈指引条件项（交付目标含崩
  溃证据收集或包内含诊断插桩时），导出命令仅在确需 Windows 事件记录时提供，
  路径解析用 GetFolderPath、完整字段导出防表格截断。
- `hooks/discipline-router/glm-role.md`：派单语义定稿——开头句显式"不预设任何
  默认执行通道，按 ZCode 常规判断裁量派发，派出后不由主智能体代做"；§1 worker
  条目删"默认执行通道"强推。注入回归 ALL PASS（GLM 5,327 字符 / 12,978 字节）。
- 格式量测：全部技能 desc ≤1024、body <100KB（`docs/check-skill-limits.py`）。

## 0.3.10 (2026-10-31)

GLM 侧派单模式：是否派发 subagent 按 ZCode 常规方式判断；只要派发，主智能体
就负责拆解、派单、验收与裁决（任务包 + 验收循环），不自己逐步完成；worker
走 DeepSeek 官方 API 按量计费，降低 GLM coding plan 消耗与主对话轮次。

- 新增 `agents/deepseek-worker.md`：执行型派单子智能体。显式 `model:` 绑定
  DeepSeek 官方 API（`804526c5-…/deepseek-flash`，不留继承默认），工具
  Read/Grep/Glob/Bash/Edit/Write，`injectAgentsMd: false`。正文为任务包契约
  （目标/范围/验收判据/约束/上下文）+ 回报契约：DONE/PARTIAL/BLOCKED/FAILED、
  改动文件清单、验证证据，紧凑格式、大输出落盘只回路径。
- 新增 `hooks/discipline-router/glm-role.md`（GLM Main Agent Role）：①选型
  （deepseek-worker / data-researcher / fork 型 / deepseek-review 分工；何时
  自己做；不对具体通道设默认或禁用）；②任务包五要素；③派单与验收循环——
  独立任务同轮并列派发，验收不过先区分任务包缺陷/执行缺陷/假设错误再改包
  重派，同一假设族两次失败按 Discipline §11 制动，离线自验不升级实机通过。
- `profiles/glm.json` 加 `prepend: ../glm-role.md`，GLM 注入与 DeepSeek 结构
  对称（role + discipline）；`GLM-discipline.md` 头部维护说明补记承载关系。
- 注入回归：GLM 两模型 id（startplan / 火山）与 DeepSeek id 三分支 + 无匹配
  降级 + role 缺失降级，ALL PASS（体积见 handoff；测试
  `archive/tmp/test_glm_dispatch_router.py`）。

## 0.3.9 (2026-10-30)

DeepSeek Discipline / Role 增补四项。四方法定稿链：GPT 审查包（基于视频
《如何减少 ai 的雷霆大思考和降智行为》）→ GLM Review → DeepSeek 逐条裁决 →
GLM 复审确认；评审材料见工作区
`docs/review-packet-discipline-role-verdict-2026-10-29.md` 与
`docs/glm-recheck-verdict-2026-10-29.md`。

- discipline §6 尾部加一句：局部结论的普适性未证明不构成推迟下一步动作的
  理由，§13 的提升门槛（能否写成共享规则）与当前任务能否继续解耦——针对
  实测"未证明普适就卡住不走"。
- discipline §10 工具经济段加轮次合并段：已确定且相互不依赖中间结果的操作
  在同一轮次内并列提交，不把已知独立操作拆成多轮单项 batch（实测 DeepSeek
  逐轮拆散）；原"同构批量修改可用受控脚本一次完成"移入该段，避免三段讲
  批处理。
- role §1 询问触发扩写：缺失信息会实质改变实现方向、验收标准或受保护行为
  且只有用户能裁决 → 先问，补"目标清楚但缺用户侧事实"的触发缺口。
- role §3 整合重写：区分信息型返回（保留"每个关键结论至少核对一次证据
  指针"下限）与交付物型返回（子代理直接交付，低影响可再生产物可只回路径，
  警告句条件化，离线通过不升级实机通过）；加"主对话只保留结论与证据指针，
  不复述过程全文"。
- 注入回归：DeepSeek 8,828 字符 / GLM 4,201 / prepend 缺失降级 7,541，三分支
  ALL PASS，均在 max_context_chars=20000 内（GLM 分支无变化）。

## 0.3.8 (2026-10-29)

`deepseek-role.md` 重写为 subagent 使用指南（1,694 → 1,018 字符，约 -40%），
删除与 AGENTS / Discipline 的语义重复，role 只保留“选模块、发任务、整合”。

- 开头改为身份 + 专家模块激活，删除“本文件仅供…”“本 Role 只补充…”等自指句；
  注入后不再依赖模型区分文档边界。
- §1 用 subagent：fork 型优先。写明 Explore 不继承项目指令/角色/纪律，任务包须
  写清探索什么、要什么结论、边界、证据、返回；general-purpose 继承项目 AGENTS
  但不继承主会话任务状态，任务包先写角色定位；Profile（data-researcher）按
  discipline §10 选型；状态型工作留主 agent。
- §2 任务包六项（目标/已知/范围/证据/返回/格式）；§3 整合：子 agent 返回为
  候选事实，关键结论核对证据指针，冲突不取多数。
- 删除 §2 工作方式、§4 五项不得覆盖清单、预算自算/复审路由细节、skill 路由；
  分别由 Discipline / AGENTS 承担。
- 注入回归：DeepSeek 8,294 字符、GLM 4,201、DeepSeek prepend 缺失降级 7,264，
  三分支 ALL PASS；均在 max_context_chars=20000 内。

## 0.3.7 (2026-10-28)

discipline 注入的 profile `heading` 由标题文案改为 markdown 分隔线。依据
DeepSeek 实测反馈：原标题 `## DeepSeek Implementation Discipline` 夹在 role
与 discipline 两个自带 H1 之间，层级倒挂（H2 弱于其所分隔的 H1）且与
discipline 自带标题语义重复，引起载荷归属歧义。

- `hooks/discipline-router/profiles/deepseek.json` / `glm.json`：`heading`
  统一改为 `--------------`（thematic break）。注入形态变为 role 全文（仅
  DeepSeek）→ 分隔线 → discipline 文件原样；载荷归属完全由 discipline 自带
  的 H1 标示，分隔线不声明归属。脚本与 schema 未动（`heading` 仍为
  required 字段，仅改值）。
- 行为级验证（本地三 case 全过）：DeepSeek 正常（provider 前缀剥离匹配，
  role→分隔线→discipline）、GLM 正常（分隔线→discipline）、DeepSeek
  prepend 不可读降级（分隔线→discipline）；各分隔线前均为空行，无 setext
  标题陷阱；注入体积 7.5k/4.0k/7.0k 字符，均在 max_context_chars=20000 预算内。

同批并入（同版发布，未单独 bump）：

- `hooks/discipline-router/deepseek-discipline.md` / `GLM-discipline.md`：
  §10 增补大型数据单次只读检索的子智能体分工段——文本/代码定位优先评估
  内置 Explore（fork 型轻量无写入、不注入 AGENTS.md，任务提示须自带中文
  要求与本次约束），结构化数据/自定义格式解析/需脚本侧处理或落盘产物的用
  data-researcher（有 Write）；不得要求只读 Explore 执行写入或大文件完整
  解析。依据 ZCode 子智能体 wiki 与 2026-10-28 spawn 实测装配矩阵。
- `hooks/discipline-router/deepseek-role.md`：全文重写（约 1.1KB → 3.9KB）。
  新增 §1 任务责任（RE 专业身份弱化为任务条件式——router hook 对所有装有
  本插件的工作区全局注入，非仅 RE 工作区）、§3 动态子智能体协作（适时委派
  /选型/提示词组织/独立拆分/成本控制/主 Agent 责任；委派门槛不以"复杂任务"
  为限，general-purpose 限"独立上下文+可独立验收"，Profile 防惯性默认调用；
  末段用职责式表述，不依赖子智能体派发能力等易变环境事实）、§4 与工程纪律
  的关系（防扩散条款）；原 5 项不得覆盖清单保留。GLM 侧不设对应 Role
  （AGENTS.md §4 与 GLM-discipline 头部既有约定，仅约束 DeepSeek Main
  Agent）。路由细节经 ChatGPT Review 三处修正后定稿。

## 0.3.6 (2026-10-28)

版本管理新增 **prerelease 基线固化形态**；两份 discipline 增补消耗-效果边界
条款（反 flash 级模型节能保守倾向）；依据 GPT 措辞审查（裁决表见
`docs/review-packet-version-workflow-2026-10-28.md`）修正绝对化与歧义表述。

- `hooks/discipline-router/`：deepseek-discipline 与 GLM-discipline 同步增补
  ——§8 最小以完全满足当前目的为前提（不为省消耗裁剪用户要求，认为不妥实
  现前向用户提出）、§9 最小实验缩小影响面不缩验证覆盖、§10 工具经济服从效
  果（预期消耗差距不悬殊时按预期效果选择方案，不为省 token 选已知效果更差
  的一方）。
- `skills/mod-version-workflow`：新增 prerelease（基线固化）形态——开发
  test 阶段基本完成后由用户授权冻结进 release 文件夹（命名如
  `1.11prerelease1`）并登记为工作基线，后续 fix/test 在该基线上循环，列举
  问题全部验证后由用户授权发布正式 release（`1.11`）；release 后新修复做
  fix，改动较大发下一版本；main 形态保留；description / Identify / 转移表
  / 固化确认项同步。
- `skills/mod-package`：包类型新增 `prerelease`（complete clean-installable
  文件集固化为工作基线，标签保留 prerelease 标记，不含发布授权）；
  `references/package-types.md` 补 prerelease 与 add-on 定义行及
  Prerelease packages 节。
- add-on 定位补强：明确 A/B 功能替换包语义（release 是 A 功能版，add-on
  仅含替换为 B 功能的文件，非 Lua mod 常见）；样例 `bake1.10-escape1` →
  `bake1.10-escape`（对齐 No ordinal 规则）；安装说明改为"覆盖同一批安装
  路径、add-on 替换文件优先，按实际安装方式描述回退"。
- GPT 措辞审查采纳修复：prerelease 区分"安装内容完整"与"发布验收完成"、
  固化确认项改列举式、发布验证对象明确为"列举问题的修复通过验证"；lua-dev
  侧 8 处绝对化/歧义表述改条件化（补偿逻辑改调查线索、callback cadence 与
  桥调用两处同步区分、42 示例加统计边界、profiler 覆盖改条件检查、起始骨架
  改非必选、onboarding 触发改任务级理解、description 主责划界）。
- 4 份项目模板 `version-workflow.md`：新增 §4"Prerelease 固化与基线登记"
  （原"验收与发布"顺延为 §5），状态节补 prerelease 循环说明。

## 0.3.5 (2026-10-28)

`reframework-lua-development` 增补"从零开发"与"接手他人 mod"两条路径及每帧
成本心智（依据 `lua审查开发` 项目全集合 Lua 审查与两个 fix 任务的缺口分析，
已经独立复审 SUPPORTED 并采纳 3 处最小修复）。

- `SKILL.md`：description 补"从零新建脚本 / 接手他人既有 mod 二次开发"触发
  词，排除子句限定为"必须还原运行过程才能定位的故障诊断"，澄清低开销每帧
  逻辑仍属本 skill；开头段补非平凡子系统先找项目内已验证蓝本；Verify 清单
  共存条扩展到 hook 层（hooking the same methods），新增 per-frame path 前后
  profiler 对照条（场景与绘制模式匹配、说明量化下限）；hook 摘要段补桥调用
  预算一句（与 runtime-and-hooks.md 两处同步，0.3.3 裁定）。
- 新增 `references/onboarding-existing-mod.md`：接手四问（每问需源码行背
  书）、症状补丁识别（指纹检查 / 强制重扫 / 魔数刷新窗口三类特征，剥离前先
  写正确性论证）、共享面共存按实测量级裁决而非模式匹配、优化量级门槛（收
  益低于测量噪声地板不动工，确定收益与未验证候选分列）、部署验证收尾。
- `references/runtime-and-hooks.md`：Hot paths 前新增 "Per-frame cost model"
  段——预算单位为每趟 Lua→native 桥调用次数；调用频率由游戏/框架决定、不
  可优化，单趟成本由 mod 代码决定；设计期估算、profiler 事后验证。
- `references/structure-and-delivery.md`：新增最小骨架代码块（log 加载标记 +
  json 配置 + on_frame + on_draw_ui 区块顺序；`or` 仅覆盖文件缺失，旧配置需
  按字段合并默认值）、UI 技术路线选择段（imgui 面板 vs d2d HUD；d2d 回调在
  profiler 包装之外，前后性能对照不得混绘制路径）、overlay 部署加载标记做法
  （版本标记进框架日志，先查日志再归因）。
- `references/sandbox-and-errors.md`：差异清单后补 REFramework 核心全局面
  清单（sdk / re / imgui / json / log / fs / d2d）及签名核对路由。

## 0.3.4 (2026-10-26)

`context-reminder` hook 水位提醒按主 agent 模型分档（修复 GLM 对软提醒过度紧张）。

- 背景：原 hook 模型无关，对 GLM 也在 25 万 tokens 发"接近 30 万软阈值"的
  提前量催促；30 万/50 万阈值系 DeepSeek discipline 特化条款（GLM 版
  2026-10-11 裁剪有意不含），GLM 收到引用不存在条款的"接近阈值"式催促后
  过度反应（29 万即自称"软提醒严重超限，建议更换任务"，实际硬档远未触发）。
- `context_reminder.py`：新增 `WATER_PROFILES` 按主 agent 模型分档——
  DeepSeek 维持 25 万软提醒（提前量，每 +5 万重复）+ 45 万硬警告（行为与
  文案不变）；GLM 及其它模型无提前量，仅 30 万 / 50 万到点提醒（每
  +10 万 / +2 万重复），文案为到点动作指令（落盘、提议 compact / 必须
  收束），不再引用 DeepSeek 特化段名。
- 模型取档来源：`model_usage` 主 agent（`agent='zcode-agent'`）最近一条的
  `model_id`，子 agent 模型不干扰；取不到主 agent 行时 fail-open 不发提醒。
- `GLM-discipline.md`：头部维护说明补 2026-10-26 补记——数值坎仍不写入
  GLM 正文，hook 侧以 30 万/50 万到点提醒承载。
- 重复读（R）与批量 Bash（B）检查与模型无关，行为不变；离线单测 10/10
  覆盖两档触发、去重间隔、子 agent 隔离、fail-open 与 R 保留。

## 0.3.3 (2026-10-24)

`reframework-lua-development` 统一逐帧轮询措辞（0.3.2 评审闭环）。

- `SKILL.md`：hook 摘要句改为"方法名≠语义；无已验证转移 hook 时按功能所需
  节奏选择有界轮询；区分轻量身份检查与全量发现扫描"，移除"有界逐帧 /
  广域轮询"的二元表述，避免把逐帧当成缺省节奏或误伤经 `on_frame` 推进的
  分预算发现工作。
- `references/runtime-and-hooks.md`：Hook selection 段同步展开——每帧轻量
  身份检查按需用于及时重建处理；禁止的是每帧重复全量遍历；更大范围发现须
  显式预算（增量推进或重建窗口）并保留慢速恢复路径；保留"方法名≠事件语义"句。
- 评审裁定：`player-lifecycle-and-application.md` §8 基线锚点维持原样——
  版本控制权在 `mod-version-workflow` 与项目文档，历史锚点仅作追溯。
  hook 规则增量今后须 `SKILL.md` 与 `runtime-and-hooks.md` 两处同步。

## 0.3.2 (2026-10-24)

`reframework-lua-development` 对齐主文件与参考页的逐帧检查表述。

- `SKILL.md`：hook 指导句改为"无已验证转移 hook 时，每帧有界身份检查可接受；
  广域逐帧轮询不可；不得从 open/close 方法名推断事件语义"，消除与
  `runtime-and-hooks.md` 的双写漂移（0.3.1 新增两条仅进参考页），并避免对
  实测为有界形态的既有每帧模式（DamageDisplay / autoBuff）造成误改写压力。
- 评审确认 `player-lifecycle-and-application.md` §8 基线锚点维持原样：基线
  权威已由 `mod-version-workflow`（从项目 AGENTS.md / handoff 读取
  last user-validated baseline）与 mod 文件夹命名承载，不在技能内重复维护。

## 0.3.1 (2026-10-24)

`reframework-lua-development` 增补 Player 生命周期、缓存与应用参考页。

- 新增 `references/player-lifecycle-and-application.md`：玩家身份 / 意图 / 就绪 /
  写入时机分层、缓存失效边界、应用触发与记账原则、按特性的写入策略
  （AVM 材质可见性 / 变身脚本 / LuaBone 骨骼控制器）、区分性证据采集与验证范围；
  证据锚点取自 MHR AVM / BladeSwitch 实测（2026-10-24），限定为该项目证据而非
  通用时序保证。
- `references/runtime-and-hooks.md`：Managed object lifecycle 增补"有效受管引用
  不等于当前主角"的身份确认原则；Hook selection 增补有界逐帧身份检查的适用边界，
  以及不得从 open/close 方法名推断事件语义。
- `SKILL.md`：description 中英双语增补玩家扫描、外观/变身控制、LuaBone 与自定义
  骨骼控制器触发词；新增 Player scanning and application 段并链接新参考页。

## 0.3.0 (2026-10-22)

项目模板随插件分发 + 建项 command。

- 新增 `templates/`：4 份 Agent 项目模板（Generic / REFramework Lua v2 / RE Engine 外观
  v2 / RE Engine 骨骼动画 v2），自旧散装模板目录迁入并完成对外交付化修订。
- 模板修订：Discipline 权威源改指向插件 hook 与 GitHub 仓库（移除已退役的本机绝对路径）；
  Review Agent / Command 补 `re-mod-toolkit:` 前缀；AGENTS.md §4 增加"组件由 re-mod-toolkit
  插件提供"前置声明；本地 Windows 工具链改为仅 DLL / 原生编译时适用，本机缺失时建议用户
  安装 MSVC（指引见发布帖），fallback 由 Agent 自动安装 LLVM-MinGW 并设置 `LLVM_MINGW`；
  4 份 README 重写（移除 Common Core zip 旧引用，补依赖声明与建项方式）。
- 新增 command `new-mod-project`：引导选择项目类型（lua / appearance / animation / generic）、
  从 `templates/` 复制建项并填充项目身份占位符。
- README：组件表收录 templates，新增"从模板建项目"与"单模型使用边界"章节。

## 0.2.0 (2026-10-21)

MCP 架构反转：主体定位从 server 内调 GLM-4.6v 改为主模型看帧图标注。

- 新增工具 `probe_frame(video_path, t)`：抽单帧回传图片路径 + 视频元信息 + 标注协议，
  主模型 Read 帧图后以像素坐标标注主体。
- `analyze_video_diff` 新增 `subject="x,y,w,h"` 参数（像素主体框；15% 容错边距 +
  50% 宽框 ROI + 20% 紧框过滤沿用原外扩链）；`focus`/`mark_glm` 参数移除，
  省略 `subject` 时为全画面模式。
- 删除全部 GLM API 链（`_call_glm`/`_get_subject_box`/`_mark_region_impl`/
  `_draw_boxes` 等）：server 零网络请求、零凭据，README 的 ZHIPU_API_KEY 说明删除。
- ROI 无尖峰回退全画面兜底保留；自动重定位改为报告内 `probe_frame(t=尖峰时刻)` 提示。
- large-file-guard 视觉证据豁免新增 `_probe` 产物名（`probe_frame` 输出可达 256 KiB，
  不加豁免会被 64 KiB 普通档拦截）。
- 工具描述收窄为"视频 diff 工具"并反向声明不做视频内容理解/问答/浏览，防滥用。
- **破坏性变更**：0.1.0 的 `focus=auto`/`mark_glm` 调用方式不再可用。

## 0.1.0 (2026-10-21)

首个插件化版本。自 `D:\ZCODE-PLUGIN` 散装资产收敛而来：

- 收录 3 hooks + 3 agents + 4 commands + 9 skills + glm-vision MCP（单工具 `analyze_video_diff`）。
- 修复 discipline-router 模型匹配：provider 前缀逐级剥离 + 大小写不敏感，
  修复 `new-provider/glm-5.3-flash` 匹配不上 `GLM-5.3-Flash` 导致 GLM Discipline 静默失效的问题。
- discipline-router 日志改写到 `~/.zcode/data/re-mod-toolkit/logs/`（不再写入插件缓存目录）。
- MCP 无 key 化：未配置 `ZHIPU_API_KEY` 时 `focus=auto` 自动降级全画面、忽略 `mark_glm`，
  diff 扫描全程零 API 依赖。
- rife-interpolation skill 未收录（保留为用户级 skill）。
