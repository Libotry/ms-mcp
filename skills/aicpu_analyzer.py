"""AICPU 分析模块

根据 rulebook.md Section 6 实现 AICPU 算子的 masked_ratio 分类。

分类规则：
- masked_ratio >= 0.9:  AICPU_MASKED_BUT_UNDESIRABLE（隐藏在 AI_CORE 重叠下，但仍不理想）
- 0.2 <= masked_ratio < 0.9: AICPU_PARTIALLY_EXPOSED（部分暴露）
- masked_ratio < 0.2: AICPU_EXPOSED_NOT_ALLOWED（完全暴露，直接导致设备空闲）

masked_ratio = AI_CPU kernel 与 AI_CORE 活动重叠的时间 / AI_CPU kernel duration
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .kernel_details_parser import KernelEntry
from .step_analyzer import Interval, merge_intervals


# ── 数据结构 ────────────────────────────────────────────────────────────────


@dataclass
class AICPUAnalysis:
    """单个 AICPU 算子的分析结果。"""
    op_name: str
    task_type: str
    count: int
    total_duration_us: float
    total_wait_us: float
    masked_duration_us: float  # 与 AI_CORE 重叠的时间
    exposed_duration_us: float  # 暴露在 AI_CORE 之外的时间
    masked_ratio: float  # 重叠比例
    exposed_ratio: float  # 暴露比例
    classification: str  # AICPU_MASKED_BUT_UNDESIRABLE / AICPU_PARTIALLY_EXPOSED / AICPU_EXPOSED_NOT_ALLOWED
    is_problematic: bool  # True if exposed_ratio < 0.2 (fully exposed)


# ── 阈值定义 ────────────────────────────────────────────────────────────────


@dataclass
class AICPUThresholds:
    """AICPU 分类阈值。"""
    high_masked: float = 0.9  # masked_ratio >= 0.9
    low_exposed: float = 0.2  # exposed_ratio < 0.2


DEFAULT_THRESHOLDS = AICPUThresholds()


# ── 重叠计算 ────────────────────────────────────────────────────────────────


def compute_aicpu_overlap(
    aicpu_kernel: KernelEntry,
    all_kernels: List[KernelEntry],
) -> Tuple[float, float]:
    """计算单个 AICPU kernel 与 AI_CORE 的重叠时间。

    Returns:
        (masked_duration_us, exposed_duration_us)
    """
    if aicpu_kernel.duration_us <= 0:
        return 0.0, 0.0

    aicpu_start = aicpu_kernel.start_us
    aicpu_end = aicpu_kernel.start_us + aicpu_kernel.duration_us

    masked_us = 0.0

    # 遍历所有 AI_CORE kernels
    for k in all_kernels:
        if k.task_type != "AI_CORE":
            continue

        k_start = k.start_us
        k_end = k.start_us + k.duration_us

        # 计算重叠
        overlap_start = max(aicpu_start, k_start)
        overlap_end = min(aicpu_end, k_end)
        if overlap_end > overlap_start:
            masked_us += overlap_end - overlap_start

    exposed_us = aicpu_kernel.duration_us - masked_us
    return masked_us, max(0.0, exposed_us)


def aggregate_aicpu_kernels(
    kernels: List[KernelEntry],
    thresholds: Optional[AICPUThresholds] = None,
) -> List[AICPUAnalysis]:
    """聚合所有 AICPU kernels 并计算 masked_ratio。

    Args:
        kernels: 所有 kernels（来自 kernel_details）
        thresholds: 可选的阈值配置

    Returns:
        AICPUAnalysis 列表
    """
    if thresholds is None:
        thresholds = DEFAULT_THRESHOLDS

    # 分离 AICPU 和 AI_CORE kernels
    aicpu_kernels = [k for k in kernels if k.task_type == "AI_CPU"]
    all_kernels = list(kernels)  # 复制

    if not aicpu_kernels:
        return []

    # 按 op name 聚合
    aicpu_by_name: Dict[str, List[KernelEntry]] = {}
    for k in aicpu_kernels:
        aicpu_by_name.setdefault(k.name, []).append(k)

    results: List[AICPUAnalysis] = []

    for name, name_kernels in aicpu_by_name.items():
        total_duration = sum(k.duration_us for k in name_kernels)
        total_wait = sum(k.wait_us for k in name_kernels)
        count = len(name_kernels)

        total_masked = 0.0
        total_exposed = 0.0

        for k in name_kernels:
            masked, exposed = compute_aicpu_overlap(k, all_kernels)
            total_masked += masked
            total_exposed += exposed

        masked_ratio = total_masked / total_duration if total_duration > 0 else 0.0
        exposed_ratio = total_exposed / total_duration if total_duration > 0 else 0.0

        # 分类
        if masked_ratio >= thresholds.high_masked:
            classification = "AICPU_MASKED_BUT_UNDESIRABLE"
        elif exposed_ratio < thresholds.low_exposed:
            classification = "AICPU_EXPOSED_NOT_ALLOWED"
        else:
            classification = "AICPU_PARTIALLY_EXPOSED"

        is_problematic = exposed_ratio < thresholds.low_exposed

        results.append(AICPUAnalysis(
            op_name=name,
            task_type="AI_CPU",
            count=count,
            total_duration_us=total_duration,
            total_wait_us=total_wait,
            masked_duration_us=total_masked,
            exposed_duration_us=total_exposed,
            masked_ratio=masked_ratio,
            exposed_ratio=exposed_ratio,
            classification=classification,
            is_problematic=is_problematic,
        ))

    # 按 exposed_ratio 降序排序（最暴露的在前）
    results.sort(key=lambda x: x.exposed_ratio)
    return results


# ── 汇总报告 ────────────────────────────────────────────────────────────────


@dataclass
class AICPUsummary:
    """AICPU 汇总。"""
    total_aicpu_ops: int = 0
    masked_count: int = 0  # AICPU_MASKED_BUT_UNDESIRABLE
    partially_exposed_count: int = 0  # AICPU_PARTIALLY_EXPOSED
    exposed_not_allowed_count: int = 0  # AICPU_EXPOSED_NOT_ALLOWED
    problematic_ops: List[str] = field(default_factory=list)
    most_exposed_ops: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_aicpu_ops": self.total_aicpu_ops,
            "masked_count": self.masked_count,
            "partially_exposed_count": self.partially_exposed_count,
            "exposed_not_allowed_count": self.exposed_count,
            "problematic_ops": self.problematic_ops,
            "most_exposed_ops": self.most_exposed_ops,
        }


def summarize_aicpu(analyses: List[AICPUAnalysis]) -> AICPUsummary:
    """汇总 AICPU 分析结果。"""
    if not analyses:
        return AICPUsummary()

    problematic = [a for a in analyses if a.is_problematic]
    most_exposed = [
        {
            "op_name": a.op_name,
            "exposed_ratio": round(a.exposed_ratio, 4),
            "masked_ratio": round(a.masked_ratio, 4),
            "classification": a.classification,
        }
        for a in sorted(analyses, key=lambda x: x.exposed_ratio)[:5]
    ]

    return AICPUsummary(
        total_aicpu_ops=len(analyses),
        masked_count=sum(1 for a in analyses if a.classification == "AICPU_MASKED_BUT_UNDESIRABLE"),
        partially_exposed_count=sum(1 for a in analyses if a.classification == "AICPU_PARTIALLY_EXPOSED"),
        exposed_not_allowed_count=sum(1 for a in analyses if a.classification == "AICPU_EXPOSED_NOT_ALLOWED"),
        problematic_ops=[a.op_name for a in problematic],
        most_exposed_ops=most_exposed,
    )


def generate_aicpu_report(kernels: List[KernelEntry]) -> Dict[str, Any]:
    """生成完整的 AICPU 分析报告。

    Args:
        kernels: 所有 kernels

    Returns:
        包含 AICPU 汇总和详细分析的字典
    """
    analyses = aggregate_aicpu_kernels(kernels)
    summary = summarize_aicpu(analyses)

    return {
        "summary": summary.to_dict(),
        "details": [
            {
                "op_name": a.op_name,
                "count": a.count,
                "total_duration_us": round(a.total_duration_us, 2),
                "total_wait_us": round(a.total_wait_us, 2),
                "masked_duration_us": round(a.masked_duration_us, 2),
                "exposed_duration_us": round(a.exposed_duration_us, 2),
                "masked_ratio": round(a.masked_ratio, 4),
                "exposed_ratio": round(a.exposed_ratio, 4),
                "classification": a.classification,
                "is_problematic": a.is_problematic,
            }
            for a in analyses
        ],
    }
