### Papers

- Current: Surflo: Consistent 3D Surface Flow Model with Global State (`5b3d3f36094d1868`)
- Compared: NOVA3R: Non-pixel-aligned Visual Transformer for Amodal 3D Reconstruction (`812b0f64126d3bf7`)

### Result

## High-Level Takeaway

两篇论文都反对传统 pixel-aligned / per-view 3D reconstruction，主张用全局、view-agnostic scene representation 来减少多视角冗余和重叠伪影。但重点不同：**Surflo 更强调“从同一个 global state 任意分辨率解码出一致表面”**，目标是 oriented surface points / mesh；**NOVA3R 更强调“amodal / complete 3D reconstruction”**，目标是恢复可见与不可见区域的完整 non-pixel-aligned point cloud。

## Comparison Table

| Paper | problem | method | evidence | strength | limitation |
|---|---|---|---|---|---|
| Paper 1: Surflo | 从可变数量 unposed RGB views 中恢复一致 3D surface，避免 per-view pointmaps 随视角数线性增长、重叠且难融合 | 冻结 VGGT 提取几何特征；用 Perceiver-style compressor 压缩为固定大小 global latent $z \in \mathbb{R}^{K \times D}$；flow matching 独立生成任意数量 oriented surface points；推理时用 photometric / depth rendering guidance 耦合局部点 | 材料称在 8 个 3D reconstruction benchmarks 上匹配或超过 feed-forward baselines 的 surface metrics；比 Gaussian Wrapping 等 optimization-based methods 快一个数量级；图示展示从 16 张 unposed images 输出 clean mesh | 同一 latent 可解码从几千到百万级点；输出不受固定 grid/token budget 限制；面向 surface / mesh，强调 multi-view consistency 和任意分辨率 | 独立 per-point decoding 天然可能产生局部不一致，需要 inference-time guidance；对完整训练细节、具体指标数值、失败案例，材料不足，无法确定 |
| Paper 2: NOVA3R | 从一个或多个 unposed images 做 non-pixel-aligned amodal 3D reconstruction，解决 pixel-aligned 方法只恢复可见面、重叠区域重复结构的问题 | 两阶段设计：Stage 1 用 3D point autoencoder 将 complete point clouds 压缩为 latent scene tokens，并用 flow-matching decoder 解码；Stage 2 用 VGGT image encoder 加 learnable scene tokens 聚合多视角信息，映射到 decoder latent space；推理时输出 complete non-pixel-aligned point cloud | 材料称在 scene-level 和 object-level datasets 上超过 SOTA，提升 reconstruction accuracy 和 completeness；ICLR 2026 conference paper；但具体表格数值材料不足，无法确定 | 强调 complete / amodal reconstruction，可恢复 visible 与 invisible points；统一 object-level 与 scene-level；减少 duplicated geometry，输出更 physically plausible | 需要 complete point clouds 监督，尽管可由 meshes 或 depth maps 获得；具体输出分辨率是否任意、mesh extraction 能力、速度对比细节，材料不足，无法确定 |

## Key Differences

- **研究问题不同**：Surflo 的核心问题是“如何从 sparse / variable unposed views 得到一致、可高分辨率查询的 3D surface”；NOVA3R 的核心问题是“如何从 unposed images 得到 complete / amodal 的 non-pixel-aligned 3D reconstruction”。
- **输出对象不同**：Surflo 输出 oriented surface points，并强调可转为 clean mesh；NOVA3R 输出 complete point cloud，材料中没有明确说明其 mesh 化流程。
- **全局表示的作用不同**：Surflo 将多视角压缩到固定大小 latent $z \in \mathbb{R}^{K \times D}$，重点是从同一个 latent 任意采样 surface points；NOVA3R 用 scene tokens 连接图像 encoder 与 3D point latent decoder，重点是学习完整场景先验。
- **生成机制不同**：两者都使用 flow matching，但 Surflo 是对单个 query point $x \in \mathbb{R}^3 \times \mathbb{S}^2$ 预测 velocity 并通过 ODE 积分；NOVA3R 是在 3D autoencoder / latent decoder 框架中用 flow-matching loss 处理 unordered point sets 的 matching ambiguity。
- **一致性策略不同**：Surflo 明确指出 independent per-point decoding 会导致局部不一致，因此在推理阶段加入 rendering-based guidance；NOVA3R 则通过 non-pixel-aligned global representation 和 complete point-cloud latent prior 来减少重复结构，材料中未说明类似推理时 guidance。
- **完整性 vs 表面质量侧重不同**：NOVA3R 明确强调 amodal、visible + occluded completion；Surflo 主要强调可见输入约束下的一致表面、任意点数和 mesh 质量，是否系统性补全不可见区域，材料不足，无法确定。

## Complementarity

两篇论文可以看作对同一趋势的两种推进：都从 per-pixel / per-view reconstruction 转向 global scene representation，但优化目标不同。NOVA3R 更像是在问：**全局 latent 能否学习场景完整性与物理合理性？** Surflo 更像是在问：**全局 latent 能否被连续、高分辨率、表面一致地查询出来？**

因此它们互补：NOVA3R 的 amodal scene prior 可能对不可见区域补全更强；Surflo 的 arbitrary-resolution surface decoding 和 guidance 可能对高质量 surface / mesh extraction 更直接。若应用需要完整 point cloud 和遮挡补全，NOVA3R 更贴近；若应用需要 clean surface、mesh、可调输出密度和快速 feed-forward 表面重建，Surflo 更贴近。

## Reading / Usage Suggestions

- 先读 NOVA3R，把握 non-pixel-aligned reconstruction 为什么能缓解 visible-only 和 duplicated geometry 问题。
- 再读 Surflo，重点看它如何把 global state 进一步变成可任意分辨率查询的 oriented surface。
- 对比两者的 VGGT 使用方式：二者都借助 VGGT 的 multi-view geometry features，但 Surflo 偏向压缩到固定 latent 后做 surface flow decoding，NOVA3R 偏向 scene tokens 对齐到 3D autoencoder latent space。
- 如果关注 amodal completion，优先分析 NOVA3R 的 Stage 1 point autoencoder 和 complete point-cloud supervision。
- 如果关注 mesh / surface extraction，优先分析 Surflo 的 $x \in \mathbb{R}^3 \times \mathbb{S}^2$ flow matching、ODE integration 和 rendering guidance。
- 联合阅读时，可把 NOVA3R 视为“complete global 3D prior”的路线，把 Surflo 视为“consistent arbitrary-resolution surface readout”的路线。
