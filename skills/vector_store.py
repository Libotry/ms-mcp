"""向量检索模块。

使用 Sentence-BERT 生成文本嵌入向量，
支持语义相似度检索和向量存储。
"""

import hashlib
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass
class EmbeddingConfig:
    """Embedding 配置。"""

    model_name: str = "BAAI/bge-small-zh-v1.5"  # 中文优化的轻量模型
    dimension: int = 512  # 向量维度
    normalize: bool = True  # 是否归一化


class EmbeddingModel:
    """Embedding 模型封装。"""

    def __init__(self, config: Optional[EmbeddingConfig] = None):
        """初始化 Embedding 模型。

        Args:
            config: Embedding 配置
        """
        self.config = config or EmbeddingConfig()
        self.model = None
        self._initialized = False

    def _ensure_loaded(self) -> None:
        """懒加载模型。"""
        if self._initialized:
            return

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "请安装 sentence-transformers: pip install sentence-transformers"
            )

        print(f"正在加载 Embedding 模型：{self.config.model_name}")
        self.model = SentenceTransformer(self.config.model_name)
        self._initialized = True

    def encode(
        self, texts: list[str], batch_size: int = 32, show_progress: bool = False
    ) -> np.ndarray:
        """生成文本嵌入向量。

        Args:
            texts: 文本列表
            batch_size: 批处理大小
            show_progress: 是否显示进度条

        Returns:
            嵌入向量数组 (n_texts, dimension)
        """
        self._ensure_loaded()

        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            normalize_embeddings=self.config.normalize,
            convert_to_numpy=True,
        )

        return embeddings

    def encode_query(self, query: str) -> np.ndarray:
        """生成查询向量。

        Args:
            query: 查询文本

        Returns:
            查询向量 (dimension,)
        """
        # 对于某些模型，查询可能需要特殊前缀
        if "bge" in self.config.model_name.lower():
            query = "为这个句子生成表示以用于检索：" + query

        embedding = self.encode([query])
        return embedding[0]


class VectorStore:
    """向量存储器。

    使用 SQLite 存储向量（pickle 序列化），
    支持高效的余弦相似度检索。
    """

    def __init__(self, db_path: Path | str, config: Optional[EmbeddingConfig] = None):
        """初始化向量存储器。

        Args:
            db_path: SQLite 数据库路径
            config: Embedding 配置
        """
        self.db_path = Path(db_path)
        self.config = config or EmbeddingConfig()
        self.embedding_model = EmbeddingModel(self.config)
        self.conn = None
        self._init_db()

    def _init_db(self) -> None:
        """初始化数据库表结构。"""
        import sqlite3

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

        # 创建向量存储表
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS skill_embeddings (
                chunk_id INTEGER PRIMARY KEY,
                embedding BLOB NOT NULL,
                normalized INTEGER DEFAULT 1,
                FOREIGN KEY (chunk_id) REFERENCES skills_fts(rowid)
            )
        """)

        # 创建索引加速查找
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_emb_chunk ON skill_embeddings(chunk_id)"
        )

        self.conn.commit()

    def store_embeddings(self, chunk_ids: list[int], embeddings: np.ndarray) -> None:
        """存储嵌入向量。

        Args:
            chunk_ids: 分块 ID 列表
            embeddings: 嵌入向量数组 (n_chunks, dimension)
        """
        cursor = self.conn.cursor()

        for chunk_id, embedding in zip(chunk_ids, embeddings):
            # 使用 pickle 序列化向量
            emb_blob = pickle.dumps(embedding.astype(np.float32))

            # 检查是否已存在
            cursor.execute(
                "SELECT 1 FROM skill_embeddings WHERE chunk_id = ?", (chunk_id,)
            )
            exists = cursor.fetchone() is not None

            if exists:
                cursor.execute(
                    "UPDATE skill_embeddings SET embedding = ? WHERE chunk_id = ?",
                    (emb_blob, chunk_id),
                )
            else:
                cursor.execute(
                    "INSERT INTO skill_embeddings (chunk_id, embedding) VALUES (?, ?)",
                    (chunk_id, emb_blob),
                )

        self.conn.commit()

    def load_embedding(self, chunk_id: int) -> Optional[np.ndarray]:
        """加载单个嵌入向量。

        Args:
            chunk_id: 分块 ID

        Returns:
            嵌入向量或 None
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT embedding FROM skill_embeddings WHERE chunk_id = ?", (chunk_id,)
        )
        row = cursor.fetchone()

        if row is None:
            return None

        return pickle.loads(row["embedding"])

    def cosine_similarity(
        self, query_vector: np.ndarray, chunk_vectors: np.ndarray
    ) -> np.ndarray:
        """计算余弦相似度。

        Args:
            query_vector: 查询向量 (dimension,)
            chunk_vectors: 分块向量矩阵 (n_chunks, dimension)

        Returns:
            相似度分数 (n_chunks,)
        """
        # 如果向量已归一化，余弦相似度简化为点积
        if self.config.normalize:
            similarities = np.dot(chunk_vectors, query_vector)
        else:
            # 手动计算余弦相似度
            query_norm = np.linalg.norm(query_vector)
            chunk_norms = np.linalg.norm(chunk_vectors, axis=1)

            # 避免除零
            chunk_norms[chunk_norms == 0] = 1e-10

            dot_products = np.dot(chunk_vectors, query_vector)
            similarities = dot_products / (chunk_norms * query_norm)

        return similarities

    def search(
        self, query: str, top_k: int = 20, chunk_ids: Optional[list[int]] = None
    ) -> list[tuple[int, float]]:
        """向量相似度检索。

        Args:
            query: 查询文本
            top_k: 返回结果数量
            chunk_ids: 限制检索范围的分块 ID 列表（可选）

        Returns:
            [(chunk_id, similarity_score), ...]
        """
        # 生成查询向量
        query_vector = self.embedding_model.encode_query(query)

        # 确定要检索的分块
        if chunk_ids is None:
            cursor = self.conn.cursor()
            cursor.execute("SELECT chunk_id FROM skill_embeddings")
            chunk_ids = [row["chunk_id"] for row in cursor.fetchall()]

        if not chunk_ids:
            return []

        # 加载所有候选向量
        vectors = []
        valid_ids = []
        for chunk_id in chunk_ids:
            emb = self.load_embedding(chunk_id)
            if emb is not None:
                vectors.append(emb)
                valid_ids.append(chunk_id)

        if not vectors:
            return []

        chunk_matrix = np.array(vectors)

        # 计算相似度
        similarities = self.cosine_similarity(query_vector, chunk_matrix)

        # 排序取 top-k
        sorted_indices = np.argsort(similarities)[::-1][:top_k]

        results = [(valid_ids[i], float(similarities[i])) for i in sorted_indices]

        return results

    def count(self) -> int:
        """获取向量总数。"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM skill_embeddings")
        return cursor.fetchone()[0]

    def close(self) -> None:
        """关闭数据库连接。"""
        if self.conn:
            self.conn.close()
