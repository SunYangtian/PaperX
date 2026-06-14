# JRM: Joint Reconstruction Model for Multiple Objects without Alignment

- Imported from: https://openaccess.thecvf.com/content/CVPR2026/papers/Wu_JRM_Joint_Reconstruction_Model_for_Multiple_Objects_without_Alignment_CVPR_2026_paper.pdf
- PDF URL: https://openaccess.thecvf.com/content/CVPR2026/papers/Wu_JRM_Joint_Reconstruction_Model_for_Multiple_Objects_without_Alignment_CVPR_2026_paper.pdf
- Hash: ee229e3e8a919bfa
- Slug: ee229e3e8a919bfa
- Status: imported

## Structured Analysis

### Motivation

- 论文关注 object-centric / compositional scene reconstruction：将场景表示为一组独立、有位姿的完整对象 mesh，而不是单一整体 mesh。独立对象重建便于交互、编辑和建模，但会丢弃对象之间的上下文信息，尤其是“同一或相似对象在空间/时间中重复出现”的强信号（Section 1, p.1-2）。
- 作者将重复观测拆成三类：spatial instance repetition（同一扫描中多个相同/相似对象，如餐桌旁椅子）、temporal instance repetition（多次扫描中同一对象被重新观测，可能移动）、articulation dynamics（同一对象不同关节状态，如抽屉开合）（Fig. 1, p.1）。
- 现有利用重复实例的方法通常需要显式 instance matching、rigid alignment、registration，再融合观测；这种管线对匹配/配准误差敏感，也难以处理非刚性或子部件变化。JRM 的动机是用生成模型 latent space 中的隐式聚合替代观测空间中的显式对齐（Fig. 2, p.2；Section 1, p.2）。

### Problem Setting

- 输入是若干对象的 multimodal observations，包括分割后的 partial point cloud / depth、稀疏图像视角、VLM-derived text description；相机位姿、深度或点云、instance segmentation 由上游 pipeline 提供。输出是每个对象的完整 3D mesh，并组合成 object-centric scene（Section 3, p.3-4）。
- 给定一个 target object，可只用自身观测做 individual reconstruction，也可引入 support objects，与 target 共同重建。support set 可以来自同一扫描中的重复对象、跨时间重扫对象，或不同 articulation state 的同一对象（Section 4, p.5）。
- 论文不要求输入对象在同一坐标系中被显式刚性对齐；JRM 目标是在无 alignment 的情况下，使相关对象之间传递可用信息，同时每个对象仍服从自己的 pose / state / observation（Abstract, p.1；Section 3.2, p.4）。

### Core Idea

- JRM 将“多次观测同一 subject”类比为 personalized generation：多个对象实例共享一个潜在 subject，应在几何身份上保持一致；但每个实例又有自己的观测条件，因此不能被硬性约束为完全相同（Abstract, p.1；Section 1, p.2）。
- 核心机制是在 3D flow-matching generative model 的 latent denoising 过程中耦合多个对象：各对象 latent token 可通过 attention 相互访问，从而在高维生成 latent space 中学习如何聚合未对齐观测，而不是在输入点云/图像空间做显式配准（Fig. 3, p.3；Section 3.2, p.4）。
- 这种隐式耦合是一种“软约束”：当 source 与 target 真正相同或相似时，模型可利用额外信息；当匹配错误或对象仅部分相似时，模型可学习降低对错误 support 的依赖，避免 alignment-based 融合的灾难性退化（Fig. 6-7, p.7）。

### Method

- 基础模型来自 ShapeR：先用 VecSets-based VAE 将 3D mesh 编码为一组 latent tokens `z ∈ R^{n×L}`，decoder 通过 query point 预测 signed-distance values；再用 DiT 通过 rectified flow matching 从高斯噪声 latent 传输到训练形状 latent manifold（Section 3.1, p.4）。
- 条件 `C` 由多模态编码组成：分割 partial point cloud 用 SparseConvNet 编码，图像用 frozen DINOv2，文本描述用 pretrained T5。ShapeR / FM baseline 对单个对象独立去噪重建（Section 3.1, p.4）。
- JRM 同时生成一个 object group 中 `K` 个对象的 latent token，所有对象共享同一个 DiT 权重。作者将原 DiT 中交替的 single-stream block 替换为 coupled fusion block：把所有对象的 shape latent tokens concat 后送入 shared attention block，再 split 回各对象；注意 coupled attention 只作用于 shape latents，不直接混合各对象 observation tokens，以保持每个实例对自身观测的忠实性（Fig. 3, p.3；Section 3.2, p.4）。
- 训练采用 pair-wise training，而不是依赖完整场景数据。对象对通过 DuoDuoCLIP shape embedding 的 cosine similarity 构造：相似度大于 0.9 视为 positive/similar pair，否则为 negative pair；训练中以 0.1 概率采样 negative pair，以鼓励模型在相关时聚合、不相关时抑制错误信息。尽管只用 pair 训练，attention-based coupling 支持推理时扩展到任意数量对象（Section 3.3, p.4）。

### Key Contributions

- 提出 JRM：一个在生成 latent space 中进行 implicit coupling 的 joint reconstruction model，可联合重建一组未对齐对象，为 repetition-aware reconstruction 提供通用框架（Section 1, p.2）。
- 相比显式 matching + alignment + registration 管线，JRM 不需要硬性对齐观测，因而对 alignment error、association / matching error 更鲁棒，也能自然扩展到 articulation 等非刚性或子部件变化场景（Fig. 2, p.2；Fig. 6, p.7）。
- 方法在训练数据上更可扩展：不需要完整多对象场景监督，只需从大规模单体 3D assets 中构造对象对训练；这与 scene-level multi-instance generation / reconstruction 方法形成区别（Section 2, p.3；Section 3.3, p.4）。

### Experiments / Evidence

- **Temporal instance repetition**：在 100 个合成场景、多次 rescan 设置中，JRM 随 rescan 数增加而提升；例如多模态条件下，CD 从 target-only 的 2.84 降至 1 rescan 的 2.55、3 rescans 的 2.49。FM 在使用预测 alignment 融合时反而退化，显示显式对齐敏感；oracle alignment 的灰色数字说明 FM 的瓶颈主要在 alignment，而非生成能力本身（Table 1, p.5；Fig. 5, p.6）。
- **Spatial repetition 与错误匹配鲁棒性**：当 source 与 target identical 时，FM 和 JRM 都能提升，验证重复观测有益；但 source 为 similar / negative pair 时，FM 明显退化，例如 negative pair CD 达 8.83、F1 为 59.22，而 JRM 保持较稳定，negative pair CD 为 3.04、F1 为 86.31。Fig. 6 进一步显示 FM 对 alignment error 和 matching error 都敏感，JRM 更稳健（Table 2, p.5；Fig. 6-7, p.7）。
- **Articulation 与真实场景**：在 3 个不同 articulation state 的重复对象上，JRM 在 CD 和 F1 上优于 object-level rigid alignment 的 FM-align，也优于独立 FM，说明它能生成一致但不必完全相同的对象状态。真实 Replica / ScanNet++ 上，JRM 整体优于 DPRecon 和 FM；例如 ScanNet++ 中 JRM CD 2.69、F1 85.53，高于 FM 的 CD 4.20、F1 72.96（Table 3, p.7；Table 4, p.8）。

### Conclusions, Limitations, and Relation to Other Work

- 结论是：JRM 通过 latent-space implicit aggregation，在重复实例、跨时间重扫和 articulation 场景中提升 object-centric reconstruction，并减少对显式 alignment / registration 的依赖；实验显示其在合成和真实数据上均优于 independent reconstruction 与 alignment-based baselines（Section 5, p.8）。
- 局限性主要来自 problem setting：论文假设相机位姿、depth/point cloud、instance segmentation 已由上游方法提供，因此重建质量受这些输入精度约束；此外，本文主要研究 repeated observations，虽然作者认为框架可扩展到更多场景上下文线索，但材料中没有给出充分实验证明（Section 3, p.3；Section 5, p.8）。
- 与相关工作相比，JRM 区别于 retrieval / pixel-aligned / scene-level end-to-end reconstruction，也区别于 LivingScenes、Splat-and-Replace 等显式对齐重复实例的方法；它更接近 multi-instance diffusion / personalized generation 中的 token coupling 思路，但将其用于 3D object reconstruction，并重点证明 joint generation 对几何重建和错误鲁棒性的作用（Section 2, p.2-3）。
