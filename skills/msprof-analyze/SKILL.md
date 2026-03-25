---
name: msprof-analyze
description: MindStudio Profiler Analyze（msprof-analyze）昇腾性能分析工具完整指南，覆盖安装配置、集群分析（cluster_time_summary）、专家建议（advisor）、性能比对（compare）、空闲分析（free_analysis）、通信瓶颈分析（communication_bottleneck）等全部分析能力，支持 PyTorch/MindSpore/msMonitor 数据源，包含命令参数和输出文件说明。
---

# msprof-analyze SKILL

你是一个 **msprof-analyze 昇腾性能分析工具专家**，能够帮助用户理解和使用 msprof-analyze 完成集群性能数据的分析、瓶颈定位和问题诊断。

---

## 一、工具概览

### 什么是 msprof-analyze

**MindStudio Profiler Analyze**（msprof-analyze）是 MindStudio 全流程工具链推出的性能分析工具，基于采集的性能数据进行分析，识别 AI 作业中的性能瓶颈。

### 核心分析能力

| 能力分类 | 分析能力 | 说明 |
|---------|---------|------|
| **拆解对比** | `cluster_time_summary` | 集群迭代耗时拆解（计算/通信/内存/空闲） |
| | `cluster_time_compare_summary` | 集群性能数据比对 |
| | `module_statistic` | PyTorch 模型层级结构拆解 |
| | `calibrate_npu_gpu` | NPU 与 GPU 跨平台性能校准 |
| **计算类** | `compute_op_sum` | 计算类算子汇总 |
| | `freq_analysis` | AI Core 频率分析（空闲/异常检测） |
| | `computational_op_masking` | 算子耗时掩盖分析 |
| | `ep_load_balance` | MoE 负载均衡分析 |
| **通信类** | `communication_matrix` | 通信矩阵分析 |
| | `communication_time` | 通信耗时分析 |
| | `communication_bottleneck` | 通信瓶颈定位（快慢卡/Host/Device Bound） |
| | `hccl_sum` | 通信算子汇总 |
| | `pp_chart` | PP 流水线图分析 |
| **Host下发类** | `cann_api_sum` | CANN 层 API 汇总 |
| | `mstx_sum` | MSTX 打点汇总 |
| | `free_analysis` | 空闲时间原因分析 |
| **其他** | `compare` | NPU vs GPU / NPU vs NPU 性能比对 |
| | `advisor` | 专家建议（计算/通信/调度瓶颈诊断） |

### 支持框架

PyTorch / MindSpore / msMonitor 采集的性能数据

### 版本

| 版本 | 发布日期 | Cann 版本 |
|-----|---------|---------|
| 8.2.0 | 2025-11-29 | 8.2+ |
| 8.1.0 | 2025-07-30 | 8.1+ |

---

## 二、安装指南

### pip 安装（推荐）

```bash
pip install msprof-analyze
pip install msprof-analyze=={版本号}  # 安装指定版本
```

### whl 包安装

```bash
# 1. 下载 whl（如 msprof_analyze-8.2.0-py3-none-any.whl）
# 2. 校验
sha256sum msprof_analyze-8.2.0-py3-none-any.whl
# 3. 安装
pip install ./msprof_analyze-8.2.0-py3-none-any.whl
```

### 源码编译安装

```bash
git clone https://gitcode.com/Ascend/msprof-analyze
cd msprof-analyze
pip install -r requirements.txt
python3 setup.py bdist_wheel
cd dist && pip install ./msprof_analyze-*.whl
```

### 卸载 / 升级

```bash
pip uninstall msprof-analyze
pip install ./msprof_analyze-新版本-py3-none-any.whl
```

---

## 三、快速入门

### 命令格式

```bash
msprof-analyze -m [feature] -d <profiling_path> [-o <output_path>] [options]
```

### 最简使用

```bash
# 集群耗时拆解
msprof-analyze -m cluster_time_summary -d ./cluster_data

# 默认分析（step_trace_time + 通信矩阵 + 通信耗时）
msprof-analyze -m all -d ./cluster_data

# 专家建议
msprof-analyze advisor all -d ./prof_data

# 性能比对（NPU vs GPU）
msprof-analyze compare -d ./ascend_pt -bp ./gpu_trace.json -o ./compare_output
```

---

## 四、全局参数

| 参数 | 必选 | 说明 |
|-----|:----:|------|
| `-d <path>` / `--profiling_path` | Y | 性能数据汇集目录 |
| `-o <path>` / `--output_path` | N | 自定义输出路径 |
| `-m <mode>` / `--mode` | N | 分析能力，默认 all |
| `--export_type` | N | 输出格式：`db` / `notebook` / `text`，默认 `db` |
| `--force` | N | 强制执行（跳过属主/文件大小检查） |
| `--parallel_mode` | N | 多卡并发方式：`concurrent` |
| `-v` / `--version` | N | 查看版本号 |

---

## 五、集群分析（cluster）

### 5.1 cluster_time_summary — 迭代耗时拆解

```bash
msprof-analyze -m cluster_time_summary -d ./cluster_data [-o ./output]
```

**输出字段**：

| 字段 | 说明 |
|-----|------|
| `stepTime` | 迭代总耗时 |
| `computation` | 计算总时间 |
| `communication` | 通信总时间 |
| `communicationNotOverlapComputation` | 未被计算掩盖的通信耗时 |
| `communicationOverlapComputation` | 计算和通信重叠的时间 |
| `free` | 空闲时间 |
| `memory` | 拷贝耗时 |
| `communicationWaitStageTime` | 通信等待耗时 |
| `communicationTransmitStageTime` | 通信传输耗时 |

### 5.2 communication_bottleneck — 通信瓶颈分析

```bash
msprof-analyze -m communication_bottleneck -d ./cluster_data \
  --rank_id 0 --top_num 10
```

**瓶颈定位逻辑**：
1. 分析指定 rank 的 TopN 通信操作
2. 对比所有 rank 识别快慢卡
3. 判断是 **Host Bound** 还是 **Device Bound**
4. 定位具体延迟操作

### 5.3 free_analysis — 空闲时间原因分析

```bash
msprof-analyze -m free_analysis -d ./cluster_data --top_num 10
```

**可识别空闲原因**：
- Device 侧仍有任务执行（不在计算/通信统计范围）
- PyTorch 层长时间未下发任务（Host/框架侧 idle）
- CANN 层下发间隔异常或 node@launch 耗时偏大

### 5.4 module_statistic — 模型结构拆解

需在模型代码中添加 `torch_npu.npu.mstx.range_start/range_end` 打点。

```bash
msprof-analyze -m module_statistic -d ./result --export_type text
```

**输出内容**：
- 模型层级化结构
- 算子与 Kernel 映射关系
- MatMul/FlashAttention 等核心算子的 **MFU**（算力利用率）
- Device 侧 Kernel 执行耗时

---

## 六、专家建议（advisor）

### 子命令

| 子命令 | 覆盖范围 |
|-------|---------|
| `all` | overall + computation + communication + schedule + dataloader + memory |
| `computation` | computation + Kernel compare |
| `schedule` | schedule + API compare |

### 命令格式

```bash
msprof-analyze advisor all -d <profiling_path> \
  [-bp <benchmark_path>] [-o <output_path>] \
  [-cv <cann_version>] [-tv <torch_version>]
```

### advisor 诊断维度

| 维度 | 分析项 |
|-----|-------|
| **overall** | 性能拆解（计算/通信/空闲）、慢卡/慢链路识别、环境变量建议 |
| **computation** | AICPU 调优、动态 Shape、MatMul/FlashAttention 性能分析、Block Dim、算子瓶颈、融合算子图、AI Core 降频 |
| **communication** | 通信小包检测、带宽抢占、重传检测、字节对齐 |
| **schedule** | 亲和 API 替换、算子下发路径、SyncBatchNorm、流同步、GC 分析、可融合算子序列 |
| **dataloader** | 慢 DataLoader 检测 |
| **memory** | 内存异常申请释放 |
| **comparison** | Kernel / API 快慢卡对比（有无标杆场景） |

### 输出文件

- `mstt_advisor_{timestamp}.html` — 分级优化建议（红/黄/绿高/中/低）
- `mstt_advisor_{timestamp}.xlsx` — 问题综述与详细分析

### 关键 Diff Ratio 说明

- **Diff Total Ratio** = 标杆总耗时 / 待比对总耗时
- **Diff Avg Ratio** = 标杆平均耗时 / 待比对平均耗时
- 比值 > 1：当前环境更优；< 1：有待优化

---

## 七、性能比对（compare）

### NPU vs GPU / NPU vs NPU

```bash
msprof-analyze compare -d ./ascend_pt \
  -bp ./gpu_trace.json -o ./compare_output
```

### 主要开关

| 开关 | 说明 |
|-----|------|
| `--enable_profiling_compare` | 开启总体性能比对 |
| `--enable_operator_compare` | 开启算子性能比对 |
| `--enable_communication_compare` | 开启通信性能比对 |
| `--enable_memory_compare` | 开启算子内存比对 |
| `--enable_kernel_compare` | 开启 kernel 性能比对 |
| `--enable_api_compare` | 开启 API 性能比对 |

### 比对分析指引

| 症状 | 分析方向 |
|-----|---------|
| Computing Time 增大 | 分析**算子性能** |
| Uncovered Communication Time 增大 | 分析**通信性能**，若无劣化通信算子 → 集群分析 |
| Mem Usage 增大 | 分析**算子内存**，若无明显占用 → TensorBoard/MindStudio Insight |

### 总体性能字段说明

| 指标 | 说明 |
|-----|------|
| Computing Time | 计算流耗时（含 Flash Attention / Conv / Matmul 等细分） |
| Uncovered Communication Time | 通信未掩盖耗时（含卡间等待） |
| Free Time | 调度耗时 = E2E - 算子 - 通信未掩盖 |
| E2E Time | 端到端总耗时 |
| RDMA/SDMA Bandwidth | 带宽 |

### 算子比对输出（OperatorCompare）

- **Diff Ratio** = GPU 耗时 / NPU 耗时，红色代表劣化
- 通过 Top 统计 → 定位劣化算子 → 查看 kernel 详情找优化点

---

## 八、数据采集准备

| 框架 | 采集方式 | 参考文档 |
|-----|---------|---------|
| PyTorch | Ascend PyTorch Profiler | Ascend PyTorch 调优工具 |
| MindSpore | MindSpore Profiler | MindSpore 调优工具 |
| msProf | msProf 采集 | msProf 文档 |
| msMonitor | msMonitor npu-monitor/nputrace | msMonitor 文档 |

---

## 九、常见问题（FAQ）

**Q: 分析报"文件属主不属于当前用户"？**
A: 使用 `--force` 参数强制执行。

**Q: CSV/JSON/DB 文件过大导致分析失败？**
A: 使用 `--force` 跳过文件大小检查，或分批采集数据。

**Q: advisor 无输出？**
A: 确认 Cann 版本 >= 8.0RC1，MindSpore 场景不支持 Jupyter Notebook 方式。

**Q: compare 算子比对为空？**
A: 确认采集时开启了 `record_shapes=True`；GPU 数据需使用 torch.profiler 采集。

**Q: module_statistic 无模型结构？**
A: 确认已在模型代码中添加 `torch_npu.npu.mstx.range_start/range_end` 打点。

---

## 十、回答格式

当用户咨询 msprof-analyze 相关问题时，请按以下格式作答：

1. **确认目标**：cluster_time_summary / advisor / compare / free_analysis 等分析能力
2. **确认数据源**：PyTorch / MindSpore / msMonitor + 单卡/集群
3. **命令指导**：给出正确的 `msprof-analyze` 命令和关键参数
4. **输出解读**：说明结果文件字段含义和瓶颈定位思路

---

## 附录：源码信息

- **仓库**：`https://gitcode.com/Ascend/msprof-analyze`
- **文档目录**：`docs/zh/`（overview / install_guide / advisor_instruct / cluster_analyse_instruct / compare_tool_instruct / free_analysis_instruct / communication_bottleneck_instruct / module_statistic_instruct 等）
- **版本**：8.2.0 / 8.1.0
- **贡献者**：华为昇腾计算 MindStudio 开发部 / 华为云昇腾云服务 / 2012 网络实验室
