"""Model Architecture Report Generator

根据 SKILL.md 和 architecture_report_template.md 生成完整的 Model Architecture Markdown 报告。

报告必须包含 10 个章节：
1. Configuration Context — 并行配置、序列长度、batch size
2. Model Architecture Determination — FIA 证据链
3. Forward Pass Boundaries — per-pass 时间范围
4. Layer Classification — 层类型分类表
5. Cross-Verification Table — per-pass op 计数验证
6. Per-Layer Sub-Structure — 每个层类型的核函数序列树
7. Decode Phase Analysis — decode 层 vs prefill 对比
8. Communication Pipeline Structure — stream 角色 + ASCII 流水线图
9. Layer-to-Layer Variation — 层类型横向对比
10. Model Architecture Summary — ASCII 模型图 + 执行时间线
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .kernel_details_parser import KernelEntry, aggregate_by_op, compute_op_rankings
from .structure_analyzer import (
    LayerType,
    find_fia_kernels,
    segment_by_fia,
    classify_layer_type,
    compute_block_side_metrics,
    analyze_step_structures,
)
from .step_analyzer import merge_intervals


# ── 数据结构 ────────────────────────────────────────────────────────────────


@dataclass
class FIAInfo:
    """FIA (FusedInferAttentionScore) 调用信息。"""
    name: str
    start_us: float
    duration_us: float
    end_us: float
    is_prefill: bool  # duration > 10ms = prefill, < 1ms = decode
    layer_index: int


@dataclass
class PassInfo:
    """单个 Forward Pass 的信息。"""
    pass_index: int
    fia_range: Tuple[int, int]  # (start_idx, end_idx)
    start_us: float
    end_us: float
    wall_time_ms: float
    avg_fia_duration_ms: float
    kernel_count: int
    is_prefill: bool


@dataclass
class LayerInfo:
    """单个 Layer 的信息。"""
    layer_index: int
    layer_type: str  # dense / moe_dfc / moe_gmm / embedding / head / unknown
    fia_duration_ms: float
    wall_time_ms: float
    kernel_count: int
    kernel_names: List[str]
    block_metrics: Optional[Any] = None


@dataclass
class ArchitectureReportData:
    """架构报告数据（从 profiling 数据提取）。"""
    profiling_dir_name: str
    # Configuration Context
    parallelism_config: str = "unknown"
    sequence_length: str = "unknown"
    batch_size: str = "unknown"
    # FIA Analysis
    total_fia_count: int = 0
    prefill_fia_count: int = 0
    decode_fia_count: int = 0
    fia_infos: List[FIAInfo] = field(default_factory=list)
    # Pass Analysis
    passes: List[PassInfo] = field(default_factory=list)
    # Layer Analysis
    layers: List[LayerInfo] = field(default_factory=list)
    layer_type_counts: Dict[str, int] = field(default_factory=dict)
    # Cross-verification
    op_counts: Dict[str, int] = field(default_factory=dict)
    # Communication
    has_communication: bool = False
    stream_count: int = 0
    # Overall
    total_kernel_count: int = 0
    total_wall_time_ms: float = 0.0


# ── 数据提取 ────────────────────────────────────────────────────────────────


def extract_architecture_data(
    kernels: List[KernelEntry],
    profiling_dir_name: str,
) -> ArchitectureReportData:
    """从 kernel 列表提取架构数据。

    Args:
        kernels: 所有 kernel 数据
        profiling_dir_name: 目录名（用于报告）

    Returns:
        ArchitectureReportData
    """
    data = ArchitectureReportData(profiling_dir_name=profiling_dir_name)

    if not kernels:
        return data

    # 按时间排序
    kernels_sorted = sorted(kernels, key=lambda x: x.start_us)

    # 总览
    data.total_kernel_count = len(kernels)
    data.total_wall_time_ms = (
        max(k.start_us + k.duration_us for k in kernels) - min(k.start_us for k in kernels)
    ) / 1000.0

    # Stream 统计
    data.stream_count = len(set(k.stream_id for k in kernels))

    # 是否有通信算子
    data.has_communication = any(
        "HCCL" in k.task_type or "Hcom" in k.task_type
        for k in kernels
    )

    # FIA 分析
    fia_kernels = find_fia_kernels(kernels)
    data.total_fia_count = len(fia_kernels)

    fia_infos: List[FIAInfo] = []
    for i, fia in enumerate(fia_kernels):
        is_prefill = fia.duration_us > 10000  # > 10ms
        if is_prefill:
            data.prefill_fia_count += 1
        else:
            data.decode_fia_count += 1

        fia_infos.append(FIAInfo(
            name=fia.name,
            start_us=fia.start_us,
            duration_us=fia.duration_us,
            end_us=fia.start_us + fia.duration_us,
            is_prefill=is_prefill,
            layer_index=i,
        ))

    data.fia_infos = fia_infos

    # 如果有 FIA，进行 Pass 和 Layer 分析
    if fia_infos:
        # 估计 pass 数（简化：假设每 pass 有 90-100 层）
        avg_fia_per_pass = 95  # typical for large models
        estimated_passes = max(1, len(fia_infos) // avg_fia_per_pass)

        # Pass 分析
        pass_size = len(fia_infos) // estimated_passes
        for p in range(estimated_passes):
            start_idx = p * pass_size
            end_idx = start_idx + pass_size if p < estimated_passes - 1 else len(fia_infos)
            pass_fias = fia_infos[start_idx:end_idx]

            if not pass_fias:
                continue

            pass_wall = (
                pass_fias[-1].end_us - pass_fias[0].start_us
            ) / 1000.0
            avg_dur = sum(f.duration_us for f in pass_fias) / len(pass_fias) / 1000.0

            data.passes.append(PassInfo(
                pass_index=p,
                fia_range=(start_idx, end_idx),
                start_us=pass_fias[0].start_us,
                end_us=pass_fias[-1].end_us,
                wall_time_ms=pass_wall,
                avg_fia_duration_ms=avg_dur,
                kernel_count=0,  # 需要重新统计
                is_prefill=pass_fias[0].is_prefill,
            ))

        # Layer 分析（基于 FIA）
        for i, fia in enumerate(fia_infos):
            # 找到该 layer 的 kernels
            start_us = fia.start_us
            end_us = fia_infos[i + 1].start_us if i + 1 < len(fia_infos) else (
                max(k.start_us + k.duration_us for k in kernels)
            )

            layer_kernels = [
                k for k in kernels_sorted
                if k.start_us >= start_us and k.start_us < end_us
            ]

            layer_type = classify_layer_type(layer_kernels)

            # 统计 kernel names
            from collections import Counter
            name_counts = Counter(k.name for k in layer_kernels)
            top_names = [n for n, _ in name_counts.most_common(10)]

            # Block/Side metrics
            block_metrics = compute_block_side_metrics(layer_kernels)

            data.layers.append(LayerInfo(
                layer_index=i,
                layer_type=layer_type,
                fia_duration_ms=fia.duration_us / 1000.0,
                wall_time_ms=(end_us - start_us) / 1000.0,
                kernel_count=len(layer_kernels),
                kernel_names=top_names,
                block_metrics=block_metrics,
            ))

        # Layer 类型统计
        data.layer_type_counts = {
            lt: sum(1 for l in data.layers if l.layer_type == lt)
            for lt in set(l.layer_type for l in data.layers)
        }

    # Op counts 交叉验证
    op_stats = aggregate_by_op(kernels)
    data.op_counts = {
        name: stats.count
        for name, stats in list(op_stats.items())[:20]
    }

    return data


# ── 报告生成 ────────────────────────────────────────────────────────────────


def generate_architecture_report(
    data: ArchitectureReportData,
    output_dir: Optional[Path] = None,
) -> str:
    """生成完整的 Model Architecture Markdown 报告。

    Args:
        data: 架构数据
        output_dir: 可选的输出目录（如果指定则保存文件）

    Returns:
        Markdown 格式的报告字符串
    """
    lines: List[str] = []

    # 标题
    lines.append(f"# Model Architecture Report: {data.profiling_dir_name}")
    lines.append("")
    lines.append(f"**Generated from Ascend NPU Profiling Data**")
    lines.append("")

    # ═══════════════════════════════════════════════════════════════
    # Section 1: Configuration Context
    # ═══════════════════════════════════════════════════════════════
    lines.append("## 1. Configuration Context")
    lines.append("")
    lines.append("| Parameter | Value |")
    lines.append("|-----------|-------|")
    lines.append(f"| Parallelism | {data.parallelism_config} |")
    lines.append(f"| Sequence Length | {data.sequence_length} |")
    lines.append(f"| Batch Size | {data.batch_size} |")
    lines.append(f"| Total Device Kernels | {data.total_kernel_count:,} |")
    lines.append(f"| Total Wall Time | {data.total_wall_time_ms:.2f} ms |")
    lines.append(f"| Device Streams | {data.stream_count} |")
    lines.append(f"| Has Communication | {'Yes' if data.has_communication else 'No'} |")
    lines.append("")

    # ═══════════════════════════════════════════════════════════════
    # Section 2: Model Architecture Determination
    # ═══════════════════════════════════════════════════════════════
    lines.append("## 2. Model Architecture Determination")
    lines.append("")
    lines.append("### Evidence Chain")
    lines.append("")
    lines.append("| Evidence | Value | Interpretation |")
    lines.append("|----------|-------|---------------|")
    lines.append(f"| Total FIA Invocations | {data.total_fia_count} | One FIA per layer per pass |")
    lines.append(f"| Prefill FIA (>{'>'}10ms) | {data.prefill_fia_count} | Forward pass layers |")
    lines.append(f"| Decode FIA (<{'>'}1ms) | {data.decode_fia_count} | Decode/generation layers |")
    if data.passes:
        lines.append(f"| Estimated Passes | {len(data.passes)} | Forward passes captured |")
    lines.append("")

    # ═══════════════════════════════════════════════════════════════
    # Section 3: Forward Pass Boundaries
    # ═══════════════════════════════════════════════════════════════
    lines.append("## 3. Forward Pass Boundaries")
    lines.append("")
    if data.passes:
        lines.append("| Pass | FIA Range | Wall Time (ms) | Avg FIA Duration (ms) | Type |")
        lines.append("|------|------------|----------------|----------------------|------|")
        for p in data.passes:
            lines.append(
                f"| Pass {p.pass_index} | {p.fia_range[0]}-{p.fia_range[1]} | "
                f"{p.wall_time_ms:.2f} | {p.avg_fia_duration_ms:.2f} | "
                f"{'Prefill' if p.is_prefill else 'Decode'} |"
            )
    else:
        lines.append("*No pass boundary information available.*")
    lines.append("")

    # ═══════════════════════════════════════════════════════════════
    # Section 4: Layer Classification
    # ═══════════════════════════════════════════════════════════════
    lines.append("## 4. Layer Classification")
    lines.append("")
    if data.layer_type_counts:
        lines.append("### Layer Type Summary")
        lines.append("")
        lines.append("| Layer Type | Count | Description |")
        lines.append("|-----------|-------|-------------|")
        type_descriptions = {
            LayerType.DENSE: "Dense transformer layer (attention + FFN)",
            LayerType.MOE_DFC: "MoE layer with fused DFC (DispatchFFNCombine)",
            LayerType.MOE_GMM: "MoE layer with GroupedMatmul",
            LayerType.EMBEDDING: "Embedding/input layer",
            LayerType.HEAD: "Output head layer",
            LayerType.UNKNOWN: "Unclassified layer",
        }
        for lt, count in sorted(data.layer_type_counts.items(), key=lambda x: -x[1]):
            desc = type_descriptions.get(lt, "Unknown")
            lines.append(f"| {lt} | {count} | {desc} |")
        lines.append("")
    else:
        lines.append("*No layer classification available (no FIA kernels found).*")
    lines.append("")

    # ═══════════════════════════════════════════════════════════════
    # Section 5: Cross-Verification Table
    # ═══════════════════════════════════════════════════════════════
    lines.append("## 5. Cross-Verification Table")
    lines.append("")
    lines.append("| Op Category | Count | Interpretation |")
    lines.append("|------------|-------|---------------|")
    if data.op_counts:
        for op_name, count in list(data.op_counts.items())[:15]:
            lines.append(f"| {op_name} | {count} | |")
    else:
        lines.append("| - | - | No op data available |")
    lines.append("")
    lines.append("*Note: Verify that op counts are consistent with layer classification.*")
    lines.append("")

    # ═══════════════════════════════════════════════════════════════
    # Section 6: Per-Layer Sub-Structure
    # ═══════════════════════════════════════════════════════════════
    lines.append("## 6. Per-Layer Sub-Structure")
    lines.append("")
    if data.layers:
        # 按类型分组展示
        layers_by_type: Dict[str, List[LayerInfo]] = {}
        for layer in data.layers:
            layers_by_type.setdefault(layer.layer_type, []).append(layer)

        for lt, lt_layers in sorted(layers_by_type.items(), key=lambda x: -len(x[1])):
            if not lt_layers:
                continue
            lines.append(f"### {lt.upper()} Layer Type ({len(lt_layers)} layers)")
            lines.append("")

            # 展示第一个作为代表
            sample = lt_layers[0]
            lines.append(f"**Sample Layer ({sample.layer_index}) Kernel Sequence:**")
            lines.append("")
            lines.append("```")
            lines.append(f"FIA ({sample.fia_duration_ms:.2f}ms)")
            for kn in sample.kernel_names[:8]:
                lines.append(f"├─ {kn}")
            if len(sample.kernel_names) > 8:
                lines.append(f"└─ ... ({len(sample.kernel_names) - 8} more)")
            lines.append("```")
            lines.append("")
            lines.append(f"| Metric | Value |")
            lines.append("|--------|-------|")
            lines.append(f"| Wall Time | {sample.wall_time_ms:.2f} ms |")
            lines.append(f"| Kernel Count | {sample.kernel_count} |")
            if sample.block_metrics:
                bm = sample.block_metrics
                lines.append(f"| Block Compute Share | {bm.block_share_of_compute:.1%} |")
            lines.append("")
    else:
        lines.append("*No per-layer structure data available.*")
    lines.append("")

    # ═══════════════════════════════════════════════════════════════
    # Section 7: Decode Phase Analysis
    # ═══════════════════════════════════════════════════════════════
    lines.append("## 7. Decode Phase Analysis")
    lines.append("")
    if data.decode_fia_count > 0:
        decode_layers = [l for l in data.layers if not any(
            fia.is_prefill for fia in data.fia_infos if
            l.layer_index == data.fia_infos.index(fia)
        )]
        if decode_layers:
            lines.append("| Metric | Prefill | Decode |")
            lines.append("|--------|---------|-------|")
            avg_prefill = sum(l.fia_duration_ms for l in data.layers if l not in decode_layers) / max(1, len(data.layers) - len(decode_layers))
            avg_decode = sum(l.fia_duration_ms for l in decode_layers) / max(1, len(decode_layers))
            lines.append(f"| Avg FIA Duration | {avg_prefill:.2f} ms | {avg_decode:.2f} ms |")
            lines.append(f"| Layer Count | {len(data.layers) - len(decode_layers)} | {len(decode_layers)} |")
            lines.append("")
        lines.append("*Decode phase shows significantly shorter FIA durations due to caching and reduced compute.*")
    else:
        lines.append("*No decode phase detected in this profiling capture.*")
    lines.append("")

    # ═══════════════════════════════════════════════════════════════
    # Section 8: Communication Pipeline Structure
    # ═══════════════════════════════════════════════════════════════
    lines.append("## 8. Communication Pipeline Structure")
    lines.append("")
    if data.has_communication:
        lines.append("| Stream | Purpose |")
        lines.append("|--------|---------|")
        lines.append("| 0 | Main compute stream (AI_CORE) |")
        lines.append("| 1 | Communication stream (HCCL) |")
        lines.append("| 2+ | Auxiliary streams |")
        lines.append("")
        lines.append("**Pipeline Overlap Analysis:**")
        lines.append("")
        lines.append("Communication overlaps with compute via multi-stream execution.")
        lines.append("Overlap ratio can be estimated from kernel timing relationships.")
        lines.append("")
    else:
        lines.append("*No significant communication patterns detected in this capture.*")
    lines.append("")

    # ═══════════════════════════════════════════════════════════════
    # Section 9: Layer-to-Layer Variation
    # ═══════════════════════════════════════════════════════════════
    lines.append("## 9. Layer-to-Layer Variation")
    lines.append("")
    if data.layers:
        lines.append("| Layer | Type | Wall Time (ms) | Kernels |")
        lines.append("|-------|------|----------------|---------|")
        # 展示前 10 层和后 5 层
        for layer in data.layers[:10]:
            lines.append(
                f"| {layer.layer_index} | {layer.layer_type} | "
                f"{layer.wall_time_ms:.2f} | {layer.kernel_count} |"
            )
        if len(data.layers) > 15:
            lines.append("| ... | | | |")
            for layer in data.layers[-5:]:
                lines.append(
                    f"| {layer.layer_index} | {layer.layer_type} | "
                    f"{layer.wall_time_ms:.2f} | {layer.kernel_count} |"
                )
    else:
        lines.append("*No layer variation data available.*")
    lines.append("")

    # ═══════════════════════════════════════════════════════════════
    # Section 10: Model Architecture Summary
    # ═══════════════════════════════════════════════════════════════
    lines.append("## 10. Model Architecture Summary")
    lines.append("")

    # ASCII 模型图
    lines.append("### Model Structure")
    lines.append("")
    lines.append("```")
    if data.layer_type_counts:
        layer_desc = []
        for lt, count in sorted(data.layer_type_counts.items(), key=lambda x: -x[1]):
            if count > 0:
                layer_desc.append(f"{count}x {lt}")
        lines.append(f"Transformer Model ({', '.join(layer_desc)})")
    else:
        lines.append("Model (structure unknown)")
    lines.append(f"Total Layers: {len(data.layers)}")
    lines.append(f"Prefill FIA: {data.prefill_fia_count}")
    lines.append(f"Decode FIA: {data.decode_fia_count}")
    lines.append("```")
    lines.append("")

    # 执行时间线
    lines.append("### Execution Timeline")
    lines.append("")
    if data.passes:
        timeline_start = 0.0
        for p in data.passes:
            bar_len = min(50, max(10, int(p.wall_time_ms / data.total_wall_time_ms * 100)))
            bar = "█" * bar_len
            lines.append(
                f"Pass {p.pass_index}: [{bar}] {p.wall_time_ms:.2f}ms "
                f"({'Prefill' if p.is_prefill else 'Decode'})"
            )
    lines.append("")
    lines.append(f"Total Wall Time: {data.total_wall_time_ms:.2f} ms")
    lines.append("")

    # Footer
    lines.append("---")
    lines.append("*Report generated by ms-mcp Ascend Profiling Analyzer*")

    report_content = "\n".join(lines)

    # 保存文件
    if output_dir:
        output_path = output_dir / f"model_architecture_report_{data.profiling_dir_name}.md"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report_content)

    return report_content


# ── 入口函数 ────────────────────────────────────────────────────────────────


def generate_report_from_directory(
    profiling_dir: Path,
    output_dir: Optional[Path] = None,
) -> Tuple[str, Optional[Path]]:
    """从 profiling 目录生成架构报告。

    Args:
        profiling_dir: Profiling 数据目录
        output_dir: 可选的输出目录（默认与 profiling_dir 相同）

    Returns:
        (markdown_report, output_path)
    """
    from .kernel_details_parser import parse_kernel_details

    # 查找 kernel_details 文件
    kernel_files = sorted(profiling_dir.glob("kernel_details*.csv"))
    if not kernel_files:
        return "*No kernel_details file found. Architecture report requires kernel_details*.csv.*", None

    kernel_file = kernel_files[0]
    kernels = parse_kernel_details(str(kernel_file))

    if kernels.empty:
        return "*kernel_details file is empty.*", None

    # 提取数据
    dir_name = profiling_dir.name
    data = extract_architecture_data(kernels, dir_name)

    # 生成报告
    if output_dir is None:
        output_dir = profiling_dir

    report = generate_architecture_report(data, output_dir)

    output_path = output_dir / f"model_architecture_report_{dir_name}.md"

    return report, output_path
