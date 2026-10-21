# Version / Candidate / Release Workflow

本文件只规定通用状态与授权门禁。项目特有的包结构、命名、依赖、测试矩阵和发布渠道写入项目 workflow。

## 1. 状态

建议使用：

`WORKING → CANDIDATE → VALIDATED → USER_ACCEPTED → RELEASED`

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

## 4. 验收与发布

发布前至少确认：

- candidate 与实际源码 / 资源 / binary 身份一致；
- 项目声明的必测项完成；
- 文件清单、版本、hash / manifest（若项目使用）一致；
- 无意外调试文件、临时证据或私有工作区内容；
- README / changelog / handoff / 项目 workflow 按项目要求更新；
- 用户验收与发布授权对应同一 candidate。

CI、静态检查或离线测试通过，只证明各自 oracle 覆盖的范围，不自动等于实机验收或正式支持。
