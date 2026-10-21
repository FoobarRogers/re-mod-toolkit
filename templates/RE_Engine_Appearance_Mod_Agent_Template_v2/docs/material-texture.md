# Material / Texture / FX 工作流

## 问题分类

### 亮度
区分：
- base color 太亮
- emissive 太高
- 环境光响应过强
- roughness/metalness 导致高光
- shader/FX 自发光
- HDR/场景曝光

不要直接把“暗光下太亮”归因于 base texture。

### 金属感
检查：
- roughness
- metalness
- specular
- normal
- MDF 参数

### 透明 / 头纱 / 蕾丝
检查：
- alpha channel
- blend mode
- cutoff
- dithering
- shader 类型
- mip 后的透明边缘

### 摩尔纹 / 高频纹理
检查：
- texture 本身的高频细节
- mipmap
- 压缩格式
- UV 密度
- 法线/细纹叠加
- 远景 LOD/采样

不要只看大本营中模；如果剧情使用高模，也要分别验证。

## 二次元化方向

如果目标是动画风：

- 优先统一 base color / 中间调
- 控制过强的金属高光
- 适度保留阴影层次
- 谨慎使用 emissive
- 远景保证五官可读
- 暗场景不要“像手电筒”

## 测试环境

至少取：
- 普通据点
- 暗光
- 强光/训练场
- 正面/背面
- 中景/远景

若高模和中模表现不同，再增加剧情/CG。

## 补丁策略

一个 texture/material test 尽量只改目标文件。
如果改了多张贴图，记录每张职责和原因，避免后续不知道哪张真正起效。
