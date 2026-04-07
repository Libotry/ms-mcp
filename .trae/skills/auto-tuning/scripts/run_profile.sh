#!/usr/bin/env bash
# run_profile.sh - 自动执行 profiling 采集
# 用法: bash run_profile.sh <session_id> <framework> [scenario]
# 示例: bash run_profile.sh sess_abc123 pytorch training
# 示例: bash run_profile.sh sess_abc123 msmonitor inference

set -e

SESSION_ID="${1:-}"
FRAMEWORK="${2:-pytorch}"
SCENARIO="${3:-training}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
SESSION_DIR="$SKILL_DIR/tuning_sessions/$SESSION_ID"
CURRENT_STATE="$SESSION_DIR/current_state.json"

if [ -z "$SESSION_ID" ] || [ -z "$FRAMEWORK" ]; then
    echo "用法: bash run_profile.sh <session_id> <framework> [scenario]"
    echo "framework: pytorch | mindspore | msmonitor | msprof"
    echo "scenario: training | inference | service"
    exit 1
fi

if [ ! -d "$SESSION_DIR" ]; then
    echo "错误: 会话目录不存在: $SESSION_DIR"
    exit 1
fi

# 读取当前 iteration
CURRENT_ITER=$(grep -o '"iteration": [0-9]*' "$CURRENT_STATE" 2>/dev/null | head -1 | grep -o '[0-9]*' || echo "0")
PROF_DIR="$SESSION_DIR/iteration_$CURRENT_ITER/profiling"

mkdir -p "$PROF_DIR"

echo "🔍 开始 profiling: framework=$FRAMEWORK scenario=$SCENARIO"
echo "📁 输出目录: $PROF_DIR"

# 根据框架生成 profiling 命令
case "$FRAMEWORK" in
    pytorch)
        echo "📋 检测到 PyTorch 场景"
        echo ""
        echo "请在训练脚本中添加以下 profiling 代码（已有 SKILL.md 指导）："
        echo ""
        cat << 'PYEOF'
```python
import torch_npu
from torch_npu.npu import npu_profile

with npu_profile(
    activities=[
        torch.profiler.ProfilerActivity.NPU,
        torch.profiler.ProfilerActivity.CPU,
    ],
    record_shapes=True,
    profile_memory=True,
    on_trace_ready=torch.profiler.tensorboard_trace_handler('./profiler_output')
) as prof:
    for step, (images, labels) in enumerate(train_loader):
        # ... 训练代码 ...
        prof.step()
```
PYEOF
        echo ""
        echo "💡 或使用 msprof 命令进行集群级采集："
        echo "   msprof --output=$PROF_DIR --application=/path/to/your_app"
        echo ""
        echo "请提供训练脚本路径或 msprof 命令参数，SKILL 将自动执行采集。"
        ;;

    mindspore)
        echo "📋 检测到 MindSpore 场景"
        echo "使用 MindSpore Profiler 进行采集："
        echo "   from mindspore.profiler import Profiler"
        echo "   profiler = Profiler(output_path='$PROF_DIR')"
        ;;

    msmonitor)
        echo "📋 检测到 msMonitor 场景"
        echo "使用 npu-monitor 采集："
        echo "   msmonitor --output=$PROF_DIR --application=/path/to/app"
        ;;

    msprof|*)
        echo "📋 使用 msprof 通用采集"
        echo "请提供 msprof 命令参数，SKILL 将执行采集："
        echo "   msprof --output=$PROF_DIR --application=/path/to/your_app"
        ;;
esac

echo ""
echo "✅ Profiling 目录已就绪: $PROF_DIR"
echo "⚠️ 请提供训练脚本路径或具体命令，SKILL 将执行采集并保存到该目录"
