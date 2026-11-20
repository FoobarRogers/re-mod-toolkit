# ZCode Large File Guard

这是一个针对模型上下文 / Token 爆炸的 ZCode `PreToolUse` Hook。

## 行为

- `Read`：目标普通文件大于 **64 KiB** 时，阻止直接整文件读取。
- `Read`：**图片扩展名**（`.jpg` / `.jpeg` / `.png` / `.webp` / `.gif` / `.bmp`）放宽到 **16 MiB**——图片进上下文是视觉 token（按分辨率计、总量有界），与文件字节量不成比例。原 glm-vision 视觉证据图 256 KiB 特判档（`_spike`/`_probe` 命名闭环）已于 2026-11-20 并入本档：MCP 产物即图片，直接按图片档放行，字节级精调在套餐计费下不再有意义。仅 Read 通道适用；**Bash 通道不放宽**——图片被 `cat` 裸 dump 到 stdout 时字节全部变成文本 token，64 KiB 拦截保留。glm-vision 出图为**原分辨率 q90 JPEG**（`_save_jpeg`，产出超 8 MiB 才降级兜底），正常产物远小于 16 MiB 档，不受本门禁影响。
- `Bash`：阻止明显会把整个大文件直接打到 stdout 的 `cat` / `type` / `more` / `Get-Content` / `gc`，统一按 64 KiB（图片扩展名不适用 16 MiB 档）。
- 判断完全不依赖文件内容；`.json`、`.bin`、`.528`、`.pfb`、`.mesh`、自定义后缀、无后缀都按实际文件大小处理。
- `grep` / `rg` / `jq` / Python / SQLite / 项目已有解析器等本地过滤与索引操作继续允许。
- 触发后会提示主 Agent 改用 `@data-researcher` 或本地脚本/索引。
- 回归测试矩阵：`tmp\hook-test\run_guard_tests.py`（工作区内，可重跑；历史版本见 `archive\tmp\hook-test\`）。

## 为什么做成 Plugin

ZCode 当前不执行 workspace/project-level Hook；用户级 Hook 或 Plugin Hook 才会真正执行。Plugin 便于你在不同 MH Mod 项目复用。

## 安装

1. ZCode → Settings → Plugins。
2. 把本目录作为本地 Plugin / Marketplace source 添加并启用。
3. Settings → Hooks 中确认出现 `large-file-guard` 的 `PreToolUse` Hook。
4. **新建 session** 后再测试；Hook 配置在 session 启动时快照。

## 阈值

按 argv 位置或环境变量覆盖（config.json 实际传参：`65536 120 16777216`）：

| argv 位 | 环境变量 | 默认 | 作用 |
| --- | --- | --- | --- |
| 1 | `ZCODE_LARGE_FILE_GUARD_BYTES` | 65536（64 KiB） | 普通文件整读上限 |
| 2 | `ZCODE_LARGE_FILE_GUARD_LINES` | 120 | 有界部分读取的最大行数 |
| 3 | `ZCODE_IMAGE_GUARD_BYTES` | 16777216（16 MiB） | 图片扩展名 Read 整读上限（Bash 不适用） |

例如普通文件放宽到 1 MiB：`ZCODE_LARGE_FILE_GUARD_BYTES=1048576`。

## 推荐配套

与之前建立的 `data-researcher` 子智能体配合：

大文件 → Hook 阻止直接读取 → `@data-researcher` → 本地过滤/索引 → 只返回少量有效结果。

## 第一版边界

这是保守型防爆 Hook，不是完整 shell 解析器。它重点拦截 `Read` 和最常见的“整文件打印”命令；不会阻止 Python/grep 等本地处理，否则会妨碍 data-researcher 正常工作。
