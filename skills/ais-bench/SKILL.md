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
| **精度评测** | 推理问答、 数学 / 常识 / 多模态 / 函数调用 / 代码等数据集 |
| **性能评测** | 延迟 / 吞吐 / 稳态 / 压测 / 真实流量模拟 |
| **Mooncake Trace 模拟** | 支持 hash_id 缓存和按时间戳调度请求 |
| **多任务并行** | 多模型 / 多数据集 / 多场景并行执行 |
| **实时看板** | 任务状态 / 进度 / 日志路径 |

---

## 二、安装

### 环境要求

- **Python**：仅 3.10 / 3.11 / 12
- **不兼容**：3.9 以下 / 3.13 以上
- **推荐**：Conda 管理环境

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

---

## 三、快速入门

### 精度评测

```bash
# 基础精度评测（vLLM + gsm8k 数据集）
ais_bench --models vllm_api_general_chat --datasets demo_gsm8k_gen_4_shot_cot_prompt
```

### 性能评测

```bash
# 吞吐评测（1k 请求）
ais_bench --models vllm_api --datasets 1k_rps_avg_throughput

# 稳态性能
ais_bench --models vllm_api --evaluator stable_stage
```

---

## 四、核心概念

### 任务三元组

| 组成 | 说明 |
|------|------|
| `--models` | 推理服务端点、并发数、API 配置 |
| `--datasets` | 数据集名称、prompt 配置 |
| `--evaluator` | 结果汇总方式（精度 / 性能 / 稳态） |

### 任务查询

```bash
# 查找模型/数据集对应的配置文件路径
ais_bench --models <model> --datasets <dataset> --search
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
        model="your-model-name",     # 实际模型名称
        host="localhost",
        port=8080,
        url="/v1/chat/completions",
        batch_size=1,
        temperature=0.01,
        retry=2,
    )
]
```

---

## 六、数据集

### 支持的数据集类型

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
| xsum / ROPES | 摘要 / 推理 |
| vocalsound | 声音理解 |
| mooncake_trace | 模拟流量调度（按时间戳 / hash_id 缓存 / 可复现 prompt） |

### 数据集查询

```bash
ais_bench --models <model> --datasets <dataset> --search
```

---

## 七、性能指标

### 核心指标

| 指标 | 说明 |
|------|------|
| first_token_latency | 首 Token 延迟 |
| per_token_latency | Token 间隔延迟 |
| request_throughput | 请求吞吐 |
| token_throughput | Token 吞吐 |
| RPS | 每秒请求数 |
| stable_stage | 稳态性能（预热后压测）|

### 性能配置参数

```bash
# 请求级配置
--request_rate <n>    # 每秒 n 请求
--batch_size <n>        # 并发数
--max_tokens <n>         # 最大输出 Token 数
--evaluation_interval <n>  # 评测间隔
```

---

## 八、输出结构

```
outputs/default/YYYYMMDD_HHMMSS/
├── configs/          # 任务配置合集
├── predictions/      # 推理输出（JSONL）
├── results/          # 精度/性能结果
├── summary/          # 汇总报告
│   ├── summary.csv       # CSV 格式
│   ├── summary.md        # Markdown 格式
│   └── summary.jsonl     # JSONL 格式
└── logs/
    ├── infer/           # 推理日志
    └── eval/            # 评测日志
```

---

## 九、Mooncake Trace 特殊支持

### Trace 模拟

支持 hash_id 缓存 / 时间戳调度 / 可复现 prompt：

| 特性 | 说明 |
|------|------|
| 按时间戳调度 | 支持真实业务流量回放 |
| hash_id 缓存 | 请求缓存复用 |
| 可复现 prompt | 相同 hash_id 生成一致结果 |

---

## 十、常见问题

**Q: 推理服务连不上？**
A: `curl http://host:port` 验证服务可达性。

**Q: 精度结果异常？**
A: 检查模型名称、API key、prompt 配置、数据集路径。

**Q: Python 版本报错？**
A: 仅支持 3.10 / 3.11 / 3.12。

**Q: 任务卡住？**
A: 推理服务是否正常；增加 `--retry` 重试次数。

**Q: 多任务并行？**
A: AISBench 支持多模型 + 多数据集 + 多场景并行。

**Q: BFCL 函数调用评测怎么做？**
A: 安装 `requirements/datasets/bfcl_eval.txt` 后使用 `vllm_api_function_call` 模型。

**Q: 输出格式选哪个？**
A: jsonl（低 IO 开销）/ CSV（Excel 分析）/ Markdown（可读报告）。

**Q: 性能结果在哪里看？**
A: `results/` 目录，`summary/` 目录。

---

## 十一、回答格式

1. **确认场景**：精度 / 性能 / 稳态 + 模型类型 + 数据集
2. **给出命令**：ais_bench 命令或 Python 配置
3. **解释指标**：输出结果中的具体数值含义
4. **排查方向**：精度异常 / 延迟高 / 吞吐低 / 服务不可用
</parameter>
</parameter>
</minimax:tool_call>