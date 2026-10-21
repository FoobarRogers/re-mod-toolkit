# 纯 Lua REFramework 项目结构

推荐：

```text
Project/
├─ AGENTS.md
├─ README.md
├─ reframework/
│  ├─ autorun/
│  │  └─ ProjectName.lua
│  └─ data/
│     └─ project_name/
│        ├─ config.json
│        └─ logs/
├─ docs/
│  ├─ session-handoff.md
│  ├─ lua-development.md
│  ├─ runtime-and-hooks.md
│  ├─ project-workflow.md
│  ├─ review-protocol.md
│  ├─ version-workflow.md
│  ├─ token-discipline.md
│  └─ project-layout.md
├─ tools/
│  └─ ...            # 只放离线分析 / 打包 / lint 等辅助工具
└─ tmp/
   └─ ...            # 一次性分析结果，不入库
```

## 文件职责

### `reframework/autorun/`
只放 REFramework 实际加载的 Lua。

### `reframework/data/<project>/`
运行时配置、缓存、日志。
如果项目已有固定路径，以项目既有约定为准。

### `docs/`
保存长期知识，尤其是：
- 已验证 API
- 已验证对象生命周期
- 失败路线
- 兼容性结论
- 发布流程

### `tools/`
离线脚本：
- 大日志过滤
- diff
- 配置迁移
- 打包
- 静态检查

不要让 REFramework Lua 在游戏运行时承担离线数据分析。

### `tmp/`
中间产物。
默认 `.gitignore`。

## 新项目启动时要补齐的项目特定信息

在 `docs/session-handoff.md` 或新增 `docs/game-runtime.md` 中写清：

- 游戏名 / 版本
- REFramework 版本
- 目标 singleton / player 获取链
- 已验证 hook
- 配置路径
- 日志路径
- 其他依赖 Mod
- 已知冲突
