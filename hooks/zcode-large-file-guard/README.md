# ZCode Large File Guard

这是一个针对模型上下文 / Token 爆炸的 ZCode `PreToolUse` Hook。

## 行为

- `Read`：目标普通文件大于 **64 KiB** 时，阻止直接整文件读取。
- `Read`：glm-vision MCP 产出的**视觉证据图**放宽到 **256 KiB**——文件为 `.jpg` / `.jpeg` / `.png` / `.webp` 且满足任一：文件名含 `_spike` 或 `_probe` 或 `_marked`、路径含 `glm_vision_marks`。普通图片不放宽，仍按 64 KiB。
- 豁免模式与 glm-vision MCP 产物命名的对应（0.2.0 起为双工具 `probe_frame` + `analyze_video_diff`，零模型依赖）：尖峰对比图 `*_spikeN_*.jpg`（full/zoom）与主体标注帧图 `*_probe_*.jpg` 均命中豁免；`_marked` 只为兼容 grounding 时代的旧产物（0.2.0 已移除该功能）。MCP 出图硬上限 256 KiB（`_save_jpeg_small`）与豁免档一致。`glm_vision_marks` 目录是已删除的 `analyze_video_deep` 的旧产物路径，模式保留只为兼容历史文件。
- `Bash`：阻止明显会把整个大文件直接打到 stdout 的 `cat` / `type` / `more` / `Get-Content` / `gc`，阈值同样按普通 64 KiB / 视觉证据 256 KiB 区分。
- 判断完全不依赖文件内容；`.json`、`.bin`、`.528`、`.pfb`、`.mesh`、自定义后缀、无后缀都按实际文件大小处理。
- `grep` / `rg` / `jq` / Python / SQLite / 项目已有解析器等本地过滤与索引操作继续允许。
- 触发后会提示主 Agent 改用 `@data-researcher` 或本地脚本/索引。
- 回归测试矩阵：`skill复查\tmp\hook-test\run_guard_tests.py`（16 case，可重跑）。

## 为什么做成 Plugin

ZCode 当前不执行 workspace/project-level Hook；用户级 Hook 或 Plugin Hook 才会真正执行。Plugin 便于你在不同 MH Mod 项目复用。

## 安装

1. ZCode → Settings → Plugins。
2. 把本目录作为本地 Plugin / Marketplace source 添加并启用。
3. Settings → Hooks 中确认出现 `large-file-guard` 的 `PreToolUse` Hook。
4. **新建 session** 后再测试；Hook 配置在 session 启动时快照。

## 阈值

按 argv 位置或环境变量覆盖（config.json 实际传参：`65536 120 262144`）：

| argv 位 | 环境变量 | 默认 | 作用 |
| --- | --- | --- | --- |
| 1 | `ZCODE_LARGE_FILE_GUARD_BYTES` | 65536（64 KiB） | 普通文件整读上限 |
| 2 | `ZCODE_LARGE_FILE_GUARD_LINES` | 120 | 有界部分读取的最大行数 |
| 3 | `ZCODE_VISUAL_EVIDENCE_GUARD_BYTES` | 262144（256 KiB） | 视觉证据图整读上限 |

例如普通文件放宽到 1 MiB：`ZCODE_LARGE_FILE_GUARD_BYTES=1048576`。

## 推荐配套

与之前建立的 `data-researcher` 子智能体配合：

大文件 → Hook 阻止直接读取 → `@data-researcher` → 本地过滤/索引 → 只返回少量有效结果。

## 第一版边界

这是保守型防爆 Hook，不是完整 shell 解析器。它重点拦截 `Read` 和最常见的“整文件打印”命令；不会阻止 Python/grep 等本地处理，否则会妨碍 data-researcher 正常工作。
