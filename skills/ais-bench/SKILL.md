---
name: ais-bench-benchmark
description: AISBench Benchmark 大模型评测工具的完整使用指南，支持精度评测和性能评测，覆盖安装、快速入门、模型配置、数据集、性能指标、结果解读和常见问题。
---

# AISBench Benchmark 评测工具 SKILL

你是一个 **AISBench 评测工具专家**，能够帮助用户快速上手和熟练使用 AISBench 完成模型评测任务。

（本回答基于 ais-bench-benchmark Skill 的 AISBench 使用规范）

---

## 一、工具概览

### 1.1 什么是 AISBench

**AISBench Benchmark** 是基于 [OpenCompass](https://github.com/open-compass/opencompass) 构建的 AI 模型评测工具，兼容 OpenCompass 配置体系，支持对服务化模型进行**精度评测**和**性能评测**。

### 1.2 核心能力

| 能力 | 说明 |
|------|------|
| **精度评测** | 文本推理、数学、常识、多模态、函数调用等数据集的精度验证 |
| **性能评测** | 延迟、吞吐、稳态性能、压测、真实流量模拟 |
| **多任务并行** | 多模型/多数据集/多场景并行执行 |
| **断点续测** | 精度评测支持失败用例重测 |
| **结果可视化** | 实时任务看板 + jsonl / CSV / Markdown 输出 |

### 1.3 环境要求

- **Python 版本**：仅支持 3.10 / 3.11 / 3.12
- **不支持** Python 3.9 及以下或 3.13 及以上
- **推荐使用 Conda** 管理环境避免依赖冲突

---

## 二、安装

### 2.1 源码安装

```bash
git clone https://github.com/AISBench/benchmark.git
cd benchmark
pip install -e ./ --use-pep 517
```

### 2.2 可选依赖

```bash
# 服务化模型支持（vLLM / TGI / MindIE / Triton）
pip install -r requirements/api.txt
pip install -r requirements/extra.txt

# 多模态支持
pip install -r requirements/hf_vl.txt

# 函数调用评测
pip install -r requirements/datasets/bfcl_eval.txt --no-deps

# OCRBench v2 支持
pip install -r requirements/datasets/ocrbench_v2.txt
```

### 2.3 验证安装

```bash
ais_bench -h
```

---

## 三、快速入门

### 3.1 精度评测

```bash
# 基础精度评测
ais_bench --models vllm_api_general_chat --datasets demo_gsm8k_gen_4_shot_cot_chat_prompt
```

### 3.2 性能评测

```bash
# 吞吐评测（1k 请求）
ais_bench --models vllm_api --datasets 1k_rps_avg_throughput

# 稳态性能评测
ais_bench --models vllm_api --evaluator stable_stage
```

### 3.3 实时看板

执行命令后看板实时显示任务状态，按 **`P`** 暂停/恢复刷新，`Ctrl+C` 退出。

---

## 四、核心概念

### 4.1 任务三元组

AISBench 评测任务由三类配置组合：

| 任务类型 | 说明 |
|---------|------|
| `--models` | 推理服务配置（模型地址、API 端点、并发数等） |
| `--datasets` | 数据集任务（数据集名称、prompt 配置） |
| `--evaluator` | 结果汇总任务（精度 / 性能 / 稳态） |

### 4.2 任务查询

```bash
# 查询模型/数据集对应的配置文件路径
ais_bench --models <model> --datasets <dataset> --search
```

---

## 五、模型配置

### 5.1 支持的模型类型

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

### 5.2 配置文件示例

```python
from ais_bench.benchmark.models import VLLMCustomAPI

models = [
    dict(
        type=VLLMCustomAPI,
        abbr="vllm-api-general-chat",
        model="your-model-name",      # 实际模型名称
        host="localhost",              # 推理服务 IP
        port=8080,                    # 推理服务端口
        url="/v1/chat/completions",  # 自定义路径
        api_key="",
        max_out_len=512,
        batch_size=1,
        temperature=0.01,
        retry=2,
        request_rate=0,              # 0 = 全速发送
    )
]
```

---

## 六、数据集

### 6.1 主要数据集

| 数据集 | 类型 |
|--------|------|
| `gsm8k` | 数学推理 |
| `hellaswag` | 常识推理 |
| `mmmu` / `mmmu_pro` | 多模态理解 |
| `ARC_c` / `ARC_e` | 科学问答 |
| `BFCL` | 函数调用评测 |
| `docvqa` / `textvqa` | 文档问答 |
| `longbenchv2` | 长文本理解 |
| `livecodebench` | 代码评测 |
| `mmlu` / `mmlu_pro` | 考试评测 |
| `ifeval` | 指令遵循 |
| `race` | 阅读理解 |
| `xsum` / `ROPES` | 摘要 / 推理 |
| `vocalbench` | 声音理解 |
| `mooncake_trace` | 模拟真实流量 Trace 调度 |

### 6.2 数据集搜索

```bash
ais_bench --models <model> --datasets <dataset> --search
```

---

## 七、性能评测参数

### 7.1 核心性能指标

| 指标 | 说明 |
|------|------|
| `first_token_latency` | 首 Token 延迟 |
| `per_token_latency` | Token 间隔延迟 |
| `request_throughput` | 请求吞吐 |
| `token_throughput` | Token 吞吐 |
| `RPS` | 每秒请求数 |
| `stable_stage` | 稳态性能（预热后压测） |

### 7.2 性能配置参数

| 参数 | 说明 |
|------|------|
| `--request_rate` | 请求发送速率（每秒请求数）|
| `--batch_size` | 并发请求数 |
| `--max_tokens` | 最大输出 Token 数 |
| `--stable_warmup` | 稳态预热轮数 |
| `--evaluation_interval` | 评测间隔 |

---

## 八、结果输出

### 8.1 输出目录结构

```
outputs/default/YYYYMMDD_HHMMSS/
├── configs/              # 任务配置合集
├── predictions/         # 推理输出
├── results/            # 评测分数原始数据
├── summary/            # 最终汇总报告
│   ├── summary.csv     # CSV 格式
│   ├── summary.md      # Markdown 格式
│   └── summary.jsonl   # JSONL 格式
└── logs/               # 详细执行日志
    ├── infer/          # 推理日志
    └── eval/           # 评测日志
```

### 8.2 汇总指标

精度评测结果示例：
```
dataset      version  metric  mode  vllm_api_chat
-------------------------------------------------
gsm8k       401e4c   accuracy  gen   62.50
```

---

## 九、精度 vs 性能

| 对比维度 | 精度评测 | 性能评测 |
|---------|---------|---------|
| 目标 | 验证模型输出质量 | 测量系统吞吐和延迟 |
| 指标 | Accuracy / Pass@k 等 | RPS / Latency / Throughput |
| 工具 | AISBench + 外部裁判模型 | AISBench 内置 |
| 输出 | summary/ | results/ |

---

## 十、常见问题

**Q: Python 版本不支持？**
A: 仅支持 3.10 / 3.11 / 3.12，不支持 3.9 和 3.13+。

**Q: 推理服务连不上？**
A: 检查 `host` / `port` 是否正确，`curl` 验证服务可达性。

**Q: 精度结果异常低？**
A: 检查 `model` 名称、`api_key`、数据集 prompt 配置。

**Q: 多任务并行？**
A: AISBench 支持多任务并行执行，参考配置文件组合多个 `--models` / `--datasets`。

---

## 十一、回答格式要求

当用户咨询 AISBench 问题时，请按以下格式作答：

1. **问题确认**：确认是精度评测还是性能评测，什么模型/数据集
2. **配置建议**：推荐合适的模型 + 数据集组合
3. **操作步骤**：给出 `ais_bench` 命令或 Python 配置
4. **结果解读**：说明输出文件内容和指标含义
</parameter>
