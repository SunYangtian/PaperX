# Unified Camera Positional Encoding for Controlled Video Generation

- Imported from: https://arxiv.org/pdf/2512.07237
- PDF URL: https://arxiv.org/pdf/2512.07237.pdf
- Hash: 926522b8c9c6b497
- Slug: 926522b8c9c6b497
- Status: imported

## Structured Analysis

### Motivation

- 论文关注一个基础但常被简化的问题：Transformer 已成为 3D perception、video generation、world models 等任务的通用骨干，但这些任务要真正理解视觉序列，需要知道图像是由何种 camera geometry 形成的，包括 pose、intrinsics、projection model 和 lens distortion（Section 1, p.2）。
- 现有 camera-conditioned video generation 多依赖 pinhole camera 假设，或只控制 extrinsics / 6-DoF poses；这对真实应用中的 wide-angle、fisheye、catadioptric、panoramic 等相机不够，难以覆盖自动驾驶、机器人、embodied AI 中常见的大 FoV 和非线性畸变（Section 1, p.2）。
- 论文认为关键瓶颈不只是模型容量，而是 camera positional encoding 本身：direct parameterization 缺少几何可解释性，Plücker / ray-map 等 absolute encoding 依赖任意 world frame，PRoPE / GTA 等 relative encoding 虽改进多视角一致性，但仍主要建立在 pinhole projection 上（Fig. 2, p.2；Section 3.1, p.4）。

### Problem Setting

- 任务设定为 camera-controlled text-to-video generation：输入文本 prompt 和相机控制参数，生成符合指定相机运动、镜头类型、FoV、distortion 以及可选绝对朝向的视频（Fig. 1, p.1）。
- 相机控制被拆成三类：relative camera pose 用于控制跨帧 6-DoF 运动；camera lens 用 horizontal field-of-view 和 distortion 参数 ξ 表示；absolute orientation 用 pitch、roll 对齐重力方向，论文以 Lat-Up map 表示（Fig. 1, p.1；Section 3.2, p.5）。
- 论文指出，已有 T2V camera control 方法通常把第一帧作为相对坐标系原点，因此初始视角的全局旋转不唯一，尤其 pitch 和 roll 无法被明确指定或复现；这会限制“绝对朝向”控制（Section 1, p.2）。
- 为系统评估，作者构造了约 48k clips 的合成数据集，来自 in-the-wild 360° videos，并用 Unified Camera Model 随机采样 xFoV 和 distortion ξ，覆盖 pinhole、wide-angle、fisheye 等配置；另外在 RealEstate10K 上测试分布外泛化（Section 4.1, p.6）。

### Core Idea

- 核心思想是把 camera positional encoding 从“camera-level relative encoding”推进到“ray-level relative encoding”：每个 token 不再共享同一相机矩阵，而是对应自己的 viewing ray，并在该 ray 的局部坐标系中进行几何一致的 attention 计算（Section 3.2, p.5）。
- 这种 Relative Ray Encoding 的动机是：非线性投影和镜头畸变会导致同一图像内不同位置 token 的投影几何不同；用单一 camera encoding 表示整张图会丢失 intra-camera variation，尤其不适合 wide FoV 和 distortion（Section 3.2, p.4-p.5）。
- UCPE 由两个互补部分组成：Relative Ray Encoding 负责局部 ray-space 几何与跨镜头统一表示；Absolute Orientation Encoding 通过 Lat-Up map 提供 gravity-aligned 的 pitch / roll 控制（Section 3.2, p.5）。
- 最终目标不是提出一个只适用于视频生成的 control trick，而是提出一种 camera model-agnostic representation，可把 6-DoF poses、intrinsics、lens distortions 统一注入 Transformer attention（Section 1, p.3）。

### Method

- 论文首先把任意相机抽象为 ray mapping function：给定像素坐标 \((u,v)\)，输出 camera coordinate 下的 ray origin 和 unit direction；central camera 的所有 ray origin 相同，non-central camera 也可通过像素相关 origin 表示。正文推导默认 central camera，并以 Unified Camera Model 为代表（Section 3.1, p.4）。
- Relative Ray Encoding 对每个 token 构造世界坐标中的 ray \((o_t,d_t)\)，再以 ray direction 作为局部 z-axis，用相机 downward direction 与其叉乘构造 x-axis，再得到 y-axis，形成 ray-to-world transform \(T^{wr}_t\)，其逆 \(T^{rw}_t\) 作为 attention 中的几何算子（Eq. 5-7, p.5）。
- Absolute Orientation Encoding 使用 Lat-Up map：Latitude map 由 world-space ray direction 相对水平面的 elevation angle 得到；Up map 通过将 ray 绕局部轴小角度旋转、投影回图像平面，并取归一化 pixel displacement 得到。该表示为每个 token 提供全局 up direction 与 pitch / roll 线索（Eq. 8-9, p.5）。
- 在 Transformer 注入方式上，UCPE 与 RoPE 做 hybrid encoding：一半维度用于 world-to-ray transform，另一半用于 image-space RoPE；attention 形式沿用 GTA 式的 query/key/value 几何变换，同时可把 Lat-Up feature 线性投影后加到 token 上（Eq. 10, p.6）。
- 为避免破坏预训练视频 DiT 的先验，作者没有直接替换原 self-attention，而是在 Wan Diffusion Transformer 中加入并行的 lightweight spatial attention adapter：输入 token 先压缩到原维度的 \(1/C\)，经过 UCPEAttn，再由 zero-initialized linear layer 投回，使初始化时不改变原模型行为；新增可训练参数少于 1%（Fig. 3, p.5；Section 3.3, p.6）。

### Key Contributions

- 提出 UCPE：统一编码 6-DoF poses、intrinsics、lens distortions，并兼容不同 camera lens / projection types；其中 Relative Ray Encoding 解决非线性投影下的 token-level 几何差异，Lat-Up map 解决第一帧绝对 orientation 不明确的问题（Section 1, p.3）。
- 提出轻量注入机制：通过 spatial attention adapter 将 UCPE 接入预训练视频 Diffusion Transformer，保持原模型视觉先验，同时只增加 35.5M 左右参数，约为 7.3B base model 的 0.5%（Table 1, p.8）。
- 构建用于训练和评估的 camera-diverse video dataset，覆盖多种 motion trajectories、intrinsics 和 distortion profiles，使 lens control、orientation control、relative pose control 能在同一框架下被量化评估（Section 4.1, p.6）。
- 相比已有 direct parameterization、Plücker encoding、GTA、PRoPE 等，论文的关键区别在于：不是把相机作为一个全局刚体参数编码，而是把每个 token 的 viewing ray 作为 attention 几何单元，因此更适合跨 pinhole、wide-angle、fisheye 的统一控制（Fig. 2, p.2）。

### Experiments / Evidence

- 在合成 camera-diverse 数据集上，UCPE 在 lens、orientation、relative pose 和 video quality 多项指标上优于 ReCamMaster 与 Wan CameraCtrl。带 absolute orientation control 时，UCPE 的 FoV error 为 8.22°，pitch / roll error 为 4.35° / 3.74°，RotErr 为 4.12°，FVD 为 495.14，同时只用 35.6M trainable params；相比 ReCamMaster 的 354M 和 Wan CameraCtrl 的 1.5B 参数更轻（Table 1, p.8）。
- 在 RealEstate10K 上，UCPE 未针对该数据集 fine-tune，却取得最低的 relative pose errors：RotErr 0.56°、TransErr 1.25、CamMC 1.58，优于 ReCamMaster、Wan CameraCtrl、CameraCtrl 和 AC3D；说明该 encoding 对未见轨迹和短 prompt 也有较强泛化（Table 2, p.8）。
- 消融显示 Relative Ray Encoding 是关键：在保留 Lat-Up map 的情况下，用 PRoPE 或 GTA 替换 UCPE 的 ray encoding，会导致 lens control、relative pose control 和 video quality 下降；作者将其归因于这些方法对整张图使用单一 camera encoding，难以表示 distortion variation（Table 1, p.8；Section 4.3, p.8）。
- 定性结果显示，UCPE 更能同时跟随目标轨迹和生成符合镜头畸变的视觉效果；ReCamMaster 往往复现不了目标 distortion，Wan CameraCtrl 存在 camera motion deviations，在 RealEstate10K pinhole 设置下也会出现 motion 不足或不期望的 distortion artifacts（Fig. 4, p.6；Fig. 5, p.7）。

### Conclusions, Limitations, and Relation to Other Work

- 论文结论是：UCPE 通过 Relative Ray Encoding 和 Absolute Orientation Encoding，把 pose、intrinsics、lens distortion、pitch / roll 统一进 Transformer attention，可在极少新增参数下显著提升 camera-controllable video generation 的可控性与质量（Section 5, p.8）。
- 与 camera-controlled generation 相关工作相比，UCPE 不依赖显式 3D reconstruction，也不同于只控制 extrinsics 的方法；它直接在扩散模型中注入完整 camera geometry，因此更适合多镜头、多 FoV、多畸变条件（Section 2, p.3）。
- 与 camera encoding 相关工作相比，UCPE 继承 relative encoding 对坐标系选择更鲁棒的优势，但把关系从 camera-to-camera 细化到 ray-to-ray；这使其比 Plücker absolute encoding 更少依赖任意 world frame，也比 PRoPE / GTA 更能处理非 pinhole projection（Section 2, p.4；Fig. 2, p.2）。
- 局限性方面，材料没有展开失败案例、训练数据偏差、真实非中心相机支持程度或对更复杂动态场景的鲁棒性；正文虽声称 formulation 可扩展到 non-central cameras，但主要推导和实验以 central camera / UCM 为主，实际泛化到 catadioptric 或 full panoramic 系统的证据材料不足，无法确定（Section 3.1, p.4；Section 4.1, p.6）。
