# Lyra 2.0 解读

PDF: `papers/pdfs/2604.13036_Lyra_2.0_Explorable_Generative_3D_Worlds.pdf`

## 一句话定位

Lyra 2.0 不是传统意义上用键鼠动作驱动的 interactive world model，而是一个 **camera-trajectory controlled generative reconstruction** 系统：从单张图出发，用户指定长程相机轨迹，视频 diffusion model 生成 3D-consistent walkthrough video，再用 feed-forward 3DGS / mesh reconstruction 得到可探索 3D world。

它主要解决两个问题：

- spatial forgetting：相机走远后再回看旧区域，模型忘记之前生成过什么。
- temporal drifting：自回归生成过程中小误差不断累积，导致颜色、结构、几何逐步漂移。

## 1. Teacher / 视频模型训练

### 基础模型

Lyra 2.0 建在 DiT-based latent video diffusion model 上，使用 Wan 2.1 VAE：

- VAE spatial downsample 为 8x；
- temporal compression 为 4x；
- DiT 在 latent space 中用 flow matching 训练；
- 长视频通过 fixed-length segments 自回归生成。

论文没有像 Lingbot / Matrix-Game 那样详细描述一个多阶段 teacher 训练体系。这里的 “teacher model” 更接近 **完整训练后的 35-step camera-conditioned video diffusion model**，后续 DMD 用它蒸馏 4-step student。

### 训练数据

训练数据来自 DL3DV：

- 10K long video clips；
- 每个视频采样约 1,000 frames；
- 用 ViPE 估计 camera poses；
- 用 Depth Anything V3 预测 per-frame depth；
- 用 Qwen3-VL-8B-Instruct 生成 captions。

### paired data curation

训练时构造 conditioning-target pairs，有两种模式：

- 30% I2V mode：给定单张初始图，生成前 `L=80` 连续帧。
- 70% autoregressive chunk mode：从长序列里采样 segment index `s`，把 `[0, s*L+1)` 作为 history context，把下一个长度 `L` 的 segment 作为 target。

这里 `L=80 frames`，所以 Lyra 2.0 的训练单元比 HY-World 的 16-frame chunk 更长。

## 2. 相机 / 交互控制机制

Lyra 2.0 的“action”不是 WASD 离散动作，而是用户指定的 **camera trajectory**。

它使用两类 camera conditioning：

### Depth-based warping

给定最近帧、depth、目标相机位姿，把最近帧 forward-warp 到目标视角，然后把 warp rendering 编码并与 denoising latent 拼接。

优点：

- 对相机控制非常直接；
- 在 Wan 2.1 里已经能提供较准确的 camera control。

缺点：

- 大视角变化时，很多目标像素没有对应 warped pixels，控制信号会消失；
- warp 图像可能有空洞和边界伪影。

### Plucker ray injection

为补充大视角变化下的控制，Lyra 2.0 计算每个像素的 6D Plucker ray：

`r_i(u,v) = (d, o x d)`

然后经 MLP 投影到 DiT hidden dimension，并加到 token features 上。

所以 Lyra 2.0 的控制机制可以理解为：

- depth warping 提供强几何提示；
- Plucker ray 提供 dense per-pixel camera pose hint；
- 用户通过 GUI 指定 trajectory，而不是直接给模型键鼠动作。

## 3. Memory 机制：Anti-Forgetting

Lyra 2.0 的 memory 是一个增量增长的 **per-frame 3D cache**。

### 3D cache 内容

每生成一帧 `I_i`，系统估计 depth `D_i`，并存储：

- full-resolution depth map `D_i`；
- camera intrinsics / extrinsics；
- downsampled point cloud `P_i`，由 depth unproject 到 world coordinates。

关键点：它 **不把所有历史帧融合成一个 global point cloud**。原因是生成视频上的 depth 会逐步变差，如果强行融合，跨视角误差会污染全局 3D 表示。Lyra 2.0 只保存 per-frame geometry，让每帧误差局部化。

### Geometry-aware retrieval

每次生成新 segment 前，系统根据目标相机视角，从历史中选 `N_s` 个最相关的 history frames。

检索依据是 target viewpoint 下的可见性：

1. 把每个历史帧的 downsampled point cloud 投影到目标视角；
2. 做 occlusion-aware visibility test；
3. 计算每帧可见点数量作为 visibility score；
4. 训练时按 visibility score 采样，增强鲁棒性；
5. 推理时 greedy 选择覆盖最多未覆盖目标像素的 frames，避免重复选择相近视角。

因此，哪怕相机几百帧后回到旧区域，系统也能通过 3D overlap 找回相关历史帧。

### Spatial slots 注入

检索到的 history frames 被作为 spatial slots 送入视频模型：

- 每个 retrieved frame 用 VAE 独立编码成 image tokens；
- 放在 temporal FramePack slots 和 generation tokens 旁边；
- 所有 tokens 进入完整 DiT self-attention；
- 默认 `N_s=5`：4 个 subsampling factor 2 的 frames + 1 个 full-resolution frame。

### Dense 3D correspondence

只放 history frame 还不够，模型还需要知道“历史图像里的哪个位置对应当前目标视角里的哪个位置”。Lyra 2.0 用 canonical coordinate warping：

- 给每个 retrieved frame 生成 canonical coordinate map；
- 用 depth 和相机位姿 forward-warp 到 target view；
- 再把 warped depth 作为第 4 个 channel；
- 通过 positional encoding + learned MLP 编码；
- 加到每个 transformer block 的 self-attention token 上。

重要设计：它 warp 的不是 RGB，而是 canonical coordinates + depth。这样不会把 RGB warp 的空洞、拉伸和边界 bleeding 直接喂给生成器，避免模型复制几何伪影。

## 4. Anti-Drifting：Self-Augmentation Training

Lyra 2.0 认为 temporal drift 的根本原因是 observation bias：

- 训练时，history context 是 ground-truth；
- 推理时，history context 是模型自己生成的、有噪声的历史；
- 这个 train-test mismatch 会让错误逐段累积。

它的 self-augmentation 做法：

1. 取 ground-truth history frames `x_hist` 和 current chunk `x_cur`。
2. 用 VAE 编码得到 `z_hist_0` 和 `z_cur_0`。
3. 以概率 `p_aug` 对 `z_hist_0` 加噪，采样 `t ~ U(0, 0.5)`。
4. 用当前视频模型做一次 one-step denoising，得到近似重建 `tilde z_hist_0`。
5. 用这个 imperfect `tilde z_hist_0` 替代 clean history，作为 DiT conditioning context。
6. 但 target `z_cur_0` 仍然用 clean history cache 编码，并作为 flow matching 目标。

直观理解：训练时故意让模型看到“自己生成过、带瑕疵的历史”，但要求它仍然生成干净的下一段，从而学会纠正漂移，而不是传播漂移。

这和 Matrix-Game 的 error injection / multi-segment rollout、HY-World 的 student self-rollout 有相似动机，但 Lyra 2.0 用的是更轻量的 one-step denoised history augmentation。

## 5. Student 蒸馏：DMD

Lyra 2.0 额外训练 distilled model 来加速推理：

- teacher：完整训练后的 35-step video model；
- student：蒸馏到 4 denoising steps；
- 方法：Distribution Matching Distillation；
- 同时 distill classifier-free guidance，因此推理时不需要 conditional / unconditional 两次 forward；
- 蒸馏期间保留 self-augmentation，使 student 仍然能处理自回归误差累积；
- 论文报告 per-step generation time 约减少 13x。

和 HY-World 的 Context Forcing 相比，Lyra 2.0 没有专门提出 teacher/student memory context mask。原因可能是它的 memory 主要来自生成当前 segment 前的历史 3D cache 和 retrieved frames；DMD 目标是当前 segment，合法条件是过去历史和相机轨迹。只要当前 segment 没被提前写入 cache，就不会出现 HY-World 那种 teacher 在 condition 中看到当前 target 的明显泄露。

## 6. 3D Reconstruction

视频只是中间结果，Lyra 2.0 最终要输出可探索 3D world。

### 3DGS

它采用 Depth Anything V3 作为 feed-forward 3D foundation model，预测 per-pixel 3D Gaussian attributes。但做了两个调整：

- 修改 Gaussian DPT head，让输出 feature map 下采样 `k x k`，减少 Gaussian 数量，便于实时渲染和数据流传输。
- 用 Lyra 2.0 生成的视频场景 fine-tune DAv3，让重建模型更适应 generated video 中的小几何不一致。

### Mesh

得到 3DGS 后，再用 hierarchical sparse grid / OpenVDB 提取 surface mesh：

- 视角附近分配细网格；
- 远处背景用粗网格；
- 从 Gaussian reconstruction rasterize median depth；
- 用 oriented point cloud 构造 signed distance function；
- marching cubes 提取 mesh，并做 stitching / decimation。

输出可用于 interactive viewer、VR、NVIDIA Isaac Sim 等模拟环境。

## 7. 与前几篇的关系

- 对比 HY-World 1.5：HY-World 更像实时交互视频世界模型，重点是动作控制、Context Forcing、Reconstituted Context Memory；Lyra 2.0 更像可探索 3D 场景生成系统，重点是 camera trajectory、3D cache routing 和 3DGS/mesh。
- 对比 Matrix-Game 3.0：Matrix-Game 用 camera-aware memory retrieval 和 DMD 做实时 streaming interactive model；Lyra 2.0 不追求游戏式实时动作响应，而是从单图扩展大规模 3D scene，并更重视最终 3D reconstruction。
- 对比 Lyra 1：Lyra 1 更强调用 video diffusion teacher self-distill 3D reconstruction；Lyra 2.0 把视频生成本身扩展成长程、可回看、可探索的 3D-consistent trajectory。
