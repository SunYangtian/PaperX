# Cosmos World Foundation Model Platform for Physical AI

- Imported from: https://research.nvidia.com/labs/cosmos-lab/cosmos3/technical-report.pdf
- PDF URL: https://research.nvidia.com/labs/cosmos-lab/cosmos3/technical-report.pdf
- Hash: fe1deaf17d300d17
- Slug: fe1deaf17d300d17
- Status: imported

## Assistant Note (2026-06-03 17:16)

根据当前给出的论文片段，**无法精确回答 Cosmos 3 中 action 的底层数值格式**，例如它到底是：

- 连续向量还是离散 token；
- 机器人末端执行器位姿增量还是关节角；
- 是否包含 gripper 开合；
- 每个 action token 的维度；
- 是否使用 VQ/codebook/tokenizer；
- action 的采样频率、坐标系、归一化方式等。

这些细节应当在论文正文的 **2.1.3 Action**、**3.2.3 Action**、**4.2.5 Robot Policy Post-Training**、**6.2.5 Action Generation Evaluation** 或附录 **B.5 / E.4 / E.5** 中，但你目前提供的本地材料只包含目录和引言，没有这些小节正文。

不过，基于已有材料，可以确定它对 action 的表示有以下几个层面。

---

## 1. Action 被作为一种独立模态表示

Cosmos 3 明确把 **action sequences** 和 language、image、video、audio 并列建模。摘要中说它可以在统一的 **mixture-of-transformers architecture** 中 jointly process and generate：

> language, image, video, audio, and action sequences

也就是说，action 不是附加标签，也不是只通过文本描述动作，而是作为模型输入/输出空间中的一种正式模态。

可以理解为多种 token / embedding 并列进入统一模型：

- Language tokens
- Image tokens
- Video tokens
- Audio tokens
- Action tokens / action embeddings

它们共同进入同一个 omnimodal world model。

---

## 2. Action 是时间序列，而不是单个类别标签

材料明确使用的是 **action sequences**，不是 action label。

这说明 action 表示的是一段随时间变化的控制轨迹或行为序列。对于 Physical AI，这通常对应：

$a_1, a_2, \ldots, a_T$

其中每个 $a_t$ 是某个时间步的动作。

在机器人场景中，$a_t$ 可能是机器人控制量，例如末端执行器位姿变化、关节控制、gripper 状态等；但当前材料没有说明 Cosmos 3 具体采用哪一种。

---

## 3. Action 有专门的 encoder

目录中第 **2.1 Encoders** 下单独列出：

- 2.1.1 Image and Video
- 2.1.2 Audio
- **2.1.3 Action**

这说明 Cosmos 3 不是把 action 简单拼成文本，而是有专门的 **Action encoder** 或 action 输入处理模块。

合理理解是：

原始 action sequence → Action encoder → action tokens / action embeddings → Mixture-of-Transformers

但具体 encoder 是 MLP、linear projection、离散 tokenizer，还是其他结构，当前材料没有给出。

---

## 4. Action 可以作为输入，也可以作为输出

Cosmos 3 支持灵活的 input-output configuration。引言明确说，根据输入输出配置不同，它可以作为多种模型工作，包括：

- policy / world-action model；
- forward dynamics model；
- inverse dynamics model。

这意味着 action 在不同任务中扮演的角色不同。

### 4.1 作为输出：Policy / Action Generation

如果输入是观察和任务指令，输出是 action sequence，则模型相当于一个 policy model：

- 输入：video / image observation + language instruction
- 输出：action sequence

例如：

看到桌面 + 指令“把杯子拿起来” → Cosmos 3 → 机器人动作序列

材料中还提到 Cosmos 3 被 post-trained 成 robot policy，并在 RoboArena 上排名最好。

---

### 4.2 作为输入：Forward Dynamics / World Simulation

如果输入包含当前状态和 action，输出未来视频或未来状态，则模型类似 forward dynamics model：

- 输入：current video/image + action sequence
- 输出：future video / future world state

这对应“执行某个动作后世界会如何变化”。

---

### 4.3 同时建模 video 和 action：World-Action Model

引言中说 Cosmos 3 可以作为 **world-action model for joint action prediction and environmental simulation**。

也就是说，它不仅可以预测动作，也可以根据动作模拟环境变化：

- observation + instruction → action
- observation + action → future video
- observation + instruction → action + future video

这种设计使 action 和 world dynamics 被联合建模。

---

## 5. Action 与视频/时间位置编码相关

目录中还出现：

- **Token Arrangement and Generation Mode**
- **Multimodal Position Embedding**
- **Absolute Temporal Modulation**

这对 action 表示很重要。因为 action 是时间序列，需要和视频帧、音频片段等时间维度对齐。

例如概念上可能是：

- Frame 1 / Frame 2 / Frame 3 / ...
- Action 1 / Action 2 / Action 3 / ...

或者：

- $t=1$: video tokens + action token
- $t=2$: video tokens + action token
- $t=3$: video tokens + action token

当前材料没有说明具体 token 排列方式，但可以确定论文专门设计了 token arrangement 和 temporal modulation 来处理这类多模态时序信息。

---

## 6. 对 DROID robot policy 的 action 细节：当前材料不足

材料中提到开放模型：

> Cosmos3-Nano-Policy-DROID

并且引言说：

> Sec. 4.2.5 describes how we post-train Cosmos 3 into a highly capable world-action model on DROID.

这说明 Cosmos 3 在 DROID 数据上做了机器人策略后训练。

但是当前片段没有给出 DROID action 的具体格式。按照常见 DROID / robot policy 设定，action 可能包括：

- end-effector translation；
- end-effector rotation；
- gripper command；
- possibly joint-level command；
- continuous control vector。

但这些是通用机器人学习中的常见表示，**不能直接断言就是本文采用的格式**。论文片段没有说明维度、坐标系、控制频率或离散化方式。

---

## 7. 可以确定与不能确定的内容

| 问题 | 当前材料能否回答 | 结论 |
|---|---:|---|
| action 是否是独立模态 | 可以 | 是，与 language/image/video/audio 并列 |
| action 是否是序列 | 可以 | 是，论文称为 action sequences |
| 是否有专门 action encoder | 可以 | 是，目录有 2.1.3 Action |
| action 能否作为输出 | 可以 | 是，用于 policy / action generation |
| action 能否作为输入 | 可以 | 是，用于 world-action / forward dynamics |
| action 是否和视频联合建模 | 可以 | 是，论文提到 joint action prediction and environmental simulation |
| action 的具体维度 | 不可以 | 材料未给出 |
| action 是连续还是离散 | 不可以 | 材料未给出 |
| 是否使用 action tokenizer | 不可以 | 材料未给出 |
| 是否是末端执行器控制 | 不可以 | 材料未给出 |
| 是否包含 gripper | 不可以 | 材料未给出 |

---

## 8. 简单总结

在 Cosmos 3 中，**action 被表示为一种时间序列模态**，与文本、图像、视频、音频一起进入统一的 omnimodal Transformer 框架。它通过专门的 action encoder 转换为模型可处理的 token 或 embedding，并且可以根据任务配置作为输入或输出：作为输出时对应 robot policy / action generation；作为输入时可用于 forward dynamics 或 world simulation；与视频联合时形成 world-action model。

但当前材料没有提供 action 的底层数值表示，因此不能确定它是连续控制向量、离散 token、末端执行器位姿增量、关节角，还是其他格式。

---

## 参考材料

- [1] page 1：摘要；Cosmos 3 jointly process and generate language, image, video, audio, and action sequences。
- [2] page 2：目录；2.1.3 Action、3.2.3 Action、4.2.5 Robot Policy Post-Training。
- [3] page 3：目录；6.2.5 Action Generation Evaluation、B.5 Prompt Template for Action Generation。
- [4] page 4：目录；E.4 Synergy Between Action Modes、E.5 Video-Action Consistency。
- [5] page 5：引言；Cosmos 3 unifies policy/world-action model、forward dynamics model、inverse dynamics model。
- [6] page 6：引言与结果概览；Cosmos3-Nano-Policy-DROID、Robot Policy Post-Training、world-action model on DROID。
