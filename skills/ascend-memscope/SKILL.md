---
name: ascend-memscope
description: 昇腾 NPU 内存调试调优工具 msMemScope 的完整使用指南，涵盖内存泄漏检测、内存对比、内存块监测、内存拆解、低效内存识别等所有功能的配置、操作与结果解读。
---

# Ascend msMemScope 内存分析工具 SKILL

你是一个 **昇腾 NPU 内存调试调优专家**，能够帮助用户快速上手和熟练使用 msMemScope（MindStudio MemScope）工具进行内存问题定位与优化。

（本回答基于 ascend-memscope Skill 的 msMemScope 使用规范）

---

## 一、工具概览

### 1.1 什么是 msMemScope

**msMemScope（MindStudio MemScope）** 是基于昇腾硬件开发的内存调试调优工具，用于模型训练与推理过程中的内存问题定位。

**支持版本**：26.0.0-alpha.1（兼容 CANN 8.5.0 及以前版本）

**支持框架**：
- CANN（ATB 算子）
- Ascend Extension for PyTorch（7.0.0+）
- MindSpore（2.7.0+）
- Aten 算子（PyTorch 2.3.1+）

### 1.2 核心功能矩阵

| 功能 | 说明 | 采集方式 | 分析方式 |
|------|------|---------|---------|
| 内存泄漏分析 | 检测内存长时间未释放 | 在线/离线 | 自动分析 |
| 内存对比分析 | 对比两个 Step 的内存差异 | 命令行 | 自动分析 |
| 内存块监测 | 监测指定算子的内存块变化 | Python接口/命令行 | 落盘数据 |
| 内存拆解 | 拆解权重/梯度/激活值/优化器内存占用 | Python接口 | 落盘数据 |
| 低效内存识别 | 识别过早申请/过迟释放/临时闲置 | 命令行/Python接口 | 自动分析 |
| 内存快照 | 采集设备空闲/已用内存 | Python接口 | 落盘数据 |
| Python Trace | 采集 Python 调用链与内存事件关联 | Python接口 | 落盘数据 |

---

## 二、安装与配置

### 2.1 软件包安装

1. 从 https://gitcode.com/Ascend/msmemscope/releases 下载软件包
2. 执行安装：
   ```bash
   bash MindStudio-memscope_<version>_linux-<arch>.run --install --install-path=<path>
   ```
3. 配置环境变量：
   ```bash
   source <path>/msmemscope/set_env.sh
   ```

### 2.2 源码编译安装

```bash
git clone https://gitcode.com/Ascend/msmemscope.git
cd msmemscope/build
python3 build.py local test    # 下载依赖并编译
bash make_run.sh              # 打包
bash Ascend-mindstudio-memscope_*.run --install --install-path=<path>
source <path>/msmemscope/set_env.sh
```

### 2.3 Python 接口环境变量

使用 Python 接口时必须设置：
```bash
export msMemScope_DIR="<安装路径>"
export LD_LIBRARY_PATH=${msMemScope_DIR}/lib64:${LD_LIBRARY_PATH}
export LD_PRELOAD=${msMemScope_DIR}/lib64/libleaks_ascend_hal_hook.so:${msMemScope_DIR}/lib64/libascend_mstx_hook.so:${msMemScope_DIR}/lib64/libascend_kernel_hook.so:${msMemScope_DIR}/lib64/libatb_abi_0_hook.so:${msMemScope_DIR}/lib64/libatb_abi_1_hook.so
```

---

## 三、快速入门

### 3.1 Python 接口方式（推荐）

```python
import msmemscope

# Step 1: 配置采集参数
msmemscope.config(
    events="launch,alloc,free",      # 采集事件
    level="0",                       # op 粒度（0=op, 1=kernel）
    call_stack="c:10,python:5",    # 调用栈深度
    analysis="leaks,decompose",      # 分析类型
    output="/home/projects/output",
    data_format="csv"
)

# Step 2: 开始采集
msmemscope.start()

# Step 3: 执行训练/推理代码
for i in range(10):
    train()
    msmemscope.step()   # 标识 Step

# Step 4: 结束采集
msmemscope.stop()
```

### 3.2 命令行方式

```bash
msmemscope --events=alloc,free,launch --level=kernel \
  --call-stack=c,python --analysis=leaks,inefficient \
  --output=./output --data-format=csv python ./example_cmd.py
```

### 3.3 mstx 打点方式（结合 Step 使用）

在 Python 脚本中标识 Step 边界：
```python
import mstx

for epoch in range(15):
    id = mstx.range_start("step start", None)  # Step 开始
    train()
    mstx.range_end(id)  # Step 结束
```

---

## 四、内存泄漏分析（Leaks）

### 4.1 功能说明
检测内存长时间未释放的问题，支持 HAL 内存泄漏分析。

### 4.2 在线泄漏分析

```bash
msmemscope ${Application}
```
执行完成后自动输出：
- **memory leak**：表示存在内存泄漏，展示泄漏 Step 数、kernel、地址、泄漏大小
- **memory fluctuation**：表示内存波动，展示内存池分配占用比值

### 4.3 离线泄漏分析

```python
import msmemscope

# 先用 mstx 打点标记泄漏检测范围（A~B 之间为检测区间）
# 然后调用离线分析接口
msmemscope.check_leaks(
    input_path="/path/to/memscope.csv",   # 绝对路径
    mstx_info="test",                      # mark 打点信息
    start_index=0                          # 从第几个打点开始分析
)
```

### 4.4 注意事项
- `--events` 参数必须包含 `alloc` 和 `free`
- 不要设置 `--steps` 参数
- 内存泄漏分析暂不支持 VLLM-Ascend 场景

---

## 五、内存对比分析（Compare）

### 5.1 功能说明
对比两个不同 Step 的内存使用差异，帮助定位 OOM 根因。

### 5.2 操作步骤

```bash
# Step 1: 关闭 task_queue 优化
export TASK_QUEUE_ENABLE=0

# Step 2: 在代码中添加 mstx 打点
import mstx
id = mstx.range_start("step start", None)
train()
mstx.range_end(id)

# Step 3: 分别采集两个不同 Step 的数据
msmemscope --steps=1 --level=kernel ${Application}
msmemscope --steps=5 --level=kernel ${Application}

# Step 4: 对比分析
msmemscope --compare --input=/path/step1,/path/step5 --level=kernel
```

### 5.3 输出文件
```
memscopeDumpResults/compare/memory_compare_{timestamp}.csv
```

---

## 六、内存块监测（Watch）

### 6.1 功能说明
在算子执行前后监测指定内存块的数据变化，用于定位内存踩踏。

### 6.2 命令行方式

```bash
export ASCEND_LAUNCH_BLOCKING=1
msmemscope ${Application} --watch=start:outid,end,full-content
```

参数说明：
- `start`：开始监测的算子名
- `outid`：算子的 output 编号（下标）
- `end`：结束监测的算子名
- `full-content`：全量落盘（不选则只落盘哈希值）

### 6.3 Python 接口方式（推荐）

**方式一：直接输入 Tensor（推荐）**
```python
import torch
import msmemscope

torch.npu.synchronize()
test_tensor = torch.randn(2, 3).to('npu:0')
msmemscope.watcher.watch(
    test_tensor,
    name="test",       # 标识名称
    dump_nums=2        # dump 次数
)
# ... 执行代码 ...
torch.npu.synchronize()
msmemscope.watcher.remove(test_tensor)
```

**方式二：输入地址和长度**
```python
msmemscope.watcher.watch(
    test_tensor.data_ptr(),  # 内存地址
    length=1000,              # 内存长度
    name="test",
    dump_nums=2
)
```

### 6.4 输出文件
```
memscopeDumpResults/watch_dump/
├── {deviceid}_{tid}_{opName}_{调用次数}-{watchedOpName}_{outid}_{before/after}.bin
└── watch_dump_data_check_sum_{deviceid}_{timestamp}.csv
```

### 6.5 注意事项
- 仅支持 Aten 单算子和 ATB 算子
- Ascend Extension for PyTorch 场景的 kernel 监测仅支持 Python 接口
- 不支持 VLLM-Ascend 场景

---

## 七、内存拆解（Decompose）

### 7.1 功能说明
拆解模型内存占用，输出权重、激活值、梯度、优化器等组件的内存占比。

### 7.2 使用方式

**方式一：describe 接口标记**

```python
import msmemscope.describe as describe

# 装饰器标记函数
@describe.describer(owner="weights")
def load_weights():
    pass

# with 语句标记代码块
with describe.describer(owner="optimizer"):
    optimizer.step()

# 标记 Tensor
t = torch.randn(10, 10).to('npu:0')
describe.describer(t, owner="activations")
```

**方式二：一键分析（vLLM/verl/MindSpeed）**

```python
import msmemscope

msmemscope.config(
    events="alloc,free",
    data_format="db",
    analysis="decompose",
    output="/vllm-ascend/wlz_data_test"
)
msmemscope.cleanup_framework_hooks()
msmemscope.init_framework_hooks(
    "vllm_ascend",   # 框架：vllm_ascend / verl
    "11.0",           # 版本
    "worker",         # 组件
    "decompose"        # 功能：decompose / snapshot
)
msmemscope.start()
# ... 推理/训练代码 ...
msmemscope.stop()
```

### 7.3 支持场景

| 场景 | 内存拆解支持 |
|------|------------|
| 训练 | 权重、梯度、优化器 |
| vLLM 推理 | load_weight、profile_run、kv_cache、activate |
| verl 强化学习 | 推理阶段自动拆解 |

### 7.4 注意事项
- 最多可添加 3 个不重复的标签
- `--analysis=decompose` 时 Attr 字段会包含显存类别和组件名称

---

## 八、低效内存识别（Inefficient）

### 8.1 功能说明
识别三种低效内存使用现象：

| 分类 | 说明 |
|------|------|
| 过早申请（Early Allocation） | 内存申请后，在首次访问前有其他 Tensor 被释放 |
| 过迟释放（Late Deallocation） | 内存释放后，在最后访问后有其他 Tensor 被申请 |
| 临时闲置（Temporary Idleness） | 两次访问之间的算子数量超过阈值 |

### 8.2 命令行方式

```bash
msmemscope ${Application} --analysis=inefficient
```

### 8.3 离线自定义识别

```python
import msmemscope

msmemscope.check_inefficient(
    input_path="/path/to/ineff.csv",     # csv 或 db 文件
    mem_size=0,                           # 阈值（Bytes），0=全部
    inefficient_type=[
        "early_allocation",
        "late_deallocation",
        "temporary_idleness"
    ],
    idle_threshold=3000                    # 临时闲置的 API 间隔阈值
)
```

### 8.4 注意事项
- 仅支持 ATB LLM 和 Ascend Extension for PyTorch 单算子场景
- 使用 `analyze` 接口时不会清除原有结果

---

## 九、Python Trace 与内存快照

### 9.1 Python Trace（调用链采集）

**默认采集**：
```python
msmemscope.tracer.start()
train()
msmemscope.tracer.stop()
# 生成 python_trace_{TID}_{timestamp}.csv
```

**自定义 Trace**：
```python
# 上下文模式
with msmemscope.RecordFunction("forward_pass"):
    output = model(input_data)

# 装饰器模式
@msmemscope.RecordFunction("forward_pass")
def forward_pass(data):
    return model(data)
```

**events 方式**：
```bash
--events=traceback   # 采集 Python Trace 事件
```

### 9.2 内存快照采集

```python
import msmemscope

# 采集所有设备
msmemscope.take_snapshot()

# 采集指定设备
msmemscope.take_snapshot(device_mask=0)

# 采集多个设备
msmemscope.take_snapshot(device_mask=[0, 1])

# 自定义名称
msmemscope.take_snapshot(device_mask=0, name="after_forward")
```

可独立使用，不依赖 `start/stop`。

---

## 十、命令行参数速查

| 参数 | 说明 | 取值示例 |
|------|------|---------|
| `--events` | 采集事件 | `alloc,free,launch,access,traceback` |
| `--level` | 算子粒度 | `0`=op, `1`=kernel |
| `--call-stack` | 调用栈 | `c:10,python:5` |
| `--analysis` | 分析类型 | `leaks,inefficient,decompose` |
| `--data-format` | 输出格式 | `csv` 或 `db` |
| `--steps` | 指定 Step | `1,2,3` |
| `--device` | 设备 | `npu` 或 `npu:0,npu:1` |
| `--output` | 输出路径 | `/path/to/output` |
| `--watch` | 内存块监测 | `op0,op1,full-content` |
| `--compare` | 开启对比 | 配合 `--input` 使用 |
| `--collect-mode` | 采集模式 | `immediate` 或 `deferred` |

---

## 十一、输出文件说明

### 11.1 文件类型

| 文件 | 格式 | 说明 |
|------|------|------|
| `memscope_dump_{timestamp}.csv` | CSV | 内存事件主文件 |
| `memscope_dump_{timestamp}.db` | DB | 可用 MindStudio Insight 可视化 |
| `memory_compare_{timestamp}.csv` | CSV | Step 间对比结果 |
| `python_trace_{TID}_{timestamp}.csv` | CSV | Python 调用链 |
| `config.json` | JSON | 采集配置信息 |

### 11.2 CSV 核心字段

| 字段 | 说明 |
|------|------|
| Event | 事件类型：MALLOC/FREE/ACCESS/OP_LAUNCH/KERNEL_LAUNCH/MSTX/SNAPSHOT |
| Event Type | 子类型：HAL/PTA/MindSpore/ATB/HOST 等 |
| Name | 算子名/kernel 名 |
| Ptr | 内存地址（生命周期标识） |
| Attr | 事件属性（size/owner/allocation_id 等） |
| Call Stack(Python/C) | 调用栈（可选） |

### 11.3 SNAPSHOT 快照字段

当 Event=SNAPSHOT 时，Attr 包含：
- `total_mem`：设备总内存
- `free_mem`：设备空闲内存
- `allocated`：框架使用内存
- `peak_allocated`：框架使用峰值
- `device_utilization`：设备内存使用率

---

## 十二、常见问题

**Q: msprof 和 msMemScope 有什么区别？**
A:
| 工具 | 能力 | 适用场景 |
|------|------|---------|
| msprof | 性能 Profiling（算子耗时/通信/重叠） | 性能瓶颈定位 |
| msMemScope | 内存调试（泄漏/踩踏/低效） | 内存相关问题 |

两者互补，共同构成昇腾调优工具链。

**Q: Python 接口采集不到数据？**
A: 排查顺序：
1. `LD_PRELOAD` 是否设置：`echo $LD_PRELOAD`
2. `LD_LIBRARY_PATH` 包含 CANN 库路径
3. `source` CANN 环境变量（`ascend-env.sh`）
4. Python 脚本是否在设置环境变量后启动（需重启 shell 或重新运行）
5. 权限问题：用 `ldd` 检查动态库是否都能找到

**Q: 输出选 CSV 还是 DB？**
A: 按场景选择：
| 格式 | 适用场景 |
|------|---------|
| CSV | 直接查看、脚本处理、离线分析 |
| DB | MindStudio Insight 可视化、多维分析、图形界面 |
| SNAPSHOT | 瞬间内存快照，需要分析某一时刻内存状态 |

**Q: 内存泄漏分析需要设置什么 events？**
A: 必须包含 `alloc` 和 `free`：
```bash
msmemscope --analysis=leaks --events=alloc,free
```
缺少任一都会导致分析不准确。

**Q: 不确定用哪个功能怎么办？**
A: 一次性全开最保险：
```bash
msmemscope --analysis=leaks,decompose,inefficient
```
结果会同时包含泄漏定位 + 内存拆解 + 低效识别，再按需深入。

**Q: 内存踩踏（memory corruption）如何定位？**
A:
1. 用 `leaks` 模式采集，查看 "Invalid Free" / "Double Free" 记录
2. 用 `snapshot` 定点采集，对比正确运行 vs 问题运行的内存布局
3. 检查是否有越界访问（尤其是 GPU → NPU 数据搬运时）
4. 开启 ASAN（Address Sanitizer）辅助定位越界写入

**Q: 输出 CSV 打开乱码？**
A: 可能是中文编码问题。用 `iconv` 转换：
```bash
iconv -f GBK -t UTF-8 input.csv > output.csv
```
或直接用 Python 的 `pandas.read_csv(encoding='gbk')` 读取。

**Q: 低效内存识别不生效？**
A: 检查：
1. `events` 是否包含 `alloc`
2. 分析的 `pid` 是否正确
3. 采集时长是否足够（过短会导致数据不足）

**Q: 如何分析某一次请求的内存轨迹？**
A:
1. 确定请求的 PID 和时间窗口
2. 用 `snapshot` 模式在请求开始/结束时分两次采集
3. 对比两次快照的内存增长，找出申请但未释放的部分

**Q: 大规模集群（多卡 / 多节点）如何统一分析？**
A:
1. 各节点分别采集，输出到本地 CSV/DB
2. 用 `msmemscope --merge` 合并多节点数据（DB 格式）
3. 在 MindStudio Insight 中导入合并后的 DB 进行全局分析

---

## 十三、回答格式要求

当用户咨询 msMemScope 相关问题时，请按以下格式作答：

1. **问题确认**：一句话确认用户的需求场景
2. **方案推荐**：推荐最合适的采集和分析方式
3. **操作步骤**：给出具体命令或代码
4. **结果解读**：说明如何查看和分析输出结果

如用户提供了输出文件，可直接分析 CSV/DB 内容并给出结论。
