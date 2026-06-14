# Surflo: Consistent 3D Surface Flow Model with Global State

- Imported from: https://arxiv.org/abs/2606.13644
- PDF URL: https://arxiv.org/pdf/2606.13644.pdf
- Hash: 5b3d3f36094d1868
- Slug: 5b3d3f36094d1868
- Status: imported

## Structured Analysis

### Motivation

- 论文的出发点是：3D geometry 对视角变换不变，多张图像只是同一 3D state 的冗余投影；随着输入视图增加，像素数量线性增长，但几何内容并不线性增长。因此理想模型应学习一个共享的 global state，而不是按视图或像素保留冗余表示（Section 1, p.2）。
- 现有 feed-forward 重建方法主要有两类缺陷：per-view 方法如 VGGT/DepthAnything-3 输出每张图对应的 pointmap，点数随视图数增长，且不同视图的点云重叠但不严格对齐，难以融合成干净 mesh；global-latent 方法虽然压缩场景，但通常只能输出固定低分辨率点集或仍以 per-view 方式解码（Section 1, p.2；Fig. 1, p.1）。
- Surflo 要解决的核心矛盾是：既要把任意数量 unposed RGB views 压缩成固定大小、跨视图一致的场景表示，又要能从这个表示中按需解码任意数量的 oriented surface points，并保持局部表面一致性（Section 1, p.2）。

### Problem Setting

- 输入是数量可变的 unposed RGB views，推理时输入视图数 N 可以自由变化；输出是场景表面的 oriented 3D points，即坐标和法向，输出点数 P 也可以自由指定，从几千到百万级（Abstract, p.1；Section 2, p.3）。
- 模型目标不是逐视图深度或 pointmap，而是恢复一个全局一致的 scene geometry。Surflo 将多视图图像压缩为固定大小 latent `z ∈ R^{K×D}`，并以该 latent 为条件生成表面点（Fig. 2, p.3）。
- 评估任务是 few-view scene-level surface reconstruction。默认每个测试场景使用 16 张 unposed input views，指标为归一化 Chamfer Distance 和 1% scene diagonal 阈值下的 F1-score（Section 3.1, p.6）。

### Core Idea

- Surflo 的核心思想是“one global state + arbitrary-resolution surface decoding”：先用 frozen VGGT 提取多视图几何特征，再用 Perceiver-style compressor 将所有视图 token 压缩成固定数量 K 个 latent tokens；随后用 flow matching decoder 从噪声中独立运输 query points 到目标表面（Section 2, p.3；Fig. 2, p.3）。
- 独立 per-point decoding 使输出分辨率摆脱固定网格或固定 token budget：同一个 latent 可解码 8K、32K、128K 乃至更多点，粗略预览和高密度重建只需改变 query 数量（Section 2.2, p.4；Fig. 5, p.8）。
- 但独立生成点也会带来局部不一致：每个点单独预测，缺乏 joint surface distribution 约束，可能出现漂浮点、双层表面或细节缺失。因此论文在推理阶段加入 rendering-based guidance，让点通过全局渲染损失的梯度“通信”，增强一致性（Section 2.3, p.5）。

### Method

- **Encoder**：Surflo 使用 frozen VGGT-1B 作为 backbone，从多个中间层提取 patch tokens 和 camera tokens。patch tokens 加入 VGGT pointmap 中 patch center 的 3D Fourier positional encoding，使 decoder query 的 3D 坐标能与 encoded scene token 在同一空间中建立局部关联。随后用 Perceiver cross-attention 将 `N × 4Np` 个 patch tokens 压缩为 K 个 latent tokens，camera tokens 也被压缩为一个 world-space 相关 latent，并与 patch latent 拼接（Section 2.1, pp.3-4）。
- **Flow-matching decoder**：将表面解码视为在 `R^3 × S^2` 中把 source distribution `p0` 的点和法向运输到 surface distribution `p1`。训练时采样目标表面点 `x1`、噪声源点 `x0` 和时间 `t`，构造线性插值 `xt=(1-t)x0+t x1`，模型预测 velocity `x1-x0`，使用标准 flow-matching loss（Section 2.2, p.4）。
- **Source distribution**：3D 坐标不直接从标准高斯采样，而是从以扰动 VGGT pointmap samples 为中心的 Gaussian mixture 采样；这让初始点集中在几何附近，同时保留覆盖遮挡区域的空间。法向则在 `S^2` 上均匀初始化（Section 2.2, p.4）。
- **Guidance**：推理时用 Euler ODE 从 `t=0` 积分到 `t=1`。在后期 `t ≥ 0.95`，先估计目标点 `x_hat_1`，把这些点当作 oriented Gaussians 渲染到 VGGT 恢复的相机视角，计算 photometric/DSSIM 及深度正则等 rendering loss，然后对目标点做 M 步梯度更新，得到 guided velocity。可选 monocular depth guidance 进一步强化深度排序（Section 2.3, p.5；Fig. 3, p.4）。
- **Mesh extraction 与训练数据**：输出 oriented Gaussians 后按 Gaussian Wrapping 的流程用 Delaunay triangulation 转为三角网格。训练监督来自作者构建的 meshed DL3DV：约 10.5K 场景，每个场景通过 Gaussian Wrapping 得到 watertight mesh，并采样约 `10^7` oriented points（Section 2.3-2.4, p.5）。

### Key Contributions

- 提出一种 feed-forward global-state 3D reconstruction 架构：能将任意数量 unposed RGB views 压缩成固定大小 latent，避免 per-view pointmap 的冗余和融合困难（Section 1, p.2）。
- 提出基于 flow matching 的 arbitrary-resolution surface decoder：从同一个 global latent 中独立解码任意数量 oriented surface points，不受固定输出网格或固定点数限制（Section 2.2, p.4）。
- 提出 inference-time rendering guidance：用可微渲染的 photometric/depth loss 梯度耦合独立生成的点，缓解漂浮点和局部不一致，并提升与输入图像的对齐和细节质量（Section 2.3, p.5；Fig. 3, p.4）。
- 构建并计划释放 meshed DL3DV 数据集，为约 10.5K 个真实场景补充 watertight surfaces 和大规模 oriented point samples，用于 scene-level surface learning（Section 2.4, p.5）。

### Experiments / Evidence

- 在 4 个由 dense views + Gaussian Wrapping 生成参考表面的数据集上，Surflo 从同样 16 张输入图像取得最强或接近最强结果。例如在 DL3DV test split 上，无 guidance 版本 CD=0.0072、F1=81.92，优于 VGGT+TSDF 的 CD=0.0126、F1=69.23；在 Tanks & Temples 上无 guidance CD=0.0053、F1=88.57，也明显优于 optimization 和 TSDF-fused baselines（Table 1, p.7）。
- 在带 native surface ground truth 的 OOD benchmarks 上，Surflo 整体优于固定 latent 输出和 per-scene optimization 方法。例如 ML-Hypersim 上 guided Surflo CD=0.0079、F1=87.97，显著优于 Gaussian Wrapping 的 CD=0.0145、F1=66.86；SCRREAM 上 guided Surflo CD=0.0070、F1=81.11，也优于 Gaussian Wrapping 的 CD=0.0123、F1=62.96（Table 2, p.8）。
- 输入视图数变化实验显示，Surflo 可在 2 到 32 views 范围内无需改架构使用固定大小 latent，并在 Tanks & Temples 与 Mip-NeRF 360 上各视图数下保持最优或接近最优。更多视图会逐步补全缺失几何和细化细节，而 decoder cost 不随视图数增加（Tables 3-4, p.9；Fig. 6, p.10）。
- 消融显示关键设计有效：K 从 32 增至 128 提升明显；加入 Gaussian Fourier 3D positional encoding 优于 raw VGGT tokens；VGGT-pointmap Gaussian mixture source 优于 pure Gaussian source。例如 Tanks & Temples 上完整设置 CD=0.0055、F1=88.02，而 pure Gaussian source 为 CD=0.0074、F1=77.09（Table 5, p.10）。

### Conclusions, Limitations, and Relation to Other Work

- Surflo 的定位是在 per-view feed-forward、fixed-output global latent 和 per-scene optimization 之间取得新的组合：它保留 feed-forward 推理速度和 sparse-view 能力，同时提供 fixed-size global latent 与 arbitrary-resolution surface decoding。与 VGGT/DUSt3R 类方法不同，它不输出按视图增长的 pointmaps；与 NOVA3R 不同，它不固定为 10K 点且支持更多输入视图；与 Gaussian Splatting/NeuS/Gaussian Wrapping 类优化方法不同，它不依赖大量 posed views 和长时间 per-scene optimization（Section 4, pp.9-10）。
- 论文结论认为，Surflo 是唯一同时具备 global latent、任意分辨率 oriented surface decoding 和 feed-forward few-view reconstruction 能力的方法；实验上在多组 surface metrics 中超过强基线，并且缓存 latent 后解码 `10^5` 点仅需数秒，显著快于 per-scene optimization（Section 3.2, p.9；Section 5, p.10）。
- 主要限制包括：模型继承 VGGT 的失败模式，当视图极少或 baseline 极端导致 pointmaps 较差时，source distribution 和 patch tokenization 会不可靠；photometric guidance 提升质量但增加推理时间；监督表面来自 Gaussian Wrapping，本身在透明或无纹理结构上可能不完美；当前模型只表示几何，不预测外观或 view-dependent radiance（Section 5, p.11）。
