# Changelog

## 0.1.0 (2026-10-21)

首个插件化版本。自 `D:\ZCODE-PLUGIN` 散装资产收敛而来：

- 收录 3 hooks + 3 agents + 4 commands + 9 skills + glm-vision MCP（单工具 `analyze_video_diff`）。
- 修复 discipline-router 模型匹配：provider 前缀逐级剥离 + 大小写不敏感，
  修复 `new-provider/glm-5.3-flash` 匹配不上 `GLM-5.3-Flash` 导致 GLM Discipline 静默失效的问题。
- discipline-router 日志改写到 `~/.zcode/data/re-mod-toolkit/logs/`（不再写入插件缓存目录）。
- MCP 无 key 化：未配置 `ZHIPU_API_KEY` 时 `focus=auto` 自动降级全画面、忽略 `mark_glm`，
  diff 扫描全程零 API 依赖。
- rife-interpolation skill 未收录（保留为用户级 skill）。
