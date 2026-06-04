# HY-World 1.5 / WorldPlay 解读

PDF: `papers/pdfs/pdf_HY-World_1.5_A_Systematic_Framework_for_Interactive_World_Modeling_with_Real-Time_Latency_and_Geometric_Consistency.pdf`

## 一句话定位

HY-World 1.5 的核心是 WorldPlay：把一个原本非因果的双向视频扩散模型，改造成按 chunk 自回归生成的交互式世界模型；再通过 Dual Action Representation 控制动作，通过 Reconstituted Context Memory 保持长程几何一致性，最后用 Context Forcing 蒸馏到 few-step 实时推理。

它的关键问题不是单纯“如何蒸馏得更快”，而是：蒸馏之后还能不能继续使用 long-range memory。论文认为普通 DMD 失败的根源在 teacher 和 student 看到的 memory context 不一致。

## 1. Teacher / Base Model 训练流程

### 数据与标注

论文使用 320K curated video clips：

- AAA game recordings: 170K clips，第一/第三人称游戏录制，提供丰富交互和物理行为。
- Real-world 3D: 60K clips，来自 DL3DV，经 3D reconstruction 后设计相机轨迹。
- Synthetic 4D: 50K clips，Unreal Engine 渲染，提供精确 ground truth。
- Real-world video: 40K clips，来自 Sekai，提供自然视频的动态和运动先验。

标注包括：

- text caption：用 HunyuanVideo 1.5 caption model 生成结构化文本。
- continuous camera poses：通过 VIPE 估计，或直接从 UE / 3D 渲染管线获得。
- discrete action signals：从 camera trajectories 推导 movement commands / view rotations；AAA game 录制中也可直接记录键鼠动作。

### 预训练：双向视频 diffusion 到 chunk-wise AR

起点是 bidirectional video diffusion model，结构上包含 3D VAE + DiT，在 latent space 用 flow matching 训练。这个模型本身不是 causal 的，因此不能直接做无限长度交互生成。

WorldPlay 把视频切成 chunk：

- 1 chunk = 4 video latents = 16 frames。
- 训练目标变成 next chunk prediction：给定过去观测 `O_{t-1}`、过去 action `A_{t-1}`、当前 action `a_t`，生成当前 chunk `x_t`。
- 训练中借鉴 Diffusion Forcing：不同 chunk 加不同噪声水平。
- 把原来的 bidirectional self-attention 改成 block-causal attention，使模型只能依赖过去 chunk。

这一步得到的是 autoregressive diffusion base model。它是后续 action、memory 和 distillation 的基础。

### 中训练：加入 control 和 memory

Middle-training 把两个能力接进 AR base model：

- Dual Action Representation：离散键鼠 + 连续相机位姿。
- Reconstituted Context Memory：每次生成新 chunk 时从历史帧动态重建 context memory。

这时模型已经是 memory-aware AR diffusion model，能在探索时利用过去的时空上下文。

### 后训练 I：WorldCompass RL

论文还加入 WorldCompass RL post-training，用于增强复杂动作跟随和视觉质量：

- Clip-Level Rollout：让模型在训练时依赖自己的生成结果，缓解 exposure bias。
- Complementary Rewards：动作跟随分数 + 视觉质量分数，降低 reward hacking。
- DiffusionNFT：作为 diffusion model 的 RL 算法。

这部分可以理解为 teacher / strong model 的质量增强阶段，不是蒸馏本身。

## 2. Student 蒸馏：Context Forcing

### 为什么普通 DMD 不够

标准 DMD 类方法一般让 autoregressive student 对齐 bidirectional teacher 的分布，用 score difference 近似 distribution matching gradient。

但 memory-aware world model 里有一个额外问题：

- teacher 是 bidirectional，天然可以看到更完整的上下文。
- student 是 autoregressive，推理时只能看到 past-only context。
- memory retrieval 依赖已生成历史，teacher 和 student 如果拿到不同 memory context，则两者条件分布 `p(x|C)` 不一致。

所以问题不是“teacher 不够强”，而是 teacher 监督的条件和 student 推理时的条件不匹配。对 memory-aware 模型，这会直接破坏长程一致性。

### Context Forcing 怎么做

论文的方法是让 teacher 和 student 在蒸馏时使用对齐后的 memory context。

Student 侧：

- 从某个起点 `j` 开始 self-rollout 4 个 chunks，即 `x_j, x_{j+1}, x_{j+2}, x_{j+3}`。
- 每一步生成 `x_i` 前，都从已有历史 `{x_0, ..., x_{i-1}}` 中重构 memory context `C_i`。
- 这模拟真实推理，因为 student 的历史里包含自己生成的 chunk。

Teacher 侧：

- teacher 是 memory-augmented bidirectional video diffusion model。
- 但 teacher 的 context 不能直接包含被监督的 student rollout chunk。
- 因此构造 `C_tea = C_{j:j+3} - x_{j:j+3}`，也就是把当前要蒸馏的 4 个 student chunks 从 teacher memory context 中 mask 掉。

然后：

- 给 `x_{j:j+3}` 加噪声。
- teacher / critic 计算 real score 和 fake score。
- 用 distribution matching loss 更新 student。
- 同时更新 fake teacher / critic 的参数。

最终 student 可以用 4 denoising steps 生成，同时尽量保留 memory-aware teacher 的长程一致性。

### 和 Matrix-Game 3.0 的 multi-segment DMD 的差别

两者都强调训练时模拟推理时的 self-generated history，但关注点不同：

- Matrix-Game 3.0 的 multi-segment rollout 更强调多段 streaming 误差传播，segment 之间前后衔接，最后随机抽一个 segment 做 DMD。
- HY-World 1.5 的 Context Forcing 更强调 teacher/student 的 memory context 对齐，核心操作是让 teacher 也在“student 实际可见的 memory 条件”下打分。

HY-World 的 segment/chunk 单元更明确：一次 Context Forcing self-rollout 是 4 chunks，每个 chunk 是 16 frames。

## 3. Action 注入机制

论文叫 Dual Action Representation，即同时使用离散动作和连续相机位姿。

### 离散动作：keyboard / mouse

离散动作对应用户输入，例如：

- movement command: forward/backward/left/right。
- view rotation: mouse-like rotation 或视角变化。

实现上：

- 先把 discrete action 编成 action embedding。
- 用 zero-initialized MLP 投影。
- 投影结果加到 timestep embedding 中。
- timestep embedding 再用于调制 DiT blocks。

这种路径类似 AdaLN / timestep modulation：动作不是简单拼到 token 上，而是进入 block 的调制信号。zero-init 的意义是训练初期不破坏原视频模型能力，动作控制逐步学进去。

### 连续动作：camera pose / PRoPE

连续相机位姿包括 rotation 和 translation matrix。它的好处是提供准确空间位置，尤其对 spatial memory retrieval 很关键。

HY-World 1.5 用 PRoPE 把 camera intrinsic / extrinsic 注入 self-attention：

- 原 self-attention 使用 3D RoPE 处理视频 latent 的时空位置。
- 新增一个由 camera parameters 派生的 `Dproj`。
- 构造额外 attention 分支 `Attn2`，用于编码相机 frustum 之间的投影关系。
- 最终输出为 `Attn1 + zero_init(Attn2)`。

离散动作负责跨场景尺度下的鲁棒运动控制，连续相机位姿负责精确空间定位和 memory retrieval。两者互补。

## 4. Memory 机制：Reconstituted Context Memory

### Memory 的构成

生成每个新 chunk `x_t` 时，模型从过去观测 `O_{t-1}` 中动态重建 context memory `C_t`。它由两部分组成：

- temporal memory `C^T_t`：最近 `L` 个 chunks，例如 `{x_{t-L}, ..., x_{t-1}}`，用于短期运动平滑。
- spatial memory `C^S_t`：从非相邻历史帧中采样，用于重访旧区域时保持几何和外观一致。

Spatial memory 的采样依据不是简单时间距离，而是 geometric relevance：

- FOV overlap：当前视野和历史帧视野的重叠。
- camera distance：当前相机位置和历史相机位置的距离。

所以它更像“按几何相关性找过去见过的视角”，而不是固定取若干历史帧。

### Temporal Reframing

Memory 检索出来之后，还有一个 positional encoding 问题。

如果直接使用绝对时间 RoPE，过去很久的 memory chunk 和当前 chunk 的相对距离会越来越大：

- 超出 RoPE 训练时的插值范围，容易产生 extrapolation artifact。
- Transformer 会把很远的 token 当成弱相关上下文，削弱 long-past memory 的影响。

Temporal Reframing 的做法是：

- 丢弃 memory 的真实绝对时间 index。
- 对当前 context frames 动态重新分配 positional encoding。
- 让重要历史 memory 与当前 predicted chunk 保持固定且较小的相对距离。

直观讲，就是把“很久以前但几何相关的帧”在 attention 位置上拉近，让模型愿意用它。

### 推理时的 KV cache

推理阶段每个 chunk 仍会重构 context memory `C_i`。算法 2 中还用 KV cache 缓存 attention 的上下文表示，减少自回归生成里的重复计算。工程上再配合 8 GPU sequence/attention parallelism、progressive VAE decoding、quantization 和 SageAttention，达到 24 FPS streaming generation。

## 5. 我的理解

HY-World 1.5 的技术主线可以概括为：

1. 用大规模多源视频数据训练/改造一个 chunk-wise AR diffusion base。
2. 用离散动作解决“用户意图”和跨尺度移动，用连续 pose 解决“我在哪里”和 memory 检索。
3. 每个 chunk 生成前都重新组织 temporal + spatial memory，而不是把全部历史塞进去。
4. 蒸馏时不只追求 few-step，而是强制 teacher 在与 student 对齐的 memory context 下监督，避免 teacher 教的是 student 推理时看不到的条件分布。

和 Lingbot-World 相比，HY-World 的 memory 更显式、更几何化；和 Matrix-Game 3.0 相比，HY-World 对 teacher/student memory context mismatch 的表述更直接，Context Forcing 是它最值得关注的蒸馏设计。
