# Representation Forcing for Bottleneck-Free Unified Multimodal Models

- Imported from: https://arxiv.org/abs/2605.31604
- PDF URL: https://arxiv.org/pdf/2605.31604.pdf
- Hash: ac519bcaaad0823a
- Slug: ac519bcaaad0823a
- Status: imported

## Structured Analysis

### Motivation

- 现有 unified multimodal models（UMMs）希望在同一模型中同时完成理解与生成，但主流做法仍在图像生成路径依赖单独预训练并冻结的 VAE：先把图像压到 latent，再在 latent 上扩散，最后由固定 decoder 还原像素。这种 VAE latent space 不是为 UMM 的联合目标优化，且有损压缩会给生成质量设置结构性上限（Abstract, p.1；Introduction, p.1）。

- 直接移除 VAE、改为 pixel-space generation 看似更端到端，但在 UMM 中效果不佳。作者认为原因是 UMM 面对更宽的图像分布和更复杂的文本条件，模型需要从同一 raw pixel signal 同时学习高层语义结构与低层细节，训练负担过重，导致 naive pixel-space 生成存在明显质量差距（Fig. 1, p.2；Introduction, p.2）。

- 论文的核心动机是：是否可以不用外部 VAE latent，又为 pixel-space diffusion 提供某种结构性中间表示，使模型先确定 object identity、spatial layout、scene composition 等高层结构，再渲染低层细节（Section 3, p.4）。

### Problem Setting

- 目标是在统一 transformer backbone 中处理 multimodal understanding 与 text-to-image generation，同时去除外部生成 latent space，即构建 bottleneck-free、end-to-end 的 UMM。输入包括文本 token 与图像；输出可以是文本，也可以是像素图像（Abstract, p.1；Fig. 1, p.2）。

- 对比对象包括三类：VAE-based UMMs，依赖冻结 VAE encoder/decoder；naive pixel-space UMMs，直接用 pixel head 生成像素但缺少结构引导；Representation Forcing UMMs，在文本与像素之间插入由模型自身预测的 representation tokens（Fig. 1, p.2）。

- 论文强调 controlled comparison：在相同架构、数据与训练预算下比较 Pixel、Pixel+RF、VAE、VAE+RF 四种变体，差异只在生成路径是否使用 VAE，以及是否启用 RF（Section 4.1, p.6）。

### Core Idea

- Representation Forcing（RF）的核心是把“理解路径中的视觉表示”转化为“生成路径中的预测目标”。理解时，image encoder 从图像中提取高层 visual representations；生成时，没有图像可用，decoder 必须先根据文本自回归预测这些表示，再在同一上下文中生成像素（Section 3, p.4）。

- 这些 predicted representation tokens 不是最终可见图像的一部分，而是留在 transformer sequence 中作为 in-context conditioning，让后续 noisy pixel patches 通过 shared self-attention 直接 attend 到它们。这样不需要额外 cross-attention、adapter 或外部 diffusion decoder（Section 3.2, p.5-p.6；Fig. 3, p.5）。

- RF 的双重“forcing”含义是：understanding encoder 的表示迫使 decoder 学会高层视觉结构；decoder 预测出的表示又迫使 pixel generation 遵循预期语义布局。由此，感知与生成被绑定到同一个、模型内部学习得到的表示空间中（Section 3.2, p.5）。

### Method

- 表示来源：作者使用 jointly trained understanding encoder 的 patch-level features 作为中间表示来源。为适配 next-token prediction 与推理采样，将连续特征通过 online vector quantization 离散化为 representation token 序列；离散化也被认为有助于保留高层结构、丢弃低层细节，从而分离“结构预测”和“像素渲染”（Section 3.1, p.4）。

- 量化细节：由于 encoder 在联合训练中不断变化，目标特征来自 image encoder 的 EMA copy，以获得更稳定的 discrete assignment。每个 patch feature 与 K 个 learnable prototype embeddings 计算 cosine similarity，并分配到最近 prototype；codebook 通过类似 SwAV 的 momentum update 在线更新，并用 Sinkhorn-Knopp balancing 防止 codebook collapse（Section 3.1, p.4-p.5）。

- 序列与注意力：统一序列为 `[text tokens, representation tokens, pixel patches]`。text 与 representation tokens 使用 causal autoregressive attention；noisy pixel patches 彼此之间双向 attention，并 causal attend 到前面的文本和 representation tokens。这使 representation tokens 成为像素扩散的上下文结构引导（Fig. 3, p.5；Section 3.2, p.5-p.6）。

- 训练目标：模型采用 BAGEL 风格的 Mixture-of-Transformers（MoT）架构，共享 self-attention，但按 token 类型路由到理解、representation prediction、pixel generation 三组 FFN experts。总损失为 `L = LLM + LFM + LRep`，其中 `LLM` 是文本 next-token 交叉熵，`LRep` 是 representation token 交叉熵，`LFM` 是 pixel flow matching loss。训练时以 0.1 概率独立丢弃 text conditioning 和 representation token sequence，以支持 classifier-free guidance（Section 3.3, p.6）。

- 推理流程分两步：decoder 首先从文本 prompt 自回归生成完整 representation token sequence；然后在文本与 predicted representations 条件下，从 Gaussian noise 迭代去噪，在 pixel space 直接合成最终图像（Section 3.3, p.6）。

### Key Contributions

- 论文提出 RF 作为一种去除 VAE bottleneck 的 UMM 训练机制：不再依赖外部 generative latent space，而是让 decoder 预测模型自身 understanding encoder 的表示，并将这些表示作为 pixel-space diffusion 的 in-context scaffold（Abstract, p.1；Introduction, p.3）。

- 论文显示 RF 不只是改善生成，也影响理解：Pixel+RF 在多个理解 benchmark 上优于 Pixel，并且总体上比 VAE+RF 更强，说明 pixel-space generation 与 unified multimodal modeling 可能更兼容（Table 2, p.8）。

- 与已有 representation-guided generation 不同，RF 不是用冻结外部 encoder 的表示作为辅助对齐损失，也不是 LLM 预测特征后交给外部 diffusion decoder，而是在同一 backbone 内把 representation prediction 纳入自回归生成过程，使表示在推理时显式参与像素生成（Related Work, p.4；Table 3b, p.9）。

### Experiments / Evidence

- 文生图主结果：RF-Pixel 在不使用 LLM rewriter 时 GenEval overall 达到 0.84，略高于 BAGEL 的 0.82，并与 BLIP3-o 的 0.84 持平；使用 LLM rewriter 时达到 0.88，匹配 unified models 中的 SOTA 水平。DPG-Bench 上 RF-Pixel 为 84.15，与强 VAE-based unified models 相当（Table 1, p.7；Section 4.2, p.7-p.8）。

- 理解能力：Pixel+RF 在 8 个理解 benchmark 中提升 6 个，包括 MMMU +4.3、MME +3.6、BLINK +3.6、AI2D +4.5、RealWorldQA +2.7；但 DocVQA -2.0、ChartQA -0.4 略降。作者认为 RF 更帮助高层视觉理解，对精细文字识别和布局解析支持较弱。Pixel+RF 在 8 项中有 6 项超过 VAE+RF（Table 2, p.8）。

- 消融最关键证据：无 RF 的 pixel-space GenEval 只有 0.25，加入 RF 后跃升到 0.76，接近 VAE+RF 的 0.77；VAE 设置中 RF 也从 0.52 提升到 0.77。与 REPA 式辅助 alignment 相比，REPA 只到 0.43，而 RF 到 0.76，说明“在序列中显式预测并条件化”比隐式特征对齐更有效。连续表示回归几乎无效，仅 0.26，而离散 token 达到 0.76（Table 3a-c, p.9；Fig. 4, p.10）。

### Conclusions, Limitations, and Relation to Other Work

- 结论上，RF 表明 pixel-space UMM 的质量差距并非必须由外部 VAE 解决；只要模型先预测自身理解表示，再用这些表示指导像素扩散，就能在生成质量上接近 VAE-based UMM，并同时改善多模态理解。这支持“perception and generation share a single end-to-end learned representation space”的方向（Conclusion, p.10）。

- 局限性方面，模型并非从零开始多模态预训练，而是初始化自 pretrained LLM；作者认为完全 from-scratch multimodal pretraining 可能产生更丰富的 joint representations。此外，论文只研究 still-image generation，未扩展到 video 或其他 temporal modalities（Discussion, p.10）。

- 与相关工作的关系：VAE/VQVAE-based UMMs 仍依赖外部视觉 tokenizer 或 generative latent；LLM+external diffusion 系列让 LLM 预测视觉特征但渲染仍由外部 diffusion decoder 完成；REPA/RAE 等方法使用冻结外部表征或辅助对齐。RF 的区别在于 representation 来自 jointly trained understanding encoder，并由同一 decoder 自回归预测、在同一 transformer 序列中直接指导 pixel diffusion（Related Work, p.3-p.4）。
