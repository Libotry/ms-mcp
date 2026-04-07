#!/usr/bin/env bash
# start_session.sh - 创建调优会话目录
# 用法: bash start_session.sh <goals_string>
# 示例: bash start_session.sh "MFU:65% iteration_time:15% max_iter:5 framework:pytorch"

set -e

GOALS="${1:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
SESSION_BASE="$SKILL_DIR/tuning_sessions"
SESSIONS_FILE="$SESSION_BASE/sessions.json"

if [ -z "$GOALS" ]; then
    echo "用法: bash start_session.sh <goals_string>"
    echo "示例: bash start_session.sh \"MFU:65% max_iter:5 framework:pytorch\""
    exit 1
fi

mkdir -p "$SESSION_BASE"

# 生成 session_id
SESSION_ID="sess_$(date +%Y%m%d_%H%M%S)_$$"
SESSION_DIR="$SESSION_BASE/$SESSION_ID"
ITER_DIR="$SESSION_DIR/iteration_0"
mkdir -p "$SESSION_DIR" "$ITER_DIR/baseline" "$ITER_DIR/profiling"

# 解析 goals_string 并生成 config.yaml
cat > "$SESSION_DIR/config.yaml" << EOF
session_id: $SESSION_ID
created: $(date -Iseconds)
goals: $GOALS
iterations: []
current_iteration: 0
status: active
EOF

# 更新 sessions.json 索引
if [ -f "$SESSIONS_FILE" ]; then
    # 追加新 session，保持 JSON 格式
    TEMP=$(mktemp)
    # 简单追加：找到 } 闭合对象，在末尾插入新条目
    # 使用 jq 更可靠
    if command -v jq &> /dev/null; then
        echo '{"sessions": []}' > "$SESSIONS_FILE" 2>/dev/null || true
        jq --arg id "$SESSION_ID" --arg dir "$SESSION_DIR" --arg goals "$GOALS" \
           --arg created "$(date -Iseconds)" \
           '.sessions += [{"id": $id, "dir": $dir, "goals": $goals, "created": $created}]' \
           "$SESSIONS_FILE" > "$TEMP" && mv "$TEMP" "$SESSIONS_FILE"
    else
        # 无 jq 时的退化方案：直接追加到文件
        echo "{\"id\": \"$SESSION_ID\", \"dir\": \"$SESSION_DIR\", \"goals\": \"$GOALS\"}" >> "$SESSIONS_FILE"
    fi
else
    echo "[]" > "$SESSIONS_FILE"
    if command -v jq &> /dev/null; then
        TEMP=$(mktemp)
        jq --arg id "$SESSION_ID" --arg dir "$SESSION_DIR" --arg goals "$GOALS" \
           --arg created "$(date -Iseconds)" \
           '. += [{"id": $id, "dir": $dir, "goals": $goals, "created": $created}]' \
           "$SESSIONS_FILE" > "$TEMP" && mv "$TEMP" "$SESSIONS_FILE"
    else
        echo "[{\"id\": \"$SESSION_ID\", \"dir\": \"$SESSION_DIR\", \"goals\": \"$GOALS\"}]" > "$SESSIONS_FILE"
    fi
fi

# 写入初始 current_state.json
cat > "$SESSION_DIR/current_state.json" << EOF
{
  "session_id": "$SESSION_ID",
  "phase": "align",
  "iteration": 0,
  "status": "align",
  "goals": "$GOALS",
  "findings": null,
  "hypotheses": null,
  "last_updated": "$(date -Iseconds)"
}
EOF

echo "✅ 会话已创建: $SESSION_ID"
echo "📁 目录: $SESSION_DIR"
echo "📋 配置: $SESSION_DIR/config.yaml"
