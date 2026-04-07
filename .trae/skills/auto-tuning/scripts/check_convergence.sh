#!/usr/bin/env bash
# check_convergence.sh - 调用 convergence.py 判断收敛
# 用法: bash check_convergence.sh <session_id>

set -e

SESSION_ID="${1:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
SESSION_DIR="$SKILL_DIR/tuning_sessions/$SESSION_ID"
CURRENT_STATE="$SESSION_DIR/current_state.json"

if [ -z "$SESSION_ID" ]; then
    echo "用法: bash check_convergence.sh <session_id>"
    exit 1
fi

if [ ! -d "$SESSION_DIR" ]; then
    echo "错误: 会话目录不存在: $SESSION_DIR"
    exit 1
fi

# 读取当前 iteration
CURRENT_ITER=$(grep -o '"iteration": [0-9]*' "$CURRENT_STATE" 2>/dev/null | head -1 | grep -o '[0-9]*' || echo "0")

echo "🔍 收敛判断: session=$SESSION_ID iteration=$CURRENT_ITER"

# 运行 convergence.py
python "$SCRIPT_DIR/convergence.py" "$SESSION_ID"

# convergence.py 输出 JSON 结果
RESULT=$?

if [ $RESULT -eq 0 ]; then
    echo "✅ 收敛判断完成"
else
    echo "⚠️ 收敛判断跳过（无足够数据）"
fi
