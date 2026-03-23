"""Ascend Profiling Anomaly Analyzer

Analyzes Huawei Ascend NPU profiling data to discover performance anomalies,
identify bottlenecks, and generate detailed architecture reports.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


@dataclass
class Interval:
    """时间区间表示."""

    start_us: float
    end_us: float

    @property
    def dur_us(self) -> float:
        """返回区间持续时间 (微秒)."""
        return max(0.0, self.end_us - self.start_us)


@dataclass
class BubbleMetrics:
    """气泡分析指标."""

    service_ms: float = 0.0
    device_busy_union_ms: float = 0.0
    underfeed_ms: float = 0.0
    underfeed_ratio: float = 0.0
    prelaunch_gap_ms: float = 0.0
    tail_gap_ms: float = 0.0
    internal_bubble_total_ms: float = 0.0
    largest_internal_bubble_ms: float = 0.0
    bubble_count: int = 0
    bubble_intervals: List[Interval] = field(default_factory=list)


@dataclass
class StepAnalysis:
    """单步分析结果."""

    step_id: int
    step_start_us: float
    step_end_us: float
    duration_ms: float
    bubble_metrics: BubbleMetrics
    findings: List[str] = field(default_factory=list)
    risk_level: str = "low"  # low, medium, high, critical


@dataclass
class AnalysisReport:
    """完整分析报告."""

    total_steps: int
    analyzed_steps: List[StepAnalysis]
    overall_risk_level: str
    key_findings: List[str]
    recommendations: List[str]
    architecture_hints: Dict[str, Any] = field(default_factory=dict)


def merge_intervals(intervals: List[Interval]) -> List[Interval]:
    """合并重叠的时间区间."""
    items = sorted((i for i in intervals if i.end_us > i.start_us), 
                   key=lambda x: (x.start_us, x.end_us))
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


def interval_union_us(intervals: List[Interval]) -> float:
    """计算区间并集的总时长."""
    return sum(i.dur_us for i in merge_intervals(intervals))


def compute_step_bubble_metrics(
    step_start_us: float,
    step_end_us: float,
    device_intervals: List[Interval]
) -> BubbleMetrics:
    """计算单步的气泡指标."""
    service_us = max(0.0, step_end_us - step_start_us)
    merged = merge_intervals(device_intervals)
    
    if not merged:
        return BubbleMetrics(
            service_ms=service_us / 1000.0,
            underfeed_ms=service_us / 1000.0,
            underfeed_ratio=1.0 if service_us > 0 else 0.0,
        )
    
    busy_union_us = sum(seg.dur_us for seg in merged)
    prelaunch_us = max(0.0, merged[0].start_us - step_start_us)
    tail_us = max(0.0, step_end_us - merged[-1].end_us)
    
    # 计算内部气泡
    bubbles: List[Interval] = []
    for left, right in zip(merged[:-1], merged[1:]):
        if right.start_us > left.end_us:
            bubbles.append(Interval(left.end_us, right.start_us))
    
    bubble_total_us = sum(b.dur_us for b in bubbles)
    largest_bubble_us = max((b.dur_us for b in bubbles), default=0.0)
    underfeed_us = max(0.0, service_us - busy_union_us)
    underfeed_ratio = underfeed_us / service_us if service_us > 0 else 0.0
    
    return BubbleMetrics(
        service_ms=service_us / 1000.0,
        device_busy_union_ms=busy_union_us / 1000.0,
        underfeed_ms=underfeed_us / 1000.0,
        underfeed_ratio=underfeed_ratio,
        prelaunch_gap_ms=prelaunch_us / 1000.0,
        tail_gap_ms=tail_us / 1000.0,
        internal_bubble_total_ms=bubble_total_us / 1000.0,
        largest_internal_bubble_ms=largest_bubble_us / 1000.0,
        bubble_count=len(bubbles),
        bubble_intervals=bubbles,
    )


def analyze_step_health(metrics: BubbleMetrics) -> Tuple[str, List[str]]:
    """分析步骤健康度，返回风险等级和问题发现."""
    findings = []
    risk_scores = []
    
    # 检查预启动间隙
    if metrics.prelaunch_gap_ms > 5.0:
        findings.append(f"预启动间隙过大：{metrics.prelaunch_gap_ms:.2f}ms (>5ms)")
        risk_scores.append("high" if metrics.prelaunch_gap_ms > 20 else "medium")
    
    # 检查尾部间隙
    if metrics.tail_gap_ms > 3.0:
        findings.append(f"尾部间隙明显：{metrics.tail_gap_ms:.2f}ms (>3ms)")
        risk_scores.append("medium")
    
    # 检查欠载率
    if metrics.underfeed_ratio > 0.3:
        findings.append(f"设备欠载严重：{metrics.underfeed_ratio:.1%} (>30%)")
        risk_scores.append("critical" if metrics.underfeed_ratio > 0.6 else "high")
    
    # 检查内部气泡
    if metrics.bubble_count > 5:
        findings.append(f"内部碎片化：{metrics.bubble_count}个气泡")
        risk_scores.append("medium")
    
    if metrics.largest_internal_bubble_ms > 10.0:
        findings.append(f"存在大型内部气泡：{metrics.largest_internal_bubble_ms:.2f}ms (>10ms)")
        risk_scores.append("high")
    
    # 确定整体风险等级
    if not risk_scores:
        return "low", ["运行状态良好"]
    
    if "critical" in risk_scores:
        return "critical", findings
    elif "high" in risk_scores:
        return "high", findings
    elif "medium" in risk_scores:
        return "medium", findings
    else:
        return "low", findings


def build_device_intervals_from_csv(
    csv_path: Path,
    step_start_us: float,
    step_end_us: float
) -> List[Interval]:
    """从 CSV 构建设备执行区间."""
    df = pd.read_csv(csv_path)
    
    # 假设列名包含 start_time/us 和 duration/us
    # 需要根据实际 profilling 数据调整
    time_col = None
    dur_col = None
    
    for col in df.columns:
        col_lower = col.lower()
        if 'start' in col_lower and ('time' in col_lower or 'us' in col_lower):
            time_col = col
        if 'dur' in col_lower or ('time' in col_lower and 'us' in col_lower):
            dur_col = col
    
    if not time_col or not dur_col:
        # 尝试其他常见命名
        if 'Timestamp' in df.columns:
            time_col = 'Timestamp'
        if 'Duration' in df.columns:
            dur_col = 'Duration'
    
    if not time_col or not dur_col:
        return []
    
    intervals: List[Interval] = []
    for _, row in df.iterrows():
        start = float(row[time_col])
        duration = float(row[dur_col])
        end = start + duration
        
        # 只保留与当前步骤有交集的区间
        if start < step_end_us and end > step_start_us:
            s = max(step_start_us, start)
            e = min(step_end_us, end)
            if e > s:
                intervals.append(Interval(s, e))
    
    return intervals


class ProfilingAnalyzer:
    """昇腾 Profiling 数据分析器."""
    
    def __init__(self, profiling_dir: Path | str):
        """初始化分析器.
        
        Args:
            profiling_dir: Profiling 数据目录路径
        """
        self.profiling_dir = Path(profiling_dir)
        # 加载 SKILL.md 配置
        from .skill_parser import load_skill_config
        self.skill_config, self.thresholds = load_skill_config(self.profiling_dir)
        self.op_stats_path = self.profiling_dir / "op_statistic_0.csv"
        self.step_trace_path = self.profiling_dir / "step_trace_time.csv"
        self.logger = None  # Can be set externally for logging
        
    def analyze(self) -> AnalysisReport:
        """执行完整分析."""
        analyzed_steps = []
        all_findings = []
        
        # 读取步骤追踪数据
        if not self.step_trace_path.exists():
            msg = f"Step trace file not found: {self.step_trace_path}"
            if self.logger:
                self.logger.warning(msg)
            return AnalysisReport(
                total_steps=0,
                analyzed_steps=[],
                overall_risk_level="unknown",
                key_findings=[msg],
                recommendations=["请确保profiling数据包含step_trace_time.csv"],
            )
        
        step_df = pd.read_csv(self.step_trace_path)
        
        # 识别步骤边界列
        step_col = None
        start_col = None
        end_col = None
        
        for col in step_df.columns:
            col_lower = col.lower()
            if 'step' in col_lower or 'iter' in col_lower:
                step_col = col
            if 'start' in col_lower and ('time' in col_lower or 'us' in col_lower):
                start_col = col
            if 'end' in col_lower and ('time' in col_lower or 'us' in col_lower):
                end_col = col
        
        # 如果没有明确的结束时间列，使用开始时间 + 持续时间
        dur_col = None
        if not end_col:
            for col in step_df.columns:
                col_lower = col.lower()
                if 'dur' in col_lower or ('time' in col_lower and 'us' in col_lower):
                    dur_col = col
        
        if not step_col or not start_col:
                msg = f"Step trace file has unexpected format. Expected columns with step/iteration and start time info, Got: {set(step_df.columns)}. Skipping step analysis."
                if self.logger:
                    self.logger.warning(msg)
                return AnalysisReport(
                    total_steps=0,
                    analyzed_steps=[],
                    overall_risk_level="unknown",
                    key_findings=[msg],
                    recommendations=["检查 step_trace_time.csv 文件格式是否正确"],
                )
        
        # 遍历每个步骤进行分析
        for _, row in step_df.iterrows():
            step_id = int(row[step_col])
            step_start_us = float(row[start_col])
            
            if end_col:
                step_end_us = float(row[end_col])
            elif dur_col:
                step_end_us = step_start_us + float(row[dur_col])
            else:
                continue
            
            # 构建设备执行区间
            device_intervals = build_device_intervals_from_csv(
                self.op_stats_path,
                step_start_us,
                step_end_us
            )
            
            # 计算气泡指标
            metrics = compute_step_bubble_metrics(
                step_start_us,
                step_end_us,
                device_intervals
            )
            
            # 分析健康度
            risk_level, findings = analyze_step_health(metrics)
            all_findings.extend(findings)
            
            step_analysis = StepAnalysis(
                step_id=step_id,
                step_start_us=step_start_us,
                step_end_us=step_end_us,
                duration_ms=(step_end_us - step_start_us) / 1000.0,
                bubble_metrics=metrics,
                findings=findings,
                risk_level=risk_level,
            )
            analyzed_steps.append(step_analysis)
        
        # 汇总分析结果
        overall_risk = self._compute_overall_risk(analyzed_steps)
        recommendations = self._generate_recommendations(analyzed_steps)
        
        return AnalysisReport(
            total_steps=len(analyzed_steps),
            analyzed_steps=analyzed_steps,
            overall_risk_level=overall_risk,
            key_findings=all_findings[:10],  # 限制数量
            recommendations=recommendations,
        )
    
    def _compute_overall_risk(self, steps: List[StepAnalysis]) -> str:
        """计算整体风险等级."""
        if not steps:
            return "unknown"
        
        risk_counts = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        for step in steps:
            risk_counts[step.risk_level] += 1
        
        if risk_counts["critical"] > 0:
            return "critical"
        elif risk_counts["high"] > len(steps) * 0.3:
            return "high"
        elif risk_counts["medium"] > len(steps) * 0.5:
            return "medium"
        else:
            return "low"
    
    def _generate_recommendations(self, steps: List[StepAnalysis]) -> List[str]:
        """生成优化建议."""
        recs = []
        
        # 统计常见问题
        prelaunch_issues = sum(1 for s in steps if s.bubble_metrics.prelaunch_gap_ms > 5)
        underfeed_issues = sum(1 for s in steps if s.bubble_metrics.underfeed_ratio > 0.3)
        fragmentation_issues = sum(1 for s in steps if s.bubble_metrics.bubble_count > 5)
        
        if prelaunch_issues > len(steps) * 0.5:
            recs.append("优化 Host 侧数据预处理流水线，减少 Device 等待时间")
        
        if underfeed_issues > len(steps) * 0.5:
            recs.append("增加算子并行度或采用 Graph 模式提升设备利用率")
        
        if fragmentation_issues > len(steps) * 0.5:
            recs.append("融合小算子或使用 TBE 自定义算子减少内核启动开销")
        
        if not recs:
            recs.append("当前性能表现良好，可继续监控关键指标变化")
        
        return recs
    
    def export_report(self, output_path: Path | str) -> None:
        """导出分析报告为 JSON."""
        report = self.analyze()
        
        output = {
            "summary": {
                "total_steps": report.total_steps,
                "overall_risk_level": report.overall_risk_level,
                "key_findings": report.key_findings,
                "recommendations": report.recommendations,
            },
            "steps": [
                {
                    "step_id": s.step_id,
                    "duration_ms": s.duration_ms,
                    "risk_level": s.risk_level,
                    "findings": s.findings,
                    "bubble_metrics": {
                        "service_ms": s.bubble_metrics.service_ms,
                        "device_busy_union_ms": s.bubble_metrics.device_busy_union_ms,
                        "underfeed_ratio": s.bubble_metrics.underfeed_ratio,
                        "prelaunch_gap_ms": s.bubble_metrics.prelaunch_gap_ms,
                        "tail_gap_ms": s.bubble_metrics.tail_gap_ms,
                        "internal_bubble_total_ms": s.bubble_metrics.internal_bubble_total_ms,
                        "largest_internal_bubble_ms": s.bubble_metrics.largest_internal_bubble_ms,
                        "bubble_count": s.bubble_metrics.bubble_count,
                    }
                }
                for s in report.analyzed_steps
            ]
        }
        
        output_file = Path(output_path)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        print(f"报告已导出至：{output_file}")
