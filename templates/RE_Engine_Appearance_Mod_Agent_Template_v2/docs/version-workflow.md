# Version / Candidate / Release Workflow

本文件只规定通用状态与授权门禁。项目特有的包结构、命名、依赖、测试矩阵和发布渠道写入项目 workflow。

## 1. 状态

建议使用：

`WORKING → CANDIDATE → VALIDATED → USER_ACCEPTED → RELEASED`

阶段性固化走 prerelease：VALIDATED 的成果经用户授权固化为 prerelease 基线并登记，后续 fix / test 在该基线上循环；全部列举问题验证完成后进入 USER_ACCEPTED → RELEASED（见 §4）。

允许某一步为 `BLOCKED`，但不得把未运行的验证写成 PASS。

始终区分：implemented / offline-validated / runtime-validated / fully verified。

## 2. 授权

普通 `test` / `fix` / 适配指令只授权工作区修改、调查、本地验证和候选构建；不自动授权远程 push、合并 `main`、tag 或正式 Release。

只有用户明确授权时才执行对应的提交、推送、晋升或发布动作。已有授权只覆盖其明确范围。

已发布版本不原地覆盖；后续修订使用新的可识别版本 / candidate 身份。

## 3. Candidate 最小记录

每个非平凡 candidate 至少记录：

- baseline 身份；
- candidate 身份；
- changed surface；
- 修改原因与预期机制；
- validation evidence 与 validation level；
- known uncertainties；
- 回退方式；
- 关键证据位置。

失败 candidate 不要抹掉；保留真正可复用的反证和不要重复的路线。

## 4. Prerelease 固化与基线登记

开发 test 达到阶段性基本完整后，可由用户提出将成果固化为 prerelease：

- prerelease 包按 release 级完整度打包，固化进 release 文件夹，命名保留 `prerelease` 标记（如 `1.11prerelease1`），与正式 release 可区分；
- 固化时登记基线：版本号、内容范围、验证状态与证据位置写入版本记录，作为后续 fix / test 的工作 baseline；
- prerelease 不是正式发布；其后发现的新问题以它为基线继续 fix / test；
- 列举问题全部验证完成后，由用户提出发布正式 release，去掉 prerelease 标记打包（如 `1.11`）；
- release 之后的新修复在 release 基线上做 fix；改动较大时发布下一版本 release。

prerelease 固化与正式发布都是用户授权动作，不得由 agent 自行触发。

## 5. 验收与发布

发布前至少确认：

- candidate 与实际源码 / 资源 / binary 身份一致；
- 项目声明的必测项完成；
- 文件清单、版本、hash / manifest（若项目使用）一致；
- 无意外调试文件、临时证据或私有工作区内容；
- README / changelog / handoff / 项目 workflow 按项目要求更新；
- 用户验收与发布授权对应同一 candidate。

CI、静态检查或离线测试通过，只证明各自 oracle 覆盖的范围，不自动等于实机验收或正式支持。
