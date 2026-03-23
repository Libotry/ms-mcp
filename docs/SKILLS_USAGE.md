# Skills 知识库功能

## 📚 功能概述

Skills 功能为 TRAE 模型后端提供昇腾工具的专有知识库支持，可以将 `tool_docs` 目录下的 PDF、Word、Markdown、HTML 等文档直接喂给 LLM 进行分析，从而给出更为精确的回答。

### 核心能力

- **多格式文档支持**: PDF、Word (.docx)、Markdown (.md)、HTML
- **智能分块**: 自动将长文档切分为语义完整的片段（约 500-1000 字）
- **混合检索**: 结合 BM25 算法和 SQLite FTS5 全文检索，提高召回准确率
- **意图识别**: 自动识别用户问题类型，路由到合适的知识源
- **增量更新**: 自动检测文件变化，仅重新索引变更的文档

## 🏗️ 架构设计

```
┌─────────────────────────────────────────────────────────┐
│                     TRAE IDE                            │
│                  (LLM Backend)                          │
└────────────────────┬────────────────────────────────────┘
                     │ MCP Protocol
┌────────────────────▼────────────────────────────────────┐
│                   MCP Server                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   Router     │  │   Retriever  │  │   Analyzer   │ │
│  │  意图识别     │  │   混合检索    │  │  性能分析     │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘ │
│         │                 │                  │         │
│  ┌──────▼─────────────────▼──────────────────▼───────┐ │
│  │              Knowledge Layer                       │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────┐    │ │
│  │  │tools.json│  │SQLite DB │  │  CSV/DB/JSON │    │ │
│  │  │工具推荐   │  │PDF 知识库  │  │ Profiling 数据│    │ │
│  │  └──────────┘  └──────────┘  └──────────────┘    │ │
│  └───────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
                     ▲
                     │ 文档目录
┌────────────────────┴────────────────────────────────────┐
│                    tool_docs/                           │
│  - CANN 社区版 9.0.0-beta1 性能调优工具用户指南 01.pdf  │
│  - CANN 社区版 9.0.0-beta1 算子开发工具用户指南 01.pdf  │
│  - *.md, *.docx, *.html                                 │
└─────────────────────────────────────────────────────────┘
```

## 📁 目录结构

```
ms-mcp/
├── server.py                 # MCP Server 主入口（包含 Skills 相关 Tool）
├── skills/                   # Skills 功能模块
│   ├── __init__.py          # 模块导出
│   ├── parser.py            # 文档解析器（PDF/Word/MD/HTML）
│   ├── indexer.py           # 索引构建与管理
│   ├── retriever.py         # 混合检索引擎（BM25 + FTS5）
│   └── router.py            # 意图识别与路由
├── tool_docs/               # 原始文档目录（放置 PDF/Word 等文件）
├── knowledge/               # 知识库数据
│   ├── skills.db           # SQLite 索引数据库
│   └── tools.json          # 工具推荐知识库
└── examples/
    └── usage_example.py    # 使用示例
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install pymupdf4llm rank-bm25 beautifulsoup4 python-docx
```

或在项目根目录运行：

```bash
pip install -e .
```

### 2. 准备文档

将您的昇腾工具文档放入 `tool_docs/` 目录：

```
tool_docs/
├── CANN 社区版 9.0.0-beta1 性能调优工具用户指南 01.pdf
├── CANN 社区版 9.0.0-beta1 算子开发工具用户指南 01.pdf
├── msprof 使用指南.md
└── ...
```

支持的文件格式：
- `.pdf` - PDF 文档
- `.docx` - Word 文档
- `.md` / `.markdown` - Markdown 文档
- `.html` / `.htm` - HTML 网页

### 3. 构建索引

在 TRAE 中调用 MCP Tool：

```python
rebuild_skill_index(force=False)
```

或在命令行运行：

```bash
python examples/usage_example.py
```

### 4. 查询知识库

在 TRAE 对话中直接提问：

```
问：msprof 如何进行延迟采集？
问：如何使用 msSanitizer 调试算子？
问：性能分析的步骤是什么？
```

或使用 MCP Tool：

```python
query_skill_knowledge("msprof 延迟采集怎么用？", top_k=5)
```

## 🔧 MCP Tools 使用说明

### `query_skill_knowledge(query: str, top_k: int = 5)`

查询昇腾工具专业知识库，返回相关的文档片段和操作指南。

**参数：**
- `query`: 用户的查询问题，例如 "msprof 如何进行延迟采集？"
- `top_k`: 返回最相关的 K 个文档片段，默认 5

**返回：**
格式化的 Markdown 文本，包含：
- 相关知识库内容（来源、章节、内容片段）
- 相关性得分
- 使用建议

**示例：**

```python
result = query_skill_knowledge("msprof 如何进行延迟采集？")
print(result)
```

输出：
```markdown
## 相关知识库内容

### 片段 1
**来源**: CANN 社区版 9.0.0-beta1 性能调优工具用户指南 01.pdf
**章节**: 3.2 延迟采集模式
**内容**:
延迟采集模式适用于...
**相关性得分**: 0.892

### 片段 2
...
```

---

### `rebuild_skill_index(force: bool = False)`

重建 Skills 知识库索引。

**参数：**
- `force`: 是否强制重新索引所有文件（即使未变化），默认 False

**返回：**
重建结果的描述文本。

**示例：**

```python
# 增量更新（仅索引变化的文件）
result = rebuild_skill_index()

# 强制重建（清空所有旧索引）
result = rebuild_skill_index(force=True)
```

---

### `ascend://skills/status` (Resource)

查看 Skills 知识库状态。

**示例：**

在 TRAE 中访问该 Resource，或 programmatically：

```python
from mcp import ClientSession
async with ClientSession(...) as session:
    status = await session.read_resource("ascend://skills/status")
```

## 🎯 意图识别

系统会自动识别用户问题的意图类型：

| 意图类型 | 触发关键词 | 知识源 | 示例问题 |
|---------|-----------|--------|---------|
| `tool_recommendation` | "推荐工具"、"什么工具"、"msprof" | tools.json | "推荐一个性能分析工具" |
| `howto_guide` | "如何使用"、"操作步骤"、"--param" | PDF 知识库 | "msprof 如何进行延迟采集？" |
| `performance_analysis` | "op_summary"、"分析 profiling" | analyzer | "如何分析 op_summary 文件？" |
| `general_chat` | 其他 | 通用知识 | "你好" |

意图识别结果会影响：
1. 选择哪个知识源进行检索
2. 返回结果的格式化方式
3. 是否需要额外的提示信息

## 🔍 检索算法

### 混合检索策略

系统采用 **BM25 + FTS5** 的混合检索策略：

1. **FTS5 初筛**: 使用 SQLite FTS5 全文检索快速获取候选集（top_k × 2）
2. **BM25 精排**: 对候选集计算 BM25 分数，提高语义相关性
3. **分数归一化**: 将两种分数归一化到 [0, 1] 区间
4. **加权融合**: `combined = 0.6 × BM25 + 0.4 × FTS5`
5. **最终排序**: 按综合得分返回 top_k 结果

### 分词策略

支持中英文混合分词：

- **英文**: 按单词分割（保留数字和下划线）
  - `"msprof_tool"` → `["msprof", "tool"]`
  
- **中文**: 字符二元组（Bigram）
  - `"性能分析"` → `["性能", "能分", "分析"]`

这种策略在保证召回率的同时，不需要依赖外部中文分词库。

## 📊 性能优化

### 懒加载机制

- BM25 索引在首次检索时才加载到内存
- 避免启动时的不必要开销

### 增量索引

- 记录每个文件的修改时间和大小
- 仅当文件发生变化时重新索引
- 大幅减少重复构建的时间消耗

### 数据库优化

- 使用 SQLite FTS5 虚拟表
- 建立全文索引加速检索
- 合理的分块大小（500-1000 字）平衡精度和速度

## 🛠️ 高级用法

### 自定义分块大小

```python
from skills import SkillIndex

index = SkillIndex("knowledge/skills.db")
index.chunk_size = 1000  # 增大分块（默认 500）
index.chunk_overlap = 200  # 增加重叠（默认 50）
```

### 调整检索权重

```python
from skills import Retriever

retriever = Retriever("knowledge/skills.db")
results = retriever.search(
    query="msprof 使用",
    top_k=10,
    bm25_weight=0.7,  # 增加 BM25 权重（默认 0.6）
    fts_weight=0.3    # 降低 FTS5 权重（默认 0.4）
)
```

### 手动管理索引

```python
from skills import SkillIndex
from pathlib import Path

index = SkillIndex("knowledge/skills.db")

# 添加单个文件
index.add_file(Path("tool_docs/manual.pdf"))

# 移除文件
index.remove_file(Path("tool_docs/old_guide.md"))

# 列出所有已索引的文档
docs = index.indexer.list_documents()
for doc in docs:
    print(f"{doc.file_path}: {doc.chunk_count} chunks")

index.close()
```

## 🧪 测试与验证

### 运行示例脚本

```bash
python examples/usage_example.py
```

输出：
```
============================================================
示例 1: 构建知识库索引
============================================================
扫描目录：tool_docs
✓ 成功索引 2 个文件:
  - CANN 社区版 9.0.0-beta1 性能调优工具用户指南 01.pdf
    类型：pdf, 片段数：45
  - CANN 社区版 9.0.0-beta1 算子开发工具用户指南 01.pdf
    类型：pdf, 片段数：38

============================================================
示例 2: 意图识别
============================================================
查询：推荐一个性能分析工具
  意图：tool_recommendation
  置信度：0.30
  知识源：tools_json
  ...

============================================================
示例 3: 查询知识库
============================================================
查询：msprof 如何进行延迟采集？
------------------------------------------------------------
  [1] 来源：CANN 社区版 9.0.0-beta1 性能调优工具用户指南 01.pdf
      章节：3.2 延迟采集模式
      相关性：0.892
      内容：延迟采集模式适用于...
...
```

### 单元测试

```bash
pytest tests/test_skills.py -v
```

## ⚠️ 注意事项

1. **PDF 解析依赖**: 需要安装 `pymupdf4llm`，首次使用会下载 ONNX 模型（约 100MB）
2. **索引文件大小**: 大型 PDF 文档可能产生较大的 SQLite 数据库（通常 < 50MB）
3. **内存占用**: BM25 索引加载后约占文档总大小的 10-20% 内存
4. **中文检索**: 使用 Bigram 分词，对于专业术语可能需要更精确的提问

## 🔮 未来扩展

- [ ] 支持更多文档格式（PPT、Excel）
- [ ] 集成向量检索（Embedding + FAISS）
- [ ] 多语言支持（英文、日文等）
- [ ] 图表内容提取与描述
- [ ] 问答式检索（直接返回答案而非片段）

## 📞 技术支持

如有问题，请参考：
- [MCP Server 文档](../README.md)
- [Skills 技术实现细节](./skills 详细技术方案.md)
