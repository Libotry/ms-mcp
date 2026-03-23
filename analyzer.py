"""Profiling 数据解析与性能瓶颈分析模块。

支持解析 msprof 导出的 CSV 和 DB 格式性能数据，
自动识别高耗时算子、内存瓶颈、通信瓶颈等问题并给出优化建议。
"""

import csv
import sqlite3
from pathlib import Path


# ── CSV 解析 ──────────────────────────────────────────────


def _read_csv(file_path: str) -> list[dict]:
    """读取 CSV 文件，返回字典列表。"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    # 尝试多种编码
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


def analyze_op_summary(file_path: str, top_n: int = 10) -> dict:
    """分析 op_summary CSV，找出高耗时算子和潜在瓶颈。"""
    rows = _read_csv(file_path)
    if not rows:
        return {"error": "文件为空或无有效数据"}

    # 按 Task Duration 排序
    dur_key = None
    for key in rows[0]:
        if "Task Duration" in key or "task_time" in key:
            dur_key = key
            break

    if not dur_key:
        return {"error": f"未找到耗时字段，可用字段: {list(rows[0].keys())[:10]}"}

    for row in rows:
        row["_duration"] = _safe_float(row.get(dur_key, "0"))

    rows.sort(key=lambda r: r["_duration"], reverse=True)
    total_time = sum(r["_duration"] for r in rows)

    # Top-N 算子
    top_ops = []
    for row in rows[:top_n]:
        op_info = {
            "name": row.get("Op Name", row.get("kernel_name", "unknown")),
            "type": row.get("OP Type", row.get("Task Type", "unknown")),
            "task_type": row.get("Task Type", "unknown"),
            "duration_us": row["_duration"],
            "ratio": round(row["_duration"] / total_time * 100, 2) if total_time > 0 else 0,
        }
        # memory bound 检查
        if "memory_bound" in row:
            op_info["memory_bound"] = row["memory_bound"]
        if "cube_utilization(%)" in row:
            op_info["cube_utilization"] = row["cube_utilization(%)"]
        top_ops.append(op_info)

    # 按 Task Type 分布
    type_dist: dict[str, float] = {}
    for row in rows:
        tt = row.get("Task Type", "unknown")
        type_dist[tt] = type_dist.get(tt, 0) + row["_duration"]

    # 客观事实标记（不含主观建议，由 LLM 自行生成建议）
    findings = []
    if top_ops and top_ops[0]["ratio"] > 30:
        findings.append({
            "type": "dominant_op",
            "op_name": top_ops[0]["name"],
            "ratio_pct": top_ops[0]["ratio"],
        })

    ai_cpu_time = type_dist.get("AI_CPU", 0)
    if total_time > 0 and ai_cpu_time / total_time > 0.1:
        ratio = round(ai_cpu_time / total_time * 100, 2)
        findings.append({
            "type": "high_ai_cpu_ratio",
            "ratio_pct": ratio,
            "ai_cpu_time_us": round(ai_cpu_time, 2),
        })

    for op in top_ops:
        if op.get("memory_bound", "").lower() == "true":
            findings.append({
                "type": "memory_bound_op",
                "op_name": op["name"],
                "duration_us": op["duration_us"],
            })

    return {
        "total_ops": len(rows),
        "total_time_us": round(total_time, 2),
        "top_ops": top_ops,
        "type_distribution": {
            k: {"time_us": round(v, 2), "ratio": round(v / total_time * 100, 2) if total_time > 0 else 0}
            for k, v in sorted(type_dist.items(), key=lambda x: x[1], reverse=True)
        },
        "findings": findings,
    }


def analyze_op_statistic(file_path: str) -> dict:
    """分析 op_statistic CSV，统计各类算子的调用次数和耗时。"""
    rows = _read_csv(file_path)
    if not rows:
        return {"error": "文件为空或无有效数据"}

    total_time = sum(_safe_float(r.get("Total Time(us)", "0")) for r in rows)

    op_stats = []
    for row in rows:
        stat = {
            "op_type": row.get("OP Type", "unknown"),
            "core_type": row.get("Core Type", "unknown"),
            "count": int(_safe_float(row.get("Count", "0"))),
            "total_time_us": _safe_float(row.get("Total Time(us)", "0")),
            "avg_time_us": _safe_float(row.get("Avg Time(us)", "0")),
            "max_time_us": _safe_float(row.get("Max Time(us)", "0")),
            "ratio": _safe_float(row.get("Ratio(%)", "0")),
        }
        op_stats.append(stat)

    op_stats.sort(key=lambda x: x["total_time_us"], reverse=True)

    findings = []
    for stat in op_stats[:5]:
        if stat["count"] > 100 and stat["avg_time_us"] > 100:
            findings.append({
                "type": "high_frequency_op",
                "op_type": stat["op_type"],
                "count": stat["count"],
                "avg_time_us": stat["avg_time_us"],
                "total_time_us": stat["total_time_us"],
                "ratio_pct": stat["ratio"],
            })
        if stat["max_time_us"] > stat["avg_time_us"] * 5 and stat["count"] > 10:
            findings.append({
                "type": "long_tail_op",
                "op_type": stat["op_type"],
                "max_time_us": stat["max_time_us"],
                "avg_time_us": stat["avg_time_us"],
                "max_avg_ratio": round(stat["max_time_us"] / stat["avg_time_us"], 2),
            })

    return {
        "total_time_us": round(total_time, 2),
        "op_stats": op_stats[:15],
        "findings": findings,
    }


def analyze_step_trace(file_path: str) -> dict:
    """分析 step_trace CSV，检查迭代耗时分布和通信计算重叠。"""
    rows = _read_csv(file_path)
    if not rows:
        return {"error": "文件为空或无有效数据"}

    # 兼容两种格式
    is_framework = "Computing" in rows[0] or "Step" in rows[0]

    if is_framework:
        steps = []
        for row in rows:
            step = {
                "step": row.get("Step", ""),
                "computing_us": _safe_float(row.get("Computing", "0")),
                "communication_us": _safe_float(row.get("Communication", "0")),
                "overlapped_us": _safe_float(row.get("Overlapped", "0")),
                "comm_not_overlapped_us": _safe_float(row.get("Communication(Not Overlapped)", "0")),
                "free_us": _safe_float(row.get("Free", "0")),
                "bubble_us": _safe_float(row.get("Bubble", "0")),
            }
            steps.append(step)

        avg_compute = sum(s["computing_us"] for s in steps) / len(steps) if steps else 0
        avg_comm = sum(s["communication_us"] for s in steps) / len(steps) if steps else 0
        avg_free = sum(s["free_us"] for s in steps) / len(steps) if steps else 0
        avg_bubble = sum(s["bubble_us"] for s in steps) / len(steps) if steps else 0
        avg_overlap = sum(s["overlapped_us"] for s in steps) / len(steps) if steps else 0

        total_avg = avg_compute + avg_comm - avg_overlap + avg_free
        findings = []

        if total_avg > 0 and avg_free / total_avg > 0.1:
            findings.append({
                "type": "high_free_ratio",
                "free_ratio_pct": round(avg_free / total_avg * 100, 1),
                "avg_free_us": round(avg_free, 2),
            })
        if avg_comm > 0 and avg_overlap / avg_comm < 0.3:
            findings.append({
                "type": "low_overlap_ratio",
                "overlap_ratio_pct": round(avg_overlap / avg_comm * 100, 1),
                "avg_overlap_us": round(avg_overlap, 2),
                "avg_communication_us": round(avg_comm, 2),
            })
        if avg_bubble > 0 and total_avg > 0 and avg_bubble / total_avg > 0.05:
            findings.append({
                "type": "high_bubble_ratio",
                "bubble_ratio_pct": round(avg_bubble / total_avg * 100, 1),
                "avg_bubble_us": round(avg_bubble, 2),
            })

        return {
            "total_steps": len(steps),
            "avg_computing_us": round(avg_compute, 2),
            "avg_communication_us": round(avg_comm, 2),
            "avg_overlapped_us": round(avg_overlap, 2),
            "avg_free_us": round(avg_free, 2),
            "avg_bubble_us": round(avg_bubble, 2),
            "steps_detail": steps[:10],
            "findings": findings,
        }
    else:
        # msprof 原始 step_trace
        steps = []
        for row in rows:
            step = {
                "iteration_id": row.get("Iteration ID", ""),
                "iteration_time_us": _safe_float(row.get("Iteration Time(us)", "0")),
                "fp_bp_time_us": _safe_float(row.get("FP to BP Time(us)", "0")),
                "iteration_refresh_us": _safe_float(row.get("Iteration Refresh(us)", "0")),
                "data_aug_bound_us": _safe_float(row.get("Data Aug Bound(us)", "0")),
            }
            steps.append(step)

        times = [s["iteration_time_us"] for s in steps if s["iteration_time_us"] > 0]
        avg_iter = sum(times) / len(times) if times else 0
        max_iter = max(times) if times else 0

        findings = []
        if max_iter > avg_iter * 1.5 and len(times) > 2:
            findings.append({
                "type": "unstable_iteration",
                "max_iteration_us": round(max_iter, 1),
                "avg_iteration_us": round(avg_iter, 1),
                "max_avg_ratio": round(max_iter / avg_iter, 2),
            })

        avg_data_aug = sum(s["data_aug_bound_us"] for s in steps) / len(steps) if steps else 0
        if avg_iter > 0 and avg_data_aug / avg_iter > 0.1:
            findings.append({
                "type": "high_data_aug_ratio",
                "data_aug_ratio_pct": round(avg_data_aug / avg_iter * 100, 1),
                "avg_data_aug_us": round(avg_data_aug, 2),
            })

        return {
            "total_steps": len(steps),
            "avg_iteration_time_us": round(avg_iter, 2),
            "max_iteration_time_us": round(max_iter, 2),
            "steps_detail": steps[:10],
            "findings": findings,
        }


def analyze_memory(file_path: str, top_n: int = 10) -> dict:
    """分析 operator_memory CSV，找出高内存占用算子。"""
    rows = _read_csv(file_path)
    if not rows:
        return {"error": "文件为空或无有效数据"}

    # 兼容 KB 和 MB 单位
    size_key = None
    for key in rows[0]:
        if "Size" in key:
            size_key = key
            break
    if not size_key:
        return {"error": f"未找到内存大小字段，可用字段: {list(rows[0].keys())[:10]}"}

    for row in rows:
        row["_size"] = _safe_float(row.get(size_key, "0"))

    rows.sort(key=lambda r: r["_size"], reverse=True)
    total_mem = sum(r["_size"] for r in rows)

    unit = "KB" if "KB" in size_key else ("MB" if "MB" in size_key else "Byte")

    top_mem = []
    for row in rows[:top_n]:
        info = {
            "name": row.get("Name", "unknown"),
            f"size_{unit}": round(row["_size"], 2),
            "ratio": round(row["_size"] / total_mem * 100, 2) if total_mem > 0 else 0,
        }
        dur = _safe_float(row.get("Duration(us)", "0"))
        if dur > 0:
            info["duration_us"] = round(dur, 2)
        top_mem.append(info)

    findings = []
    if top_mem and top_mem[0]["ratio"] > 30:
        findings.append({
            "type": "dominant_memory_op",
            "op_name": top_mem[0]["name"],
            "ratio_pct": top_mem[0]["ratio"],
            f"size_{unit}": top_mem[0][f"size_{unit}"],
        })

    return {
        "total_ops": len(rows),
        f"total_memory_{unit}": round(total_mem, 2),
        "top_memory_ops": top_mem,
        "findings": findings,
    }


def analyze_communication(file_path: str) -> dict:
    """分析 communication_statistic CSV。"""
    rows = _read_csv(file_path)
    if not rows:
        return {"error": "文件为空或无有效数据"}

    total_time = sum(_safe_float(r.get("Total Time(us)", "0")) for r in rows)

    comm_stats = []
    for row in rows:
        stat = {
            "op_type": row.get("OP Type", "unknown"),
            "count": int(_safe_float(row.get("Count", "0"))),
            "total_time_us": _safe_float(row.get("Total Time(us)", "0")),
            "avg_time_us": _safe_float(row.get("Avg Time(us)", "0")),
            "max_time_us": _safe_float(row.get("Max Time(us)", "0")),
            "ratio": _safe_float(row.get("Ratio(%)", "0")),
        }
        comm_stats.append(stat)

    comm_stats.sort(key=lambda x: x["total_time_us"], reverse=True)

    findings = []
    for stat in comm_stats[:3]:
        if stat["max_time_us"] > stat["avg_time_us"] * 3 and stat["count"] > 5:
            findings.append({
                "type": "comm_jitter",
                "op_type": stat["op_type"],
                "max_time_us": stat["max_time_us"],
                "avg_time_us": stat["avg_time_us"],
                "max_avg_ratio": round(stat["max_time_us"] / stat["avg_time_us"], 2),
            })

    return {
        "total_communication_time_us": round(total_time, 2),
        "comm_stats": comm_stats,
        "findings": findings,
    }


# ── DB 解析 ───────────────────────────────────────────────


def analyze_db(db_path: str, top_n: int = 10) -> dict:
    """分析 msprof 导出的 db 文件，提取关键性能指标。"""
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {db_path}")

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 获取所有表名
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]

    result: dict = {"tables": tables}

    # 分析 TASK 表（算子耗时）
    if "TASK" in tables and "COMPUTE_TASK_INFO" in tables:
        try:
            cursor.execute("""
                SELECT
                    s.value as op_name,
                    t2.value as op_type,
                    t.endNs - t.startNs as duration_ns,
                    t.taskType,
                    t.deviceId
                FROM TASK t
                JOIN COMPUTE_TASK_INFO c ON t.globalTaskId = c.globalTaskId
                LEFT JOIN STRING_IDS s ON c.name = s.id
                LEFT JOIN STRING_IDS t2 ON c.opType = t2.id
                WHERE t.endNs > t.startNs
                ORDER BY duration_ns DESC
                LIMIT ?
            """, (top_n,))
            top_ops = []
            for row in cursor.fetchall():
                top_ops.append({
                    "name": row["op_name"] or "unknown",
                    "type": row["op_type"] or "unknown",
                    "duration_us": round(row["duration_ns"] / 1000, 2),
                    "device_id": row["deviceId"],
                })
            result["top_ops"] = top_ops

            # 总耗时
            cursor.execute("SELECT SUM(endNs - startNs) as total FROM TASK WHERE endNs > startNs")
            total_row = cursor.fetchone()
            total_ns = total_row["total"] if total_row and total_row["total"] else 0
            result["total_task_time_us"] = round(total_ns / 1000, 2)

            # 为 top_ops 补充占比
            for op in top_ops:
                op["ratio"] = round(op["duration_us"] / (total_ns / 1000) * 100, 2) if total_ns > 0 else 0
        except Exception as e:
            result["task_error"] = str(e)

    # 分析通信
    if "COMMUNICATION_OP" in tables:
        try:
            cursor.execute("""
                SELECT
                    s.value as op_name,
                    t2.value as op_type,
                    c.endNs - c.startNs as duration_ns,
                    c.deviceId
                FROM COMMUNICATION_OP c
                LEFT JOIN STRING_IDS s ON c.opName = s.id
                LEFT JOIN STRING_IDS t2 ON c.opType = t2.id
                WHERE c.endNs > c.startNs
                ORDER BY duration_ns DESC
                LIMIT ?
            """, (top_n,))
            comm_ops = []
            for row in cursor.fetchall():
                comm_ops.append({
                    "name": row["op_name"] or "unknown",
                    "type": row["op_type"] or "unknown",
                    "duration_us": round(row["duration_ns"] / 1000, 2),
                })
            result["top_comm_ops"] = comm_ops
        except Exception as e:
            result["comm_error"] = str(e)

    # 分析内存
    if "NPU_OP_MEM" in tables:
        try:
            cursor.execute("""
                SELECT
                    s.value as op_name,
                    m.size,
                    m.totalAllocate,
                    m.totalReserve
                FROM NPU_OP_MEM m
                LEFT JOIN STRING_IDS s ON m.operatorName = s.id
                ORDER BY m.size DESC
                LIMIT ?
            """, (top_n,))
            mem_ops = []
            for row in cursor.fetchall():
                mem_ops.append({
                    "name": row["op_name"] or "unknown",
                    "size_MB": round(row["size"] / 1024 / 1024, 2) if row["size"] else 0,
                    "total_allocated_MB": round(row["totalAllocate"] / 1024 / 1024, 2) if row["totalAllocate"] else 0,
                })
            result["top_memory_ops"] = mem_ops
        except Exception as e:
            result["memory_error"] = str(e)

    # PyTorch 框架 STEP_TIME
    if "STEP_TIME" in tables:
        try:
            cursor.execute("""
                SELECT id, (endNs - startNs) / 1000 as duration_us
                FROM STEP_TIME
                ORDER BY id
            """)
            steps = [{"step": row["id"], "duration_us": row["duration_us"]} for row in cursor.fetchall()]
            result["step_times"] = steps[:20]
            if steps:
                durations = [s["duration_us"] for s in steps]
                result["avg_step_time_us"] = round(sum(durations) / len(durations), 2)
                result["max_step_time_us"] = round(max(durations), 2)
        except Exception as e:
            result["step_error"] = str(e)

    conn.close()

    # 客观事实标记
    findings = []
    if result.get("top_ops") and result.get("total_task_time_us", 0) > 0:
        top = result["top_ops"][0]
        if top["ratio"] > 30:
            findings.append({
                "type": "dominant_op",
                "op_name": top["name"],
                "op_type": top["type"],
                "ratio_pct": top["ratio"],
                "duration_us": top["duration_us"],
            })

    if result.get("step_times") and len(result["step_times"]) > 2:
        avg = result.get("avg_step_time_us", 0)
        max_t = result.get("max_step_time_us", 0)
        if avg > 0 and max_t > avg * 1.5:
            findings.append({
                "type": "unstable_step",
                "max_step_us": round(max_t, 1),
                "avg_step_us": round(avg, 1),
                "max_avg_ratio": round(max_t / avg, 2),
            })

    result["findings"] = findings
    return result


# ── JSON 解析 ─────────────────────────────────────────────


def _read_json(file_path: str) -> dict | list:
    """读取 JSON 文件。"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    import json
    for enc in ("utf-8", "utf-8-sig", "gbk"):
        try:
            with open(path, "r", encoding=enc) as f:
                return json.load(f)
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"无法解码文件: {file_path}")


def _process_trace_segment(seg, pat_ph, pat_dur, pat_name, pat_cat, op_agg):
    """处理一个 trace_view 事件片段，聚合到 op_agg 中。"""
    ph_m = pat_ph.search(seg)
    if not ph_m or ph_m.group(1) != "X":
        return
    dur_m = pat_dur.search(seg)
    if not dur_m:
        return
    dur = float(dur_m.group(1))
    if dur <= 0:
        return
    name_m = pat_name.search(seg)
    name = name_m.group(1) if name_m else "unknown"
    cat_m = pat_cat.search(seg)
    cat = cat_m.group(1) if cat_m else ""
    key = (name, cat)
    if key not in op_agg:
        op_agg[key] = [0, 0.0, 0.0]
    op_agg[key][0] += 1
    op_agg[key][1] += dur
    if dur > op_agg[key][2]:
        op_agg[key][2] = dur


def analyze_trace_view(file_path: str, top_n: int = 10) -> dict:
    """分析 trace_view.json（Chrome Tracing 格式），按算子名聚合统计耗时。

    由于文件可能非常大（数百 MB），采用分块正则提取，避免逐字符遍历。
    """
    import json
    import re

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    # 按 (name, cat) 聚合: [count, total_dur, max_dur]
    op_agg: dict[tuple[str, str], list] = {}

    # 快速正则：提取 "ph":"X" 的事件中的 name, cat, dur
    # 对于 Chrome Tracing 格式，每个事件是 {"ph":"X","name":...,"dur":...,"cat":...,...}
    pat_name = re.compile(r'"name"\s*:\s*"([^"]*)"')
    pat_dur = re.compile(r'"dur"\s*:\s*([\d.eE+\-]+)')
    pat_cat = re.compile(r'"cat"\s*:\s*"([^"]*)"')
    pat_ph = re.compile(r'"ph"\s*:\s*"([^"]*)"')

    chunk_size = 8 * 1024 * 1024  # 8MB chunks
    # 预编译分隔正则：匹配顶层对象之间的 "}, {" 或 "},{"
    split_pat = re.compile(r'\}\s*,\s*\{')

    with open(path, "r", encoding="utf-8") as f:
        leftover = ""
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                # 处理最后的 leftover
                if leftover.strip():
                    seg = leftover.strip().strip("[]{},")
                    if seg:
                        _process_trace_segment(seg, pat_ph, pat_dur, pat_name, pat_cat, op_agg)
                break

            text = leftover + chunk

            # 用正则 split 顶层对象
            # 先找最后一个 "}, {" 以便安全切割
            parts = list(split_pat.finditer(text))
            if parts:
                last_split = parts[-1]
                # 保留从最后分隔点之后的内容作为 leftover
                leftover = "{" + text[last_split.end():]
                process_text = text[:last_split.start() + 1]  # 包含 }
            else:
                # 整个 chunk 没有分隔符，可能是一个巨大的对象，追加到 leftover
                leftover = text
                continue

            # 按分隔符切分
            segments = split_pat.split(process_text)
            for seg in segments:
                _process_trace_segment(seg, pat_ph, pat_dur, pat_name, pat_cat, op_agg)

    if not op_agg:
        return {"error": "文件为空或无有效的 tracing 事件"}

    total_dur = sum(v[1] for v in op_agg.values())
    total_events = sum(v[0] for v in op_agg.values())

    # 按总耗时降序排
    sorted_ops = sorted(op_agg.items(), key=lambda x: x[1][1], reverse=True)

    top_ops = []
    for (name, cat), (count, tot, mx) in sorted_ops[:top_n]:
        top_ops.append({
            "name": name,
            "category": cat,
            "count": count,
            "total_dur_us": round(tot, 2),
            "avg_dur_us": round(tot / count, 2),
            "max_dur_us": round(mx, 2),
            "ratio": round(tot / total_dur * 100, 2) if total_dur > 0 else 0,
        })

    # 按 category 聚合
    cat_dist: dict[str, float] = {}
    for (_, cat), (_, tot, _) in op_agg.items():
        label = cat if cat else "unknown"
        cat_dist[label] = cat_dist.get(label, 0) + tot

    findings = []
    if top_ops and top_ops[0]["ratio"] > 30:
        findings.append({
            "type": "dominant_op",
            "op_name": top_ops[0]["name"],
            "ratio_pct": top_ops[0]["ratio"],
        })
    for op in top_ops[:5]:
        if op["max_dur_us"] > op["avg_dur_us"] * 5 and op["count"] > 10:
            findings.append({
                "type": "long_tail_op",
                "op_type": op["name"],
                "max_time_us": op["max_dur_us"],
                "avg_time_us": op["avg_dur_us"],
                "max_avg_ratio": round(op["max_dur_us"] / op["avg_dur_us"], 2),
            })

    return {
        "total_events": total_events,
        "unique_ops": len(op_agg),
        "total_dur_us": round(total_dur, 2),
        "top_ops": top_ops,
        "category_distribution": {
            k: {"time_us": round(v, 2), "ratio": round(v / total_dur * 100, 2) if total_dur > 0 else 0}
            for k, v in sorted(cat_dist.items(), key=lambda x: x[1], reverse=True)
        },
        "findings": findings,
    }


def analyze_communication_json(file_path: str) -> dict:
    """分析 communication.json，提取通信算子的耗时和带宽信息。"""
    data = _read_json(file_path)
    if not isinstance(data, dict) or not data:
        return {"error": "文件为空或格式不符"}

    all_ops = []
    for step_key, step_val in data.items():
        if not isinstance(step_val, dict):
            continue
        for comm_type in ("collective", "p2p"):
            ops = step_val.get(comm_type, {})
            if not isinstance(ops, dict):
                continue
            for op_name, op_info in ops.items():
                if not isinstance(op_info, dict):
                    continue
                time_info = op_info.get("Communication Time Info", {})
                bw_info = op_info.get("Communication Bandwidth Info", {})

                elapse = time_info.get("Elapse Time(ms)", 0)
                transit = time_info.get("Transit Time(ms)", 0)
                wait = time_info.get("Wait Time(ms)", 0)
                sync = time_info.get("Synchronization Time(ms)", 0)
                idle = time_info.get("Idle Time(ms)", 0)
                wait_ratio = time_info.get("Wait Time Ratio", 0)

                # 汇总各链路带宽
                total_size_mb = 0
                total_transit_ms = 0
                link_details = {}
                for link in ("RDMA", "HCCS", "PCIE", "SDMA", "SIO"):
                    link_info = bw_info.get(link, {})
                    s = link_info.get("Transit Size(MB)", 0)
                    t = link_info.get("Transit Time(ms)", 0)
                    bw = link_info.get("Bandwidth(GB/s)", 0)
                    if s > 0 or t > 0:
                        link_details[link] = {
                            "size_MB": round(s, 4),
                            "time_ms": round(t, 6),
                            "bandwidth_GBps": round(bw, 4),
                        }
                        total_size_mb += s
                        total_transit_ms += t

                all_ops.append({
                    "step": step_key,
                    "comm_type": comm_type,
                    "op_name": op_name.split("@")[0],
                    "elapse_ms": round(elapse, 6),
                    "transit_ms": round(transit, 6),
                    "wait_ms": round(wait, 6),
                    "sync_ms": round(sync, 6),
                    "idle_ms": round(idle, 6),
                    "wait_ratio": round(wait_ratio, 4),
                    "total_size_MB": round(total_size_mb, 4),
                    "link_details": link_details,
                })

    if not all_ops:
        return {"error": "未找到通信算子数据"}

    all_ops.sort(key=lambda x: x["elapse_ms"], reverse=True)
    total_elapse = sum(op["elapse_ms"] for op in all_ops)

    findings = []
    # 检查高 wait ratio
    high_wait_ops = [op for op in all_ops if op["wait_ratio"] > 0.3]
    if high_wait_ops:
        worst = max(high_wait_ops, key=lambda x: x["wait_ratio"])
        findings.append({
            "type": "comm_high_wait_ratio",
            "op_name": worst["op_name"],
            "wait_ratio": worst["wait_ratio"],
            "elapse_ms": worst["elapse_ms"],
        })

    # 检查 idle 占比高
    high_idle_ops = [op for op in all_ops if op["elapse_ms"] > 0 and op["idle_ms"] / op["elapse_ms"] > 0.5]
    if high_idle_ops:
        worst = max(high_idle_ops, key=lambda x: x["idle_ms"])
        findings.append({
            "type": "comm_high_idle",
            "op_name": worst["op_name"],
            "idle_ms": worst["idle_ms"],
            "elapse_ms": worst["elapse_ms"],
            "idle_ratio": round(worst["idle_ms"] / worst["elapse_ms"], 4),
        })

    # 检查耗时抖动
    from collections import defaultdict
    op_groups: dict[str, list[float]] = defaultdict(list)
    for op in all_ops:
        op_groups[op["op_name"]].append(op["elapse_ms"])
    for name, times in op_groups.items():
        if len(times) > 1:
            avg_t = sum(times) / len(times)
            max_t = max(times)
            if avg_t > 0 and max_t > avg_t * 3:
                findings.append({
                    "type": "comm_jitter",
                    "op_type": name,
                    "max_time_us": round(max_t * 1000, 2),
                    "avg_time_us": round(avg_t * 1000, 2),
                    "max_avg_ratio": round(max_t / avg_t, 2),
                })

    return {
        "total_ops": len(all_ops),
        "total_elapse_ms": round(total_elapse, 4),
        "top_ops": all_ops[:15],
        "findings": findings,
    }


def analyze_communication_matrix_json(file_path: str) -> dict:
    """分析 communication_matrix.json，提取设备间通信矩阵和带宽。"""
    data = _read_json(file_path)
    if not isinstance(data, dict) or not data:
        return {"error": "文件为空或格式不符"}

    matrix_entries = []
    for step_key, step_val in data.items():
        if not isinstance(step_val, dict):
            continue
        for comm_type in ("collective", "p2p"):
            groups = step_val.get(comm_type, {})
            if not isinstance(groups, dict):
                continue
            for group_name, pairs in groups.items():
                if not isinstance(pairs, dict):
                    continue
                for pair_key, info in pairs.items():
                    if not isinstance(info, dict):
                        continue
                    matrix_entries.append({
                        "step": step_key,
                        "comm_type": comm_type,
                        "group": group_name.split("@")[0],
                        "pair": pair_key,
                        "transport_type": info.get("Transport Type", ""),
                        "size_MB": round(info.get("Transit Size(MB)", 0), 4),
                        "time_ms": round(info.get("Transit Time(ms)", 0), 6),
                        "bandwidth_GBps": round(info.get("Bandwidth(GB/s)", 0), 4),
                        "op_name": info.get("Op Name", ""),
                    })

    if not matrix_entries:
        return {"error": "未找到通信矩阵数据"}

    # 按传输类型汇总
    transport_stats: dict[str, dict] = {}
    for e in matrix_entries:
        tt = e["transport_type"] or "unknown"
        if tt not in transport_stats:
            transport_stats[tt] = {"count": 0, "total_size_MB": 0, "total_time_ms": 0, "bandwidths": []}
        transport_stats[tt]["count"] += 1
        transport_stats[tt]["total_size_MB"] += e["size_MB"]
        transport_stats[tt]["total_time_ms"] += e["time_ms"]
        if e["bandwidth_GBps"] > 0:
            transport_stats[tt]["bandwidths"].append(e["bandwidth_GBps"])

    for tt, stats in transport_stats.items():
        bws = stats.pop("bandwidths")
        stats["total_size_MB"] = round(stats["total_size_MB"], 4)
        stats["total_time_ms"] = round(stats["total_time_ms"], 6)
        stats["avg_bandwidth_GBps"] = round(sum(bws) / len(bws), 4) if bws else 0
        stats["min_bandwidth_GBps"] = round(min(bws), 4) if bws else 0

    findings = []
    # 检查带宽差异
    for tt, stats in transport_stats.items():
        if stats["avg_bandwidth_GBps"] > 0 and stats["min_bandwidth_GBps"] > 0:
            ratio = stats["avg_bandwidth_GBps"] / stats["min_bandwidth_GBps"]
            if ratio > 3:
                findings.append({
                    "type": "comm_bandwidth_imbalance",
                    "transport_type": tt,
                    "avg_bandwidth_GBps": stats["avg_bandwidth_GBps"],
                    "min_bandwidth_GBps": stats["min_bandwidth_GBps"],
                    "imbalance_ratio": round(ratio, 2),
                })

    return {
        "total_entries": len(matrix_entries),
        "transport_stats": transport_stats,
        "sample_entries": matrix_entries[:10],
        "findings": findings,
    }


# ── 统一入口 ──────────────────────────────────────────────


def detect_file_type(file_path: str) -> str:
    """根据文件名自动检测 Profiling 数据类型。"""
    name = Path(file_path).name.lower()
    if name.endswith(".db"):
        return "db"
    if name.endswith(".json"):
        if "trace_view" in name:
            return "trace_view"
        if "communication_matrix" in name:
            return "communication_matrix"
        if "communication" in name:
            return "communication_json"
        return "unknown"
    if "op_summary" in name:
        return "op_summary"
    if "op_statistic" in name:
        return "op_statistic"
    if "step_trace" in name:
        return "step_trace"
    if "operator_memory" in name or "op_memory" in name:
        return "memory"
    if "communication" in name or "comm" in name:
        return "communication"
    if "memory_record" in name:
        return "memory"
    return "unknown"


def analyze_profiling_data(file_path: str, top_n: int = 10) -> dict:
    """自动检测文件类型并执行对应分析。"""
    file_type = detect_file_type(file_path)

    if file_type == "db":
        return {"file_type": "db", **analyze_db(file_path, top_n)}
    elif file_type == "op_summary":
        return {"file_type": "op_summary", **analyze_op_summary(file_path, top_n)}
    elif file_type == "op_statistic":
        return {"file_type": "op_statistic", **analyze_op_statistic(file_path)}
    elif file_type == "step_trace":
        return {"file_type": "step_trace", **analyze_step_trace(file_path)}
    elif file_type == "memory":
        return {"file_type": "memory", **analyze_memory(file_path, top_n)}
    elif file_type == "communication":
        return {"file_type": "communication", **analyze_communication(file_path)}
    elif file_type == "trace_view":
        return {"file_type": "trace_view", **analyze_trace_view(file_path, top_n)}
    elif file_type == "communication_json":
        return {"file_type": "communication_json", **analyze_communication_json(file_path)}
    elif file_type == "communication_matrix":
        return {"file_type": "communication_matrix", **analyze_communication_matrix_json(file_path)}
    else:
        return {
            "file_type": "unknown",
            "error": (
                f"无法识别文件类型: {Path(file_path).name}。"
                f"支持的文件: op_summary*.csv, op_statistic*.csv, "
                f"step_trace*.csv, operator_memory*.csv, "
                f"communication_statistic*.csv, *.db, "
                f"trace_view.json, communication.json, communication_matrix.json"
            ),
        }
