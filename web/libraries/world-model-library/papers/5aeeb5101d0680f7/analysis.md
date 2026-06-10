# An Image is Worth 32 Tokens for Reconstruction and Generation

- Imported from: https://arxiv.org/pdf/2406.07550
- PDF URL: https://arxiv.org/pdf/2406.07550.pdf
- Hash: 5aeeb5101d0680f7
- Slug: 5aeeb5101d0680f7
- Status: imported

## Structured Analysis

### Motivation

- 现有图像生成系统普遍先把像素压缩为 latent tokens，再在 latent space 中训练生成器，以降低高分辨率图像建模成本。VQGAN、MaskGIT 等方法通常把图像编码成二维 latent grid，例如 256 或 1024 个 tokens，但这种设计默认 latent token 与图像 patch 存在固定空间对应关系（Section 1, p.2）。
- 论文质疑“图像 tokenization 是否必须保留 2D 结构”。作者认为自然图像存在明显区域冗余，相邻 patch 往往相似，固定 2D grid 会限制 tokenizer 利用这种冗余进行更强压缩（Section 1, p.2）。
- 受 object queries、perceiver resampler 和 MLLM 中 1D 视觉 token 表示启发，作者尝试把图像压缩成固定长度的一维离散序列，同时要求它不仅保留高层语义，还能支持低层细节重建和图像生成（Section 1, p.2；Section 2, p.3）。

### Problem Setting

- 目标是学习一个 image tokenizer / de-tokenizer：输入图像，输出紧凑的离散 latent tokens；再从这些 tokens 重建图像，并可作为 MaskGIT 类生成器的 token space（Section 3, p.4）。
- 与传统 VQ-VAE / VQGAN 不同，传统方法将图像编码为 `H/f × W/f × D` 的二维 latent grid；TiTok 将图像表示为长度为 `K` 的 1D latent sequence，`K` 可独立于输入分辨率设定，例如 32、64、128（Section 3.1-3.2, p.4-p.5）。
- 核心问题不是单纯压缩，而是在极小 token 数下同时满足三类要求：合理重建质量、可训练的生成 latent space、显著更高的训练与采样效率（Section 4.1, p.6；Fig. 4, p.7）。

### Core Idea

- TiTok 的核心主张是：图像可以由少量全局 latent tokens 表示，而不必让每个 latent token 对应固定图像区域。这样每个 token 可通过 Transformer attention 聚合全图信息，并在解码时参与重建任意区域（Fig. 3, p.4；Section 3.2, p.5）。
- 这种 1D 表示打破了二维网格约束，使 latent size 与图像分辨率解耦。对于 256×256 图像，传统 VQ tokenizer 常见为 256 或 1024 tokens，而 TiTok 可使用 32 tokens（Section 3.2, p.5）。
- 作者强调，将 2D latent flatten 成 1D 序列并不等价于 TiTok，因为 flatten 后的 token 仍隐含固定空间网格对应；TiTok 的 latent tokens 是独立引入的可学习序列，经过 encoder 后才作为图像表示（Section 3.2, p.5）。

### Method

- TiTok 包含 ViT encoder、vector quantizer 和 ViT decoder。图像先被 patchify 得到 patch embeddings，再与 `K` 个 latent tokens 拼接输入 ViT encoder；encoder 输出中只保留 latent tokens，形成 `Z1D`（Fig. 3, p.4；Section 3.2, p.5）。
- 量化阶段沿用 VQ 模型思路：每个 latent embedding 被映射到 codebook 中最近的 code。解码时，量化后的 1D latent tokens 与一组 mask tokens 拼接输入 ViT decoder，decoder 预测并重建图像（Section 3.1-3.2, p.4-p.5）。
- 生成阶段不改 MaskGIT 主框架，只把其 VQGAN tokenizer 替换为 TiTok。训练时随机 mask 一部分 latent tokens，bidirectional transformer 预测被 mask 的 token ID；推理时从全 mask 序列逐步采样 tokens，再经 TiTok decoder 还原为图像（Section 3.2, p.5）。
- 训练采用 two-stage strategy。第一阶段不直接回归 RGB，而是用已有 MaskGIT-VQGAN 产生的离散 proxy codes 作为监督，以避免复杂 GAN/perceptual loss 调参；第二阶段可冻结 encoder 和 quantizer，仅 fine-tune decoder 到像素空间，以提升重建质量（Section 3.3, p.6）。

### Key Contributions

- 提出 Transformer-based 1-Dimensional Tokenizer（TiTok），将图像压缩为极短的一维离散 token 序列，用于 reconstruction 和 generation，是对传统 2D VQ tokenizer 工作流的结构性替代（Fig. 1, p.1；Section 3.2, p.5）。
- 系统展示 token 数、tokenizer 模型规模、重建质量、语义性和生成质量之间的关系：增加 token 数会提升重建，但 128 之后收益变小；扩大 tokenizer 尺寸可在更少 tokens 下保持性能（Fig. 4, p.7）。
- 证明紧凑 latent space 不只是节省计算，还可能改善生成训练。作者观察到 32-token 变体虽然重建质量不一定最优，但可获得更好的生成性能，说明更紧凑、更语义化的 latent tokens 对 MaskGIT 训练有利（Fig. 4, p.7）。
- 在 ImageNet 256 和 512 benchmarks 上，TiTok 以远少于 2D tokenizer 的 tokens 达到竞争性或更好的 gFID，并显著提升采样速度（Table 1, p.8；Table 2, p.9）。

### Experiments / Evidence

- 初步实验显示，TiTok-L 使用 32 latent tokens 即可取得优于 256-token 2D VQGAN 的重建表现；token 数从 16 增加到 128 时提升明显，但超过 128 后收益趋于边际（Fig. 4a, p.7）。
- 在 ImageNet 256×256 上，TiTok-L-32 仅用 32 tokens 达到 rFID 2.21，接近 MaskGIT-VQGAN 的 rFID 2.28；在相同 MaskGIT-ViT generator 和 8 sampling steps 下，gFID 从 MaskGIT baseline 的 6.18 降至 2.77。TiTok-S-128 进一步达到 gFID 1.97，优于 DiT-XL/2 的 2.27，并有约 13× speed-up（Table 1, p.8）。
- 在 ImageNet 512×512 上，TiTok-L-64 达到 gFID 2.74，优于 DiT-XL/2 的 3.04，吞吐 41.0 samples/s 对比 0.1 samples/s，约 410× faster；TiTok-B-128 达到 gFID 2.13，并仍比 DiT-XL/2 快约 74×（Table 2, p.9）。
- Ablation 表明 two-stage training 对最终重建质量很关键：TiTok-L-32 从 baseline rFID 6.59，经更大 codebook、更多训练和 decoder fine-tuning 后提升到 rFID 2.21；proxy codes 训练下 TiTok-B-64 达到 rFID 1.70，优于 MaskGIT-VQGAN 的 2.28（Table 3, p.9）。

### Conclusions, Limitations, and Relation to Other Work

- 论文结论是，图像 tokenization 不必局限于 2D latent grid；紧凑 1D tokens 可以在重建和生成中同时有效，并将常见 2D tokenizer 的 token 数减少 8× 到 64×（Section 5, p.10）。
- 相比 VQGAN、ViT-VQGAN、RQ-VAE、MAGVIT-v2 等仍基于二维 latent grid 的 tokenizer，TiTok 的主要差异在于取消 latent token 与图像 patch 的固定空间对应，而不是仅改进 codebook 或量化策略（Section 2, p.3）。
- 相比 CLIP/MLLM 类视觉 token，它不是只追求高层语义，而是面向图像重建和生成，需要同时恢复 layout、纹理和低层细节；因此 TiTok 更接近 VQ-VAE/VQGAN tokenizer 的任务设定（Section 2, p.3）。
- 局限方面，材料中明确可见的限制包括：训练仍依赖 off-the-shelf MaskGIT-VQGAN 产生 proxy codes；作者说明更先进 quantization 方法可能进一步受益但不是本文重点；大规模数据训练和更强单阶段 recipe 留作未来工作。其他失败案例、泛化到非 ImageNet 数据或文本条件生成的限制，材料不足，无法确定（Section 3.3, p.6；Table 2 note, p.8；p.10）。
