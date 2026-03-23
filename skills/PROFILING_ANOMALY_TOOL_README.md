# Profiling Anomaly Analysis Tool

## 概述

Profiling Anomaly Analysis（性能异常分析）工具是一个深度分析昇腾 NPU Profiling 数据的 MCP 工具，能够自动检测训练过程中的各类性能问题和瓶颈。

该工具基于 `skills/ascend-profiling-anomaly/SKILL.md` 中定义的专业分析方法论，实现了完整的自动化分析流程。

## 功能特性

### 核心能力

- **气泡检测**: 识别 Prelaunch Gap、Tail Gap、Internal Bubbles 等各类时间间隙
- **设备利用率分析**: 评估 AI Core/AI Vector Core 的负载情况
- **迭代稳定性监控**: 检测不同 Step 之间的耗时波动
- **风险分级**: 将性能问题按严重程度分为 low/medium/high/critical四级
- **智能诊断**: 自动生成根因分析和优化建议

### 支持的输入文件

工具会自动读取并分析以下 Profiling 数据文件：

- [`step_trace_time.csv`](../test_data/step_trace_time.csv) - Iteration 时间边界信息（必需）
- [`op_statistic_0.csv`](../test_data/op_statistic_0.csv) - 算子执行统计数据
- [`operator_memory_0.csv`](../test_data/operator_memory_0.csv) - 内存使用统计
- （未来可扩展支持 trace_view.json、communication.json 等）

## 使用方法

### MCP 工具调用

```python
# 通过 MCP 协议调用
analyze_profiling_anomaly(
    profiling_dir="/path/to/profiling/data",
    output_report=True  # 是否导出详细 JSON 报告
)
```

### 参数说明

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `profiling_dir` | str | ✓ | - | Profiling 数据目录路径，应包含 step_trace_time.csv 等文件 |
| `output_report` | bool | ✗ | True | 是否导出详细的 JSON 格式分析报告到 `analyzing_result.json` |

### 返回值示例

```json
{
  "summary": {
    "total_steps": 10,
    "overall_risk_level": "high",
    "key_findings": [
      "Step 3 出现严重的 Tail Gap (占比 45%)",
      "AI Core 利用率低于阈值 (68% < 80%)",
      "连续 3 个 Step 存在 Internal Bubble"
    ],
    "recommendations": [
      "检查 DataLoader 配置，增加 prefetch_factor",
      "优化模型最后几层的计算图调度",
      "考虑使用 Graph Mode 减少 Kernel 启动开销"
    ]
  },
  "step_statistics": {
    "avg_duration_ms": 125.4,
    "risk_distribution": {
      "low": 2,
      "medium": 3,
      "high": 4,
      "critical": 1
    }
  },
  "detailed_report_path": "/path/to/profiling/data/analyzing_result.json"
}
```

## 输出报告结构

当 `output_report=True` 时，会在指定目录下生成 `analyzing_result.json` 文件，包含完整分析结果：

```json
{
  "metadata": {
    "analysis_timestamp": "...",
    "data_source": "/path/to/dir",
    "analyzer_version": "1.0"
  },
  "executive_summary": {...},
  "analyzed_steps": [...],
  "aggregated_metrics": {...},
  "diagnosis_engine_results": {...},
  "optimization_playbook": [...]
}
```

详细内容请参考 [`SKILL.md`](./ascend-profiling-anomaly/SKILL.md#schema---report-schema)。

## 技术实现

### 架构设计

```
┌─────────────────────────────────────┐
│   MCP Server (server.py)            │
│  ┌──────────────────────────────┐   │
│  │ analyze_profiling_anomaly()  │   │
│  └──────────────┬───────────────┘   │
└─────────────────┼───────────────────┘
                  │ calls
┌─────────────────▼───────────────────┐
│   ProfilingAnalyzer                 │
│  (skills/profiling_analyzer.py)     │
│                                     │
│  ┌──────────────────────────────┐   │
│  │ 1. loadData()                │   │
│  │ 2. analyzeSteps()            │   │
│  │ 3. computeMetrics()          │   │
│  │ 4. diagnoseIssues()          │   │
│  │ 5. generateRecommendations() │   │
│  └──────────────────────────────┘   │
└─────────────────────────────────────┘
```

### 关键算法

详见 [`reference_host_gap_branch.py`](./ascend-profiling-anomaly/scripts/reference_host_gap_branch.py) 中的参考实现。

主要步骤：

1. **数据加载与清洗**
   - 解析 CSV 文件，处理缺失值和异常值
   - 统一时间戳单位（秒→毫秒）
   - 过滤无效或重复记录

2. **Step 级别分析**
   ```python
   duration = end_time - start_time
   service_time = sum(kernel_durations)
   
   tail_gap = device_end - last_kernel_end
   internal_bubble = service_time - actual_compute_time
   prelaunch_gap = stream_start - first_kernel_start
   ```

3. **风险评估规则**
   ```python
   if bubble_ratio >= 0.4 or avg_device_load <= 0.5:
       risk = "critical"
   elif bubble_ratio >= 0.25 or avg_device_load <= 0.65:
       risk = "high"
   elif bubble_ratio >= 0.15 or avg_device_load <= 0.75:
       risk = "medium"
   else:
       risk = "low"
   ```

4. **模式识别**
   - 连续性检测：相邻 Step 是否存在相同问题
   - 趋势分析：风险等级是否恶化
   - 关联挖掘：多类问题的共现关系

## 与其他组件集成

### Skills 系统

本工具是 Skills 系统的扩展应用之一，利用了：

- **parser.py**: 结构化数据解析逻辑可复用
- **vector_store.py**: 可用于存储历史 Profiling 数据特征向量
- **retriever.py**: 检索相似的性能问题案例

### Knowledge Base

可将典型问题分析报告存入知识库，供后续查询参考：

```bash
knowledge/
└── profiling_cases/
    ├── tail_gap_severe_case_001.json
    ├── dataloader_bottleneck_case_002.json
    └── ...
```

## 测试验证

使用项目自带的测试数据进行验证：

```bash
cd e:\Bernard\Project\code\github.com\Libotry\ms-mcp

# 运行单元测试
pytest tests/test_profiling_anomaly.py -v

# 或使用实际数据手动测试
python -c "
from skills.profiling_analyzer import ProfilingAnalyzer
from pathlib import Path

analyzer = ProfilingAnalyzer(Path('test_data'))
report = analyzer.analyze()
print(f'Total Steps: {report.total_steps}')
print(f'Overall Risk: {report.overall_risk_level}')
"
```

## 故障排查

### 常见问题

#### FileNotFoundError

确保 `profiling_dir` 路径正确且包含必需的 CSV 文件：

```bash
ls /path/to/profiling/data/*.csv
# 至少应有 step_trace_time.csv
```

#### 空报告或无发现问题

可能原因：
- Profiling 数据采集不完整
- 所有 Step 都很健康（确实没有性能问题）
- 阈值设置过于宽松

可通过调整 [`rulebook.py`](./ascend-profiling-anomaly/references/rulebook.py) 中的判定条件来调优灵敏度。

## 参考资料

- [技能详细说明](../../docs/skills 详细技术方案.md)
- [Skills 使用说明](../../docs/SKILLS_USAGE.md)
- [原始 Skill 规范](./ascend-profiling-anomaly/SKILL.md)
- [参考脚本源码](./ascend-profiling-anomaly/scripts/reference_host_gap_branch.py)
