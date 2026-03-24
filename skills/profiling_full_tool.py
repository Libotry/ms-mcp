"""Profiling Full Analysis MCP Tool

统一的 Profiling 深度分析 MCP Tool（P1/P2 完整版）：
- 自动检测可用数据源（kernel_details > op_statistic > step_trace）
- 执行完整 Step 级别气泡分析
- Wait-Anchor 假热点检测
- Soft Attribution（根因分析）
- AICPU masked_ratio 分类
- Step Grouping（forward/backward/iterationrefresh）
- Structure/Layer 分析 + Block/Side 四时钟视角
- Model Architecture Report 生成（10章节 Markdown）
- Cross-Verification
- 输出统一格式的结构化结果
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def register_profiling_full_tool(mcp):
    """向 MCP 实例注册统一 Profiling 分析工具。"""

    @mcp.tool()
    def analyze_profiling_full(
        profiling_dir: str,
        top_n: int = 10,
        output_report: bool = True,
        generate_arch_report: bool = True,
        use_skill_fallback: bool = True,
    ) -> str:
        """深度分析昇腾 Profiling 数据，返回完整的性能分析结果。

        自动检测可用数据源并执行综合分析（P1/P2 完整功能）：
        1. Step 级别气泡分析（prelaunch gap / tail gap / internal bubbles / underfeed）
        2. Wait-Anchor 假热点检测（识别 total_cost 排名虚高的算子）
        3. Soft Attribution 根因分析（5类标签：possible_sync_or_h2d / possible_comm_wait 等）
        4. AICPU masked_ratio 分类（AICPU_MASKED_BUT_UNDESIRABLE / PARTIALLY_EXPOSED / EXPOSED_NOT_ALLOWED）
        5. Step Grouping（区分 forward / backward / iterationrefresh）
        6. 四时钟视角（wall / busy_union / kernel_sum / total_cost）
        7. 异常标签（DEVICE_IDLE_GAP_HEAVY / PRELAUNCH_GAP_HEAVY / TAIL_GAP_HEAVY 等）
        8. 算子排名对比（by total_cost vs by duration）
        9. Cross-Verification（验证数据一致性）
        10. Model Architecture Report（10章节 Markdown 报告，可选）

        ⚠️ **自动分析失败时**：默认回退到 SKILL.md 模式，返回完整的方法论文档，
        让 LLM 能够借助文档对数据进行人工分析，无需人工干预。

        Args:
            profiling_dir: Profiling 数据目录路径
            top_n: 返回 Top-N 高耗时算子数量，默认 10
            output_report: 是否导出详细 JSON 报告到 profiling_full_result.json，默认 True
            generate_arch_report: 是否生成 Model Architecture Markdown 报告，默认 True
            use_skill_fallback: 自动分析失败时是否回退到 SKILL.md 模式（默认 True）

        Returns:
            JSON 格式的统一分析结果，包含：
            - summary: 总体风险评估和关键发现
            - step_analysis: 每个 Step 的详细气泡指标 + Soft Attribution
            - wait_anchor_analysis: Wait-Anchor 假热点分析
            - aicpu_analysis: AICPU masked_ratio 分类
            - step_grouping: Step 类型分组结果
            - cross_verification: 数据一致性验证结果
            - risk_distribution: 风险等级分布统计
            - requires_host_followup: 是否需要进一步收集 host 侧数据
            - architecture_report_path: Model Architecture 报告路径（如果生成）

            当自动分析失败且 use_skill_fallback=True 时：
            返回完整的 SKILL.md 方法论文档，包含 LLM 人工分析指南
        """
        return _analyze_profiling_full_impl(
            profiling_dir, top_n, output_report, generate_arch_report, use_skill_fallback
        )

    return analyze_profiling_full


# ── 内部实现 ───────────────────────────────────────────────────────────────


def _get_skill_fallback_content(profiling_dir: str) -> str:
    """获取 SKILL.md 回退内容，供 LLM 人工分析使用。

    当自动分析失败时，返回完整的方法论文档，
    让 LLM 能够借助文档对数据进行人工分析。
    """
    skill_path = Path(__file__).parent / "ascend-profiling-anomaly" / "SKILL.md"
    rulebook_path = Path(__file__).parent / "ascend-profiling-anomaly" / "references" / "rulebook.md"

    skill_content = ""
    if skill_path.exists():
        skill_content = skill_path.read_text(encoding="utf-8")

    rulebook_content = ""
    if rulebook_path.exists():
        rulebook_content = rulebook_path.read_text(encoding="utf-8")

    return f"""# 自动分析失败 - SKILL.md 回退模式

## 错误原因

无法自动解析 Profiling 数据文件。可能的原因：
1. 文件格式与预期不符
2. 列名与标准昇腾格式不一致
3. 缺少必要的列字段

## 支持的数据文件

| 文件名 | 优先级 | 说明 |
|--------|--------|------|
| `kernel_details*.csv` | P0 | 算子级详细性能数据（首选） |
| `op_statistic*.csv` | P1 | 算子级聚合统计 |
| `step_trace*.csv` | P2 | Step 级别 timeline |
| `trace_view.json` | 可选 | Host 侧事件（用于根因分析） |

## 预期 CSV 列名（kernel_details）

| 标准列名 | 说明 |
|----------|------|
| `Start Time(us)` | 启动时间（微秒） |
| `Duration(us)` | 执行时长（微秒） |
| `Wait Time(us)` | 等待时长（微秒） |
| `Task Type` | 任务类型（AI_CORE/AI_CPU/HCCL等） |
| `Stream ID` | 流 ID |
| `Name` | 算子名称 |

---

## 📋 LLM 人工分析指南

请借助以下方法论文档，对 **{profiling_dir}** 目录下的 Profiling 数据进行人工分析。

---

# SKILL.md 方法论

{skill_content}

---

# Rulebook.md 阈值规则

{rulebook_content}

---

## 快速分析步骤

### Step 1: 检测数据文件
列出目录下的所有 CSV 文件：
```
kernel_details*.csv, op_statistic*.csv, step_trace*.csv
```

### Step 2: 解析数据
1. 读取 kernel_details*.csv
2. 识别列名映射关系
3. 按 Start Time 排序

### Step 3: 识别 Step 边界
查找 `ProfilerStep#N` 或 `Iteration#N` 标记

### Step 4: 计算气泡指标
对于每个 Step：
- `underfeed_ratio = (step_end - step_start - busy_union) / (step_end - step_start)`
- `prelaunch_gap = first_kernel_start - step_start`
- `tail_gap = step_end - last_kernel_end`
- `internal_bubbles = gaps between merged kernel intervals`

### Step 5: 应用异常标签
根据 rulebook.md 阈值：
- `underfeed_ratio >= 0.30` → DEVICE_IDLE_GAP_HEAVY
- `prelaunch_gap_ms >= max(1.0, 0.10 * service_ms)` → PRELAUNCH_GAP_HEAVY
- `tail_gap_ms >= max(1.0, 0.10 * service_ms)` → TAIL_GAP_HEAVY

### Step 6: Wait-Anchor 检测
对于每个算子：
- `wait_ratio = wait_us / (duration_us + wait_us)`
- `wait_ratio > 0.95` 且 `duration_us < 10.0` 且排名靠前 → 假热点

### Step 7: 生成报告
按照 SKILL.md 要求的输出格式生成分析结果。
"""


def _analyze_profiling_full_impl(
    profiling_dir: str,
    top_n: int = 10,
    output_report: bool = True,
    generate_arch_report: bool = True,
    use_skill_fallback: bool = True,
) -> str:
    """统一分析实现。

    Args:
        profiling_dir: Profiling 数据目录
        top_n: 返回 Top-N 算子数量
        output_report: 是否导出 JSON 报告
        generate_arch_report: 是否生成架构报告
        use_skill_fallback: 自动分析失败时是否回退到 SKILL.md 模式
    """
    dir_p = Path(profiling_dir)

    if not dir_p.exists():
        return json.dumps(
            {"error": f"目录不存在: {profiling_dir}"},
            ensure_ascii=False,
            indent=2,
        )

    # 尝试多种数据源
    result = _try_kernel_details_full_analysis(
        dir_p, top_n, generate_arch_report
    )
    if result is not None and "error" not in result:
        if output_report:
            _export_report(dir_p, result)
        return json.dumps(result, ensure_ascii=False, indent=2)

    # 回退到 op_statistic 分析
    result = _try_op_statistic_analysis(dir_p, top_n)
    if result is not None and "error" not in result:
        if output_report:
            _export_report(dir_p, result)
        return json.dumps(result, ensure_ascii=False, indent=2)

    # 最后回退到 step_trace
    result = _try_step_trace_analysis(dir_p)
    if result is not None and "error" not in result:
        if output_report:
            _export_report(dir_p, result)
        return json.dumps(result, ensure_ascii=False, indent=2)

    # 所有自动分析都失败 - 返回 SKILL.md 回退内容
    if use_skill_fallback:
        return _get_skill_fallback_content(profiling_dir)

    return json.dumps(
        {
            "error": f"未找到可分析的 Profiling 数据文件: {profiling_dir}",
            "supported_files": [
                "kernel_details*.csv",
                "op_statistic*.csv",
                "step_trace*.csv",
            ],
            "hint": "尝试设置 use_skill_fallback=True 获取 SKILL.md 分析指南",
        },
        ensure_ascii=False,
        indent=2,
    )


def _try_kernel_details_full_analysis(
    dir_p: Path,
    top_n: int,
    generate_arch_report: bool,
) -> Optional[Dict[str, Any]]:
    """使用 kernel_details*.csv 进行 P1/P2 完整分析。"""
    from .kernel_details_parser import parse_kernel_details, aggregate_by_op, KernelEntry
    from .step_analyzer import StepAnalyzer
    from .wait_anchor import detect_wait_anchors_from_op_stats, analyze_ranking_discrepancies, generate_wait_anchor_report
    from .aicpu_analyzer import generate_aicpu_report
    from .step_grouper import group_steps, extract_step_signature, generate_grouping_report
    from .anomaly_reporter import build_enhanced_report, report_to_dict
    from .arch_report import generate_report_from_directory
    from .trace_view_parser import parse_trace_view, build_host_intervals_for_bubble_analysis

    kernel_files = sorted(dir_p.glob("kernel_details*.csv"))
    if not kernel_files:
        return None

    try:
        kernel_file = kernel_files[0]
        kernel_df = parse_kernel_details(str(kernel_file))

        if kernel_df.empty:
            return None

        # Step 边界检测
        step_bounds = StepAnalyzer._detect_step_bounds(dir_p, kernel_df)
        if not step_bounds:
            return None

        # 构建 step_intervals
        step_intervals = [
            {"step_id": b.step_id, "start_us": b.start_us, "end_us": b.end_us}
            for b in step_bounds
        ]

        # 转换为 KernelEntry 列表
        kernels = _df_to_kernel_entries(kernel_df)

        # 查找 trace_view.json（用于 Soft Attribution）
        trace_file = dir_p / "trace_view.json"
        trace_file = trace_file if trace_file.exists() else None

        # 构建增强报告
        report = build_enhanced_report(
            kernels=kernels,
            profiling_dir=str(dir_p),
            step_intervals=step_intervals,
            trace_file=str(trace_file) if trace_file else None,
        )

        result = report_to_dict(report)

        # 补充 top_ops
        op_stats = aggregate_by_op(kernel_df)
        by_cost, by_duration = _compute_rankings(op_stats)

        result["top_ops_by_cost"] = [
            {
                "op_name": name,
                "task_type": stats.task_type,
                "count": stats.count,
                "total_cost_us": round(stats.total_duration_us + stats.total_wait_us, 2),
                "total_duration_us": round(stats.total_duration_us, 2),
                "total_wait_us": round(stats.total_wait_us, 2),
            }
            for name, stats in by_cost[:top_n]
        ]
        result["top_ops_by_duration"] = [
            {
                "op_name": name,
                "task_type": stats.task_type,
                "count": stats.count,
                "total_duration_us": round(stats.total_duration_us, 2),
                "avg_duration_us": round(
                    stats.total_duration_us / stats.count, 2
                ) if stats.count > 0 else 0,
            }
            for name, stats in by_duration[:top_n]
        ]

        # 生成 Model Architecture Report
        arch_report_path = None
        if generate_arch_report:
            try:
                _, arch_report_path = generate_report_from_directory(dir_p, dir_p)
                if arch_report_path:
                    result["architecture_report_path"] = str(arch_report_path)
            except Exception:
                pass

        return result

    except Exception as e:
        return {"error": f"kernel_details 完整分析失败: {type(e).__name__}: {e}"}


def _df_to_kernel_entries(df) -> List:
    """将 DataFrame 转换为 KernelEntry 列表。"""
    from .kernel_details_parser import KernelEntry
    entries = []
    for _, row in df.iterrows():
        try:
            entries.append(KernelEntry(
                name=str(row.get("name", "")),
                task_type=str(row.get("task_type", "")),
                start_us=float(row.get("start_us", 0)),
                duration_us=float(row.get("duration_us", 0)),
                wait_us=float(row.get("wait_us", 0)),
                stream_id=int(row.get("stream_id", 0)),
            ))
        except (ValueError, TypeError):
            continue
    return entries


def _compute_rankings(op_stats):
    """计算算子排名。"""
    by_cost = sorted(
        op_stats.items(),
        key=lambda x: x[1].total_duration_us + x[1].total_wait_us,
        reverse=True,
    )
    by_duration = sorted(
        op_stats.items(),
        key=lambda x: x[1].total_duration_us,
        reverse=True,
    )
    return by_cost, by_duration


def _try_op_statistic_analysis(dir_p: Path, top_n: int) -> Optional[Dict[str, Any]]:
    """尝试使用 op_statistic*.csv 进行分析。"""
    from analyzer import analyze_op_statistic

    op_stat_files = sorted(dir_p.glob("op_statistic*.csv"))
    if not op_stat_files:
        return None

    try:
        result = analyze_op_statistic(str(op_stat_files[0]))

        if "error" in result:
            return None

        return {
            "profiling_dir": str(dir_p),
            "data_source": "op_statistic",
            "file": op_stat_files[0].name,
            "summary": {
                "total_ops": result.get("total_ops", 0),
                "total_time_us": result.get("total_time_us", 0),
                "key_findings": [
                    f.get("type", "") + ": " + f.get("op_type", f.get("op_name", ""))
                    for f in result.get("findings", [])
                ],
                "recommendations": _recommendations_from_op_stat(result),
            },
            "op_stats": result.get("op_stats", [])[:top_n],
            "findings": result.get("findings", []),
            "risk_distribution": _estimate_risk_from_op_stat(result),
            "requires_host_followup": False,
        }

    except Exception as e:
        return {"error": f"op_statistic 分析失败: {type(e).__name__}: {e}"}


def _try_step_trace_analysis(dir_p: Path) -> Optional[Dict[str, Any]]:
    """尝试使用 step_trace*.csv 进行分析。"""
    from analyzer import analyze_step_trace

    step_trace_files = sorted(dir_p.glob("step_trace*.csv"))
    if not step_trace_files:
        return None

    try:
        result = analyze_step_trace(str(step_trace_files[0]))

        if "error" in result:
            return None

        return {
            "profiling_dir": str(dir_p),
            "data_source": "step_trace",
            "file": step_trace_files[0].name,
            "summary": {
                "total_steps": result.get("total_steps", 0),
                "key_findings": [
                    f.get("type", "") for f in result.get("findings", [])
                ],
                "recommendations": _recommendations_from_step_trace(result),
            },
            "step_times": result.get("steps_detail", []),
            "findings": result.get("findings", []),
            "risk_distribution": _estimate_risk_from_step_trace(result),
            "requires_host_followup": False,
        }

    except Exception as e:
        return {"error": f"step_trace 分析失败: {type(e).__name__}: {e}"}


def _export_report(dir_p: Path, result: Dict[str, Any]) -> Path:
    """导出详细 JSON 报告。"""
    report_path = dir_p / "profiling_full_result.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return report_path


# ── 辅助函数 ─────────────────────────────────────────────────────────────


def _recommendations_from_op_stat(result: Dict[str, Any]) -> List[str]:
    """从 op_statistic 结果生成建议。"""
    recs: List[str] = []
    for finding in result.get("findings", []):
        ftype = finding.get("type", "")
        if ftype == "high_frequency_op":
            recs.append(f"高频算子 {finding.get('op_type')} 调用次数过多，考虑算子融合")
        elif ftype == "long_tail_op":
            recs.append(
                f"算子 {finding.get('op_type')} 耗时抖动大（max/avg={finding.get('max_avg_ratio')}），检查数据依赖"
            )
    if not recs:
        recs.append("当前算子执行无明显异常")
    return recs


def _recommendations_from_step_trace(result: Dict[str, Any]) -> List[str]:
    """从 step_trace 结果生成建议。"""
    recs: List[str] = []
    for finding in result.get("findings", []):
        ftype = finding.get("type", "")
        if ftype == "high_free_ratio":
            recs.append("设备空闲占比过高，增加并行任务或优化调度")
        elif ftype == "low_overlap_ratio":
            recs.append("通信计算重叠率低，优化通信调度时机")
        elif ftype == "high_bubble_ratio":
            recs.append("流水线气泡比例过高，检查同步点和数据依赖")
        elif ftype == "unstable_iteration":
            recs.append("迭代耗时不稳定，检查数据加载和预处理流程")
        elif ftype == "high_data_aug_ratio":
            recs.append("数据增强占比过高，优化数据管道或增加预取")
    if not recs:
        recs.append("当前迭代执行无明显异常")
    return recs


def _estimate_risk_from_op_stat(result: Dict[str, Any]) -> Dict[str, int]:
    """从 op_statistic 结果估算风险分布。"""
    findings = result.get("findings", [])
    high_count = len(
        [
            f
            for f in findings
            if f.get("type") in ("high_frequency_op", "long_tail_op")
        ]
    )
    return {
        "low": max(0, 10 - high_count),
        "medium": min(high_count, 5),
        "high": min(max(0, high_count - 5), 3),
        "critical": 0,
    }


def _estimate_risk_from_step_trace(result: Dict[str, Any]) -> Dict[str, int]:
    """从 step_trace 结果估算风险分布。"""
    findings = result.get("findings", [])
    high_count = len(findings)
    return {
        "low": max(0, 10 - high_count),
        "medium": min(high_count, 5),
        "high": min(max(0, high_count - 5), 3),
        "critical": 0,
    }
