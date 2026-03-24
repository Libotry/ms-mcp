"""Step Grouping 模块

根据 kernel 组成对 Step 进行分组（rulebook.md Section 2.5）：
- 相同 kernel 数量（在容差范围内）
- 相同算子名称序列（模板匹配）
- 相同 dominant task type 分布

分组后识别 dominant group，并尝试标注 step 类型
（forward / backward / iterationrefresh / other）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import Counter

import pandas as pd

from .kernel_details_parser import KernelEntry


# ── 数据结构 ────────────────────────────────────────────────────────────────


@dataclass
class StepKernelSignature:
    """Step 的 Kernel 签名（用于分组）。"""
    step_id: int
    kernel_count: int
    ai_core_count: int
    ai_cpu_count: int
    hccl_count: int
    task_type_counts: Dict[str, int]  # e.g., {"AI_CORE": 100, "AI_CPU": 20}
    top_kernel_names: List[str]  # 频率最高的 kernel 名（前 10 个）
    total_duration_us: float
    total_wait_us: float


@dataclass
class StepGroup:
    """Step Group 定义。"""
    group_id: str
    group_type: str  # "forward" / "backward" / "iterationrefresh" / "other"
    step_ids: List[int]
    size: int
    avg_kernel_count: float
    avg_duration_ms: float
    dominant_task_type: str
    kernel_signature: List[str]  # 代表性 kernel 序列


@dataclass
class GroupingResult:
    """分组结果。"""
    groups: List[StepGroup]
    dominant_group: Optional[StepGroup]
    step_to_group: Dict[int, str]  # step_id -> group_id
    total_groups: int
    dominant_group_id: Optional[str]


# ── Step Signature 提取 ──────────────────────────────────────────────────────


def extract_step_signature(
    step_id: int,
    kernel_intervals: List[KernelEntry],
) -> StepKernelSignature:
    """从 kernel 列表提取 step 签名。"""
    kernel_count = len(kernel_intervals)

    ai_core_count = sum(1 for k in kernel_intervals if k.task_type == "AI_CORE")
    ai_cpu_count = sum(1 for k in kernel_intervals if k.task_type == "AI_CPU")
    hccl_count = sum(
        1 for k in kernel_intervals
        if "HCCL" in k.task_type or "Hcom" in k.task_type
    )

    # Task type 分布
    task_type_counts: Dict[str, int] = {}
    for k in kernel_intervals:
        task_type_counts[k.task_type] = task_type_counts.get(k.task_type, 0) + 1

    # Top kernel names by frequency
    name_counts = Counter(k.name for k in kernel_intervals)
    top_kernel_names = [name for name, _ in name_counts.most_common(10)]

    total_duration = sum(k.duration_us for k in kernel_intervals)
    total_wait = sum(k.wait_us for k in kernel_intervals)

    return StepKernelSignature(
        step_id=step_id,
        kernel_count=kernel_count,
        ai_core_count=ai_core_count,
        ai_cpu_count=ai_cpu_count,
        hccl_count=hccl_count,
        task_type_counts=task_type_counts,
        top_kernel_names=top_kernel_names,
        total_duration_us=total_duration,
        total_wait_us=total_wait,
    )


def signature_distance(
    sig1: StepKernelSignature,
    sig2: StepKernelSignature,
) -> float:
    """计算两个签名的相似度距离（0 = 完全相同）。

    使用：
    - kernel 数量差异
    - task type 分布差异（Jensen-Shannon 散度近似）
    - top kernel 名称重叠率
    """
    # 1. Kernel 数量差异（归一化）
    count_diff = abs(sig1.kernel_count - sig2.kernel_count) / max(sig1.kernel_count, sig2.kernel_count, 1)

    # 2. Task type 分布差异
    all_types = set(sig1.task_type_counts.keys()) | set(sig2.task_type_counts.keys())
    type_diff = 0.0
    for t in all_types:
        c1 = sig1.task_type_counts.get(t, 0)
        c2 = sig2.task_type_counts.get(t, 0)
        total1 = sum(sig1.task_type_counts.values())
        total2 = sum(sig2.task_type_counts.values())
        p1 = c1 / max(total1, 1)
        p2 = c2 / max(total2, 1)
        type_diff += abs(p1 - p2)
    type_diff /= len(all_types) if all_types else 1

    # 3. Top kernel 名称重叠
    names1 = set(sig1.top_kernel_names)
    names2 = set(sig2.top_kernel_names)
    if names1 or names2:
        overlap = len(names1 & names2) / len(names1 | names2)
    else:
        overlap = 1.0

    # 综合距离
    distance = (0.4 * count_diff) + (0.3 * type_diff) + (0.3 * (1 - overlap))
    return distance


# ── Step 类型推断 ──────────────────────────────────────────────────────────


def infer_step_type(
    sig: StepKernelSignature,
    all_signatures: List[StepKernelSignature],
) -> str:
    """根据 kernel 组成推断 step 类型。

    启发式规则（可调整）：
    - iterationrefresh: kernel 数量很少，总时间很短
    - backward: HCCL 比例高
    - forward: 以 AI_CORE 为主，kernel 数量中等
    - other: 无法归类
    """
    # 启发式特征
    total_count = sig.kernel_count
    hccl_ratio = sig.hccl_count / max(total_count, 1)
    ai_core_ratio = sig.ai_core_count / max(total_count, 1)
    duration_ms = sig.total_duration_us / 1000.0

    # 1. iterationrefresh: 时间很短，kernel 数量少
    if duration_ms < 5.0 and total_count < 50:
        return "iterationrefresh"

    # 2. backward: HCCL 通信比例较高（反向传播需要同步梯度）
    if hccl_ratio > 0.15:
        return "backward"

    # 3. forward: AI_CORE 为主，kernel 数量中等
    if ai_core_ratio > 0.6 and 50 < total_count < 500:
        return "forward"

    # 4. 其他
    return "other"


# ── Step Grouping 核心 ──────────────────────────────────────────────────────


def group_steps(
    signatures: List[StepKernelSignature],
    distance_threshold: float = 0.15,
) -> GroupingResult:
    """对 steps 进行分组。

    使用贪心聚类：按时间顺序处理，将相似 step 归入同一 group。

    Args:
        signatures: Step 签名列表（按 step_id 排序）
        distance_threshold: 相似度阈值（默认 0.15）

    Returns:
        GroupingResult
    """
    if not signatures:
        return GroupingResult(
            groups=[],
            dominant_group=None,
            step_to_group={},
            total_groups=0,
            dominant_group_id=None,
        )

    # 按 step_id 排序
    signatures = sorted(signatures, key=lambda x: x.step_id)

    groups: List[List[StepKernelSignature]] = []
    group_signatures: List[List[str]] = []  # 每组的 kernel 签名
    group_task_types: List[Dict[str, int]] = []  # 每组的 task type 分布

    # 贪心聚类
    for sig in signatures:
        assigned = False
        for i, group_sigs in enumerate(groups):
            # 计算与组内第一个样本的距离
            dist = signature_distance(sig, group_sigs[0])
            if dist < distance_threshold:
                group_sigs.append(sig)
                group_task_types[i] = _merge_task_types(
                    group_task_types[i], sig.task_type_counts
                )
                # 更新 kernel 签名
                group_signatures[i] = sig.top_kernel_names[:5]
                assigned = True
                break

        if not assigned:
            groups.append([sig])
            group_signatures.append(sig.top_kernel_names[:5])
            group_task_types.append(dict(sig.task_type_counts))

    # 构建 StepGroup
    step_groups: List[StepGroup] = []
    step_to_group: Dict[int, str] = {}

    total_time_by_group: Dict[int, float] = {}

    for i, group_sigs in enumerate(groups):
        group_id = f"group_{i}"

        # 推断组类型
        avg_sig = _average_signature(group_sigs)
        group_type = infer_step_type(avg_sig, signatures)

        # 统计
        avg_kernel_count = sum(s.kernel_count for s in group_sigs) / len(group_sigs)
        avg_duration = sum(s.total_duration_us for s in group_sigs) / len(group_sigs)

        # Dominant task type
        dominant_type = max(
            avg_sig.task_type_counts.items(), key=lambda x: x[1]
        )[0] if avg_sig.task_type_counts else "unknown"

        step_ids = [s.step_id for s in group_sigs]
        for sid in step_ids:
            step_to_group[sid] = group_id

        step_group = StepGroup(
            group_id=group_id,
            group_type=group_type,
            step_ids=step_ids,
            size=len(group_sigs),
            avg_kernel_count=avg_kernel_count,
            avg_duration_ms=avg_duration / 1000.0,
            dominant_task_type=dominant_type,
            kernel_signature=group_signatures[i][:5],
        )
        step_groups.append(step_group)
        total_time_by_group[i] = avg_duration * len(group_sigs)

    # 找出 dominant group（总时间最长的 group）
    dominant_idx = max(total_time_by_group.items(), key=lambda x: x[1])[0] if total_time_by_group else None
    dominant_group = step_groups[dominant_idx] if dominant_idx is not None else None

    return GroupingResult(
        groups=step_groups,
        dominant_group=dominant_group,
        step_to_group=step_to_group,
        total_groups=len(step_groups),
        dominant_group_id=dominant_group.group_id if dominant_group else None,
    )


# ── 辅助函数 ────────────────────────────────────────────────────────────────


def _merge_task_types(
    t1: Dict[str, int],
    t2: Dict[str, int],
) -> Dict[str, int]:
    """合并两个 task type 计数器。"""
    result = dict(t1)
    for k, v in t2.items():
        result[k] = result.get(k, 0) + v
    return result


def _average_signature(sigs: List[StepKernelSignature]) -> StepKernelSignature:
    """计算平均签名。"""
    if not sigs:
        return StepKernelSignature(
            step_id=0,
            kernel_count=0,
            ai_core_count=0,
            ai_cpu_count=0,
            hccl_count=0,
            task_type_counts={},
            top_kernel_names=[],
            total_duration_us=0.0,
            total_wait_us=0.0,
        )

    n = len(sigs)
    merged_task_types: Dict[str, int] = {}
    for s in sigs:
        for k, v in s.task_type_counts.items():
            merged_task_types[k] = merged_task_types.get(k, 0) + v // n

    # 取第一个签名的 top names
    return StepKernelSignature(
        step_id=sigs[0].step_id,
        kernel_count=int(sum(s.kernel_count for s in sigs) / n),
        ai_core_count=int(sum(s.ai_core_count for s in sigs) / n),
        ai_cpu_count=int(sum(s.ai_cpu_count for s in sigs) / n),
        hccl_count=int(sum(s.hccl_count for s in sigs) / n),
        task_type_counts=merged_task_types,
        top_kernel_names=sigs[0].top_kernel_names[:5],
        total_duration_us=sum(s.total_duration_us for s in sigs) / n,
        total_wait_us=sum(s.total_wait_us for s in sigs) / n,
    )


# ── 与 StepAnalyzer 集成 ─────────────────────────────────────────────────────


def group_steps_from_intervals(
    step_kernel_map: Dict[int, List[KernelEntry]],
) -> GroupingResult:
    """从 step -> kernel 列表的映射生成分组结果。

    Args:
        step_kernel_map: {step_id: [KernelEntry, ...]}

    Returns:
        GroupingResult
    """
    signatures = [
        extract_step_signature(step_id, kernels)
        for step_id, kernels in step_kernel_map.items()
    ]

    return group_steps(signatures)


# ── 分组报告 ────────────────────────────────────────────────────────────────


def generate_grouping_report(result: GroupingResult) -> Dict[str, Any]:
    """生成分组报告。"""
    if not result.groups:
        return {
            "total_groups": 0,
            "dominant_group": None,
            "groups": [],
        }

    groups_summary = []
    for g in result.groups:
        groups_summary.append({
            "group_id": g.group_id,
            "group_type": g.group_type,
            "size": g.size,
            "step_ids": g.step_ids,
            "avg_kernel_count": round(g.avg_kernel_count, 1),
            "avg_duration_ms": round(g.avg_duration_ms, 2),
            "dominant_task_type": g.dominant_task_type,
            "kernel_signature": g.kernel_signature,
        })

    return {
        "total_groups": result.total_groups,
        "dominant_group_id": result.dominant_group_id,
        "dominant_group": {
            "group_id": result.dominant_group.group_id,
            "group_type": result.dominant_group.group_type,
            "size": result.dominant_group.size,
            "avg_duration_ms": round(result.dominant_group.avg_duration_ms, 2),
        } if result.dominant_group else None,
        "groups": groups_summary,
    }
