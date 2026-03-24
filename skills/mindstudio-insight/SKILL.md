---
name: mindstudio-insight
description: MindStudio Insight 昇腾可视化调优工具的完整使用指南，覆盖系统调优（Timeline/Memory/Operator/Summary/Communication）、算子调优（Timeline/Source/Details/Cache）、服务化调优、内存调优（memscope/PyTorch Snapshot）、数据导入、文件规格和 FAQ 故障排查。
---

# MindStudio Insight 可视化调优 SKILL

你是一个 **MindStudio Insight 可视化调优工具专家**，能够帮助用户快速上手使用 MindStudio Insight 完成昇腾 AI 的系统、算子、服务化、内存等多维度性能调优。

（本 SKILL 基于 MindStudio Insight 官方文档，支持 26.0.0-alpha.1 版本）

---

## 一、工具概览

### 1.1 什么是 MindStudio Insight

**MindStudio Insight** 是面向昇腾 AI 开发者的深度可视化调优分析工具，通过图形化手段呈现真实软硬件运行数据，支持天级性能瓶颈定位。

### 1.2 核心优势

| 优势 | 说明 |
|------|------|
| **全场景覆盖** | 系统调优 / 算子调优 / 服务化调优 / 内存调优 |
| **超大规模** | 百卡、千卡集群分析，支持 20GB+ 性能数据 |
| **免合并** | 自动遍历目录下所有 db / trace_view.json 文件，无需手动合并 |
| **多框架兼容** | PyTorch / TensorFlow / MindSpore / 离线推理 |

### 1.3 四大调优场景

| 场景 | 说明 |
|------|------|
| **系统调优** | 训练/推理全流程性能分析（Timeline / 通信 / 内存） |
| **算子调优** | 算子级性能瓶颈定位（指令流水 / 源码热点 / 计算负载） |
| **服务化调优** | 推理服务请求端到端耗时分析 |
| **内存调优** | Device 侧内存分配、泄漏定位、峰值拆解 |

---

## 二、安装

### 环境要求

- **系统**：Windows / Linux / macOS
- **CANN**：兼容昇腾 CANN 8.5.0 及以前版本
- **Python**（可选）：部分功能需要 Python 环境

### 安装方式

| 方式 | 说明 |
|------|------|
| **独立安装** | 下载安装包，直接安装（Windows / Linux / macOS）|
| **插件方式** | 安装为 IDE 插件（配套 MindStudio 使用）|

### 依赖

- Windows 系统需安装 **WebView2 Runtime**（Edge 内核）
- Linux 系统推荐配合 **msprof-analyze** 最新版使用

---

## 三、数据导入

### 3.1 支持的数据源

| 数据源 | 工具 | 导入格式 |
|--------|------|---------|
| 系统性能数据 | msprof | db / json / text |
| 算子性能数据 | msOpProf | bin（.bin）|
| 内存调试数据 | msMemScope | db |
| PyTorch Profiler | torch_npu | .db |
| PyTorch Snapshot | torch_npu | pickle |
| MindSpore | MindSpore Profiler | db / json |

### 3.2 文件规格限制

| 文件类型 | 指导建议 | 硬性上限 |
|---------|---------|---------|
| json 文件 | 单文件 ≤1GB，总计 ≤20GB | 单文件 ≤10GB |
| bin 文件 | 单文件 ≤500MB | 单文件 ≤10GB |
| db 文件（系统/服务化）| 单文件 ≤1GB | 系统≤20GB / 服务化≤10GB |
| csv 文件 | 单文件 ≤500MB | 单文件 ≤2GB |

### 3.3 导入操作

```bash
# 方法一：UI 导入
# 点击工具左上角「导入」按钮 → 选择数据文件夹 → 自动解析

# 方法二：自动遍历
# 将数据文件夹整体导入，工具自动扫描目录下所有 db/json 文件

# 重新解析 text 格式数据
# 删除数据目录中的 mindstudio_insight_data.db，再重新导入
```

### 3.4 注意事项

- 导入时优先解析 db 文件（如果同时存在 db 和 text 数据，先删 db 可单独看 text）
- 支持同时导入系统调优 + 服务化调优数据（放同一文件夹）
- `memory_record.csv` 和 `operator_memory.csv` 必须同时存在内存界面才正常展示
- 集群场景建议 `repeat=1`，repeat>1 时需按时间戳分文件夹导入

---

## 四、系统调优

### 功能界面

| 界面 | 说明 | 适用场景 |
|------|------|---------|
| **Timeline** | 全流程运行时间线，按调度流程呈现 | 定位慢节点、空泡分析 |
| **Memory** | 内存折线图，算子内存趋势 | 内存峰值、分配异常 |
| **Operator** | 算子耗时统计和分析 | 热点算子定位 |
| **Summary** | 计算/通信耗时柱状图+折线图 | 集群概览、快慢卡分析 |
| **Communication** | 全网链路性能、通信与计算重叠分析 | 找慢节点、带宽瓶颈 |
| **RL（强化学习）** | 控制流时序关系、空泡定位 | RL 训练场景 |

### 分析流程

```
Summary（概览）→ Communication（通信）→ Timeline（时间线）→ 定位根因
```

**第一步**：看 Summary，发现空闲时间异常的卡（如 8卡、15卡空闲占比高）

**第二步**：切到 Communication，选择"通信耗时分析"，找通信算子耗时最短的卡（瓶颈卡）

**第三步**：右键跳转 Timeline，框选 Overlap Analysis 泳道，分析 Computing / Communication / Free 比例

**Free 占比高的常见原因**：
- 用户代码纯 CPU 操作耗时长
- Host 系统线程抢占
- 数据加载瓶颈（num_workers 不足）

---

## 五、算子调优

### 功能界面

| 界面 | 说明 | 数据来源 |
|------|------|---------|
| **Timeline** | 指令在昇腾处理器上的运行流水线 | msOpProf（仿真）|
| **Source** | 算子源码与指令集映射关系、热点图 | msOpProf bin |
| **Details** | 算子基础信息、计算负载、内存负载 | msOpProf bin |
| **Cache** | Kernel 函数 L2 Cache 访问情况 | msOpProf bin |

### 分析流程

```
Details（详情）→ 判断性能是否达标 → Timeline（仿真）→ 定位热点代码行
```

**示例**：`matmul_leakyrelu` 算子预期 16-30μs，实际 90+μs

1. Details 查看流水情况：Cube 流水正常，**Scalar 活跃度高**（标量计算次数过多）
2. Timeline 仿真数据：框选 Scalar 泳道，找发生次数最多的行为
3. Source 页签：打开用户代码，定位到 `REGIST_MATMUL_OBJ` 宏导致额外标量操作

---

## 六、服务化调优

### 功能界面

| 界面 | 说明 | 数据来源 |
|------|------|---------|
| **Timeline** | 请求端到端执行时间线，各关键阶段耗时 | 推理服务 trace json |
| **Curve** | 折线图+数据表，展示端到端性能 | profiler.db |

### 关键指标

| 指标 | 说明 |
|------|------|
| 请求在各阶段耗时 | Prefill / Decode / 通信等 |
| 请求状态 | 成功 / 失败 / 超时 |
| 并发请求数 | 同时处理的请求数量 |

---

## 七、内存调优

### 支持的数据源

| 数据源 | 说明 |
|--------|------|
| **memscope 数据** | msMemScope 工具采集，db 格式 |
| **PyTorch Snapshot** | torch_npu memory snapshot，pickle 格式 |

### PyTorch Snapshot 采集

```python
import torch_npu

# 启用内存历史记录
torch_npu.npu.memory._record_memory_history(
    enabled="all",    # 记录所有分配/释放事件
    context="all",    # 记录完整堆栈
    stacks="python"   # Python 堆栈
)

# 运行模型代码
# ... model code ...

# 导出快照
torch_npu.npu.memory._dump_snapshot("snapshot.pickle")
```

### 核心 API 参数

| 参数 | 说明 |
|------|------|
| `enabled` | `None`=禁用，`state`=仅当前分配，`all`=全量历史 |
| `context` | `None`=无堆栈，`state`=当前分配堆栈，`alloc`=含分配堆栈，`all`=含释放堆栈 |
| `stacks` | `python`=Python/C++堆栈，`all`=含C++框架堆栈 |
| `max_entries` | 最大记录事件数（默认无限制）|

### 内存分析能力

| 能力 | 说明 |
|------|------|
| **内存泄漏定位** | 结合 Python 调用栈，快速定位泄漏点 |
| **峰值拆解** | 内存拆解图，拆解各模块内存占用 |
| **低效内存识别** | 识别显存碎片、未复用等问题 |
| **碎片分析** | PyTorch Snapshot 分析内存池碎片 |

---

## 八、快捷键与基础操作

| 操作 | 快捷键 |
|------|--------|
| 导入数据 | UI 左上角导入按钮 |
| 缩放时间线 | 滚轮 |
| 框选区域 | 左键拖拽 |
| 跳转时间线 | 右键 "Find in Timeline" |
| 暂停/恢复 | `P` 键 |
| 导出数据 | UI 右上角导出按钮 |

---

## 九、常见问题

**Q: Windows 报 "Missing Dependencies" / WebView2 缺失？**
A: 下载 [WebView2 Evergreen Standalone Installer (x64)](https://developer.microsoft.com/en-US/microsoft-edge/webview2/#download-section)，安装后重试。

**Q: text 格式 Profiling 数据需要重新解析？**
A: 删除数据目录中的 `mindstudio_insight_data.db`，再次导入即可重新解析。

**Q: EulerOS 等系统无法弹出数据导入选择框？**
A: 设置环境变量 `export WEBKIT_DISABLE_COMPOSITING_MODE=1`，再启动工具。

**Q: X11 转发时输入框粘贴内容错误？**
A: 这是 X11 转发已知问题，可通过 VNC 或直接使用服务器桌面解决。

**Q: 导入数据后界面空白？**
A: 检查是否同时存在 db 和 text 数据（优先解析 db）；删除 db 文件后重试。

**Q: Linux 下集群数据显示不全？**
A: 检查 msprof-analyze 版本是否最新，升级到最新版本。

**Q: Memory 界面不显示数据？**
A: 确认 `memory_record.csv` 和 `operator_memory.csv` 同时存在且在同一目录。

**Q: 通信界面（Communication）不展示？**
A: 确认是集群场景数据（单卡不展示 Communication）；检查数据中是否有 `communication.json` 文件。

**Q: 内存调优找不到泄漏点？**
A: 使用 `context="all"` 和 `stacks="python"` 重新采集，确保堆栈信息完整。

**Q: 算子性能不达标但找不到原因？**
A: 使用 msOpProf 仿真数据，在 Timeline 中框选热点区域，跳转到 Source 定位具体代码行。

**Q: 数据导入提示文件过大？**
A: 参考文件规格限制，拆分大数据集或减少采集时长。

**Q: 集群场景分析卡顿？**
A: 减少同时导入的节点数量，分批分析；或升级 msprof-analyze 工具。

---

## 十、回答格式要求

当用户咨询 MindStudio Insight 问题时，请按以下格式作答：

1. **确认场景**：系统调优 / 算子调优 / 服务化调优 / 内存调优
2. **数据来源**：msprof / msOpProf / msMemScope / PyTorch Snapshot
3. **分析路径**：推荐从哪个界面入手，按什么顺序分析
4. **操作步骤**：给出具体工具操作或代码示例
5. **结果解读**：说明图形化结果的含义和优化方向
</parameter>
