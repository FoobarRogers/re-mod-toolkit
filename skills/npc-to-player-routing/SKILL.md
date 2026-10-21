---
name: npc-to-player-routing
description: 把 RE Engine 游戏（Monster Hunter Rise 及其 mod 生态）里的 NPC / 盟友 / 角色模型 mod，判定并路由成"玩家可装备外观 mod"的转换任务，或诊断这类转换包的问题时使用。触发场景：拿到一个 NPC mod 要转成玩家装备；判断某个包该走哪条转换路线（按文件构成）；生成 build-spec 交给构建流程；转换包出问题需要先定位层级（整模浮空/下陷、颈部折角或缝隙、贴图不加载、装备装上后角色无法动弹、头身比例不对、LuaBone offset 异常）。中文触发词：NPC 转玩家、NPC mod 转换、外观转换、转成装备、盟友包转装备、装备槽 id、pl3xx、J0xx、LuaBone 偏移、浮空、脚不离地、脖子折角、carrier 判定、build-spec。只要用户提到要把某个游戏角色做成玩家外观、或要排查这类转换包，就应该用本 skill 先做 intake 与路线判定，再交给 workflow 执行——不要跳过判定直接改文件。
---

# NPC → Player 转换：判定与路由

## 本 skill 的职责边界

**做**：intake（源包身份与可解析性）→ 分类判定（5 个维度）→ 风险门禁 → 输出 `build-spec.json` → 路由。

**不做**：任何资源改写、任何构建、任何打包、任何实机结论。
判定与执行**只通过 `build-spec.json` 通信** —— 不要在这个 skill 里顺手改文件。

**为什么这么切**：同类转换的失败几乎都不是"工具不会用"，而是**判定错**（选错 carrier、
漏掉尺寸差、把非离线的数值当基线）。判定和执行混在一起时，判错会在构建之后才暴露，
而那时已经产出一个看起来正常的坏包。

## 前置：先读工作区约定

工作区根通常是一个 mod 项目目录。开工前确认：

1. 该工作区的 `AGENTS.md`（项目边界、资源硬门禁、Skill 路由）。
2. 若存在 `docs/NPC_TO_PLAYER_PLAYBOOK.md`（三段式操作手册）→ **读它**：
   判定表细节、通用 10 步流程、四类专属修复参数、以及引用历史文档的陷阱都在那里。
3. 若存在 `docs/SKILL_WORKFLOW_BOUNDARY_PROPOSAL.md` 与
   `docs/NPC_TO_PLAYER_COMMON_VS_CLASSIFIED.md` → 按需读（维度判据详表 / 共同不变量与验证矩阵）。
4. **工具随本 skill 携带**（`<skill>/scripts/`，18 个，已用 J017 回归 oracle 验证可独立运行）。
   **优先用 skill 自带的这一份** —— 每个项目重造一遍工具是不稳定性的主要来源。若工作区里已有
   同名脚本，先比对差异再决定用哪份（工作区那份可能带本地改动）。
5. **baseline 数据有两种来源**：
   - 工作区已有 `base/`（研发型项目）⇒ 直接用。
   - **工作区没有 `base/`（无明确 baseline 的批量项目）** ⇒ 从 `<skill>/assets/baseline/` 复制到
     工作区根，得到 `base/f_shadow.json`、`base/m_shadow.json` 与 `base/golden/J017_AstonMachan_R1/`
     （**结构模板**：5 个 PFB + 3 个 dummy + 4 份 LuaBone JSON，不含贴图；贴图按源原路径走，模板不需要）。
     **玩家原生骨架的权威来源就只有 LuaBone 自带的这两个 shadow 文件**（`f_`/`m_` 按性别），
     不要在工作区里再放第二份"由外观 mod 倒算出来的"骨名集 —— 两份并存只会让人不知道该信哪个。
     脚本用的是相对工作区的路径（`Path("base/...")`）⇒ 这一步不做，构建与 LuaBone 都调不起来。

---

## 步骤 1 · intake

| 检查 | 做法 | 不通过时 |
| --- | --- | --- |
| 源包身份唯一 | 只读副本 + 逐文件 SHA256 登记 | 身份不唯一 ⇒ STOP |
| 可解析 | 解开，清点 MESH / MDF2 / TEX / CHAIN / USER / PFB / JCNS / EFX / LUA | 无法解析 ⇒ STOP |
| 是否只读 | **绝不操作用户游戏目录、不修改用户 Mods 库** | 只能读 |
| 是否要处理 | 无 `natives/` 模型内容 ⇒ icon / 过场包 | 直接剔除，不往下走 |

## 步骤 2 · 五项判定（只有这五项改变施工）

其余维度（头部层绑定面、村别、变体号、PFB 版本、盟友标记）都只是 intake 元数据 ——
**记录即可，不影响配方**。

### 维度 A · 承载路径类型

| 看到 | 归类 | 影响 |
| --- | --- | --- |
| `npc/prefab/*/nidXXX.pfb.N` | PFB 覆盖型 | 要写 PFB 引用（从 baseline 模板等长改写） |
| 有模型、**无** PFB | `PATH_OVERRIDE_ONLY` | 靠同路径覆盖；**走私有资源路线必然缺 body chain** |
| 资源直接落在 `player/mod/<f\|m>/plNNN/` 五槽 | 原位型（多为盟友包） | 原位路线通常已弃用（绑专属槽、与源包冲突）⇒ 改走标准私有资源 + PFB |

### 维度 B / C · carrier 是哪一个、有几个

**判据只能用材质与贴图引用，不看文件名、不看大小。** 这一条是硬教训：某包的身体名 mesh 其实是被替换
NPC 的原版躯干（只引用 NPC 默认 mmtr + Fur），真正的整身外观在 `*_hair` mesh 里（引用作者贴图
`dddder4/<npc>/*.tex`，材质含 `tail/body/eye/face/hair`）。按名字选 carrier ⇒ 玩家外观缺头脸发尾。

- 用 `mesh_skeleton.py` 读每个 mesh 的 `material_names` 与关节数。
- 含 `eye/face/hair` 且引用作者贴图的那件 = 外观本体。
- 同作者的不同包**可能把外观挂在不同 mesh 上** ⇒ 每个包都要重判，不能套用上一个包的结论。
- 满足条件的有多件 ⇒ 多组件多槽，必须**逐槽静态证明引用闭合**（build 后必须跑门禁）。

### 维度 D · LuaBone 关键骨齐全度

用 `luabone_generate.py` 对照 baseline 的 `f_shadow`（72 键）跑匹配。

- 缺骨 ⇒ 触发门禁：要么在 spec 里**逐骨显式声明放行**（`lua_bone_allow_missing`，
  实际缺失必须 ⊆ 声明名单），要么 STOP 转人工。**生产门禁不要放宽。**
- 常见缺失集中在 `neck_00_s` / `*_hand_ik` / `*_arm_02_t` 这类目标骨与挂点骨上。
- 缺的若是「目标骨/挂点骨」，往往比补上更安全 —— 源 mesh 里没有该骨时，写它反而会拖走邻近顶点。

### 维度 K · 顶点权重归属

必须**先解析骨身份**再做任何权重判断：BoneInfo 里的索引是 armature 头部一张**蒙皮槽位表**的下标，
不是关节数组下标。把索引当关节下标去并骨，会改坏部件（历史事故：把刘海拉成长尖刺）。

判据形态（度量，不自动决策）：
- 某根玩家骨的顶点区域**在解剖学上不属于它**，且与四周主导骨不一致 ⇒ 症状区域。
- 例：某骨"身体区最低 y − 相邻颈骨 y"在异常包为负、在正常包为正。
- 用 `mesh_rebind_bones.py --scan`（只读）产出候选清单，**把清单呈现给用户**，由用户决定是否改。
- 它需要一个"玩家骨名集"。**现场从 `f_shadow.json` 派生即可，不要另维护一份文件**：
  `python -c "import json;d=json.load(open('base/f_shadow.json',encoding='utf-8'));json.dump({'names':sorted(d)},open('base/_player-names.json','w',encoding='utf-8'),ensure_ascii=False,indent=2)"`
  再 `--player-names base/_player-names.json`。**已验证与历史那份 74 名集合的结果完全一致**
  （只差 `Root`/`Cog` 两个无顶点权重的结构骨，不参与 player-inert 判定）。

### 附加筛查（不做会翻车，成本几秒）

**几何尺寸与脚底基准**（只读，读顶点缓冲）：

```python
import sys; sys.path.insert(0, 'scripts')
import mesh_rebind_bones as m
data = open(mesh_path, 'rb').read(); geo = m.locate_geometry(data, None)
pos = m.read_positions(data, geo); ys = [p[1] for p in pos]
print(min(ys), max(ys), max(ys) - min(ys))     # 脚底 y-min、总高
```

把结果与**玩家基线**（`f_shadow` 推得的脚底 y ≈ −1.05 m）比。差得多（历史上遇到过高的 21 cm、
总高只有 0.82 倍、骨架腿链只有 0.76 倍）⇒ 直接穿在玩家身上会**整模悬空或沉入地面**。
这类包必须走"整模垂直对齐"分支（见 workflow 的 `vertical_align`），**不要**靠缩放去凑比例 ——
源可能是小体型/小孩网格，缩放会把设定改错。

---

## 步骤 3 · 门禁（命中即停，输出 `MANUAL_REVIEW_REQUIRED` + 四要素）

1. 主体 visual carrier 无法唯一确定（多组件且材质判据不足以定主次）。
2. 需要靠猜测二进制字段才能继续。
3. LuaBone 关键骨缺失且不在声明放行名单内。
4. PFB 出现模板之外的未知引用 / 引用不闭合。
5. 需要覆盖普通玩家装备槽模型才能成立。
6. 需要操作用户游戏目录、或需要修改用户 Mods 库。

**未决项优先转人工**：体积/表关联类的未决问题（关键骨门禁策略、某类包必然缺 chain 的补法是否安全、
未登记资源版本能否进生产、头部层机制、某些只登记未实机的分类）**不得静默自动化**。

---

## 步骤 4 · 输出 build-spec

按 `assets/build-spec.template.json` 填。**字段名一律以 `scripts/taxonomy_build.py` 的实际读取为准**
（2026-09-30 曾因模板写成顶层 `carriers`/`dummy_roles` 而漂移，已按源码校正）。模板里标了两类消费者：

**① 构建器直接消费**
- `private.carriers[]` —— 每个给 `role`（放哪个槽）、`stem`（源 mesh 路径）、`rename`（私有资源名）；
  **未承载模型的槽写 `dummy: true`**；`private.leg_reuses` 一律 `"arm"`（全项目没有 `JRleg###`）。
- `prefab.template_dir` + `prefab.rewrite[]`（+ `prefab.filename_rewrite[]`，仅目标槽号 ≠ 模板槽号时需要）。
- `textures[]`、`copy_paths[]`、`extra_files[]`（chain 的补/改名落这里）、`head_layer[]`。
- `allow_mesh_version[]` / `register_mesh_version[]`、`lua_bone_allow_missing[]` / `lua_bone_mirror`。
- `modinfo_name` / `version` / `modinfo_description`（一律新建，不含源资源内容）。

**② §7 条件分支消费**（分支处理完再交给构建器）
- `route[]` —— **本 skill 唯一的判定输出**，取 `weight_surgery` / `vertical_align` / `chain_fill` 任意组合。
- `rebind[]`（§7.1，构建**前**改源 mesh）、`vertical_offset_y`（§7.2，构建**后**改 4 份 LuaBone JSON 的
  `Waist_00.y`）、`chain_fills[]`（§7.3，转写进 `extra_files[]`）。

**写完 spec 必须自检**：`rg 'spec\.get\(' scripts/taxonomy_build.py` 对着核一遍字段名 ——
**漂移不会报错，只会静默不生效**（这是实测踩过的坑）。

**不要把 baseline 当成"目标值"**：baseline（Golden）提供**结构模板与回归 oracle**
（PFB 模板、dummy 资源、架构、公式正确性），**不提供**新包应有的数值。
另外注意 baseline 与某些样本存在"逐字节相同"的关系 —— 那是**来源关系**，不是可照抄的配方。

## 步骤 5 · 路由

| 情况 | 去哪 |
| --- | --- |
| 门禁全通过 | 路由到工作区的构建 workflow（主路径 10 步 + 按 `route[]` 触发条件分支） |
| 命中门禁 | `MANUAL_REVIEW_REQUIRED`，把"现象 / 证据 / 卡在哪条判据 / 需要用户裁决什么"四要素写清 |
| 是**诊断**而非新建（包已存在、出现浮空/错位/折角） | 先按症状定位层级，再回到对应维度；不要从零重跑整条流程 |

**诊断入口速查**（详细判据见工作区的 `docs/NPC_TO_PLAYER_PLAYBOOK.md` 第三段）：

| 症状 | 先查 |
| --- | --- |
| 整模浮空 / 脚不离地 / 沉入地面 | 维度 B/C 之后的**几何尺寸筛查**（脚底 y 与玩家基线的差） |
| 颈部折角、转头时露出缝隙 | 维度 K（顶点权重归属），扫颈管内相邻顶点权重差 |
| 贴图不加载 | mdf2 引用 vs 包内实体的闭合性（原路径保留策略是否被破坏） |
| 装备装上后角色无法动弹 | PFB 引用闭合（悬空 chain 是典型原因）+ carrier 是否选错 |
| 头身比例不对 | 先确认源是不是小体型/小孩网格；再看是否有人为缩放 |

---

## 工具路由表（步骤 → 脚本 → 命令）

工具在 `<skill>/scripts/`。**回归门禁**：任何工具改动后必须重跑下面这条，必须报
`BYTE-IDENTICAL (9908 bytes)`：

```bash
python <skill>/scripts/luabone_generate.py   --mesh base/golden/J017_AstonMachan_R1/mod/natives/STM/player/JRRB/J017/JRwst017.mesh.2109148288   --shadow base/f_shadow.json --out /tmp/o.json   --compare base/golden/J017_AstonMachan_R1/mod/reframework/data/LUABoneSystem/custom/JRwst017.json
```

| 步骤 | 脚本 | 用途 / 关键参数 |
| --- | --- | --- |
| 1 intake | `inventory.py` | 分类 + 自引用门禁 + carrier 判定（SPLIT / SINGLE-CARRIER / HYBRID） |
| 1 intake | `inspect_npc_package.py` | 单包清点：逐文件 sha256、每 mesh 版本/关节/材质/`f_shadow` 差集、`binding_strategy`（`npc_side`/`player_slot`） |
| 1 intake（可选） | `survey_npc_variants.py` | 跨包普查（传 mod 库根目录）：形态 tags，用来先摸清整个库再选包 |
| 2 判定 B/C | `mesh_skeleton.py` | 读 `material_names` + 关节数 ⇒ carrier 候选表 |
| 2 判定 D | `luabone_generate.py` | 匹配报告：matched / missing target bones / keys_without_f_shadow_base |
| 2 判定 K | `mesh_rebind_bones.py --scan` | **只读**列 player-inert 加权骨与候选清单（**不自动决策**） |
| 2 附加筛查 | `mesh_rebind_bones.py`（调 `locate_geometry` + `read_positions`） | 顶点 bbox 高与脚底 y-min ⇒ 判是否需要垂直对齐 |
| 3 门禁 / 6 验证 | `verify_package_refs.py --slot N [--baseline 源包]` | 引用闭合：PFB→实体、对象名→部件、**LuaBone JSON ↔ 部件名**、装备 id 唯一；`--baseline` 区分 INHERITED 与自引入 |
| 4b 权重修正 | `mesh_rebind_bones.py --map 子骨:父骨` | 区域限定 `--region-radius-below` / `--only-if-dominant` / `--ramp-y FULL:ZERO`；**硬前置**：骨身份须经 `read_skin_slots` 解析 |
| 5 构建 | `taxonomy_build.py` | 参数化构建器，**由 spec JSON 驱动**（不假设槽位）；内含构建后引用闭合硬门禁 |
| 6 静态验证 | `static_validate.py` / `test_static_validate.py` | 独立读最终包（不复用改写过程的中间状态）；输出 STATIC PASS / FAIL / MANUAL_REVIEW_REQUIRED |
| 6 残留扫描 | `fullscan.py` | 旧 namespace / 旧 id / 不必要覆盖 / 悬空路径（**NPC 贴图路径里的 NPC id 是允许项**） |
| 7 换槽 | `reslot_package.py` | **只改路径**，含 LuaBone JSON 文件名；改名前后逐成员 SHA256 必须相同 |
| 8 打包 | `test_package.py` | test 包命名规范；只改文件名不改内容，前后比对 SHA256 与成员表 |
| 诊断（颈部/姿态） | `head_neck_axis.py`、`skin_motion_predict.py` | 骨架平移旋转对照；离线预测"某骨一动，皮肤被拖多少"（`--crease --centerline` 看方向性症状） |
| 诊断（PFB/JCNS） | `inspect_npc_pfb.py`、`inspect_jcns.py` | PFB 两张绝对寻址表 + 一张相对表；JCNS 字段与骨名哈希 |

**没有随 skill 携带的**（本项目研究分支或专用编排，需要时从项目取）：
`npc2player.py`（Golden 专用编排，作者自己注明不是通用工具）、`gen_taxonomy_docs.py`（生成该项目的分类文档）、
`compare_skeleton_contexts.py`、`source_resource_graph.py`、`source_fidelity_matrix.py`。

## 边界（不要越界）

- 不改用户游戏目录、不修改用户 Mods 库（只读）。
- **不得宣称实机 PASS** —— 实机由用户执行，本 skill 只出静态结论与待验证清单。
- 未决项不得静默自动化。
- 工具用 `<skill>/scripts/` 自带的那份；需要改工具时改 skill 里的，改完必须重跑 J017 oracle。
- 判定与执行分离：本 skill 的产出止于 `build-spec.json` 与路由结论。
