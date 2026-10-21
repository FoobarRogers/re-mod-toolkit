# Independent Review Protocol

本文件规定 **Main Agent 如何向独立 Review Agent 提交只读复审**。Reviewer 自身权限、工具和输出格式由对应 Review Agent 的提示词或手动 Command 约束；本文件不替代那些更严格的限制。

## 1. 角色边界

Review 是当前工程循环的独立证伪检查，不是新的实现任务。

Main Agent 负责：形成 candidate、固化关键证据、提交 ReviewPacket、接收并裁决结果，以及决定是否执行最小修复与定向复验。

Review Agent 负责：检查当前因果模型是否被证据支持，尝试证伪关键实现主张，寻找由当前改动引入的实质回归与 test-oracle 盲点。

Review Agent 不接管 Main Agent 的实现职责，也不得再调用另一个 Review Agent。

## 2. 发起前 Gate

只有当前工作已形成可识别 candidate 时才发起独立复审。发起前 Main Agent 必须已经明确并持久化：

- 当前唯一目标；
- baseline 与 candidate；
- confirmed facts；
- leading causal model；
- 实际 changed surface；
- 已完成的 validation；
- 仍存在的不确定项。

ReviewPacket 不是重要证据的唯一存储位置。若关键事实仍只存在于会话上下文，先按项目约定落盘，再发起 Review。

## 3. 固定请求语义

Main Agent 自动调用 Reviewer 时，使用以下语义边界；可替换项目名、路径和 Review Focus，但不要改写成开放式开发任务：

```text
你是本项目的独立只读复审者。

只审查下面给出的当前候选、因果模型和证据。
不要修改、创建或删除任何文件；不要继续实现、修复、重构、打包、提交或推送；
不要从零重新执行主 Agent 已完成的调查；不要扩大任务范围；
不要调用另一个 Review Agent，也不要发起递归复审。

重点尝试证伪：
1. 当前根因是否真正由证据支持；
2. 当前修改是否确实作用于声称的机制；
3. 是否存在由当前修改引入的实质回归；
4. 当前验证 oracle 是否存在无法证明其主张的盲点。

只报告有具体证据且可能改变当前工程决策的问题。
低置信度猜测、纯风格建议、既有且与当前改动无关的问题应明确降级或省略。

如果现有证据支持当前候选且没有阻断问题，明确返回 SUPPORTED。
SUPPORTED 不要求为了体现 Review 价值而制造修改建议。
```

用户通过 `/glm-review`、`/deepseek-review` 等手动 Command 发起时，也按本协议解释 ReviewPacket；若 Command 自身限制更严格，以更严格者为准。

## 4. 标准 ReviewPacket

```markdown
### Goal
<当前唯一目标>

### Baseline
<上一已验收状态 / commit / binary / configuration>

### Candidate
<当前候选身份>

### Confirmed Facts
<已确认事实 + 稳定证据位置>

### Leading Causal Model
<为什么问题发生，以及为什么当前修改能解决它>

### Changed Surface
<实际改动的文件 / 函数 / 代码路径>

### Validation Evidence
<A/B、测试、日志、运行数值、截图、hash 等>

### Known Uncertainties
<仍未验证且本次 Review 不应擅自填补的部分>

### Review Focus
<最希望 Reviewer 尝试证伪的 1–3 个关键主张>
```

Packet 应引用已经持久化的证据，而不是复制大型日志、dump 或整个 diff。

## 5. 返回后的职责

Review 结束后控制权回到原 Main Agent。

Main Agent 对每个发现按以下维度裁决：`evidence strength / impact on current goal / introduced by current change / in scope`。

只有证据充分且影响当前目标的问题进入最小修复；修复后只做 targeted revalidation。

`SUPPORTED` 时直接进入下一 Gate 或 STOP，不得为了“已经调用 Review”而继续制造工作。

一次 Review 不自动触发第二次广泛调查，也不自动触发递归 Review。
