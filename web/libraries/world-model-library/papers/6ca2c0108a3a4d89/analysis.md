# ChordEdit: One-Step Low-Energy Transport for Image Editing

- Imported from: https://arxiv.org/pdf/2602.19083
- PDF URL: https://arxiv.org/pdf/2602.19083.pdf
- Hash: 6ca2c0108a3a4d89
- Slug: 6ca2c0108a3a4d89
- Status: imported

## Structured Analysis

### Motivation

- one-step T2I models（如 SD-Turbo、SwiftBrush-v2、InstaFlow）通过蒸馏实现极快生成，理论上适合实时交互式 image editing；但把已有 training-free / inversion-free 编辑方法直接压缩到单步时，会出现严重物体形变、背景破碎、非编辑区域一致性下降等问题（Section 1, p.2；Fig. 3, p.2）。
- 论文认为失败根源不在“单步模型不能编辑”，而在 naive simple drift：直接取 target prompt 与 source prompt 条件漂移之差，会得到 high-energy、erratic、high-variance 的控制场；单个大步长积分会放大误差（Section 1, p.2；Fig. 4, p.4）。
- 目标是在不训练专用网络、不做 inversion、且模型无关的条件下，让 one-step / fast generative models 支持高保真文本引导编辑，同时保留非编辑区域（Abstract, p.1）。

### Problem Setting

- 论文把预训练 T2I 模型表示为条件 probability flow：图像状态 \(x_t\) 随时间 \(t\in[0,1]\) 按 drift / velocity \(v(x_t,t,c)\) 演化，文本条件为 \(c\)。给定源 prompt \(c_{src}\)、目标 prompt \(c_{tar}\) 和源图像，编辑可视为在两个条件分布之间 transport（Section 3.1, p.3）。
- 常见 training-free 编辑会使用 instantaneous residual \(\Delta v=v(\cdot,c_{tar})-v(\cdot,c_{src})\)。在多步扩散中，多次小步积分可平均不稳定性；在 one-step distilled model 中，这一残差场过于剧烈，无法直接用一个大步长走完（Section 3.1, p.3；Fig. 4, p.4）。
- 实际模型不一定直接输出 drift，可能输出 noise prediction、velocity、score、\(x_0\) 等。论文定义 observable output \(Q(z,t,c)\)，并通过时间相关线性映射 \(B_t\) 转到统一比较空间，从而支持不同参数化模型；若模型直接输出 velocity，则 \(B_t=I\)（Section 3.2–3.3, p.3）。

### Core Idea

- ChordEdit 将编辑重新解释为 dynamic optimal transport：寻找从 source distribution 到 target distribution 的低能量 transport field，而不是对两个大幅度轨迹做瞬时向量相减（Section 4.1, p.3）。
- 核心是 Chord Control Field：对可观测残差场 \(R(x_\tau,t)\) 做局部时间加权平均，用一个低能量、低方差、平滑的“弦”替代 naive drift difference。该场更稳定，因此可用单个大 integration step 完成编辑（Section 4.2, p.4）。
- 直观上，multi-step simple drift 依靠多次迭代获得稳定；one-step simple drift 会因高能量路径偏离目标；ChordEdit 则把局部轨迹平滑为更接近直达目标的低能量控制方向（Fig. 4, p.4；Fig. 5, p.5）。

### Method

- 首先定义 observable proxy field：在源图像锚点 \(x_\tau\) 附近采样 synthetic noisy proxy \(z\sim K_t(\cdot|x_\tau)\)，计算源/目标条件输出差 \(\Delta Q\)，再经 \(B_t\) 映射并取期望，得到 \(R(x_\tau,t)=\mathbb{E}[B_t\Delta Q(z,t)]\)。实践中用 shared-noise Monte Carlo；默认甚至只用一个 noise sample（Section 3.2, p.3；Section 4.4, p.5）。
- OT 视角下，理想场 \(u_t\) 最小化 Benamou–Brenier kinetic energy，并满足连续性方程；但 \(u_t\) 不可直接访问，论文把 \(R\) 视为 \(u_t\) 加零均值噪声的观测。naive 方法直接令控制场为 \(R\)，因此继承高能量噪声（Section 4.1, p.3）。
- Chord Control Field 来自一个局部二次优化：在窗口 \([t-\delta,t]\) 内，估计局部常量控制 \(u\)，同时接近前一估计和当前观测。经一阶因果近似得到实用公式  
  \[
  \hat u_t(x_\tau)=\frac{tR(x_\tau,t-\delta)+\delta R(x_\tau,t)}{t+\delta}.
  \]  
  这等价于 one-sided temporal kernel smoothing；理论上可降低 \(L_2\) 能量、收缩场幅值及时间/空间梯度上界，从而改善 Euler 单步误差和稳定裕度（Section 4.2, p.4）。
- 算法上，输入源图像与源/目标 prompt，在 latent space 查询 \(R(x,t-\delta)\) 和 \(R(x,t)\)，构造 \(\hat u\)，执行 \(x_{pred}=x_{in}+\lambda\hat u\)。可选 proximal refinement 再用目标 prompt 做一次 forward pass，以增强目标语义；transport 本身为 1-NFE，带 refinement 为 2-NFE（Algorithm 1, p.5；Section 4.3–4.4, p.4–5）。

### Key Contributions

- 提出 ChordEdit：model-agnostic、training-free、inversion-free 的 one-step image editing 框架，面向 SD-Turbo、SwiftBrush-v2、InstaFlow 等快速 T2I 模型（Abstract, p.1；Section 4.4, p.5）。
- 从 dynamic OT 角度解释单步编辑，并提出低能量 Chord Control Field，替代高能量 naive drift difference；论文给出稳定性论证，包括能量收缩、梯度/时间导数上界收缩、Euler 误差界改善等（Section 4.1–4.2, p.3–4）。
- 方法将“结构保持 transport”和“语义增强 refinement”解耦：无 prox 时更强调一致性，有 prox 时提升目标语义；这使其在实时效率和编辑质量之间取得较好平衡（Section 4.3, p.4；Table 2, p.8）。

### Experiments / Evidence

- PIE-bench 上，ChordEdit（SD-Turbo）在 one-step 类别中以 0.38s runtime、6988 MiB VRAM 达到 PSNR 22.20、CLIP-Edited 22.96；w/o prox 版本仅 1-NFE、0.20s，PSNR 23.89，验证 transport field 本身的背景保持能力。相较 FlowEdit 约快 19×，相较 Direct Inversion 超过 208×；同模型/同类别下显著少于 SwiftEdit 的显存占用（Table 1, p.6；Section 5.2, p.5）。
- 与 naive baseline 的消融显示，当步数趋近 1 时，naive field 能量上升、PSNR 崩塌；ChordEdit 在 \(\delta=0.15\) 时能量保持较低，PSNR 稳定，并在 LPIPS–CLIP trade-off 上 Pareto dominate naive。可视化中 naive 常产生伪影和背景破坏，而 ChordEdit 保留身份与非编辑区域（Fig. 8–9, p.7）。
- 模型无关性和低方差得到支持：在 InstaFlow、SwiftBrush-v2、SD-Turbo 上，ChordEdit 均优于 naive；例如 SD-Turbo 从 PSNR 21.38 / CLIP-Edited 21.96 提升到 22.20 / 22.96。噪声样本数 \(n=1\) 到 \(4\) 的 Pareto fronts 几乎重合，且单噪声 20 seeds 下 CLIP CoV 0.20%、PSNR CoV 0.07%，说明额外 Monte Carlo 收益很小（Table 3, p.8；Fig. 11, p.8）。

### Conclusions, Limitations, and Relation to Other Work

- 结论：ChordEdit 通过低能量 temporal smoothing 控制场解决 one-step editing 的核心不稳定性，在无需训练、无需 inversion、无需保护 mask 的条件下实现实时、高保真、背景一致的文本引导编辑（Section 7, p.8）。
- 与相关工作相比，多步/少步 diffusion editors 往往依赖 inversion、多次迭代或特定架构，实时性较差；SwiftEdit 等 one-step 方法需要训练专用 inversion network，牺牲 model-agnostic flexibility。ChordEdit 位于更困难的 training-free、inversion-free、single-step regime，并用 OT-inspired control 替代训练式或多步平均式稳定化（Section 2, p.2–3）。
- 局限方面，正文未系统展开技术失败案例；可确定的是：默认最优配置包含 optional proximal refinement，因此完整版本为 2-NFE 而非纯 1-NFE；参数 \(\delta,t,\lambda,t_c\) 存在稳定性与语义强度 trade-off。论文也简要承认潜在 misuse，详细社会影响讨论在 Appendix，但材料未提供更多内容（Section 5.1, p.5；Section 7, p.8）。
