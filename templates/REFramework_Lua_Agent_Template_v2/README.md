# REFramework Lua Profile

REFramework 纯 Lua Mod 项目的 Agent 模板，随 `re-mod-toolkit` 插件分发。

## 依赖

本模板路由到的全部 Skills（`reframework-lua-development`、`reframework-api-reference`、
`mod-debugging`、`mod-visual-validation`、`mod-version-workflow`、`mod-package`）、
复审 Agent / Command 与 Discipline 注入 hook 均由 `re-mod-toolkit` 插件提供。使用前先
安装并启用该插件，安装方式见插件仓库 README（https://github.com/FoobarRogers/re-mod-toolkit）。

## 领域内容

本 Profile 只保留 Lua / REFramework 领域内容：`AGENTS.md`、`lua-development.md`、
`runtime-and-hooks.md`、`project-layout.md`。Lua 特有的症状分类、日志和 Mod 冲突诊断
在 `runtime-and-hooks.md`。

`docs/project-workflow.md` 保留该 Profile 的 candidate / 验收 / 打包特有规则；通用授权
与发布状态由 `docs/version-workflow.md` 管理。

## 建项方式

复制本目录为新的项目根目录，按 `AGENTS.md` §1 填项目身份即可开工；也可以在装有插件的
环境里用 `/new-mod-project` 让 Agent 引导建项。
