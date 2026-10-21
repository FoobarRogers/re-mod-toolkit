# PFB / Prefab 工作流

## 何时考虑 PFB

当问题表现为：

- 资源存在但没有实例化
- component 绑定缺失
- 非默认路径资源需要对象引用
- 某场景生成、某场景不生成
- 需要把 mesh/material/对象挂到特定 GameObject

才优先进入 PFB 层。

如果只是：
- 颜色不对
- 骨骼歪
- 部件显隐不对

先检查 texture/MDF、LuaBone/mesh、AVM。

## 修改前先画引用链

至少写清：

```text
PFB
→ GameObject / Component
→ resource path
→ mesh / material / other asset
```

如果引用链没弄清，不先重做整个 PFB。

## 路径改动

改 PFB 中的资源路径时必须核对：

- 目标文件真实存在
- 扩展版本号正确
- 大小写/目录层级正确
- loader 是否支持该路径
- 缓存是否要求切图/回主界面/重载存档

## 验证

PFB 修改后至少测试：

- 冷启动
- 读档
- 切图
- 重新进入目标场景
- 如果项目存在热重载，再测试 Reset Script / loader reload

## 不确定字段

不要凭字段名字或十六进制位置猜。
先比较：
- 原版 PFB
- 一个已知能工作的同类 Mod PFB
- 当前目标 PFB

只对确认字段做最小修改。
