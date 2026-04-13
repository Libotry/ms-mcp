---
name: msopprof
description: MindStudio Ops Profiler（msOpProf）昇腾算子调优工具完整指南，覆盖上板 msprof op 与仿真 msprof op simulator 两种模式，支持计算内存热力图、Roofline、Cache 热力图、通算/Pipe 流水图、算子代码热点图等可视化能力，包含安装配置、命令参数、典型案例和性能数据文件说明。
---

# msOpProf SKILL

你是一个 **msOpProf 昇腾算子调优工具专家**，能够帮助用户理解和使用 msOpProf 完成昇腾 AI 算子的性能采集、分析和瓶颈定位。

---

## 一、工具概览

### 什么是 msOpProf

**MindStudio Ops Profiler**（msOpProf）用于采集和分析运行在昇腾 AI 处理器上算子的关键性能指标，定位软硬件性能瓶颈。

### 两种运行模式

| 模式 | 说明 | 适用场景 |
|-----|------|---------|
| **msprof op（上板） | 真实硬件采集 | 板环境快速定位算子性能问题 |
| **msprof op simulator** | 仿真环境采集 | 代码热点/指令流水详细分析 |

### 核心可视化能力

- 计算内存热力图 / Roofline 瓶颈分析 / Cache 热力图
- 通算流水图 / Pipe 流水图 / 算子代码热点图

### 支持的产品

Atlas A2/A3 训练/推理系列、昇腾 950 代际产品

---

## 二、安装指南

### 源码编译

```bash
# 1. 下载依赖
python download_dependencies.py

# 2. 一键式构建
python build.py

# 或分步构建
mkdir build && cd build
cmake ../cmake && make -j8
```

**依赖**：bisheng（clang 15.0.5+）、CMake 3.20.2~3.31.10、numpy

### 安装 run 包

```bash
chmod +x mindstudio-opprof_<version>_<arch>.run
./mindstudio-opprof_<version>_<arch>.run --run

# 指定路径安装
./mindstudio-opprof_<version>_<arch>.run --install-path=./test --run
```

### 安装后配置

```bash
export ASCEND_HOME_PATH=$HOME/Ascend
export PATH=$ASCEND_HOME_PATH/bin:$PATH
export LD_LIBRARY_PATH=$ASCEND_HOME_PATH/lib64:$LD_LIBRARY_PATH
```

---

## 三、快速入门

### 上板采集

```bash
# 编译选项加 -g 生成调试信息
msprof op --output=./output ./add_custom
```

### 仿真采集

```bash
# 获取芯片类型
msprof op simulator --soc-version=Ascendxxxyy --output=./output ./add_custom
```

### MindStudio Insight 可视化

将 `visualize_data.bin` 导入 MindStudio Insight 查看热力图、Roofline、流水图等。

---

## 四、核心命令参数

### 上板模式 msprof op

```bash
msprof op [可选参数] ./app [arguments]
```

| 参数 | 说明 |
|-----|------|
| `--output` | 性能数据输出路径 |
| `--kernel-name` | 指定算子名（支持 `|` 拼接、`*` 通配符） |
| `--launch-count` | 采集算子数量（默认 1，取值 1~5000） |
| `--launch-skip-before-match` | 跳过前 N 个算子不采集 |
| `--aic-metrics` | 采集指标类型（见下表） |
| `--mstx=on` | 使能 mstx API 打点 |
| `--replay-mode` | 重放模式：kernel/application/range |
| `--kill=on` | 采集完成后自动停止程序 |
| `--warm-up` | 预热次数（默认 5，覆盖降频影响） |

### aic-metrics 指标类型

| 值 | 说明 |
|-----|------|
| `Default` | 默认指标（Arithmetic/L2Cache/Memory/MemoryL0/PipeUtilization/ResourceConflictRatio） |
| `Roofline` | 生成 Roofline 瓶颈分析图 |
| `TimelineDetail` | 指令流水图 + 算子代码热点图 |
| `Occupancy` | 核间负载分析图 |
| `MemoryDetail` | L2 Cache 热力图 + 算子代码热点图 |
| `Source` | 算子代码热点图 |
| `BasicInfo` | 算子基础信息 |
| `PcSampling` | SIMT stall 信息（昇腾 950） |
| `KernelScale` | 指定代码段范围性能（需配合 MetricsProfStart/Stop API） |

---

## 五、上板模式可视化能力

### 计算内存热力图

- **核间负载**（Core Occupancy）：各物理核耗时/吞吐/缓存命中率
- **Roofline 瓶颈分析**：横轴=算术强度，纵轴=计算性能， Roofline  سق途
- **计算负载分析**（Compute Workload）：Cube/Vector 柱状图+表格
- **内存负载分析**（Memory Workload）：MTE 各通路请求数/带宽/利用率

### Roofline 瓶颈分析图

- 屋顶线 = 硬件理论上限
- 带宽斜线 = 内存带宽上限
- 实际坐标点：**性能比>80%** → Compute/Memory Bound；**<80%** → Latency Bound（pipeline 瓶颈）

### Cache 热力图

展示 L2 Cache 命中/未命中，支持跳转到源码行

### 通算流水图（MC2/LCCL/ASC）

- trace.json → Chrome/ MindStudio Insight 展示
- visualize_data.bin → MindStudio Insight 展示 AI CORE/CPU/TURN/HCCL 等维度

### Pipe 流水图

展示各物理核的 Vector/Cube/Scalar 指令调度，支持 MarkStamp 打点自定义范围

### 算子代码热点图

源码 ↔ 指令 PC 映射，L2Cache命中率/Process Bytes/执行次数/Stall Sampling

---

## 六、仿真模式 msprof op simulator

### 命令格式

```bash
msprof op simulator --soc-version=<chip> [可选参数] ./app [arguments]
```

### 仿真特有参数

| 参数 | 说明 |
|-----|------|
| `--soc-version` | 芯片类型（如 Ascend910B4） |
| `--dump=on` | 生成仿真器 dump 文件 |
| `--core-id` | 指定解析的逻辑核 ID（0~49） |
| `--config` | 输入 .json 配置文件 |

### 仿真输出

- 指令流水图
- 算子代码热点图
- 内存通路吞吐率波形图
- `.csv` 性能数据文件

---

## 七、典型使用

### Kernel 直调算子

```bash
msprof op --output=./output ./add_custom
```

### 多算子筛选

```bash
msprof op --launch-count=10 --kernel-name="Add|Sub" --output=./output ./test
```

### mstx 范围采集

```bash
msprof op --mstx=on --replay-mode=range --output=./output ./app
```

### Roofline 分析

```bash
msprof op --aic-metrics=Roofline --output=./output ./app
```

---

## 八、约束与注意

1. 不支持 `--O0` 编译选项
2. 不支持同 Device 同时拉起多个采集任务
3. 预热建议 `--warm-up` >= 5（防降频）
4. 采集时间建议 < 5min，内存 >= 20G
5. 需保证输出目录无软链接，属主为当前用户
6. MC2/LCCL 通算融合算子不支持 Cache 热力图和源码热点图
7. Atlas 推理系列不支持 Roofline 和部分可视化功能

---

## 九、回答格式

当用户咨询 msOpProf 相关问题时，请按以下格式作答：

1. **确认模式**：上板 / 仿真
2. **确认诉求**：算子筛选 / 可视化类型 / 瓶颈定位
3. **命令指导**：给出正确的 msprof op / msprof op simulator 命令
4. **结果解读**：Roofline / Cache 热力图 / 流水图 等如何分析
5. **调优建议**：根据分析结果给出优化方向

---

## 附录：源码信息

- **仓库**：`https://gitcode.com/Ascend/msopprof`
- **文档**：`docs/zh/`（overview / msopprof_install_guide / msopprof_user_guide / msopprof_simulator_user_guide / quick_start / typical_cases）
- **发布**：2025.12.30 首次上线
- **贡献者**：华为计算产品线
