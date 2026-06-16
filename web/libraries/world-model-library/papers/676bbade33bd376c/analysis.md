# Veda: Scalable Video Diffusion via Distilled Sparse Attention

- Imported from: https://arxiv.org/pdf/2605.30325
- PDF URL: https://arxiv.org/pdf/2605.30325.pdf
- Hash: 676bbade33bd376c
- Slug: 676bbade33bd376c
- Status: imported

## Structured Analysis

### Motivation

- 高分辨率、长时长视频生成中的 Diffusion Transformer（DiT）主要瓶颈来自 self-attention 对时空 token 长度 $N=THW$ 的二次复杂度 $O(N^2)$；在 720P、数百帧场景中，attention 成为主要计算与显存开销（Section 1, p.1；Section 3.1, p.3）。
- Sparse attention 是自然加速方向，但在 GPU 上必须以 tile/block 粒度执行，而非 token 粒度。因此问题从“删哪些 token pair”转化为“每个 query tile 选择哪些 key tile”，并需要 sparse kernel 将稀疏性转化为真实 wall-clock speedup（Section 1, p.1；Section 3.1, p.4）。
- 现有方法在高稀疏率下容易产生结构性退化：空间扭曲、水波纹、随机噪声和时间闪烁。论文的核心观察是：质量退化并非由 sparsity ratio 本身决定，而主要由 sparse mask 是否对齐 full attention 的 tile-wise geometry 决定（Fig. 3–5, p.4）。

### Problem Setting

- 给定视频 latent 形状 $(T,H,W)$，展平为长度 $N=THW$ 的 token 序列。单个 attention head 中 $Q,K,V\in\mathbb{R}^{N\times d}$，full attention 为  
  $$
  A=\mathrm{Softmax}\left(\frac{QK^\top}{\sqrt d}\right),\quad O=AV .
  $$
  其计算和存储复杂度为 $O(N^2)$（Section 3.1, p.3）。
- Tile-level sparse attention 将 token 分为 $N_T$ 个大小为 $B$ 的 tile，使用二值 tile mask $\widetilde M_{ij}\in\{0,1\}$ 表示 query tile $i$ 是否 attend key tile $j$。在固定 Top-$k$ 预算下，每个 query tile 只保留 $k$ 个 key tiles：  
  $$
  |\{j\mid \widetilde M_{ij}=1\}|=k .
  $$
  被选中的 key/value tiles 拼接后执行局部 attention，从而允许 tile-skipping kernel 跳过未选 tile（Section 3.1, p.4）。
- 评价 mask 质量时，作者定义相对 full-attention oracle 的 tile recall。若 $S_i^{fu}$ 是 full attention 聚合后 Top-$k$ key tile 集合，$S_i^{sp}$ 是稀疏方法选择集合，则  
  $$
  \mathrm{Recall@}k=\frac{1}{N_T}\sum_{i=1}^{N_T}\frac{|S_i^{sp}\cap S_i^{fu}|}{k}.
  $$
  更高 recall 与更少结构性 artifact 强相关（Fig. 5, p.4）。

### Core Idea

- Veda 的核心思想是把 sparse tile selection 从“由扩散训练隐式学出”改为“显式蒸馏 full attention 的 tile-level ranking”。也就是说，目标不是简单提高稀疏率，而是在固定 Top-$k$ tile budget 下最大程度恢复 full attention 的 tile-wise score structure（Section 4, p.5）。
- 论文通过 oracle mask 实验证明：即使在 90% sparsity 下，只要 mask 来自 full attention 的高响应 tile，生成质量仍可保持；而 average pooling 等粗糙估计会错选 tile 并导致明显 artifacts。这说明“mask precision / alignment”比 sparsity ratio 更关键（Fig. 4, p.4）。
- Veda 同时处理两个误差源：一是动态方法中 tile importance 估计不准，二是统一 tiling 无法适应不同 head 的时空注意力模式。对应设计为 statistics-aware tile scoring 与 Head-Aware Tiling（Section 4.1–4.2, p.5–6）。

### Method

- **Full-attention target construction**：Veda 先从 full-attention backbone 构造 tile-level supervision。给定 token-level attention $A^\ast=\mathrm{Softmax}(QK^\top/\sqrt d)$，对每个 query-key tile 区域做 max pooling：  
  $$
  S^{tgt}_{ij}=\max_{(u,v)\in \mathrm{Tile}(i,j)}A^\ast_{uv}.
  $$
  选择 max 而非 average 的原因是 attention 往往稀疏且 peaky，平均会稀释关键高响应依赖（Section 4.1, p.5）。
- **Statistic-aware estimator**：每个 tile 的压缩表示使用 TripPool，即拼接平均值、最大值、最小值：  
  $$
  \mathrm{TripPool}[\cdot]=\mathrm{Avg}[\cdot]\oplus\mathrm{Max}[\cdot]\oplus\mathrm{Min}[\cdot].
  $$
  然后通过 head-specific MLP $\phi_q,\phi_k$ 投影到共享空间，并用点积预测 tile score：  
  $$
  S^{pred}_{ij}=\frac{\phi_q(\mathrm{TripPool}[\widetilde Q_i])\cdot \phi_k(\mathrm{TripPool}[\widetilde K_j])^\top}{\sqrt{d'}} .
  $$
  该设计旨在捕获 tile 内 salient peaks，降低平均池化造成的估计误差（Section 4.1, p.5）。
- **Distillation objective 与训练稳定性**：对 $S^{tgt}$ 做 row-wise normalization，对 $S^{pred}$ 在 key tiles 维度做 softmax，得到 $A^{tgt},A^{pred}$，最小化  
  $$
  L_{distill}=D_{KL}(A^{tgt}\Vert A^{pred}).
  $$
  Backbone 仍使用标准 diffusion denoising objective $L_{diff}$。进入 estimator 的 backbone features 使用 stop-gradient，以解耦 mask learning 和 feature learning；作者观察到若让梯度回传至 base model，会明显损害生成质量（Section 4.1, p.5–6）。
- **Head-Aware Tiling**：不同 attention heads 在空间局部关系和长程时间依赖上差异明显，因此 Veda 为每层每头选择 tiling $\pi_{l,h}=(p_t,p_h,p_w)$，约束 $p_tp_hp_w=B$。在 calibration set 上枚举候选 $\Omega$，选择使 sparse attention output 最接近 full attention output 的配置：  
  $$
  \pi^\ast_{l,h}=\arg\min_{\pi\in\Omega}\mathbb{E}_{x\sim D_{cal}}\left[\|O^{fu}_{l,h}(x)-O^{sp}_{l,h}(x;\pi)\|_F^2\right].
  $$
  这减少统一 tiling 带来的 structural mismatch（Section 4.2, p.6；Fig. 6, p.5）。
- **Hardware kernel**：Veda 使用基于 ThunderKittens DSL 的 tile-skipping sparse attention kernel，利用 Hopper GPU 的 TMA 与 Warp Specialization，以 producer-consumer 方式只加载被选 key/value tiles，并用 WGMMA 执行 dense tile matmul。该 kernel 在 480P、81 帧序列上达到约 FlashAttention-3 MFU 的 80%；训练时的 full-attention heatmap supervision 也通过两阶段 TileLang kernel 近似以 $0.9\times$ FA3 throughput 生成（Section 4.3, p.6）。

### Key Contributions

- 提出一个经验性但关键的判断：视频 DiT sparse attention 的质量瓶颈主要不是稀疏率，而是 sparse mask 与 full attention tile-wise geometry 的对齐程度；oracle mask 在高稀疏率下仍能保持质量，为该判断提供直接证据（Fig. 4, p.4）。
- 将 tile selection 表述为 explicit reconstruction / distillation problem，用 full attention 监督动态 tile scoring，而不是依赖 diffusion objective 隐式学习稀疏结构；这也是 Veda 与 VSA、VMOBA 等动态稀疏方法的核心区别（Fig. 2, p.2；Section 4.1, p.5）。
- 结合 TripPool statistics、head-specific estimator、Head-Aware Tiling 和硬件友好的 tile-skipping kernel，使高 sparsity 能同时保持生成质量与实际推理加速，而非仅降低理论 FLOPs（Section 4, p.5–6）。

### Experiments / Evidence

- **质量证据**：在人评 Waver-bench 1.0 上，Waver-T2V-1B、480P、81 帧条件下，Veda 90% sparsity 与 full attention 达到感知接近；Motion Quality 有 63% tie，Visual Quality 中 Veda/full attention 基本持平。Veda 95% sparsity 相比 VSA 87.5% sparsity 仍更优，等 95% sparsity 时在 VQ 上 76% vs. 24%，OQ 上 39% vs. 16%（Fig. 7, p.7–8）。
- **效率证据**：Waver-T2V-12B 720P、121 帧单层 latency 从 FA3 的 315.3 ms 降至 78.3 ms，速度提升 4.03×；Wan2.1-T2V-14B 720P、81 帧从 583.7 ms 降至 220.7 ms，提升 2.64×。端到端长视频场景中，Waver-T2V-12B 720P、241 帧采样时间从 19.4 分钟降至 3.8 分钟，达到 5.1× speedup（Fig. 1, p.1；Fig. 8, p.7–8）。
- **消融证据**：Head-Aware Tiling 相比最佳静态 tiling 在 Motion Quality 和 Overall Quality 上分别提升 +7.2% 与 +9.6%；Triplet pooling 的 score estimator training loss 为 0.912，优于 Avg pooling 0.965 和 MaxMin 0.982，支持统计增强 tile descriptor 的必要性（Table 2, p.9；Fig. 10 信息见文字描述, p.9）。

### Conclusions, Limitations, and Relation to Other Work

- Veda 相比静态稀疏方法（如 SVG、STA）更能适应动态、head-specific 的 attention geometry；相比 VSA、VMOBA 等动态方法，它引入 full-attention distillation 作为显式监督，减少 pooled feature 粗估带来的 mask drift（Section 2, p.3；Fig. 2, p.2）。
- 与 TeaCache、PAB 等跨 denoising step 复用 activation 的方法，以及 CausVid、rCM 等减少采样步数的 distillation 方法不同，Veda 直接降低每一步 attention 的二次时空成本，因此原则上与这些方向正交、可组合（Section 2, p.3）。
- 局限与未来方向主要包括：进一步做 kernel-level fusion 以减少 mask preparation overhead；在超过 95% sparsity 时维持高 MFU 的调度策略；使用更丰富的 distillation signals 或 adaptive sparsity，在不同 timestep 与 head 间动态分配计算；以及跨相邻 diffusion steps 轻量缓存 tile scores 以提升稳定性（Section 6, p.9）。
