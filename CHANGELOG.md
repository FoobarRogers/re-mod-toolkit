# Changelog

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
