# $μ_0$: A Scalable 3D Interaction-Trace World Model

- Imported from: https://arxiv.org/abs/2606.13769
- PDF URL: https://arxiv.org/pdf/2606.13769.pdf
- Hash: 300b83040672967b
- Slug: 300b83040672967b
- Status: imported

## Structured Analysis

### Motivation

- 机器人学习面临“数据悖论”：互联网和人类视频提供大量物理交互观察，但真正适合控制的 action-labeled robot demonstrations 稀缺、昂贵，并且强绑定具体硬件形态；这限制了跨 embodiment 的可扩展学习（Introduction, p.1-2）。
- 现有 world model 的预测目标存在两端问题：pixel-space video model 可从大规模视频学习，但大量容量消耗在背景和外观重建上，且不一定保留操控所需的 metric geometry、contact structure 和 occlusion pattern；VLA 直接预测动作，则依赖 embodiment-specific action labels（Introduction, p.2）。
- 论文主张位于二者之间的表示：预测物体部件、工具、手、接触区域等 semantic interaction points 的 3D traces。它们比像素更紧凑，比动作更少依赖机器人形态，能描述“什么需要移动”和“如何移动”（Introduction, p.2）。
- 既有 motion-centric 方法仍有三类不足：容易漏掉小但关键的区域，如 tool tip 和 contact patch；2D 或局部坐标会混淆物体运动和相机运动；长演示通常只配 episode-level caption，无法绑定局部运动意图（Introduction, p.2）。

### Problem Setting

- 目标是训练一个 action-free、可复用的 trace-space world model：给定当前视觉观测、语言指令、查询关键点及可选历史轨迹，预测这些 interaction-centric keypoints 的未来 3D 轨迹，而不是生成像素或机器人动作（Section 2.4, p.4）。
- TraceExtract 将视频转换为监督元组 $D_{TE}=\{(I_t,l_c,Q_t,T^{ref}_{t-h:t+H})\}$，其中 $I_t$ 是观测，$l_c$ 是事件或合并任务 caption，$Q_t=\{q^t_n\}_{n=1}^N$ 是查询关键点集合，$T^{ref}_{t-h:t+H}$ 包含 reference camera 下的过去和未来 3D traces（Section 2.4, p.4）。
- 模型学习的映射可概括为 $\mu_0:(I_t,l_c,Q_t,T^{ref}_{t-h:t})\mapsto \hat{T}^{ref}_{t:t+H}$。这一定义强调 query-conditioned dynamics：输出只针对被选中的交互点，而非整幅图像或固定动作空间（Section 2.4, p.4）。
- 下游控制阶段中，预训练好的 $\mu_0$ 被冻结，只训练 action expert，使 trace 表示作为 embodiment-agnostic motion prior 被不同机器人接口复用（Fig. 1, p.1; Section 3.4, p.6）。

### Core Idea

- 核心思想是把“可规模化的视频预训练”和“可执行的机器人控制”之间的中间层设为 3D interaction traces：这些 traces 保留运动、几何和目标相关实体，同时避免像素级重建和动作标签的成本（Introduction, p.2）。
- TraceExtract 是数据引擎，回答三个问题：what to move，通过 DINOv2 entity clusters 选择语义关键点；where to move，通过 globally aligned 3D tracking 构建相机运动解耦的轨迹；how to move，通过 motion-centric chunking 和 hierarchical captioning 绑定事件级语言（Fig. 1, p.1; Fig. 2, p.3）。
- $\mu_0$ 则是模型端实现：在 pretrained VLM backbone 上接入 permutation-equivariant Trace Expert，将每个查询点表示为 B-spline control points，并用 semantic flow matching 生成平滑、多模态的未来轨迹（Fig. 3, p.5; Section 3, p.4-6）。
- 对下游策略而言，完整 trace rollout 不是必须的；action expert 可以读取 $\mu_0$ 的 partial-denoising features，将其作为中间 motion tokens 来预测 continuous action chunks（Section 3.4, p.6-7）。

### Method

- TraceExtract 首先做 semantic keypoint sampling：抽取 DINOv2 patch features，聚类为 entity-level groups，传播实体身份，并为每个实体分配固定关键点预算，在高可见帧中选择空间多样的点；movement filter 用于降低静态背景轨迹对监督的干扰（Section 2.1, p.3）。
- 3D trace construction 采用 global-local reconstruction：用 sparse anchor frames 建立共享全局坐标系，再重建 dense local chunks 并对齐回全局系；关键点在公共 3D 空间中跟踪，并跨 chunk 传播最后有效 world-space 位置。随后轨迹被重投影到每个 chunk 的 reference camera，得到 $T^{ref,n}_{t:t+H}=[x_{n,i},y_{n,i},z_{n,i}]_{i=t}^{t+H}$，以同时去除相机运动并保持图像对齐（Section 2.2, p.4）。
- Event-centric captioning 用 trace acceleration 定义语言单元：平滑每帧轨迹加速度 $\tilde{a}_t$，寻找峰值 $p_i$ 作为动作 anchor，再在相邻峰之间的低加速度 valley 处切分，$b_i=\arg\min_{t\in[p_i,p_{i+1}]}\tilde{a}_t$。VLM 为每个 chunk 基于起点、中点、终点帧生成 caption，LLM 再合并相邻 caption 形成层级描述（Section 2.3, p.4）。
- $\mu_0$ 使用 SmolVLM2-2.2B prefix 编码 RGB 和语言，depth 可经单独可训练 patch stem 后共享更深 SigLIP 层；Trace Expert cross-attend 到 VLM KV cache，同时保留独立 motion stream，以分离语义记忆和运动计算（Section 3.1, p.5）。
- Trace Expert 将查询点视为无序可交换集合，保证 permutation equivariance；每个查询的未来轨迹减去当前 3D anchor 后，用 cubic B-spline control points 表示。训练目标为条件 flow matching，并加入 validity prediction 与 semantic rigidity，整体损失为 $L=L_{flow}+\lambda_{done}L_{done}+\lambda_{rig}L_{rig}$（Section 3.2-3.3, p.6）。

### Key Contributions

- 提出 TraceExtract：从异构人类和机器人操控视频中自动抽取 event-captioned 3D trace supervision，结合语义关键点选择、全局对齐 3D lifting/tracking 和运动事件语言标注，论文称其相对 prior 3D trace datasets 将 trace curation 扩展约 $8\times$（Introduction, p.2）。
- 提出 $\mu_0$：一个 query-conditioned 3D trace-space world model，结合 VLM backbone、permutation-equivariant Trace Expert、B-spline trace targets 和 semantic flow-matching training，用紧凑轨迹替代 dense pixels 或 embodiment-specific actions（Introduction, p.2; Fig. 3, p.5）。
- 提出 trace-conditioned action adaptation：冻结视频预训练的 $\mu_0$，只训练 action expert，使 action-free video pretraining 能迁移到具体机器人控制，并限制动作监督只发生在目标 embodiment 的接口层（Section 3.4, p.6）。
- 相比最接近的 TraceGen，本文不依赖固定网格轨迹和 episode-level captions，并通过语义查询、全局 3D 对齐和事件级语言增强了 supervision 与模型输入的任务相关性（Introduction, p.2; Related Work, p.9-10）。

### Experiments / Evidence

- Trace prediction 上，$\mu_0$ 在 2D 中取得所有 horizon 的最佳 Top-5 ADE、FDE、DTW；在 3D 中取得所有报告 ADE、FDE、DTW 指标的最佳结果。推理延迟为 $0.29$s，快于 Track2Act 的 $0.85$s，也显著快于 API VLM 和 video/flow baselines（Table 1, p.7）。
- RoboCasa365 仿真中，$\mu_0$ + action expert 在 8 个任务上平均成功率为 $30.25\%$，高于 Diffusion Policy 的 $22.75\%$、$\pi_0$ 的 $25.25\%$ 和 TraceGen + action expert 的 $23\%$，但低于 $\pi_{0.5}$ 的 $42\%$；作者强调 $\pi_{0.5}$ 使用大规模 action-labeled pretraining，比较并非数据匹配（Table 2, p.8）。
- 真实 UR3 实验中，$\mu_0$ + action expert 在 Pick & Place、Pour、Unfold 三类任务上平均成功率为 $91.7\%$，高于 VLM + action expert 的 $73.3\%$、$\pi_0$ 的 $71.7\%$、$\pi_{0.5}$ 的 $80\%$ 和 TraceGen + action expert 的 $81.7\%$；其中与去除 trace expert 的 VLM baseline 相差 $18.4$ 个百分点，支持 trace features 的额外运动指导价值（Fig. 6, p.9）。
- Ablation 和 scaling 只在正文中概述：更大模型与更多预训练数据提升 trace prediction，trace representation 在较小 action head 下更能弥补策略容量不足；B-spline、DINOv2 features、rigidity loss、depth input 和 historical traces 的详细消融在附录，材料中未给出具体表格数值（p.9）。

### Conclusions, Limitations, and Relation to Other Work

- 论文结论是：3D interaction traces 可作为 scalable robot world modeling 的紧凑、可迁移、可执行中间表示。它们相比像素模型更关注几何和交互运动，相比动作模型更少受机器人形态和动作标签约束（Conclusion, p.10）。
- 与 pixel-space world models、visual motion priors、2D tracks、3D flow 和 object trajectory 方法相比，$\mu_0$ 的差异在于显式预测 query-selected interaction points 的 3D trajectories，避免固定网格浪费预算，也保留 metric depth；与 TraceGen 最接近，但 TraceGen 依赖 fixed-grid traces 和 inference-time depth，而本文强调语义查询、事件 caption 和更强的 action transfer（Related Work, p.9-10）。
- 主要限制来自 trace 构造链路：semantic clustering、3D reconstruction、tracking 或 captioning 的错误都会引入 noisy supervision。换言之，$\mu_0$ 的质量部分受前置感知系统上限约束（Limitations, p.10）。
- 表示能力上，trace 捕捉几何和运动，但没有显式建模 forces、tactile feedback 或 contact modes；这可能限制精细操控、强接触任务或需要触觉反馈的场景（Limitations, p.10）。
- 实验覆盖仍有限：action expert 评估集中在 tabletop manipulation、有限 embodiment 和有限任务族；移动操作臂、灵巧手、更长时序任务上的泛化仍是未来工作，材料不足，无法确定其在这些设置下的表现（Limitations, p.10）。
