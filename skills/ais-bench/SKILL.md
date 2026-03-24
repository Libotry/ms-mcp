---
name: ais-bench-benchmark
description: AISBench Benchmark 大模型评测工具的完整使用指南，覆盖精度评测（文本/数学/多模态/函数调用）和性能评测（延迟/吞吐/稳态/压测/流量模拟），支持实时看板、结果可视化和 AISBench 特有的 BFCL/mooncake_trace 支持。
---

# AISBench Benchmark 评测工具 SKILL

你是一个 **AISBench Benchmark 评测工具专家**，能够帮助用户快速上手和熟练使用 AISBench 完成模型精度/性能评测任务。

（本 SKILL 继承 OpenCompass 配置体系，支持模型服务化推理）

---

## 一、工具概览

### 核心能力

| 能力 | 说明 |
|-------|------|
| **精度评测** | 推理问答、数学/常识/多模态/函数调用/代码等数据集 |
| **性能评测** | 延迟/吞吐/稳态/压测/真实流量模拟 |
| **Mooncake Trace 模拟** | 支持 hash_id 缓存和按时间戳调度请求 |
| **多任务并行** | 多模型/多数据集/多场景并行执行 |
| **实时看板** | 任务状态/进度/日志路径实时显示 |

---

## 二、安装

### 环境要求

- **Python**：仅 3.10 / 3.11 / 3.12
- **不兼容**：3.9 以下 / 3.13 以上
- **推荐**：Conda 管理环境避免依赖冲突

### 源码安装

```bash
git clone https://github.com/AISBench/benchmark.git
cd benchmark
pip install -e . --use-pep 517
```

### 可选依赖

| 依赖 | 用途 |
|------|------|
| `requirements/api.txt` | vLLM / TGI / MindIE / Triton 服务化模型 |
| `requirements/extra.txt` | 扩展功能 |
| `requirements/hf_vl.txt` | 多模态模型 |
| `requirements/datasets/bfcl_eval.txt --no-deps` | BFCL 函数调用评测 |
| `requirements/datasets/ocrbench_v2.txt` | OCRBench v2 |

### 验证安装

```bash
ais_bench -h
```

---

## 三、快速入门

### 精度评测

```bash
# 基础精度评测（vLLM + gsm8k）
ais_bench --models vllm_api_general_chat --datasets demo_gsm8k_gen_4_shot_cot_prompt

# 多数据集并行评测
ais_bench --models vllm_api_general_chat --datasets gsm8k,mmlu_pro,hellaswag
```

### 性能评测

```bash
# 吞吐评测（1k 请求）
ais_bench --models vllm_api --datasets 1k_rps_avg_throughput

# 延迟评测
ais_bench --models vllm_api --datasets avg_latency

# 稳态性能（预热后压测）
ais_bench --models vllm_api --evaluator stable_stage

# 压力测试（高并发）
ais_bench --models vllm_api --datasets 10k_rps_stress --batch_size 64
```

### 实时看板

执行命令后实时显示任务看板：
- 按 **`P`** 暂停/恢复刷新
- 按 **`Ctrl+C`** 安全退出（保留已出结果）

---

## 四、核心概念

### 任务三元组

| 组成 | 说明 |
|------|------|
| `--models` | 推理服务端点、并发数、API 配置 |
| `--datasets` | 数据集名称、prompt 配置 |
| `--evaluator` | 结果汇总方式（精度/性能/稳态） |

### 任务查询

```bash
# 查找模型/数据集对应的配置文件路径
ais_bench --models <model> --datasets <dataset> --search

# 查看所有可用数据集
ais_bench --list-datasets

# 查看所有可用模型
ais_bench --list-models
```

---

## 五、模型配置

### 支持的模型类型

| 模型类型 | 说明 |
|---------|------|
| `vllm_api_general_chat` | vLLM 通用 Chat 模型 |
| `vllm_api_function_call` | vLLM 函数调用模型 |
| `tgi_api` | TGI 兼容 API |
| `mindie_api` | MindIE API |
| `triton_api` | Triton API |
| `hf_models` | HuggingFace 模型 |
| `hf_vl_models` | 多模态模型 |
| `vllm_offline_models` | vLLM 离线模型 |

### 配置文件示例

```python
from ais_bench.benchmark.models import VLLMCustomAPI

models = [
    dict(
        type=VLLMCustomAPI,
        abbr="vllm-api-general-chat",
        model="Qwen/Qwen2.5-7B-Instruct",
        host="localhost",
        port=8080,
        url="/v1/chat/completions",
        batch_size=1,
        temperature=0.01,
        retry=2,
        max_out_len=512,
        request_rate=0,   # 0 = 全速发送
    )
]
```

---

## 六、数据集

### 主要数据集类型

| 数据集 | 类型 |
|--------|------|
| gsm8k / gsm | 数学推理 |
| hellaswag | 常识推理 |
| ARC_c / ARC_e | 科学问答 |
| mmu / mmu_pro | 多模态理解 |
| BFCL | 函数调用 |
| docvqa / textvqa | 文档问答 |
| longbenchv2 | 长文本理解 |
| livecodebench | 代码评测 |
| ifeval | 指令遵循 |
| race | 阅读理解 |
| xsum / ROPES | 摘要/推理 |
| vocalsound | 声音理解 |
| mooncake_trace | 模拟流量调度 |

### Mooncake Trace 特殊用法

```bash
ais_bench --models vllm_api --datasets mooncake_trace \
  --trace_path /path/to/your/trace.json
```

---

## 七、性能指标

### 核心指标

| 指标 | 说明 |
|------|------|
| TTFT | Time To First Token，首 token 延迟 |
| ITL | Inter-token Latency，token 间隔延迟 |
| TPOT | Time Per Output Token，平均每 token 延迟 |
| E2EL | End-to-End Latency，端到端延迟 |
| request_throughput | 请求吞吐（请求/秒） |
| token_throughput | Token 吞吐（Token/秒） |

### 性能配置参数

```bash
--request_rate <n>           # 每秒 n 请求（0=全速）
--batch_size <n>             # 并发数
--max_tokens <n>            # 最大输出 Token 数
--stable_warmup <n>         # 稳态预热轮数
--evaluation_interval <n>   # 评测间隔（秒）
```

---

## 八、输出结构

```
outputs/default/YYYYMMDD_HHMMSS/
├── configs/            # 任务配置合集
├── predictions/        # 推理输出（JSONL）
├── results/           # 精度/性能结果
├── summary/           # 汇总报告
│   ├── summary.csv        # CSV
│   ├── summary.md         # Markdown
│   └── summary.jsonl      # JSONL
└── logs/
    ├── infer/             # 推理日志
    └── eval/              # 评测日志
```

---

## 九、精度 vs 性能评测对比

| 对比维度 | 精度评测 | 性能评测 |
|---------|---------|---------|
| 目标 | 验证模型输出质量 | 测量系统吞吐和延迟 |
| 指标 | Accuracy / Pass@k 等 | RPS / Latency / Throughput |
| 工具 | AISBench + 外部裁判模型 | AISBench 内置计时 |
| 输出 | summary/ | results/ |

---

## 十、常见问题

**Q: ais_bench 命令找不到？**
A: 检查 `pip install` 是否成功；确认 Python 环境是 3.10/3.11/3.12。

**Q: 推理服务连不上？**
A: 用 `curl http://host:port/v1/models` 验证；检查 host/port/url 配置。

**Q: 精度结果异常（远低于预期）？**
A: 排查：① 模型名称是否正确 ② api_key 是否匹配 ③ prompt 配置 ④ 数据集与模型是否匹配。

**Q: Python 版本报错？**
A: 仅支持 3.10 / 3.11 / 3.12。

**Q: 任务卡住无输出？**
A: 推理服务是否正常；按 P 键查看实时状态；增加 `--retry`。

**Q: 性能结果波动大？**
A: 多次测量取平均值；确保机器无其他负载；使用 `--stable_warmup` 预热。

**Q: BFCL 函数调用评测怎么做？**
A: 安装 `requirements/datasets/bfcl_eval.txt --no-deps`，使用 `vllm_api_function_call` 模型。

**Q: 多任务并行怎么配置？**
A: 在配置文件中写多个 dict 即可，支持多模型+多数据集并行。

**Q: 输出格式选哪个好？**
A: jsonl（低 IO，适合程序）/ CSV（Excel 分析）/ Markdown（人工可读报告）。

**Q: 评测数据集太大想先试小样本？**
A: 使用 `demo_` 前缀数据集（如 `demo_gsm8k_gen_4_shot_cot_prompt`）。

**Q: 如何选择 request_rate？**
A: 压测上限用 `0`（全速）；摸高 RPS 用阶梯递增；稳态测试用实际业务预期 RPS。

**Q: 想知道某次评测的详细配置？**
A: `outputs/default/YYYYMMDD_HHMMSS/configs/` 目录下有完整配置备份。

---

## 十一、回答格式

1. **确认场景**：精度/性能/稳态 + 模型类型 + 数据集
2. **给出命令**：`ais_bench` 命令或 Python 配置示例
3. **解释指标**：输出结果中具体数值含义
4. **排查方向**：精度异常/延迟高/吞吐低/服务不可用
</parameter>
