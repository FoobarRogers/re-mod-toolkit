# 外观资源工作流

## 1. 先识别资源层

典型外观包可能包含：

```text
natives/
└─ <platform>/
   ├─ player/
   │  └─ .../
   │     └─ plxxx/
   │        ├─ *.mesh.*
   │        ├─ *.mdf2.*
   │        └─ 其他模型相关资源
   ├─ textures/
   │  └─ ...
   └─ .../
      └─ *.pfb.*
```

实际目录以游戏和基线 Mod 为准；不要为了符合模板而改路径。

## 2. 资源问题分类

### 模型几何 / 权重
常见现象：
- 穿模
- 胸口空洞
- 衣摆形变
- 侧面挂饰方向异常
- 动作时局部被拉长

优先检查：
- mesh
- skin weights
- bone index / bone mapping
- pivot / bind pose
- 模型导出流程

### 骨骼 / Transform
常见现象：
- 整体偏转
- 翅膀整体歪
- 骨架相对定位错误
- 特定动作后姿态错位

优先检查：
- 父骨
- local/world transform
- bind pose
- LuaBone 的 override
- scene reload 后对象重建

### 材质 / 贴图
常见现象：
- 暗处发白
- 金属反光过强
- 头发层次丢失
- 发光像手电筒
- 透明边缘异常
- 摩尔纹

优先检查：
- texture
- MDF 参数
- FX/shader
- mip
- normal/roughness/metalness
- emissive

### PFB / 实例化
常见现象：
- 资源存在但不生成
- 绑定对象错误
- 非默认路径资源无法实例化
- 某场景加载、某场景不加载

优先检查：
- PFB 引用链
- component
- resource path
- object lifecycle
- loader / cache 行为

## 3. 修改原则

一次测试优先只修改一个层。

推荐命名：

```text
test1_mesh
test2_bone
test3_texture
test4_pfb
```

若必须联合修改，写清依赖：

```text
PFB path 改动
→ 必须同步 mesh path
→ Lua / JSON 无变化
```

## 4. Diff

对资源包比较时，先输出：

- 新增文件
- 删除文件
- 同路径 hash 变化
- 路径变化
- 文件大小显著变化

不要一开始把所有二进制内容解码进模型上下文。


## 5. 症状 → 资源层诊断路由

优先把症状归到最可能的资源层，再做最小 discriminator：

- **完全不加载**：路径、文件名 / 版本后缀、Loader、PFB 引用、缓存 / 刷新；
- **加载但黑屏 / 卡读档**：mesh / bone 不兼容、非法 PFB / 引用循环、Loader 或同路径覆盖冲突、二进制损坏；
- **模型出现但形变**：bone mapping、bind pose、skin weights、父骨 / Transform、LuaBone；
- **姿态正常但外观异常**：texture、MDF、shader / FX、normal / roughness / metalness、alpha / emissive；
- **AVM 状态错误**：JSON 文件名、equipment/body ID、默认 / 差分 / 组合预设、Reset 后候选刷新、schema 版本。

### 缓存与刷新

项目应记录实际有效的刷新方式（切图、进出 CG、回主界面读档、Reset Script、loader reload、完整重启等）。“这次没变化”不能单独证明修改无效；先排除缓存和部署状态。

### 多 Loader 冲突

同时涉及 FirstNatives / LooseFileLoader / 其它 Loader 时，用相同 baseline 分别验证 A、B、A+B，并记录第一个引入异常的组合。不要在多 Loader 全开状态直接猜根因。

对资源问题至少保留文件 hash、路径、修改工具 / 参数、是否加载成功和实机现象；通用失败刹车与证据落盘由全局注入的 DeepSeek Discipline 管理。
