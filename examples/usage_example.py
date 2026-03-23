"""Skills 功能使用示例。

演示如何使用昇腾工具专业知识库功能：
1. 构建索引
2. 查询知识库
3. 混合检索
"""

from pathlib import Path

# ── 示例 1: 构建知识库索引 ────────────────────────────────────
def demo_build_index():
    """演示如何构建知识库索引。"""
    from skills import SkillIndex
    
    print("=" * 60)
    print("示例 1: 构建知识库索引")
    print("=" * 60)
    
    # 初始化索引
    index = SkillIndex(Path("knowledge") / "skills.db")
    
    # 从 tool_docs 目录构建索引
    docs_dir = Path("tool_docs")
    if not docs_dir.exists():
        print(f"文档目录不存在：{docs_dir}")
        return
    
    print(f"\n扫描目录：{docs_dir}")
    indexed = index.build_from_directory(docs_dir)
    
    if indexed:
        print(f"\n✓ 成功索引 {len(indexed)} 个文件:")
        for info in indexed:
            print(f"  - {Path(info.file_path).name}")
            print(f"    类型：{info.doc_type}, 片段数：{info.chunk_count}")
    else:
        print("\n✓ 知识库已是最新，无需重新索引")
    
    index.close()


# ── 示例 2: 查询知识库 ────────────────────────────────────────
def demo_query_knowledge():
    """演示如何查询知识库。"""
    from skills import Retriever
    
    print("\n" + "=" * 60)
    print("示例 2: 查询知识库")
    print("=" * 60)
    
    queries = [
        "msprof 如何进行延迟采集？",
        "如何使用 msSanitizer 调试算子？",
        "性能分析的步骤是什么？",
    ]
    
    db_path = Path("knowledge") / "skills.db"
    if not db_path.exists():
        print("\n知识库索引尚未建立，请先运行 demo_build_index()")
        return
    
    retriever = Retriever(db_path)
    
    for query in queries:
        print(f"\n查询：{query}")
        print("-" * 60)
        
        results = retriever.search(query, top_k=3)
        
        if not results:
            print("  未找到相关内容")
            continue
        
        for i, result in enumerate(results, 1):
            chunk = result.chunk
            print(f"\n  [{i}] 来源：{Path(chunk.source).name}")
            if chunk.chapter:
                print(f"      章节：{chunk.chapter}")
            print(f"      相关性：{result.combined_score:.3f}")
            print(f"      内容：{chunk.content[:200]}...")
    
    retriever.close()


# ── 示例 3: 意图识别 ─────────────────────────────────────────
def demo_intent_classification():
    """演示意图识别功能。"""
    from skills import route_query
    
    print("\n" + "=" * 60)
    print("示例 3: 意图识别")
    print("=" * 60)
    
    queries = [
        "推荐一个性能分析工具",
        "msprof 如何使用延迟采集？",
        "如何分析 op_summary 文件？",
        "有什么工具可以调试算子？",
    ]
    
    for query in queries:
        result = route_query(query)
        print(f"\n查询：{query}")
        print(f"  意图：{result.intent}")
        print(f"  置信度：{result.confidence:.2f}")
        print(f"  知识源：{result.source.value}")
        print(f"  建议动作：{result.suggested_action}")


# ── 示例 4: 使用 MCP Tool ────────────────────────────────────
def demo_mcp_tools():
    """演示如何在 MCP Server 中使用 Skills 功能。"""
    print("\n" + "=" * 60)
    print("示例 4: MCP Tool 使用")
    print("=" * 60)
    
    print("""
在 TRAE 中，您可以直接使用以下 MCP Tool：

1. query_skill_knowledge(query, top_k=5)
   - 查询昇腾工具专业知识库
   - 示例：query_skill_knowledge("msprof 延迟采集怎么用？")

2. rebuild_skill_index(force=False)
   - 重建知识库索引
   - 示例：rebuild_skill_index(force=True)

3. 访问 Resource: ascend://skills/status
   - 查看知识库状态
    """)


# ── 主函数 ──────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n📚 Skills 功能使用示例\n")
    
    # 运行所有示例
    demo_build_index()
    demo_intent_classification()
    demo_query_knowledge()
    demo_mcp_tools()
    
    print("\n" + "=" * 60)
    print("✅ 所有示例运行完成！")
    print("=" * 60)
