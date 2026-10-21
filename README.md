# re-mod-toolkit

RE Engine Mod 开发工具箱，一个 ZCode 插件：把 Discipline 注入 hook、跨模型复审 subagent、
Mod 开发 skill、视频帧 diff MCP 工具整合为单一可版本管理的分发单元。

> 本仓库是**权威维护仓库**。作者机器上另有插件安装源
> （`D:\ZCODE-PLUGIN\re-mod-toolkit`），内容跟随本仓库同步。

## 组件

| 类型 | 数量 | 内容 |
| --- | --- | --- |
| hooks | 3 | `discipline-router`（SessionStart 按模型路由 Discipline 注入）、`zcode-large-file-guard`（PreToolUse 大文件读取硬拦截）、`context-reminder`（PostToolUse 上下文水位提醒） |
| agents | 3 | `glm-review`、`deepseek-review`（跨模型复审）、`data-researcher`（大数据过滤研究） |
| commands | 4 | `deepseek-review`、`glm-review`（手动触发复审）、`promote-main`、`release`（版本晋升/发布授权） |
| skills | 9 | RE Engine Mod 开发全链路：`reframework-lua-development`、`reframework-api-reference`、`mod-debugging`、`mod-package`、`mod-version-workflow`、`mod-visual-validation`、`reengine-asset-diagnosis`、`npc-to-player-routing`、`animation-bake-tuning` |
| MCP | 1 | `glm-vision`：`analyze_video_diff` 像素级视频帧 diff，定位画面突变帧对 |

## 安装

本仓库根即 marketplace（`marketplace.json`，`source: "."`），两种装法：

1. **clone 后安装**：`git clone https://github.com/FoobarRogers/re-mod-toolkit.git` →
   ZCode → Plugin Marketplace → Add marketplace → 粘贴 clone 出的目录路径 → Install → Enable。
2. **本地路径安装**：不 clone，直接把仓库 ZIP 解压目录（或本地已有副本）粘给 Add marketplace。

## 版本管理与更新流程

1. 修改源码。
2. 递增 `.zcode-plugin/plugin.json` 的 `version`，同步改 `marketplace.json` 条目与 `CHANGELOG.md`。
3. commit + push。
4. 已安装的机器：Plugin Marketplace 里对 `re-mod-toolkit` 点 Update 生效。

插件是缓存拷贝制：只改源码不递增版本号、不在 UI 里更新，改动不会生效。

## MCP：无 key 运作

`analyze_video_diff` 的 diff 扫描本体是纯像素计算，始终零 API 费用。
`ZHIPU_API_KEY` 为纯可选项：未配置时 `focus=auto` 自动降级为全画面 diff、`mark_glm` 被忽略，
并在输出头部注明；配置后仅用于主体定位与可选 grounding（各一次廉价请求）。

如需启用语义定位，在**各自机器**上设置用户级环境变量后完全重启 ZCode：

```
setx ZHIPU_API_KEY "你的智谱key"
```

插件清单永不携带 key；`ZHIPU_MODEL` 可选（默认 `glm-4.6v`）。

## Discipline 文件同步约定

`hooks/discipline-router/` 下 `GLM-discipline.md` 与 `deepseek-discipline.md` 同源、
14 节编号一致；修改通用条款时两份必须同步，模型特有条款只改对应文件。
`deepseek-role.md` 是 DeepSeek Main Agent 专属角色文件，由 `profiles/deepseek.json`
的 `prepend` 注入，GLM 侧不得读取或套用。

## 与 D:\ZCODE-PLUGIN 归档的关系

作者机器上 `D:\ZCODE-PLUGIN\skill|hook|agent|command|mcp` 旧散装目录在插件验证通过并
退役后转为只读归档，不再同步；`Template\`、`llvm-mingw\`、`zcode_export\`、`test\`
等非运行时内容与本插件无关，仍在原处维护。
