# ms-mcp：昇腾工具推荐与性能分析 MCP Server

根据用户需求智能推荐昇腾（Ascend）开发工具（性能分析工具 + 算子开发工具），并解析 msprof 采集的 Profiling 数据，返回结构化的客观性能指标和事实标记（findings），由调用方 LLM 生成优化建议。
根据用户需求智能推荐昇腾（Ascend）开发工具（性能分析工具 + 算子开发工具），解析 msprof 采集的 Profiling 数据，并提供昇腾工具专业知识库查询能力（支持 PDF/Word/Markdown/HTML 文档），返回结构化的客观性能指标、事实标记（findings）和详细操作指南，由调用方 LLM 生成优化建议。

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                      TRAE IDE                           │
│                                                         │
│  用户提问 ──→ TRAE LLM                                  │
│                 │                                       │
│                 ├── 工具推荐类问题                        │
│                 │   → 调用 recommend_tool / list_all_tools│
│                 │   → MCP 返回匹配的工具信息              │
│                 │                                       │
│                 ├── 操作指南类问题                        │
│                 │   → 调用 query_skill_knowledge         │
│                 │   → MCP 返回 PDF 知识库相关片段         │
│                 │                                       │
│                 └── 性能分析类问题                        │
│                     → 调用 analyze_profiling             │
│                     → MCP 返回客观数据 + findings         │
│                     → TRAE LLM 生成优化建议              │
└─────────────────────────────────────────────────────────┘
                          │
                    MCP 协议通信
                          │
┌─────────────────────────────────────────────────────────┐
│                    ms-mcp Server                        │
│                                                         │
│  ┌───────────────┐   ┌──────────────────┐              │
│  │ 工具知识库     │   │ Profiling 分析引擎│              │
│  │ (tools.json)  │   │ (analyzer.py)    │              │
│  │               │   │                  │              │
│  │ 性能分析 x12  │   │ CSV / DB / JSON  │              │
│  │ 算子开发 x7   │   │ 9 种文件格式      │              │
│  │ 可视化   x1   │   │ 16 种 findings   │              │
│  │ 环境检查 x1   │   │                  │              │
│  └───────────────┘   └──────────────────┘              │
│                                                         │
│  ┌───────────────────────────────────────────────────┐ │
│  │              Skills 知识库                         │ │
│  │  (skills/)                                         │ │
│  │                                                    │ │
│  │  PDF/Word/MD/HTML 文档解析与检索                   │ │
│  │  - 智能分块 (500-1000 字)                           │ │
│  │  - 混合检索 (BM25 + FTS5)                          │ │
│  │  - 意图识别 (4 种类型)                               │ │
│  │  - 增量更新                                        │ │
│  └───────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**职责边界**：MCP 不做任何网络请求，只读取用户本地文件并计算。搜索和建议生成的责任交给 TRAE 后端 LLM。

## 快速开始

### 1. 安装依赖

```bash
pip install "mcp[cli]"
# 如需使用 Skills 知识库功能（推荐）：
pip install pymupdf4llm rank-bm25 beautifulsoup4 python-docx
# 或直接：
pip install -e .

### 2. 在 TRAE IDE 中配置

在 MCP 配置文件（`mcp.json`）中添加：

```json
{
  "mcpServers": {
    "ascend-tools": {
      "command": "python",
      "args": ["<项目路径>/server.py"],
      "env": {}
    }
  }
}
```

> 将 `<项目路径>` 替换为实际路径。确保 `python` 在系统 PATH 中可用，否则使用完整路径。

### 3. 验证连接

配置保存后，TRAE 会自动启动 MCP Server。确认 `ascend-tools` 显示为**已连接**状态。

## 提供的 MCP 能力

### Tools

| 工具名 | 说明 |
|--------|------|
| `recommend_tool` | 根据需求描述推荐昇腾开发工具（支持性能分析 + 算子开发工具） |
| `list_all_tools` | 列出所有可用工具概览（共 21 个工具，4 大分类） |
| `get_tool_detail` | 获取指定工具的详细信息 |
| `analyze_profiling` | 分析单个 Profiling 数据文件，返回客观指标 + findings |
| `analyze_profiling_directory` | 批量分析目录下所有 Profiling 文件，汇总 findings |
| `query_skill_knowledge` | 查询昇腾工具专业知识库（支持 PDF/Word/Markdown/HTML 文档） |
| `rebuild_skill_index` | 重建知识库索引（可选强制全量重建） |

### Resources

| 资源 URI | 说明 |
|----------|------|
| `ascend://tools/catalog` | 工具目录（供 AI 作为上下文） |
| `ascend://skills/status` | 知识库状态信息（文档数量、索引大小等） |

## 工具知识库

### 工具分类总览（21 个工具）

#### 性能分析工具（12 个）

| 工具 ID | 名称 | 功能定位 |
|---------|------|---------|
| `msprof` | msprof 模型调优工具 | 命令行性能数据采集和解析 |
| `mspti` | MSPTI 调优工具 | 通用 Profiling API 接口（Python/C） |
| `ms_service_profiler` | msServiceProfiler | MindIE 推理服务化性能采集 |
| `mindspore_profiler` | MindSpore Profiler | MindSpore 框架性能分析 |
| `ascend_pytorch_profiler` | Ascend PyTorch Profiler | PyTorch 框架性能分析 |
| `tensorflow_profiling` | TensorFlow 框架接口采集 | TensorFlow 框架性能采集 |
| `acl_cpp_profiling` | ACL C&C++ 接口采集 | 离线推理定制化性能采集 |
| `acl_python_profiling` | ACL Python 接口采集 | ACL 的 Python 封装版本 |
| `ascend_graph_profiling` | Ascend Graph 接口采集 | Graph 模式性能采集 |
| `acl_json_profiling` | acl.json 配置文件采集 | 无代码修改的配置文件采集 |
| `env_var_profiling` | 环境变量采集 | 通过环境变量控制性能采集 |
| `msprof_analyze` | msprof-analyze | 性能数据自动化分析 |

#### 算子开发工具（7 个）

| 工具 ID | 名称 | 功能定位 |
|---------|------|---------|
| `mskpp` | msKPP 算子设计工具 | 算子性能建模、自动调优、msOpGen 工程调用 |
| `msopgen` | msOpGen 算子工程创建工具 | 基于算子原型定义生成工程、编译部署 |
| `msopst` | msOpST 算子测试工具 | 真实硬件环境 ST 测试、功能正确性验证 |
| `mssanitizer` | msSanitizer 异常检测工具 | 内存检测/竞争检测/未初始化检测/同步检测 |
| `msdebug` | msDebug 算子调试工具 | 断点、单步调试、内存打印、Core dump 解析 |
| `msprof_op` | msProf 算子调优工具 | Roofline、热力图、指令流水图等性能可视化 |
| `op_ut_run` | op_ut_run 算子 UT 测试工具 | 算子单元测试，代码分支覆盖验证 |

#### 可视化工具（1 个）

| 工具 ID | 名称 | 功能定位 |
|---------|------|---------|
| `mindstudio_insight` | MindStudio Insight | 性能数据图形化展示 |

#### 环境检查工具（1 个）

| 工具 ID | 名称 | 功能定位 |
|---------|------|---------|
| `msprechecker` | msprechecker | 服务化配置环境预检 |

## 性能分析功能

### 支持的数据格式（9 种）

| 文件类型 | 文件名模式 | 分析内容 |
|----------|-----------|---------|
| op_summary | `op_summary*.csv` | 算子耗时排名、Task Type 分布、memory bound 检测 |
| op_statistic | `op_statistic*.csv` | 算子调用统计、高频低效算子、长尾问题检测 |
| step_trace | `step_trace*.csv` | 迭代耗时、通信计算重叠率、Bubble/Free 占比 |
| operator_memory | `operator_memory*.csv` | 算子内存占用排名、内存热点定位 |
| communication | `communication_statistic*.csv` | 通信算子统计、通信抖动检测（CSV 格式） |
| DB | `*.db` | msprof/PyTorch Profiler 导出的数据库，含全维度分析 |
| trace_view | `trace_view.json` | Chrome Tracing 格式的算子级时间线，按算子聚合耗时统计 |
| communication | `communication.json` | 通信算子耗时、带宽、等待/空闲时间详情 |
| communication_matrix | `communication_matrix.json` | 设备间通信矩阵、传输类型带宽统计 |

### findings 类型（16 种）

MCP 返回的 `findings` 是结构化的事实标记列表，每个标记包含 `type` 和相关数值。

| type | 含义 | 关键字段 |
|------|------|---------|
| `dominant_op` | 单算子耗时占比 >30% | op_name, ratio_pct |
| `high_ai_cpu_ratio` | AI CPU 算子占比 >10% | ratio_pct, ai_cpu_time_us |
| `memory_bound_op` | 算子存在内存瓶颈 | op_name, duration_us |
| `high_frequency_op` | 高频高耗时算子 | op_type, count, avg_time_us, ratio_pct |
| `long_tail_op` | 最大耗时远超平均值 | op_type, max_time_us, avg_time_us, max_avg_ratio |
| `dominant_memory_op` | 单算子内存占比 >30% | op_name, ratio_pct, size |
| `high_free_ratio` | 设备空闲占比 >10% | free_ratio_pct |
| `low_overlap_ratio` | 通信计算重叠率 <30% | overlap_ratio_pct |
| `high_bubble_ratio` | 流水线 Bubble >5% | bubble_ratio_pct |
| `unstable_iteration` | 迭代耗时不稳定 | max_iteration_us, avg_iteration_us |
| `high_data_aug_ratio` | 数据加载占比 >10% | data_aug_ratio_pct |
| `comm_jitter` | 通信抖动 | op_type, max_time_us, avg_time_us |
| `unstable_step` | Step 耗时不稳定 | max_step_us, avg_step_us |
| `comm_high_wait_ratio` | 通信算子等待占比高 | op_name, wait_ratio, elapse_ms |
| `comm_high_idle` | 通信算子空闲占比高 | op_name, idle_ms, idle_ratio |
| `comm_bandwidth_imbalance` | 通信链路带宽不均衡 | transport_type, avg/min_bandwidth_GBps |

### 使用示例

在 TRAE 对话中：

- "帮我分析一下 `/path/to/op_summary_0.csv` 的性能数据"
- "分析 `/path/to/profiling_output/` 目录下所有 profiling 数据"
- "分析 `/path/to/trace_view.json` 的算子耗时分布"
- "我想分析 PyTorch 训练的性能瓶颈，应该用什么工具？"
- "如何检测算子内存泄漏？"
- "我想调试 Ascend C 算子，推荐什么工具？"
- "列出所有昇腾开发工具"

## 添加新工具

## 知识库检索功能（Skills）

### Skills 知识库

Skills 模块提供昇腾工具专业知识的全文检索能力，支持 PDF、Word、Markdown、HTML 等多种格式的文档。

#### MCP 工具

| 工具名 | 说明 |
|--------|------|
| `query_skill_knowledge` | 查询昇腾工具专业知识库（支持 PDF/Word/Markdown/HTML 文档） |
| `rebuild_skill_index` | 重建知识库索引（可选强制全量重建） |

#### 高级检索选项

`query_skill_knowledge` 支持以下增强参数：

- `use_vector: bool` - 启用向量检索（语义相似度匹配），默认 `False`
- `use_rerank: bool` - 启用 Cross-Encoder 重排序（精细相关性评分），默认 `False`
- `top_k: int` - 返回结果数量，默认 `5`

**检索模式对比**：

- **基础模式**（默认）：BM25 + FTS5 混合检索，适合精确关键词匹配
- **向量模式**（`use_vector=True`）：BM25 + FTS5 + 向量嵌入，适合语义相似查询
- **重排序模式**（`use_rerank=True`）：三级检索 + Cross-Encoder 重排，精度最高但速度较慢

**推荐使用场景**：
- 查询具体工具命令、API 名称 → 基础模式即可
- 查询概念解释、操作流程 → 启用向量检索
- 复杂问题、多条件筛选 → 启用重排序

#### MCP 资源

| 资源 URI | 说明 |
|----------|------|
| `ascend://skills/status` | 知识库状态信息（文档数量、索引大小等） |

#### 工作原理

1. **文档解析**：自动提取 PDF/Word/MD/HTML 内容
2. **智能分块**：按语义段落切分为 500-1000 字的文本块
3. **向量化**（可选）：使用 BGE 模型生成文本嵌入（embedding）
4. **多级检索**：
  - 一级：SQLite FTS5 快速召回候选集
  - 二级：BM25 关键词打分
  - 三级：向量相似度计算（可选）
  - 四级：Cross-Encoder 重排序（可选）
5. **意图识别**：自动判断用户意图（工具推荐/操作指南/性能分析/通用问答）
6. **增量更新**：仅处理变更文件，大幅提升重建速度

#### 使用示例

在 TRAE 对话中：

- "如何配置 msprof 进行通信分析？"
- "NPU 算子开发的完整流程是什么？"
- "性能调优有哪些常用方法？"
- "查询知识库中关于 ACL 初始化的内容"

详细说明请参考 [Skills 使用指南](docs/SKILLS_USAGE.md)。

---

## 添加新工具

编辑 `knowledge/tools.json`，按以下格式添加：

```json
{
  "id": "tool_id",
  "name": "工具名称",
  "category": "分类",
  "summary": "一句话简介",
  "description": "详细说明",
  "use_cases": ["场景1", "场景2"],
  "keywords": ["关键词1", "关键词2"],
  "doc_url": "文档链接",
  "related_tools": ["相关工具ID"],
  "supported_products": ["支持的硬件型号"],
  "usage_example": "使用示例命令"
}
```

## 项目结构

```
ms-mcp/
├── server.py              # MCP Server 主程序（8 个 Tools + 2 个 Resources）
├── skills/                # Skills 知识库模块
│   ├── __init__.py        # 模块导出
│   ├── parser.py          # 文档解析器（PDF/Word/MD/HTML）
│   ├── indexer.py         # 索引构建与管理
│   ├── retriever.py       # 混合检索引擎（BM25 + FTS5）
│   └── router.py          # 意图识别与路由
├── analyzer.py            # Profiling 数据解析与事实标记引擎
├── knowledge/
│   └── tools.json         # 工具知识库（21 个工具，4 大分类）
├── test_data/             # 测试用 Profiling 数据（CSV）
├── tool_docs/             # 原始参考文档（PDF）
│   ├── CANN 9.0.0-beta1 性能调优工具用户指南
│   └── CANN 9.0.0-beta1 算子开发工具用户指南
├── examples/              # 使用示例
│   └── usage_example.py   # Skills 功能演示脚本
├── docs/                  # 文档
│   └── SKILLS_USAGE.md    # Skills 详细使用指南
├── pyproject.toml
└── README.md
```
