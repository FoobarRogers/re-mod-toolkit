# re-mod-toolkit

RE Engine Mod 开发工具箱，一个 ZCode 插件：把 Discipline 注入 hook、跨模型复审 subagent、
Mod 开发 skill、视频帧 diff MCP 工具整合为单一可版本管理的分发单元。

## 组件

| 类型 | 数量 | 内容 |
| --- | --- | --- |
| hooks | 3 | `discipline-router`（SessionStart 按模型路由 Discipline 注入）、`zcode-large-file-guard`（PreToolUse 大文件读取硬拦截）、`context-reminder`（PostToolUse 上下文水位提醒） |
| agents | 3 | `glm-review`、`deepseek-review`（跨模型复审）、`data-researcher`（大数据过滤研究） |
| commands | 5 | `deepseek-review`、`glm-review`（手动触发复审）、`promote-main`、`release`（版本晋升/发布授权）、`new-mod-project`（从模板建项） |
| skills | 9 | RE Engine Mod 开发全链路：`reframework-lua-development`、`reframework-api-reference`、`mod-debugging`、`mod-package`、`mod-version-workflow`、`mod-visual-validation`、`reengine-asset-diagnosis`、`npc-to-player-routing`、`animation-bake-tuning` |
| MCP | 1 | `glm-vision`：`probe_frame` + `analyze_video_diff` 双工具视频帧 diff（主模型标注主体，server 纯像素定位突变帧对，零模型依赖、零凭据） |
| templates | 4 | Agent 项目模板（随项目复制使用）：`Generic_Agent_Project_Template`（通用）、`REFramework_Lua_Agent_Template_v2`、`RE_Engine_Appearance_Mod_Agent_Template_v2`、`RE_Engine_Bone_Animation_Mod_Agent_Template_v2` |

## 安装

本仓库根即 marketplace（`marketplace.json`，`source: "."`），两种装法：

1. **clone 后安装**：`git clone https://github.com/FoobarRogers/re-mod-toolkit.git` →
   ZCode → Plugin Marketplace → Add marketplace → 粘贴 clone 出的目录路径 → Install → Enable。
2. **本地路径安装**：不 clone，直接把仓库 ZIP 解压目录（或本地已有副本）粘给 Add marketplace。

## 从模板建项目

`templates/` 提供 4 份开箱即用的 Agent 项目模板（通用 / REFramework Lua / RE Engine 外观
/ RE Engine 骨骼动画），模板内的 Skills、复审 Agent 与 Discipline hook 都指向本插件的
组件，需先安装并启用插件。两种用法：

- **手动**：把所选模板目录复制为项目根，按其 `AGENTS.md` §1 填项目身份；
- **引导**：在 ZCode 会话里执行 `/new-mod-project`，Agent 会询问项目类型与目标目录、
  复制模板并填充项目身份。

## 单模型使用边界

本套件的双模型工作流（DeepSeek ↔ GLM 交叉复审）默认用户同时持有两家模型：Discipline
hook 只在 stdin 模型名含 `deepseek` / `glm` 时注入，其它模型（Claude、GPT 等）静默
不注入、模板复审路由不适用——单模型用户仍可正常使用全部 skills、commands、MCP 与
`data-researcher`，但模板中的复审章节对你是空路由，可按需删改。

## Agents 的模型绑定（首次使用前检查）

三个 subagent 中，`data-researcher` 未绑定模型（跟随当前会话模型），开箱即用；
`glm-review` 与 `deepseek-review` 默认绑定了作者环境的模型账户，新环境首次调用可能报
"余额不足 / 无可用资源包"类错误。

处理：在 ZCode 的 Agent 设置里**点击下拉框选择需要的 agent（模型）**，把
`glm-review` / `deepseek-review` 指向自己账户下可用的模型即可，无需修改插件文件。

## 版本管理与更新流程

1. 修改源码。
2. 递增 `.zcode-plugin/plugin.json` 的 `version`，同步改 `marketplace.json` 条目与 `CHANGELOG.md`。
3. commit + push。
4. 已安装的机器：Plugin Marketplace 里对 `re-mod-toolkit` 点 Update 生效。

插件是缓存拷贝制：只改源码不递增版本号、不在 UI 里更新，改动不会生效。

## MCP：glm-vision（零模型依赖）

两个工具组成"标注 → diff"工作流，server 是纯本地像素计算：不调用任何视觉模型、
不发起网络请求、不需要 API key、不携带凭据。

1. `probe_frame(video_path, t)`：抽单帧，返回图片路径 + 视频元信息 + 标注协议；
2. 主模型 Read 帧图，定位主要角色/主体，以像素坐标 `x,y,w,h` 给出主体框；
3. `analyze_video_diff(video_path, subject="x,y,w,h")`：在主体外扩 50% 的 ROI 内
   像素级 diff，定位画面突变帧对并产出标注对比图。省略 `subject` 时全画面扫描
   （阴性筛查用）。

定位与分工：两个工具只做视频 diff——不提供视频内容理解、问答、浏览。主体标注
由主模型完成，server 只做固定外扩与像素计算；语义结论由主模型 Read 对比图给出。
实测参考（MHR 站立 idle 循环接缝素材，720p60）：主体 ROI 模式孤立度 28.0x，全画面
模式仅 4.9x，背景火焰/烟雾差异被主体紧框过滤、不混入结果。

## Discipline 文件同步约定

`hooks/discipline-router/` 下 `GLM-discipline.md` 与 `deepseek-discipline.md` 同源、
14 节编号一致；修改通用条款时两份必须同步，模型特有条款只改对应文件。
`deepseek-role.md` 是 DeepSeek Main Agent 专属角色文件，由 `profiles/deepseek.json`
的 `prepend` 注入，GLM 侧不得读取或套用。
