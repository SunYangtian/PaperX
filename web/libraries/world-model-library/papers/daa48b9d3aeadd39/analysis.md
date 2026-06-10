# URoPE: Universal Relative Position Embedding across Geometric Spaces

## Structured Analysis

### Motivation

- Transformer 在多视角视觉、2D/3D 感知、深度估计等任务中需要建模来自不同视角、坐标系或几何模态的 token 之间的空间关系；但标准相对位置编码通常假设 token 位于同一几何空间，例如 1D 序列或规则 2D/3D 网格，难以表达跨相机视角的几何对应（Abstract, p.1；Fig. 1, p.2）。
- RoPE 通过对 query/key 施加旋转实现相对位置偏置，已成为重要的 relative position embedding；但标准 2D RoPE 只在同一图像平面内工作。跨视角时，两个像素在各自 2D 网格中可能相距很远，却对应相近的 3D 内容，因此直接用图像坐标差并不合理（Section 1, p.2）。
- 既有多视角位置编码通常存在局限：Plücker ray 是绝对编码；relative ray 依赖全局坐标；GTA/PRoPE 等将相机几何和图像内位置分开处理，缺少 patch 级跨视角交互；RayRoPE 需要学习深度模块。论文的目标是把相对位置编码推广到 cross-view 与 cross-dimensional geometric spaces，同时保持简单、高效、无参数（Table 1, p.4）。

### Problem Setting

- 输入 token 可以来自不同相机图像，也可以来自 2D 图像特征与 3D query/point；任务包括 2D→2D 跨视角注意力、2D→3D 跨维度注意力，以及时间/多帧多视角场景（Abstract, p.1；Section 3, p.5）。
- 核心问题被表述为：一个 key token 所代表的 3D 内容，在 query token 所在图像中会出现在哪里？若能把 key 的几何位置转换到 query 图像平面，就能继续使用标准 2D RoPE 建模相对位置（Section 1, p.2-p.3）。
- 该问题存在深度歧义：源图像中的一个像素对应一条 3D ray，在另一视角中投影为 epipolar line，而不是唯一像素。URoPE 需要在不知道真实深度、且不引入每层深度预测的前提下表达这种多深度可能性（Section 3.2, p.6）。

### Core Idea

- URoPE 的关键思想是用显式 projective geometry 把跨视角位置关系统一到 query image plane：对 key 图像 patch 的相机射线在多个固定 depth anchors 上采样 3D 点，再投影到 query 相机，得到一组深度条件化的 2D 坐标，最后在 query 像素坐标与这些投影坐标之间应用标准 2D RoPE（Section 1, p.3；Fig. 2, p.5）。
- 深度歧义通过 depth-anchored multi-head attention 处理：不同 attention heads 或 head groups 对应不同固定深度假设，每个 head 只编码一个 depth anchor；多头联合覆盖近场到远场的 epipolar correspondence（Section 1, p.3；Section 3.3, p.6-p.7）。
- 当 source view 与 query view 相同，投影退化为恒等映射，URoPE 自然等价于标准 2D RoPE；因此它不是替代同视角 RoPE 的特殊机制，而是对 RoPE 的跨几何空间推广（Section 3.2, p.6；Fig. 2, p.5）。

### Method

- **Ray 表示与 lifting**：对相机 view \(i\) 中像素 \((u,v)\)，由内参 \(K_i\)、外参 \([R_i,t_i]\) 得到世界坐标下的 camera ray：相机中心 \(o_i=-R_i^Tt_i\)，方向 \(r_i(u,v)=R_i^TK_i^{-1}[u,v,1]^T\)。然后对固定深度集合 \(D=\{d^h\}\)，构造 lifted 3D points：\(p_i^h(u,v)=o_i+d^h r_i(u,v)\)（Section 3.1-3.2, p.5-p.6）。
- **跨视角 projection**：将源视角 lifted point \(p_i^h(u,v)\) 用 query 相机 \(j\) 的外参与内参投影为 \((u^h_{i\rightarrow j}, v^h_{i\rightarrow j})\)。这些点位于由源像素诱导的 epipolar line 上，并显式包含相机内参信息（Section 3.2, p.6）。
- **RoPE 集成**：对 head \(h\)，query 使用自身坐标 \((u',v')\)，key 使用投影坐标 \((u^h_{i\rightarrow j},v^h_{i\rightarrow j})\)。通道按水平/垂直轴拆分，对 \(u\) 和 \(v\) 分别施加 1D RoPE，再组合为 2D RoPE；Q/K/V 乘法形式不变，因此兼容 FlashAttention 和已有 RoPE-optimized kernels（Section 3.3, p.7）。
- **多视角 batch 重排**：当一个序列中包含多个 query views，URoPE 将 view 维从 sequence 移到 batch，使每次 attention call 中的 query 属于单一视角；keys/values 在 batch 维重复。时间复杂度仍为 \(O(BHL^2C)\)，不增加渐近计算量，主要额外开销是当前层临时重复 K/V（Section 3.3, p.7）。
- **2D–3D 扩展**：对于 3D token \((x,y,z)\)，论文称可跳过 image-plane projection，直接在 3D token 与 lifted image points 之间度量相对位置，以支持图像特征和 3D queries 的 cross-attention；材料未给出该部分更完整公式细节（Section 3.2, p.6）。

### Key Contributions

- 提出 URoPE：一种对 RoPE 的 universal extension，使 relative position embedding 可用于 cross-view 与 cross-dimensional geometric reasoning，而不局限于同一 1D/2D/3D 网格空间（Abstract, p.1；Fig. 1, p.2）。
- 将跨视角相对位置建模转化为“key patch 沿 ray 多深度 lifting → 投影到 query image plane → 标准 2D RoPE”的流程，使 inter-camera geometry 与 intra-image spatial position 在同一机制中交互，而不是通道分块式解耦（Section 3, p.5-p.7）。
- 方法具有若干工程与几何属性：parameter-free、intrinsics-aware、对全局坐标系 SE(3) 变换不敏感/不依赖全局坐标选择、patch-level geometry、兼容高效 attention kernel；与 Plücker、Relative Ray、GTA、PRoPE、RayRoPE 的对比集中体现这些差异（Table 1, p.4）。
- 固定 depth anchors 避免了每层学习深度预测的优化不稳定和错误深度风险；head-wise depth assignment 允许多头表达不同 epipolar depth hypotheses（Section 3.3, p.6-p.7；Table 8, p.14）。

### Experiments / Evidence

- **Novel View Synthesis**：在 LVSM 框架中替换位置编码，URoPE 在 Objaverse 与 RealEstate10k 上均优于 Plücker Ray、6D RoPE、P-RoPE、RayRoPE。RealEstate10k 上 PSNR/SSIM/LPIPS 为 26.02/0.827/0.080，优于 P-RoPE 的 25.28/0.806/0.092；Objaverse 上为 25.09/0.900/0.165，也为最佳或并列最佳趋势（Table 2, p.9）。
- **3D detection/tracking**：在 nuScenes 上，PETR + URoPE 将单帧多视角 NDS/mAP/AMOTA 从 34.9/30.9/0.222 提升到 37.3/32.2/0.255；StreamPETR + URoPE 将多帧多视角 NDS/mAP/AMOTA 从 47.6/37.5/0.335 提升到 50.6/41.1/0.380，支持其 2D–3D 与时序多视角适用性（Table 3, p.10）。
- **深度估计与分析**：在 UniMatch stereo depth 上，URoPE 在 RGBD、Scenes11、SUN3D 上相对 baseline 和 P-RoPE 多数指标进一步改善，例如 SUN3D Abs Rel/Sq Rel/RMSE/RMSE log 为 0.112/0.063/0.329/0.148，优于 P-RoPE 的 0.117/0.075/0.343/0.152（Table 4, p.11）。缩放实验显示 50× compute 下 RealEstate10k PSNR 从 Plücker 的 28.66 提升到 URoPE 的 29.24；鲁棒性分析显示对不同 focal length 和更多 context views 有较稳定表现（Table 5, p.11；Fig. 5, p.11）。

### Conclusions, Limitations, and Relation to Other Work

- 论文结论是：URoPE 通过固定深度锚点 lifting 与 query 平面投影，把跨视角/跨维度几何关系转化为标准 RoPE 可处理的相对坐标关系；在 novel view synthesis、3D object detection/tracking、stereo depth estimation 中作为 plug-in 均带来稳定收益，说明其具有较强通用性（Section 5, p.15）。
- 与 Plücker ray 等绝对 ray encoding 相比，URoPE 保留 RoPE 的相对位置偏置属性；与 Relative Ray 相比，不依赖全局坐标系；与 GTA/PRoPE 相比，它在 patch 级通过投影坐标统一 inter-camera 与 intra-image geometry；与 RayRoPE 相比，它不引入 learned depth module，使用固定 anchors 提供显式多深度覆盖（Table 1, p.4；Section 2, p.4）。
- 主要限制是需要已知相机参数，因此对未标定或相机参数不可靠场景的适用性仍未解决；作者将扩展到 uncalibrated settings 作为未来方向。材料中未提供对相机参数噪声敏感性的系统实验，无法确定其在标定误差下的稳定性（Section 5, p.15）。
