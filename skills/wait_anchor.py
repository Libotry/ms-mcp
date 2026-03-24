"""Wait-Anchor 完整检测模块

根据 rulebook.md Section 5.1 实现完整的 Wait-Anchor 假热点检测。
Wait-Anchor 是指那些在 total_cost 排名中靠前，但实际 kernel 执行时间很短、
大量时间消耗在等待上的算子。这些算子吸收了设备空闲时间，在 total_cost 排名中
表现为"热点"，但其 kernel 执行本身并不是瓶颈。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .kernel_details_parser import OpStats, aggregate_by_op, compute_op_rankings
from .skill_parser import get_default_thresholds


# ── 数据结构 ────────────────────────────────────────────────────────────────


@dataclass
class WaitAnchorOp:
    """Wait-Anchor 算子详情。"""
    op_name: str
    task_type: str
    count: int
    total_cost_us: float
    total_duration_us: float
    total_wait_us: float
    wait_ratio: float
    avg_duration_us: float
    avg_wait_us: float
    is_false_hotspot: bool
    total_cost_rank: int
    duration_rank: int


# ── 核心检测函数 ────────────────────────────────────────────────────────────


def compute_wait_ratio(
    total_duration_us: float,
    total_wait_us: float,
) -> float:
    """计算 wait_ratio。

    Formula: wait_ratio = wait_us / (duration_us + wait_us)

    当 total_cost 接近 0 时返回 0（避免除零）。
    """
    total = total_duration_us + total_wait_us
    if total <= 0:
        return 0.0
    return total_wait_us / total


def is_wait_anchor_candidate(
    wait_ratio: float,
    avg_duration_us: float,
    total_cost_rank: int,
    thresholds: Optional[Dict[str, float]] = None,
) -> bool:
    """判断是否为 Wait-Anchor 候选。

    规则（rulebook.md Section 5.1）：
    - wait_ratio > 0.95（等待时间占总成本 95% 以上）
    - avg_duration_us < 10.0（单次执行时间极短）
    - total_cost_rank <= 10（总成本排名前 10）

    Args:
        wait_ratio: 等待时间占比
        avg_duration_us: 平均执行时间（微秒）
        total_cost_rank: 总成本排名（1 = 最贵）
        thresholds: 可选的阈值配置

    Returns:
        True 如果满足 Wait-Anchor 条件
    """
    if thresholds is None:
        thresholds = get_default_thresholds()

    wait_ratio_threshold = thresholds.get("wait_anchor_ratio", 0.95)

    return bool(
        wait_ratio > wait_ratio_threshold
        and avg_duration_us < 10.0
        and total_cost_rank <= 10
    )


def detect_wait_anchors_from_df(df: pd.DataFrame) -> List[WaitAnchorOp]:
    """从 kernel_details DataFrame 检测 Wait-Anchor 算子。

    Args:
        df: parse_kernel_details() 返回的 DataFrame

    Returns:
        Wait-Anchor 算子列表（按 total_cost_rank 排序）
    """
    if df.empty:
        return []

    thresholds = get_default_thresholds()
    op_stats = aggregate_by_op(df)
    by_cost, by_duration = compute_op_rankings(op_stats)

    # 构建排名字典
    cost_rank: Dict[str, int] = {}
    duration_rank: Dict[str, int] = {}
    for rank, (name, _) in enumerate(by_cost, 1):
        cost_rank[name] = rank
    for rank, (name, _) in enumerate(by_duration, 1):
        duration_rank[name] = rank

    wait_anchors: List[WaitAnchorOp] = []

    for name, stats in op_stats.items():
        total_cost = stats.total_duration_us + stats.total_wait_us
        avg_duration = stats.total_duration_us / stats.count if stats.count > 0 else 0
        avg_wait = stats.total_wait_us / stats.count if stats.count > 0 else 0
        wait_ratio = compute_wait_ratio(stats.total_duration_us, stats.total_wait_us)

        total_cost_rank = cost_rank.get(name, 0)
        duration_rank_val = duration_rank.get(name, 0)

        is_false = is_wait_anchor_candidate(
            wait_ratio,
            avg_duration,
            total_cost_rank,
            thresholds,
        )

        wait_anchor = WaitAnchorOp(
            op_name=name,
            task_type=stats.task_type,
            count=stats.count,
            total_cost_us=total_cost,
            total_duration_us=stats.total_duration_us,
            total_wait_us=stats.total_wait_us,
            wait_ratio=wait_ratio,
            avg_duration_us=avg_duration,
            avg_wait_us=avg_wait,
            is_false_hotspot=is_false,
            total_cost_rank=total_cost_rank,
            duration_rank=duration_rank_val,
        )
        wait_anchors.append(wait_anchor)

    # 按 total_cost_rank 排序
    wait_anchors.sort(key=lambda x: x.total_cost_rank)

    return wait_anchors


def detect_wait_anchors_from_op_stats(
    op_stats: Dict[str, OpStats],
) -> List[WaitAnchorOp]:
    """从算子统计字典检测 Wait-Anchor 算子。

    Args:
        op_stats: aggregate_by_op() 返回的字典

    Returns:
        Wait-Anchor 算子列表
    """
    if not op_stats:
        return []

    thresholds = get_default_thresholds()
    by_cost, by_duration = compute_op_rankings(op_stats)

    # 构建排名字典
    cost_rank: Dict[str, int] = {}
    duration_rank: Dict[str, int] = {}
    for rank, (name, _) in enumerate(by_cost, 1):
        cost_rank[name] = rank
    for rank, (name, _) in enumerate(by_duration, 1):
        duration_rank[name] = rank

    wait_anchors: List[WaitAnchorOp] = []

    for name, stats in op_stats.items():
        total_cost = stats.total_duration_us + stats.total_wait_us
        avg_duration = stats.total_duration_us / stats.count if stats.count > 0 else 0
        avg_wait = stats.total_wait_us / stats.count if stats.count > 0 else 0
        wait_ratio = compute_wait_ratio(stats.total_duration_us, stats.total_wait_us)

        total_cost_rank = cost_rank.get(name, 0)
        duration_rank_val = duration_rank.get(name, 0)

        is_false = is_wait_anchor_candidate(
            wait_ratio,
            avg_duration,
            total_cost_rank,
            thresholds,
        )

        wait_anchor = WaitAnchorOp(
            op_name=name,
            task_type=stats.task_type,
            count=stats.count,
            total_cost_us=total_cost,
            total_duration_us=stats.total_duration_us,
            total_wait_us=stats.total_wait_us,
            wait_ratio=wait_ratio,
            avg_duration_us=avg_duration,
            avg_wait_us=avg_wait,
            is_false_hotspot=is_false,
            total_cost_rank=total_cost_rank,
            duration_rank=duration_rank_val,
        )
        wait_anchors.append(wait_anchor)

    wait_anchors.sort(key=lambda x: x.total_cost_rank)

    return wait_anchors


# ── 排名对比分析 ────────────────────────────────────────────────────────────


@dataclass
class RankingDiscrepancy:
    """两个排名之间的差异分析。"""
    op_name: str
    task_type: str
    total_cost_rank: int
    duration_rank: int
    rank_diff: int  # 正数表示在 cost 排名中更靠前
    is_suspicious: bool


def analyze_ranking_discrepancies(
    op_stats: Dict[str, OpStats],
    rank_diff_threshold: int = 5,
) -> List[RankingDiscrepancy]:
    """分析 total_cost 排名和 duration 排名之间的差异。

    当一个算子在 total_cost 排名中比 duration 排名高出 rank_diff_threshold 位以上时，
    说明该算子有大量等待时间，可能是 Wait-Anchor。

    Args:
        op_stats: 算子统计字典
        rank_diff_threshold: 排名差异阈值（默认 5 位）

    Returns:
        排名差异分析结果列表
    """
    by_cost, by_duration = compute_op_rankings(op_stats)

    cost_rank: Dict[str, int] = {}
    duration_rank: Dict[str, int] = {}
    for rank, (name, _) in enumerate(by_cost, 1):
        cost_rank[name] = rank
    for rank, (name, _) in enumerate(by_duration, 1):
        duration_rank[name] = rank

    discrepancies: List[RankingDiscrepancy] = []

    for name, stats in op_stats.items():
        cost_r = cost_rank.get(name, 0)
        dur_r = duration_rank.get(name, 0)
        if cost_r == 0 or dur_r == 0:
            continue

        rank_diff = dur_r - cost_r  # 正数表示 cost 排名更靠前

        # cost 排名远高于 duration 排名（等待时间多）
        is_suspicious = rank_diff >= rank_diff_threshold

        discrepancies.append(RankingDiscrepancy(
            op_name=name,
            task_type=stats.task_type,
            total_cost_rank=cost_r,
            duration_rank=dur_r,
            rank_diff=rank_diff,
            is_suspicious=is_suspicious,
        ))

    # 按 rank_diff 降序排序（最可疑的在前）
    discrepancies.sort(key=lambda x: -x.rank_diff)

    return discrepancies


# ── 汇总报告 ────────────────────────────────────────────────────────────────


def generate_wait_anchor_report(
    wait_anchors: List[WaitAnchorOp],
    discrepancies: List[RankingDiscrepancy],
) -> Dict[str, Any]:
    """生成 Wait-Anchor 分析汇总报告。

    Args:
        wait_anchors: 检测到的 Wait-Anchor 算子列表
        discrepancies: 排名差异分析列表

    Returns:
        汇总报告字典
    """
    false_hotspots = [w for w in wait_anchors if w.is_false_hotspot]
    high_wait = [w for w in wait_anchors if w.wait_ratio > 0.5 and not w.is_false_hotspot]

    suspicious_discrepancies = [d for d in discrepancies if d.is_suspicious]

    findings = []
    if false_hotspots:
        findings.append({
            "type": "wait_anchor_detected",
            "count": len(false_hotspots),
            "ops": [
                {
                    "op_name": w.op_name,
                    "wait_ratio": round(w.wait_ratio, 4),
                    "avg_duration_us": round(w.avg_duration_us, 2),
                    "total_cost_rank": w.total_cost_rank,
                }
                for w in false_hotspots[:5]
            ],
        })

    return {
        "total_wait_anchor_candidates": len(wait_anchors),
        "confirmed_false_hotspots": len(false_hotspots),
        "high_wait_ops": len(high_wait),
        "false_hotspots": [
            {
                "op_name": w.op_name,
                "task_type": w.task_type,
                "count": w.count,
                "total_cost_us": round(w.total_cost_us, 2),
                "total_duration_us": round(w.total_duration_us, 2),
                "total_wait_us": round(w.total_wait_us, 2),
                "wait_ratio": round(w.wait_ratio, 4),
                "avg_duration_us": round(w.avg_duration_us, 2),
                "avg_wait_us": round(w.avg_wait_us, 2),
                "total_cost_rank": w.total_cost_rank,
                "duration_rank": w.duration_rank,
            }
            for w in false_hotspots
        ],
        "suspicious_discrepancies": [
            {
                "op_name": d.op_name,
                "task_type": d.task_type,
                "total_cost_rank": d.total_cost_rank,
                "duration_rank": d.duration_rank,
                "rank_diff": d.rank_diff,
            }
            for d in suspicious_discrepancies[:10]
        ],
        "findings": findings,
    }
