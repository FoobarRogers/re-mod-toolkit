# Runtime、Hook 与性能

## 生命周期优先于接口猜测

REFramework 脚本往往在游戏对象建立前就加载。

出现：

```text
singleton == nil
player == nil
component == nil
```

先判断：

- 当前是否还在标题界面
- 是否正在读档 / 切图
- 玩家对象是否刚被销毁
- 管理器是否只在任务 / 据点场景创建

不要立即换 API。

## Hook 前检查清单

Hook 一个方法前先确认：

1. 类型名正确。
2. 方法名与重载正确。
3. 参数数量与类型正确。
4. 静态 / 实例方法判断正确。
5. 调用频率大概是多少。
6. 是否存在更低频、更直接的事件点。
7. Hook 失败后的安全退路是什么。

## Hook 内限制

Pre-hook / post-hook 默认只做：

- 读取少量字段
- 更新 Lua 状态
- 设置“待处理”标志

复杂工作放到后续一次性流程里。

不要在高频 hook 中：

- 遍历大量 managed objects
- 保存 JSON
- 扫文件
- 打几十行日志
- 重新构造大型表

## 状态机优先

复杂 Mod 推荐明确状态：

```text
DISABLED
WAITING_RUNTIME
READY
ACTIVE
SUSPENDED
```

切场景 / 读档时回到 `WAITING_RUNTIME`，重新确认对象可用，再进入 `READY`。

## Managed Object 缓存

缓存对象时至少记录：

- 如何获取
- 何时认为失效
- 如何重新获取

若无法可靠判断有效性，宁可每隔合理周期重新解析一次关键引用，也不要长期保留可能已销毁的实例。

## Reset Script / 热重载

热重载后：

- Lua 全局状态会重建
- 游戏 managed objects 仍可能处于原状态
- hook 是否重复注册要特别检查
- 配置应重新读取
- UI 下拉候选等动态内容应在用户操作时刷新，避免长期缓存旧结果

如果脚本支持 Reset Script，必须验证：
1. 第一次加载；
2. Reset 后；
3. 切图 / 读档后；
4. 多次 Reset 后；
行为均不重复叠加。


## 诊断路由与日志

出现运行时异常时先判定属于哪一层，再选择证据；不要把不同类别混在一次修改里：

- Lua 语法 / 加载错误：保留第一条真实 error、stack trace 与加载阶段；
- `nil` / 生命周期：先确认当前场景、对象是否尚未创建或刚被销毁；
- 方法签名 / Hook：核对类型、重载、参数、静态/实例与 Hook 是否实际命中；
- 状态机 / 配置：记录状态转换、配置版本和迁移结果；
- 其它 Mod 冲突：先用 REFramework + 当前 Mod 的 clean environment，再逐个恢复相关 Mod；
- 性能：优先检查高频 callback / hook 中是否存在枚举、I/O、JSON 或日志轰炸。

日志应能回答版本、场景、关键对象、状态变化、Hook 是否命中和触发条件。高频位置只在状态变化、首次出现或限频后输出，不要每帧打印。

项目复杂 bug 的精确证据链按 Persistence Gate 写入项目事实 / evidence 文件，不再维护独立的 `debugging.md`。
