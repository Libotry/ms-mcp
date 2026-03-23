"""昇腾工具推荐与性能分析 MCP Server

提供昇腾(Ascend)开发工具的智能推荐能力，
Profiling 数据的解析与性能瓶颈分析能力，
以及昇腾工具专业知识库查询能力(支持 PDF/Word/Markdown/HTML 文档)，
通过 MCP 协议接入 TRAE IDE。
"""

import json
import re
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from skills.profiling_analyzer import ProfilingAnalyzer

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"
TOOL_DOCS_DIR = Path(__file__).parent / "tool_docs"

mcp = FastMCP(
    "ms-mcp",
    instructions=(
        "昇腾工具推荐与性能分析 MCP Server："
        "根据用户需求推荐昇腾开发工具(包括性能分析工具和算子开发工具如 msKPP、msOpGen、msOpST、msSanitizer、msDebug、msProf 等)，"
        "解析 Profiling 数据(CSV、DB、JSON 格式均支持，包括 trace_view.json、communication.json、communication_matrix.json)"
        "返回结构化的客观性能指标和事实标记(findings)，由调用方 LLM 根据数据生成优化建议；"
        "同时支持查询昇腾工具专业知识库(PDF/Word/Markdown/HTML 文档)，提供详细的操作指南和技术说明"
    ),
)


def load_tools() -> list[dict]:
    """加载工具知识库。"""
    tools_file = KNOWLEDGE_DIR / "tools.json"
    with open(tools_file, "r", encoding="utf-8") as f:
        return json.load(f)


def _extract_keywords(text: str) -> list[str]:
    """从文本中提取关键词，支持中文二元组和英文单词。"""
    import re
    text = text.lower()
    en_words = re.findall(r'[a-z][a-z0-9_]+', text)
    cn_segments = re.findall(r'[\u4e00-\u9fff]+', text)
    cn_bigrams = []
    for seg in cn_segments:
        if len(seg) >= 2:
            for i in range(len(seg) - 1):
                cn_bigrams.append(seg[i:i+2])
        else:
            cn_bigrams.append(seg)
    return en_words + cn_bigrams


def search_tools(query: str) -> list[dict]:
    """根据查询匹配工具（含已索引文档）。

    匹配逻辑: 将 query 拆分为英文单词和中文二元组，在工具的各字段中
    匹配命中数，按命中数降序排列。
    """
    tools = load_tools() + _get_indexed_doc_tools()
    query_keywords = _extract_keywords(query)
    if not query_keywords:
        return []

    scored: list[tuple[int, dict]] = []
    for tool in tools:
        searchable = " ".join([
            tool.get("name", ""),
            tool.get("summary", ""),
            tool.get("description", ""),
            " ".join(tool.get("keywords", [])),
            " ".join(tool.get("use_cases", [])),
            tool.get("category", ""),
        ]).lower()

        score = 0
        for kw in query_keywords:
            if kw in searchable:
                score += 1

        if score > 0:
            scored.append((score, tool))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in scored]


def format_tool_info(tool: dict, detail: bool = False) -> str:
    """格式化工具信息用于输出。"""
    lines = [
        f"## {tool['name']}",
        f"**分类**：{tool.get('category', '未分类')}",
        f"**简介**：{tool['summary']}",
    ]
    if detail:
        if tool.get("description"):
            lines.append(f"\n**详细说明**：{tool['description']}")
        if tool.get("use_cases"):
            lines.append("\n**适用场景**：")
            for uc in tool["use_cases"]:
                lines.append(f"- {uc}")
        if tool.get("doc_url"):
            lines.append(f"\n**文档链接**：{tool['doc_url']}")
        if tool.get("related_tools"):
            lines.append(f"\n**相关工具**：{', '.join(tool['related_tools'])}")
        if tool.get("doc_source"):
            lines.append(f"\n**文档来源**：{tool['doc_source']}")
    return "\n".join(lines)


def _get_indexed_doc_tools() -> list[dict]:
    """从已索引的 PDF 文档中生成工具条目，用于合并到工具列表中。

    将每个已索引的文档作为一个"文档来源"条目，
    与 tools.json 中的工具互补展示。
    """
    db_path = KNOWLEDGE_DIR / "skills.db"
    if not db_path.exists():
        return []

    try:
        from skills import SkillIndex
        index = SkillIndex(db_path)
        docs = index.indexer.list_documents()
    except Exception:
        return []

    if not docs:
        return []

    # 读取 tools.json 中已有的文档名，避免重复
    existing_tools = load_tools()
    existing_names = {t.get("name", "").lower() for t in existing_tools}

    doc_tools = []
    for doc in docs:
        file_name = Path(doc.file_path).stem  # 去掉扩展名
        # 如果 tools.json 已有同名条目则跳过
        if file_name.lower() in existing_names:
            continue

        doc_tools.append({
            "id": f"doc_{Path(doc.file_path).stem}",
            "name": file_name,
            "category": "文档资料",
            "summary": f"{doc.doc_type.upper()} 文档，包含 {doc.chunk_count} 个知识片段，"
                       f"可通过 query_skill_knowledge 查询详细内容。",
            "description": f"来源文件：{Path(doc.file_path).name}，"
                          f"索引时间：{doc.indexed_at}，"
                          f"文件大小：{doc.file_size / 1024:.0f} KB。",
            "keywords": _extract_keywords(file_name),
            "use_cases": [],
            "doc_source": Path(doc.file_path).name,
        })

    return doc_tools


# ── Skills 知识库管理 ──────────────────────────────────────────────


def get_skill_index():
    """获取 Skills 知识库索引(懒加载)。"""
    from skills import SkillIndex
    return SkillIndex(KNOWLEDGE_DIR / "skills.db")


def build_skill_index_if_needed():
    """检查并构建 Skills 索引(如果不存在或需要更新)。"""
    from skills import SkillIndex

    index = SkillIndex(KNOWLEDGE_DIR / "skills.db")

    # 检查是否有文档需要索引
    if not TOOL_DOCS_DIR.exists():
        return []

    indexed = index.build_from_directory(TOOL_DOCS_DIR)
    return indexed


# ── MCP Tools: 知识库查询 ─────────────────────────────────────────


@mcp.tool()
def query_skill_knowledge(
    query: str,
    top_k: int = 5,
    use_vector: bool = False,
    use_rerank: bool = False,
) -> str:
    """查询昇腾工具专业知识库，返回相关的文档片段和操作指南。

    支持从 PDF、Word、Markdown、HTML 等文档中检索知识，
    适用于查询工具的使用方法、配置说明、操作步骤等详细指南。

    Args:
        query: 用户的查询问题，例如 "msprof 如何进行延迟采集？"
        top_k: 返回最相关的 K 个文档片段，默认 5
        use_vector: 是否启用向量检索（语义相似度），默认 False
        use_rerank: 是否启用 Cross-Encoder 重排序，默认 False
    """
    from skills import Retriever, route_query

    # Step 1: 意图识别
    route_result = route_query(query)

    # 如果不是操作指南类问题，提示用户
    if route_result.intent != "howto_guide":
        hint = (
            f"检测到您的问题可能属于「{route_result.intent}」类型。\n"
            f"如果是查询工具使用方法，建议明确提问如：「如何使用 xxx 工具？」\n\n"
        )
    else:
        hint = ""

    # Step 2: 检索知识库
    try:
        retriever = Retriever(KNOWLEDGE_DIR / "skills.db")

        # 启用高级检索功能
        if use_vector:
            retriever.enable_vector_search()

        if use_rerank:
            retriever.enable_reranking()

        # 根据配置选择检索方法
        if use_rerank:
            results = retriever.search_with_rerank(query, top_k=top_k)
        elif use_vector:
            results = retriever.search_with_vectors(query, top_k=top_k)
        else:
            results = retriever.search(query, top_k=top_k)

        retriever.close()
    except FileNotFoundError:
        return (
            "知识库索引尚未建立。\n"
            "请先调用 rebuild_skill_index 工具构建索引。"
        )

    if not results:
        return (
            f"{hint}未在知识库中找到相关内容。\n"
            "您可以尝试：\n"
            "- 换一种提问方式\n"
            "- 使用更具体的关键词\n"
            "- 调用 recommend_tool 查询工具推荐\n"
        )

    # Step 3: 上下文组装（Token 预算控制）
    # 粗略估算：1 个中文字符 ≈ 1.5 token，1 个英文单词 ≈ 1 token
    max_token_budget = 2000
    used_tokens = 0
    seen_contents = set()  # 用于去重
    selected_results = []

    for result in results:
        content = result.chunk.content
        # 去重：跳过内容高度相似的片段
        content_key = content[:100]
        if content_key in seen_contents:
            continue
        seen_contents.add(content_key)

        # 粗略估算 token 数
        cn_chars = len(re.findall(r'[\u4e00-\u9fff]', content))
        en_words = len(re.findall(r'[a-zA-Z]+', content))
        estimated_tokens = int(cn_chars * 1.5 + en_words)

        if used_tokens + estimated_tokens > max_token_budget and selected_results:
            # 超预算且已有结果，截断当前片段后停止
            remaining_budget = max_token_budget - used_tokens
            if remaining_budget > 200:
                # 还有余量，截断后加入
                truncated = content[:remaining_budget]
                result.chunk.content = truncated + "..."
                selected_results.append(result)
            break

        selected_results.append(result)
        used_tokens += estimated_tokens

    # Step 4: 格式化输出
    parts = [f"{hint}## 相关知识库内容\n"]

    for i, result in enumerate(selected_results, 1):
        chunk = result.chunk
        parts.append(f"\n### 片段 {i}")
        parts.append(f"**来源**: {chunk.source}")
        if chunk.chapter:
            parts.append(f"**章节**: {chunk.chapter}")
        if chunk.section:
            parts.append(f"**小节**: {chunk.section}")
        parts.append(f"\n```\n{chunk.content}\n```")
        parts.append(f"**相关性得分**: {result.combined_score:.3f}")

    parts.append("\n---\n以上是检索到的相关文档片段，供您参考。")

    return "\n".join(parts)


@mcp.tool()
def rebuild_skill_index(force: bool = False, with_vectors: bool = False) -> str:
    """重建 Skills 知识库索引。

    扫描 tool_docs 目录下的所有文档(PDF/Word/Markdown/HTML)，
    建立全文检索索引。正常情况下会自动检测文件变更，
    仅在文件变化时重新索引。

    Args:
        force: 是否强制重新索引所有文件(即使未变化)，默认 False
        with_vectors: 是否同时生成向量嵌入(用于语义检索)，默认 False。
                      需要安装 sentence-transformers 和模型，首次运行会下载模型。
    """
    from skills import SkillIndex

    if not TOOL_DOCS_DIR.exists():
        return f"错误：文档目录不存在：{TOOL_DOCS_DIR}"

    try:
        if force:
            # 强制重建：重置单例 + 清空旧索引
            SkillIndex.reset()
            db_path = KNOWLEDGE_DIR / "skills.db"
            if db_path.exists():
                import sqlite3
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                cursor.execute("DELETE FROM skills_fts")
                cursor.execute("DELETE FROM documents")
                cursor.execute("DELETE FROM chunks")
                # 如果向量表存在也一并清空
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='skill_embeddings'"
                )
                if cursor.fetchone():
                    cursor.execute("DELETE FROM skill_embeddings")
                conn.commit()
                conn.close()

        index = SkillIndex(KNOWLEDGE_DIR / "skills.db")

        if with_vectors:
            indexed = index.build_from_directory_with_vectors(TOOL_DOCS_DIR)
        else:
            indexed = index.build_from_directory(TOOL_DOCS_DIR)

        if not indexed:
            return "知识库已是最新，无需重新索引。"

        files_info = []
        for info in indexed:
            files_info.append(f"- {info.file_path}: {info.chunk_count} 个片段")

        mode = "FTS5 + 向量嵌入" if with_vectors else "FTS5"
        return (
            f"成功重建知识库索引（模式：{mode}）\n\n"
            f"新增/更新 {len(indexed)} 个文件：\n"
            + "\n".join(files_info)
        )
    except Exception as e:
        return f"重建索引失败：{type(e).__name__}: {e}"


# ── MCP Resources: 知识库状态 ─────────────────────────────────────


@mcp.resource("ascend://skills/status")
def skills_status() -> str:
    """提供 Skills 知识库状态信息。"""
    from skills import SkillIndex

    db_path = KNOWLEDGE_DIR / "skills.db"
    if not db_path.exists():
        return "状态：未初始化\n\n请调用 rebuild_skill_index 构建索引。"

    try:
        index = SkillIndex(db_path)
        docs = index.indexer.list_documents()

        if not docs:
            return "状态：空索引\n\n暂无已索引的文档。"

        lines = ["状态：正常\n", f"已索引 {len(docs)} 个文件：\n"]
        for doc in docs:
            lines.append(f"- {Path(doc.file_path).name} ({doc.doc_type}): {doc.chunk_count} 片段")

        return "\n".join(lines)
    except Exception as e:
        return f"状态：异常\n\n错误：{type(e).__name__}: {e}"


# ── MCP Tools ──────────────────────────────────────────────


@mcp.tool()
def recommend_tool(query: str) -> str:
    """根据用户的需求描述，推荐合适的昇腾开发工具(支持性能分析工具和算子开发工具)。

    支持推荐的工具类别：
    - 性能分析工具：msprof、MSPTI、PyTorch Profiler、MindSpore Profiler 等
    - 算子开发工具：msKPP(性能建模)、msOpGen(工程创建)、msOpST(算子测试)、
      msSanitizer(异常检测)、msDebug(算子调试)、msProf op(算子调优)、op_ut_run(UT测试)
    - 可视化工具：MindStudio Insight
    - 环境检查工具：msprechecker

    Args:
        query: 用户的需求描述，例如 "我想调试算子"、"如何检测算子内存泄漏"、"算子性能建模"
    """
    results = search_tools(query)
    if not results:
        hint = (
            "\u672a\u627e\u5230\u5339\u914d\u7684\u5de5\u5177\u3002"
            "\u8bf7\u5c1d\u8bd5\u6362\u4e00\u79cd\u63cf\u8ff0\u65b9\u5f0f\uff0c"
            "\u6216\u4f7f\u7528 list_all_tools \u67e5\u770b\u6240\u6709\u53ef\u7528\u5de5\u5177\u3002"
        )
        return hint

    parts = [f"\u6839\u636e\u4f60\u7684\u9700\u6c42\u300c{query}\u300d\uff0c\u63a8\u8350\u4ee5\u4e0b\u5de5\u5177\uff1a\n"]
    for tool in results:
        parts.append(format_tool_info(tool, detail=True))
        parts.append("---")
    return "\n".join(parts)


@mcp.tool()
def list_all_tools() -> str:
    """列出所有可用的昇腾开发工具概览（含已索引的文档资料）。"""
    tools = load_tools()
    doc_tools = _get_indexed_doc_tools()
    all_tools = tools + doc_tools

    if not all_tools:
        return "知识库为空，请先添加工具资料。"

    categories: dict[str, list[dict]] = {}
    for tool in all_tools:
        cat = tool.get("category", "未分类")
        categories.setdefault(cat, []).append(tool)

    parts = ["# 昇腾开发工具列表\n"]
    for cat, cat_tools in categories.items():
        parts.append(f"## {cat}")
        for tool in cat_tools:
            parts.append(format_tool_info(tool, detail=False))
            parts.append("")

    if doc_tools:
        parts.append("\n> 提示：「文档资料」分类下的条目来自已索引的 PDF/Word 等文档，"
                     "可通过 `query_skill_knowledge` 查询其中的详细内容。")

    return "\n".join(parts)


@mcp.tool()
def get_tool_detail(tool_id: str) -> str:
    """获取指定工具的详细信息。

    Args:
        tool_id: 工具的唯一标识符，例如 "msprof"
    """
    tools = load_tools()
    for tool in tools:
        if tool["id"] == tool_id:
            return format_tool_info(tool, detail=True)
    available_ids = [t["id"] for t in tools]
    return f"\u672a\u627e\u5230 ID \u4e3a '{tool_id}' \u7684\u5de5\u5177\u3002\u53ef\u7528\u7684\u5de5\u5177 ID\uff1a{', '.join(available_ids)}"


# ── MCP Resources ─────────────────────────────────────────


@mcp.resource("ascend://tools/catalog")
def tools_catalog() -> str:
    """提供昇腾工具完整目录作为上下文资源（含已索引文档）。"""
    tools = load_tools() + _get_indexed_doc_tools()
    parts = []
    for tool in tools:
        parts.append(f"- {tool['id']}: {tool['name']} - {tool['summary']}")
    return "\n".join(parts)


# ── MCP Tools: 性能分析 ───────────────────────────────────


@mcp.tool()
def analyze_profiling(file_path: str, top_n: int = 10) -> str:
    """分析 Profiling 性能数据文件(支持 CSV、DB、JSON)，返回结构化的客观性能指标和事实标记。

    本工具支持所有 msprof/Ascend Profiler 导出的数据格式，直接传入文件路径即可自动识别并分析。
    只输出客观数据和事实性标记(findings)，不包含主观优化建议。

    支持的文件格式：
    - op_summary*.csv: 算子耗时详情分析
    - op_statistic*.csv: 算子调用统计分析
    - step_trace*.csv: 迭代耗时和通信计算重叠分析
    - operator_memory*.csv: 算子内存占用分析
    - communication_statistic*.csv: 通信算子统计分析(CSV 格式)
    - *.db: msprof/PyTorch Profiler 导出的数据库文件
    - trace_view.json: Chrome Tracing 格式的算子级时间线数据(支持数百 MB 大文件)
    - communication.json: 通信算子耗时和带宽详情
    - communication_matrix.json: 设备间通信矩阵和带宽统计

    返回的 findings 字段是结构化的事实标记列表，每个标记包含 type 和相关数值，
    type 取值包括：dominant_op, high_ai_cpu_ratio, memory_bound_op,
    high_frequency_op, long_tail_op, high_free_ratio, low_overlap_ratio,
    high_bubble_ratio, unstable_iteration, high_data_aug_ratio,
    dominant_memory_op, comm_jitter, unstable_step,
    comm_high_wait_ratio, comm_high_idle, comm_bandwidth_imbalance 等。

    Args:
        file_path: Profiling 数据文件的绝对路径
        top_n: 返回 Top-N 高耗时/高占用的算子数量，默认 10
    """
    from analyzer import analyze_profiling_data
    try:
        result = analyze_profiling_data(file_path, top_n)
        return json.dumps(result, ensure_ascii=False, indent=2)
    except FileNotFoundError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"分析失败: {type(e).__name__}: {e}"}, ensure_ascii=False)


@mcp.tool()
def analyze_profiling_directory(dir_path: str, top_n: int = 10) -> str:
    """批量分析目录下所有 Profiling 数据文件(CSV、DB、JSON 均支持)，返回结构化客观数据。

    自动扫描目录中的 CSV、DB 和 JSON 文件(包括 trace_view.json、communication.json 等)，
    逐一分析并汇总结果。只输出客观数据和事实性标记(findings)，不包含主观优化建议。

    Args:
        dir_path: 包含 Profiling 数据文件的目录路径
        top_n: 返回 Top-N 高耗时/高占用的算子数量，默认 10
    """
    from analyzer import analyze_profiling_data, detect_file_type

    dir_p = Path(dir_path)
    if not dir_p.exists():
        return json.dumps({"error": f"目录不存在: {dir_path}"}, ensure_ascii=False)

    results = {}
    all_findings = []

    for f in sorted(dir_p.iterdir()):
        if not f.is_file():
            continue
        if f.suffix.lower() not in (".csv", ".db", ".json"):
            continue
        ftype = detect_file_type(str(f))
        if ftype == "unknown":
            continue
        try:
            analysis = analyze_profiling_data(str(f), top_n)
            results[f.name] = analysis
            if analysis.get("findings"):
                for finding in analysis["findings"]:
                    all_findings.append({"source_file": f.name, **finding})
        except Exception as e:
            results[f.name] = {"error": str(e)}

    if not results:
        return json.dumps({
            "error": f"目录 {dir_path} 中未找到可分析的 Profiling 数据文件"
        }, ensure_ascii=False)

    summary = {
        "analyzed_files": list(results.keys()),
        "total_files": len(results),
        "all_findings": all_findings,
        "details": results,
    }
    return json.dumps(summary, ensure_ascii=False, indent=2)


# ── Entry Point ────────────────────────────────────────────

if __name__ == "__main__":
    # 注册 Profiling Anomaly Analysis 工具
    try:
        from skills.profiling_anomaly_tool import register_profiling_anomaly_tool
        register_profiling_anomaly_tool(mcp)
        print("[Tools] Profiling Anomaly Analysis tool registered")
    except Exception as e:
        print(f"[Tools] Failed to register anomaly tool: {e}")
    
    # 注册 MFU Calculator 工具
    try:
        from skills.mfu_calculator_tool import register_mfu_calculator_tool
        register_mfu_calculator_tool(mcp)
        print("[Tools] MFU Calculator tool registered")
    except Exception as e:
        print(f"[Tools] Failed to register MFU calculator tool: {e}")
    
    # 启动时自动构建/更新知识库索引
    try:
        indexed = build_skill_index_if_needed()
        if indexed:
            print(f"[Skills] 已索引 {len(indexed)} 个文档")
        else:
            print("[Skills] 知识库索引已是最新")
    except Exception as e:
        print(f"[Skills] 索引构建跳过: {e}")

    mcp.run()
