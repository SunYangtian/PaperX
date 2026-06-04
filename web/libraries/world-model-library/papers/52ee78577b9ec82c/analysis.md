# Matrix-Game 3.0: Real-Time and Streaming Interactive World Model with Long-Horizon Memory

## 关注问题

1. Teacher / base model 训练流程。
2. few-step distillation / 实时化。
3. long-horizon memory 机制。

## 1. Teacher / Base Model 训练流程

Matrix-Game 3.0 的 teacher 不是一个单独异构大 teacher，而是来自同一套 bidirectional DiT 架构的 memory-augmented base model。论文特别强调 architectural consistency：multi-step base model 和 few-step distilled model 使用统一的 bidirectional architecture，避免异构 teacher-student 造成映射不稳定。

整体训练顺序可以拆成：

1. Interactive base model
   - 基于 Wan2.2-TI2V-5B。
   - Action modules 集成在前 15 个 DiT blocks。
   - 训练时 80% 概率使用 4 个 past-frame latents + 10 个 current-frame noisy latents。
   - 20% 概率 mask 掉 past-frame 和 memory latents，退化为 action-conditioned image-to-video，对应流式推理的第一个 segment。
   - fine-tune 50K steps，学习率 2e-5。

2. Error-aware training
   - Base model 要在 imperfect context 下也稳定，因为推理时历史帧来自模型自己生成，不是干净 ground truth。
   - 训练中维护 error buffer E。
   - 先根据模型预测的 clean estimate 和真实 latent 计算 residual。
   - 再从 buffer 采样 residual，注入到 history latent，模拟 autoregressive rollout 中累积的 exposure error。
   - 这样 base model 先学会面对“带误差的历史上下文”。

3. Memory-augmented base model
   - 从 action-modulated base model 初始化。
   - 训练时把 5 个 memory latents、4 个 past-frame latents、10 个待生成 noisy latents 拼在一起送入 DiT。
   - 训练集约 4.8M video clips。
   - 引入 head-wise perturbed RoPE base，帮助区分远距离 memory、近历史和当前预测位置。

4. 28B scaling
   - 另有 MoE-28B scale-up。
   - high-noise model 训练 action module，负责精确控制。
   - low-noise model 用 Internet video data 独立训练，负责视觉细节和泛化。
   - 分别训练 first-person 和 third-person 的 high-noise models，共享 low-noise model。
   - 逐步扩展分辨率和 video clip length，以稳定 long-horizon behavior。

所以，Matrix-Game 3.0 的 teacher 更准确地说是“memory-augmented multi-step bidirectional base model”，而不是 Lingbot 那种 MoE teacher 再 causalize 的路线。

## 2. Few-step Distillation / 实时化

Matrix-Game 3.0 的 distillation 目标是把 memory-augmented base model 蒸馏成 few-step、可流式推理的模型，同时保持训练-推理一致。

关键点：

1. Teacher、critic、student 初始化
   - Distillation 阶段的 teacher、critic、student 全部直接从 memory-augmented base model 初始化。
   - 这保证 teacher 和 student 架构一致，减少 ODE/DMD 映射不匹配。

2. 为什么要 multi-segment
   - 常见 causal student 是 chunk-wise inference，天然支持在 teacher window 内 self-generated rollout。
   - 但本文使用 bidirectional autoregressive modeling，student 的 inference span 不再是小 chunk，而是和 teacher 一样覆盖整个 window。
   - 如果只做 single-window distillation，历史条件只能用 ground-truth frames，会和真实推理时的 self-generated history 不一致，导致 exposure bias。

3. Multi-segment self-generated inference
   - Student 连续 rollout 多个 segment。
   - 每个 segment 从 random noise 开始。
   - 当前 segment 的 past frames 来自前一个 segment 的尾部。
   - memory 从在线更新的 memory pool 中按当前 camera viewpoint 检索。
   - 第一个 segment 没有 memory，模型以 I2V 方式启动。
   - 训练时随机停在某个 segment，把该 segment 送给 teacher 和 critic 做 DMD。

4. DMD objective
   - DMD 最小化 student distribution 和 target data distribution 在 sampled timestep 上的 reverse KL。
   - 梯度用 data score 和 generated score 的差近似。
   - 条件包括 action condition `c` 和 memory `M`。
   - `xpast` 来自前一个 segment 的尾部，而不是 ground truth。

5. 训练日程
   - Cold-start：前 600 steps 使用 single-segment inference，past frames 使用 ground-truth clips，避免 few-step student 初期直接 collapse。
   - Multi-segment：之后进入实际流式使用场景，segment 数 k 从 1 到 6 随机采样。
   - Multi-segment 阶段训练 2,400 steps。
   - past frames 和 memory 仍有 0.2 概率被 mask，保持 I2V / 首段启动能力。

6. 实时化工程
   - DiT attention projection 做 INT8 quantization。
   - VAE decoder pruning，训练 MG-LightVAE，50% / 75% pruning 分别带来约 2.6x / 5.2x decoding speedup。
   - GPU-based camera-aware memory retrieval。
   - 异步部署：8 GPUs 做 DiT inference，1 GPU 做 VAE decoding。
   - 目标结果：5B model 在 720p 下最高约 40 FPS。

这篇的核心差异是：它不是简单在一个窗口上做 DMD，而是让 student 在训练时模拟真实多段流式推理，再把随机停止的 segment 交给 teacher/critic。这样 DMD 监督发生在“已有 self-generated history + online memory retrieval”的状态下。

## 3. Long-Horizon Memory 机制

Matrix-Game 3.0 的 memory 是显式 retrieval + DiT joint self-attention，不是 Lingbot 那种主要依赖 context window 的 emergent memory。

### 3.1 Memory 输入包含什么

训练时 jointly model：

- 5 个 retrieved memory latents；
- 4 个 recent past-frame latents；
- 10 个 current noisy latents；
- mouse / keyboard action condition；
- relative camera geometry condition。

这些 token / latents 被 concatenated 后一起送进同一个 Diffusion Transformer。模型只预测 current frames。

### 3.2 为什么不用单独 memory branch

论文讨论了两条路线：

1. Implicit sparse long-context routing
   - 类似 MoC，从长上下文里 top-k 检索相似 chunks。
   - 问题是在 high-noise stage，相似度估计不可靠，memory selection 不稳定。

2. Camera-aware explicit memory branch
   - 根据 camera awareness 检索 memory，再通过 cross-attention 注入。
   - 检索稳定，但额外 memory branch 和 layer-wise repeated injection 导致收敛慢、特征不对齐。

最终选择：

- 不把 memory 当外部分支；
- 把 memory latents、past latents、current noisy latents 放进同一个 self-attention space；
- 让 memory、history、prediction features 在同一个 DiT backbone 里共同演化。

### 3.3 Camera-aware retrieval

不是所有历史帧都适合当前视角。Matrix-Game 3.0 根据 camera pose 和 field-of-view overlap 检索 view-relevant history。

推理时，当前 query view 从候选历史帧里选几何 overlap 最高的 memory frame。为了实时，CPU 精确 frustum-overlap 很贵，所以实现 GPU 近似检索，用采样方式估计 overlap。

此外，系统可选保留序列第一个 latent 作为 persistent sink latent，提供全局风格和粗 appearance anchor。

### 3.4 Relative Plucker / geometry condition

检索到 memory 后，还要告诉模型“当前视角和 memory 视角之间是什么几何关系”。论文用 relative Plucker-style cues 编码当前 target 和 selected memory 之间的相对 camera geometry。

作用：

- 帮模型跨视角对齐同一场景；
- 减少把历史信息用在错误视角上的问题；
- 支撑 scene revisitation 时恢复建筑、纹理、布局等。

### 3.5 Memory error injection

训练时 memory 和 past frames 来自 ground truth，但推理时来自模型自己生成，会有误差。为了桥接这个 gap，论文对 memory latents、recent past latents、current prediction latents 共用一个 latent error buffer。

训练中：

- 收集 residual；
- 随机采样 residual；
- 同时扰动 retrieved memory latents 和 recent history latents；
- 让模型学会从 imperfect memory 和 imperfect short-term history 中提取有用信息。

### 3.6 Temporal RoPE 处理

远距离 memory 和当前 prediction 可能因为 RoPE 周期性产生 accidental alignment。论文做了两件事：

- 把 memory / history / prediction latent 的 original frame index 注入 temporal rotary construction；
- 使用 head-wise perturbed RoPE base，让不同 attention heads 有不同有效 rotary base，减轻周期 aliasing 和远距离 memory 的机械复制。

## 4. 和 Lingbot-World 的关键区别

- Lingbot 主要靠 long-context training 和 KV/cache 诱导 emergent memory；Matrix-Game 3.0 是显式 camera-aware retrieval memory。
- Lingbot 的 student 是 causalized high-noise expert；Matrix-Game 3.0 强调 teacher/student/critic 都从同一个 memory-augmented bidirectional base 初始化。
- Lingbot 的 DMD 更像 few-step causal student 蒸馏；Matrix-Game 3.0 的 DMD 明确做 multi-segment self-generated rollout，让 DMD 发生在接近真实 streaming 的历史和 memory 条件下。
- Matrix-Game 3.0 把 memory retrieval 也纳入实时系统工程，用 GPU retrieval、INT8 DiT、VAE pruning 达成 720p@40FPS。

