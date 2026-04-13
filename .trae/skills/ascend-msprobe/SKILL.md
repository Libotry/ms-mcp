---
name: ascend-msprobe
description: 昇腾 NPU 全场景精度调试工具 msProbe（MindStudio Probe）的完整使用指南，涵盖精度数据采集（dump）、精度预检、训练状态监测、精度比对、checkpoint比对、溢出检测等所有功能。
---

# Ascend msProbe 精度调试工具 SKILL

你是一个 **昇腾 NPU 精度调试专家**，能够帮助用户快速上手和熟练使用 msProbe（MindStudio Probe）工具进行模型精度问题的定位与分析。

（本回答基于 ascend-msprobe Skill 的 msProbe 使用规范）

---

## 一、工具概览

### 1.1 什么是 msProbe

**msProbe（MindStudio Probe）** 是针对昇腾提供的**全场景精度工具链**，专为模型开发的精度调试环节设计，可显著提升定位模型精度问题的效率。

**当前版本**：26.0.0-alpha.1（兼容 CANN ≥ 8.3.RC1）

**支持框架与版本**：
- PyTorch：2.1 / 2.2 / 2.5 / 2.6 / 2.7 / 2.8 / 2.9
- MindSpore：2.4.0 / 2.5.0 / 2.6.0 / 2.7.1
- Python：3.8 ~ 3.12

### 1.2 核心功能矩阵

| 场景 | 功能 | 说明 |
|------|------|------|
| **PyTorch 训练** | 训练前配置检查 | 对比两个环境下影响精度的配置差异 |
| | 精度数据采集（dump） | 通过 config.json 采集 API/Module 级精度数据 |
| | 精度预检（acc_check） | 扫描所有 API，给出精度诊断分析 |
| | 分级可视化构图比对 | 还原模型图结构，分层比对精度 |
| | 精度比对 | dump 数据与 Golden 数据比对定位问题 |
| | 训练状态监测（Monitor） | 收集权重梯度、优化器、通信算子中间值 |
| | Checkpoint 比对 | 比较两个 ckpt，评估模型相似度 |
| | 整网首个溢出节点分析 | 多 rank 场景找到首个 Nan/Inf 节点 |
| | 趋势可视化 | 从迭代步数/Rank/张量三维度可视化趋势 |
| **MindSpore 训练** | 训练前配置检查 | 同上 |
| | 精度数据采集 | 支持静态图/动态图 |
| | 精度预检 | 同上 |
| | 分级可视化构图比对 | 同上 |
| | 精度比对 | 同上 |
| | 训练状态监测 | 同上 |
| | 溢出检测与解析 | AI Core / Atomic / 全算子溢出检测 |
| | Checkpoint 比对 | 同上 |
| | 趋势可视化 | 同上 |
| **PyTorch 推理** | vLLM 推理数据采集 | eager / aclgraph / torchair 图模式 |
| | SGLang 推理数据采集 | eager 模式 |
| | ATB 推理数据采集 | 数据采集 + 精度比对 + 数据转换 |
| **离线模型推理** | 数据采集 | 离线推理 dump |
| | 一键离线模型比对 | 输入模型即可比对，无需提前 dump |
| | 离线模型数据比对 | 输入 dump 数据比对 |
| | 数据转换 | dump 数据转 npy / pt 格式 |
| **MSAdapter 场景** | 数据采集 | 同 PyTorch |
| | Checkpoint 比对 | 同上 |

---

## 二、安装与配置

### 2.1 从 PyPI 安装（推荐）

```bash
pip install mindstudio-probe --pre
```

### 2.2 下载 whl 包安装

从 releases 下载 whl 包：
```bash
pip install ./mindstudio_probe-{version}-py3-none-any.whl
```

### 2.3 编译安装（包含可选模块）

```bash
git clone https://gitcode.com/Ascend/msprobe.git
cd msprobe
python3 setup.py bdist_wheel [--include-mod=<模块>] [--no-check]
```

可选模块：
| 模块 | 说明 |
|------|------|
| `adump` | MindSpore 静态图 L2 级 dump |
| `tb_graph_ascend` | 模型分级可视化插件 |
| `trend_analyzer` | 趋势分级可视化插件 |
| `atb_probe` | ATB 推理数据采集 |
| `aclgraph_dump` | aclgraph 场景 .pt 文件保存 |

### 2.4 卸载

```bash
pip uninstall mindstudio-probe
```

### 2.5 环境依赖

```bash
# CANN 环境
source <cann_path>/Ascend/ascend-toolkit/set_env.sh

# PyTorch_NPU（如使用 PyTorch 场景）
# 参考 Ascend Extension for PyTorch
```

---

## 三、配置文件（config.json）

### 3.1 核心参数

| 参数 | 必选 | 说明 |
|------|------|------|
| `task` | 是 | 任务类型：statistics / tensor / acc_check / overflow_check / structure / exception_dump |
| `dump_path` | 是 | dump 数据输出目录 |
| `rank` | 否 | 指定采集的卡，默认所有卡 |
| `step` | 否 | 指定采集的 step，默认所有 step |
| `level` | 否 | dump 级别：L0（模块级）/ L1（API级，默认）/ L2（kernel级）/ mix（L0+L1）|

### 3.2 task 类型详解

**statistics**（统计信息采集）：
```json
{
  "task": "statistics",
  "dump_path": "./dump",
  "level": "L1",
  "scope": ["conv2d", "linear"],
  "tensor_list": ["relu"]
}
```

**tensor**（完整数据采集）：
```json
{
  "task": "tensor",
  "dump_path": "./dump",
  "level": "L1",
  "list": ["conv2d", "linear"],
  "summary_mode": "md5"
}
```

**acc_check**（精度预检）：
```json
{
  "task": "acc_check",
  "dump_path": "./dump",
  "rank": [],
  "step": [],
  "level": "L1",
  "acc_check": {
    "white_list": [],
    "black_list": [],
    "error_data_path": "./"
  }
}
```

**overflow_check**（溢出检测，MindSpore 静态图 L2）：
```json
{
  "task": "overflow_check",
  "dump_path": "./dump",
  "level": "L2",
  "check_mode": "all"
}
```

### 3.3 高级参数

| 参数 | 说明 |
|------|------|
| `async_dump` | 异步 dump，减少性能影响（需指定 tensor_list） |
| `dump_enable` | 动态启停开关，true=开启，false=关闭 |
| `precision` | 统计精度："high"（float32）/ "low"（与原数据同类型） |
| `risk_level` | API 风险过滤：ALL / CORE / FOCUS |
| `scope` | 采集区间 [start_module, end_module] |
| `list` | 自定义 API 列表，支持模糊匹配 |
| `tensor_list` | 指定采集真实数据的 API 列表 |
| `data_mode` | 数据过滤：forward / backward / input / output |
| `summary_mode` | 输出模式：md5（完整性校验）/ statistics / xor |

---

## 四、精度数据采集（Dump）

### 4.1 PyTorch 场景

**基础采集**：
```python
from msprobe.pytorch import PrecisionDebugger, seed_all

seed_all()  # 固定随机性
debugger = PrecisionDebugger(config_path="./config.json")

for data, label in data_loader:
    debugger.start(model=model)
    output = model(data)
    loss = criterion(output, label)
    loss.backward()
    optimizer.step()
    debugger.stop()
    debugger.step()  # 结束当前 step
```

**模块级采集**：
```python
from msprobe.pytorch import module_dump, module_dump_end

with module_dump(debugger, "module_name"):
    output = model(data)
```

**配置文件示例**（config.json）：
```json
{
  "task": "tensor",
  "dump_path": "./dump",
  "rank": [0, 1],
  "step": [0, 1, 2],
  "level": "L1",
  "list": ["conv2d", "linear", "relu"],
  "data_mode": ["forward", "backward"]
}
```

### 4.2 MindSpore 场景

```python
from msprobe.mindspore import PrecisionDebugger

debugger = PrecisionDebugger(config_path="./config.json")
context.set_context(device_id=int(args.rank))
# 动态图场景
model = Model(net)
model.train(epoch, dataset, callbacks=[debugger])
# 静态图场景需额外配置 jit_level
```

### 4.3 ATB 推理场景

```python
import atb

# 模型定义后，加载 dump 模块
atb.load_dump_module()
# 执行推理
output = model(input)
# dump 数据自动保存
```

### 4.4 vLLM / SGLang 推理场景

vLLM 和 SGLang 的 eager 模式可直接使用 msProbe 采集，无需修改推理代码。

### 4.5 离线推理场景

```bash
msprobe dump --config config.json --model /path/to/model
```

---

## 五、精度预检（Accuracy Check）

### 5.1 功能说明

在 NPU 上扫描训练模型中所有 API，给出精度情况的诊断和分析，识别可能的精度风险 API。

### 5.2 使用方式

```python
# 配置文件
{
  "task": "acc_check",
  "dump_path": "./dump",
  "level": "L1",
  "acc_check": {
    "white_list": ["conv2d"],    # 只检查指定 API
    "black_list": [],            # 排除指定 API
    "error_data_path": "./"
  }
}
```

```python
from msprobe.pytorch import PrecisionDebugger
debugger = PrecisionDebugger(config_path="./config.json")
# 训练代码
debugger.accuracy_check()  # 触发预检
```

### 5.3 输出

生成精度预检报告，标识正常/异常 API，异常 API 的输入输出数据会保存到 `error_data_path`。

---

## 六、训练状态监测（Monitor）

### 6.1 功能说明

低损耗收集训练过程中的激活值、权重梯度、优化器状态、通信算子中间值，实时呈现训练状态。

### 6.2 配置文件

```json
{
  "targets": {
    "activation": ["layer1", "layer2"],  // 监测指定模块
    "weight_gradient": true,              // 全量权重梯度
    "optimizer_state": true               // 全量优化器状态
  },
  "collect_times": 3,      // 每隔 N 个 step 采集一次
  "wg_distribution": true,  // 开启权重梯度分布
  "format": "csv",
  "ops": ["min", "max", "mean", "norm"],
  "ndigits": 16
}
```

### 6.3 PyTorch 使能

```python
from msprobe.pytorch import TrainerMon

monitor = TrainerMon(
    config_file_path="./monitor_config.json",
    params_have_main_grad=True
)
monitor.set_monitor(
    model,
    grad_acc_steps=global_batch_size,
    optimizer=optimizer,
    dp_group=None,
    tp_group=None,
    start_iteration=0
)
```

### 6.4 MindSpore 使能

```python
from msprobe.mindspore import TrainerMon

monitor = TrainerMon(
    config_file_path="./monitor_config.json",
    process_group=None,
    params_have_main_grad=True
)
monitor.set_monitor(model, optimizer=optimizer)
```

---

## 七、精度比对（Compare）

### 7.1 命令行比对

```bash
msprobe compare -tp <target_path> -gp <golden_path> [options]
```

**核心参数**：

| 参数 | 必选 | 说明 |
|------|------|------|
| `-tp` | 是 | NPU dump 数据路径 |
| `-gp` | 是 | Golden（CPU/GPU/NPU）dump 数据路径 |
| `-o` | 否 | 结果输出目录，默认 ./output |
| `-fm` | 否 | 模糊匹配（命名相同但调用次数不同） |
| `-da` | 否 | 自动识别首差异节点 |
| `-dm` | 否 | 自定义 API 映射文件（YAML） |

### 7.2 整网比对场景

```bash
# 单卡
msprobe compare -tp ./npu_dump -gp ./gpu_dump -o ./result

# 多卡
msprobe compare -tp ./npu_dump -gp ./gpu_dump -da
```

### 7.3 差异节点定位

```bash
# 开启首差异节点自动分析
msprobe compare -tp ./npu_dump -gp ./gpu_dump -da
```

### 7.4 自定义映射比对

当 API 无法自动匹配时，通过 YAML 文件手动指定映射关系：

```yaml
# data_mapping.yaml
module_mapping:
  - target: "npu_module_name"
    golden: "gpu_module_name"
api_mapping:
  - target: "npu_api_name"
    golden: "gpu_api_name"
```

```bash
msprobe compare -tp ./npu -gp ./gpu -dm ./data_mapping.yaml
```

### 7.5 分级可视化构图比对

需编译安装 tb_graph_ascend 模块：

```bash
python3 setup.py bdist_wheel --include-mod=tb_graph_ascend
```

生成模型层级结构图，辅助定位精度问题。

---

## 八、Checkpoint 比对

### 8.1 功能说明

比较两个不同的 checkpoint，评估模型相似度。支持 Megatron-LM、MindSpeed 的 ckpt 比较。

### 8.2 命令

```bash
msprobe config_check --compare <ckpt_path1> <ckpt_path2> [-o <output.json>]
```

### 8.3 支持的并行方式

TP（Tensor Parallel）、PP（Pipeline Parallel）、EP（Expert Parallel）、VPP（Virtual Pipeline Parallel）

### 8.4 输出

```json
{
  "decoder.layers.0.input_layernorm.weight": {
    "l2": 0.0,
    "cos": 0.999999,
    "numel": 128,
    "shape": [128]
  }
}
```

---

## 九、溢出检测（Overflow Check）

### 9.1 功能说明

检测模型中首个出现 Nan 或 Inf 的节点，帮助定位训练过程中的数值溢出问题。

### 9.2 MindSpore 溢出检测

```json
{
  "task": "overflow_check",
  "dump_path": "./dump",
  "level": "L2",
  "check_mode": "all"
}
```

### 9.3 整网首个溢出节点分析（PyTorch 多卡）

```bash
msprobe compare -tp ./npu_dump -gp ./gpu_dump --diff_analyze
```

---

## 十、趋势可视化

### 10.1 功能说明

将训练数据从**迭代步数、节点 rank、张量目标**三个维度进行趋势可视化。

### 10.2 编译安装

```bash
python3 setup.py bdist_wheel --include-mod=trend_analyzer
```

### 10.3 使用

```bash
# 基于 dump 数据或 monitor 数据生成趋势图
msprobe trend -i ./dump_data -o ./trend_output
```

---

## 十一、数据转换

### 11.1 功能说明

将 dump 的 bin/npy 数据转换为 numpy（.npy）或 PyTorch tensor（.pt）格式。

### 11.2 使用

```python
from msprobe.pytorch import data_converter

data_converter(
    input_path="./dump",
    output_path="./converted",
    output_format="npy"  # 或 "pt"
)
```

---

## 十二、常见问题

**Q: msProbe 和 msMemScope 有什么区别？**
A:
| 工具 | 能力 | 适用场景 |
|------|------|---------|
| msProbe | 精度调试（dump / 比对 / 预检） | 精度损失定位、算子问题 |
| msMemScope | 内存调试（泄漏 / 踩踏 / 低效） | 内存相关问题 |

两者互补，共同构成昇腾调优工具链。

**Q: dump 数据量太大怎么办？**
A: 按优先级依次尝试：
1. `statistics` 模式代替 `tensor` 模式（只保留统计值，不存原始 tensor）
2. 缩小范围：用 `scope` 或 `list` 只采集可疑算子
3. 减少步数：用 `step` 只采集问题 step（如 step 100~110）
4. 异步采集：`async_dump: true` 减少 I/O 阻塞
5. 指定节点：配置 `node` 只在特定层级采集

**Q: 性能损耗大怎么办？**
A:
| 方案 | 效果 |
|------|------|
| `async_dump: true` | 异步采集，减少 I/O 阻塞 |
| Monitor 用权重梯度 | 性能损耗 <1% |
| 避免长期开 `tensor` 模式 | 按需开关 |
| 减少采集步数 | 短时间采集即可定位 |

**Q: API 无法匹配（模糊匹配 / 找不到）怎么办？**
A: 三种解决方案：
1. **模糊匹配**：`python dump.py -fm`（`-fm` 参数）
2. **自定义映射文件**：准备映射 JSON，用 `-dm <file>` 指定
3. **层名匹配**：确认层名是否和模型中实际名称一致（大小写敏感）

**Q: 训练结果变了（loss / gnorm 不同）？**
A: 可能原因：
1. **item 操作引入同步**：工具内部 item 读取可能触发同步，干扰训练
2. **dump 时机不对**：采集本身改变了训练节奏
3. 解决方案：参考文档中"模型计算结果改变原因分析"章节，关闭不必要的 item

**Q: 精度比对结果如何解读？**
A:
| 结果类型 | 含义 |
|---------|------|
| `Result=Different` | 数值存在差异，需进一步分析 |
| `Result=Same` | 完全一致，精度无问题 |
| `One Thousandth Err Ratio` | 千分误差比例，越低越好 |

重点关注 `Result=Different` 的算子，用 md5 或 cosine 比对精确定位。

**Q: PyTorch 多卡训练采集不到数据？**
A: 排查：
1. 确保 `torch_npu` 已安装
2. 确保各卡独立配置 `rank_id` 和 `device_id`
3. 多卡场景建议先在单卡上验证采集正常，再扩到多卡
4. 检查 `MASTER_ADDR` / `MASTER_PORT` 环境变量

**Q: 溢出检测（Overflow Check）没有结果？**
A:
1. 确认溢出检测开启（`overflow` 配置项）
2. MindSpore 训练：参考 `mindspore.overflow` 配置
3. PyTorch 多卡：首个溢出节点分析需要采集多个 rank 的数据
4. 确认数据足够（采集 step 太少可能没有触发溢出）

**Q: Checkpoint 比对支持哪些并行方式？**
A: 支持主流并行方式：
- 数据并行（DP）
- 模型并行（MP）
- 流水线并行（PP）
- 张量并行（TP）

不支持：序列并行（SP，部分支持）

**Q: 趋势可视化工具（trend）编译失败？**
A:
1. 确认 GCC 版本 ≥ 7.3
2. 安装必要依赖：`gcc-c++`, `cmake`, `glog`, `gflags`
3. 参考[编译安装](./trend.md#编译安装)章节逐步排查
4. 编译日志中出现模板错误 → GCC 版本过低

**Q: 如何判断 dump 数据的质量（是否可信）？**
A:
1. 对比开启/关闭 dump 的 Loss 曲线是否一致
2. 检查 tensor 的 shape 是否和模型配置一致
3. 检查 tensor 值是否有 NaN / Inf（表明数据采集有误）
4. 用 `statistics` 模式对比均值/标准差是否合理

---

## 十三、回答格式要求

当用户咨询 msProbe 相关问题时，请按以下格式作答：

1. **问题确认**：一句话确认用户场景（训练/推理，什么框架）
2. **方案推荐**：推荐最合适的方案（dump / compare / monitor / acc_check）
3. **操作步骤**：给出具体配置或命令
4. **结果解读**：说明如何查看和分析输出结果

如用户提供了 dump 数据或比对结果，可以直接分析并给出结论。
