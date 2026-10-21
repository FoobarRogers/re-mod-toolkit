# 项目布局

## 推荐最少结构

```text
<项目根>/
├─ AGENTS.md
├─ docs/
│  ├─ animation-pipeline.md     # 管线口径、修改方式、验收门禁
│  ├─ slot-map.md               # 槽位画像（核心资产）
│  ├─ session-handoff.md
│  ├─ established-conclusions.md # 已证实结论（实机定案 / 双源验证，每条带出处）
│  └─ version-workflow.md
├─ tools/                       # 项目正身脚本：构建 / 验收 / 打包 / 探针
│  └─ lua/                      # 游戏内 autorun 脚本（只放要部署的 .lua）
├─ provider/                    # 原版与参照资源（只读基准，永不原地修改）
├─ tmp_mot/                     # 构建产物（不入库）
├─ release/                     # 已验收交付：完整包 + add-on
└─ patch/                       # test / fix 试验增量
```

## 原则

- 基准（provider / release）只读：动画修改永远发生在工具输出与源码 / 参数层，由验收器保证"其余槽逐字节不变"。
- 游戏内 autorun 脚本与本地测试桩分开存放；本机桩永不部署（命名与目录隔离，见 REFramework Lua skill）。
- 可复用且跨项目的工具可沉淀进 skill 的 `scripts/`（自包含）；项目正身留在 `tools/`。
- 产物 zip 不入库，交分发渠道；目录内其余内容（清单 / 证据 / 文档）按项目声明入库。
