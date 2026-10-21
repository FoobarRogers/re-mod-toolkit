# scripts/ —— 批量转换工具链

> 状态：**已实现**（首次实际转换任务：J018 / NPC709 / Oguri Cap / PL279）。
> 各工具的输入 / 输出契约见下，实现不得偏离 `docs/NPC_TO_PLAYER_CONVERSION_WORKFLOW_v0.2-draft.md`
> 的对应 Phase 定义。

## 实现文件与 Phase 对应

| Phase | 实现文件 | 说明 |
| --- | --- | --- |
| T / F 底层 | `mesh_skeleton.py` | MESH → `bone → LocalT`（+ 内存中的只读 `rotation`）。生产只支持 version `0x014111C0`；研究分支可用 `allowed_versions=` 显式放开（生产调用点不传该参数）。**不感知 `f_shadow.json`**。`rotation` 字段**不进入 `to_report()`**，以保持已落盘 evidence 与 Phase F 输出契约逐字节稳定 |
| T / F 上层 | `luabone_generate.py` | `LocalT → offset`；case-insensitive exact-name 匹配；`missing_policy = golden_compatible_zero` |
| A / B | `inventory.py` | 分类 + 自引用门禁 + skeleton-carrier 判定（SPLIT / SINGLE-CARRIER / HYBRID） |
| G | `pfb_equal_length_replace.py` | UTF-16LE 等长 token 替换 + 改动区间声明 + 越界字节统计 |
| H | `static_validate.py` | **独立读取最终候选包**做验证，不复用改写过程的中间状态 |
| I | `fullscan.py` | 残留 / 错误 ID / 不必要覆盖 / 悬空引用扫描 |
| A~G 编排 | `npc2player.py` | 串起全链，产出 `conversion-manifest.json` 与包内 README |
| 打包命名 | `test_package.py` | test 包命名规范（`docs/project-workflow.md` §3.1）。`name` 按规范拼包名（输入容错 `709` / `NPC709`）；`rename` 把已有 zip 改成规范名并同步 `.manifest.json` / `.sha256`。**只改文件名、不改包内容** —— 执行前后比对 zip 的 SHA256 与成员表（成员名 / CRC / 大小），不一致即报错并回滚；对已合规的包幂等；`--dry-run` 只预览 |
| 换装备 id | `reslot_package.py` | 把包从一个 player 装备 id 换到另一个（如 `pl279` → `pl314`）。**只改路径**：`pl***` 目录段 + 文件名里的 `<slot>.`（后者同时覆盖 LuaBone custom JSON，因为其文件名必须等于部件对象名）。刻意不动文件名里的 `pl<slot>` 前缀（那是源 NPC 侧资源名）与 `JRRB/J0##`。改名**前**按 UTF-16LE 扫全部成员**内容**，一旦发现内容引用旧 slot 即 `MANUAL_REVIEW_REQUIRED` 停止；改名后逐成员比对内容 SHA256 必须完全相同。失败自动回滚 |
| 引用闭合 | `verify_package_refs.py` | `reslot_package.py` 证明"只改了路径"，本工具证明"引用仍闭合"：①PFB `path_table` → 包内实体 ②PFB 对象名 → 包内部件 ③**LuaBone JSON 文件名 ↔ 部件名**（最容易漏的一处）④包内装备 id 是否唯一 ⑤引擎内置引用白名单（`systems/rendering/`、`Sound/Asset/`）。带 `--baseline <源包>` 时，源包已有的问题标为 `INHERITED`，不计入 FAIL —— 用来区分"我们引入的"与"继承的" |

## 研究分支只读工具（2026-09-25 新增）

对应 `docs/research/NPC709_FACE_RUNTIME_JCNS.md`。全部**只读、可重放、可审计**，
不参与生产候选构建。

| 工具 | 输入 | 输出 | 说明 |
| --- | --- | --- | --- |
| `inspect_npc_pfb.py` | NPC 的 `.pfb.N` | 源资源引用图 JSON/MD | 解析 PFB 的两张绝对寻址引用表 + 一张**相对 `strings_end` 寻址**的引用表。生产只认 v7；研究用 `--allow-version N` 可放开（实测 v1 / v6 / v7 同布局） |
| `inspect_jcns.py` | `.jcns.N`（+ 可选 mesh 取骨名表） | 已确认字段 / 未知字段报告 | 内置 `murmur3_x86_32(utf-16-le, seed 0xFFFFFFFF)` 骨名哈希解析 |
| `compare_skeleton_contexts.py` | 两个 mesh | 骨架差 JSON/MD | joint 集合差 + 共同 joint 的 LocalT delta 与旋转夹角分档统计。`--allow-version` 的语义是**追加**到已支持集合，不是替换 |
| `head_neck_axis.py` | 两个 mesh | 骨架平移 / 旋转 / 累积世界变换对照 JSON/MD | **2026-09-25 新增**。在 `compare_skeleton_contexts` 之上补三件它没有的事：①每根骨的旋转**轴角**（角度 + 轴向量，不只夹角）②**FK 累积世界变换**（`W(child) = Local(child) × W(parent)`，行向量约定）给出关节世界位置与世界朝向差 ③内置 FK 自校验（世界矩阵行范数偏差）。动机：LuaBone 只表达 Translation，**"LocalT 已对齐"不能推出"头颈姿态正确"**。用于 `docs/research/J018_HEAD_NECK_RATIO_DIAGNOSIS.md` |
| `source_fidelity_matrix.py` | 引用图 JSON + 源包 + 候选包 | 六态忠实度矩阵 JSON/MD | `RETAINED / RETAINED_RENAMED / REPLACED / DROPPED_RUNTIME_REVIEW / SOURCE_MISSING / SOURCE_NOT_APPLICABLE`；**不自动产生 `DROPPED_CONFIRMED_SAFE`** |
| `inspect_npc_package.py` | 解压后的 NPC 包根目录 | 包结构清点 JSON | 逐文件 sha256 + 每个 mesh 的版本/关节/材质/f_shadow 差集 + 每个 mdf2 的材质/贴图/chain + 每个 PFB 的引用表 + **`binding_strategy`（`npc_side` / `player_slot`）自动判定** |
| `survey_npc_variants.py` | **mod 库根目录**（每个子目录一个包） | 全系列形态普查 JSON/MD | 逐包一行：`prefab_dir` / 玩家脸槽 / 玩家发槽 / NPC 侧 face·hair / body 基名 / chain 基名 / 贴图 / LuaBone / **形态 tags**（`PATH_OVERRIDE_ONLY`、`NPC_PREFAB_OVERRIDE`、`PLAYER_FACE_SLOT`、`PLAYER_HAIR_SLOT`、`ARMOR_SET_INPLACE`）。**只 `os.walk` + 读文件名与文件头，不打开/不修改资源** |

`inspect_npc_package.py` 的存在理由：**版本、材质绑定、槽位绑定策略三者必须一起看**，
才能决定"这次转化要搬哪些资源"。单看一个 mesh 或一个 PFB 不足以做这个判断
（NPC4 系列实测，见 `docs/research/NPC4_HAMON_PAZ_CONVERSION_DIRECTION.md` §2.6）。

`survey_npc_variants.py` 的存在理由：单包视角会漏掉**跨包规律**。
全系列 64 包普查证明了三件单看一个包看不出来的事：
**通用共用件**（305932 那份出现在 41 包/97 槽位）、
**盟友包 ⟺ 装备形态 10/10 对应**、
**村别可由 `_MR` 消息后缀客观判定**。
见 `docs/research/NPC_SERIES_STRUCTURE_TAXONOMY.md`。

## 分类学 Test 工具链（2026-09-25 新增，研究用途）

对应 `TODO_WORKFLOW_Taxonomy_Runtime_Validation_v0.1-draft.md`。

| 工具 | 用途 |
| --- | --- |
| `mesh_rebind_bones.py` | **顶点蒙皮归属的诊断与等长改写**（2026-09-26）。`--scan` 只读列出"玩家骨名集之外"的加权骨及其"与玩家骨混合"的顶点数（候选清单，**不自动决策**）；`--map 子骨:父骨` 做等长改写，只动 BoneInfo 字节，可加 `--region-below-y` / `--region-abs-x-below` / `--region-radius-below`（**按到 `Neck_00`→`Head_00` 轴的距离限定**，用于把改动锁在真正的颈管内）/ `--only-if-dominant` 定点到某块区域，并用 `--ramp-y FULL:ZERO` 做**按高度渐变**的部分转移（避免硬切接缝）、`--body-only` 排除装饰骨主导的顶点。**硬前置：骨身份必须经 armature 头部的蒙皮槽位表解析**（`read_skin_slots`：`S=u64@0x30`，`u32@S+0` 关节数、`u32@S+4` 槽位数、`u16×slot_count@S+0x30` 槽位→关节），把 u8 当关节下标会改坏部件（test3 的实际教训）。玩家骨名集 = `base/player-bone-names.json` |
| `skin_motion_predict.py` | **离线预测"头一动，各区域皮肤被拖动多少"**（2026-09-26，只读）。给定头骨绕自身原点旋转（`--deg` + `--axis roll/yaw/pitch`），用线性混合蒙皮算各**解剖带**（锚在颈骨，不随头骨位置变）的中位/最大位移 cm，并相对头壳刚性顶点归一化；`--head-local-y/-z` 可模拟"把头骨枢轴下移"（同时改绑定与运行时骨架，绑定姿态下形变恒为 0）。用途：test5 实机失败后，判定"头骨枢轴过高 ⇒ 颈顶被甩得远"是否成立（结论：**不成立**，npc709 0.49 cm 相对 0.25 vs 正常包 0.58/0.22、0.74/0.21）。自校验：能把 test4 的 108 个顶点精确识别出来。`--dom-in 骨名,骨名` 只统计指定主导骨的顶点，**排除头发/耳朵等装饰件对 max 的污染**；`--rotate 骨名`（可重复）把旋转施加到指定骨（默认只旋 `Head_00`）——用于量「锁骨/颈骨/任意骨一动，皮肤被拽多少」，test6 的判据即由此得出（锁骨 12° 下 A1 颈下带 max 1.043 cm vs 正常包 0.265/0.387）；`--crease --binw H` 输出沿颈高的位移剖面与**相邻层跳变**（只统计相邻分箱，空箱会造成假跳变）；`--centerline` 输出变形后颈部**中心线 center_x(y)、逐层无偏 Δx（变形后−原位）**与「颈根下 1/4 / 上 3/4」中心线倾角 —— 用于量化『下段向右斜、上段竖直』这类**方向性**症状（center_x 绝对值受采样影响，判断方向必须用 Δx）（首版没加该过滤时，颈带 max 被后脑长发主导，读数不可比）。修正后结论：npc709 颈顶带中位 0.247 cm，**小于** npc002 0.569 / npc746 0.665；「领口/上胸」带 max 源 mesh 4.309 cm、test4 产物与两个正常包均 0.000 |
| `source_resource_graph.py` | TODO 03：把源包每个资源映射到角色枚举（16 类 + 4 个已声明扩展），有 PFB 时按 PFB 实际引用建图，无 PFB 时显式说明 path override |
| `taxonomy_build.py` | TODO 06/07：**参数化**构建器。不假设任何槽位（`npc2player.py` 硬编码了 Golden 的 wst 承载 + arm/body/helm dummy，TODO 06 禁止套用）。每个 Test 由 spec JSON 显式声明"哪个槽放什么" |
| `test_static_validate.py` | TODO 08：独立读最终包做静态验证，结果只有 `STATIC PASS` / `STATIC FAIL` / `MANUAL_REVIEW_REQUIRED` |
| `gen_taxonomy_docs.py` | TODO 02~09：从已落盘证据派生四个工作区的文档（不引入未落盘的判断） |

**版本登记语义**（TODO 08）分两种，不要混：
`spec.allow_mesh_version` = 允许**解析**（承载件，要算 LuaBone）；
`spec.register_mesh_version` = 随包携带但只复制。
两者都阻断未声明版本，但只有前者能让新版本进生产讨论。

**`npc2player.py` 的定位**：它是 J018 那次转换的 Golden 专用编排，**不是通用批量工具**。
批量/多类型请用 `taxonomy_build.py`（参数化）。在 TODO 11 的边界提案确定前，不要用
`npc2player.py` 处理非 Golden 形态的包。

⚠ 以上工具全部**只读源**、只写工作区与 `dist/research-taxonomy/`。
用户 Mods 库的部署与游戏内实测由用户手工执行，工具不得代为操作。

可用作跨工具库：

```python
from inspect_jcns import bone_name_hash, murmur3_x86_32
```

**回归 oracle**（工具正确性的硬验收，任何改动后必须重跑）：

```bash
python scripts/luabone_generate.py \
  --mesh base/golden/J017_AstonMachan_R1/mod/natives/STM/player/JRRB/J017/JRwst017.mesh.2109148288 \
  --shadow base/f_shadow.json --out <tmp>.json \
  --compare base/golden/J017_AstonMachan_R1/mod/reframework/data/LUABoneSystem/custom/JRwst017.json
# 必须 BYTE-IDENTICAL (9908 bytes)
```

## 计划工具契约（对应 workflow Phase）

### Phase A — `inventory`
- 输入：NPC mod 解压目录
- 输出：`source-tree.txt` + `inventory.json`（分类：MESH / MDF2 / TEX / CHAIN / USER / PFB / JCNS / EFX / LUA / OTHER）
- 约束：只读，不修改任何源文件

### Phase B — 依赖闭包辅助
- 输入：`inventory.json`
- 输出：REQUIRED / OPTIONAL / EXCLUDED / UNKNOWN 分类表
- 约束：目标是最小完整闭包；主体识别结果必须人工确认后才能进入后续 Phase

### Phase F — `luabone_generate`
- 输入：目标 NPC mesh + `base/f_shadow.json`
- 输出：与私有模型同名的 custom JSON + 报告（matched bones / aliases used / missing target bones / missing base bones / max abs offset）
- 约束：按同名骨逐轴计算 target − base；允许明确 alias，禁止模糊猜骨；关键骨匹配不完整即停（workflow §5 条件 4）

### Phase G — `pfb_equal_length_replace`
- 输入：Golden PFB + 已确认的字符串替换声明（J### / JR*###，UTF-16LE 等长）
- 输出：改写后 PFB + 变更区域声明
- 原则：Minimum Rewrite / Equal-Length Preferred / No Blind Numeric Replace / Explain Every Changed Region

### Phase H — `static_validate`
- 输入：改写前后 PFB
- 输出：`pfb-rewrite-report` + `pfb-after-refs` + binary diff
- PASS 条件（workflow Phase H）：文件大小不变；历史私有路径残留 = 0；新引用全有实体；changed bytes 全落在声明区域；无未知二进制变化

### Phase I — `fullscan`
- 输入：整个候选包
- 输出：旧 namespace / 旧 J### / 旧资源私有名 / 错误 J### / 不必要 `player/mod/.../plxxx` 覆盖 / 悬空路径清单
- 约束：NPC texture 原路径中的 NPC ID 是允许项，不得当成旧 ID 清理

## 通用约定

- 所有输出落盘 `work/<task>/reports/` 或 `evidence/`，stdout 只返回摘要与指针。
- 触发 `docs/NPC_TO_PLAYER_CONVERSION_WORKFLOW_v0.2-draft.md` §5 任一 STOP 条件时，
  输出 `MANUAL_REVIEW_REQUIRED` 并停止，不做进一步自动修改。
- 工具只在工作区内读写；Mod Manager 部署与游戏内实测由用户手工完成。
