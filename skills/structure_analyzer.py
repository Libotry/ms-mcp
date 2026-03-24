"""Structure Analyzer: Layer 分割 + Block/Side 四时钟视角

实现 SKILL.md 定义的两项分析能力：

P1-3: Structure (Layer) 分割
  - 使用 FIA (FusedInferAttentionScore) 作为主要结构标记
  - 基于 kernel name pattern 重复序列识别层
  - 分类层类型: Dense / MoE+DFC / MoE+GMM

P1-4: Block/Side 四时钟视角
  - Block = 主计算路径 (AI_CORE kernels 在主 stream 上)
  - Side = 辅助算子 (HCCL, AI_CPU, 小算子)
  - 四个时钟: wall_ms / busy_union_ms / kernel_sum_ms / total_cost_ms
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from .kernel_details_parser import KernelEntry
from .step_analyzer import Interval, merge_intervals


# ── Layer 类型定义 ───────────────────────────────────────────────────────────


class LayerType:
    """层类型常量。"""
    DENSE = "dense"
    MOE_DFC = "moe_dfc"
    MOE_GMM = "moe_gmm"
    EMBEDDING = "embedding"
    HEAD = "head"
    UNKNOWN = "unknown"


# ── Layer Kernel Pattern 定义 ───────────────────────────────────────────────


LAYER_PATTERNS = {
    # MoE+DFC 标记
    LayerType.MOE_DFC: {
        "dispatch_ffn_combine",  # DispatchFFNCombine
        "moefusion",  # MoEFusion
    },
    # MoE+GMM 标记
    LayerType.MOE_GMM: {
        "grouped_matmul",  # GroupedMatmul
        "alltoallv",
        "alltoall",
    },
    # Attention / Dense 层标记
    LayerType.DENSE: {
        "matmul",
        "softmax",
        "layernorm",
        "rmsnorm",
        "rope",
        "attention",
    },
}


def classify_kernel_for_layer(name: str) -> Set[str]:
    """根据 kernel name 判断可能的层类型。"""
    name_lower = name.lower()
    types: Set[str] = set()

    for layer_type, patterns in LAYER_PATTERNS.items():
        for pattern in patterns:
            if pattern in name_lower:
                types.add(layer_type)
                break

    return types


# ── Structure/Layer 数据结构 ───────────────────────────────────────────────


@dataclass
class StructureSegment:
    """单个结构段（层）。"""
    structure_id: str  # e.g., "layer_0", "layer_1"
    structure_type: str  # LayerType 常量
    start_us: float
    end_us: float
    kernel_count: int
    kernels: List[KernelEntry] = field(default_factory=list)

    @property
    def wall_ms(self) -> float:
        return (self.end_us - self.start_us) / 1000.0


@dataclass
class BlockSideMetrics:
    """Block/Side 四时钟视角指标。"""
    # Block metrics
    block_wall_ms: float = 0.0
    block_busy_union_ms: float = 0.0
    block_kernel_sum_ms: float = 0.0
    block_total_cost_ms: float = 0.0
    block_kernel_count: int = 0
    block_dominant_task_type: str = ""

    # Side metrics
    side_wall_ms: float = 0.0
    side_busy_union_ms: float = 0.0
    side_kernel_sum_ms: float = 0.0
    side_total_cost_ms: float = 0.0
    side_kernel_count: int = 0
    side_dominant_task_type: str = ""

    # Ratio
    block_share_of_wall: float = 0.0
    block_share_of_compute: float = 0.0


# ── Structure 分割核心 ─────────────────────────────────────────────────────


def find_fia_kernels(kernels: List[KernelEntry]) -> List[KernelEntry]:
    """从 kernel 列表中找到所有 FIA (FusedInferAttentionScore) kernels。"""
    fia_kernels = []
    for k in kernels:
        name_lower = k.name.lower()
        if "fusedinferattentionscore" in name_lower or "fia" in name_lower:
            fia_kernels.append(k)
    return sorted(fia_kernels, key=lambda x: x.start_us)


def segment_by_fia(
    kernels: List[KernelEntry],
    fia_kernels: List[KernelEntry],
) -> List[StructureSegment]:
    """基于 FIA kernels 对 kernel 序列进行分段。

    相邻两个 FIA 之间的 kernels 属于同一个 layer。

    Returns:
        StructureSegment 列表
    """
    if not fia_kernels:
        # 没有 FIA，回退到基于 kernel name pattern 的分割
        return segment_by_pattern(kernels)

    structures: List[StructureSegment] = []
    kernels_sorted = sorted(kernels, key=lambda x: x.start_us)

    for i, fia in enumerate(fia_kernels):
        # 确定该 layer 的时间范围
        start_us = fia.start_us
        if i + 1 < len(fia_kernels):
            end_us = fia_kernels[i + 1].start_us
        else:
            # 最后一个 layer：到下一个结构或 step 结束
            end_us = max(k.start_us + k.duration_us for k in kernels_sorted)

        # 收集该 layer 内的所有 kernels
        layer_kernels = [
            k for k in kernels_sorted
            if k.start_us >= start_us and k.start_us < end_us
        ]

        # 分类层类型
        layer_type = classify_layer_type(layer_kernels)

        structures.append(StructureSegment(
            structure_id=f"layer_{i}",
            structure_type=layer_type,
            start_us=start_us,
            end_us=end_us,
            kernel_count=len(layer_kernels),
            kernels=layer_kernels,
        ))

    return structures


def segment_by_pattern(kernels: List[KernelEntry]) -> List[StructureSegment]:
        """基于 kernel name pattern 重复序列进行分割。

        当没有 FIA 时使用此方法。
        寻找最长的重复 kernel name 序列作为 layer。
        """
        if not kernels:
            return []

        kernels_sorted = sorted(kernels, key=lambda x: x.start_us)
        names = [k.name for k in kernels_sorted]

        # 寻找重复模式
        # 简化：使用滑动窗口找最长重复子序列
        structures: List[StructureSegment] = []

        # 计算可能的 layer 数量（基于 kernel 数量）
        # 假设每个 layer 平均 100-200 个 kernels
        total_kernels = len(names)
        if total_kernels < 20:
            # 太少，直接作为一个结构
            return [StructureSegment(
                structure_id="layer_0",
                structure_type=LayerType.UNKNOWN,
                start_us=kernels_sorted[0].start_us,
                end_us=kernels_sorted[-1].start_us + kernels_sorted[-1].duration_us,
                kernel_count=len(kernels_sorted),
                kernels=kernels_sorted,
            )]

        # 估计 layer 数（简化处理）
        estimated_layers = max(1, total_kernels // 100)
        kernels_per_layer = total_kernels // estimated_layers

        for i in range(estimated_layers):
            start_idx = i * kernels_per_layer
            if i == estimated_layers - 1:
                end_idx = total_kernels
            else:
                end_idx = start_idx + kernels_per_layer

            layer_kernels = kernels_sorted[start_idx:end_idx]
            layer_type = classify_layer_type(layer_kernels)

            structures.append(StructureSegment(
                structure_id=f"layer_{i}",
                structure_type=layer_type,
                start_us=layer_kernels[0].start_us,
                end_us=layer_kernels[-1].start_us + layer_kernels[-1].duration_us,
                kernel_count=len(layer_kernels),
                kernels=layer_kernels,
            ))

        return structures


def classify_layer_type(layer_kernels: List[KernelEntry]) -> str:
    """根据 layer 内的 kernels 分类层类型。"""
    kernel_names = " ".join(k.name.lower() for k in layer_kernels)
    kernel_types = Counter(k.task_type for k in layer_kernels)

    # 检查 MoE+DFC 标记
    moe_dfc_markers = sum(
        1 for k in layer_kernels
        if "dispatchffncombine" in k.name.lower() or "moefusion" in k.name.lower()
    )

    # 检查 MoE+GMM 标记
    moe_gmm_markers = sum(
        1 for k in layer_kernels
        if "groupedmatmul" in k.name.lower() or "alltoall" in k.name.lower()
    )

    if moe_dfc_markers > 0:
        return LayerType.MOE_DFC
    if moe_gmm_markers > 0:
        return LayerType.MOE_GMM

    # 检查是否为 embedding/head
    first_layer = layer_kernels[0] if layer_kernels else None
    if first_layer and first_layer.start_us < 1000000:  # 第一个 kernel 在 1s 内
        return LayerType.EMBEDDING

    # 检查是否为 head
    if "logits" in kernel_names or "output" in kernel_names or "head" in kernel_names:
        return LayerType.HEAD

    # 默认为 Dense
    return LayerType.DENSE


# ── Block/Side 四时钟视角 ──────────────────────────────────────────────────


def compute_block_side_metrics(
    kernels: List[KernelEntry],
) -> BlockSideMetrics:
    """计算 Block/Side 的四时钟视角指标。

    分类规则（kernel_data_guide.md Section 4.1）：
    - Block: 主计算路径，主流上的 AI_CORE kernels
    - Side: HCCL, AI_CPU, 小算子(kernel duration < 10us)

    Args:
        kernels: 该 structure/layer 内的所有 kernels

    Returns:
        BlockSideMetrics
    """
    if not kernels:
        return BlockSideMetrics()

    # 按 stream 分组
    stream_kernels: Dict[int, List[KernelEntry]] = {}
    for k in kernels:
        stream_kernels.setdefault(k.stream_id, []).append(k)

    # 找出主 stream（kernel 数量最多的）
    main_stream_id = max(stream_kernels.keys(), key=lambda sid: len(stream_kernels[sid]))

    block_kernels: List[KernelEntry] = []
    side_kernels: List[KernelEntry] = []

    for k in kernels:
        is_small = k.duration_us < 10.0
        is_hccl = "HCCL" in k.task_type or "Hcom" in k.task_type
        is_aicpu = k.task_type == "AI_CPU"

        if is_hccl or is_aicpu or is_small:
            side_kernels.append(k)
        elif k.stream_id == main_stream_id and k.task_type == "AI_CORE":
            block_kernels.append(k)
        else:
            # 其他放在 side
            side_kernels.append(k)

    # 计算 Block 四时钟
    block_metrics = _compute_four_clock(block_kernels)
    side_metrics = _compute_four_clock(side_kernels)

    # Block 在总 compute 中的占比
    total_wall = block_metrics.wall_ms + side_metrics.wall_ms
    total_compute = block_metrics.kernel_sum_ms + side_metrics.kernel_sum_ms

    # Dominant task type
    block_task_counts = Counter(k.task_type for k in block_kernels)
    side_task_counts = Counter(k.task_type for k in side_kernels)

    return BlockSideMetrics(
        block_wall_ms=block_metrics.wall_ms,
        block_busy_union_ms=block_metrics.busy_union_ms,
        block_kernel_sum_ms=block_metrics.kernel_sum_ms,
        block_total_cost_ms=block_metrics.total_cost_ms,
        block_kernel_count=len(block_kernels),
        block_dominant_task_type=block_task_counts.most_common(1)[0][0] if block_task_counts else "",
        side_wall_ms=side_metrics.wall_ms,
        side_busy_union_ms=side_metrics.busy_union_ms,
        side_kernel_sum_ms=side_metrics.kernel_sum_ms,
        side_total_cost_ms=side_metrics.total_cost_ms,
        side_kernel_count=len(side_kernels),
        side_dominant_task_type=side_task_counts.most_common(1)[0][0] if side_task_counts else "",
        block_share_of_wall=block_metrics.wall_ms / total_wall if total_wall > 0 else 0,
        block_share_of_compute=block_metrics.kernel_sum_ms / total_compute if total_compute > 0 else 0,
    )


def _compute_four_clock(kernels: List[KernelEntry]) -> BlockSideMetrics:
    """计算四个时钟视角。

    - wall_ms: 第一个 kernel 开始到最后一个 kernel 结束
    - busy_union_ms: 合并后的设备忙时间（跨 stream）
    - kernel_sum_ms: 所有 kernel duration 算术和
    - total_cost_ms: duration + wait 之和
    """
    if not kernels:
        return BlockSideMetrics()

    # Sort by start time
    sorted_kernels = sorted(kernels, key=lambda x: x.start_us)

    # wall_ms
    first_start = min(k.start_us for k in kernels)
    last_end = max(k.start_us + k.duration_us for k in kernels)
    wall_ms = (last_end - first_start) / 1000.0

    # kernel_sum_ms
    kernel_sum_ms = sum(k.duration_us for k in kernels) / 1000.0

    # total_cost_ms
    total_cost_ms = sum(k.total_cost_us for k in kernels) / 1000.0

    # busy_union_ms
    intervals = [
        Interval(k.start_us, k.start_us + k.duration_us)
        for k in kernels
    ]
    merged = merge_intervals(intervals)
    busy_union_ms = sum(i.dur_us for i in merged) / 1000.0

    return BlockSideMetrics(
        block_wall_ms=wall_ms,
        block_busy_union_ms=busy_union_ms,
        block_kernel_sum_ms=kernel_sum_ms,
        block_total_cost_ms=total_cost_ms,
    )


# ── Structure 分析报告 ──────────────────────────────────────────────────────


@dataclass
class StructureAnalysisResult:
    """单个 Structure 的完整分析结果。"""
    structure_id: str
    structure_type: str
    wall_ms: float
    kernel_count: int
    layer_classification: str  # 层类型描述
    block_metrics: BlockSideMetrics
    top_kernels_by_duration: List[Dict[str, Any]]
    top_kernels_by_cost: List[Dict[str, Any]]


def analyze_structure(
    segment: StructureSegment,
    top_n: int = 5,
) -> StructureAnalysisResult:
    """分析单个 Structure。"""
    kernels = segment.kernels

    # 计算 Block/Side metrics
    block_side = compute_block_side_metrics(kernels)

    # Top kernels by duration
    by_duration = sorted(kernels, key=lambda x: x.duration_us, reverse=True)
    top_duration = [
        {
            "name": k.name,
            "task_type": k.task_type,
            "duration_us": round(k.duration_us, 2),
            "wait_us": round(k.wait_us, 2),
            "total_cost_us": round(k.total_cost_us, 2),
        }
        for k in by_duration[:top_n]
    ]

    # Top kernels by total_cost
    by_cost = sorted(kernels, key=lambda x: x.total_cost_us, reverse=True)
    top_cost = [
        {
            "name": k.name,
            "task_type": k.task_type,
            "duration_us": round(k.duration_us, 2),
            "wait_us": round(k.wait_us, 2),
            "total_cost_us": round(k.total_cost_us, 2),
        }
        for k in by_cost[:top_n]
    ]

    # 层类型描述
    layer_desc = {
        LayerType.DENSE: "Dense layer",
        LayerType.MOE_DFC: "MoE layer (DFC fused)",
        LayerType.MOE_GMM: "MoE layer (GMM)",
        LayerType.EMBEDDING: "Embedding layer",
        LayerType.HEAD: "Output head",
        LayerType.UNKNOWN: "Unknown layer",
    }.get(segment.structure_type, "Unknown layer")

    return StructureAnalysisResult(
        structure_id=segment.structure_id,
        structure_type=segment.structure_type,
        wall_ms=segment.wall_ms,
        kernel_count=len(kernels),
        layer_classification=layer_desc,
        block_metrics=block_side,
        top_kernels_by_duration=top_duration,
        top_kernels_by_cost=top_cost,
    )


def analyze_step_structures(
    step_kernels: List[KernelEntry],
    fia_kernels: Optional[List[KernelEntry]] = None,
) -> List[StructureAnalysisResult]:
    """分析 Step 的所有 Structure。

    Args:
        step_kernels: 该 step 的所有 kernels
        fia_kernels: 可选的 FIA kernels 列表（用于分割）

    Returns:
        StructureAnalysisResult 列表
    """
    if not step_kernels:
        return []

    # 分割 structure
    if fia_kernels:
        segments = segment_by_fia(step_kernels, fia_kernels)
    else:
        segments = segment_by_pattern(step_kernels)

    # 分析每个 segment
    return [analyze_structure(seg) for seg in segments]


# ── 辅助 ─────────────────────────────────────────────────────────────────


from collections import Counter
from typing import Dict
