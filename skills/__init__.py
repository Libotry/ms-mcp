"""昇腾工具专业知识库技能模块。

支持从 PDF、Word、Markdown、HTML 等文档中提取知识，
建立全文检索索引，为 LLM 提供精准的领域知识上下文。
"""

from .parser import DocumentParser, parse_document
from .indexer import Indexer, SkillIndex
from .retriever import Retriever
from .router import RouteResult, route_query

__all__ = [
    "DocumentParser",
    "parse_document",
    "Indexer",
    "SkillIndex",
    "Retriever",
    "RouteResult",
    "route_query",
]
