# RE Engine Bone Animation Profile

RE Engine 骨骼动画 Mod（MOT / MOTLIST 替换、重建、烘焙、过渡重接）项目的 Agent 模板，
随 `re-mod-toolkit` 插件分发。

## 依赖

本模板路由到的全部 Skills（`animation-bake-tuning`、`reframework-lua-development`、
`reframework-api-reference`、`mod-debugging`、`mod-visual-validation`、
`mod-version-workflow`、`mod-package`）、复审 Agent / Command 与 Discipline 注入 hook
均由 `re-mod-toolkit` 插件提供。使用前先安装并启用该插件，安装方式见插件仓库 README
（https://github.com/FoobarRogers/re-mod-toolkit）。

## 领域内容

本 Profile 保留 MOT / MOTLIST、烘焙、槽位画像和动画项目布局：MOT/MOTLIST 结构、修改
方式、烘焙与运行时症状路由见 `animation-pipeline.md`，动作 / 槽位事实索引见
`slot-map.md`。

`docs/project-workflow.md` 保留该 Profile 的 candidate / 验收 / 打包特有规则；通用授权
与发布状态由 `docs/version-workflow.md` 管理。

## 建项方式

复制本目录为新的项目根目录，按 `AGENTS.md` §1 填项目身份即可开工；也可以在装有插件的
环境里用 `/new-mod-project` 让 Agent 引导建项。
