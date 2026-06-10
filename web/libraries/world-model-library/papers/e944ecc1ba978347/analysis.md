# Lingbot-World: Advancing Open-source World Models

## 关注问题

1. Teacher model 训练流程，包括训练视频长度。
2. 长视频蒸馏。
3. Memory 机制。

## 1. Teacher Model 训练流程

这里的 teacher 基本对应 Stage II 得到的 middle-trained MoE world model，也就是高质量但非实时的 LingBot-World-Base。

训练是三段式：

1. Stage I: Pre-training
   - 不是从零训练，而是采用 Wan2.2 14B image-to-video diffusion model 作为基础视频先验。
   - 作用是保留高质量纹理、自然视频动态、物体持续性和时空一致性。

2. Stage II: Middle-training
   - 把短视频 I2V diffusion model 训练成 bidirectional world model。
   - 继承 Wan2.2 的 MoE 结构。
   - 两个 expert：high-noise expert 负责全局结构和粗布局，low-noise expert 负责细节和高频时空纹理。
   - 每个 expert 约 14B，总参数约 28B，但每个 denoising timestep 只激活一个 expert。
   - 训练长度采用 curriculum：先用 5 秒视频训练，再逐步扩展到 60 秒。
   - 同时做 image-to-video 和 video-to-video / continuation 多任务训练，让模型既能从单帧启动，也能从历史视频继续预测未来。

3. Action-conditioned finetuning
   - 连续相机旋转用 Plucker embeddings。
   - 离散动作如 W/A/S/D 用 multi-hot。
   - 两者拼接后通过 AdaLN 注入 DiT block。
   - 主 DiT backbone 冻结，只训练 action adapter、action projection、AdaLN 参数，以避免破坏视频生成质量。

训练 60 秒、28B MoE 的显存压力很大，所以论文用 FSDP2 分片参数、梯度和优化器状态，用 Ulysses context parallel 按 temporal sequence 维度切分长上下文。

## 2. 长视频蒸馏

Stage III 把 bidirectional teacher 变成实时 autoregressive student，也就是 LingBot-World-Fast。

核心步骤：

1. Causal architecture adaptation
   - Student 从 teacher 的 high-noise expert 初始化，因为 high-noise expert 更擅长 dynamics 和全局结构。
   - 将 full bidirectional temporal attention 改成 block causal attention。
   - Chunk 内部仍然 bidirectional，保证局部一致性。
   - Chunk 之间 causal，只能看当前和过去 chunk。
   - 推理时用 KV cache 流式生成。

2. Diffusion forcing training
   - 训练序列切成多个 chunk，每个 chunk 分配独立 diffusion timestep。
   - 模型只在少量选定 timestep 上训练，这些 timestep 后面作为蒸馏目标。
   - 由于 student 来自 high-noise expert，论文还加入 timestep 0 的 clean frame supervision，用来补上 low-noise expert 的细节能力缺口。

3. Few-step distillation + long-horizon training
   - Self-rollout extended horizon training：student 用自己生成的历史帧继续生成，模拟真实 AR 推理时的分布偏移。
   - Rolling KV cache 存之前生成帧。
   - 只对最近 K 个 generation steps 反传，但 forward 保留完整上下文，降低长 rollout 训练成本。
   - DMD：middle-trained MoE teacher 作为 fixed real score model；fake score model 用同一个 MoE teacher 初始化，但在 student 生成视频上继续训练。
   - Adversarial objective：在 fake score network 上加 discriminator head，用真实视频监督，缓解 DMD 后 student 画质下降和 teacher bias 继承。

直观理解：teacher 是“慢但强”的 60 秒 bidirectional world model；student 是“快且因果”的流式模型。蒸馏目标不是只复制单帧质量，而是尽量保留 action-following、结构一致性和长 rollout 稳定性。

## 3. Memory 机制

这篇的 memory 不是显式外部记忆模块。论文在 limitation 里明确说明：当前 memory 是从 context window 里涌现出来的能力，不是 explicit storage module。

它的 memory 来源主要有三层：

1. 长视频 curriculum
   - 训练从 5 秒逐步扩到 60 秒，让模型在训练中反复看到长时间上下文，从而学习减少 forgetting 和 drift。

2. Video-to-video continuation
   - 模型不仅从单图生成，也从历史视频继续预测未来。这会逼它利用历史帧作为隐式状态。

3. Self-attention / causal KV cache
   - Base teacher 的 bidirectional attention 有利于全局 temporal dependency。
   - Fast student 改成 block causal attention 后，用 KV cache 维护历史 chunk 表示。

论文展示的 memory 能力包括：

- 静态 landmarks 离开视野 60 秒后仍能保持结构。
- 相机向前移动后，返回正面视角时远处桥梁变近，说明模型不只是记像素，而是在隐式更新空间关系。
- 车辆离开视野后仍沿道路运动，再出现时位置合理。
- Figure 13 声称可生成最长 10 分钟 coherent sequence。

但需要注意：这不是稳定可控的 memory system。作者也承认长时间 gameplay 仍有 drifting，未来要做 explicit memory module。也就是说，Lingbot-World 的 memory 更像“长上下文训练 + attention/KV cache 诱导出的隐式空间时间状态”，不是 RELIC/WorldMem 那种明确的检索式或外部记忆库。

## 4. Action 注入机制与交互实现

Lingbot-World 的 action 注入不是把动作写进文本 prompt，而是在 DiT block 内部加入一条独立的 action conditioning path。它的目标是把“场景生成能力”和“运动控制能力”解耦：文本负责语义和外观，action 负责相机/运动/交互轨迹。

### Action 表示

论文使用 hybrid action representation：

1. 连续相机运动
   - 用 Plucker embeddings 表示 camera rotation / 3D transformation。
   - 这样比普通角度数值更适合表达连续三维几何变化。

2. 离散键盘动作
   - W/A/S/D 等离散控制编码成 multi-hot vector。
   - 这类动作代表前进、后退、左右移动等逻辑状态变化。

3. 融合
   - 连续相机动作和离散键盘动作沿 channel dimension 拼接。
   - 得到 fused action embedding。

### 注入位置

Action 被注入到 DiT block 中，具体是通过 AdaLN / adaptive layer normalization：

1. video latent 先经过 self-attention，学习时空一致性和隐式 spatial memory。
2. action 经过 Plucker Encoder / action projection。
3. action embedding 被变成 normalization 的 scale 和 shift。
4. 这些 scale/shift 调制 video latent 的 normalized features。
5. 最后 cross-attention 再接入 text embedding。

因此，动作不是作为普通 token 被 cross-attend，也不是简单拼到文本里，而是直接调制 DiT block 的内部特征。

### 训练方式

在 action-conditioned finetuning 阶段，论文冻结主 DiT blocks，只训练新加的 action adapter：

- action embedding projection；
- Plucker/action encoder 相关参数；
- AdaLN scale/shift 参数。

这样做有两个目的：

1. 保留 fundamental world model 的视频质量、长时一致性和 memory 能力。
2. 避免 action-labeled data 较少或偏合成时，全量 finetune 导致 catastrophic forgetting。

### 推理时如何实现交互

实时交互依赖 Stage III 的 autoregressive / causal student：

1. 用户每个时间段输入动作，例如 W/A/S/D 和鼠标/相机方向。
2. 系统把这些动作编码成 fused action embedding。
3. 当前 chunk 生成时，模型看历史 KV cache、当前 noisy latent、文本条件和当前 action。
4. Action 通过 AdaLN 调制 DiT block，使生成的下一段视频符合动作。
5. 生成出的 chunk 被加入历史 cache，下一轮动作继续驱动下一个 chunk。

交互闭环可以理解为：

```text
当前视觉历史 + 当前用户动作 + 文本/场景条件
        -> 生成下一小段视频
        -> 更新历史 KV cache
        -> 等待下一步用户动作
```

这就是它从普通 video generator 变成 interactive world model 的关键。

### 局限

论文也承认当前 action space 仍然有限，主要覆盖 navigation 和 basic movements；精确 object-level interaction 仍然困难，例如在复杂桌面上拿起特定杯子。这说明它的 action 注入目前更适合“移动/转向/视角控制”，还不是完整的物体操作或多智能体交互控制。
