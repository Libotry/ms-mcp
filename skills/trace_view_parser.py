"""trace_view.json 解析器

解析 Chrome Tracing 格式的 trace_view.json，
提取 Host 侧和 Device 侧事件，用于气泡根因分析（Soft Attribution）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

from .step_analyzer import Interval


# ── 数据结构 ────────────────────────────────────────────────────────────────


@dataclass
class TraceEvent:
    """单个 trace 事件。"""
    name: str
    category: str
    timestamp_us: float
    duration_us: float
    pid: int
    tid: int
    ph: str = "X"  # X=complete, B=begin, E=end, i=instant
    args: Dict[str, Any] = field(default_factory=dict)

    @property
    def end_us(self) -> float:
        return self.timestamp_us + self.duration_us


@dataclass
class HostInterval:
    """Host 侧时间区间（用于与 bubble 重叠分析）。"""
    start_us: float
    end_us: float
    name: str
    category: str
    pid: int = 0
    tid: int = 0

    @property
    def dur_us(self) -> float:
        return max(0.0, self.end_us - self.start_us)


# ── Host Event 类别定义 ────────────────────────────────────────────────────


class HostEventCategories:
    """Host Event 类别常量（对应 rulebook.md Section 4）。"""

    # Sync / H2D markers
    SYNC_PATTERNS = {
        "aten::to",
        "aten::_to_copy",
        "aten::copy_",
        "HostToDevice",
        "torch_to_npu",
        "aclrtMemcpy",
        "aclrtSynchronize",
        "torch.cuda.synchronize",
    }

    # Communication markers
    COMM_PATTERNS = {
        "c10d",
        "Hccl",
        "hcom",
        "StreamWaitEvent",
        "Notify_Wait",
        "allreduce",
        "allgather",
        "broadcast",
        "send",
        "recv",
    }

    # CPU op patterns
    CPU_OP_PATTERNS = {
        "aten::",
        "torch::",
        "torch_npu::",
        "cpu_op",
    }

    # Python function patterns
    PYTHON_PATTERNS = {
        "python_function",
        "python::",
    }

    # ACL runtime patterns
    ASCENDCL_PATTERNS = {
        "AscendCL@",
        "aclrt",
        "aclop",
    }


def _matches_any(text: str, patterns: Set[str]) -> bool:
    """检查 text 是否匹配任一 pattern。"""
    text_lower = text.lower()
    for p in patterns:
        if p.lower() in text_lower:
            return True
    return False


# ── 核心解析函数 ────────────────────────────────────────────────────────────


TRACE_PATTERNS = {
    "ph": re.compile(r'"ph"\s*:\s*"([^"]*)"'),
    "ts": re.compile(r'"ts"\s*:\s*([\d.eE+\-]+)'),
    "dur": re.compile(r'"dur"\s*:\s*([\d.eE+\-]+)'),
    "name": re.compile(r'"name"\s*:\s*"([^"]*)"'),
    "cat": re.compile(r'"cat"\s*:\s*"([^"]*)"'),
    "pid": re.compile(r'"pid"\s*:\s*(\d+)'),
    "tid": re.compile(r'"tid"\s*:\s*(\d+)'),
}


def _parse_event_from_segment(seg: str) -> Optional[TraceEvent]:
    """从 JSON 片段解析单个事件。"""
    ph_m = TRACE_PATTERNS["ph"].search(seg)
    if not ph_m or ph_m.group(1) not in ("X", "B", "E", "i"):
        return None

    ts_m = TRACE_PATTERNS["ts"].search(seg)
    dur_m = TRACE_PATTERNS["dur"].search(seg)
    name_m = TRACE_PATTERNS["name"].search(seg)
    cat_m = TRACE_PATTERNS["cat"].search(seg)
    pid_m = TRACE_PATTERNS["pid"].search(seg)
    tid_m = TRACE_PATTERNS["tid"].search(seg)

    if not ts_m:
        return None

    ph = ph_m.group(1)
    ts = float(ts_m.group(1))

    # dur 对于 X 是必需的，对于 B/E 可以忽略
    dur = float(dur_m.group(1)) if dur_m else 0.0
    if dur < 0:
        dur = 0.0

    name = name_m.group(1) if name_m else "unknown"
    cat = cat_m.group(1) if cat_m else ""
    pid = int(pid_m.group(1)) if pid_m else 0
    tid = int(tid_m.group(1)) if tid_m else 0

    return TraceEvent(
        name=name,
        category=cat,
        timestamp_us=ts,
        duration_us=dur,
        pid=pid,
        tid=tid,
        ph=ph,
    )


def parse_trace_view(
    file_path: str,
    limit_mb: int = 500,
) -> List[TraceEvent]:
    """解析 trace_view.json，返回事件列表。

    采用流式正则解析，避免将整个大文件读入内存。
    支持 Chrome Tracing Format。

    Args:
        file_path: trace_view.json 文件路径
        limit_mb: 最大处理大小（MB），默认 500MB

    Returns:
        TraceEvent 列表
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    # 检查文件大小
    file_size_mb = path.stat().st_size / 1024 / 1024
    if file_size_mb > limit_mb:
        raise ValueError(
            f"trace_view.json 文件过大 ({file_size_mb:.1f}MB)，"
            f"超过处理限制 {limit_mb}MB"
        )

    events: List[TraceEvent] = []
    chunk_size = 8 * 1024 * 1024  # 8MB chunks
    split_pat = re.compile(r'\}\s*,\s*\{')

    try:
        with open(path, "r", encoding="utf-8") as f:
            leftover = ""
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    # 处理最后的 leftover
                    if leftover.strip():
                        seg = leftover.strip().strip("[]{},")
                        if seg:
                            event = _parse_event_from_segment(seg)
                            if event:
                                events.append(event)
                    break

                text = leftover + chunk
                parts = list(split_pat.finditer(text))

                if parts:
                    last_split = parts[-1]
                    leftover = "{" + text[last_split.end():]
                    process_text = text[:last_split.start() + 1]
                else:
                    leftover = text
                    continue

                segments = split_pat.split(process_text)
                for seg in segments:
                    event = _parse_event_from_segment(seg)
                    if event:
                        events.append(event)

    except UnicodeDecodeError:
        # 尝试其他编码
        with open(path, "r", encoding="gbk") as f:
            content = f.read()
        # 按行处理，查找 traceEvents
        pass

    return events


# ── Host Interval 构建 ─────────────────────────────────────────────────────


def build_host_intervals(
    events: List[TraceEvent],
    categories: Optional[List[str]] = None,
) -> List[HostInterval]:
    """从 trace events 构建 Host Interval 列表。

    Args:
        events: trace_view.json 解析的事件列表
        categories: 可选的类别过滤（如 ["cpu_op", "python_function", "AscendCL"]）

    Returns:
        HostInterval 列表（按 start_us 排序）
    """
    intervals: List[HostInterval] = []

    for e in events:
        # 跳过 device 事件（category 包含 "kernel" 且 pid=0 通常是 device）
        if e.category in ("kernel", "communication") and e.pid == 0:
            continue

        # 跳过 duration 为 0 的事件
        if e.duration_us <= 0:
            continue

        # 类别过滤
        if categories and e.category not in categories:
            continue

        intervals.append(HostInterval(
            start_us=e.timestamp_us,
            end_us=e.end_us,
            name=e.name,
            category=e.category,
            pid=e.pid,
            tid=e.tid,
        ))

    intervals.sort(key=lambda x: x.start_us)
    return intervals


def build_host_intervals_for_bubble_analysis(
    events: List[TraceEvent],
) -> Dict[str, List[HostInterval]]:
    """为气泡分析构建分类型的 host intervals。

    返回：
    {
        "all": [...],           # 所有 host 事件
        "sync": [...],          # Sync/H2D 标记
        "comm": [...],          # 通信标记
        "cpu_op": [...],        # CPU 算子
        "python": [...],        # Python 函数
        "ascendcl": [...],      # ACL 运行时
    }
    """
    all_intervals: List[HostInterval] = []
    sync_intervals: List[HostInterval] = []
    comm_intervals: List[HostInterval] = []
    cpu_op_intervals: List[HostInterval] = []
    python_intervals: List[HostInterval] = []
    ascendcl_intervals: List[HostInterval] = []

    for e in events:
        if e.duration_us <= 0:
            continue

        # 判断类别
        name_lower = e.name.lower()
        cat_lower = e.category.lower()

        is_sync = _matches_any(e.name, HostEventCategories.SYNC_PATTERNS) or \
                  _matches_any(cat_lower, HostEventCategories.SYNC_PATTERNS)
        is_comm = _matches_any(e.name, HostEventCategories.COMM_PATTERNS) or \
                  _matches_any(cat_lower, HostEventCategories.COMM_PATTERNS) or \
                  e.category in ("communication",)
        is_cpu_op = e.category in ("cpu_op",) or \
                    _matches_any(e.name, HostEventCategories.CPU_OP_PATTERNS)
        is_python = e.category in ("python_function",) or \
                    _matches_any(e.name, HostEventCategories.PYTHON_PATTERNS)
        is_ascendcl = e.category.startswith("AscendCL@") or \
                      _matches_any(e.name, HostEventCategories.ASCENDCL_PATTERNS) or \
                      _matches_any(cat_lower, HostEventCategories.ASCENDCL_PATTERNS)

        interval = HostInterval(
            start_us=e.timestamp_us,
            end_us=e.end_us,
            name=e.name,
            category=e.category,
            pid=e.pid,
            tid=e.tid,
        )

        all_intervals.append(interval)

        if is_sync:
            sync_intervals.append(interval)
        if is_comm:
            comm_intervals.append(interval)
        if is_cpu_op:
            cpu_op_intervals.append(interval)
        if is_python:
            python_intervals.append(interval)
        if is_ascendcl:
            ascendcl_intervals.append(interval)

    all_intervals.sort(key=lambda x: x.start_us)
    sync_intervals.sort(key=lambda x: x.start_us)
    comm_intervals.sort(key=lambda x: x.start_us)
    cpu_op_intervals.sort(key=lambda x: x.start_us)
    python_intervals.sort(key=lambda x: x.start_us)
    ascendcl_intervals.sort(key=lambda x: x.start_us)

    return {
        "all": all_intervals,
        "sync": sync_intervals,
        "comm": comm_intervals,
        "cpu_op": cpu_op_intervals,
        "python": python_intervals,
        "ascendcl": ascendcl_intervals,
    }


# ── 与 Bubble 重叠分析 ─────────────────────────────────────────────────────


def compute_overlap_ratio(
    bubble: Interval,
    intervals: Sequence[HostInterval],
) -> float:
    """计算气泡与 host intervals 的重叠比例。

    Formula: overlap_ratio = sum(clipped_overlaps) / bubble_duration
    """
    if bubble.dur_us <= 0:
        return 0.0

    total_overlap = 0.0
    for h in intervals:
        # 计算重叠
        left = max(bubble.start_us, h.start_us)
        right = min(bubble.end_us, h.end_us)
        if right > left:
            total_overlap += right - left

    return total_overlap / bubble.dur_us


def analyze_bubble_host_evidence(
    bubble: Interval,
    host_intervals: Dict[str, List[HostInterval]],
) -> Dict[str, Any]:
    """分析气泡窗口的 host 侧证据。

    Args:
        bubble: 气泡区间
        host_intervals: 分类型的 host intervals

    Returns:
        重叠比例分析结果
    """
    all_intervals = host_intervals.get("all", [])
    sync_intervals = host_intervals.get("sync", [])
    comm_intervals = host_intervals.get("comm", [])
    cpu_op_intervals = host_intervals.get("cpu_op", [])
    ascendcl_intervals = host_intervals.get("ascendcl", [])

    all_coverage = compute_overlap_ratio(bubble, all_intervals)
    sync_coverage = compute_overlap_ratio(bubble, sync_intervals)
    comm_coverage = compute_overlap_ratio(bubble, comm_intervals)
    cpu_op_coverage = compute_overlap_ratio(bubble, cpu_op_intervals)
    ascendcl_coverage = compute_overlap_ratio(bubble, ascendcl_intervals)

    # 收集覆盖该气泡的具体事件
    covering_events = []
    for h in all_intervals:
        if h.start_us < bubble.end_us and h.end_us > bubble.start_us:
            covering_events.append({
                "name": h.name,
                "category": h.category,
                "start_us": h.start_us,
                "end_us": h.end_us,
                "duration_us": h.dur_us,
            })

    return {
        "bubble_start_us": bubble.start_us,
        "bubble_end_us": bubble.end_us,
        "bubble_duration_us": bubble.dur_us,
        "all_coverage_ratio": round(all_coverage, 4),
        "sync_coverage_ratio": round(sync_coverage, 4),
        "comm_coverage_ratio": round(comm_coverage, 4),
        "cpu_op_coverage_ratio": round(cpu_op_coverage, 4),
        "ascendcl_coverage_ratio": round(ascendcl_coverage, 4),
        "covering_events": covering_events[:20],  # 最多 20 个事件
    }


# ── 工具函数 ────────────────────────────────────────────────────────────────


def detect_file_type(file_path: str) -> str:
    """检测 trace_view 系列文件。"""
    name = Path(file_path).name.lower()
    if "trace_view" in name and name.endswith(".json"):
        return "trace_view"
    return "unknown"


def get_trace_summary(events: List[TraceEvent]) -> Dict[str, Any]:
    """获取 trace 概要统计。"""
    categories: Dict[str, int] = {}
    names: Dict[str, int] = {}
    total_duration = 0.0

    for e in events:
        categories[e.category] = categories.get(e.category, 0) + 1
        names[e.name] = names.get(e.name, 0) + 1
        total_duration += e.duration_us

    return {
        "total_events": len(events),
        "total_duration_us": round(total_duration, 2),
        "categories": dict(sorted(categories.items(), key=lambda x: -x[1])[:20]),
        "top_names": dict(sorted(names.items(), key=lambda x: -x[1])[:20]),
    }
