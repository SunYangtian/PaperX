# InSpatio-WorldFM 解读

PDF: `papers/pdfs/2603.11911_InSpatio-WorldFM_An_Open-Source_Real-Time_Generative_Frame_Model.pdf`

## 一句话定位

InSpatio-WorldFM 是一个 **real-time generative frame model**，它刻意避开 video world model 的 window-level sequential generation。传统视频模型每次生成一段窗口，延迟来自整段视频 denoising；InSpatio-WorldFM 改成每次独立生成单帧，通过 explicit 3D anchors + implicit spatial memory 维持多视角一致性。

这篇的重点不是长视频蒸馏，而是：**用 image diffusion backbone 做实时 novel-view frame generation**。

## 1. 整体框架：offline + online

系统分两阶段：

- Offline stage：从单张输入图出发，用 multi-view-consistent model 或 panorama generation 生成一组多视角观测；再用 reconstruction model 得到 3D anchors。
- Online stage：frame model 根据 reference image、target camera pose、point cloud rendering 等条件，实时生成目标视角图像，并在 keyframes 更新局部场景内容。

因此它和 Lyra 2.0 有一个重要差别：

- Lyra 2.0 是生成长程视频，再重建成 3DGS/mesh。
- InSpatio-WorldFM 是直接做实时单帧 novel view synthesis，用 3D anchor 和 reference memory 保持空间一致。

## 2. Teacher / 训练流程

论文提出三阶段训练：

### Stage I: Pre-training

选择 PixArt-Sigma 作为 foundation image generator：

- PixArt-Sigma 是 text-to-image DiT；
- 优点是质量和计算效率比较平衡；
- 它提供高保真图像生成先验，但本身没有空间一致性和交互控制能力。

这里没有从头训练 teacher，而是继承 pretrained image diffusion backbone。

### Stage II: Middle-training

这一阶段把 image generator 改造成 controllable frame model with spatial memory。

训练目标是条件扩散：

`C = {x_ref, pi_ref, pi_tgt, xhat_tgt}`

其中：

- `x_ref`：reference image，是 implicit scene memory；
- `pi_ref`：reference camera pose；
- `pi_tgt`：target camera pose；
- `xhat_tgt`：target viewpoint 下的 point cloud rendering，是 explicit 3D anchor；
- `z_t`：target image latent 加噪后的 latent；
- 模型预测噪声，训练 denoising loss。

### 训练数据

训练 pair 来自三类数据：

- public videos，例如 internet videos、DL3DV、RealEstate10K；
- 自采视频；
- Unreal Engine synthetic data。

真实视频构造流程：

1. 对每个 video clip 随机采样 16 frames。
2. 用 feed-forward reconstruction model，例如 MapAnything，估计每帧 camera pose 和 depth。
3. 从 16 帧中选 4 帧作为 reference group，用于构建 global point cloud。
4. 剩余 12 帧作为 target frames。
5. 对每个 target frame，从 4 个 reference frames 中选时间最近的一帧作为 reference image。
6. 把 global point cloud 投影到 target camera plane，得到 point cloud rendering。
7. 使用 random shuffling 和 masking，模拟真实在线场景里历史观测的离散、无序和缺失。

### Synthetic finetuning

真实数据里的 pose/depth 是估计出来的，会有 inter-view inconsistency。论文因此用 Unreal Engine 构造 synthetic data：

- 选择语义合理的初始相机位置；
- 用随机 motion sampling 或预定义 motion templates 生成轨迹；
- 用 collision avoidance 保证视点有效；
- 同样构造 4 reference + 12 target 的训练 pair；
- 只做有限步 finetuning，避免过拟合 synthetic distribution，损害自然图像外观。

## 3. 模型结构与 action / camera 注入

InSpatio-WorldFM 生成目标视角图像时，把三个部分沿 width 维度拼接：

1. noisy target latent `z_t`；
2. target viewpoint 下的 point cloud rendering，也就是 explicit 3D anchor；
3. reference image，也就是 implicit memory。

三者通过 shared patch embedding 变成 tokens，加 sinusoidal positional embedding，然后进入 self-attention-only DiT。最后输出按 width 维度切开，只保留 target 部分。

### Camera pose encoding

论文比较了三种 camera pose 注入：

- Plucker ray embedding：每个 patch 计算 6D Plucker coordinates `(o x d, d)`，MLP 投影后加到 patch embeddings。
- PRoPE：用 camera projection matrix 直接调制 Q/K/V，把 camera geometry 放进 attention。
- Pure parametric injection：把 rotation/translation matrix 直接 MLP 成 token embedding。

最终采用 **PRoPE**，因为实验中收敛最快、camera control 最稳定。PRoPE 的优势是：它不是简单 additive embedding，而是直接改变 attention 里的几何关系，让模型在 self-attention 中做 cross-view correspondence reasoning。

这里的 action 本质是 user-defined camera motion / target pose，不是 WASD 多热向量。

## 4. Memory 机制：Hybrid Spatial Memory

InSpatio-WorldFM 的 memory 不是时间窗口，而是空间条件。

### Explicit anchors

`xhat_tgt` 是 target viewpoint 下的 point cloud rendering。它和 target camera pose 一起提供粗几何约束：

- 保持 coarse 3D structure；
- 提供全局 3D prior；
- 防止每帧独立生成时几何漂移。

但 point cloud rendering 往往缺少精细纹理和未观测区域的外观，所以不能只依赖它。

### Implicit memory

reference image `x_ref` 和 reference pose `pi_ref` 提供外观记忆：

- transformer 通过 self-attention 访问 reference image tokens；
- 用来迁移细节、纹理、局部 appearance；
- 在未观测区域 hallucinate plausible content。

所以它的 memory 是：

`coarse geometry anchor + fine appearance memory`

这和 Lyra 2.0 的 per-frame 3D cache 不一样。Lyra 2.0 做历史检索和 dense correspondence；InSpatio-WorldFM 更像固定 reference / global point cloud 的单帧视角生成器。

### Training tricks

论文用了三个训练策略：

- Noise schedule biasing：增加 high-noise timestep 采样概率，让模型先学 coarse spatial layout，再学细节。
- Progressive condition injection：早期只给 implicit memory，即 reference image，迫使模型学会用 reference appearance；之后逐渐加入 explicit anchor。
- Random anchor masking：后期随机 mask point cloud rendering，防止模型过度依赖 explicit 3D prior。

## 5. Student 蒸馏：DMD 到 2-step

Stage III 把 middle-trained multi-step frame model 蒸馏成 few-step generator。

DMD 配置：

- frozen base model 估计 real score；
- dynamically-updated model 在 generator outputs 上训练，估计 fake score；
- 用 denoising prediction difference 更新 generator；
- 加 regression loss 到 base deterministic sampler 生成的 noise-image pairs，稳定训练并保持 mode coverage。

InSpatio-WorldFM 的关键经验：

- 1-step 可以恢复粗几何，但细节不够；
- 2-step 更好，因为第一步建立 coarse spatial structure，第二步从较干净状态恢复 fine details；
- 中间 timestep 很关键；
- 在 1000-step schedule 下，`t_mid = 200` 最佳。

性能：

- baseline 512x512 在单张 H-series GPU 上约 25 FPS；
- RTX 4090 上约 10 FPS；
- 使用 KV-cache management 和 efficient VAE latent caching。

## 6. 与其他论文的关系

### 与 HY-World / Matrix-Game / Lingbot 的差异

这些模型大多是 video model，生成单位是 chunk/window，需要处理长视频上下文、rollout error 和 teacher/student memory mismatch。

InSpatio-WorldFM 则把单位缩到单帧：

- 优点：低延迟，天然适合交互；
- 缺点：缺少连续帧之间的 temporal constraint，论文也承认会有 frame jitter。

### 与 Lyra 2.0 的差异

Lyra 2.0 是 long-horizon camera trajectory video generation + 3DGS reconstruction。它维护 per-frame 3D cache，并检索历史帧。

InSpatio-WorldFM 是 real-time frame synthesis。它用 offline multi-view observations / panorama / reconstruction 得到 3D anchors，再在线逐帧生成。

### 与 RTFM 的关系

论文明确说 World Labs 的 RTFM 展示了 frame model 潜力，但技术细节和源码有限。InSpatio-WorldFM 的贡献之一就是开源一个 frame-based world model，并给出具体训练和架构。

## 7. 主要限制

论文自己列了几个关键限制：

- dynamic content 不稳定：训练数据和 frame model 都更偏静态 multi-view consistency。
- motion boundary：历史 memory 依赖 offline multi-view / panorama observations，在线扩展范围受限。
- interactive visual stability：单帧生成降低延迟，但缺少跨帧 temporal constraint，会产生 frame jitter。

我的理解是：InSpatio-WorldFM 是用空间一致性换实时交互的路线。它牺牲了视频模型的时间建模能力，但显著降低了交互延迟，是和 HY-World / Matrix-Game 完全不同的一条 world model 工程路线。
