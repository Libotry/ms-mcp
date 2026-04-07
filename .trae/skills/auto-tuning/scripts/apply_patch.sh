#!/usr/bin/env bash
# apply_patch.sh - 应用/回滚代码 patch
# 用法: bash apply_patch.sh <session_id> <iteration> <action>
# action: dry-run | apply | rollback

set -e

SESSION_ID="${1:-}"
ITERATION="${2:-0}"
ACTION="${3:-dry-run}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
SESSION_DIR="$SKILL_DIR/tuning_sessions/$SESSION_ID"
ITER_DIR="$SESSION_DIR/iteration_$ITERATION"
PATCH_FILE="$ITER_DIR/patch.diff"
HASH_FILE="$ITER_DIR/git_commit.hash"

if [ -z "$SESSION_ID" ] || [ -z "$ACTION" ]; then
    echo "用法: bash apply_patch.sh <session_id> <iteration> <action>"
    echo "action: dry-run | apply | rollback"
    exit 1
fi

if [ ! -d "$ITER_DIR" ]; then
    echo "错误: iteration 目录不存在: $ITER_DIR"
    exit 1
fi

echo "🔧 apply_patch: session=$SESSION_ID iteration=$ITERATION action=$ACTION"

case "$ACTION" in
    dry-run)
        if [ -f "$PATCH_FILE" ]; then
            echo "📋 Dry-run diff preview:"
            echo "---"
            cat "$PATCH_FILE"
            echo "---"
            echo "✅ 确认执行 apply？当前目录将应用上述改动"
        else
            echo "⚠️ 未找到 patch 文件: $PATCH_FILE"
            echo "请先生成 patch（通过 TRAE LLM 编辑代码后生成 diff）"
        fi
        ;;

    apply)
        # 保存当前 git commit hash（用于 rollback）
        if [ -d ".git" ]; then
            git rev-parse HEAD > "$HASH_FILE"
            echo "📌 Rollback 点已保存: $(cat "$HASH_FILE")"
        fi

        if [ -f "$PATCH_FILE" ]; then
            echo "📝 应用 patch..."
            git apply "$PATCH_FILE"
            echo "✅ Patch 已应用"
        else
            echo "⚠️ 无 patch 文件，跳过"
        fi
        ;;

    rollback)
        if [ -f "$HASH_FILE" ]; then
            HASH=$(cat "$HASH_FILE")
            echo "🔙 回滚到: $HASH"
            git checkout "$HASH" -- .
            echo "✅ 已回滚"
        else
            echo "⚠️ 未找到 rollback 点（无 git commit hash）"
            echo "尝试: git stash 或手动回滚"
        fi
        ;;

    *)
        echo "错误: 未知的 action: $ACTION"
        echo "action: dry-run | apply | rollback"
        exit 1
        ;;
esac
