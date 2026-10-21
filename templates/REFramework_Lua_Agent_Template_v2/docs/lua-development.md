# REFramework Lua 开发规范

## 代码组织

推荐最少拆成：

```text
reframework/
└─ autorun/
   └─ <Project>.lua

reframework/
└─ data/
   └─ <project>/
      ├─ config.json
      └─ logs/

lua/
├─ core/          # 可选：状态、配置、通用函数
├─ features/      # 可选：功能模块
└─ localization/  # 可选：文本
```

如果 REFramework 运行环境不适合 `require` 多文件，则保持单文件，但仍按区块分层：
配置 → 状态 → runtime 获取 → 功能逻辑 → hook → UI → 生命周期回调。

## 基本原则

### 1. 不相信对象永远存在

任何 managed object 都可能在：

- 标题界面
- 读档
- 切图
- 任务开始 / 结束
- CG
- MasterPlayer 销毁 / 重建

期间失效。

推荐模式：

```lua
local function get_xxx()
    local obj = sdk.get_managed_singleton("...")
    if not obj then return nil end
    return obj
end
```

不要把启动阶段的 `nil` 误判成 API 不存在。

### 2. 缓存要说明失效条件

可缓存：

- 纯 Lua 配置
- 常量
- 已验证不会变的类型定义

谨慎缓存：

- Player
- GameObject
- Transform
- QuestManager
- UI 实例
- Scene 相关对象

对 managed object 的长期缓存必须有重新获取机制。

### 3. 高频回调只做轻工作

`re.on_frame` / 高频 hook 内：

- 不读写文件
- 不 JSON encode/decode 大对象
- 不全局枚举对象
- 不输出大量日志
- 不重复做稳定状态判断

应使用状态边沿：

```text
旧状态 != 新状态
→ 才执行一次
```

而不是每帧重复应用。

### 4. 配置集中化

推荐：

```lua
local default_config = { ... }
local config = load_config_or_default()

local function save_config()
    ...
end
```

UI 不直接散落写文件。

配置字段新增时：
- 有默认值
- 旧配置缺字段时自动补齐
- 类型异常时回退安全值

### 5. UI 不控制核心生命周期

错误思路：

```text
UI 打开 → 才运行逻辑
UI 关闭 → 功能偷偷停止
```

除非这就是设计目标。

UI 仅修改 `config.enabled`、参数值或发出一次性操作请求。

### 6. 文本集中管理

推荐：

```lua
local L = {
    title = "中文名",
    enabled = "启用",
}
```

后续若支持多语言，再升级成语言表。

## 修改已有 Lua

先回答四个问题：

1. 当前状态由哪些变量保存？
2. 哪个回调/Hook 真正驱动行为？
3. 配置在何时加载、保存？
4. 游戏对象在哪些场景可能重建？

如果这四点没弄清，不先大改结构。
