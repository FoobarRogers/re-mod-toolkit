# RE Engine Appearance Project Workflow

> 通用授权与 candidate 状态遵守 `version-workflow.md`；本文件只保存外观资源项目的领域流程与打包规则。

## 1. Baseline

记录游戏 / 资源版本、已验收完整包、目标角色 / 装备 / body ID、Loader 组合、实际生效 natives 路径和关键依赖版本。

## 2. Candidate

一次 test 至少记录：baseline、修改层（mesh / bone / texture / MDF / PFB / LuaBone / AVM）、修改文件、工具与参数、机制 / 预期现象、刷新方式、验证结果和回退包。

多层修改只有存在不可分割引用链时才一起进行，并在记录中逐层列出，不写成笼统的“修复模型”。

## 3. Packaging

没有项目既有规则时可采用：

```text
<Project>_<version>.zip
<Project>_<version>-testN.zip
<Project>_<version>-fixN.zip
```

ZIP 顶层保持 Fluffy / 项目现有可直接安装结构；不得为了模板统一改动真实资源路径。

## 4. Release Gate

除 `version-workflow.md` 的通用 Gate 外，至少确认：

- 文件清单与预期一致，无意外资源；
- 项目使用的 JSON 可 parse、Lua 可加载；
- 关键二进制资源 hash / 来源可追溯；
- 主要场景和实际刷新路径完成验证；
- Loader / LuaBone / AVM 等关键依赖版本与 candidate 匹配；
- README / handoff / 项目事实索引同步。

资源层诊断与缓存 / Loader 路由见 `asset-workflow.md`。
