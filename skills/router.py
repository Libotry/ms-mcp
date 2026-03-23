"""意图识别与路由模块。

根据用户问题类型，路由到不同的知识源：
- 工具推荐类 → tools.json
- 操作指南类 → PDF 知识库
- 性能分析类 → analyzer + 数据文件
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Literal

QueryIntent = Literal["tool_recommendation", "howto_guide", "performance_analysis", "general_chat"]


class IntentSource(Enum):
    """知识源类型。"""
    TOOLS_JSON = "tools_json"
    PDF_KNOWLEDGE = "pdf_knowledge"
    ANALYZER = "analyzer"
    GENERAL = "general"


@dataclass
class RouteResult:
    """路由结果。"""

    intent: QueryIntent
    confidence: float
    source: IntentSource
    keywords: list[str]
    suggested_action: str


# ── 意图识别规则 ──────────────────────────────────────────────

# 工具推荐类问题关键词
TOOL_RECOMMEND_PATTERNS = [
    r"推荐.*工具",
    r"什么工具.*(?:适合|可以|用来)",
    r"(?:哪个|哪些).*工具",
    r"工具.*比较",
    r"(?:性能分析 | 算子开发 | 调试 | 测试).*工具",
    r"msprof|mspti|mssanitizer|msdebug|msopgen|mskpp",  # 工具名直接出现
    r"list.*tool",
    r"available.*tool",
]

# 操作指南类问题关键词
HOWTO_GUIDE_PATTERNS = [
    r"如何.*(?:使用 | 操作 | 配置 | 设置 | 安装)",
    r"怎么.*(?:使用 | 操作 | 配置 | 设置 | 安装)",
    r"(?:用法 | 使用方法 | 操作步骤 | 操作流程)",
    r"(?:教程 | 指南 | 手册 | 说明)",
    r"(?:采集 | 解析 | 导出 | 导入).*数据",
    r"(?:动态采集 | 延迟采集 | 离线采集)",
    r"命令.*(?:参数 | 选项 | 用法)",
    r"--\w+",  # 命令行参数
    r"how.*(?:to|use)",
    r"(?:guide|tutorial|manual|instruction)",
]

# 性能分析类问题关键词
PERFORMANCE_ANALYSIS_PATTERNS = [
    r"(?:分析 | 解析).*profiling",
    r"(?:性能 | 耗时 | 瓶颈 | 优化).*分析",
    r"(?:op_summary|op_statistic|step_trace|trace_view)",
    r"(?:csv|db|json).*文件",
    r"analyze.*profiling",
    r"performance.*analysis",
]


def classify_intent(query: str) -> RouteResult:
    """分类用户查询意图。

    Args:
        query: 用户查询文本

    Returns:
        RouteResult: 路由结果
    """
    query_lower = query.lower()

    # 计分制：匹配的模式越多，置信度越高
    scores = {
        "tool_recommendation": 0.0,
        "howto_guide": 0.0,
        "performance_analysis": 0.0,
        "general_chat": 0.0,
    }

    matched_patterns = {
        "tool_recommendation": [],
        "howto_guide": [],
        "performance_analysis": [],
    }

    # 检测工具推荐类
    for pattern in TOOL_RECOMMEND_PATTERNS:
        if re.search(pattern, query_lower):
            scores["tool_recommendation"] += 0.3
            matched_patterns["tool_recommendation"].append(pattern)

    # 检测操作指南类
    for pattern in HOWTO_GUIDE_PATTERNS:
        if re.search(pattern, query_lower):
            scores["howto_guide"] += 0.3
            matched_patterns["howto_guide"].append(pattern)

    # 检测性能分析类
    for pattern in PERFORMANCE_ANALYSIS_PATTERNS:
        if re.search(pattern, query_lower):
            scores["performance_analysis"] += 0.3
            matched_patterns["performance_analysis"].append(pattern)

    # 提取关键词
    keywords = _extract_keywords(query)

    # 确定最高分的意图
    max_intent = max(scores, key=scores.get)
    max_score = scores[max_intent]

    # 如果所有分数都很低，认为是普通聊天
    if max_score < 0.3:
        max_intent = "general_chat"
        max_score = 0.5

    # 映射到知识源
    source_map = {
        "tool_recommendation": IntentSource.TOOLS_JSON,
        "howto_guide": IntentSource.PDF_KNOWLEDGE,
        "performance_analysis": IntentSource.ANALYZER,
        "general_chat": IntentSource.GENERAL,
    }

    # 生成建议动作
    action_map = {
        "tool_recommendation": "调用 recommend_tool 或 list_all_tools",
        "howto_guide": "查询 PDF 知识库并返回相关文档片段",
        "performance_analysis": "调用 analyze_profiling 分析性能数据",
        "general_chat": "直接回复或使用通用知识",
    }

    return RouteResult(
        intent=max_intent,  # type: ignore
        confidence=min(max_score, 1.0),
        source=source_map[max_intent],
        keywords=keywords,
        suggested_action=action_map[max_intent],
    )


def _extract_keywords(text: str) -> list[str]:
    """从文本中提取关键词。

    支持中英文：
    - 英文：提取单词
    - 中文：提取二元组

    Args:
        text: 输入文本

    Returns:
        list[str]: 关键词列表
    """
    import re

    text_lower = text.lower()

    # 英文单词
    en_words = re.findall(r"[a-z][a-z0-9_]+", text_lower)

    # 中文二元组
    cn_segments = re.findall(r"[\u4e00-\u9fff]+", text)
    cn_bigrams = []
    for seg in cn_segments:
        if len(seg) >= 2:
            for i in range(len(seg) - 1):
                cn_bigrams.append(seg[i:i+2])
        else:
            cn_bigrams.append(seg)

    # 合并并去重
    all_keywords = en_words + cn_bigrams
    seen = set()
    unique = []
    for kw in all_keywords:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)

    return unique


def route_query(query: str) -> RouteResult:
    """路由用户查询到合适的知识源。

    Args:
        query: 用户查询

    Returns:
        RouteResult: 路由结果
    """
    return classify_intent(query)


# ── 测试入口 ──────────────────────────────────────────────

if __name__ == "__main__":
    # 测试用例
    test_queries = [
        "推荐一个性能分析工具",
        "msprof 如何使用延迟采集？",
        "如何分析 op_summary 文件？",
        "有什么工具可以调试算子？",
        "帮我分析这个 profiling 数据",
        "你好",
    ]

    for q in test_queries:
        result = route_query(q)
        print(f"\n查询：{q}")
        print(f"意图：{result.intent}")
        print(f"置信度：{result.confidence:.2f}")
        print(f"知识源：{result.source.value}")
        print(f"关键词：{result.keywords}")
        print(f"建议动作：{result.suggested_action}")
