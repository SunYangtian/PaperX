# NeoVerse 解读

PDF: `papers/pdfs/2601.00393_NeoVerse_Enhancing_4D_World_Model_with_in-the-wild_Monocular_Videos.pdf`

arXiv: https://arxiv.org/abs/2601.00393

## 一句话定位

NeoVerse 是一个面向 **4D world modeling** 的 reconstruction + generation 混合系统。它从 in-the-wild monocular videos 出发，先用 pose-free feed-forward 4DGS reconstruction 得到动态 4D Gaussians，再把这些 4DGS 在 novel trajectory 下渲染成 degraded conditions，交给视频生成模型修复/补全，得到高质量、时空一致、可控相机轨迹的视频。

它的核心问题不是“如何实时交互”，而是：**如何让 4D world model 能利用廉价、大规模、无多视角标注的野外单目视频训练**。

## 1. 总体流程

NeoVerse 有两大模块：

1. Pose-free feed-forward 4DGS reconstruction：从 monocular video 中直接预测 camera、depth、Gaussian attributes 和动态 motion。
2. Reconstruction-guided video generation：把 4DGS 在用户指定的 novel camera trajectory 下渲染成 degraded renderings，作为视频 diffusion model 的条件，生成高质量 novel video。

训练时的关键闭环是：

- 输入一段普通单目视频；
- sparse keyframes 做 on-the-fly 4DGS reconstruction；
- 把 4DGS 渲染为 degraded conditions；
- 原始 monocular video 自身作为 target；
- 这样就不需要昂贵的 multi-view 4D 数据，也不需要离线预重建整个训练集。

## 2. 4DGS Reconstruction

### 基础：VGGT + Gaussianization

重建模型部分基于 VGGT backbone。VGGT 原本擅长从多帧图像估计 camera / depth / geometry，但 NeoVerse 做了两件事：

- dynamic：加入 bidirectional motion modeling；
- Gaussianized：让网络直接输出 4D Gaussian Splatting 属性。

每个 Gaussian primitive 包含：

- 3D position `mu`；
- opacity `alpha`；
- rotation `r`；
- scale `s`；
- spherical harmonics `sh`；
- lifespan `tau`；
- forward / backward linear velocity `v+`, `v-`；
- forward / backward angular velocity `omega+`, `omega-`。

### Bidirectional motion modeling

NeoVerse 不只预测单向速度，而是同时预测：

- `t -> t+1` 的 forward motion；
- `t -> t-1` 的 backward motion。

具体做法是对 frame features 做两个方向的 cross-attention：

- forward branch：用当前帧 features query 下一帧 features；
- backward branch：用当前帧 features query 上一帧 features。

这样得到的 motion features 用来预测 Gaussian 的双向线速度和角速度。

这个设计服务于两个目的：

- 支持 keyframe 间的 temporal interpolation；
- 支持 bullet-time / slow-motion / intermediate timestamp rendering。

### Sparse keyframe reconstruction

为了让训练可扩展，NeoVerse 不对长视频每帧都跑重建网络。

给定 `N` 帧视频：

- 只选 `K` 个 sparse keyframes 作为 reconstruction input；
- 预测这些 keyframes 的 4DGS；
- 对非 keyframes，用 bidirectional motion 把最近 keyframe 的 Gaussian 转移到 query timestamp；
- 然后渲染所有 `N` 帧。

这显著降低了 on-the-fly reconstruction 的训练成本。

## 3. Degradation Simulation

NeoVerse 认为生成模型要学会从低质量 novel-view rendering 中恢复高质量视频。问题是：单目视频没有真实 novel-view paired data。所以它设计了在线退化模拟，把普通 monocular video 变成训练 pair。

### 3 类退化

1. Visibility-based Gaussian Culling  
   对原相机轨迹做随机变换，得到 novel trajectory；根据深度和可见性判断哪些 Gaussian 在新视角下不可见，把这些 Gaussian cull 掉，再渲染回原视角，模拟 occlusion / missing regions。

2. Average Geometry Filter  
   在 depth discontinuity 边缘，深度网络容易产生 flying edge pixels。NeoVerse 对 novel trajectory 下的 rendered depth 做 average filter，再调整 Gaussian center，模拟 flying edge pixels。

3. Broader distortion  
   使用更大 filter kernel，模拟更大范围的几何扭曲。

这些退化都来自几何和深度学习的常见错误模式，而不是随便加噪声。

## 4. Video Generation 模型

NeoVerse 使用 Wan-T2V 14B + Rectified Flow 作为视频生成模型。

训练输入：

- video latent `x1`；
- sampled noise `x0`；
- degraded rendering condition `c_render`；
- text condition `c_text`，从 video caption 中抽取；
- timestep `t`。

训练目标是预测 rectified flow velocity：

`L_gen = || f_theta(x_t, t, c_render, c_text) - v_t ||^2`

其中 `c_render` 包含多模态条件：

- RGB renderings；
- depth maps；
- binary masks，表示 empty regions；
- 原始 trajectory 的 Plucker embeddings，提供 explicit 3D camera motion information。

这些条件通过 control branch 注入视频生成模型。训练时只训练 control branch，冻结原视频生成模型。这样做有两个目的：

- 训练效率高；
- 可以兼容现成的 video diffusion distillation LoRA / acceleration LoRA。

## 5. 训练流程

NeoVerse 的训练分两大阶段：

### Reconstruction model training

训练 feed-forward 4DGS reconstruction model，损失包括：

- `L_rgb`：rendered vs ground-truth image 的 L2 + LPIPS；
- `L_camera`：camera parameters supervision；
- `L_depth`：depth supervision，包括 Gaussian rendered depth；
- `L_motion`：forward/backward velocity supervision；
- `L_regular`：opacity regularization，防止模型把不确定区域预测成透明 primitive。

补充细节：

- reconstruction input resize 到 longest edge 560；
- 每次采样 `2 <= N <= 8` keyframes，以及相邻 keyframes 中间的 `N-1` target frames；
- 只把 keyframes 输入重建模型，但 loss 在全部 `2N-1` 帧上计算；
- 使用 temporal reversal augmentation，概率 0.5。

### Generation model training

生成模型训练分辨率固定为 `336 x 560`，视频长度 `81 frames`。

训练时：

- 从每个 video clip 随机采样 `11 ~ 21` keyframes；
- on-the-fly reconstruct 4DGS；
- 进行 degradation simulation；
- degraded renderings 作为 condition；
- 原始 monocular video 作为 target；
- 使用 mask drop，概率 0.2，把所有 mask 置为 0，提升鲁棒性。

论文实现中：

- 使用 32 张 A800；
- reconstruction 阶段 150K iterations；
- generation 阶段 50K iterations。

### 数据

重建模型使用 18 个公开数据源，覆盖 static / dynamic / depth / pose / flow 等类型，包括 DL3DV、ARKitScenes、Scannet++、Waymo、Kubric、PointOdyssey 等。

生成模型主要使用：

- SpatialVID 约 371.3K clips；
- 自收集 monocular videos，超过 1M clips。

这正是 NeoVerse 的核心卖点：训练生成器时可以吃大规模 in-the-wild monocular videos。

## 6. 推理流程

给定 monocular video：

1. feed-forward model 输出 4DGS 和每帧 camera parameters；
2. 可选做 global motion tracking，把 Gaussians 分成 static set 和 dynamic set；
3. static Gaussians 可以跨所有帧聚合；
4. dynamic Gaussians 只聚合附近几帧，避免 motion drift；
5. 需要 intermediate timestamp 时，用 bidirectional motion 插值；
6. 把聚合/插值后的 Gaussians 渲染到任意 desired novel trajectory；
7. degraded renderings + conditions 输入视频生成模型，生成最终 novel video。

## 7. Action / Camera Control

NeoVerse 的控制不是键鼠 action，而是 novel camera trajectory。

控制来源有两层：

- 4DGS 渲染：目标轨迹下的 RGB/depth/mask renderings 给出强几何条件；
- Plucker embeddings：原始/目标轨迹相关的 Plucker camera motion information 作为显式 3D camera condition。

和纯生成式 camera control 方法相比，NeoVerse 的轨迹可控性更强，因为生成器不是凭空理解相机动作，而是在 4DGS novel-view renderings 上做 artifact suppression 和内容补全。

## 8. Memory 机制

如果把 memory 广义理解为“模型如何保留过去场景信息”，NeoVerse 的 memory 是显式 4D representation，而不是 Transformer context memory：

- 4DGS 保存了 scene geometry、appearance 和 motion；
- static/dynamic Gaussian aggregation 在推理时保留跨时间的信息；
- global motion tracking 避免把曾经运动过的物体错误当成 static background；
- degraded rendering conditions 把这个显式 memory 输入给视频生成器。

所以它和 HY-World / Matrix-Game 的 memory retrieval 不同：

- HY-World / Matrix-Game：从历史帧里选 memory tokens 进入 DiT；
- Lyra 2.0：per-frame 3D cache 用于检索和 dense correspondence；
- NeoVerse：先构造完整 4DGS，再渲染成多模态条件供视频模型生成。

## 9. 蒸馏 / 加速

论文没有提出自己的 DMD 或 teacher-student 蒸馏流程。它提到由于生成训练只训练 control branch 并冻结 Wan-T2V 主干，因此可以使用现成的 video diffusion distillation LoRA 来加速生成过程。

也就是说：

- NeoVerse 的主要贡献不是 distillation；
- 它的“teacher/base”可以理解为冻结的 Wan-T2V 14B 视频生成模型；
- 可加速性来自控制分支设计对外部 distillation LoRA 的兼容。

## 10. 主要应用

NeoVerse 支持：

- novel trajectory video generation；
- 4D reconstruction；
- video editing；
- stabilization；
- super-resolution；
- image-to-world；
- single-view to multi-view video generation。

## 11. 局限

论文指出它依赖视频中可恢复的 3D geometry。对于缺乏真实 3D 几何的 2D cartoons 等数据，novel view generation 会失败。例如相机绕到脸的另一侧时，输入视频并没有提供足够 3D profile 信息，模型可能生成错误外观。

我的理解是：NeoVerse 是一条非常实用的路线。它把 4D reconstruction 作为显式 memory / geometry prior，再用强视频生成模型修复重建伪影，从而把大规模单目视频纳入训练。它不像 HY-World / Matrix-Game 那样强调实时交互，而是强调 4D 世界生成训练数据的可扩展性。
