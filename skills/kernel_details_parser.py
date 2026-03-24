"""kernel_details.csv 解析器

解析昇腾 NPU profiling 数据中最细粒度的设备侧核函数数据，
支持设备区间构建、按算子聚合、Top-N 排名等核心功能。
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


# ── 列名映射 ────────────────────────────────────────────────────────────────

# kernel_details.csv 原始列名 → 标准列名
KERNEL_DETAILS_COLUMN_MAP = {
    "Start Time(us)": "start_us",
    "Duration(us)": "duration_us",
    "Wait Time(us)": "wait_us",
    "Task Type": "task_type",
    "Stream ID": "stream_id",
    "Name": "name",
    "Block Dim": "block_dim",
    "Input Shapes": "input_shapes",
    "Output Shapes": "output_shapes",
    "Input Data Types": "input_types",
    "Output Data Types": "output_types",
    "Accelerator Core": "accelerator_core",
    "Task ID": "task_id",
}


def _read_csv(file_path: str) -> list[dict]:
    """读取 CSV 文件，返回字典列表。"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    for enc in ("utf-8", "utf-8-sig", "gbk", "gb2312"):
        try:
            with open(path, "r", encoding=enc) as f:
                reader = csv.DictReader(f)
                return list(reader)
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"无法解码文件: {file_path}")


def _safe_float(value: str, default: float = 0.0) -> float:
    """安全转换为 float。"""
    if not value or value.strip() in ("N/A", "", "-"):
        return default
    try:
        return float(value.strip())
    except (ValueError, TypeError):
        return default


def _safe_int(value: str, default: int = 0) -> int:
    """安全转换为 int。"""
    if not value or value.strip() in ("N/A", "", "-"):
        return default
    try:
        return int(float(value.strip()))
    except (ValueError, TypeError):
        return default


# ── 数据结构 ────────────────────────────────────────────────────────────────


@dataclass
class KernelEntry:
    """单个核函数执行记录。"""
    name: str
    task_type: str  # AI_CORE, AI_CPU, HCCL, MIX_AIC, MIX_AIV, etc.
    start_us: float
    duration_us: float
    wait_us: float
    stream_id: int
    total_cost_us: float = field(init=False)
    # 可选字段
    block_dim: Optional[int] = None
    input_shapes: Optional[str] = None
    output_shapes: Optional[str] = None
    accelerator_core: Optional[str] = None

    def __post_init__(self):
        self.total_cost_us = self.duration_us + self.wait_us


@dataclass
class StepBound:
    """Step 边界定义。"""
    step_id: int
    start_us: float
    end_us: float


# ── 核心解析函数 ────────────────────────────────────────────────────────────


def parse_kernel_details(csv_path: str) -> pd.DataFrame:
    """解析 kernel_details.csv，返回标准化 DataFrame。

    列名自动映射（兼容不同命名变体）：
    - Start Time(us) / start_time / timestamp → start_us
    - Duration(us) / dur / duration → duration_us
    - Wait Time(us) / wait_time / wait → wait_us
    - Task Type / task_type / type → task_type
    - Stream ID / stream_id / stream → stream_id
    - Name / name / kernel_name → name
    """
    rows = _read_csv(csv_path)
    if not rows:
        return pd.DataFrame()

    raw_columns = list(rows[0].keys())

    # 构建列名映射（原始名 → 标准名）
    col_map: Dict[str, str] = {}
    reverse_map: Dict[str, str] = {}  # 标准名 → 原始名

    for raw_col in raw_columns:
        col_lower = raw_col.lower().strip()
        std_name = None

        # Start Time
        if "start" in col_lower and ("time" in col_lower or "us" in col_lower or col_lower == "timestamp"):
            std_name = "start_us"
        # Duration
        elif ("dur" in col_lower or col_lower == "duration") and std_name is None:
            std_name = "duration_us"
        # Wait Time
        elif "wait" in col_lower and std_name is None:
            std_name = "wait_us"
        # Task Type
        elif ("task" in col_lower and "type" in col_lower) or col_lower == "type":
            std_name = "task_type"
        # Stream ID
        elif ("stream" in col_lower and "id" in col_lower) or col_lower == "stream":
            std_name = "stream_id"
        # Name
        elif col_lower == "name" or "kernel" in col_lower:
            std_name = "name"
        # Block Dim
        elif "block" in col_lower and "dim" in col_lower:
            std_name = "block_dim"
        # Shapes
        elif "input" in col_lower and "shape" in col_lower:
            std_name = "input_shapes"
        elif "output" in col_lower and "shape" in col_lower:
            std_name = "output_shapes"
        # Accelerator Core
        elif "accelerator" in col_lower or "core" in col_lower:
            std_name = "accelerator_core"

        if std_name:
            col_map[raw_col] = std_name
            reverse_map[std_name] = raw_col

    # 转换数据
    normalized: List[Dict[str, Any]] = []
    for row in rows:
        new_row = {}
        for raw_col, std_name in col_map.items():
            raw_val = row.get(raw_col, "")
            if std_name in ("start_us", "duration_us", "wait_us"):
                new_row[std_name] = _safe_float(raw_val)
            elif std_name in ("stream_id", "block_dim"):
                new_row[std_name] = _safe_int(raw_val)
            else:
                new_row[std_name] = raw_val.strip() if raw_val else ""
        normalized.append(new_row)

    df = pd.DataFrame(normalized)

    # 确保必需的列存在
    required = ["name", "task_type", "start_us", "duration_us", "wait_us", "stream_id"]
    for col in required:
        if col not in df.columns:
            df[col] = 0 if col in ("start_us", "duration_us", "wait_us") else ""

    return df


def build_kernel_intervals(
    df: pd.DataFrame,
    step_start_us: float,
    step_end_us: float,
) -> List[KernelEntry]:
    """从 kernel_details DataFrame 构建设备核函数区间列表。

    只保留与给定 step 窗口有交集的核函数。
    核函数区间被裁剪到 step 窗口边界内。
    """
    if df.empty:
        return []

    # 筛选与 step 窗口有交集的核函数
    mask = (df["start_us"] < step_end_us) & (
        (df["start_us"] + df["duration_us"]) > step_start_us
    )
    sub = df[mask]

    intervals: List[KernelEntry] = []
    for _, row in sub.iterrows():
        # 裁剪到 step 窗口
        s = max(step_start_us, float(row["start_us"]))
        e = min(step_end_us, float(row["start_us"]) + float(row["duration_us"]))
        if e <= s:
            continue

        entry = KernelEntry(
            name=str(row.get("name", "")),
            task_type=str(row.get("task_type", "")),
            start_us=s,
            duration_us=e - s,  # 使用裁剪后的 duration
            wait_us=float(row.get("wait_us", 0.0)),
            stream_id=int(row.get("stream_id", 0)),
        )
        intervals.append(entry)

    return intervals


# ── 按算子聚合 ──────────────────────────────────────────────────────────────


@dataclass
class OpStats:
    """算子聚合统计。"""
    op_name: str
    count: int = 0
    total_duration_us: float = 0.0
    total_wait_us: float = 0.0
    min_duration_us: float = float("inf")
    max_duration_us: float = 0.0
    task_type: str = ""


def aggregate_by_op(df: pd.DataFrame) -> Dict[str, OpStats]:
    """按算子名聚合，返回 {op_name: OpStats}。"""
    if df.empty:
        return {}

    stats: Dict[str, OpStats] = {}

    for _, row in df.iterrows():
        name = str(row.get("name", "unknown"))
        duration = float(row.get("duration_us", 0.0))
        wait = float(row.get("wait_us", 0.0))
        task_type = str(row.get("task_type", ""))

        if name not in stats:
            stats[name] = OpStats(op_name=name, task_type=task_type)

        s = stats[name]
        s.count += 1
        s.total_duration_us += duration
        s.total_wait_us += wait
        if duration < s.min_duration_us:
            s.min_duration_us = duration
        if duration > s.max_duration_us:
            s.max_duration_us = duration

    return stats


def compute_op_rankings(
    op_stats: Dict[str, OpStats],
) -> Tuple[List[Tuple[str, OpStats]], List[Tuple[str, OpStats]]]:
    """返回两个排名元组列表：(by_total_cost, by_kernel_duration)。

    - by_total_cost: duration + wait 之和降序
    - by_kernel_duration: 纯 duration 之和降序
    """
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


# ── 工具函数 ────────────────────────────────────────────────────────────────


def detect_file_type(file_path: str) -> str:
    """检测 kernel_details 系列文件。

    匹配模式：kernel_details*.csv（含 timestamp 后缀）
    """
    name = Path(file_path).name.lower()
    if "kernel_details" in name and name.endswith(".csv"):
        return "kernel_details"
    return "unknown"


def analyze_kernel_details(
    csv_path: str,
    top_n: int = 10,
) -> Dict[str, Any]:
    """分析 kernel_details.csv，返回结构化结果。

    Args:
        csv_path: kernel_details.csv 文件路径
        top_n: 返回 Top-N 高耗时/高占比算子数量

    Returns:
        包含 kernel 统计、Top 算子、Task Type 分布的字典
    """
    df = parse_kernel_details(csv_path)
    if df.empty:
        return {"error": "文件为空或无有效数据"}

    # 基本统计
    total_kernels = len(df)
    total_duration_us = df["duration_us"].sum()
    total_wait_us = df["wait_us"].sum()
    distinct_ops = df["name"].nunique()
    distinct_streams = sorted(df["stream_id"].unique().tolist())

    # 按 Task Type 分布
    type_dist: Dict[str, float] = {}
    for task_type, group in df.groupby("task_type"):
        type_dist[task_type] = group["duration_us"].sum()

    # 按算子聚合
    op_stats = aggregate_by_op(df)
    by_cost, by_duration = compute_op_rankings(op_stats)

    # Top-N by total_cost
    top_by_cost = []
    for name, stats in by_cost[:top_n]:
        total = stats.total_duration_us + stats.total_wait_us
        top_by_cost.append({
            "op_name": name,
            "task_type": stats.task_type,
            "count": stats.count,
            "total_cost_us": round(total, 2),
            "total_duration_us": round(stats.total_duration_us, 2),
            "total_wait_us": round(stats.total_wait_us, 2),
            "avg_duration_us": round(stats.total_duration_us / stats.count, 2) if stats.count > 0 else 0,
            "avg_wait_us": round(stats.total_wait_us / stats.count, 2) if stats.count > 0 else 0,
            "wait_ratio": round(stats.total_wait_us / total, 4) if total > 0 else 0,
            "ratio_pct": round(total / (total_duration_us + total_wait_us) * 100, 2)
            if (total_duration_us + total_wait_us) > 0
            else 0,
        })

    # Top-N by duration (pure compute)
    top_by_duration = []
    for name, stats in by_duration[:top_n]:
        top_by_duration.append({
            "op_name": name,
            "task_type": stats.task_type,
            "count": stats.count,
            "total_duration_us": round(stats.total_duration_us, 2),
            "avg_duration_us": round(stats.total_duration_us / stats.count, 2) if stats.count > 0 else 0,
            "min_duration_us": round(stats.min_duration_us, 2),
            "max_duration_us": round(stats.max_duration_us, 2),
            "ratio_pct": round(stats.total_duration_us / total_duration_us * 100, 2)
            if total_duration_us > 0
            else 0,
        })

    # Findings（客观事实标记）
    findings = []

    # Dominant op (by total_cost)
    if top_by_cost and top_by_cost[0]["ratio_pct"] > 30:
        findings.append({
            "type": "dominant_op",
            "op_name": top_by_cost[0]["op_name"],
            "ratio_pct": top_by_cost[0]["ratio_pct"],
        })

    # High AI_CPU ratio
    ai_cpu_time = type_dist.get("AI_CPU", 0.0)
    if (total_duration_us + total_wait_us) > 0 and ai_cpu_time / (total_duration_us + total_wait_us) > 0.1:
        findings.append({
            "type": "high_ai_cpu_ratio",
            "ratio_pct": round(ai_cpu_time / (total_duration_us + total_wait_us) * 100, 2),
            "ai_cpu_time_us": round(ai_cpu_time, 2),
        })

    # Wait-anchor candidates
    for op in top_by_cost[:5]:
        if op["wait_ratio"] > 0.95 and op["avg_duration_us"] < 10.0:
            findings.append({
                "type": "wait_anchor_candidate",
                "op_name": op["op_name"],
                "wait_ratio": op["wait_ratio"],
                "avg_duration_us": op["avg_duration_us"],
            })

    return {
        "total_kernels": total_kernels,
        "distinct_ops": distinct_ops,
        "total_duration_us": round(total_duration_us, 2),
        "total_wait_us": round(total_wait_us, 2),
        "distinct_streams": distinct_streams,
        "type_distribution": {
            k: {"time_us": round(v, 2), "ratio": round(v / total_duration_us * 100, 2) if total_duration_us > 0 else 0}
            for k, v in sorted(type_dist.items(), key=lambda x: x[1], reverse=True)
        },
        "top_ops_by_cost": top_by_cost,
        "top_ops_by_duration": top_by_duration,
        "findings": findings,
    }
