# re-mod-toolkit

RE Engine Mod 开发工具箱，以 ZCode 插件形式维护。前身是 `D:\ZCODE-PLUGIN` 下的散装资产
（Junction 映射 + 手动同步 + .7z 快照），0.1.0 起收敛为插件 + git 版本管理。

## 组件

| 类型 | 数量 | 内容 |
| --- | --- | --- |
| hooks | 3 | `discipline-router`（SessionStart 按模型路由 Discipline 注入）、`zcode-large-file-guard`（PreToolUse 大文件读取硬拦截）、`context-reminder`（PostToolUse 上下文水位提醒） |
| agents | 3 | `glm-review`、`deepseek-review`（跨模型复审）、`data-researcher`（大数据过滤研究） |
| commands | 4 | `deepseek-review`、`glm-review`（手动触发复审）、`promote-main`、`release`（版本晋升/发布授权） |
| skills | 9 | RE Engine Mod 开发全链路：`reframework-lua-development`、`reframework-api-reference`、`mod-debugging`、`mod-package`、`mod-version-workflow`、`mod-visual-validation`、`reengine-asset-diagnosis`、`npc-to-player-routing`、`animation-bake-tuning` |
| MCP | 1 | `glm-vision`：`analyze_video_diff` 像素级视频帧 diff，定位画面突变帧对 |

## 安装与更新

- 安装：ZCode → Plugin Marketplace → Add marketplace → 粘贴本目录路径 → Install → Enable。
- 更新：修改源码 → 递增 `.zcode-plugin/plugin.json` 的 `version`（与 `marketplace.json` 条目同步）→
  Plugin Marketplace 里对 `re-mod-toolkit` 点 Update。插件是缓存拷贝制，改源码不递增版本不会生效。

## MCP：无 key 运作

`analyze_video_diff` 的 diff 扫描本体是纯像素计算，始终零 API 费用。
`ZHIPU_API_KEY` 为纯可选项：未配置时 `focus=auto` 自动降级为全画面 diff、`mark_glm` 被忽略，
并在输出头部注明；配置后仅用于主体定位与可选 grounding（各一次廉价请求）。
本插件清单不携带 key；如需启用语义定位，自行在环境变量中设置 `ZHIPU_API_KEY`。

## Discipline 文件同步约定

`hooks/discipline-router/` 下 `GLM-discipline.md` 与 `deepseek-discipline.md` 同源、
14 节编号一致；修改通用条款时两份必须同步，模型特有条款只改对应文件。
`deepseek-role.md` 是 DeepSeek Main Agent 专属角色文件，由 `profiles/deepseek.json`
的 `prepend` 注入，GLM 侧不得读取或套用。

## 与 D:\ZCODE-PLUGIN 归档的关系

本目录独立 git 管理。`D:\ZCODE-PLUGIN\skill|hook|agent|command|mcp` 在插件验证通过并
退役旧机制后转为只读归档，不再双向同步；`Template\`、`llvm-mingw\`、`zcode_export\`、`test\`
等非运行时内容与本插件无关，仍在原处维护。
