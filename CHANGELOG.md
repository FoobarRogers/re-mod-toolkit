# Changelog

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
