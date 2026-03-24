"""Soft Attribution 模块

根据 rulebook.md Section 4 实现气泡根因的软归属分析。
对每个气泡窗口，根据 host 证据重叠比例分配概率级标签。

规则（Section 4.4 Decision Table）：
| 条件 | 标签 |
|------|------|
| sync_overlap ≥ 0.20 | possible_sync_or_h2d |
| comm_overlap ≥ 0.20 | possible_comm_wait |
| host_coverage < 0.05 | possible_untraced_host_blocking |
| host_coverage ≥ 0.10 但无 sync/comm 主导 | possible_host_launch_lag |
| host_parallelism < 1.2 且无上述证据 | possible_python_serialization_or_lock |
| 上述都不适用 | insufficient_evidence |
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .step_analyzer import Interval


# ── 数据结构 ────────────────────────────────────────────────────────────────


@dataclass
class SoftAttributionResult:
    """软归属结果。"""
    bubble_start_us: float
    bubble_end_us: float
    bubble_duration_us: float
    host_visible_coverage_ratio: float = 0.0
    sync_marker_overlap_ratio: float = 0.0
    comm_marker_overlap_ratio: float = 0.0
    cpu_op_coverage_ratio: float = 0.0
    ascendcl_coverage_ratio: float = 0.0
    labels: List[str] = field(default_factory=list)
    covering_events_count: int = 0
    requires_host_followup: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bubble_start_us": self.bubble_start_us,
            "bubble_end_us": self.bubble_end_us,
            "bubble_duration_us": self.bubble_duration_us,
            "host_visible_coverage_ratio": self.host_visible_coverage_ratio,
            "sync_marker_overlap_ratio": self.sync_marker_overlap_ratio,
            "comm_marker_overlap_ratio": self.comm_marker_overlap_ratio,
            "cpu_op_coverage_ratio": self.cpu_op_coverage_ratio,
            "ascendcl_coverage_ratio": self.ascendcl_coverage_ratio,
            "labels": self.labels,
            "covering_events_count": self.covering_events_count,
            "requires_host_followup": self.requires_host_followup,
        }


@dataclass
class BubbleHostEvidence:
    """气泡窗口的 host 证据。"""
    all_coverage: float = 0.0
    sync_coverage: float = 0.0
    comm_coverage: float = 0.0
    cpu_op_coverage: float = 0.0
    ascendcl_coverage: float = 0.0
    covering_events: List[Dict[str, Any]] = field(default_factory=list)


# ── 重叠比例计算 ────────────────────────────────────────────────────────────


def compute_overlap_ratio(
    bubble: Interval,
    intervals: Sequence,
) -> float:
    """计算气泡与区间的重叠比例。"""
    if bubble.dur_us <= 0:
        return 0.0

    total_overlap = 0.0
    for h in intervals:
        left = max(bubble.start_us, h.start_us)
        right = min(bubble.end_us, h.end_us)
        if right > left:
            total_overlap += right - left

    return total_overlap / bubble.dur_us


def analyze_host_evidence(
    bubble: Interval,
    host_intervals: Dict[str, List],
) -> BubbleHostEvidence:
    """分析气泡的 host 证据。"""
    all_intervals = host_intervals.get("all", [])
    sync_intervals = host_intervals.get("sync", [])
    comm_intervals = host_intervals.get("comm", [])
    cpu_op_intervals = host_intervals.get("cpu_op", [])
    ascendcl_intervals = host_intervals.get("ascendcl", [])

    return BubbleHostEvidence(
        all_coverage=compute_overlap_ratio(bubble, all_intervals),
        sync_coverage=compute_overlap_ratio(bubble, sync_intervals),
        comm_coverage=compute_overlap_ratio(bubble, comm_intervals),
        cpu_op_coverage=compute_overlap_ratio(bubble, cpu_op_intervals),
        ascendcl_coverage=compute_overlap_ratio(bubble, ascendcl_intervals),
        covering_events=[
            {
                "name": h.name,
                "category": h.category,
                "start_us": h.start_us,
                "end_us": h.end_us,
            }
            for h in all_intervals
            if h.start_us < bubble.end_us and h.end_us > bubble.start_us
        ][:20],
    )


# ── Soft Attribution 核心 ───────────────────────────────────────────────────


THRESHOLDS = {
    "sync_overlap_threshold": 0.20,
    "comm_overlap_threshold": 0.20,
    "untraced_threshold": 0.05,
    "launch_lag_threshold": 0.10,
    "parallelism_threshold": 1.2,
}


def apply_soft_attribution_rules(
    evidence: BubbleHostEvidence,
) -> List[str]:
    """应用软归属规则（rulebook.md Section 4.4）。

    Returns:
        标签列表（可能包含多个标签）
    """
    labels: List[str] = []

    # 1. possible_sync_or_h2d: sync_overlap >= 0.20
    if evidence.sync_coverage >= THRESHOLDS["sync_overlap_threshold"]:
        labels.append("possible_sync_or_h2d")

    # 2. possible_comm_wait: comm_overlap >= 0.20
    if evidence.comm_coverage >= THRESHOLDS["comm_overlap_threshold"]:
        labels.append("possible_comm_wait")

    # 3. possible_untraced_host_blocking: host_coverage < 0.05
    if evidence.all_coverage < THRESHOLDS["untraced_threshold"]:
        labels.append("possible_untraced_host_blocking")

    # 4. possible_host_launch_lag: host_coverage >= 0.10 但无 sync/comm 主导
    #    且有 CPU op 覆盖
    if (
        evidence.all_coverage >= THRESHOLDS["launch_lag_threshold"]
        and "possible_sync_or_h2d" not in labels
        and "possible_comm_wait" not in labels
        and evidence.cpu_op_coverage > 0
    ):
        labels.append("possible_host_launch_lag")

    # 5. 额外的 AscendCL 证据
    if (
        evidence.ascendcl_coverage >= THRESHOLDS["sync_overlap_threshold"]
        and "possible_sync_or_h2d" not in labels
    ):
        labels.append("possible_ascendcl_blocking")

    # 6. Fallback: insufficient_evidence
    if not labels:
        labels.append("insufficient_evidence")

    return labels


def analyze_bubble_attribution(
    bubble: Interval,
    host_intervals: Dict[str, List],
) -> SoftAttributionResult:
    """分析单个气泡的软归属。

    Args:
        bubble: 气泡区间
        host_intervals: 分类型的 host intervals

    Returns:
        SoftAttributionResult
    """
    evidence = analyze_host_evidence(bubble, host_intervals)
    labels = apply_soft_attribution_rules(evidence)

    # 判断是否需要 host 跟进
    requires_followup = (
        "possible_untraced_host_blocking" in labels
        or evidence.all_coverage < THRESHOLDS["untraced_threshold"]
        or (
            len(labels) == 1
            and labels[0] == "insufficient_evidence"
        )
    )

    return SoftAttributionResult(
        bubble_start_us=bubble.start_us,
        bubble_end_us=bubble.end_us,
        bubble_duration_us=bubble.dur_us,
        host_visible_coverage_ratio=evidence.all_coverage,
        sync_marker_overlap_ratio=evidence.sync_coverage,
        comm_marker_overlap_ratio=evidence.comm_coverage,
        cpu_op_coverage_ratio=evidence.cpu_op_coverage,
        ascendcl_coverage_ratio=evidence.ascendcl_coverage,
        labels=labels,
        covering_events_count=len(evidence.covering_events),
        requires_host_followup=requires_followup,
    )


def analyze_all_bubbles_attribution(
    bubbles: List[Interval],
    host_intervals: Dict[str, List],
) -> List[SoftAttributionResult]:
    """分析所有气泡的软归属。

    Args:
        bubbles: 气泡区间列表
        host_intervals: 分类型的 host intervals

    Returns:
        每个气泡的软归属结果列表
    """
    results: List[SoftAttributionResult] = []
    for bubble in bubbles:
        result = analyze_bubble_attribution(bubble, host_intervals)
        results.append(result)
    return results


# ── 汇总分析 ────────────────────────────────────────────────────────────────


@dataclass
class AttributionSummary:
    """归属汇总。"""
    total_bubbles: int = 0
    bubbles_with_evidence: int = 0
    bubbles_need_followup: int = 0
    label_counts: Dict[str, int] = field(default_factory=dict)
    dominant_label: str = "unknown"
    requires_host_followup: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_bubbles": self.total_bubbles,
            "bubbles_with_evidence": self.bubbles_with_evidence,
            "bubbles_need_followup": self.bubbles_need_followup,
            "label_counts": self.label_counts,
            "dominant_label": self.dominant_label,
            "requires_host_followup": self.requires_host_followup,
        }


def summarize_attributions(
    results: List[SoftAttributionResult],
) -> AttributionSummary:
    """汇总所有气泡的归属结果。"""
    if not results:
        return AttributionSummary()

    label_counts: Dict[str, int] = {}
    bubbles_with_evidence = 0
    bubbles_need_followup = 0

    for r in results:
        for label in r.labels:
            label_counts[label] = label_counts.get(label, 0) + 1

        if r.host_visible_coverage_ratio > 0.05:
            bubbles_with_evidence += 1

        if r.requires_host_followup:
            bubbles_need_followup += 1

    # 找出最常见的标签
    dominant = max(label_counts.items(), key=lambda x: x[1]) if label_counts else ("insufficient_evidence", 0)

    # 判断整体是否需要 host 跟进
    # 如果超过 50% 的气泡需要跟进，则整体需要
    overall_followup = bubbles_need_followup > len(results) * 0.5

    return AttributionSummary(
        total_bubbles=len(results),
        bubbles_with_evidence=bubbles_with_evidence,
        bubbles_need_followup=bubbles_need_followup,
        label_counts=label_counts,
        dominant_label=dominant[0],
        requires_host_followup=overall_followup,
    )


# ── 与 Step Analyzer 集成 ──────────────────────────────────────────────────


def build_attribution_report(
    bubbles: List[Interval],
    host_intervals: Dict[str, List],
) -> Dict[str, Any]:
    """构建完整的归属报告。

    用于整合到 Step 分析结果中。
    """
    if not bubbles:
        return {
            "bubble_count": 0,
            "summary": AttributionSummary().to_dict(),
            "bubbles": [],
        }

    results = analyze_all_bubbles_attribution(bubbles, host_intervals)
    summary = summarize_attributions(results)

    return {
        "bubble_count": len(bubbles),
        "summary": summary.to_dict(),
        "bubbles": [r.to_dict() for r in results],
    }
