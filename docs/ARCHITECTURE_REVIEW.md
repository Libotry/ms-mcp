# ms-mcp 架构设计说明书（v1.4）

> 主导：宪宪（布偶猫）
> 审阅：所有猫咪
> 日期：2026-04-07
> 状态：草稿 → 征询意见中

---

## 一、需求分析

### 1.1 业务场景

ms-mcp 是一个**面向昇腾（Ascend）AI 处理器的开发者工具助手**，通过 MCP 协议接入 TRAE IDE，解答三类问题：

| 问题类型 | 用户意图 | 系统动作 |
|---------|---------|---------|
| **工具推荐** | "我想调试算子用什么工具？" | 关键词匹配 → 返回工具列表 |
| **领域方法论** | "如何用 msprof 做通信分析？" | SKILL 匹配 → 返回角色指令 + 方法论文档 |
| **操作指南** | "msprof 怎么配置参数？" | 知识库检索 → 返回 PDF/MD 文档片段 |
| **性能分析** | "帮我分析这个 CSV 文件" | 数据解析 → 返回结构化指标 + findings |

### 1.2 用户画像

- **主要用户**：昇腾开发者（训练/推理/算子开发）
- **交互方式**：TRAE IDE 对话 → MCP 工具调用 → 返回结构化结果
- **核心诉求**：减少工具选择成本，快速获得可操作的优化建议

### 1.3 非功能需求

- **离线优先**：MCP 不做网络请求，只读写本地文件
- **零依赖部署**：纯 Python，pip 安装即可
- **可解释性**：每个 findings 必须有 type + 数值 + 含义

---

## 二、当前架构分析

> ⚠️ **架构盲区修正（铲屎官 2026-04-07 澄清）：**
>
> `.trae/skills/` 和 `skills/` 是**两个独立的系统**，不是副本/symlink 关系：
>
> | 系统 | 路径 | 优先级 | 调用方式 | 能力强度 |
> |------|------|--------|---------|---------|
> | **TRAE 原生 Skill** | `.trae/skills/` | **高（IDE 原生）** | IDE 启动时自动读取，无需代码 | **强** |
> | **MCP Skill** | `skills/` | 低（MCP 中转） | 必须通过 MCP 工具调用 | **弱** |
>
> **关键洞察**：走 MCP 后 SKILL 能力比 TRAE 原生 SKILL 弱很多。因此：
> - `.trae/skills/` 是铲屎官**重点发力的方向**
> - `skills/` 的定位需要重新审视（见 §2.5 分工建议）
>
> 此前的 v2.0 草稿将两者视为"歧义"是错误的，现已更正。

### 2.1 整体结构

```
server.py (FastMCP)
├── 工具知识库 (tools.json)         → recommend_tool / list_all_tools / get_tool_detail
├── Skills 知识库                  → resolve_skill / list_skills / get_skill / get_skill_reference
│   ├── SkillManager               → 扫描 / 匹配 / 裁剪 / 角色指令
│   ├── parser.py                  → PDF / Word / MD / HTML 解析
│   ├── indexer.py                 → SQLite FTS5 索引
│   ├── retriever.py               → BM25 + FTS5 混合检索
│   └── router.py                  → 意图识别 (4 种类型)
├── 文档知识库                      → query_skill_knowledge / rebuild_skill_index
├── Profiling 分析 (analyzer.py)   → analyze_profiling / analyze_profiling_directory
│   └── 9 种文件格式 × 16 种 findings
├── 深度异常分析                    → analyze_profiling_anomaly (BubbleMetrics, StepAnalysis...)
└── MFU 计算                       → calculate_operator_mfu
```

### 2.2 优点

1. **分层清晰**：接入层（server.py）→ 服务层（各模块）→ 知识层（JSON/SQLite）→ 数据层（文件）
2. **Skills 技能系统设计优雅**：SKILL.md + 两阶段匹配 + 章节优先级裁剪，是真正的领域专家封装
3. **安全意识**：路径校验防止遍历攻击，多编码兼容
4. **懒加载**：BM25 索引、SkillManager、Retriever 都是懒加载
5. **职责边界明确**：MCP 不做网络请求，搜索/建议交给 TRAE LLM

### 2.3 问题清单（宪宪提纲）

| # | 严重度 | 领域 | 问题 | 根因 |
|---|--------|------|------|------|
| P1 | 🔴 高 | 工具注册 | `analyze_profiling_full` / `analyze_profiling_anomaly` 在 `__main__` 中注册，但 MCP Resource `ascend://tools/catalog` 只读 `tools.json`，两者脱节 | 动态注册与静态目录分离 |
| P2 | 🔴 高 | 工具注册 | `SKILL_TOOL_MAP` 中映射的工具名（如 `analyze_profiling_full`）从未在 server.py 中注册 | 工具注册分散在两处，无全局视图 |
| P3 | 🔴 高 | 返回类型 | 有的工具返回 `json.dumps()`，有的返回 Markdown 字符串，LLM 调用方无法统一处理 | 无统一的响应格式约定 |
| P4 | 🟡 中 | 代码重复 | CSV 解析逻辑在 `analyzer.py` 和 `skills/indexer.py` 各有一份 | 无共享的 IO 工具层 |
| P5 | 🟡 中 | Skills 结构 | `skills/` 和 `.trae/skills/` 两套并存，`.trae/` 是 symlink 还是独立副本未说明 | 多 IDE 协作场景未归档 |
| P6 | 🟡 中 | TypedDict 未验证 | `FindingItem` 等 TypedDict 仅做类型提示，无运行时校验 | 依赖 Python 类型注解但无 enforcement |
| P7 | 🟡 中 | 状态管理 | `_get_skill_manager` 用函数属性做单例，风格 Pythonic 但不显式 | 无显式生命周期管理 |
| P8 | 🟡 中 | 向量检索 | `vector_store.py` / `reranker.py` 存在但 README 说"不实现"，造成读者困惑 | 预留代码与实际功能不符 |
| P9 | 🟡 中 | Schema 演化 | `analyze_profiling` 返回的 findings 无 JSON Schema，LLM 只能靠猜 | 无机器可读的结果契约 |
| P10 | 🟢 低 | frontmatter | YAML frontmatter 解析用 regex，当描述含多行 `>` 折叠时有边界 case | 无 pyyaml 依赖但用简易解析 |
| P11 | 🟢 低 | docstring | 多处 docstring 是中文，server.py 的 instructions 是中文但 TRAE 界面可能显示英文 | 国际化未考虑 |

---

## 三、目标架构（v2.0）

### 3.0 TRAE 原生 Skill vs MCP Skill 职责分工（核心）

这是当前最需要澄清的架构问题。

**原则：TRAE 原生 Skill 擅长"说"，MCP Skill 擅长"做"。**

| 维度 | TRAE 原生 Skill (`.trae/skills/`) | MCP Skill (`skills/` via MCP) |
|------|-----------------------------------|-------------------------------|
| **核心能力** | 方法论文档读取、对话式引导、多轮推理 | 文件 IO、CSV/JSON 计算、结构化数据解析 |
| **调用方式** | IDE 自动读取，即时可用 | 需显式调用 MCP 工具，有延迟 |
| **适用场景** | 决策建议、流程说明、FAQ、工具选型 | 性能数据分析、大文件解析、数值计算 |
| **输出形式** | 文本（Markdown 对话） | 结构化 JSON / findings |
| **Token 消耗** | 低（原生上下文） | 高（MCP 往返开销） |

**建议的分工：**

```
用户提问
    │
    ├── "如何配置 msprof？" / "msdebug 怎么调试？"
    │       → TRAE 原生 Skill (.trae/skills/)
    │          直接回答方法论、步骤、FAQ
    │
    ├── "帮我分析这个 CSV" / "计算这个算子的 MFU"
    │       → MCP Skill (skills/ → MCP Tool)
    │          执行文件解析 + 数值计算 + 返回结构化结果
    │
    └── 组合场景：先 MCP 返回数据 → 再 TRAE 原生 Skill 解读
           e.g. MCP 分析完 CSV → TRAE Skill 基于结果给优化建议
```

**`skills/` 的重新定位（待铲屎官确认）：**

当前 `skills/` 里放的是 SKILL.md（方法论文档），这其实是"控制平面"的东西，
更适合放在 `.trae/skills/`。`skills/` 作为 MCP 模块，应该专注"数据平面"：

- `skills/` 下的 Python 代码（`analyzer.py`, `mfu_calculator.py` 等）→ 留在 MCP 层，做数据计算
- `skills/*/SKILL.md` 方法论文档 → 考虑迁移到 `.trae/skills/`，或明确为"离线参考"

### 3.1 核心原则

1. **MCP 工具注册表是唯一真相源** — 所有工具必须注册，不存在"动态注册但不在目录中"的情况
2. **响应格式统一** — 所有工具返回结构化 JSON，Markdown 只用于人工阅读友好的展示
3. **可发现性** — 新增工具/技能后，文档、Resource、Tool Map 必须同步更新
4. **零隐藏状态** — 所有服务层对象通过显式工厂创建，不依赖函数属性模拟单例

### 3.2 分层架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         TRAE IDE                                 │
│         用户提问 → LLM 决策 → MCP 调用 → 解析结果 → 展示            │
└─────────────────────────────────────────────────────────────────┘
                              │ MCP 协议
┌─────────────────────────────────────────────────────────────────┐
│  接入层：server.py                                                │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ ToolRegistry (统一工具注册中心)                              │ │
│  │ - register_tools() 扫描所有 tool_*.py 注册                   │ │
│  │ - get_tool_catalog() → ascend://tools/catalog                │ │
│  │ - 禁止在 __main__ 偷偷注册                                   │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│  服务层                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ ToolService  │  │ SkillService │  │ ProfilingService     │  │
│  │ (工具推荐)    │  │ (技能管理)    │  │ (数据分析)            │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ 共享基础层 (Shared Kernel)                               │   │
│  │ - io_utils: 统一 CSV/JSON 读取（多编码、路径校验）        │   │
│  │ - schema: findings JSON Schema 定义 + 验证               │   │
│  │ - response: 统一响应格式封装                              │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│  知识层                                                          │
│  knowledge/tools.json  ←→  ToolService (只读)                   │
│  knowledge/skills.db   ←→  SkillService (读写)                  │
│  skills/*/SKILL.md    ←→  SkillManager (只读)                  │
│  tool_docs/            ←→  Indexer (读写)                       │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 关键重构

#### 重构 1：统一工具注册中心

**当前问题**：工具注册分散在 `@mcp.tool()` 装饰器、动态 `register_*` 函数、`__main__` 条件调用三处。

**目标**：所有工具通过 `tools/` 子模块注册，server.py 启动时统一扫描注册。

```
tools/
├── __init__.py           # register_all(mcp) → 统一入口
├── tool_registry.py      # ToolCatalog 单例
├── recommend_tool.py      # 工具推荐
├── analyze_profiling.py  # Profiling 分析
├── analyze_anomaly.py    # 深度异常分析
└── mfu_calculator.py     # MFU 计算
```

`server.py` 只做：
1. `mcp = FastMCP("ms-mcp", ...)`
2. `register_all(mcp)` 一次性注册所有工具
3. `mcp.run()`

**Resource 动态生成**：catalog Resource 从 `ToolCatalog` 实时读取，保证 Tool 注册和 Resource 描述始终一致。

#### 重构 2：统一响应格式

**当前问题**：有的返回 `json.dumps(result)`，有的直接返回 Markdown。

**约定**：
- 所有工具返回 `json.dumps(...)`，格式统一为 `{"ok": bool, "data": ..., "error": str|null}`
- Markdown 渲染由 TRAE LLM 根据上下文决定
- `query_skill_knowledge` 和 `list_skills` 改为返回结构化 JSON + 明示 `output_format: "markdown"` 字段，供 LLM 决定是否渲染

#### 重构 3：Shared Kernel

```
shared/
├── io.py           # read_csv(), read_json(), validate_path()
├── schema.py       # FindingItem, OpInfo 的 JSON Schema + jsonschema 验证
└── response.py     # ApiResponse(data=..., warnings=[], meta={})
```

#### 重构 4：移除 `.trae/skills/` 歧义

`.trae/skills/` 应明确为 **symlink 指向 `skills/`**，或明确说明是 TRAE IDE 的独立副本。禁止两套并行。

---

## 四、各工具评价维度

| 工具/模块 | 成熟度 | 内聚 | 扩展性 | 可测试性 | 备注 |
|-----------|--------|------|--------|----------|------|
| `server.py` | 🟡 中 | 🟡 中 | 🟢 好 | 🟡 中 | 注册逻辑需重构 |
| `analyzer.py` | 🟢 高 | 🟢 高 | 🟢 好 | 🟢 高 | CSV 格式处理扎实，逻辑清晰 |
| `skills/skill_manager.py` | 🟢 高 | 🟢 高 | 🟢 好 | 🟡 中 | 两阶段匹配设计好，frontmatter 解析需加固 |
| `skills/indexer.py` | 🟢 高 | 🟢 高 | 🟢 好 | 🟡 中 | FTS5 + 增量更新设计好 |
| `skills/retriever.py` | 🟢 高 | 🟢 高 | 🟡 中 | 🟡 中 | BM25 + FTS5 混合检索扎实 |
| `skills/router.py` | 🟡 中 | 🟡 中 | 🟢 好 | 🟢 高 | 规则驱动，意图识别简单有效 |
| `skills/profiling_analyzer.py` | 🟢 高 | 🟢 高 | 🟡 中 | 🟡 中 | BubbleMetrics 等 dataclass 设计好，与 analyzer.py 有重叠 |
| `knowledge/tools.json` | 🟡 中 | 🟢 高 | 🟢 好 | 🟢 高 | JSON 结构良好，无版本控制 |
| `mfu_calculator_tool.py` | 🟢 高 | 🟢 高 | 🟢 好 | 🟢 高 | 独立工具，职责单一 |

---

## 五、待猫咪们确认的问题

> 每只猫咪可以针对以下问题给出立场：**同意 / 需讨论 / 反对 + 理由**

| # | 问题 | 选项 |
|---|------|------|
| Q1 | 工具注册分散在 `server.py` 和 `__main__` 两处，是否接受统一到 `tools/` 子模块？ | 同意 / 需讨论 / 反对 |
| Q2 | 所有 MCP 工具是否应统一返回 `{"ok", "data", "error"}` JSON 格式，放弃部分直接返回 Markdown？ | 同意 / 需讨论 / 反对 |
| Q3 | `.trae/skills/` 与 `skills/` 是否明确为 symlink，不再各自维护独立副本？ | 同意 / 需讨论 / 反对 |
| Q4 | `skills/profiling_analyzer.py`（气泡分析）与 `analyzer.py`（基础分析）是否应该合并或明确分层？ | 合并 / 分层 / 需讨论 |
| Q5 | 是否引入 `jsonschema` 依赖对 findings 做运行时验证？会增加依赖但提升可靠性 | 同意 / 需讨论 / 反对 |
| Q6 | `SKILL_TOOL_MAP` 中的映射工具是否需要与实际注册的 MCP 工具名严格一一对应？ | 同意 / 需讨论 / 反对 |

---

## 六、实施路线（初步）

**Phase 1（短期）**：消除歧义
- `.trae/skills/` 和 `skills/` 是两个独立系统，文档中明确标注
- 清理 `SKILL_TOOL_MAP` 中不存在的工具名
- 添加 `tools/` 子目录，逐步迁移 `__main__` 中的注册逻辑
- **Auto-Tuning Phase T1**：会话管理基础设施

**Phase 2（中期）**：架构加固
- 引入 Shared Kernel（`io.py`, `schema.py`, `response.py`）
- 统一响应格式
- `SkillManager` 单例改为显式依赖注入

**Phase 3（长期）**：能力增强
- JSON Schema 验证 findings
- `analyzer.py` 和 `profiling_analyzer.py` 合并为 `ProfilingService`
- 向量检索功能补全（如果需要）

---

## 八、Auto-Tuning Pipeline（自动性能调优流水线）

> 新增能力，2026-04-07 铲屎官提出愿景，宪宪主导设计

> ⚠️ **2026-04-07 最终架构决策（铲屎官确认）：**
>
> **完全放弃 MCP 层，使用纯 TRAE 原生 SKILL 实现端到端 Auto-Tuning。**
>
> **核心洞察**：`.trae/skills/` 是 TRAE IDE 启动时自动加载的上下文目录。SKILL.md 是方法论文档，TRAE LLM 读取后自主生成并执行 bash 命令。无需 MCP 中转，无协议开销，无目录隔离问题。
>
> | 组件 | 职责 |
> |------|------|
> | **SKILL.md** | 方法论 + 角色指令 + 执行逻辑（TRAE LLM 的行动指南） |
> | **辅助脚本**（`.sh/.py`） | 会话持久化、收敛判断、profiling 包装（在 TRAE bash 中调用） |
> | **会话目录**（`.t  ra/skills/tuning_sessions/`） | 状态持久化（config.yaml、history.json、iteration 数据） |
> | **TRAE LLM** | 执行引擎：读取 SKILL.md + 会话状态 → 自主生成并运行 bash 命令 → 写回会话目录 |

### 8.1 愿景（纯 TRAE 原生 SKILL）

```
用户："优化这个训练任务的性能"
    │
    ▼
┌──────────────────────────────────────────────────────────────────┐
│  🔵 Align（对齐）                                               │
│  对话确认优化目标（指标/目标值/约束）                            │
└──────────────────────────────────────────────────────────────────┘
    │
    ▼
    TRAE LLM 执行：bash scripts/start_session.sh
    → 创建 .trae/skills/tuning_sessions/session_{id}/
    → 写入 config.yaml（目标/指标/约束）
    │
    ▼
┌──────────────────────────────────────────────────────────────────┐
│  🟡 Discover（探索）× N 轮                                       │
│  TRAE LLM：读取 config.yaml → 自主决定 profiling 命令            │
│      → 执行 msprof-analyze（长时间 bash，TRAE 支持）             │
│      → 将数据写入 session_{id}/iteration_{i}/profiling/          │
│      → 调用 analyze_results.py → findings                       │
│      → 生成 N 条假设（含收益/风险/范围）                         │
└──────────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────────┐
│  🟢 Verify（验证）× N 轮                                         │
│  TRAE LLM：选择最高收益假设 → 生成代码 patch                      │
│  → 展示 dry-run diff → 用户批准                                  │
│  → 应用 patch → 重新 profiling → check_convergence.sh           │
│  → 对比基线，判断收敛                                            │
└──────────────────────────────────────────────────────────────────┘
    │
    ▼
最终报告：每轮迭代效果对比 + 推荐方案
```

**核心原则**：
- SKILL.md 是方法论文档 + 角色指令，TRAE LLM 是执行引擎
- TRAE LLM 通过 bash 调用辅助脚本（不依赖 MCP 工具）
- 会话目录在 `.trae/skills/` 树下，TRAE LLM 可以直接读写

### 8.2 用户决策确认

| 决策点 | 交互方式 | 内容 |
|--------|---------|------|
| **指标对齐** | 对话确认 | 用户选关注指标（MFU/迭代时间/通信重叠/内存等），设定目标值 |
| **假设选择** | 展示列表 | LLM 列出 N 个假设，每条附收益预期（🎯/📊/📉）+ 风险（🔴/🟡/🟢）+ 范围 |
| **代码改动** | dry-run diff | 每次改代码前展示 diff，用户明确批准 |
| **继续/终止** | 对话确认 | 每次迭代后可继续、终止、或调整方向 |

**假设格式示例**：
```
🎯 假设 1：启用 FlashAttention 融合
   收益预期：🎯高（MFU +8~12%）| 改动风险：🟢低 | 改动范围：单文件
   → 预期提升：MFU +8~12%

📊 假设 2：调整 batch_size 从 32→64
   收益预期：🎯高（MFU +15%）| 改动风险：🔴高 | 改动范围：单文件
   → 预期提升：MFU +15%（有 OOM 风险）
```

### 8.3 辅助脚本清单

> 所有脚本由 TRAE LLM 通过 bash 调用，位于 `.trae/skills/auto-tuning/scripts/`

| 脚本 | 职责 | 调用方式 |
|------|------|---------|
| `start_session.sh` | 创建会话目录 + 写入 config.yaml | `bash .trae/skills/auto-tuning/scripts/start_session.sh <goal>` |
| `run_profile.sh` | 框架检测 + 生成 profiling 命令 + 采集数据 | `bash .trae/skills/auto-tuning/scripts/run_profile.sh <session_id> <framework>` |
| `check_convergence.sh` | 对比基线和当前指标 + 判断收敛 | `bash .trae/skills/auto-tuning/scripts/check_convergence.sh <session_id>` |
| `apply_patch.sh` | 生成/应用/回滚代码 diff | `bash .trae/skills/auto-tuning/scripts/apply_patch.sh <session_id> <action>` |

> 分析由 `ascend-auto-profiling` SKILL 提供，Discover 阶段 TRAE LLM 加载该 SKILL 进行 profiling 数据分析。无需单独写分析脚本。

### 8.4 会话持久化设计

**双写策略：内存 + 文件，断连可恢复**

```
.trae/skills/                          # ← 必须在 TRAE Skill 目录树内
└── tuning_sessions/
    ├── sessions.json          # 索引：session_id → 磁盘目录
    └── session_{id}/
        ├── config.yaml        # 用户对齐的指标、目标、约束
        ├── history.json       # 所有迭代记录（追加写）
        ├── current_state.json # 当前状态（快照）
        ├── audit.log          # 审计日志（每操作追加一行 JSON）
        └── iteration_{i}/
            ├── baseline/       # 基线数据
            ├── profiling/      # 本次采集数据
            ├── analysis.json  # findings（analyzer.py 输出）
            ├── hypotheses.json # LLM 生成的假设
            ├── patch.diff     # 代码改动
            └── compare.json   # 与基线对比结果
```

**断连恢复流程**：
```
用户重连 → 读取 sessions.json → 找到最近的 session
    │
    ├── 如果 current_state.json 有未完成的迭代 → 展示状态卡片，询问是否继续
    ├── 如果收敛完成 → 返回最终报告
    └── 如果用户放弃 → 标记会话为 abandoned
```

### 8.5 收敛判断逻辑

> 由 `scripts/check_convergence.sh` 调用 `scripts/convergence.py` 实现

```python
def judge_convergence(baseline, current, thresholds):
    """
    baseline: dict  当前迭代前的指标
    current:  dict  当前迭代后的指标
    thresholds: dict  e.g. {"mfu": 0.1}  提升 10%

    返回: ConvergenceResult
    """
    common_keys = set(baseline.keys()) & set(current.keys())  # ⚠️ 必须显式匹配，不用 zip
    improvements = {}
    regressions = {}

    for metric in common_keys:
        b_val = baseline[metric]
        c_val = current[metric]
        if b_val == 0:
            continue
        delta_pct = (c_val - b_val) / b_val * 100
        improvements[metric] = delta_pct
        if metric in thresholds:
            if delta_pct < 0:
                regressions[metric] = delta_pct

    if regressions:
        return ConvergenceResult(
            converged=True, reason="⚠️ regression",
            recommendations=["检测到性能回退，建议回滚"]
        )
    elif all(i >= thresholds.get(m, 0) for m, i in improvements.items()):
        return ConvergenceResult(
            converged=True, reason="🎉 target_achieved",
            recommendations=["目标达成，停止迭代"]
        )
    else:
        return ConvergenceResult(
            converged=False, reason="⏳ no_improvement",
            recommendations=["未达标，继续下一轮"]
        )
```

### 8.6 TRAE LLM 执行模型

**TRAE LLM 如何执行 Auto-Tuning？**

TRAE LLM 读取 `.trae/skills/auto-tuning/SKILL.md` 后，以 bash 命令形式执行：

```
# Align 阶段：启动会话
$ bash .trae/skills/auto-tuning/scripts/start_session.sh "优化MFU至65%"

# Discover 阶段：执行 profiling
$ bash .trae/skills/auto-tuning/scripts/run_profile.sh sess_001 pytorch

# 分析结果
$ python .trae/skills/auto-tuning/scripts/analyze_results.py \
    .trae/skills/tuning_sessions/sess_001/iteration_0/profiling/

# Verify 阶段：收敛判断
$ bash .trae/skills/auto-tuning/scripts/check_convergence.sh sess_001

# 应用 patch
$ bash .trae/skills/auto-tuning/scripts/apply_patch.sh sess_001 dry-run
$ bash .trae/skills/auto-tuning/scripts/apply_patch.sh sess_001 apply
```

**每个迭代的完整流程**：

```
TRAE LLM 读取 config.yaml（目标/指标/约束）
    │
    ├── 决策：跑什么 profiling 命令？（基于 SKILL.md 方法论 + 框架检测）
    ├── 执行：bash run_profile.sh（长时间命令，TRAE 支持）
    ├── 解析：python analyze_results.py（调用已有 analyzer.py）
    ├── 合成：基于 findings 生成 N 条假设（收益/风险/范围）
    ├── 展示：假设列表供用户选择
    ├── 生成：代码 patch（基于用户选择的假设）
    ├── 展示：dry-run diff 供用户确认
    ├── 应用：bash apply_patch.sh（用户批准后）
    ├── 判断：bash check_convergence.sh（对比基线）
    └── 决策：继续迭代 / 终止 / 调整方向
```

**关键约束**：TRAE LLM 在多轮对话中天然保持对会话目标的追踪（铲屎官确认可行）。无需额外状态管理。

```python
@dataclass
class ConvergenceResult:
    converged: bool
    reason: str           # "mfu_improved" / "no_improvement" / "regression"
    metric_delta: dict    # {metric: (before, after, delta_pct)}
    iteration: int
    recommendations: list[str]

def judge_convergence(baseline, current, thresholds):
    common_keys = set(baseline.keys()) & set(current.keys())
    improvements, regressions = {}, {}
    for metric in common_keys:
        b_val, c_val = baseline[metric], current[metric]
        if b_val == 0: continue
        delta_pct = (c_val - b_val) / b_val * 100
        improvements[metric] = delta_pct
        if metric in thresholds and delta_pct < 0:
            regressions[metric] = delta_pct
    if regressions:
        return ConvergenceResult(converged=True, reason="⚠️ regression",
            recommendations=["检测到性能回退，建议回滚"])
    elif all(i >= thresholds.get(m, 0) for m, i in improvements.items()):
        return ConvergenceResult(converged=True, reason="🎉 target_achieved",
            recommendations=["目标达成，停止迭代"])
    else:
        return ConvergenceResult(converged=False, reason="⏳ no_improvement",
            recommendations=["未达标，继续下一轮"])
```

### 8.7 与现有系统的关系

```
Auto-Tuning Pipeline（纯 TRAE SKILL，无 MCP）
    │
    ├── TRAE IDE 上下文：
    │   └── .trae/skills/auto-tuning/SKILL.md（新增）→ 方法论 + 执行逻辑
    │
    ├── 辅助脚本（新增）：
    │   └── .trae/skills/auto-tuning/scripts/
    │       ├── start_session.sh
    │       ├── run_profile.sh
    │       ├── analyze_results.py   # 调用 analyzer.py
    │       ├── check_convergence.sh
    │       └── apply_patch.sh
    │
    ├── 已有复用：
    │   ├── analyzer.py（已有）→ CSV/JSON/DB 解析
    │   └── SKILL.md（已有）→ 场景识别 + 工具推荐
    │
    └── 会话持久化：
        └── .trae/skills/tuning_sessions/session_{id}/
```

### 8.8 目录结构（v1.4 新增后）

```
ms-mcp/
├── analyzer.py              # 已有，复用
├── skills/                  # 已有（方法论文档 + MCP 工具）
│   └── ...（现有 SKILL 保持不变）
├── .trae/skills/
│   ├── auto-tuning/        # 新增（纯 TRAE SKILL）
│   │   ├── SKILL.md        # 核心：方法论 + 执行逻辑
│   │   └── scripts/
│   │       ├── start_session.sh
│   │       ├── run_profile.sh
│   │       ├── analyze_results.py
│   │       ├── check_convergence.sh
│   │       ├── convergence.py
│   │       └── apply_patch.sh
│   ├── tuning_sessions/    # 会话持久化（TRAE LLM 可直接读写）
│   │   ├── sessions.json
│   │   └── session_{id}/
│   │       ├── config.yaml
│   │       ├── history.json
│   │       ├── current_state.json
│   │       └── iteration_{i}/
│   │           ├── baseline/
│   │           ├── profiling/
│   │           ├── analysis.json
│   │           ├── hypotheses.json
│   │           ├── patch.diff
│   │           └── compare.json
│   └── ...（现有 SKILL 保持不变）
└── docs/
    └── ARCHITECTURE_REVIEW.md
```

### 8.9 实施路线（纯 TRAE SKILL 版）

> 完全去掉 MCP 层，核心产物是 `.trae/skills/auto-tuning/SKILL.md`

**Phase T1（最优先）**：SKILL.md 核心 + 会话基础设施
- `.trae/skills/auto-tuning/SKILL.md`：定义完整的三阶段工作流
- `scripts/start_session.sh`：创建会话目录 + 写 config.yaml
- `scripts/convergence.py`：收敛判断逻辑
- Rollback 机制：`apply_patch.sh` 在 patch.diff 旁存 git commit hash

**Phase T2**：Profiling 自动化
- `scripts/run_profile.sh`：框架检测 + profiling 命令生成
- `scripts/analyze_results.py`：封装 analyzer.py 调用

**Phase T3**：迭代闭环
- `scripts/check_convergence.sh`：基线对比 + 收敛判断
- `scripts/apply_patch.sh`：diff 应用 + dry-run + rollback

**UX 设计（gemini25 意见落地）**：
- 阶段视觉代号：🔵 Align → 🟡 Discover → 🟢 Verify
- 状态返回第一行：当前阶段 + 进度摘要
- 假设元信息：每条假设附收益预期（🎯高/📊中/📉低）+ 改动风险 + 改动范围
- `ConvergenceResult` 使用 emoji 翻译（🎉/⚠️/⏳）

### 8.10 Review 意见闭环（sonnet + gemini25 + dare + opus 独立审查）

> 2026-04-07 review → 2026-04-07 最终架构确认
> 参与：sonnet（快速灵活）| gemini25（体验）| dare（零信任/审计）| opus（架构）

#### 一、已处置的问题

| 状态 | 来源 | 问题 | 处置 |
|------|------|------|------|
| ✅ 已处置 | opus | `judge_convergence` zip bug | §8.5 中已修复为显式 key 匹配 |
| ✅ 已处置 | opus | MCP 层多余 | 完全去掉，改用纯 TRAE SKILL（铲屎官确认）|
| ✅ 已处置 | opus | rollback 缺失 | `apply_patch.sh` 旁存 git commit hash |
| ✅ 已处置 | opus | profiling 长时间运行 | TRAE 支持，SKILL.md 指导 LLM 执行 |
| ✅ 已处置 | gemini25 | 阶段无视觉锚点 | SKILL.md 中定义 🔵🟡🟢 代号 |
| ✅ 已处置 | gemini25 | 单一 Skill 人格 | `.trae/skills/auto-tuning/SKILL.md` 即为调优助手人格 |

#### 二、新发现的问题（待处置）

| # | 严重度 | 来源 | 问题 | 建议处置 |
|---|--------|------|------|---------|
| **P1** | 🔴 阻塞 | opus | `run_profile.sh` 只打印 Python 模板代码，不执行任何实际 profiling 命令。Discover 阶段的数据采集完全依赖用户手动，SKILL 价值从"自动采集"退化为"告诉你怎么写代码" | SKILL.md 应指导 TRAE LLM 根据框架（PyTorch/MindSpore）自动生成并执行 profiling 命令 |
| **P2** | 🔴 阻塞 | opus | `analyze_results.py` 用 `Path(__file__).parent.parent.parent` 定位 `analyzer.py`。TRAE bash 中工作目录不确定，analyzer.py 可能找不到 | 改用环境变量 `ANALYZER_PATH` 或绝对路径，使脚本在任意工作目录下可用 |
| **P3** | 🟡 中 | opus | `history.json` 从未被任何脚本写入。迭代记录全靠 LLM 记忆，断连后历史无法重建 | `convergence.py` 或 `check_convergence.sh` 每次收敛判断后应自动追加到 `history.json` |
| **P4** | 🟡 中 | opus | `apply_patch.sh rollback` 用 `git checkout "$HASH" -- .` 会丢弃**所有**未暂存改动，不只是 patch.diff 涉及的改动 | 改用更精确的 git 操作，或只 checkout patch.diff 涉及的文件 |
| **P5** | 🟡 中 | sonnet | Phase T1 起点描述有误。Align 阶段是对话而非工具，不应算作"会话基础设施"的 T1 起点 | §8.9 应明确 T1 起点是 `start_tuning_session` + `convergence.py` |
| **P6** | 🟡 中 | dare | 脚本缺少零信任校验：无输入验证（session_id 格式/路径遍历）、无幂等性保证（重复执行 start_session 会覆盖旧会话） | 所有脚本应对输入参数做格式校验；幂等性操作（如 session 已存在时）应报错而非静默覆盖 |
| **P7** | 🟡 中 | dare | 审计追踪不足：脚本执行结果（profiling 成功/失败、patch 应用结果）未写入 audit log | 建议增加 `.trae/skills/tuning_sessions/session_{id}/audit.jsonl`，每次操作追加一行结构化审计记录 |
| **P8** | 🟢 低 | sonnet | 8 个 MCP 工具（已废弃 MCP 层）的设计残留到辅助脚本粒度问题。实际 6 个脚本数量合理，但 `run_profile.sh` 目前是空壳导致粒度失真 | 等 P1 处置后重新评估粒度 |
| **P9** | 🟢 低 | sonnet | `start_session.sh` 对 `jq` 的 fallback 逻辑混乱（无 jq 时 sessions.json 格式会变成非标准 JSON 数组混入对象） | 统一使用 jq，Windows 环境提供 jq 路径检测或内置 fallback 生成标准 JSON |

### 8.11 断连恢复用户引导（gemini25 UX4）

```
👋 检测到未完成的调优会话
目标：MFU 提升 10%
当前：第 3 轮 / 共 N 轮
最近发现：通信重叠度偏低（32%）

[继续调优 🔵]  [查看详情]  [终止会话]
```

#### 收敛判断翻译层（gemini25 UX3）

| 程序 reason | 用户可见文案 |
|-------------|-------------|
| `mfu_improved` | MFU 提升达标 🎉 |
| `no_improvement` | 本次优化未带来改善，继续探索中 |
| `regression` | ⚠️ 检测到性能回退，建议回滚 |

**注意**：dataclass 内部用语义字符串（`"target_achieved"` / `"regression"` / `"no_improvement"`），emoji 只在 UI 展示层翻译。这样 `ConvergenceResult` 结构干净，程序和用户各取所需。

### 8.12 第二轮 Review 意见（sonnet + gemini25 + dare · 补充）

> 来源：多猫咪对 §八 第一版的独立审阅 + 铲屎官架构决策

#### 一、本轮已处置的问题

| 状态 | 来源 | 问题 | 处置 |
|------|------|------|------|
| ✅ 已处置 | 铲屎官 | P2：`analyze_results.py` 路径不可达 | **复用 `ascend-auto-profiling` SKILL 做分析，删除该脚本** |
| ✅ 已处置 | gemini25 | §8.2 假设格式缺少示例 | §8.2 补充假设格式示例（🎯/📊/🔴/🟡/🟢） |
| ✅ 已处置 | gemini25 | 迭代次数无上限 | SKILL.md §二 明确 `max_iterations: 5` 硬上限 |
| ✅ 已处置 | gemini25 | framework 参数有效值未文档化 | SKILL.md §三 Step 2 补充支持框架列表 |

#### 二、本轮新发现的问题（待处置）

| # | 严重度 | 来源 | 问题 | 建议处置 |
|---|--------|------|------|---------|
| **P10** | 🟡 中 | sonnet | `analyzer.py` 在 TRAE bash 中 import 路径不可达。`analyze_results.py` 删除后，Discover 阶段 LLM 调用 `analyzer.py` 时，`sys.path` 不包含 ms-mcp 根目录 | SKILL.md 应指导 LLM 通过绝对路径调用：`python /path/to/ms-mcp/analyzer.py <data>` |
| **P11** | 🟡 中 | sonnet | 框架检测逻辑未定义。`run_profile.sh` 说"检测框架"，但实际只打印模板，真实检测靠 LLM 自行判断，不确定性高 | 实现 `detect_framework.py` 脚本，读取训练脚本的 import 语句判断框架类型 |
| **P12** | 🟡 中 | dare | `session_id` 用时间+PID 生成，同一秒内并发调用会生成重复 ID，导致会话覆盖 | 改用 UUID 或在 session 已存在时报错而非静默覆盖 |
| **P13** | 🟡 中 | sonnet | `config.yaml` 字段结构未在 §八 定义。阈值来源（`parse_thresholds_from_config`）只解析 `MFU:65%` 格式，兼容性差 | 定义标准 config.yaml schema，明确字段名和格式 |
| **P14** | 🟡 中 | sonnet | `apply_patch.sh rollback` 用 `git checkout -- .` 会清除**所有**未提交改动 | 改用 `git stash` 或只 checkout patch.diff 涉及的文件 |
| **P15** | 🟡 中 | dare | `start_session.sh` 的 goals 参数无校验。特殊字符（引号/换行）会破坏 YAML/JSON 格式 | 增加输入校验：拒绝换行符、限制长度（≤2048）、转义特殊字符 |
| **P16** | 🟡 中 | dare | `parse_thresholds_from_config` 静默失败。当配置格式不对时返回空 `thresholds`，导致 `judge_convergence` 的 `all()` 在空字典上永远为 True，误判为"已达标" | 空阈值时应显式报错，而非静默退化 |
| **P17** | 🟢 低 | dare | `iteration` 目录与 `current_state.json` 可能不一致。用户手动创建目录时状态文件不会同步 | 增加一致性校验，不一致时报错 |
| **P18** | 🟢 低 | dare | `BASH_SOURCE[0]` 在非标准 bash 调用时可能失效（如 `sh script.sh`） | 改用 `realpath` 或在脚本开头设置绝对路径基准 |

#### 三、设计决策确认

> 以下决策已由铲屎官确认，记录在此防止回退

| 决策 | 内容 |
|------|------|
| **分析层复用** | Discover 阶段分析 profiling 数据，复用 `ascend-auto-profiling` SKILL，不另写脚本 |
| **迭代硬上限** | `max_iterations: 5`，防止无限循环 |
| **收敛翻译** | dataclass 用语义值（`target_achieved`），UI 层翻译为 emoji |
| **Audit 日志** | 每次操作追加一行 JSON 到 `audit.log`（dare 零信任要求） |

---

## 七、附录

### A. 当前目录结构（含 .trae 歧义）

```
ms-mcp/
├── server.py                          # 接入层（混合职责：接入 + 部分业务）
├── analyzer.py                        # Profiling 分析 v1
├── skills/
│   ├── skill_manager.py               # 技能管理器
│   ├── indexer.py                     # FTS5 索引
│   ├── retriever.py                   # BM25 + FTS5 检索
│   ├── parser.py                      # 文档解析
│   ├── router.py                      # 意图识别
│   ├── profiling_analyzer.py          # Profiling 分析 v2（气泡级）
│   ├── profiling_anomaly_tool.py       # 注册 analyze_profiling_anomaly
│   ├── profiling_full_tool.py          # 注册 analyze_profiling_full
│   ├── mfu_calculator_tool.py         # 注册 MFU 工具
│   ├── vector_store.py                 # 预留（未使用）
│   ├── reranker.py                    # 预留（未使用）
│   ├── calc_mfu/calculator.py          # MFU 计算核心
│   ├── ascend-profiling-anomaly/      # 技能 + 气泡分析脚本
│   ├── ascend-profiler-db-explorer/   # 技能
│   ├── cluster-fast-slow-rank-detector/ # 技能
│   ├── mindstudio_profiler_data_check/ # 技能
│   ├── calc-mfu/                       # 技能
│   ├── msdebug/                        # 技能
│   ├── msmodeling/                     # 技能
│   ├── msmonitor/                      # 技能
│   ├── msopprof/                       # 技能
│   ├── msprof-analyze/                 # 技能
│   ├── mssanitizer/                    # 技能
│   └── [其他技能]/                     # 共 19 个
├── .trae/skills/                       # TRAE IDE 原生 Skill（高优先级，铲屎官重点发力方向）
├── knowledge/
│   ├── tools.json                     # 21 个工具元信息
│   └── skills.db                      # 文档索引
├── tool_docs/                          # PDF/MD 参考文档
└── docs/
    └── ARCHITECTURE.md                # 当前架构文档（v1）
```

### B. 发现类型与 JSON Schema（建议）

```json
{
  "type": "object",
  "properties": {
    "type": { "type": "string", "enum": ["dominant_op", "high_ai_cpu_ratio", ...] },
    "op_name": { "type": "string" },
    "ratio_pct": { "type": "number" },
    ...
  },
  "required": ["type"]
}
```
