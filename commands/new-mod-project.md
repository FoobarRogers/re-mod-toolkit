---
description: 从 re-mod-toolkit 插件自带模板创建新的 Agent 项目（RE Engine Mod 或通用项目）
argument-hint: [目标目录] [--type=lua|appearance|animation|generic]
---

用户要求基于插件自带模板创建新的 Agent 项目。按以下流程执行：

1. **定位模板源**：模板位于 `re-mod-toolkit` 插件安装目录的 `templates/` 下。ZCode 插件
   缓存路径形如 `~/.zcode/cli/plugins/cache/<marketplace>/re-mod-toolkit/<version>/templates/`，
   用 Glob / ls 定位实际存在的版本目录。找不到 `templates/` 时说明插件未安装或版本过旧，
   提示用户先安装 / 更新 `re-mod-toolkit` 插件，然后停止。

2. **确认项目类型**（用户未通过 `--type` 参数指定时，用 AskUserQuestion 询问，四选一）：
   - `lua` → `REFramework_Lua_Agent_Template_v2`：REFramework 纯 Lua Mod；
   - `appearance` → `RE_Engine_Appearance_Mod_Agent_Template_v2`：RE Engine 外观 Mod（mesh / 材质 / 贴图 / PFB）；
   - `animation` → `RE_Engine_Bone_Animation_Mod_Agent_Template_v2`：RE Engine 骨骼动画 Mod（MOT / MOTLIST）；
   - `generic` → `Generic_Agent_Project_Template`：上述之外的通用项目。
   同时确认目标目录（未通过参数给出时默认在当前工作区下新建子目录）与项目名称。

3. **复制模板**：把所选模板目录的完整内容（含 `.gitignore` 与 `docs/`）复制到目标目录；
   目标目录已存在且非空时先向用户确认。

4. **填充项目身份**：向用户询问（或从既有资料推断）游戏、目标对象与技术路线，据此填写
   `AGENTS.md` §1 的项目身份占位符（`<PROJECT>` 等）。其余章节保持模板原文，不预先扩展、
   不引入模板之外的额外治理文件；项目专属规则等真实任务出现后再加。

5. **初始化收尾**：`docs/session-handoff.md` 保持模板骨架。最后向用户报告：项目位置、
   所用模板、已填充的身份字段，以及开工前提（已安装并启用 `re-mod-toolkit` 插件）和首条
   工作建议（从只读调查开始）。
