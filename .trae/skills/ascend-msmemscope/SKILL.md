---
name: ascend-msmemscope
description: 昇腾 NPU 内存分析调优工具 msMemScope（MindStudio MemScope）的完整使用指南，涵盖内存采集、内存泄漏分析、内存对比、内存块监测、内存拆解、低效内存识别五大功能，支持 Python 接口和命令行两种使用方式。
---

# Ascend msMemScope 内存分析调优 Skill

你是一个 **昇腾 NPU 内存分析调优专家**，熟练掌握 msMemScope（MindStudio MemScope）工具，能够根据用户描述的内存问题场景，推荐最合适的采集和分析方式，输出结构化的内存瓶颈分析结果。

（本回答基于 ascend-msmemscope Skill 的 msMemScope 使用规范）

---

## 一、工具概述

### 1.1 什么是 msMemScope

**msMemScope**（MindStudio MemScope）是基于昇腾硬件的**内存调试调优工具**，用于模型训练与推理过程中的内存问题定位，提供五大核心功能：

| 功能 | 说明 |
|------|------|
| 内存泄漏分析 | 检测内存长时间未释放、泄漏定位 |
| 内存对比分析 | 对比两个 Step 的内存使用差异 |
| 内存块监测 | 在算子执行前后监测指定内存块 |
| 内存拆解 | 拆解权重/梯度/激活值/优化器的内存占用 |
| 低效内存识别 | 识别过早申请、过迟释放、临时闲置的内存 |

### 1.2 兼容性

| 产品 | 版本要求 |
|------|---------|
| CANN | 8.2.RC1 及之后版本的 ATB 算子 |
| Ascend Extension for PyTorch | 7.0.0 及之后版本 |
| MindSpore | 2.7.0 及之后版本 |
| Aten 算子 | PyTorch 2.3.1 或更高版本 |

---

## 二、采集方式

### 2.1 快速决策树

```
用户场景
 │
 ├── Python 脚本训练/推理
 │       ├── 推荐：Python 接口采集（精准、可控）
 │       └── 命令行方式（备选）
 │
 ├── 非 Python 场景（C++ 应用等）
 │       └── 命令行采集
 │
 └── 需要标记代码范围（Step 开始/结束）
          └── mstx 打点 + 采集
```

### 2.2 Python 接口采集（推荐）

**环境准备**

```bash
# 1. 设置 CANN 环境
source <cann-path>/Ascend/cann/set_env.sh

# 2. 设置 msMemScope 环境
source <msmemscope-path>/msmemscope/set_env.sh

# 3. 设置 LD_PRELOAD 和 LD_LIBRARY_PATH（Python 接口必须）
export LD_LIBRARY_PATH=${msMemScope_DIR}/lib64:${LD_LIBRARY_PATH}
export LD_PRELOAD=${msMemScope_DIR}/lib64/libleaks_ascend_hal_hook.so:\
${msMemScope_DIR}/lib64/libascend_mstx_hook.so:\
${msMemScope_DIR}/lib64/libascend_kernel_hook.so:\
${msMemScope_DIR}/lib64/libatb_abi_0_hook.so:\
${msMemScope_DIR}/lib64/libatb_abi_1_hook.so
```

**四步 API 使用模式**

```python
import msmemscope

# Step 1: 配置参数
msmemscope.config(
    events="alloc,free,launch",   # 采集事件
    level="op",                    # op 或 kernel 粒度
    call_stack="c:10,python:5",  # 调用栈深度
    analysis="leaks,decompose",   # 分析类型
    output="./output",
    data_format="csv"             # csv 或 db
)

# Step 2: 开始采集
msmemscope.start()

# Step 3: 用户代码
for i in range(10):
    train()
    msmemscope.step()  # 可选，固化 Step 信息

# Step 4: 结束采集
msmemscope.stop()
```

**config 参数详解**

| 参数 | 可选值 | 默认值 | 说明 |
|------|--------|--------|------|
| `events` | `alloc`/`free`/`launch`/`access`/`traceback` | `alloc,free,launch` | 内存事件类型 |
| `level` | `0`(op) / `1`(kernel) | `0` | 采集粒度 |
| `call_stack` | `python:N` / `c:N` | `c:50` | 调用栈深度 |
| `analysis` | `leaks`/`inefficient`/`decompose` | `leaks` | 分析功能 |
| `data_format` | `csv` / `db` | `csv` | 输出格式 |
| `output` | 路径 | `memscopeDumpResults` | 输出目录 |
| `device` | `npu` / `npu:id` | `npu` | 设备 |
| `watch` | `start:op,end:op,full-content` | - | 内存块监测 |

### 2.3 命令行采集

```bash
msmemscope [options] bash user.sh
```

**常用参数**

| 参数 | 说明 |
|------|------|
| `--events=alloc,free,launch,access` | 采集事件 |
| `--level=0` | op 粒度（`1`=kernel） |
| `--call-stack=python,c` | 调用栈 |
| `--analysis=leaks,decompose,inefficient` | 分析功能 |
| `--data-format=csv` | 输出格式 |
| `--output=/path/to/output` | 输出路径 |
| `--steps=1,2,3` | 采集特定 Step |
| `--device=npu:0,npu:1` | 指定设备 |
| `--watch=op0,op1,full-content` | 内存块监测 |

### 2.4 mstx 打点采集

在 Step 开始和结束处标记，配合 msMemScope 使用：

**Python 脚本**
```python
import mstx

id = mstx.range_start("step start", None)
train()
mstx.range_end(id)
```

**C 脚本**
```cpp
#include "mstx/ms_tools_ext.h"
uint64_t id = mstxRangeStartA("step start", nullptr);
train();
mstxRangeEnd(id);
```

---

## 三、内存分析功能详解

### 3.1 内存泄漏分析

**使用场景**：内存长时间未释放、疑似泄漏

**在线方式**
```bash
msmemscope user_script.py
```
输出示例（存在泄漏）：
```
Memory Leak Detected:
- Step 数: 5
- 泄漏地址: 0x7f...
- 泄漏大小: 128 MB
- 关联 kernel: MatMul_v2
```

**离线方式**（推荐，精准定位）
```python
import msmemscope

# Step 1: 用 mstx 标记泄漏检测范围（A-B 之间）
# Step 2: 采集数据
msmemscope.config(events="alloc,free", data_format="csv")
msmemscope.start()
# ... 执行被测代码 ...
msmemscope.stop()

# Step 3: 离线分析
msmemscope.check_leaks(
    input_path="/path/to/memscope.csv",
    mstx_info="step start",
    start_index=0
)
```

### 3.2 内存对比分析

**使用场景**：两个 Step 内存使用存在差异，可能导致 OOM

**步骤**
1. 关闭 task_queue 优化：`export TASK_QUEUE_ENABLE=0`
2. 在代码中添加 mstx 打点
3. 分别采集两个不同 Step 的数据
4. 执行对比

```bash
# 采集 Step 1
msmemscope --steps=1 --level=kernel user_script.py

# 采集 Step 2
msmemscope --steps=2 --level=kernel user_script.py

# 对比分析
msmemscope --compare --input=/path/step1,/path/step2 --level=kernel
```

**输出**：`memory_compare_{timestamp}.csv`，包含基线数据、对比数据、差异值。

### 3.3 内存块监测

**使用场景**：定位算子间内存踩踏（模型场景）

**环境要求**：`export ASCEND_LAUNCH_BLOCKING=1`

**命令行方式**
```bash
msmemscope user_script.py --watch=start:op0,end:op1,full-content
```

**Python 接口方式**
```python
import torch
import msmemscope

torch.npu.synchronize()
test_tensor = torch.randn(2, 3).npu()

# 方式一：直接传入 Tensor
msmemscope.watcher.watch(test_tensor, name="test_tensor", dump_nums=2)

# 执行被监测代码
output = model(test_tensor)

torch.npu.synchronize()
msmemscope.watcher.remove(test_tensor)
```

**参数说明**

| 参数 | 说明 |
|------|------|
| `name` | 必选，标识 Tensor |
| `dump_nums` | 可选，dump 次数 |
| `test_tensor.data_ptr()` | 内存地址（方式二） |
| `length` | 内存块长度（方式二） |

### 3.4 内存拆解

**使用场景**：了解模型各组件（权重/梯度/激活值/优化器）的内存占用

**三种使用方式**

```python
import msmemscope.describe as describe

# 方式一：装饰器（函数内所有内存打上标签）
@describe.describer(owner="weight")
def load_weights():
    pass

# 方式二：with 语句（代码块打标签）
with describe.describer(owner="optimizer"):
    optimizer.step()

# 方式三：标记具体 Tensor
t = torch.randn(10, 10).npu()
describe.describer(t, owner="activation")
```

**一键分析（vLLM / FSDP / verl）**
```python
import msmemscope

msmemscope.config(events="alloc,free", data_format="db", analysis="decompose")
msmemscope.cleanup_framework_hooks()
msmemscope.init_framework_hooks("vllm_ascend", "11.0", "worker", "decompose")
msmemscope.start()
# ... vLLM 推理代码 ...
msmemscope.stop()
```

### 3.5 低效内存识别

**使用场景**：识别内存申请后未立即使用、使用后未及时释放的低效行为

**三种低效类型**

| 类型 | 说明 |
|------|------|
| `early_allocation` | 过早申请（申请到首次使用之间有其他算子释放内存） |
| `late_deallocation` | 过迟释放（最后一次使用到释放之间有其他算子申请内存） |
| `temporary_idleness` | 临时闲置（两次访问之间存在大量无关算子） |

**使用方式**

```bash
msmemscope user_script.py --analysis=inefficient
```

**离线自定义分析**
```python
import msmemscope

msmemscope.check_inefficient(
    input_path="/path/to/memscope.csv",
    mem_size=0,           # 低于此阈值的内存块不输出
    inefficient_type=["early_allocation", "late_deallocation", "temporary_idleness"],
    idle_threshold=3000   # 临时闲置的算子数量阈值
)
```

---

## 四、Python Trace 采集

**使用场景**：关联内存事件与 Python 代码全链路

```python
import msmemscope

# 默认采集
msmemscope.tracer.start()
train()
msmemscope.tracer.stop()

# 自定义采集（上下文模式）
with msmemscope.RecordFunction("forward_pass"):
    output = model(input_data)

# 自定义采集（装饰器模式）
@msmemscope.RecordFunction("forward_pass")
def forward_pass(data):
    return model(data)
```

**输出文件**：`python_trace_{TID}_{timestamp}.csv`

---

## 五、内存快照采集

**使用场景**：快速获取设备总空闲内存、torch 框架内存使用情况

```python
import msmemscope

# 采集一次快照
msmemscope.take_snapshot(device_mask=0)

# 指定多个设备
msmemscope.take_snapshot(device_mask=[0, 1])

# 自定义名称
msmemscope.take_snapshot(name="after_forward")
```

**注意**：`take_snapshot()` 可独立使用，不依赖 `start()/stop()`

---

## 六、输出文件说明

### 6.1 CSV 文件（memscope_dump_{timestamp}.csv）

| 字段 | 说明 |
|------|------|
| `ID` | 事件 ID |
| `Event` | 事件类型：SYSTEM / MALLOC / FREE / ACCESS / OP_LAUNCH / KERNEL_LAUNCH / MSTX / SNAPSHOT |
| `Event Type` | 子类型（如 MALLOC 的 HAL / PTA / MindSpore / ATB） |
| `Name` | 算子/ kernel 名称 |
| `Timestamp(ns)` | 时间戳（纳秒） |
| `Ptr` | 内存地址 |
| `Attr` | 事件属性（size / owner / allocation_id 等） |
| `Call Stack(Python)` | Python 调用栈 |
| `Call Stack(C)` | C 调用栈 |

### 6.2 DB 文件

db 格式可使用 **MindStudio Insight** 工具图形化展示内存数据。

---

## 七、常见问题

| 问题 | 解决方案 |
|------|---------|
| OOM 发生在采集区间 | 落盘 OOM 前后快照，查看 SNAPSHOT 事件的 `free_mem` / `allocated` |
| 需要采集特定 Step | 使用 `--steps=1,2,3` 或 `mstx.range_start/end` |
| 内存块监测不生效 | 确认设置了 `ASCEND_LAUNCH_BLOCKING=1` |
| 低效内存识别无效 | 确认使用的是 ATB LLM 或 Ascend Extension for PyTorch 单算子 |
| db 文件无法查看 | 使用 MindStudio Insight 工具打开 |
| VLLM-Ascend 场景 | 不支持内存泄漏分析和内存块监测（`--watch`） |
| 采集数据过大 | 减小 `call_stack` 深度、减少 `events` 项 |

---

## 八、回答格式要求

当用户询问 msMemScope 相关问题时，请按以下格式作答：

1. **问题类型**：一句话识别用户遇到的内存问题类型
2. **推荐方案**：推荐使用哪种采集和分析方式
3. **操作步骤**：给出关键命令或代码片段
4. **输出解读**：说明如何理解分析结果

如果用户提供了输出文件路径，直接调用 `msmemscope.analyze()` 或 `msmemscope.check_leaks()` 进行离线分析。
