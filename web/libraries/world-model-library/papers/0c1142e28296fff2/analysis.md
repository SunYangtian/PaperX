# BiWM: Advancing Open-Source Interactive Video World Models with Bidirectional Autoregression

- Imported from: https://arxiv.org/abs/2606.10135
- PDF URL: https://arxiv.org/pdf/2606.10135.pdf
- Hash: 0c1142e28296fff2
- Slug: 0c1142e28296fff2
- Status: imported

## Structured Analysis

### Motivation

- 现有交互式 video world model 的核心目标，是把离线的高质量 bidirectional video diffusion generator 改造成可随用户动作逐段生成的 autoregressive 系统；交互性与实时响应主要来自“按需续写帧/片段”的能力（Introduction, p.2-3）。
- 主流 causal autoregressive 管线虽然高效，因为历史可以放入 KV cache 复用，但历史一旦写入 cache 就不能被修正；视频扩散模型又不像语言模型会反复离散化到合法 token，小误差会在连续像素/latent 空间中累积，导致画面退化和相机控制漂移相互放大（Fig. 3, p.3）。
- 已有 Yume-1.5、Matrix-Game-3.0 等 bidirectional autoregressive 世界模型显示出更好的视觉质量与长程稳定性，但缺少完整开源训练框架；相对地，minWM 提供的是 causal 路线，无法覆盖这种范式（Introduction, p.3-4）。
- BiWM 的动机是补齐开源生态中的 bidirectional autoregressive 全栈工具，同时把训练流程压缩到学术预算可承受的程度，并兼顾生成质量、可控性和推理速度（Fig. 1, p.2；Contributions, p.4）。

### Problem Setting

- 输入可以是文本或图像提示，系统需要在用户连续动作，尤其是 camera movement/action stream 控制下，逐 chunk 延续一个虚拟世界。形式上，视频 latent 序列被分成多个连续 chunk，模型按 \(p(x|c,a)=\prod_b p(c_b|c_{<b},c,a_b)\) 生成，其中 \(c\) 是静态场景 caption，\(a_b\) 是当前 chunk 的离散相机动作序列（Section 3.1, p.6）。
- causal 与 bidirectional 的差别不在于是否分 chunk，而在于历史表示是否允许被当前 chunk 重新解释。causal 模型读取冻结历史，BiWM 则在每次生成时让历史和当前 chunk 在窗口内 full bidirectional attention，因此历史 latent/state 会随新帧一起刷新（Section 3.1, p.6）。
- 数据侧需要把真实或合成相机轨迹转换成可注入模型的动作监督。BiWM 使用 OpenVid+WorldPlay 的 prescribed trajectories，以及 Sekai 真实步行视频，通过 SLAM/monocular geometry/bundle adjustment 恢复 6-DoF pose，再量化为动作类别（Section 3.2, p.6-7）。
- caption 被严格限制为 static-only，即描述物体、布局和外观，不描述相机运动，避免文本泄露轨迹，使运动监督主要来自 action stream（Section 3.2, p.7）。

### Core Idea

- BiWM 的核心思想是保留预训练视频 foundation model 原生的 bidirectional attention：每个短 chunk 内 full attention，chunk 之间 autoregressive rollout。这样牺牲少量缓存效率，换取历史自校正能力，从而减轻长程误差累积和 camera drift（Section 3.1, p.6；Fig. 3, p.3）。
- 训练流程被压缩为两阶段：Stage 1 通过 camera/action control fine-tuning 注入控制能力；Stage 2 直接进行 few-step DMD distillation，把 50-step bidirectional sampler 蒸馏为 4-step chunk-wise generator。相比 minWM 所需四阶段，BiWM 明确主张更短、更易复现的管线（Fig. 1, p.2；Section 3, p.5-6）。
- 相机控制不新增 camera encoder 或 residual pose branch，而是把离散相机动作写成自然语言 camera-text，通过已有 text-conditioning/cross-attention 路径注入。这使模型在 step 0 仍接近原预训练生成器，只是条件文本更丰富，因此更稳定、数据效率更高（Section 3.3, p.7-8）。
- 为应对 DMD/reverse-KL 的 mode-seeking 倾向，BiWM 在蒸馏中加入 GAN、SFT 和 forward-KL anchors，以同时保持纹理、细节、运动覆盖和场景动态（Section 3.5, p.10-11）。

### Method

- **离散相机动作。** 连续 6-DoF 相对位姿 \((\Delta t_i,\Delta R_i)\) 被量化为 9 类平移 × 9 类旋转的 81-class vocabulary：平移包含 static、forward/backward/left/right 和四个对角方向，旋转包含 static、pitch/yaw 及组合方向；标签计算为 translation class × 9 + rotation class（Fig. 4, p.9；Section 3.3, p.7）。
- **Text-based camera control。** 每个动作类别对应固定自然语言短语，如“Camera moves forward. Camera yaws right.”。81 个短语在初始化时由冻结 text encoder 预编码为 buffer；运行时只 gather 对应 action embedding，再与 scene caption embedding 拼接，经原模型 text projection 和 cross-attention 注入每帧 latent token（Section 3.3, p.7-8）。
- **历史条件与压缩。** BiWM 把已生成历史转换为 memory tokens，作为当前 chunk 的 key/value prefix，并提供三种可插拔模式：sink-based sliding window、PackForcing-style learned history encoder、Yume-1.5/FramePack-style multi-scale pyramid。目标是在长程 rollout 中降低显存和计算，同时保留远距离上下文（Section 3.4, p.8-9）。
- **蒸馏目标。** Stage 2 使用 self-rollout DMD：frozen real score 作为 teacher，online fake score 作为 critic，generator 自回归生成 chunk。主损失是 distribution matching；辅助项包括 hinge GAN 用于高频纹理，低噪声 SFT velocity regression 用于细节，real/teacher forward-KL 用于 mass-covering、抑制低运动或静态退化（Section 3.5, p.10-11）。
- **部署与低比特。** 核心训练仍只有两阶段；低比特推理是可选部署路径，支持 FP8-E4M3 和 NVFP4。论文还描述了 QAT：在 Stage 2 尾部开启 fake quant，并用 full-precision forward 作为 teacher，通过 forward-KL 对齐 velocity 和 clean latent 估计（Section 3.7, p.12-13）。

### Key Contributions

- 提出 BiWM：论文称其为首个面向 bidirectional autoregressive interactive video world models 的 full-stack open-source framework，定位为 minWM 等 causal 框架的双向范式补充，而不是同一范式内的小改动（Contributions, p.4）。
- 提供紧凑两阶段 recipe：camera-text pretraining 加 multi-objective few-step distillation。论文报告 Stage 1 约 100 optimizer steps 获得 camera control，Stage 2 约 200 steps 完成 distillation，使用 8×H200 GPUs、gradient accumulation 4，整体在数小时级完成（Section 3.7, p.12；Implementation Details, p.13）。
- 方法泛化到多种 backbone：Wan2.1-T2V-1.3B、Wan2.2-TI2V-5B、HunyuanVideo-1.5-TI2V-8B、LTX-2.3-22B；覆盖 cross-attention、MMDiT 与 audio-video backbone，并支持对已有 bidirectional AR 模型二次微调到新数据分布（Contributions, p.4；Section 3.6, p.11）。
- 提供额外能力：event editing 可在探索过程中注入新文本事件；纯 T2V 蒸馏得到的 checkpoint 也可在推理时通过把用户图像编码为初始 clean latent history 实现 training-free image-to-video（Fig. 5, p.12；Fig. 6, p.13）。

### Experiments / Evidence

- 相机可控性主要由定性结果支持。Fig. 2 展示在 Sekai-domain 街景中，不同行使用不同恒定离散动作，模型能遵守平移和视角方向，同时保持画面质量；Fig. 3 则展示 causal baseline 在 walking trajectory 下出现画面洗白、结构崩坏和控制漂移，用作 BiWM 设计动机的对照证据（Fig. 2, p.2；Fig. 3, p.3）。
- anchor losses 的作用由 Fig. 8 展示：只用 DMD 的 4-step generator 画面更雾化、低对比且近似静态；加入 GAN、SFT、forward-KL 后，细节、对比度和时间动态明显增强。该证据支持作者关于 reverse-KL mode-seeking 会导致运动/内容退化，而多目标 anchors 可缓解的判断（Fig. 8, p.15）。
- 低比特推理由 Fig. 9 定性说明：BF16 与 FP8-E4M3 rollout 几乎逐帧一致，NVFP4 保留单帧清晰度、色彩和场景外观，但 autoregressive 内容会因累计量化噪声产生轻微 drift。论文也明确说低比特主要在 batch、graph compilation 和真实低比特 kernel 配合时带来吞吐收益（Fig. 9, p.16；Section 3.7, p.12-13）。
- 论文承认系统性跨 backbone quantitative study 仍在进行，将随代码发布；因此当前结果更多是机制与定性行为说明，而非完整 benchmark 结论（Results, p.13-14）。

### Conclusions, Limitations, and Relation to Other Work

- 结论上，BiWM 把预训练 bidirectional video diffusion backbone 转换为可交互的 chunk-wise autoregressive world model：窗口内保留 full bidirectional attention，窗口间 autoregressive，并通过 81 类离散 camera-text 控制、4-step distillation 和多目标反退化损失实现高质量可控 rollout（Conclusion, p.14-15）。
- 与 causal world models/minWM 的关系是互补：causal 方法更强调 KV cache 和低延迟，但更容易积累不可修正历史误差；BiWM 用较小的 per-window latency 代价换取更稳定的长程视觉质量与可控性，并将训练流程从多阶段压缩到两阶段（Introduction, p.3-4；Conclusion, p.15）。
- 与 Yume-1.5、Matrix-Game-3.0 的关系是开源可复现化：这些系统已证明 bidirectional AR 有经验优势，但训练数据和完整 pipeline 不充分开放；BiWM 的贡献在于提供代码、脚本、checkpoint 和可替换组件，而非只报告单一闭源模型效果（Related Work, p.5；Contributions, p.4）。
- 局限方面，论文材料显示完整 head-to-head quantitative benchmarking 尚未完成；实验主要为定性图示和组件说明。未来方向包括 continuous/compositional action vocabularies、更强 long-horizon memory、更丰富 audio-video control，以及与 causal recipes 的系统对比（Results, p.13-14；Conclusion, p.15）。
