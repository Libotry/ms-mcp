"""索引管理模块。

使用 SQLite FTS5 全文检索引擎建立知识库索引，
支持持久化存储和增量更新。
"""

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class Chunk:
    """文本分块数据结构。"""

    content: str  # 分块内容
    source: str  # 源文件名
    chapter: str = ""  # 所属章节
    section: str = ""  # 所属小节
    start_pos: int = 0  # 在原文中的起始位置
    end_pos: int = 0  # 在原文中的结束位置
    metadata: dict = field(default_factory=dict)  # 额外元数据

    def to_dict(self) -> dict:
        """转换为字典。"""
        return {
            "content": self.content,
            "source": self.source,
            "chapter": self.chapter,
            "section": self.section,
            "start_pos": self.start_pos,
            "end_pos": self.end_pos,
            "metadata": json.dumps(self.metadata, ensure_ascii=False),
        }


@dataclass
class DocumentInfo:
    """文档元信息。"""

    file_path: str
    file_hash: str
    doc_type: str
    chunk_count: int
    indexed_at: str
    file_size: int = 0

    def to_dict(self) -> dict:
        """转换为字典。"""
        return {
            "file_path": self.file_path,
            "file_hash": self.file_hash,
            "doc_type": self.doc_type,
            "chunk_count": self.chunk_count,
            "indexed_at": self.indexed_at,
            "file_size": self.file_size,
        }


class Indexer:
    """索引导入与管理器。"""

    def __init__(self, db_path: Path | str):
        """初始化索引器。

        Args:
            db_path: SQLite 数据库路径
        """
        self.db_path = Path(db_path)
        self.conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        """初始化数据库表结构。"""
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.cursor()

        # 创建 FTS5 虚拟表（全文检索）
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS skills_fts USING fts5(
                content,
                chapter,
                section,
                source,
                tokenize='unicode61'
            )
        """)

        # 创建文档信息表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL,
                file_hash TEXT NOT NULL,
                doc_type TEXT NOT NULL,
                chunk_count INTEGER DEFAULT 0,
                indexed_at TEXT NOT NULL,
                file_size INTEGER DEFAULT 0
            )
        """)

        # 创建分块映射表（关联 FTS5 和 documents）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                rowid INTEGER PRIMARY KEY,
                doc_id INTEGER,
                start_pos INTEGER,
                end_pos INTEGER,
                FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
            )
        """)

        # 创建索引加速查询
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_chunks_doc_id
            ON chunks(doc_id)
        """)

        self.conn.commit()

    def add_document(self, file_path: Path, content: str, doc_type: str) -> DocumentInfo:
        """添加文档到索引。

        Args:
            file_path: 文档文件路径
            content: Markdown 格式内容
            doc_type: 文档类型 (pdf/md/docx/html/txt)

        Returns:
            DocumentInfo: 文档元信息
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在：{file_path}")

        # 计算文件哈希（用于检测变更）
        file_hash = self._compute_file_hash(file_path)
        file_size = file_path.stat().st_size

        # 检查是否已存在
        existing = self._get_document_by_path(str(file_path))
        if existing and existing["file_hash"] == file_hash:
            # 文件未变更，跳过
            return DocumentInfo(
                file_path=str(file_path),
                file_hash=file_hash,
                doc_type=doc_type,
                chunk_count=0,
                indexed_at=existing["indexed_at"],
                file_size=file_size,
            )

        # 删除旧版本（如果有）
        if existing:
            self._delete_document(existing["id"])

        # 分块处理
        chunks = self._chunk_content(content, str(file_path))

        # 插入文档记录
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO documents (file_path, file_hash, doc_type, chunk_count, indexed_at, file_size)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (str(file_path), file_hash, doc_type, len(chunks), now, file_size))

        doc_id = cursor.lastrowid

        # 插入分块到 FTS5
        for chunk in chunks:
            cursor.execute("""
                INSERT INTO skills_fts (content, chapter, section, source)
                VALUES (?, ?, ?, ?)
            """, (chunk.content, chunk.chapter, chunk.section, chunk.source))

            rowid = cursor.lastrowid
            cursor.execute("""
                INSERT INTO chunks (rowid, doc_id, start_pos, end_pos)
                VALUES (?, ?, ?, ?)
            """, (rowid, doc_id, chunk.start_pos, chunk.end_pos))

        self.conn.commit()

        return DocumentInfo(
            file_path=str(file_path),
            file_hash=file_hash,
            doc_type=doc_type,
            chunk_count=len(chunks),
            indexed_at=now,
            file_size=file_size,
        )

    def _chunk_content(self, content: str, source: str, max_chunk_size: int = 800) -> list[Chunk]:
        """将文档内容分块。

        策略：按章节结构分块，保持语义完整性。

        Args:
            content: Markdown 内容
            source: 源文件名
            max_chunk_size: 最大分块大小（字符数）

        Returns:
            list[Chunk]: 分块列表
        """
        import re

        chunks = []
        lines = content.split("\n")

        current_chapter = ""
        current_section = ""
        current_block = []
        block_start = 0

        for i, line in enumerate(lines):
            # 检测章节标题
            heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()

                # 保存之前的块
                if current_block:
                    block_content = "\n".join(current_block)
                    if block_content.strip():
                        chunks.append(Chunk(
                            content=block_content,
                            source=source,
                            chapter=current_chapter,
                            section=current_section,
                            start_pos=block_start,
                            end_pos=i,
                        ))

                # 更新当前章节/小节
                if level == 1:
                    current_chapter = title
                    current_section = ""
                elif level == 2:
                    current_section = title
                elif level == 3:
                    current_section = f"{current_chapter} - {title}"

                # 开始新块
                current_block = [line]
                block_start = i

            else:
                # 累积到当前块
                current_block.append(line)

                # 检查是否超过大小限制
                if len("\n".join(current_block)) > max_chunk_size:
                    # 强制分割
                    block_content = "\n".join(current_block)
                    chunks.append(Chunk(
                        content=block_content[:max_chunk_size],
                        source=source,
                        chapter=current_chapter,
                        section=current_section,
                        start_pos=block_start,
                        end_pos=i,
                    ))
                    current_block = [block_content[max_chunk_size:]]
                    block_start = i

        # 处理最后一块
        if current_block:
            block_content = "\n".join(current_block)
            if block_content.strip():
                chunks.append(Chunk(
                    content=block_content,
                    source=source,
                    chapter=current_chapter,
                    section=current_section,
                    start_pos=block_start,
                    end_pos=len(lines),
                ))

        return chunks

    def _compute_file_hash(self, file_path: Path) -> str:
        """计算文件 SHA256 哈希值。"""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            buffer = f.read()
            hasher.update(buffer)
        return hasher.hexdigest()

    def _get_document_by_path(self, file_path: str) -> Optional[sqlite3.Row]:
        """根据文件路径获取文档信息。"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM documents WHERE file_path = ?", (file_path,))
        return cursor.fetchone()

    def _delete_document(self, doc_id: int) -> None:
        """删除文档及其索引。"""
        cursor = self.conn.cursor()

        # 先获取该文档的所有 rowid
        cursor.execute("SELECT rowid FROM chunks WHERE doc_id = ?", (doc_id,))
        rowids = [row["rowid"] for row in cursor.fetchall()]

        # 从 FTS5 删除
        for rowid in rowids:
            cursor.execute("DELETE FROM skills_fts WHERE rowid = ?", (rowid,))

        # 从 chunks 表删除
        cursor.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))

        # 从 documents 表删除
        cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))

        self.conn.commit()

    def list_documents(self) -> list[DocumentInfo]:
        """列出所有已索引的文档。"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM documents ORDER BY indexed_at DESC")

        return [
            DocumentInfo(
                file_path=row["file_path"],
                file_hash=row["file_hash"],
                doc_type=row["doc_type"],
                chunk_count=row["chunk_count"],
                indexed_at=row["indexed_at"],
                file_size=row["file_size"],
            )
            for row in cursor.fetchall()
        ]

    def needs_reindex(self, file_path: Path) -> bool:
        """检查文件是否需要重新索引。"""
        file_path = Path(file_path)
        if not file_path.exists():
            return False

        existing = self._get_document_by_path(str(file_path))
        if not existing:
            return True

        current_hash = self._compute_file_hash(file_path)
        return existing["file_hash"] != current_hash

    def close(self) -> None:
        """关闭数据库连接。"""
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class SkillIndex:
    """知识库索引高级接口（单例模式）。"""

    _instance: Optional["SkillIndex"] = None
    _initialized = False

    def __new__(cls, db_path: Optional[Path | str] = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, db_path: Optional[Path | str] = None):
        if SkillIndex._initialized:
            return

        if db_path is None:
            raise ValueError("首次初始化 SkillIndex 必须提供 db_path")

        self.indexer = Indexer(db_path)
        self.vector_store = None  # 延迟初始化
        SkillIndex._initialized = True

    def enable_vectorization(self, model_name: str = "BAAI/bge-small-zh-v1.5") -> None:
        """启用向量化功能。

        Args:
            model_name: Embedding 模型名称
        """
        from .vector_store import EmbeddingConfig, VectorStore

        config = EmbeddingConfig(model_name=model_name)
        self.vector_store = VectorStore(self.indexer.db_path, config)
        print(f"✓ 向量化功能已启用（模型：{model_name}）")

    @classmethod
    def reset(cls) -> None:
        """重置单例状态，允许重新初始化。用于 force rebuild 场景。"""
        if cls._instance is not None:
            cls._instance.close()
        cls._instance = None
        cls._initialized = False

    def build_from_directory(self, docs_dir: Path) -> list[DocumentInfo]:
        """从目录构建索引。

        Args:
            docs_dir: 文档目录路径

        Returns:
            list[DocumentInfo]: 文档信息列表
        """
        from .parser import parse_document

        docs_dir = Path(docs_dir)
        if not docs_dir.exists():
            raise FileNotFoundError(f"目录不存在：{docs_dir}")

        supported_extensions = {".pdf", ".md", ".markdown", ".docx", ".html", ".htm", ".txt"}
        indexed = []

        for file_path in docs_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in supported_extensions:
                # 检查是否需要重新索引
                if not self.indexer.needs_reindex(file_path):
                    continue

                try:
                    content, doc_type = parse_document(file_path)
                    info = self.indexer.add_document(file_path, content, doc_type)
                    indexed.append(info)
                except Exception as e:
                    print(f"解析文件失败 {file_path}: {e}")

        return indexed

    def build_from_directory_with_vectors(
        self,
        docs_dir: Path,
        model_name: str = "BAAI/bge-small-zh-v1.5",
        batch_size: int = 32,
    ) -> list[DocumentInfo]:
        """从目录构建索引并生成向量。

        Args:
            docs_dir: 文档目录路径
            model_name: Embedding 模型名称
            batch_size: 批处理大小

        Returns:
            list[DocumentInfo]: 文档信息列表
        """
        from .parser import parse_document

        # 首先启用向量化
        self.enable_vectorization(model_name)

        docs_dir = Path(docs_dir)
        if not docs_dir.exists():
            raise FileNotFoundError(f"目录不存在：{docs_dir}")

        supported_extensions = {".pdf", ".md", ".markdown", ".docx", ".html", ".htm", ".txt"}
        indexed = []
        chunks_to_embed = []
        chunk_ids = []

        # 第一阶段：解析和索引
        for file_path in docs_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in supported_extensions:
                if not self.indexer.needs_reindex(file_path):
                    continue

                try:
                    content, doc_type = parse_document(file_path)
                    info = self.indexer.add_document(file_path, content, doc_type)
                    indexed.append(info)

                    # 收集新生成的 chunks 用于向量化
                    cursor = self.indexer.conn.cursor()
                    cursor.execute(
                        "SELECT rowid, content FROM skills_fts WHERE source = ?",
                        (str(file_path),)
                    )
                    for row in cursor.fetchall():
                        chunk_ids.append(row["rowid"])
                        chunks_to_embed.append(row["content"])

                except Exception as e:
                    print(f"解析文件失败 {file_path}: {e}")

        # 第二阶段：批量生成向量
        if chunks_to_embed and self.vector_store:
            print(f"正在为 {len(chunks_to_embed)} 个分块生成向量...")
            embeddings = self.vector_store.embedding_model.encode(
                chunks_to_embed, batch_size=batch_size, show_progress=True
            )
            self.vector_store.store_embeddings(chunk_ids, embeddings)
            print(f"✓ 已向量化 {len(chunk_ids)} 个分块")

        return indexed

    def search(self, query: str, top_k: int = 10) -> list[Chunk]:
        """搜索相关文档片段。

        Args:
            query: 搜索查询
            top_k: 返回结果数量

        Returns:
            list[Chunk]: 相关分块列表
        """
        cursor = self.indexer.conn.cursor()

        # 使用 FTS5 全文检索
        cursor.execute("""
            SELECT rowid, content, chapter, section, source,
                   bm25(skills_fts) as score
            FROM skills_fts
            WHERE content MATCH ?
            ORDER BY score ASC
            LIMIT ?
        """, (query, top_k))

        results = []
        for row in cursor.fetchall():
            results.append(Chunk(
                content=row["content"],
                source=row["source"],
                chapter=row["chapter"],
                section=row["section"],
                metadata={"score": row["score"]},
            ))

        return results

    def close(self) -> None:
        """关闭索引。"""
        self.indexer.close()
