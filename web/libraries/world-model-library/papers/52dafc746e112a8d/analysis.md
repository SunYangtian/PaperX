# AgniNav: Configuration-Driven Cross-Embodiment Local Planning for Robot Navigation

- Imported from: https://arxiv.org/abs/2606.10903
- PDF URL: https://arxiv.org/pdf/2606.10903.pdf
- Hash: 52dafc746e112a8d
- Slug: 52dafc746e112a8d
- Status: imported

## Structured Analysis

### Motivation

- 单目局部导航适合轻量、低成本机器人，但现有 vision-based policy 往往把感知、动作策略与特定机器人本体、相机高度、footprint 绑定；从轮式底盘迁移到四足或人形平台时，容易因尺度歧义、相机外参变化和机体尺寸变化产生 domain shift，需要重训练或依赖主动深度传感器（Introduction, p.1）。
- 传统局部规划器如 DWA、TEB 依赖显式几何边界，1D metric laserscan 是常用接口，既紧凑又能表达安全距离；但物理 LiDAR 成本高、结构突出。单目相机虽便宜，但若直接端到端输出控制，难以稳定提供可验证的碰撞边界（Introduction, p.1）。
- AgniNav 的核心问题是：如何让单目系统产生局部规划器所需的 1D metric boundary，同时通过可测量物理参数适配不同机器人，而不是为每种 embodiment 重新采集和训练（Introduction, p.1）。

### Problem Setting

- 论文将导航拆成两个串联任务：cross-modal perception，即从 RGB 图像预测标准化 2D/1D pseudo-laserscan；以及 dimension-configurable local planning，即根据机器人 footprint 和运动学约束做局部避障（Section III, p.2）。
- 每个机器人由 collision-relevant embodiment configuration 表示：
  $$
  c_e=[H_{\max}, L_1, L_2, W/2]
  $$
  其中 $H_{\max}$ 是需要被感知保护的刚性碰撞包络上界，$L_1,L_2$ 是前后安全长度，$W/2$ 是半宽。该配置不是完整形态学描述，不编码质量、腿长、关节限制、步态、柔顺性或全身动力学，只是局部导航的 2.5D collision envelope proxy（Section III-A, p.3）。
- 感知与规划共享同一配置接口：
  $$
  \hat S_t=f_\theta(I_t,H_{\max}), \quad a_t=\pi(R_t,L_1,L_2,W/2,\kappa_e)
  $$
  其中 $H_{\max}$ 控制哪些垂直障碍对扫描预测是碰撞相关的，$(L_1,L_2,W/2)$ 控制规划器做 footprint-aware collision checking，$\kappa_e$ 表示速度、角速度和加速度限制（Section III-A, p.3）。

### Core Idea

- AgniNav 的关键抽象是把跨本体迁移从“学习完整机器人形态”降维为“指定可测量碰撞包络”。感知侧根据 $H_{\max}$ 预测 collision-relevant pseudo-laserscan，规划侧根据水平 footprint 参数检查碰撞，从而实现 zero-retraining deployment（Fig. 1, p.2）。
- 训练时不需要为每个目标机器人重新采集相同场景。作者用一次校准 RGB-D 采集，通过深度、相机内参、相机到地面外参和 traversability mask，为同一 RGB 图像生成多个不同 $H_{\max}$ 下的 scan pseudo-label，使 $H_{\max}$ 成为有监督条件变量，而非元数据（Section IV-A, p.4）。
- 与传统 center-row depth-to-scan 不同，AgniNav 用 height-conditioned column-minimum：在每一图像列的整个垂直范围内寻找 $0 \le h \le H_{\max}$ 内最近的非地面障碍。低矮机器人可忽略高于自身包络的悬垂物，高机器人则将其视作障碍（Fig. 2, p.4；Section IV-B, p.4）。

### Method

- **I2S 感知模型**：image2scan 接收 RGB 图像和 $H_{\max}$，直接输出固定宽度 pseudo-scan：
  $$
  \hat S_t=f_\theta(I_t,H_{\max})=\{(\hat x_i,\hat z_i,\hat v_i)\}_{i=1}^{W_s}
  $$
  其中 $\hat x_i,\hat z_i$ 是笛卡尔扫描点，$\hat v_i$ 是 validity confidence。之后按置信度和量程过滤，再离散化成 planner 使用的 polar range array $R_t$（Section IV-A, p.3）。
- **Scan label 生成**：对列 $u$，保留深度有效、非地面、且高度在碰撞包络内的点：
  $$
  Z_u=\{I_d(v,u)\mid I_s(v,u)=0 \wedge I_d(v,u)\in[r_{\min},r_{\max}] \wedge 0\le h(v,I_d(v,u))\le H_{\max}\}
  $$
  若 $Z_u\neq \emptyset$，取 $z_u=\min(Z_u)$。水平坐标由针孔模型计算：
  $$
  x_u=\frac{(u-c_x)z_u}{f_x}
  $$
  同时使用 visibility-aware tri-state target，避免把深度缺失误标为 free space（Section IV-B, pp.4-5）。
- **网络结构**：编码器采用 ViT backbone + Simple Depth Transformer（SDT），在 token space 融合多层特征，避免重型 spatial pyramid。ScanFormer decoder 使用 learnable scan queries 和 cross-attention，从图像特征中解码 $W_s=640$ 个 scan query，并将 $H_{\max}$ 经 MLP 投影后拼接到 query 中，实现高度条件化预测（Section IV-C, pp.5-6）。
- **规划器**：下游使用 DRL-DCLP，输入 64 个极坐标 scan bin、相对目标、当前速度、运动学限制以及 $(L_1,L_2,W/2)$。训练基于 SAC，点云式 scan embedding 中显式包含 footprint 参数，使同一策略可按尺寸配置检查碰撞（Section V-A, p.6）。

### Key Contributions

- 提出 configuration-driven cross-embodiment local planning 框架 AgniNav，把跨轮式、四足、人形平台的局部避障统一到 $c_e=[H_{\max},L_1,L_2,W/2]$ 这一 collision-envelope interface；论文明确其范围是局部 obstacle avoidance，而非完整 morphology generalization（Introduction, p.2；Conclusion, p.11）。
- 提出 height-conditioned column-minimum pseudo-scan supervision，使同一 RGB-D 帧能生成不同 $H_{\max}$ 下的 collision-relevant scan label，从而学习“安全包络边界”而不是固定相机高度的 depth-to-scan 转换（Section IV-A/B, pp.4-5）。
- 提出轻量 I2S 架构：SDT token-space fusion + ScanFormer decoder，可在不生成中间 dense depth map 的情况下直接预测 1D safety contour，兼顾几何精度和 Jetson Orin 上的实时性（Section IV-C, pp.5-6；Table V, p.9）。

### Experiments / Evidence

- **跨平台实机结果**：在 DMR1 Turtlebot2、DMR4 Unitree Go2、DMR5 K1 humanoid 上，AgniNav 分别达到 39/40、18/20、18/20 成功，碰撞数分别为 0、1、2；相比 E2E DRL、ORB-SLAM3+TEB、DPT+CR、DAv2+FT+ColMin 均更稳定。DMR2/DMR3 的长/宽 footprint 插值也保持 38/40 成功（Table III, p.8）。
- **强基线对比**：DAv2+FT+ColMin 使用同样深度监督数据和同样 ColMin 投影规则，是“depth-then-projection”强控制组；AgniNav 在 DMR4 上为 18/20 vs. 14/20，在 DMR5 上为 18/20 vs. 13/20，说明收益不只是来自 fine-tuned monocular depth，而来自端到端 scan boundary 学习和配置条件化（Table III, p.8）。
- **效率与误差**：AgniNav 在 Jetson Orin NX 上 latency 32 ms、VRAM 1.6 GB，优于 DAv2+FT+ColMin 的 58 ms、2.8 GB；DMR4/DMR5 上 scan MAE 分别为 0.132 m/0.148 m，并降低 overhanging hazard false negative rate（Table IV, p.9；Table V, p.9）。
- **消融证据**：Column-minimum 相比 center-row 将规划成功从 26/40 提升到 38/40；progressive curriculum 相比 scan-only 从 30/40 提升到 38/40；SDT 相比 DPT 只增加 0.003 m MAE，却把 latency 从 58 ms 降到 32 ms（Table VI, p.10）。

### Conclusions, Limitations, and Relation to Other Work

- AgniNav 的结论是：将感知与规划统一到 collision-relevant configuration，可把跨 embodiment 部署从网络重训练转化为参数指定。其适用对象是安全包络可由 $[H_{\max},L_1,L_2,W/2]$ 表达的局部避障任务，而非包含步态、动力学和全身接触的完整机器人泛化（Conclusion, p.11）。
- 与 X-Nav 等通过大规模多机器人数据学习共享 latent representation 的工作不同，AgniNav 的特点是接口可解释、可测量，预测 scan 可按指定 $c_e$ 独立验证；与 SLAM/深度重建管线相比，它避免 dense 3D mapping 和 depth-then-projection 的计算负担，更适合边缘部署（Section V-B/C, pp.8-9）。
- 主要局限包括反光/透明表面、低于 scan 分辨率的细小障碍、快速运动导致的 motion blur、以及语义分割边界错误；作者建议未来加入 temporal consistency、从 URDF 自动估计 $c_e$、扩展到更多平台和户外环境，并融合 infrared/ToF 以处理反光场景（Section VI-B, p.10；Conclusion, p.11）。
