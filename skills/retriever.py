"""检索引擎模块。

结合 BM25 算法和 SQLite FTS5 进行混合检索，
提供更精准的文档片段召回。
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .indexer import Chunk, Indexer


@dataclass
class SearchResult:
    """搜索结果。"""

    chunk: Chunk
    score_bm25: float
    score_fts: float
    combined_score: float


class Retriever:
    """混合检索引擎。"""

    def __init__(self, db_path: Path | str):
        """初始化检索器。

        Args:
            db_path: SQLite 数据库路径
        """
        self.db_path = Path(db_path)
        self.indexer = Indexer(db_path)
        self.bm25_index: Optional[any] = None
        self._bm25_initialized = False
        self.vector_store = None  # 向量存储
        self.reranker = None  # 重排序器

    def _ensure_bm25(self) -> None:
        """懒加载 BM25 索引。"""
        if self._bm25_initialized:
            return

        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            raise ImportError("请安装 rank-bm25: pip install rank-bm25")

        cursor = self.indexer.conn.cursor()
        cursor.execute("SELECT rowid, content FROM skills_fts")
        rows = cursor.fetchall()

        self._bm25_rowids: list[int] = []
        documents = []
        for row in rows:
            self._bm25_rowids.append(row["rowid"])
            documents.append(row["content"])

        self._rowid_to_bm25_idx: dict[int, int] = {
            rid: idx for idx, rid in enumerate(self._bm25_rowids)
        }

        if documents:
            tokenized_docs = [self._tokenize(doc) for doc in documents]
            self.bm25_index = BM25Okapi(tokenized_docs)
        else:
            self.bm25_index = None

        self._bm25_initialized = True

    def _tokenize(self, text: str) -> list[str]:
        """文本分词。

        支持中英文混合：
        - 英文：按单词分割
        - 中文：按字符二元组（bigram）

        Args:
            text: 输入文本

        Returns:
            list[str]: 分词结果
        """
        en_words = re.findall(r"[a-zA-Z][a-zA-Z0-9_]*", text.lower())
        cn_chars = re.findall(r"[\u4e00-\u9fff]", text)
        cn_bigrams = []
        for i in range(len(cn_chars) - 1):
            cn_bigrams.append(cn_chars[i:i+2])

        return en_words + ["".join(bg) for bg in cn_bigrams if len(bg) == 2]

    def search(
        self,
        query: str,
        top_k: int = 10,
        bm25_weight: float = 0.6,
        fts_weight: float = 0.4,
    ) -> list[SearchResult]:
        """执行混合检索。

        Args:
            query: 搜索查询
            top_k: 返回结果数量
            bm25_weight: BM25 权重
            fts_weight: FTS5 权重

        Returns:
            list[SearchResult]: 搜索结果列表
        """
        self._ensure_bm25()

        cursor = self.indexer.conn.cursor()

        cursor.execute("""
            SELECT rowid, content, chapter, section, source,
                   bm25(skills_fts) as fts_score
            FROM skills_fts
            WHERE content MATCH ?
            ORDER BY fts_score ASC
            LIMIT ?
        """, (query, top_k * 2))

        fts_results = []
        for row in cursor.fetchall():
            chunk = Chunk(
                content=row["content"],
                source=row["source"],
                chapter=row["chapter"],
                section=row["section"],
            )
            fts_results.append((chunk, row["fts_score"], row["rowid"]))

        if not fts_results:
            return []

        query_tokens = self._tokenize(query)

        bm25_scores = {}
        if self.bm25_index is not None:
            try:
                scores = self.bm25_index.get_scores(query_tokens)
                for chunk, _, rowid in fts_results:
                    bm25_idx = self._rowid_to_bm25_idx.get(rowid)
                    if bm25_idx is not None and bm25_idx < len(scores):
                        bm25_scores[id(chunk)] = scores[bm25_idx]
            except Exception:
                pass

        fts_scores = {id(chunk): score for chunk, score, _ in fts_results}

        min_fts = min(fts_scores.values()) if fts_scores else 0
        max_fts = max(fts_scores.values()) if fts_scores else 1
        fts_range = max_fts - min_fts if max_fts > min_fts else 1

        min_bm25 = min(bm25_scores.values()) if bm25_scores else 0
        max_bm25 = max(bm25_scores.values()) if bm25_scores else 1
        bm25_range = max_bm25 - min_bm25 if max_bm25 > min_bm25 else 1

        results = []
        for chunk, fts_score, _ in fts_results:
            chunk_id = id(chunk)

            norm_fts = (fts_score - min_fts) / fts_range
            norm_bm25 = (bm25_scores.get(chunk_id, min_bm25) - min_bm25) / bm25_range

            norm_fts = 1 - norm_fts

            combined = bm25_weight * norm_bm25 + fts_weight * norm_fts

            results.append(SearchResult(
                chunk=chunk,
                score_bm25=norm_bm25,
                score_fts=norm_fts,
                combined_score=combined,
            ))

        results.sort(key=lambda x: x.combined_score, reverse=True)

        return results[:top_k]

    def search_simple(self, query: str, top_k: int = 10) -> list[Chunk]:
        """简化检索接口（仅使用 FTS5）。

        Args:
            query: 查询文本
            top_k: 返回结果数量

        Returns:
            list[Chunk]: 搜索结果
        """
        results = self.search(query, top_k=top_k)
        return [result.chunk for result in results]

    def enable_vector_search(
        self,
        model_name: str = "BAAI/bge-small-zh-v1.5",
    ) -> None:
        """启用向量检索。

        Args:
            model_name: Embedding 模型名称
        """
        from .vector_store import EmbeddingConfig, VectorStore

        config = EmbeddingConfig(model_name=model_name)
        self.vector_store = VectorStore(self.db_path, config)
        print(f"向量检索已启用（模型：{model_name}）")

    def enable_reranking(
        self,
        model_name: str = "BAAI/bge-reranker-base",
    ) -> None:
        """启用重排序。

        Args:
            model_name: Cross-Encoder 模型名称
        """
        from .reranker import CrossEncoderReranker, RerankConfig

        config = RerankConfig(model_name=model_name)
        self.reranker = CrossEncoderReranker(config)
        print(f"重排序已启用（模型：{model_name}）")

    def search_with_vectors(
        self,
        query: str,
        top_k: int = 10,
        bm25_weight: float = 0.4,
        fts_weight: float = 0.3,
        vector_weight: float = 0.3,
    ) -> list[SearchResult]:
        """三级混合检索（BM25 + FTS5 + 向量）。

        Args:
            query: 查询文本
            top_k: 返回结果数量
            bm25_weight: BM25 权重
            fts_weight: FTS5 权重
            vector_weight: 向量相似度权重

        Returns:
            list[SearchResult]: 搜索结果
        """
        if not self.vector_store:
            return self.search(query, top_k=top_k, bm25_weight=bm25_weight + vector_weight, fts_weight=fts_weight)

        self._ensure_bm25()

        cursor = self.indexer.conn.cursor()

        cursor.execute("""
            SELECT rowid, content, chapter, section, source,
                   bm25(skills_fts) as fts_score
            FROM skills_fts
            WHERE content MATCH ?
            ORDER BY fts_score ASC
            LIMIT ?
        """, (query, top_k * 3))

        fts_results = []
        for row in cursor.fetchall():
            chunk = Chunk(
                content=row["content"],
                source=row["source"],
                chapter=row["chapter"],
                section=row["section"],
            )
            fts_results.append((chunk, row["fts_score"], row["rowid"]))

        if not fts_results:
            return []

        query_tokens = self._tokenize(query)
        bm25_scores = {}
        if self.bm25_index is not None:
            try:
                scores = self.bm25_index.get_scores(query_tokens)
                for chunk, _, rowid in fts_results:
                    bm25_idx = self._rowid_to_bm25_idx.get(rowid)
                    if bm25_idx is not None and bm25_idx < len(scores):
                        bm25_scores[id(chunk)] = scores[bm25_idx]
            except Exception:
                pass

        vector_scores = {}
        try:
            vector_results = self.vector_store.search(query, top_k=len(fts_results))
            vector_dict = {chunk_id: score for chunk_id, score in vector_results}

            for chunk, _, rowid in fts_results:
                if rowid in vector_dict:
                    vector_scores[id(chunk)] = vector_dict[rowid]
        except Exception as e:
            print(f"向量检索失败：{e}")

        fts_scores = {id(chunk): score for chunk, score, _ in fts_results}

        def normalize(scores: dict) -> dict:
            if not scores:
                return {}
            min_val = min(scores.values())
            max_val = max(scores.values())
            range_val = max_val - min_val if max_val > min_val else 1
            return {k: (v - min_val) / range_val for k, v in scores.items()}

        norm_fts = normalize({k: 1 - v for k, v in fts_scores.items()})
        norm_bm25 = normalize(bm25_scores)
        norm_vector = normalize(vector_scores)

        results = []
        for chunk, _, _ in fts_results:
            chunk_id = id(chunk)
            combined = (
                bm25_weight * norm_bm25.get(chunk_id, 0) +
                fts_weight * norm_fts.get(chunk_id, 0) +
                vector_weight * norm_vector.get(chunk_id, 0)
            )

            results.append(SearchResult(
                chunk=chunk,
                score_bm25=norm_bm25.get(chunk_id, 0),
                score_fts=norm_fts.get(chunk_id, 0),
                combined_score=combined,
            ))

        results.sort(key=lambda x: x.combined_score, reverse=True)
        return results[:top_k]

    def search_with_rerank(
        self,
        query: str,
        top_k: int = 10,
        stage_top_k: int = 50,
    ) -> list[SearchResult]:
        """带重排序的四级检索流水线。

        流程：
        1. BM25 + FTS5 + 向量 -> 召回 stage_top_k 个候选
        2. Cross-Encoder 重排序
        3. 返回 top_k 个结果

        Args:
            query: 查询文本
            top_k: 最终返回结果数量
            stage_top_k: 重排序前的候选数量

        Returns:
            list[SearchResult]: 重排序后的结果
        """
        candidates = self.search_with_vectors(
            query,
            top_k=stage_top_k,
            bm25_weight=0.4,
            fts_weight=0.3,
            vector_weight=0.3,
        )

        if not candidates:
            return []

        if self.reranker:
            candidate_pairs = [(r.chunk, r.combined_score) for r in candidates]
            reranked = self.reranker.rerank(
                query,
                [(id(chunk), chunk.content) for chunk, _ in candidate_pairs],
                top_k=top_k,
            )

            chunk_dict = {id(r.chunk): r for r in candidates}
            results = []
            for chunk_id, rerank_score in reranked:
                if chunk_id in chunk_dict:
                    result = chunk_dict[chunk_id]
                    results.append(SearchResult(
                        chunk=result.chunk,
                        score_bm25=result.score_bm25,
                        score_fts=result.score_fts,
                        combined_score=rerank_score,
                    ))
            return results

        return candidates[:top_k]

    def close(self) -> None:
        """关闭检索器。"""
        self.indexer.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
