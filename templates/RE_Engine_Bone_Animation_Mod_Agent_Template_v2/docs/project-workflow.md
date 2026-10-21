# RE Engine Bone Animation Project Workflow

> 通用授权与 candidate 状态遵守 `version-workflow.md`；本文件保存 MOT/MOTLIST 项目的版本、add-on 与打包语义。

## 1. Branch / Candidate

- 修 bug：`fix/<version>-fixN`
- 实验：`test/<version>-testN`
- 功能 add-on：以功能命名且默认无序号，例如 `<base>-escape`；add-on 由本体版本决定，基线升级时对新本体重放，而不是机械增加 add-on 序号。

每个 test 至少记录：baseline、改动槽位、修改方式（整条复制 / 换血 / 重建 / bias）、修改文件与工具参数、预期机制、离线验收、实机判据、结果与回退。

## 2. Artifact Types

项目没有自己的脚本时，可沿用：

| 类型 | 建议位置 | 说明 |
| --- | --- | --- |
| test / fix 增量 | `patch/<base>-<tag>/` | 试验 / 修复增量 |
| add-on | `release/<base>-<tag>/` | release 级验收，但不等于本体版本晋升 |
| 完整包 | `release/<version>/` | 仅在 Release 授权后形成正式产物 |

ZIP 顶层保持项目实际可安装结构。add-on 与完整包若覆盖同一 motlist，必须在说明中写明互斥、排序和回退。

## 3. Release Gate

除通用 Gate 外，至少确认：

- 目标同名资源相对 baseline 确实发生预期变化，避免空包；
- 文件清单无额外资源；
- 离线验收器全过，额外重写槽如实登记；
- ZIP、SHA256SUMS / evidence manifest（若项目使用）一致；
- README / slot-map / handoff 与实际 candidate 同步。

动画结构、烘焙与实机判据见 `animation-pipeline.md`。
