# AdaWorld: Learning Adaptable World Models with Latent Actions

- Imported from: https://arxiv.org/pdf/2503.18938
- PDF URL: https://arxiv.org/pdf/2503.18938.pdf
- Hash: b38d9c89e1e88aad
- Slug: b38d9c89e1e88aad
- Status: imported

## Structured Analysis

### Motivation

- 现有 world models 主要依赖 action-labeled data 来学习可控的未来预测；当新环境具有不同 action specification 时，往往需要重新收集大量标注并进行高成本训练，难以用少量交互快速适配（Abstract, p.1；Fig. 1, p.1）。
- 作者认为，仅从 action-agnostic videos 预训练虽然能带来视觉泛化，但没有在预训练阶段学习“动作如何导致状态转移”的可迁移知识，因此新动作空间到来时控制接口仍然脆弱（Section 1, p.1-2）。
- 核心动机是：能否像人类一样，从大量观察中学习可迁移的 action representations，再用极少交互把这些 latent action 与具体环境的动作空间对齐，从而得到 adaptable world model（Section 1, p.2）。

### Problem Setting

- 目标是学习一个 action-controlled world model，用于给定历史观测和动作条件后预测未来帧；难点在于预训练视频通常没有显式 action labels，且不同环境的 action format 很难统一（Section 2.1, p.3）。
- 论文关注两类适配能力：一是从一个 demonstration 中抽取动作并迁移到新上下文，无需训练；二是在少量 action-video pairs 下，将预训练模型适配成接受 raw action inputs 的专用 world model（Fig. 1, p.1；Section 2.3, p.5）。
- 设连续帧为 $f_t, f_{t+1}$，模型从二者中抽取 latent action $\tilde{a}$，并学习基于 $\tilde{a}$ 与历史帧预测下一帧。离散动作环境中，为每个动作初始化一个 latent action embedding；连续动作环境中，用轻量 MLP 将 raw action 映射到 latent action interface（Section 2.3, p.5）。

### Core Idea

- AdaWorld 的关键主张是将“动作信息”引入 world model 预训练，但不依赖人工动作标注；它通过 self-supervised latent action autoencoder 从无标注视频中抽取表示帧间关键转移的 compact latent action（Section 1, p.2；Fig. 2, p.3）。
- latent action 被设计成统一的 action-aware condition：不同环境、不同动作格式都先投影到同一连续 latent action space，再用于预训练和适配。这使预训练模型已经学会响应动作条件，而不是在下游才从零学习控制（Section 2.2, p.4-5）。
- 连续 latent action space 还允许动作组合与插值。例如论文展示将 “right” 与 “jump” 的 latent actions 平均，可生成 “jump right” 类型的新动作，说明该空间具有一定语义连续性（Fig. 5, p.5）。

### Method

- Latent Action Autoencoder：encoder 输入相邻两帧 $f_{t:t+1}$，通过 spatiotemporal Transformer 和 learnable tokens 聚合时间动态，只保留 $a_{t+1}$ 来估计 latent action 的 posterior $(\mu_{\tilde{a}}, \sigma_{\tilde{a}})$；decoder 输入前一帧 $f_t$ 与采样得到的 $\tilde{a}$，预测后一帧 $f_{t+1}$（Section 2.1, p.3）。
- 为避免 latent action 携带过多上下文纹理、颜色等无关信息，作者使用 information bottleneck 与 $\beta$-VAE 目标，在表达能力和 context disentanglement 之间折中：
  $$L^{pred}_{\theta,\phi}(f_{t+1})=\mathbb{E}_{q_\phi(\tilde{a}|f_{t:t+1})}\log p_\theta(f_{t+1}|\tilde{a},f_t)-\beta D_{KL}(q_\phi(\tilde{a}|f_{t:t+1})||p(\tilde{a}))$$
  默认 $\beta=2\times10^{-4}$；较小 $\beta$ 会增强区分性但削弱跨环境同类动作聚合（Eq. 2, p.4；Fig. 7, p.9）。
- Action-Aware Pretraining：先用 latent action encoder 从视频中抽取 $\tilde{a}$，再训练 autoregressive diffusion world model 预测下一帧。模型基于 Stable Video Diffusion 初始化，每次 denoise 一个 noisy frame，并将 latent action 拼接到 timestep embedding 与 CLIP image embedding 中；历史帧作为 short-term memory，训练时随机采样最多 6 帧并加入 noise augmentation，以缓解长 rollout drift（Section 2.2, p.4-5；Fig. 3, p.3）。
- 预训练损失为 diffusion loss：
  $$L_{pretrain}=\mathbb{E}_{x_0,\epsilon,t}\left[\|x_0-\hat{x}_0(x_t,t,c)\|^2\right]$$
  其中 $c$ 包含 historical frames 与 latent action $\tilde{a}$（Eq. 3, p.5）。

### Key Contributions

- 提出 AdaWorld：一种 action-aware world model pretraining 范式，通过 latent actions 在无标注视频中学习可迁移动作控制，使模型可进行 zero-training action transfer 和 low-shot world model adaptation（Section 1, p.2）。
- 提出连续 latent action autoencoder，将帧间关键变化压缩为 context-invariant latent action；相比 discrete latent action 或 optical flow condition，连续空间更能表达细粒度动作并支持组合（Section 2.1, p.3-4；Fig. 5, p.5）。
- 构建大规模多样化预训练数据，包含公共数据集和从 Gym Retro、Procgen 等 1016 个环境自动收集的视频，总量约 2000 million frames，覆盖 ego view、third-person view、虚拟游戏和真实活动等互动场景（Section 3, p.6）。
- 展示该范式具有一定通用性：将 AdaWorld 的 action-aware pretraining 应用于 iVideoGPT，也能提升其下游适配性能，说明方法不局限于本文的 diffusion 架构（Table 6, p.9）。

### Experiments / Evidence

- Action transfer：在 LIBERO 与 SSv2 的 1300 对视频评测中，AdaWorld 明显优于 action-agnostic、flow condition 和 discrete condition。LIBERO 上 FVD 从 action-agnostic 的 1545.2 降到 767.0，human success 从 0% 升到 70.5%；SSv2 上 FVD 为 473.4，human success 为 61.5%，均为最佳（Table 1, p.6）。
- World model adaptation：在 Habitat、Minecraft、DMLab、nuScenes 四个未见环境中，仅用每个离散动作 100 个样本或 nuScenes 的 100 条轨迹，并 finetune 800 steps，AdaWorld 在 PSNR/LPIPS 上均优于基线；所有 action-aware 方法都显著优于 action-agnostic，支持“预训练时引入动作信息”这一核心判断（Table 2, p.7）。
- Visual planning：在 Procgen 游戏任务中，AdaWorld finetune 后平均成功率为 56.67%，高于 action-agnostic 的 26.00% 和 Q-learning 的 27.17%；即使不更新模型权重，仅用平均 latent actions 作为 action embeddings，平均成功率也达到 44.83%（Table 3, p.8）。机器人 VP2 任务中，AdaWorld aggregate success 为 21.54，高于 action-agnostic 的 5.03（Table 4, p.8）。

### Conclusions, Limitations, and Relation to Other Work

- 论文结论是：world model 的适配能力不仅来自视觉视频预训练规模，也来自预训练阶段是否学习了 action-conditioned transition。AdaWorld 用 latent actions 作为统一控制接口，使模型能在新环境中快速迁移动作、学习动作空间，并提升规划效果（Conclusion, p.9）。
- 与 Genie、VQ-VAE latent action 等关注 playability 或 behavior cloning 的方法不同，AdaWorld 强调连续 latent action space 的表达性、可组合性和跨上下文迁移；与 optical flow condition 相比，它不是直接编码像素运动，而是通过 bottleneck 学习更抽象的动作转移表示（Section 2.1, p.2-3；Table 1, p.6）。
- 与 action-agnostic video pretraining 相比，AdaWorld 不把控制学习完全留给下游 finetuning，而是在大规模无标注视频中预先建立 latent action interface；实验中 action-agnostic baseline 在少样本规划和仿真适配上接近 random 或明显落后（Table 2, p.7；Table 3, p.8）。
- 局限包括：推理不能实时运行；当 rollout 超出初始场景范围时，生成新内容能力不足；极长时序 rollout 仍然困难。作者认为可通过 distillation、sampling acceleration、扩大模型和数据规模，以及更强 long-term rollout 技术改进（Limitations, p.9）。
