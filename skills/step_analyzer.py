"""Step 级别完整气泡检测分析器

基于 kernel_details.csv 提供的数据，执行完整的 Step 级别气泡分析：
- 四时钟视角（wall / busy_union / kernel_sum / total_cost）
- 设备欠载（underfeed）检测
- 预启动间隙 / 尾部间隙 / 内部气泡分析
- 异常标签（anomaly tags）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

import pandas as pd

from .kernel_details_parser import (
    KernelEntry,
    OpStats,
    StepBound,
    aggregate_by_op,
    build_kernel_intervals,
    compute_op_rankings,
    parse_kernel_details,
)
from .skill_parser import get_default_thresholds


# ── Interval 核心（从 reference_host_gap_branch.py 复用） ─────────────────────


@dataclass
class Interval:
    """时间区间表示。"""
    start_us: float
    end_us: float

    @property
    def dur_us(self) -> float:
        """返回区间持续时间 (微秒)。"""
        return max(0.0, self.end_us - self.start_us)


def merge_intervals(intervals: Sequence[Interval]) -> List[Interval]:
    """合并重叠的时间区间。"""
    items = sorted(
        (i for i in intervals if i.end_us > i.start_us),
        key=lambda x: (x.start_us, x.end_us),
    )
    if not items:
        return []

    merged: List[Interval] = [Interval(items[0].start_us, items[0].end_us)]
    for cur in items[1:]:
        last = merged[-1]
        if cur.start_us <= last.end_us:
            last.end_us = max(last.end_us, cur.end_us)
        else:
            merged.append(Interval(cur.start_us, cur.end_us))

    return merged


def interval_union_us(intervals: Sequence[Interval]) -> float:
    """计算区间并集的总时长。"""
    return sum(i.dur_us for i in merge_intervals(intervals))


# ── 数据结构 ────────────────────────────────────────────────────────────────


@dataclass
class StepBubbleMetrics:
    """Step 气泡指标（四时钟视角）。"""
    service_ms: float = 0.0
    device_busy_union_ms: float = 0.0
    kernel_sum_ms: float = 0.0
    total_cost_ms: float = 0.0
    underfeed_ms: float = 0.0
    underfeed_ratio: float = 0.0
    prelaunch_gap_ms: float = 0.0
    tail_gap_ms: float = 0.0
    internal_bubble_total_ms: float = 0.0
    largest_internal_bubble_ms: float = 0.0
    bubble_count: int = 0
    bubble_intervals: List[Interval] = field(default_factory=list)
    anomaly_tags: List[str] = field(default_factory=list)


@dataclass
class StepAnalysis:
    """单步分析结果。"""
    step_id: int
    step_start_us: float
    step_end_us: float
    duration_ms: float
    bubble_metrics: StepBubbleMetrics
    kernel_count: int = 0
    ai_core_count: int = 0
    ai_cpu_count: int = 0
    hccl_count: int = 0
    distinct_streams: Set[int] = field(default_factory=set)
    findings: List[str] = field(default_factory=list)
    risk_level: str = "low"  # low, medium, high, critical


# ── 气泡指标计算 ────────────────────────────────────────────────────────────


def compute_step_bubble_metrics(
    step_start_us: float,
    step_end_us: float,
    device_intervals: List[KernelEntry],
) -> StepBubbleMetrics:
    """计算单步的气泡指标（含四时钟视角）。"""
    service_us = max(0.0, step_end_us - step_start_us)

    if not device_intervals:
        return StepBubbleMetrics(
            service_ms=service_us / 1000.0,
            underfeed_ms=service_us / 1000.0,
            underfeed_ratio=1.0 if service_us > 0 else 0.0,
        )

    # 转换为 Interval 用于合并
    intervals = [
        Interval(e.start_us, e.start_us + e.duration_us)
        for e in device_intervals
    ]
    merged = merge_intervals(intervals)

    # 四时钟视角
    kernel_sum_us = sum(e.duration_us for e in device_intervals)
    total_cost_us = sum(e.total_cost_us for e in device_intervals)

    busy_union_us = sum(seg.dur_us for seg in merged)
    prelaunch_us = max(0.0, merged[0].start_us - step_start_us)
    tail_us = max(0.0, step_end_us - merged[-1].end_us)

    # 内部气泡
    bubbles: List[Interval] = []
    for left, right in zip(merged[:-1], merged[1:]):
        if right.start_us > left.end_us:
            bubbles.append(Interval(left.end_us, right.start_us))

    bubble_total_us = sum(b.dur_us for b in bubbles)
    largest_bubble_us = max((b.dur_us for b in bubbles), default=0.0)
    underfeed_us = max(0.0, service_us - busy_union_us)
    underfeed_ratio = underfeed_us / service_us if service_us > 0 else 0.0

    return StepBubbleMetrics(
        service_ms=service_us / 1000.0,
        device_busy_union_ms=busy_union_us / 1000.0,
        kernel_sum_ms=kernel_sum_us / 1000.0,
        total_cost_ms=total_cost_us / 1000.0,
        underfeed_ms=underfeed_us / 1000.0,
        underfeed_ratio=underfeed_ratio,
        prelaunch_gap_ms=prelaunch_us / 1000.0,
        tail_gap_ms=tail_us / 1000.0,
        internal_bubble_total_ms=bubble_total_us / 1000.0,
        largest_internal_bubble_ms=largest_bubble_us / 1000.0,
        bubble_count=len(bubbles),
        bubble_intervals=bubbles,
    )


# ── 异常标签 ────────────────────────────────────────────────────────────────


def tag_anomalies(metrics: StepBubbleMetrics) -> List[str]:
    """基于 rulebook.md 阈值对气泡指标打标签。"""
    tags: List[str] = []
    thresholds = get_default_thresholds()
    service_ms = metrics.service_ms

    # 2.2 High-severity bubble thresholds
    if metrics.underfeed_ratio >= thresholds.get("underfeed_heavy", 0.30):
        tags.append("DEVICE_IDLE_GAP_HEAVY")

    prelaunch_threshold = max(1.0, thresholds.get("prelaunch_gap_ratio", 0.10) * service_ms)
    if metrics.prelaunch_gap_ms >= prelaunch_threshold:
        tags.append("PRELAUNCH_GAP_HEAVY")

    tail_threshold = max(1.0, thresholds.get("tail_gap_ratio", 0.10) * service_ms)
    if metrics.tail_gap_ms >= tail_threshold:
        tags.append("TAIL_GAP_HEAVY")

    internal_threshold = max(1.0, thresholds.get("internal_bubble_ratio", 0.10) * service_ms)
    if metrics.largest_internal_bubble_ms >= internal_threshold:
        tags.append("INTERNAL_BUBBLE_HEAVY")

    return tags


def analyze_step_health(
    metrics: StepBubbleMetrics,
    anomaly_tags: List[str],
) -> tuple[str, List[str]]:
    """分析步骤健康度，返回风险等级和问题发现。"""
    findings = []
    risk_scores: List[str] = []

    # 评估各项指标
    if "PRELAUNCH_GAP_HEAVY" in anomaly_tags:
        findings.append(f"预启动间隙过大：{metrics.prelaunch_gap_ms:.2f}ms")
        risk_scores.append("high" if metrics.prelaunch_gap_ms > 20 else "medium")

    if "TAIL_GAP_HEAVY" in anomaly_tags:
        findings.append(f"尾部间隙明显：{metrics.tail_gap_ms:.2f}ms")
        risk_scores.append("medium")

    if "DEVICE_IDLE_GAP_HEAVY" in anomaly_tags:
        findings.append(f"设备欠载严重：{metrics.underfeed_ratio:.1%}")
        risk_scores.append(
            "critical" if metrics.underfeed_ratio > 0.6 else "high"
        )

    if "INTERNAL_BUBBLE_HEAVY" in anomaly_tags:
        findings.append(f"存在大型内部气泡：{metrics.largest_internal_bubble_ms:.2f}ms")
        if metrics.bubble_count > 5:
            findings.append(f"内部碎片化：{metrics.bubble_count}个气泡")
        risk_scores.append("high")

    # 确定整体风险等级
    if not risk_scores:
        return "low", ["运行状态良好"]
    if "critical" in risk_scores:
        return "critical", findings
    if "high" in risk_scores:
        return "high", findings
    if "medium" in risk_scores:
        return "medium", findings
    return "low", findings


# ── Step 分析器 ────────────────────────────────────────────────────────────


class StepAnalyzer:
    """昇腾 Profiling Step 级别完整气泡分析器。"""

    def __init__(
        self,
        kernel_df: pd.DataFrame,
        step_bounds: List[StepBound],
    ):
        """初始化分析器。

        Args:
            kernel_df: parse_kernel_details() 返回的 DataFrame
            step_bounds: Step 边界列表
        """
        self.kernel_df = kernel_df
        self.step_bounds = step_bounds
        self.thresholds = get_default_thresholds()

    def analyze_steps(self) -> List[StepAnalysis]:
        """执行完整 step 分析。"""
        analyzed_steps: List[StepAnalysis] = []

        for bound in self.step_bounds:
            # 构建设备区间
            kernel_intervals = build_kernel_intervals(
                self.kernel_df,
                bound.start_us,
                bound.end_us,
            )

            # 计算气泡指标
            metrics = compute_step_bubble_metrics(
                bound.start_us,
                bound.end_us,
                kernel_intervals,
            )

            # 异常标签
            anomaly_tags = tag_anomalies(metrics)

            # 健康度评估
            risk_level, findings = analyze_step_health(metrics, anomaly_tags)

            # 统计核函数类型
            ai_core_count = sum(
                1 for k in kernel_intervals if k.task_type == "AI_CORE"
            )
            ai_cpu_count = sum(
                1 for k in kernel_intervals if k.task_type == "AI_CPU"
            )
            hccl_count = sum(
                1 for k in kernel_intervals if "HCCL" in k.task_type or "Hcom" in k.task_type
            )
            distinct_streams = {k.stream_id for k in kernel_intervals}

            step_analysis = StepAnalysis(
                step_id=bound.step_id,
                step_start_us=bound.start_us,
                step_end_us=bound.end_us,
                duration_ms=metrics.service_ms,
                bubble_metrics=metrics,
                kernel_count=len(kernel_intervals),
                ai_core_count=ai_core_count,
                ai_cpu_count=ai_cpu_count,
                hccl_count=hccl_count,
                distinct_streams=distinct_streams,
                findings=findings,
                risk_level=risk_level,
            )
            analyzed_steps.append(step_analysis)

        return analyzed_steps

    @classmethod
    def from_directory(
        cls,
        profiling_dir: Path | str,
        kernel_file_pattern: str = "kernel_details*.csv",
    ) -> "StepAnalyzer":
        """从目录自动检测并加载 kernel_details 数据。

        Args:
            profiling_dir: Profiling 数据目录
            kernel_file_pattern: kernel_details 文件匹配模式

        Returns:
            StepAnalyzer 实例（未执行分析）

        Raises:
            FileNotFoundError: 未找到 kernel_details 文件
        """
        dir_p = Path(profiling_dir)
        if not dir_p.exists():
            raise FileNotFoundError(f"目录不存在: {profiling_dir}")

        # 查找 kernel_details 文件
        kernel_files = sorted(dir_p.glob(kernel_file_pattern))
        if not kernel_files:
            raise FileNotFoundError(
                f"未找到 kernel_details 文件: {dir_p / kernel_file_pattern}"
            )

        # 优先使用带 timestamp 的文件
        kernel_file = kernel_files[0]
        kernel_df = parse_kernel_details(str(kernel_file))

        # 查找 step 边界
        step_bounds = cls._detect_step_bounds(dir_p, kernel_df)

        return cls(kernel_df, step_bounds)

    @staticmethod
    def _detect_step_bounds(
        dir_p: Path,
        kernel_df: pd.DataFrame,
    ) -> List[StepBound]:
        """检测 Step 边界。

        优先级：
        1. step_trace_time.csv（用户标注的 step 边界）
        2. 从 kernel_details 自身的 Start Time 推断（首尾作为 single pseudo-step）
        """
        step_trace_file = dir_p / "step_trace_time.csv"

        if step_trace_file.exists():
            bounds = StepAnalyzer._parse_step_trace(step_trace_file)
            if bounds:
                return bounds

        # 回退：从 kernel_details 推断单个 pseudo-step
        if not kernel_df.empty:
            min_start = kernel_df["start_us"].min()
            max_end = kernel_df["start_us"].max() + kernel_df["duration_us"].max()
            return [StepBound(step_id=0, start_us=min_start, end_us=max_end)]

        return []

    @staticmethod
    def _parse_step_trace(step_trace_file: Path) -> List[StepBound]:
        """解析 step_trace_time.csv 获取 step 边界。"""
        import csv

        bounds: List[StepBound] = []
        prev_end_us = None

        for enc in ("utf-8", "utf-8-sig", "gbk", "gb2312"):
            try:
                with open(step_trace_file, "r", encoding=enc) as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
                    break
            except UnicodeDecodeError:
                continue

        if not rows:
            return []

        # 尝试识别时间列
        time_keys = []
        for key in rows[0].keys():
            key_lower = key.lower()
            if "time" in key_lower and "us" in key_lower:
                time_keys.append(key)
            elif "iteration" in key_lower and "time" in key_lower:
                time_keys.append(key)

        # msprof 格式：Step, Computing, Communication, ...
        if "Step" in rows[0] and time_keys:
            time_key = time_keys[0] if time_keys else None
            if not time_key:
                return []

            # 解析每行作为 step
            step_times: List[Tuple[int, float, float]] = []
            for row in rows:
                try:
                    step_id = int(row.get("Step", 0))
                    time_us = float(row.get(time_key, 0))
                    step_times.append((step_id, time_us))
                except (ValueError, TypeError):
                    continue

            if not step_times:
                return []

            # 计算 step 边界
            for i, (step_id, start_us) in enumerate(step_times):
                if i + 1 < len(step_times):
                    end_us = step_times[i + 1][1]
                else:
                    # 最后一个 step：估算结束时间
                    end_us = start_us + 50000  # 默认 50ms
                bounds.append(StepBound(step_id=step_id, start_us=start_us, end_us=end_us))

        return bounds


# ── 统一入口 ───────────────────────────────────────────────────────────────


def analyze_steps_from_directory(
    profiling_dir: Path | str,
    top_n: int = 10,
) -> Dict[str, Any]:
    """从目录执行完整 step 分析。

    Args:
        profiling_dir: Profiling 数据目录
        top_n: 返回 Top-N 算子数量

    Returns:
        包含 step 分析、算子排名、风险评估的字典
    """
    dir_p = Path(profiling_dir)

    # 查找 kernel_details 文件
    kernel_files = sorted(dir_p.glob("kernel_details*.csv"))
    if not kernel_files:
        return {
            "error": f"未在 {profiling_dir} 中找到 kernel_details*.csv 文件",
            "profiling_dir": str(profiling_dir),
        }

    kernel_file = kernel_files[0]
    kernel_df = parse_kernel_details(str(kernel_file))

    if kernel_df.empty:
        return {
            "error": "kernel_details.csv 文件为空",
            "profiling_dir": str(profiling_dir),
        }

    # 检测 step 边界
    step_bounds = StepAnalyzer._detect_step_bounds(dir_p, kernel_df)

    if not step_bounds:
        return {
            "error": "无法确定 step 边界",
            "profiling_dir": str(profiling_dir),
        }

    # 执行分析
    analyzer = StepAnalyzer(kernel_df, step_bounds)
    step_analysis = analyzer.analyze_steps()

    # 按算子聚合（全局）
    op_stats = aggregate_by_op(kernel_df)
    by_cost, by_duration = compute_op_rankings(op_stats)

    # Top-N
    top_by_cost = [
        {
            "op_name": name,
            "task_type": stats.task_type,
            "count": stats.count,
            "total_cost_us": round(stats.total_duration_us + stats.total_wait_us, 2),
            "total_duration_us": round(stats.total_duration_us, 2),
            "total_wait_us": round(stats.total_wait_us, 2),
            "wait_ratio": round(
                stats.total_wait_us / (stats.total_duration_us + stats.total_wait_us), 4
            )
            if (stats.total_duration_us + stats.total_wait_us) > 0
            else 0,
        }
        for name, stats in by_cost[:top_n]
    ]

    top_by_duration = [
        {
            "op_name": name,
            "task_type": stats.task_type,
            "count": stats.count,
            "total_duration_us": round(stats.total_duration_us, 2),
            "avg_duration_us": round(stats.total_duration_us / stats.count, 2)
            if stats.count > 0
            else 0,
        }
        for name, stats in by_duration[:top_n]
    ]

    # 汇总统计
    risk_counts = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    all_findings: List[str] = []
    for step in step_analysis:
        risk_counts[step.risk_level] += 1
        all_findings.extend(step.findings)

    # 整体风险等级
    overall_risk = "low"
    if risk_counts["critical"] > 0:
        overall_risk = "critical"
    elif risk_counts["high"] > len(step_analysis) * 0.3:
        overall_risk = "high"
    elif risk_counts["medium"] > len(step_analysis) * 0.5:
        overall_risk = "medium"

    # 生成建议
    recommendations = _generate_recommendations(step_analysis)

    return {
        "profiling_dir": str(profiling_dir),
        "data_source": "kernel_details",
        "kernel_file": kernel_file.name,
        "total_steps": len(step_analysis),
        "overall_risk_level": overall_risk,
        "summary": {
            "key_findings": all_findings[:10],
            "recommendations": recommendations,
        },
        "step_analysis": [
            {
                "step_id": s.step_id,
                "service_ms": round(s.duration_ms, 2),
                "device_busy_union_ms": round(s.bubble_metrics.device_busy_union_ms, 2),
                "kernel_sum_ms": round(s.bubble_metrics.kernel_sum_ms, 2),
                "total_cost_ms": round(s.bubble_metrics.total_cost_ms, 2),
                "underfeed_ratio": round(s.bubble_metrics.underfeed_ratio, 4),
                "prelaunch_gap_ms": round(s.bubble_metrics.prelaunch_gap_ms, 2),
                "tail_gap_ms": round(s.bubble_metrics.tail_gap_ms, 2),
                "internal_bubble_total_ms": round(s.bubble_metrics.internal_bubble_total_ms, 2),
                "largest_internal_bubble_ms": round(s.bubble_metrics.largest_internal_bubble_ms, 2),
                "bubble_count": s.bubble_metrics.bubble_count,
                "anomaly_tags": s.bubble_metrics.anomaly_tags,
                "kernel_count": s.kernel_count,
                "ai_core_count": s.ai_core_count,
                "ai_cpu_count": s.ai_cpu_count,
                "hccl_count": s.hccl_count,
                "distinct_streams": sorted(s.distinct_streams),
                "risk_level": s.risk_level,
                "findings": s.findings,
            }
            for s in step_analysis
        ],
        "top_ops_by_cost": top_by_cost,
        "top_ops_by_duration": top_by_duration,
        "risk_distribution": risk_counts,
    }


def _generate_recommendations(steps: List[StepAnalysis]) -> List[str]:
    """根据分析结果生成优化建议。"""
    recs: List[str] = []

    prelaunch_issues = sum(
        1 for s in steps if "PRELAUNCH_GAP_HEAVY" in s.bubble_metrics.anomaly_tags
    )
    underfeed_issues = sum(
        1 for s in steps if "DEVICE_IDLE_GAP_HEAVY" in s.bubble_metrics.anomaly_tags
    )
    internal_issues = sum(
        1 for s in steps if "INTERNAL_BUBBLE_HEAVY" in s.bubble_metrics.anomaly_tags
    )
    tail_issues = sum(
        1 for s in steps if "TAIL_GAP_HEAVY" in s.bubble_metrics.anomaly_tags
    )

    total = len(steps) if steps else 1

    if prelaunch_issues > total * 0.5:
        recs.append("优化 Host 侧数据预处理流水线，减少 Device 等待时间（预启动间隙过大）")
    if underfeed_issues > total * 0.5:
        recs.append("增加算子并行度或采用 Graph 模式提升设备利用率（设备欠载严重）")
    if internal_issues > total * 0.5:
        recs.append("融合小算子或使用 TBE 自定义算子减少内核启动开销（内部气泡过多）")
    if tail_issues > total * 0.5:
        recs.append("优化迭代收尾流程，减少尾部空闲时间")

    if not recs:
        recs.append("当前性能表现良好，可继续监控关键指标变化")

    return recs
