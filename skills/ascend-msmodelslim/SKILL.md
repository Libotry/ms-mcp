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

**Q: 量化显存不足？**
A: 使用逐层量化（自动生效）或设置 `--device cpu`（速度慢但省显存）。

**Q: 量化后精度下降明显？**
A: 调整离群值抑制算法（优先 Iterative Smooth），或使用 W8A8 而非 W4A8。

**Q: 哪个量化算法效果最好？**
A: 激活量化推荐 Smooth Quant / Iterative Smooth；权重量化推荐 AWQ / AutoRound。

**Q: 如何验证量化效果？**
A: 在相同输入下对比量化前后输出差异，或使用标准数据集评测精度差值。

**Q: 一键量化 vs 传统量化？**
A: 有模型对应脚本优先一键量化；脚本不支持的模型用传统量化。

---

## 十一、回答格式要求

当用户咨询 msModelSlim 量化和调优问题时，请按以下格式作答：

1. **问题确认**：确认量化场景（模型名、量化类型、精度问题现象）
2. **方案推荐**：推荐量化方式（一键/传统）和算法选择
3. **操作步骤**：给出具体命令或代码
4. **精度调优**：如涉及精度问题，按调优路径递进推荐

如用户提供具体模型和精度数据，可直接给出针对性建议。
