# REFramework API wiki（上游文档的本地副本）

> **2026-09-19 迁移注记**：本目录原在 `D:\DeepSeek\Feminine-Animation-Replacer-Rebuil\`，现移入用户级
> skill `reframework-api-reference` 的 `references/wiki/`，供所有项目共享。下文说的"本项目"、
> 游戏路径（`E:\...MonsterHunterRise\`）、`tools/` 脚本与 autorun 里的 mod 均指**原 FAR 项目语境**；
> 各项目自己的实测结论以各自 docs/ 为准。查 API 的入口是这个 skill 的 `SKILL.md` 索引。

> **这不是本项目的文档**，是上游 [REFramework Book](https://cursey.github.io/reframework-book/) 的
> markdown 源码搬运副本，放在这里只为了**离线可查、可被脚本 grep**。
> 本项目自己的 Lua 结论写在 `docs/reframework-lua-notes.md`，两者不要混。

- **上游**：<https://github.com/cursey/reframework-book>（渲染站点 <https://cursey.github.io/reframework-book/>）
- **搬运于**：2026-09-19
- **上游 commit**：`acf44b336bdedb44afd6830fcc2dc2c4cf1eaaf0`（committer date 2026-03-07）
- **搬运范围**：`src/**`（全部 markdown）+ `book.toml` + `concat.py`，**逐字节未改**（53 个文件 / 212,840 字节）
- **上游许可**：⚠ **未声明任何 license**（仓库根目录没有 LICENSE）。见文末「版权与再分发」。

## ★ 读到这一页之前：先别整包读

全量 **212,840 字节 ≈ 53K token**，整读一遍就等于把一轮上下文烧掉。
按下面的路由表**只读一页**，单页最大 4.5K token、常见 0.3–2.8K。

另外两份资料与本 wiki 分工不同，别搞混：

| 要查什么 | 去哪 |
| --- | --- |
| **REFramework 平台 API**（`sdk.*` / `re.*` / `imgui.*` / 托管对象怎么调） | **本 wiki** |
| **MHRise 游戏自己的类型与成员**（`snow.player.*` / `via.motion.*` 有哪些方法） | 游戏自带的 `il2cpp_dump.json`（`E:\...\MonsterHunterRise\`），用 `tools/dump_il2cpp_members.py` 查 |
| 本项目踩过的坑与硬结论 | `docs/reframework-lua-notes.md`、`docs/lua-player.md` |
| 游戏里**能跑**的写法（最硬的证据） | `<游戏>\reframework\autorun\` 里其它 mod（如 `autoBuff.lua`、`Evil_HaloAnimate.lua`），它们在本机 MHR + 本机 REFramework 上实测有效 |

**优先级**：项目实机实测 > 本 wiki > 旧教程 / 记忆。上游文档也会落后于 nightly（本副本最后更新 2026-03-07）。

## 路由表（按"我要干什么"找页）

| 症状 / 任务 | 读这个 | 体积 |
| --- | --- | --- |
| **托管对象到底怎么调**（字段、方法、冒号糖、重载、`get_Item`） | `src/api/types/REManagedObject.md` | 4.6K ≈ 1.2K tok |
| `sdk.*` 全部函数（单例 / 类型 / 调用 / hook / 类型转换 / 创建实例） | `src/api/sdk.md` | 11.2K ≈ 2.8K tok |
| 生命周期回调（`on_frame` / `on_draw_ui` / `on_script_reset` / application entry） | `src/api/re.md` | 8.5K ≈ 2.1K tok |
| 方法签名/重载怎么传、返回值怎么读 | `src/api/general/Notes-on-Method-Arguments.md`、`src/api/general/Notes-on-Return-Types.md` | 1.2K+0.5K |
| `RETypeDefinition` / `REMethodDefinition`（反射对象本身） | `src/api/types/RETypeDefinition.md`、`src/api/types/REMethodDefinition.md` | 2.0K / 0.7K |
| 组件与 GameObject（`via.Component` 的 `get_GameObject` 从哪来） | `src/api/types/REComponent.md` | 0.2K |
| 容器 / 数组（`get_Count` / `get_Item` / `self[i]`） | `src/api/types/SystemArray.md`、`REManagedObject.md` 的 `self[i]` 段 | 0.8K / — |
| 写脚本的经验与禁忌（性能、hook 选择、常见错误） | `src/api/general/best-practices.md` | 3.8K ≈ 1K tok |
| 配置/文件/日志/JSON | `src/api/fs.md`、`src/api/log.md`、`src/api/json.md` | 1.1K/0.3K/2.6K |
| 画面绘制（`draw.*`、ImGui、imnodes、imguizmo） | `src/api/draw.md`、`src/api/imgui.md`、`imnodes.md`、`imguizmo.md` | 2.3K / 15.2K / 2.1K / 0.3K |
| 线程 | `src/api/thread.md` | 1.3K |
| **怎么现场发现对象的真实结构**（本项目最该先看的一页） | `src/object_explorer/object_explorer.md`、`src/api/object_explorer.md` | 9.5K / 0.3K |
| 可直接抄的写法示例 | `src/examples/Example-Snippets.md`、`Example-Scripts.md` | 17.9K ≈ 4.5K tok |
| C# 插件侧（本项目不用，仅存档） | `src/api_cs/**` | 89.4K ≈ 22K tok |
| 其它工具（bhvt 编辑器 / chain viewer） | `src/bhvt_editor/`、`src/chain_viewer/` | 1.7K / 0.6K |

## 两条已经咬过我们的契约（写在这里免得下次又去猜）

原文在 `src/api/types/REManagedObject.md`，这里只摘结论：

1. `self.foo` 对**方法**返回的是 `REMethodDefinition`（**userdata，不是 Lua function**）；
   对**字段**返回字段值。⇒ 用 `type(o[name]) == "function"` 去判断"这个方法能不能调"是错的，
   会把所有方法判成"无此方法/字段"。
2. `self:foo(bar)` 对**非重载**方法可用；**重载方法必须** `self:call("foo(完整签名)", args...)`，
   冒号糖**不做重载解析**。⇒ 拿不准有没有重载时，一律用 `call` + 完整签名（本仓库 `autoBuff.lua`
   等实测可用的 mod 就是这么写的）。

## 刷新（上游有更新时）

```bash
# 1) 抓上游整包（约 65 KB）并记录 commit
curl -s "https://api.github.com/repos/cursey/reframework-book/commits/master"   # 记下 sha 与日期
curl -sL -o /tmp/rfb.tar.gz "https://codeload.github.com/cursey/reframework-book/tar.gz/refs/heads/master"

# 2) 解包替换 src/、book.toml、concat.py（保持"逐字节未改"）
rm -rf /tmp/rfb && mkdir /tmp/rfb && tar -xzf /tmp/rfb.tar.gz -C /tmp/rfb
cp -r /tmp/rfb/reframework-book-master/src .
cp /tmp/rfb/reframework-book-master/book.toml /tmp/rfb/reframework-book-master/concat.py .

# 3) 核对总量（2026-09-19 那版是 53 个文件 / 212,840 字节 markdown）
find . -type f | wc -l
find . -type f -name "*.md" -exec cat {} + | wc -c
```

刷新后**必须**回来改本文件顶部的「搬运于 / 上游 commit」，并确认「两条已经咬过我们的契约」是否仍然成立。
（本项目反复吃过"仓库改了、现场还是旧副本"的亏 —— 这里的副本同样会过期，别拿它当永久真理。）

## 版权与再分发

上游**没有声明 license**，按默认版权即"保留所有权利"。因此：

- 本副本只作**本地参考**（离线查、grep、喂给 agent），**不要**打进 mod 发布包、也不要推到公开仓库；
- 引用结论时写"依据 REFramework Book"并附上游链接，不要把上游正文大段抄进我们自己的文档；
- 若将来要公开这一目录，先去上游确认授权（提 issue / 问作者）。
