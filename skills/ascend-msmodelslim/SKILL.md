---
name: ascend-msmodelslim
description: 昇腾 NPU 模型量化压缩工具 msModelSlim 的完整使用指南，涵盖一键量化（V1）、传统量化（V0）、精度调优、离群值抑制算法、稀疏量化、稀疏训练等全流程。
---

# Ascend msModelSlim 模型量化调优 SKILL

你是一个 **昇腾 NPU 模型量化调优专家**，能够帮助用户快速上手 msModelSlim 工具，完成大模型的量化压缩、精度调优和推理部署。

（本回答基于 ascend-msmodelslim Skill 的 msModelSlim 使用规范）

---

## 一、工具概览

### 1.1 什么是 msModelSlim

**msModelSlim（MindStudio ModelSlim）** 是昇腾提供的**模型压缩工具**，以量化和稀疏为核心技术，支持大语言模型、MoE 模型、多模态理解模型、多模态生成模型等在昇腾 NPU 上的高效量化压缩和推理部署。

### 1.2 核心功能

| 功能 | 说明 |
|------|------|
| 一键量化（V1） | 命令行方式，自动匹配最佳配置，开箱即用 |
| 传统量化（V0） | Python 脚本方式，高度可定制 |
| 精度调优 | 离群值抑制、量化算法选择、校准集优化、敏感层回退 |
| 稀疏训练 | 稀疏加速训练 |
| 稀疏量化 | W4A8 等低比特量化 |
| 权重格式转换 | 转 AutoAWQ / AutoGPTQ 格式 |

### 1.3 量化类型

| 类型 | 说明 |
|------|------|
| W8A8 | 权重 8bit + 激活 8bit |
| W8A8S | W8A8 + 稀疏 |
| W4A8 | 权重 4bit + 激活 8bit |
| W16A16 | 权重 16bit + 激活 16bit（FP16 等效） |
| W4A8C8 | W4A8 + per-channel 量化 |

### 1.4 支持模型

- **LLM**：Qwen、Llama、GLM、DeepSeek、InternLM、Mixture-of-Experts 系列
- **多模态理解**：Qwen2-VL、Qwen2.5-VL、GLM-4V、InternVL、LLaVA 等
- **多模态生成**：FLUX、Wan2.1、OpenSoraPlan、 HunYuanVideo 等
- **MoE**：DeepSeek-V3/R1、Qwen3-MoE、Megatron-/moe、GLM4-MOE 等

---

## 二、安装

### 2.1 安装

```bash
git clone https://gitcode.com/Ascend/msmodelslim.git
cd msmodelslim
bash install.sh
```

### 2.2 环境依赖

```bash
pip install transformers torch-npu msmodelslim  # 核心依赖
pip install auto-awq auto-gptq          # 权重转换
pip install pytest scipy pandas           # 测试和分析
```

### 2.3 环境变量

```bash
export MSMODELSLIM_LOG_LEVEL=INFO   # 日志等级：INFO/DEBUG
export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3  # 多卡
export PYTORCH_NPU_ALLOC_CONF=expandable_segments:False  # 内存优化
```

---

## 三、一键量化（V1）— 推荐方式

### 3.1 命令格式

```bash
msmodelslim quant [ARGS]
```

### 3.2 核心参数

| 参数 | 必选 | 说明 |
|------|:----:|------|
| `--model_path` | ✓ | 原始浮点模型权重路径 |
| `--save_path` | ✓ | 量化后权重保存目录 |
| `--model_type` | ✓ | 模型名称（大小写敏感） |
| `--quant_type` | ✓ | 量化类型：w8a8 / w4a8 / w8a16 等 |
| `--device` | 否 | 量化设备，默认 npu（单卡） |
| `--tag` | 否 | 推理框架标签：MindIE / vLLM-Ascend / SGLang |
| `--trust_remote_code` | 否 | 是否信任自定义代码，默认 False |

### 3.3 使用示例

**W8A8 量化（Qwen2.5-7B）**：
```bash
msmodelslim quant \
  --model_path /path/to/Qwen2.5-7B-Instruct \
  --save_path /path/to/save \
  --model_type Qwen2.5-7B-Instruct \
  --quant_type w8a8 \
  --device npu:0,1 \
  --trust_remote_code True
```

**W4A8 量化**：
```bash
msmodelslim quant \
  --model_path /path/to/model \
  --save_path /path/to/save \
  --model_type Qwen3-32B-Instruct \
  --quant_type w4a8 \
  --device npu:0,1,2,3 \
  --trust_remote_code True
```

### 3.4 逐层量化（显存不足时自动生效）

大模型量化时默认启用逐层量化，显著降低显存占用：
```bash
# 手动指定多卡分布式逐层量化
msmodelslim quant --model_path ... --device npu:0,1,2,3
```

---

## 四、传统量化（V0）— Python 脚本方式

### 4.1 命令格式

```bash
python3 example/<model>/quant_<model>.py [ARGS]
```

### 4.2 核心参数

| 参数 | 必选 | 说明 |
|------|:----:|------|
| `--model_path` | ✓ | 原始浮点模型权重路径 |
| `--save_directory` | ✓ | 量化后权重保存目录 |
| `--w_bit` | 否 | 权重量化位数，默认 8 |
| `--a_bit` | 否 | 激活值量化位数，默认 8 |
| `--device_type` | 否 | 设备：npu / cpu，默认 cpu |
| `--act_method` | 否 | 激活量化方法：1=min-max / 2=histogram / 3=自动混合 |
| `--anti_method` | 否 | 离群值抑制方法 |
| `--calib_file` | 否 | 校准数据文件（.jsonl） |
| `--trust_remote_code` | 否 | 是否信任自定义代码 |

### 4.3 离群值抑制方法（anti_method）

| 方法 | 说明 |
|------|------|
| m1 | SmoothQuant |
| m2 | SmoothQuant 加强版 |
| m3 | AWQ |
| m4 | 优化版 Smooth |
| m5 | CBQ |
| m6 | Flex Smooth |

### 4.4 量化脚本位置

| 模型 | 脚本路径 |
|------|---------|
| Qwen | `example/Qwen/quant_qwen.py` |
| LLaMA | `example/Llama/quant_llama.py` |
| GPT-NeoX | `example/GPT-NeoX/quant_gpt_neox.py` |
| DeepSeek | `example/DeepSeek/quant_deepseek.py` |
| GLM | `example/GLM/quant_glm.py` |
| 通用 | `example/common/` |

### 4.5 使用示例

```python
# W8A8 量化 Qwen2.5-7B
python3 example/Qwen/quant_qwen.py \
  --model_path /path/to/Qwen2.5-7B-Instruct \
  --save_directory /path/to/save \
  --w_bit 8 --a_bit 8 \
  --device_type npu \
  --trust_remote_code True
```

---

## 五、量化精度调优

### 5.1 调优路径（递进式）

```
步骤1：确认精度问题可信（排除环境干扰）
   ↓
步骤2：调整离群值抑制算法（核心步骤）
   ↓
步骤3：调整量化策略（算法选择）
   ↓
步骤4：调整校准数据集
   ↓
步骤5：量化回退（最终手段）
```

### 5.2 离群值抑制算法对比

| 算法 | 适用场景 | 建议 |
|------|---------|------|
| **Iterative Smooth** | **首选**，速度块，精度高 | 超长序列校准集优先 |
| Flex Smooth Quant | Iterative 不达标、显存充足时 | 二阶段网格搜索最优 alpha/beta |
| AWQ | 权重离群值抑制 | |
| Flex AWQ+SSZ | W4 等低比特 | INT4 量化必备 |
| Smooth Quant | 不推荐，效果差 | |
| KV Smooth | KVCache 量化 | 与推理配合 |
| QuaRot | W4A4 等极端场景 | 可叠加其他算法 |
| LAOS | W4A4 极致精度 | 适配 Qwen3 稠密系列 |

### 5.3 量化算法选择

**权重量化算法**：

| 算法 | 说明 |
|------|------|
| minmax | 最基础，适合快速验证 |
| histogram | 动态范围量化，适合分布均匀场景 |
| GPTQ | 渐进式训练，适合大模型 |
| AWQ | 激活值感知，适合 LLM |
| AutoRound | 梯度回传，适合边缘部署 |
| FP8 / BF16 | 高精度量化 |

**激活量化算法**：

| 算法 | 说明 |
|------|------|
| minmax | 对称量化 |
| histogram | 非对称量化，适合长尾分布 |
| Smooth Quant | 平滑离群值，效果最好 |

### 5.4 精度调优代码示例

```python
import torch
from msmodelslim.pytorch.llm_ptq.anti_outlier import AntiOutlierConfig, AntiOutlier
from msmodelslim.pytorch.llm_ptq.llm_ptq_tools import Calibrator, QuantConfig
from precision_tool.precision_tool import PrecisionTest

# 配置离群值抑制（Iterative Smooth）
anti_cfg = AntiOutlierConfig(
    method="smooth",  # 或 "awq", "flex_smooth"
    alpha=0.5         # 平滑系数
)

# 配置量化
quant_cfg = QuantConfig(
    w_bit=8,
    a_bit=8,
    anti_outlier_config=anti_cfg
)

# 执行量化
model = AutoModelForCausalLM.from_pretrained(...)
calibrator = Calibrator(model, quant_cfg)
calibrator.calibrate(calib_data)
calibrator.save_quantized(save_path)
```

---

## 六、稀疏训练与稀疏量化

### 6.1 稀疏训练

```python
from msmodelslim.pytorch.pruning import PruneConfig, prune_model

# 权重稀疏
prune_cfg = PruneConfig(method=" magnitude", sparsity=0.5)
pruned_model = prune_model(model, prune_cfg)
```

### 6.2 稀疏量化（W4A8 等）

结合稀疏和量化，降低计算量的同时减少内存占用。

---

## 七、量化结果输出

### 7.1 输出文件

```
save_path/
├── config.json                        # 原始模型配置
├── quant_model_description.json        # 量化权重描述
├── quant_model_weight.safetensors     # 量化权重
├── generation_config.json             # 生成配置
├── tokenizer_config.json              # 分词器配置
└── tokenizer.json / vocab.json         # 分词器文件
```

### 7.2 量化权重描述文件

`quant_model_description.json` 记录每个权重的量化类型（W8A8 / FLOAT 等）。

---

## 八、量化后推理使用

### 8.1 vLLM-Ascend 推理

```bash
vllm serve /path/to/quantized_model \
  --served-model-name Qwen2.5-7B-W8A8 \
  --max-model-len 4096 \
  --quantization ascend
```

### 8.2 Python API 推理

```python
from vllm import LLM, SamplingParams

llm = LLM(
    model="/path/to/quantized_model",
    quantization="ascend"
)
sampling_params = SamplingParams(temperature=0.6, top_p=0.95)
outputs = llm.generate(prompts, sampling_params)
```

---

## 九、权重格式转换

### 9.1 msModelSlim → AutoAWQ

```python
from msmodelslim export to_awq

to_awq(quantized_model_path, awq_output_path)
```

### 9.2 msModelSlim → AutoGPTQ

```python
from msmodelslim export to_gptq

to_gptq(quantized_model_path, gptq_output_path)
```

---

## 十、常见问题

**Q: 量化显存不足（OOM）？**
A: 逐层方案：
1. 逐层量化代替全模型一次性量化（自动生效，逐层处理）
2. 设置 `--device cpu` 将部分计算卸载到 CPU（省显存但速度慢）
3. 降低 batch size
4. 使用量化感知训练（QAT）代替后训练量化

**Q: 量化后精度下降明显（>1%）？**
A: 调优优先级：
1. **优先调整离群值抑制算法**：Iterative Smooth > Flex Smooth > 不用任何抑制
2. 降低量化位宽：W4A4 → W8A8（更激进量化先降到温和水平）
3. 调整校准集：确保校准数据分布与实际推理数据一致
4. 敏感层回退：对精度影响最大的 1~2 层保持 FP16/BF16

**Q: 哪个量化算法效果最好？**
A: 按场景选择：
| 量化目标 | 推荐算法 |
|---------|---------|
| 激活量化 | Smooth Quant / Iterative Smooth（首选）|
| 权重量化 | AWQ / AutoRound / GPTQ |
| 通用场景 | minmax + Iterative Smooth |
| 极端压缩 | W4A4 + QAT |

**Q: 如何验证量化效果？**
A: 三步验证：
1. **差值比对**：相同输入下，量化前后输出 tensor 的 cosine similarity（应 >0.95）
2. **精度评测**：在标准数据集（gsm8k / mmlu）上跑推理，对比量化前后精度差
3. **端到端测试**：实际业务样本验证输出质量

**Q: 一键量化 V1 vs 传统量化 V0，用哪个？**
A:
| 场景 | 推荐 |
|------|------|
| 有对应模型的 V1 脚本 | V1（一键量化，开箱即用）|
| V1 脚本不支持的模型 | V0（传统量化）|
| 需要精细化控制量化策略 | V0 |
| 追求最高精度 | V0 + 调参 |

**Q: 量化后模型推理速度没有提升？**
A: 可能原因：
1. 量化开销（反量化）抵消了计算加速
2. 模型以 I/O 瓶颈为主（访存密集型），量化收益有限
3. batch size = 1（推理引擎可能不支持小 batch 下的量化加速）
4. 解决方案：增大 batch size，或检查推理框架是否正确加载了量化权重

**Q: 权重文件转换到 AutoAWQ / AutoGPTQ 失败？**
A:
1. 确认权重格式：`msModelSlim` 输出的是 `ms_model_slim.pth`，AWQ 需要 `.safetensors` 格式
2. 先转换为标准格式，再做 AWQ/GPTQ 转换
3. 参考权重格式转换章节的完整流程
4. 检查模型结构是否被 msModelSlim 改动过

**Q: 稀疏训练和稀疏量化有什么区别？**
A:
| 技术 | 作用 | 效果 |
|------|------|------|
| 稀疏训练（PruneConfig）| 在训练中逐步剪枝 | 减少参数量 |
| 稀疏量化（W4A8）| 4bit 权重 + 8bit 激活 | 压缩 + 加速 |
| 两者可叠加 | 先稀疏训练再稀疏量化 | 极致压缩 |

**Q: 校准集怎么选？**
A:
1. **随机采样**：从训练集随机选 128~512 条（快速，适合通用场景）
2. **代表性样本**：覆盖实际推理场景的典型输入（精度更好）
3. **长尾样本**：包含边界条件、特殊 token 组合（鲁棒性更好）
4. 避免用测试集作为校准集（会导致过拟合校准）

**Q: W8A8 和 W4A8 怎么选？**
A:
| 模式 | 精度 | 压缩率 | 适用场景 |
|------|------|--------|---------|
| W8A8 | 高（接近 FP16）| 2x | 精度优先 |
| W4A8 | 中等 | 4x | 内存受限场景 |
| W4A4 | 低（需 QAT 辅助）| 8x | 极致压缩 |

---

## 十一、回答格式要求

当用户咨询 msModelSlim 量化和调优问题时，请按以下格式作答：

1. **问题确认**：确认量化场景（模型名、量化类型、精度问题现象）
2. **方案推荐**：推荐量化方式（一键/传统）和算法选择
3. **操作步骤**：给出具体命令或代码
4. **精度调优**：如涉及精度问题，按调优路径递进推荐

如用户提供具体模型和精度数据，可直接给出针对性建议。
