好的，让我们深入讨论 Skills 功能的详细设计方案。

## 🏗️ 详细技术方案

### 一、架构设计

基于你现有的 MCP 架构，我建议采用 **"双层知识库 + 智能路由"** 的设计：

```
┌─────────────────────────────────────────────────────────┐
│                      TRAE IDE                           │
│                         │                               │
│                         ▼                               │
│              用户提问："msprof 如何采集通信性能数据？"     │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                    ms-mcp Server                        │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │           query_skill_knowledge(query)           │  │
│  │                   ↓                              │  │
│  │  ┌────────────────────────────────────────┐     │  │
│  │  │      Knowledge Router (智能路由)        │     │  │
│  │  │                                        │     │  │
│  │  │  1. 意图识别                            │     │  │
│  │  │     - 工具推荐类 → tools.json           │     │  │
│  │  │     - 操作指南类 → PDF 知识库            │     │  │
│  │  │     - 性能分析类 → analyzer + 数据文件    │     │  │
│  │  │                                        │     │  │
│  │  │  2. 混合检索                            │     │  │
│  │  │     - 关键词匹配 (BM25)                 │     │  │
│  │  │     - 语义相似度 (可选 Embedding)        │     │  │
│  │  └────────────────────────────────────────┘     │  │
│  │                   ↓                              │  │
│  │  ┌────────────────────────────────────────┐     │  │
│  │  │      Context Assembler (上下文组装)     │     │  │
│  │  │  - 检索 Top-K 相关段落                   │     │  │
│  │  │  - 去重 + 排序                          │     │  │
│  │  │  - 控制 Token 预算                       │     │  │
│  │  └────────────────────────────────────────┘     │  │
│  │                   ↓                              │  │
│  │         返回结构化上下文给 LLM                    │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                         │
         ┌───────────────┴───────────────┐
         │                               │
         ▼                               ▼
┌─────────────────┐             ┌─────────────────┐
│  结构化知识库    │             │  非结构化知识库  │
│  tools.json     │             │  tool_docs/*.pdf│
│  - 21 个工具     │             │  - 性能调优指南  │
│  - 元数据丰富    │             │  - 算子开发指南  │
│  - 精确匹配      │             │  - 详细操作步骤  │
└─────────────────┘             └─────────────────┘
```

---

### 二、核心技术选型对比

#### **1. PDF 解析方案**

| 方案                | 优点                                           | 缺点                     | 适用场景                 |
| ------------------- | ---------------------------------------------- | ------------------------ | ------------------------ |
| **PyMuPDF4LLM**     | 直接转 Markdown，保留标题/表格结构，中文支持好 | 依赖 pymupdf 库          | ✅ **推荐**，适合技术文档 |
| **pdfplumber**      | 表格提取能力强，细粒度控制                     | 不直接支持 Markdown      | 需要精确提取表格时       |
| **PyPDF2**          | 轻量，纯 Python                                | 格式丢失严重，中文易乱码 | ❌ 不推荐                 |
| **OCR (PaddleOCR)** | 支持扫描件                                     | 速度慢，准确率低         | 仅当 PDF 是扫描件时      |

**建议**：使用 `PyMuPDF4LLM`，它能直接将 PDF 转为带结构的 Markdown，非常适合技术文档。

---

#### **2. 检索策略**

##### **Level 1: 关键词检索（必选）**
```python
# BM25 算法，适合精确匹配专业术语
from rank_bm25 import BM25Okapi

# 优点：速度快，无需训练，适合"msprof 命令参数"这类查询
# 缺点：无法理解语义相似性
```

##### **Level 2: 语义检索（可选增强）**
```python
# 方案 A: 本地 Embedding (sentence-transformers)
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

# 方案 B: 调用 LLM Embedding API (如果 TRAE 提供)
# embedding = client.embeddings.create(input=query, model="text-embedding-3-small")

# 优点：能理解"如何采集数据" ≈ "数据采集方法"
# 缺点：需要额外依赖，增加复杂度
```

##### **Level 3: 混合检索（推荐）**
```python
# 关键词得分 × 0.6 + 语义得分 × 0.4
# 兼顾精确匹配和语义理解
```

**建议**：
- **第一阶段**：只用 BM25 关键词检索（快速上线，满足 80% 场景）
- **第二阶段**：如果发现关键词检索不够（如用户问法多样），再加语义检索

---

#### **3. 文本分块策略**

```python
# 方案 A: 固定长度分块（简单但效果差）
chunks = [text[i:i+500] for i in range(0, len(text), 500)]

# 方案 B: 按文档结构分块（✅ 推荐）
# - 每个章节作为一个 chunk
# - 保留章节标题作为 metadata
# - 示例：
#   {
#     "content": "msprof 支持动态采集模式...",
#     "metadata": {
#       "source": "CANN 社区版 9.0.0-beta1 性能调优工具用户指南 01.pdf",
#       "chapter": "第 3 章 数据采集",
#       "section": "3.2 动态采集",
#       "page": 15
#     }
#   }

# 方案 C: 递归分块（LangChain 风格）
# 按段落、句子逐级拆分，保持语义完整性
```

**建议**：采用 **方案 B（按文档结构分块）**，因为技术文档本身就有清晰的章节结构。

---

#### **4. 存储方案**

| 方案              | 优点                    | 缺点                   | 推荐度               |
| ----------------- | ----------------------- | ---------------------- | -------------------- |
| **内存索引**      | 零配置，启动快          | 重启后重建，文档多时慢 | ⭐⭐⭐ 适合 < 50 个文档 |
| **SQLite + FTS5** | 持久化，支持全文检索    | 需要建表管理           | ⭐⭐⭐⭐ 推荐            |
| **ChromaDB**      | 专为 RAG 设计，支持向量 | 额外依赖               | ⭐⭐ 过度设计          |
| **FAISS**         | Facebook 开源，性能好   | 需要序列化             | ⭐⭐ 适合大规模        |

**建议**：使用 **SQLite + FTS5 全文检索**，理由：
- 你已经在用 SQLite（analyzer.py 中解析 DB 文件）
- 无需额外依赖
- 支持持久化，重启不用重建索引
- 足够应对几百个文档的规模

---

### 三、详细实现方案

#### **模块设计**

```
ms-mcp/
├── skills/
│   ├── __init__.py
│   ├── parser.py        # PDF 解析器
│   ├── indexer.py       # 建立索引（SQLite FTS5）
│   ├── retriever.py     # 检索引擎（BM25 + SQL）
│   └── router.py        # 意图识别 + 路由
├── server.py            # 添加 query_skill_knowledge 工具
└── pyproject.toml       # 添加新依赖
```

---

#### **核心流程伪代码**

```python
# 1. 初始化阶段（服务器启动时）
class SkillKnowledgeBase:
    def __init__(self):
        self.db_path = KNOWLEDGE_DIR / "skills.db"
        self.indexer = Indexer(self.db_path)
        
        # 检查是否需要重建索引
        if not self.db_path.exists() or self._need_reindex():
            self.rebuild_index()
    
    def rebuild_index(self):
        # 解析所有 PDF
        pdf_files = list(TOOL_DOCS_DIR.glob("*.pdf"))
        for pdf in pdf_files:
            doc = parse_pdf_to_markdown(pdf)
            chunks = chunk_by_structure(doc)
            self.indexer.add_chunks(chunks)
```

```python
# 2. 查询阶段（用户提问时）
@mcp.tool()
def query_skill_knowledge(query: str, top_k: int = 5) -> str:
    """查询昇腾工具专业知识库，返回相关的文档片段。"""
    
    # Step 1: 意图识别
    intent = classify_intent(query)
    # - "tool_recommendation" → 走 tools.json
    # - "howto_guide" → 查 PDF 知识库
    # - "performance_analysis" → 走 analyzer
    
    if intent == "howto_guide":
        # Step 2: 检索
        results = kb.search(query, top_k=top_k)
        
        # Step 3: 组装上下文
        context = assemble_context(results, max_tokens=2000)
        
        # Step 4: 返回给 LLM
        return format_response(context, query)
```

```python
# 3. 检索实现
class Retriever:
    def search(self, query: str, top_k: int) -> list[Chunk]:
        # Step 1: BM25 粗排
        bm25_scores = self.bm25.get_scores(tokenize(query))
        
        # Step 2: SQLite FTS5 精排
        sql = """
            SELECT rowid, content, chapter, section, score
            FROM skills_fts
            WHERE content MATCH ?
            ORDER BY bm25(skills_fts) DESC
            LIMIT ?
        """
        return self.db.execute(sql, (query, top_k * 2))  # 取 2 倍候选
        
        # Step 3: 融合排序（BM25 + FTS5）
        # Step 4: 返回 Top-K
```

---

### 四、依赖清单

```toml
[project]
dependencies = [
    "mcp[cli]>=1.0.0",
    "pymupdf4llm>=0.0.10",     # PDF 转 Markdown
    "rank-bm25>=0.2.2",        # BM25 检索
    # 可选：语义检索
    # "sentence-transformers>=2.7.0",
]
```

---

### 五、关键技术决策点

#### **决策 1: 是否使用向量数据库？**
- **否**。原因：
  - 你的文档数量有限（目前 2 个，预计 < 50 个）
  - 技术文档查询以精确匹配为主（如命令、参数名）
  - BM25 + FTS5 已经足够，且更轻量

#### **决策 2: 是否需要实时更新索引？**
- **否**。原因：
  - PDF 文档不会频繁变更
  - 重启时检测文件变化再重建即可
  - 可以加一个 `force_reindex` 参数手动触发

#### **决策 3: 如何处理长文档？**
- **分块策略**：按章节拆分，每块控制在 500-1000 token
- **检索策略**：Top-K=5，最多返回 5 个最相关片段
- **上下文压缩**：如果片段过长，只保留与 query 最相关的句子

#### **决策 4: 是否支持多轮对话？**
- **暂不支持**。原因：
  - MCP 协议是无状态的
  - 如果需要，可以让 TRAE 端维护对话历史
  - 第一版先做好单轮问答

---

### 六、预期效果示例

**用户提问**：
> "msprof 如何进行延迟采集？"

**检索过程**：
1. 提取关键词：`msprof`, `延迟`, `采集`
2. BM25 检索 → 找到 PDF 中相关章节
3. 返回 Top-3 片段：
   - "3.4 延迟采集模式"（来自性能调优指南 P23）
   - "msprof --delay 参数说明"（来自性能调优指南 P25）
   - "延迟采集与动态采集的区别"（来自性能调优指南 P24）

**返回给 LLM 的上下文**：
```markdown
## 相关知识库内容

### 来源：CANN 社区版 9.0.0-beta1 性能调优工具用户指南 01.pdf - 第 3 章 数据采集

#### 3.4 延迟采集模式
延迟采集是指在应用运行一段时间后开始采集性能数据...
使用方法：msprof --delay=60 --output=./output python3 train.py

#### 3.3 动态采集模式
动态采集允许在应用运行过程中随时开启或停止采集...
```

**LLM 生成回答**：
> msprof 支持延迟采集模式，具体使用方法如下：
> 1. 使用 `--delay` 参数指定延迟时间（秒）
> 2. 示例命令：`msprof --delay=60 --output=./output python3 train.py`
> 3. 这会在应用启动 60 秒后开始采集数据...

---

## 🤔 需要你确认的问题

### **问题 1: 文档更新频率？**
- A) 很少更新（几个月一次）→ 启动时检查更新即可
- B) 经常更新（每周）→ 需要监听文件变化或提供手动刷新接口

### **问题 2: 是否需要支持其他格式？**
- A) 只需要 PDF
- B) 未来可能有 Word/Markdown/HTML

### **问题 3: 对响应速度的要求？**
- A) 1 秒内返回（需要优化索引和缓存）
- B) 3-5 秒可接受（首查询可能需要解析 PDF）

### **问题 4: 是否需要考虑多语言？**
- A) 只需中文
- B) 中英文混合（PDF 里有英文术语）

### **问题 5: 部署环境限制？**
- A) 可以安装任意 Python 包
- B) 有网络隔离，只能离线安装包

---

请回答以上问题，我会根据你的反馈调整方案并开始实现！🚀