---
name: msmodeling
description: MindStudio Modeling 性能仿真框架，包含 TensorCast（LLM/视频生成性能预测）和 ServingCast（服务化推理吞吐量优化）。触发：用户提到 msmodeling、TensorCast、ServingCast、性能仿真、TTFT/TPOT、throughput optimizer、SLO约束
---

# MindStudio Modeling 性能仿真框架

## 两大组件

| 组件 | 用途 |
|-----|------|
| **TensorCast** | PyTorch 程序性能模拟器（虚拟机器），无需真实硬件预测性能 |
| **ServingCast** | 服务化推理仿真，支持 TTFT/TPOT 指标和 SLO 约束下吞吐量寻优 |

## 安装

```bash
git clone https://gitcode.com/Ascend/msmodeling.git -b develop
cd msmodeling
pip install uv && uv venv --python 3.10 myenv && source myenv/bin/activate
pip install -r requirements.txt
```

Python >= 3.10

---

## TensorCast

无需真实硬件，模拟 PyTorch 模型在指定 DeviceProfile 上的执行，输出算子级耗时拆解、内存占用、Chrome Trace。

### 支持的模型

- **文本生成**：Qwen、DeepSeek、GLM 等 Hugging Face LLM
- **视频生成**：Stable Video Diffusion 等 diffusion transformer

### 支持的设备

内置：`TEST_DEVICE`、`ATLAS_800_A2_376T_64G`、`ATLAS_800_A3_752T_128G_DIE` 等

自定义设备：在 `device_profiles/` 放置 Python 文件定义 DeviceProfile

### 文本生成模拟

```bash
python -m cli.inference.text_generate <model_id> [options]
```

| 常用参数 | 说明 |
|---------|------|
| `--device` | 设备类型 |
| `--num-queries` | 请求数 |
| `--query-length` | 输入 token 数 |
| `--context-length` | 输出 token 数 |
| `--decode` | decode 模式（query-length=1）|
| `--compile` | torch.compile() 优化 |
| `--quantize-linear-action` | 量化：W8A8_DYNAMIC / W4A8_STATIC / FP8 / MXFP4 等 |
| `--quantize-attention-action` | KVCache 量化：INT8 / FP8 |
| `--tp-size` / `--dp-size` / `--ep-size` | 并行策略 |
| `--chrome-trace` | 生成 Chrome Trace 文件 |

**示例：Qwen3-32B Prefill 模拟**
```bash
python -m cli.inference.text_generate Qwen/Qwen3-32B \
  --num-queries 2 --query-length 3500 --device TEST_DEVICE
```

**示例：Decode 模拟 + W8A8 动态量化**
```bash
python -m cli.inference.text_generate Qwen/Qwen3-32B \
  --num-queries 10 --query-length 1 --context-length 4500 \
  --device TEST_DEVICE --quantize-linear-action W8A8_DYNAMIC
```

### 视频生成模拟

```bash
python -m cli.inference.video_generate <model_id> [options]
```

| 常用参数 | 说明 |
|---------|------|
| `--batch-size` | batch size |
| `--seq-len` | 序列长度 |
| `--chrome-trace` | 生成 Chrome Trace |
| `--height` / `--width` / `--frame-num` | 视频尺寸 |
| `--sample-step` | 采样步数 |
| `--quantize-linear-action` | 量化方案 |
| `--world-size` | 并行数 |
| `--cfg-parallel` | CFG 并行 |
| `--dit-cache` | DIT Cache |

### 输出

- **算子级耗时拆解表**：各算子执行时间
- **内存占用分析**：总内存 / 峰值内存
- **FLOPs 分析**：计算量和访存量
- **Chrome Trace**：可视化瓶颈定位

---

## ServingCast

服务化推理仿真，模拟端到端请求级性能。

### 服务仿真

```bash
export PYTHONPATH=/path/to/msmodeling:$PYTHONPATH
python main.py \
  --instance_config_path=./example/instances.yaml \
  --common_config_path=./example/common.yaml
```

输出指标：

| 指标 | 说明 |
|-----|------|
| `E2E_TIME` | 端到端延迟（issue → last token）|
| `TTFT` | 首 token 时间（Time-to-First-Token）|
| `TPOT` | 每输出 token 时间（Time-Per-Output-Token）|
| `OUTPUT_TOKEN_THROUGHPUT` | 每请求输出 token 速率 |
| `request_throughput` | 系统级请求速率 |
| `output_token_throughput` | 输出 token 吞吐 |

开启 profiling：
```bash
python main.py ... --enable_profiling --profiling_output_path=/path/to/output
```
生成 `chrome_tracing.json` 和 `profiler.db`，用 Chrome Tracing 或 MindStudio Insight 查看。

### 吞吐量寻优（SLO 约束）

```bash
python -m cli.inference.throughput_optimizer <model_id> [options]
```

| 常用参数 | 说明 |
|---------|------|
| `--device` | 设备类型 |
| `--num-devices` | 设备数 |
| `--input-length` | 最大输入 token |
| `--output-length` | 输出 token |
| `--compile` | torch.compile |
| `--quantize-linear-action` | 量化方案 |
| `--disagg` | PD 分离模式 |
| `--ttft-limits` | TTFT 上限（毫秒）|
| `--tpot-limits` | TPOT 上限（毫秒）|
| `--batch-range` | batch size 搜索范围 |
| `--jobs` | 并行任务数 |

**聚合模式（Aggregation）**
```bash
python -m cli.inference.throughput_optimizer Qwen/Qwen3-32B \
  --device TEST_DEVICE --num-devices 8 \
  --input-length 3500 --output-length 1500 \
  --compile --quantize-linear-action W8A8_DYNAMIC \
  --tpot-limits 50
```

**PD 分离模式（Disaggregation）**
```bash
# Prefill 模式：搜索 TTFT 约束下的最优吞吐
python -m cli.inference.throughput_optimizer Qwen/Qwen3-32B \
  --device TEST_DEVICE --num-devices 8 \
  --input-length 3500 --output-length 1500 \
  --disagg --ttft-limits 2000

# Decode 模式：搜索 TPOT 约束下的最优吞吐
python -m cli.inference.throughput_optimizer Qwen/Qwen3-32B \
  --device TEST_DEVICE --num-devices 8 \
  --input-length 3500 --output-length 1500 \
  --disagg --tpot-limits 50
```

### TPOT 计算公式

```
TPOT = (TTFT + decode_latency × output_length) / output_length
```

### TTFT 计算公式

```
prefill_batch_size = max_prefill_tokens // input_length
sum_for_ttft = (prefill_latency × prefill_batch_size) × (1 + calc_nums) × calc_nums / 2
TTFT = sum_for_ttft / concurrency
```

### 输出吞吐量公式

```
output_throughput = 1000 × (output_length × concurrency) / (TTFT + TPOT × output_length)
```

---

## TensorCast vs ServingCast 选择

| 场景 | 推荐工具 |
|-----|---------|
| 单算子/单步性能预测 | TensorCast |
| 端到端请求延迟（TTFT/TPOT）| ServingCast |
| 硬件容量规划 | ServingCast throughput_optimizer |
| 无硬件环境下的性能预估 | TensorCast |