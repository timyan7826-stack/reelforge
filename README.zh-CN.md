# ReelForge

> 输入主题，输出 MP4 —— 而且结果可复现。

ReelForge 是一个开源的、**确定性优先**的 AI 短视频生成引擎。给它一个主题，它就会运行一条六阶段管线 —— **脚本 → 分镜 → 素材 → 配音 → 字幕 → 渲染** —— 产出一段可直接发布的 MP4。每个阶段都是可替换的步骤，每个后端都是可插拔的组件，所以你得到的是可复现的输出、可批量生产的一致性，以及可审计的成本。

和那些"输入主题直接出片"的黑盒不同，ReelForge 是为需要**掌控力**的人设计的：内容团队、教育者、独立创作者，以及需要规模化生产、风格一致的营销人员。

## 为什么是 ReelForge？

市面上大多数 AI 视频工具是惊艳的 demo，但一到生产就露馅：

- **不可复现** —— 同一个主题跑两次，得到两个不同的视频；
- **厂商锁定** —— 脚本、配音、素材全部硬绑一家云服务商；
- **没有批产能力** —— 无法以一致的风格批量产出 20 条视频；
- **成本不透明** —— 出账单之前你永远不知道一条视频花了多少钱。

ReelForge 逐条回应：

| 痛点 | ReelForge 的解法 |
| --- | --- |
| 输出不稳定 | 固定 seed + 每次运行的完整 manifest；同一主题 ⇒ 同一管线、同一产物 |
| 厂商锁定 | LLM（OpenAI 兼容 / 离线）、TTS、素材后端全部可插拔 |
| 无法批量 | 一份配置、N 个主题；同一批次的阶段接线完全一致 |
| 成本隐藏 | 每次运行输出 `cost-report.json`，按阶段拆解 token、调用次数与预估美元 |

## 管线

```
主题
  │
  ▼
[1] 脚本         LLM 编写口语化短视频脚本（标题 + 台词行）
  ▼
[2] 分镜         每句台词 → 一条具体可拍的分镜视觉描述
  ▼
[3] 素材         每个分镜的背景图（Pexels 图库 / picsum / 本地 / 占位色块）
  ▼
[4] 配音         每场一句旁白 WAV（TTS / 离线占位）
  ▼
[5] 字幕         基于探测到的真实时间轴生成 SRT + 带样式的 ASS
  ▼
[6] 渲染         ffmpeg 合成片段 → 烧录字幕 → 混入 BGM → 输出 MP4
```

## 快速开始

环境要求：**Python ≥ 3.11** 和系统里的 **ffmpeg**。仅此而已 —— ReelForge **零 Python 第三方依赖**。

```bash
# 1. 安装
pip install -e .

# 2. 生成配置
reelforge init            # 生成 config.toml

# 3. 运行 —— 不需要任何 API key（离线演示模式）也能完整跑通
reelforge run -c config.toml --topic "晶体管是如何工作的"
```

离线演示模式使用 `template` LLM、`placeholder` 素材和 `silence` 配音，你可以在花一分钱之前，验证整条管线并检查所有中间产物。

```bash
# 4. 编辑 config.toml 接入真实后端，重新运行
reelforge run -c config.toml --topic "晶体管是如何工作的"
```

每次运行都会落在 `output/<run_id>/`：

```
output/<run_id>/
├── manifest.json      # 完整参数与产物记录（可复现的依据）
├── cost-report.json   # 分阶段用量与预估成本
├── script.json
├── storyboard.json
├── assets/scene_001.jpg ...
├── audio/scene_001.wav ...
├── captions.srt / captions.ass
├── clips/scene_001.mp4 ...
└── final.mp4          # 成片
```

## 配置

一个 TOML 文件驱动一切，见 [`examples/config.example.toml`](examples/config.example.toml)。

```toml
[llm]
backend = "openai"      # openai | template          （template = 离线演示）
model = "gpt-4o-mini"   # 任意 OpenAI 兼容模型 id
base_url = ""           # 可选：DeepSeek / Moonshot / Ollama 的 OpenAI 桥接
api_key = ""            # 或导出环境变量 OPENAI_API_KEY

[assets]
backend = "placeholder" # placeholder | picsum | pexels | local

[voiceover]
backend = "silence"     # openai | silence

[render]
subtitles = true
bgm = ""                # 可选的背景音乐文件

[reproducibility]
seed = 0                # 0 = 由主题推导 seed（每个主题确定性一致）
```

## 批量生产

管线由配置驱动、运行之间无状态，所以批量是一个内置命令 —— 主题文件里每行一个：

```bash
reelforge batch -c config.toml --topics-file topics.txt
```

```text
# topics.txt —— 空行与 # 开头的注释会被忽略
晶体管是如何工作的
天空为什么是蓝色的
互联网的历史
```

所有运行共用同一套接线（同一 LLM、同一 TTS 音色、同一渲染设置）→ 整批风格一致，且每条视频都有可审计的成本报告。

## 自带后端

后端都是普通类，一个文件即可接入：

- **LLM**：继承 `LLMBackend.complete()` → 脚本与分镜；
- **TTS**：继承 `TTSBackend.synthesize()` → 逐场旁白；
- **素材**：在 `AssetsStage` 中新增一个来源 → 逐场背景图。

OpenAI 兼容端点（DeepSeek、Moonshot、Ollama 的 OpenAI 桥接……）通过 `base_url` 即可使用内置的 `openai` 后端。

## 路线图

- [ ] 字幕样式预设与逐词卡拉OK高亮
- [ ] 片段间转场（交叉淡化、滑动）
- [ ] `--batch` 子命令：主题文件 + 每主题预算
- [ ] 本地优先的视频后端（ComfyUI / 本地模型）作为素材来源
- [ ] 动态视频片段替代静态图（文生视频或素材包）

## 开发

```bash
pip install -e ".[dev]"
pytest
```

CI 每次 push 都会运行单元测试 + 一次完整的**离线端到端渲染**——证明管线能从零产出真实的 `final.mp4`。

## 协议

[MIT](LICENSE)
