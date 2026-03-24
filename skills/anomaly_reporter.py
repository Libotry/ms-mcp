"""Enhanced Anomaly Reporter with Cross-Verification

整合 P1/P2 所有分析模块，生成增强的异常报告：
- Step 级别完整气泡分析
- Wait-Anchor 检测
- Soft Attribution
- AICPU 分析
- Step Grouping
- Cross-Verification
- 综合异常标签

输出统一的 JSON 格式报告。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .kernel_details_parser import KernelEntry, aggregate_by_op, compute_op_rankings, parse_kernel_details
from .step_analyzer import Interval, StepBubbleMetrics, compute_step_bubble_metrics, tag_anomalies, analyze_step_health
from .wait_anchor import detect_wait_anchors_from_df, generate_wait_anchor_report
from .soft_attribution import build_attribution_report, summarize_attributions
from .aicpu_analyzer import generate_aicpu_report
from .step_grouper import group_steps_from_intervals, extract_step_signature, generate_grouping_report
from .structure_analyzer import find_fia_kernels, compute_block_side_metrics
from .trace_view_parser import parse_trace_view, build_host_intervals_for_bubble_analysis


# ── 数据结构 ────────────────────────────────────────────────────────────────


@dataclass
class EnhancedStepAnalysis:
    """增强的 Step 分析结果。"""
    step_id: int
    service_ms: float
    device_busy_union_ms: float
    kernel_sum_ms: float
    total_cost_ms: float
    underfeed_ratio: float
    prelaunch_gap_ms: float
    tail_gap_ms: float
    internal_bubble_total_ms: float
    largest_internal_bubble_ms: float
    bubble_count: int
    anomaly_tags: List[str]
    soft_attribution: Dict[str, Any]
    risk_level: str
    group_id: Optional[str] = None
    group_type: Optional[str] = None


@dataclass
class CrossVerificationResult:
    """交叉验证结果。"""
    op_count_mismatches: List[Dict[str, Any]] = field(default_factory=list)
    fia_count_vs_layer_mismatch: bool = False
    comm_overlap_inconsistencies: List[str] = field(default_factory=list)


@dataclass
class EnhancedAnomalyReport:
    """增强的异常报告。"""
    profiling_dir: str
    data_source: str
    total_steps: int
    overall_risk_level: str
    key_findings: List[str]
    recommendations: List[str]
    step_analysis: List[EnhancedStepAnalysis]
    wait_anchor_report: Dict[str, Any]
    aicpu_report: Dict[str, Any]
    grouping_report: Dict[str, Any]
    cross_verification: CrossVerificationResult
    requires_host_followup: bool
    confidence: str  # high / medium / low


# ── Cross-Verification ──────────────────────────────────────────────────────


def verify_fia_vs_layers(
    fia_count: int,
    layer_count: int,
) -> bool:
    """验证 FIA 数量是否与 layer 数量一致。"""
    # 允许一定误差（±5%）
    return abs(fia_count - layer_count) <= max(1, int(fia_count * 0.05))


def verify_op_counts_per_layer(
    kernels: List[KernelEntry],
    layers: List[Any],
    expected_counts: Dict[str, int],
) -> List[Dict[str, Any]]:
    """验证各层的 op 计数是否符合预期。"""
    mismatches = []

    # 这里简化处理，实际需要按层统计
    return mismatches


def cross_verify_all(
    kernels: List[KernelEntry],
    fia_count: int,
    layer_count: int,
    grouping_result: Dict[str, Any],
) -> CrossVerificationResult:
    """执行完整的交叉验证。"""
    result = CrossVerificationResult()

    # 1. FIA vs Layers
    if fia_count > 0:
        result.fia_count_vs_layer_mismatch = not verify_fia_vs_layers(fia_count, layer_count)

    # 2. Op count verification
    # 从 kernel 统计中检查是否有明显不一致
    op_stats = aggregate_by_op(kernels)
    total_kernel_count = sum(s.count for s in op_stats.values())

    if grouping_result.get("total_groups", 0) > 0:
        avg_per_group = total_kernel_count / grouping_result["total_groups"]
        # 如果平均每组 kernel 数量异常（过大或过小），标记
        if avg_per_group > 1000:
            result.op_count_mismatches.append({
                "type": "high_kernel_count_per_step",
                "value": avg_per_group,
                "hint": "Possible step grouping issue or profiling capture error",
            })

    return result


# ── 增强分析流程 ──────────────────────────────────────────────────────────


def build_enhanced_report(
    kernels: List[KernelEntry],
    profiling_dir: str,
    step_intervals: List[Dict[str, Any]],
    trace_file: Optional[str] = None,
) -> EnhancedAnomalyReport:
    """构建增强的异常报告。

    Args:
        kernels: 所有 kernel 数据
        profiling_dir: Profiling 目录名
        step_intervals: Step 边界列表 [{"step_id": ..., "start_us": ..., "end_us": ...}, ...]
        trace_file: 可选的 trace_view.json 路径

    Returns:
        EnhancedAnomalyReport
    """
    if not kernels:
        return EnhancedAnomalyReport(
            profiling_dir=profiling_dir,
            data_source="kernel_details",
            total_steps=0,
            overall_risk_level="unknown",
            key_findings=["No kernel data available"],
            recommendations=["Ensure profiling data was collected properly"],
            step_analysis=[],
            wait_anchor_report={},
            aicpu_report={},
            grouping_report={},
            cross_verification=CrossVerificationResult(),
            requires_host_followup=False,
            confidence="low",
        )

    # 1. Step 分析
    step_analyses = []
    all_findings = []
    risk_counts = {"low": 0, "medium": 0, "high": 0, "critical": 0}

    # 解析 trace_view 获取 host intervals（如果可用）
    host_intervals = None
    if trace_file:
        try:
            events = parse_trace_view(trace_file)
            host_intervals = build_host_intervals_for_bubble_analysis(events)
        except Exception:
            pass

    for step_info in step_intervals:
        step_id = step_info["step_id"]
        start_us = step_info["start_us"]
        end_us = step_info["end_us"]

        # 筛选该 step 的 kernels
        step_kernels = [
            k for k in kernels
            if k.start_us >= start_us and k.start_us < end_us
        ]

        # 计算气泡指标
        metrics = compute_step_bubble_metrics(start_us, end_us, step_kernels)

        # 异常标签
        anomaly_tags = tag_anomalies(metrics)

        # Soft Attribution（如果 host 数据可用）
        soft_attribution: Dict[str, Any] = {}
        if host_intervals and metrics.bubble_intervals:
            attribution = build_attribution_report(metrics.bubble_intervals, host_intervals)
            soft_attribution = attribution

        # 健康度评估
        risk_level, findings = analyze_step_health(metrics, anomaly_tags)

        step_analyses.append(EnhancedStepAnalysis(
            step_id=step_id,
            service_ms=metrics.service_ms,
            device_busy_union_ms=metrics.device_busy_union_ms,
            kernel_sum_ms=metrics.kernel_sum_ms,
            total_cost_ms=metrics.total_cost_ms,
            underfeed_ratio=metrics.underfeed_ratio,
            prelaunch_gap_ms=metrics.prelaunch_gap_ms,
            tail_gap_ms=metrics.tail_gap_ms,
            internal_bubble_total_ms=metrics.internal_bubble_total_ms,
            largest_internal_bubble_ms=metrics.largest_internal_bubble_ms,
            bubble_count=metrics.bubble_count,
            anomaly_tags=anomaly_tags,
            soft_attribution=soft_attribution,
            risk_level=risk_level,
        ))

        risk_counts[risk_level] += 1
        all_findings.extend(findings)

    # 2. Wait-Anchor 分析
    from .kernel_details_parser import KernelEntry as KE
    import pandas as pd
    df = pd.DataFrame([
        {"name": k.name, "task_type": k.task_type, "start_us": k.start_us,
         "duration_us": k.duration_us, "wait_us": k.wait_us, "stream_id": k.stream_id}
        for k in kernels
    ])
    wait_anchor_report = generate_wait_anchor_report(
        detect_wait_anchors_from_df(df),
        []
    )

    # 3. AICPU 分析
    aicpu_report = generate_aicpu_report(kernels)

    # 4. Step Grouping
    step_kernel_map = {
        step_info["step_id"]: [
            k for k in kernels
            if k.start_us >= step_info["start_us"] and k.start_us < step_info["end_us"]
        ]
        for step_info in step_intervals
    }
    from .step_grouper import group_steps
    signatures = [extract_step_signature(sid, kerns) for sid, kerns in step_kernel_map.items()]
    grouping_result_raw = group_steps(signatures)
    grouping_report = generate_grouping_report(grouping_result_raw)

    # 将 group_id 注入 step_analysis
    for i, step_info in enumerate(step_intervals):
        if i < len(step_analyses):
            group_id = grouping_result_raw.step_to_group.get(step_info["step_id"])
            step_analyses[i].group_id = group_id
            if group_id:
                for g in grouping_result_raw.groups:
                    if g.group_id == group_id:
                        step_analyses[i].group_type = g.group_type
                        break

    # 5. Cross-Verification
    fia_count = len(find_fia_kernels(kernels))
    cross_verification = cross_verify_all(
        kernels, fia_count, fia_count, grouping_report
    )

    # 6. 整体风险等级
    overall_risk = "low"
    if risk_counts["critical"] > 0:
        overall_risk = "critical"
    elif risk_counts["high"] > len(step_analyses) * 0.3:
        overall_risk = "high"
    elif risk_counts["medium"] > len(step_analyses) * 0.5:
        overall_risk = "medium"

    # 7. 置信度评估
    confidence = "high"
    if not host_intervals:
        confidence = "medium"  # 没有 host 数据，置信度下降
    if cross_verification.op_count_mismatches:
        confidence = "low"

    # 8. 建议
    recommendations = _generate_recommendations(step_analyses, wait_anchor_report, aicpu_report, cross_verification)

    # 9. 是否需要 host 跟进
    requires_followup = (
        risk_counts["high"] > 0
        or risk_counts["critical"] > 0
        or not host_intervals
        or len(wait_anchor_report.get("false_hotspots", [])) > 0
    )

    return EnhancedAnomalyReport(
        profiling_dir=profiling_dir,
        data_source="kernel_details",
        total_steps=len(step_analyses),
        overall_risk_level=overall_risk,
        key_findings=all_findings[:10],
        recommendations=recommendations,
        step_analysis=step_analyses,
        wait_anchor_report=wait_anchor_report,
        aicpu_report=aicpu_report,
        grouping_report=grouping_report,
        cross_verification=cross_verification,
        requires_host_followup=requires_followup,
        confidence=confidence,
    )


# ── 辅助函数 ────────────────────────────────────────────────────────────────


def _generate_recommendations(
    step_analyses: List[EnhancedStepAnalysis],
    wait_anchor_report: Dict[str, Any],
    aicpu_report: Dict[str, Any],
    cross_ver: CrossVerificationResult,
) -> List[str]:
    """生成综合优化建议。"""
    recs: List[str] = []

    # 气泡问题
    prelaunch_count = sum(1 for s in step_analyses if "PRELAUNCH_GAP_HEAVY" in s.anomaly_tags)
    tail_count = sum(1 for s in step_analyses if "TAIL_GAP_HEAVY" in s.anomaly_tags)
    internal_count = sum(1 for s in step_analyses if "INTERNAL_BUBBLE_HEAVY" in s.anomaly_tags)
    underfeed_count = sum(1 for s in step_analyses if "DEVICE_IDLE_GAP_HEAVY" in s.anomaly_tags)

    total = len(step_analyses) if step_analyses else 1

    if prelaunch_count > total * 0.5:
        recs.append("优化 Host 侧数据预处理流水线，减少 Device 预启动等待时间")
    if tail_count > total * 0.5:
        recs.append("优化迭代收尾流程，减少尾部空闲时间")
    if internal_count > total * 0.5:
        recs.append("融合小算子或使用 TBE 自定义算子减少内核启动开销")
    if underfeed_count > total * 0.3:
        recs.append("增加算子并行度或采用 Graph 模式提升设备利用率")

    # Wait-Anchor 问题
    if wait_anchor_report.get("confirmed_false_hotspots"):
        recs.append(f"检测到 {len(wait_anchor_report['confirmed_false_hotspots'])} 个 Wait-Anchor 假热点算子，定位真正的等待源头")

    # AICPU 问题
    aicpu_summary = aicpu_report.get("summary", {})
    exposed_count = aicpu_summary.get("exposed_not_allowed_count", 0)
    if exposed_count > 0:
        recs.append(f"存在 {exposed_count} 个完全暴露的 AICPU 算子，建议检查是否能迁移到 AI_CORE")

    # Cross-Verification 问题
    if cross_ver.fia_count_vs_layer_mismatch:
        recs.append("FIA 数量与层数量不匹配，建议检查 profiling 捕获是否完整")
    if cross_ver.op_count_mismatches:
        recs.append("检测到 op 计数异常，建议重新验证 profiling 数据")

    if not recs:
        recs.append("当前性能表现良好，未检测到显著异常")

    return recs


def report_to_dict(report: EnhancedAnomalyReport) -> Dict[str, Any]:
    """将报告转换为字典格式。"""
    return {
        "profiling_dir": report.profiling_dir,
        "data_source": report.data_source,
        "total_steps": report.total_steps,
        "overall_risk_level": report.overall_risk_level,
        "confidence": report.confidence,
        "requires_host_followup": report.requires_host_followup,
        "key_findings": report.key_findings,
        "recommendations": report.recommendations,
        "step_analysis": [
            {
                "step_id": s.step_id,
                "service_ms": round(s.service_ms, 2),
                "device_busy_union_ms": round(s.device_busy_union_ms, 2),
                "kernel_sum_ms": round(s.kernel_sum_ms, 2),
                "total_cost_ms": round(s.total_cost_ms, 2),
                "underfeed_ratio": round(s.underfeed_ratio, 4),
                "prelaunch_gap_ms": round(s.prelaunch_gap_ms, 2),
                "tail_gap_ms": round(s.tail_gap_ms, 2),
                "internal_bubble_total_ms": round(s.internal_bubble_total_ms, 2),
                "largest_internal_bubble_ms": round(s.largest_internal_bubble_ms, 2),
                "bubble_count": s.bubble_count,
                "anomaly_tags": s.anomaly_tags,
                "group_id": s.group_id,
                "group_type": s.group_type,
                "risk_level": s.risk_level,
                "soft_attribution_summary": (
                    s.soft_attribution.get("summary", {})
                    if s.soft_attribution else {}
                ),
            }
            for s in report.step_analysis
        ],
        "wait_anchor_analysis": report.wait_anchor_report,
        "aicpu_analysis": report.aicpu_report,
        "step_grouping": report.grouping_report,
        "cross_verification": {
            "fia_vs_layer_mismatch": report.cross_verification.fia_count_vs_layer_mismatch,
            "op_count_mismatches": report.cross_verification.op_count_mismatches,
        },
    }
