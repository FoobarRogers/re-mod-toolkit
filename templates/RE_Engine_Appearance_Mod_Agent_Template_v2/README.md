# RE Engine Appearance Profile

RE Engine 外观 Mod（mesh / bone / MDF / texture / PFB，可选 LuaBone / AVM）项目的 Agent
模板，随 `re-mod-toolkit` 插件分发。

## 依赖

本模板路由到的全部 Skills（`reengine-asset-diagnosis`、`reframework-lua-development`、
`reframework-api-reference`、`mod-debugging`、`mod-visual-validation`、
`mod-version-workflow`、`mod-package`、`npc-to-player-routing`）、复审 Agent / Command
与 Discipline 注入 hook 均由 `re-mod-toolkit` 插件提供。使用前先安装并启用该插件，安装
方式见插件仓库 README（https://github.com/FoobarRogers/re-mod-toolkit）。

## 领域内容

本 Profile 保留 mesh / bone / MDF / texture / PFB 以及可选 LuaBone / AVM 的领域资料：
资源层级与症状路由见 `asset-workflow.md`，材质 / 贴图见 `material-texture.md`，PFB 见
`pfb-workflow.md`。

`docs/project-workflow.md` 保留该 Profile 的 candidate / 验收 / 打包特有规则；通用授权
与发布状态由 `docs/version-workflow.md` 管理。

## 建项方式

复制本目录为新的项目根目录，按 `AGENTS.md` §1 填项目身份即可开工；也可以在装有插件的
环境里用 `/new-mod-project` 让 Agent 引导建项。
