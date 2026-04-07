#!/usr/bin/env python3
"""
convergence.py - 收敛判断逻辑
用法: python convergence.py <session_id>
读取 session 的 config.yaml 和 iteration 数据，判断是否收敛
"""

import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class ConvergenceResult:
    converged: bool
    reason: str  # "target_achieved" | "regression" | "no_improvement"
    metric_delta: dict  # {metric: {"before": float, "after": float, "delta_pct": float}}
    iteration: int
    recommendations: list[str]
    user_message: str  # 用户可见翻译


def load_metrics(session_dir: Path, iteration: int) -> dict:
    """从 iteration 目录加载指标数据"""
    iter_dir = session_dir / f"iteration_{iteration}"
    compare_file = iter_dir / "compare.json"

    if compare_file.exists():
        with open(compare_file) as f:
            data = json.load(f)
            return data.get("metrics", {})

    # fallback: 从 analysis.json 读取
    analysis_file = iter_dir / "analysis.json"
    if analysis_file.exists():
        with open(analysis_file) as f:
            data = json.load(f)
            metrics = {}
            for finding in data.get("findings", []):
                # 提取关键指标
                if "mfu" in finding.get("type", "").lower():
                    metrics["mfu"] = finding.get("value", 0)
                elif "iteration_time" in finding.get("type", "").lower():
                    metrics["iteration_time"] = finding.get("value", 0)
            return metrics

    return {}


def parse_thresholds_from_config(config_file: Path) -> dict:
    """从 config.yaml 中解析目标阈值（简化版）"""
    import re
    thresholds = {}

    if not config_file.exists():
        return thresholds

    content = config_file.read_text()

    # 解析 MFU:65% 格式
    mfu_match = re.search(r"MFU[:\s]*(\d+)%", content)
    if mfu_match:
        thresholds["mfu"] = float(mfu_match.group(1))

    # 解析通信重叠率
    overlap_match = re.search(r"comm_overlap[:\s]*(\d+)%", content)
    if overlap_match:
        thresholds["comm_overlap"] = float(overlap_match.group(1))

    return thresholds


def judge_convergence(
    baseline: dict,
    current: dict,
    thresholds: dict,
    iteration: int
) -> ConvergenceResult:
    """
    核心收敛判断逻辑。
    必须显式按 key 匹配（不用 zip，zip 在字典长度不同时静默丢数据）。
    """
    improvements = {}
    regressions = {}

    common_keys = set(baseline.keys()) & set(current.keys())

    for metric in common_keys:
        b_val = baseline[metric]
        c_val = current[metric]

        if not isinstance(b_val, (int, float)) or not isinstance(c_val, (int, float)):
            continue
        if b_val == 0:
            continue

        delta_pct = (c_val - b_val) / b_val * 100
        improvements[metric] = {
            "before": round(b_val, 2),
            "after": round(c_val, 2),
            "delta_pct": round(delta_pct, 2)
        }

        if metric in thresholds and delta_pct < 0:
            regressions[metric] = delta_pct

    # 生成用户可见消息
    metric_msgs = []
    for metric, info in improvements.items():
        arrow = "↑" if info["delta_pct"] > 0 else "↓"
        metric_msgs.append(f"{metric}: {info['before']} → {info['after']} ({arrow}{abs(info['delta_pct'])}%)")

    summary = ", ".join(metric_msgs) if metric_msgs else "无变化"

    # 判断结果
    if regressions:
        return ConvergenceResult(
            converged=True,
            reason="regression",
            metric_delta=improvements,
            iteration=iteration,
            recommendations=["⚠️ 检测到性能回退，建议回滚"],
            user_message=f"⚠️ regression | {summary} | 检测到性能回退，建议回滚"
        )
    elif all(i >= thresholds.get(m, 0) for m, i in [(k, v["delta_pct"]) for k, v in improvements.items()]):
        return ConvergenceResult(
            converged=True,
            reason="target_achieved",
            metric_delta=improvements,
            iteration=iteration,
            recommendations=["🎉 目标达成，停止迭代"],
            user_message=f"🎉 target_achieved | {summary} | 目标达成，停止迭代"
        )
    else:
        return ConvergenceResult(
            converged=False,
            reason="no_improvement",
            metric_delta=improvements,
            iteration=iteration,
            recommendations=["⏳ 未达标，继续下一轮迭代"],
            user_message=f"⏳ no_improvement | {summary} | 未达标，继续下一轮迭代"
        )


def main():
    if len(sys.argv) < 2:
        print("用法: python convergence.py <session_id>")
        sys.exit(1)

    session_id = sys.argv[1]

    # 查找 session 目录
    script_dir = Path(__file__).parent.parent
    session_dir = script_dir / "tuning_sessions" / session_id

    if not session_dir.exists():
        print(f"错误: 会话目录不存在: {session_dir}")
        sys.exit(1)

    config_file = session_dir / "config.yaml"
    current_state_file = session_dir / "current_state.json"

    # 读取当前迭代轮次
    current_iteration = 0
    if current_state_file.exists():
        with open(current_state_file) as f:
            state = json.load(f)
            current_iteration = state.get("iteration", 0)

    # 加载基线指标（iteration_0）
    baseline = load_metrics(session_dir, 0)
    # 加载当前指标
    current = load_metrics(session_dir, current_iteration)

    if not baseline:
        print("⚠️ 无基线数据，跳过收敛判断")
        sys.exit(0)

    if not current or current == baseline:
        print("⏳ 无当前数据或无变化，跳过收敛判断")
        sys.exit(0)

    # 解析阈值
    thresholds = parse_thresholds_from_config(config_file)

    # 判断收敛
    result = judge_convergence(baseline, current, thresholds, current_iteration)

    # 输出结果
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))

    # 同时追加到 compare.json
    iter_dir = session_dir / f"iteration_{current_iteration}"
    iter_dir.mkdir(parents=True, exist_ok=True)
    with open(iter_dir / "convergence_result.json", "w") as f:
        json.dump(asdict(result), f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
