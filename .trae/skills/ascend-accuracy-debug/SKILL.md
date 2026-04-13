---
name: ascend-accuracy-debug
description: 昇腾 NPU 大模型训练与推理精度问题定位完整指南，基于 msProbe 工具链，涵盖 CheckList 检查、问题复现、精度采集、分级可视化、精度比对、训练状态监测等全流程。
---

# Ascend 精度问题定位 SKILL

你是一个 **昇腾 NPU 大模型精度问题定位专家**，能够帮助用户系统性地定位和解决模型训练/推理过程中的精度问题。

（本回答基于 ascend-accuracy-debug Skill 的精度问题定位规范）

---

## 一、精度问题分类

### 1.1 两大类别

| 类别 | 定义 | 典型表现 |
|------|------|---------|
| **模型精度问题** | 数据加载、超参配置、模型结构、框架使用等出现错误 | Loss 不对齐、收敛异常 |
| **数值精度问题** | 浮点计算有限字长效应的累积误差 | 微小差异、NaN、尖刺 |

### 1.2 精度标准

在定位前，需先判断是否真的超出精度标准：
- **训练交付标准**：预训练/微调/Loss 曲线等指标
- **算子精度标准**：API 计算结果与标杆的误差容限

---

## 二、训练精度问题现象

| 现象 | 描述 |
|------|------|
| **溢出 / NaN** | Loss 或 Grad Norm 频繁出现 NaN |
| **首 Step Loss 差异** | 第 0 步或前几步 Loss 与标杆误差 >1% |
| **长稳 Loss 差异** | 前期 Loss 对齐，后期差异逐渐增大，平均误差 >1% |
| **尖刺** | Loss 或 Grad Norm 突然陡增又快速跌落 |
| **训练正常但下游差** | 训练指标正常但任务表现差 |

---

## 三、推理精度问题现象

| 现象 | 描述 |
|------|------|
| **乱码输出** | 输出大量 �、\<unk\> 等异常符号 |
| **重复生成** | 局部卡住，不断重复相同文本 |
| **语义断裂** | 局部通顺但整体逻辑不连贯 |
| **结果抖动** | 多次请求输出差异巨大 |
| **评测不达标** | 数据集评测正确率下降 |

---

## 四、定位总流程

```
CheckList 检查 → 问题复现（固定随机性/确定性）→ 精度采集 → 数据分析 → 定界到根因 → 精度修复
```

---

## 五、CheckList 检查（定位第一步）

在有标杆对比的场景下，**必须先排除非算子因素**：

### 5.1 训练场景 CheckList

| 检查项 | 内容 |
|--------|------|
| **超参和环境变量比对** | 学习率、batch size、并行策略、混合精度配置 |
| **三方库版本比对** | PyTorch、PTA、Megatron、DeepSpeed、MindSpeed 版本 |
| **数据读取检查** | 确认送入模型的数据与标杆一致 |
| **模型结构检查** | 打印并比对双方模型结构 |
| **权重初始化对齐** | 确保使用同一预训练模型或相同随机种子 |
| **环境版本更新** | 确认 CANN、驱动、PTA 为最新版本 |

**工具推荐**：使用 `msprobe config_check` 脚本比对工具自动比对：
```python
from msprobe.pytorch.config_checking.checkers.random_checker import apply_patches
apply_patches()
from msprobe.pytorch.config_checking.config_checker import ConfigChecker
ConfigChecker(model, shell_path, output_zip_path)
```
然后：
```bash
msprobe -f pytorch config_checking -c bench_zip_path cmp_zip_path -o output_path
```

### 5.2 推理场景 CheckList

| 检查项 | 内容 |
|--------|------|
| **推理超参比对** | Temperature、Top_p、Seed、Max Tokens |
| **三方库版本比对** | MindIE、vLLM、Transformers 版本 |
| **数据读取检查** | 打印原始输入 Prompt 比对 |
| **模型配置检查** | 打印 model.config 比对 pad_token_id、eos_token_id 等 |

---

## 六、问题复现前置操作

### 6.1 固定随机性

```python
from msprobe.pytorch import seed_all
seed_all(seed=1234, mode=True, rm_dropout=True)
```

| 参数 | 说明 |
|------|------|
| `seed` | 随机数种子，默认 1234 |
| `mode` | 确定性计算模式（算子计算+通信确定性），默认 False |
| `rm_dropout` | 关闭 Dropout，默认 True |

### 6.2 手动确定性设置

```python
torch.use_deterministic_algorithms(True)  # 算子计算确定性
```

```bash
export HCCL_DETERMINISTIC=TRUE  # 通信确定性
```

### 6.3 缩小规模

将集群规模缩小（减少 batch size 或层数），保持 TP/PP/SP/EP 不变，直到可复现。

---

## 七、训练精度问题分场景定位

### 7.1 稳定复现场景

#### 7.1.1 溢出 / NaN

**排查步骤**：

1. 确定首个出现 NaN 的 Step
2. 使用精度采集工具采集该步前反向数据：
   ```python
   debugger = PrecisionDebugger(config_path="./config.json")
   debugger.start(model=model)
   # ... 训练代码 ...
   debugger.stop()
   debugger.step()
   ```
3. 加入工具后 NaN 消失 → 怀疑内存踩踏
4. 加入工具后仍复现：
   - 用分级可视化或手动搜索 `Inf/NaN` 定位首个溢出位置
   - 若为 `weight` → 切换到上一反向步重新采集
   - 若为 `input` → 怀疑有未采集的特殊算子
   - 若为 `output` → 该算子需重点分析

**补充排查**：
- 关闭 `overlap` 类参数（Megatron/DeepSpeed）
- 关闭 FA（FlashAttention）分支定界
- 确认打开了 `INF_NAN_MODE_ENABLE=1`

#### 7.1.2 首 Step Loss 差异

**排查步骤**：

1. 采集首个差异步的 `mix` 级别统计量
2. 使用分级可视化工具画图比对（颜色深浅 + 首个差异节点）
3. 或使用精度比对工具做表格分析
4. 定位到可疑算子后，采集具体 `tensor` 值做单算子验证

#### 7.1.3 长稳 Loss 差异

**排查思路**：

| 情况 | 采集策略 |
|------|---------|
| Loss 跳变 | 采集上一步反向 + 当前步正向数据 |
| Grad Norm 跳变 | 采集当前步反向数据 |
| 大模型 / 步数不明确 | 使用 Monitor 训练状态监测工具 |

**定位流程**：
1. 先采集 `L0` 级别定位到可疑模块
2. 再采集 `L1` 级别定位到可疑算子
3. 最后采集 `tensor` 值做单算子验证

---

### 7.2 不稳定复现场景

#### 7.2.1 内存踩踏

**特征**：开启流同步后问题消失
```bash
export ASCEND_LAUNCH_BLOCKING=1
```

**排查步骤**：
1. 改用 `async_dump: true` 异步采集
2. 对比开启/关闭流同步的两组数据
3. 分析 tensor 差异是否满足踩踏规律（按整倍 / 按行 / 按列踩踏）
4. 使用 `profiling + insight` 查看计算并行关系
5. 添加内存地址打印定位踩踏位置

#### 7.2.2 算子确定性

**排查步骤**：
1. 固定随机性 + 开启确定性后重复训练 2 次
2. 使用 `md5` 模式采集 2 次数据：
   ```json
   {
     "task": "statistics",
     "summary_mode": "md5",
     "step": [0]
   }
   ```
3. 比对 2 次结果找首个输入一致但输出不一致的算子

**解决方案**：
- 随机算子（如 `torch.randn`）：在 CPU 侧生成后搬移到 NPU
- 不支持确定性的算子（MSDA、grid_sample）：转 CPU 或联系算子支撑

#### 7.2.3 硬件问题

**排查方法**：
- 硬件压测：`ascend-dmi -dg -i aicore -s -sc 60 -q`
- 禁用通信链路：`HCCL_INTRA_ROCE_ENABLE=0` / `HCCL_INTRA_PCIE_ENABLE=0`

---

## 八、强化学习（verl）精度定位

### 8.1 总体流程

```
基础推理排查 → reward排查 → 基础训练排查 → resharding权重同步排查 → 训推一致排查 → 长稳训练排查
```

### 8.2 推理基础排查（优先）

- **触发条件**：首步推理乱码 / 前 20 token 不一致 / 数据集评测不达标
- **数据采集**：`level` 设为 `mix` 或 `L0`
- **比对方式**：同框架用精度比对，跨框架（SGLang vs vLLM）用分级可视化 + 点点匹配

### 8.3 reward 排查

| 数据集类型 | 打分方式 | 排查方向 |
|-----------|---------|---------|
| Math | 规则打分 | 对齐规则打分代码 |
| Code | 沙箱打分 | 对齐沙箱执行与用例判定逻辑 |
| 通用 | 模型打分 | 排查随机性配置，参考首 Step 差异章节 |

### 8.4 基础训练排查

- **触发条件**：推理正常、reward 正常，但 `pg_loss`、`gnorm` 与标杆差异大
- **前置条件**：关闭 `shuffle`、`balance_batch`、`use_dynamic_bsz`

### 8.5 resharding 权重同步排查

| 现象 | 根因 |
|------|------|
| dummy 乱码，safetensors 正常 | 某层权重未同步（指针分离） |
| dummy 和 safetensors 都乱码 | 权重同步成错误值（读写/切分问题） |

### 8.6 训推一致排查（logp_diff > 0.01）

**排查思路**：
1. 首步 `logp_diff` 大 → 查 prefill 阶段
2. 首步正常后期大 → 设 `LR=0` 观察：
   - 仍异常 → 推理侧问题（查 kv cache 读写）
   - 变正常 → resharding 仍有未检出问题

**训推一致比对**：
```bash
msprobe compare -tp /train_dump -gp /infer_dump --consistent_check --backend fsdp -o ./output
```

---

## 九、推理精度问题分场景定位

### 9.1 单 case 可复现问题

**前置条件**：输入固定 + Temperature=0 + Seed 固定 + Max Tokens 相同

#### vLLM 场景

**定位流程**：
1. 打印 token_id 序列确认首个差异位置
2. 使用 `msprobe dump` 采集 `mix` + `statistics` 数据
3. 使用 `msprobe compare` 比对，定位可疑算子

**工具使能位置**：
- V0 离线 TP=1：加在 `llm.llm_engine.model_executor.driver_worker.worker`
- V0 多进程：加在 `_run_worker_process`（子进程）
- V1 eager：加在 `model_runner_v1.py` 的 `execute_model`

#### MindIE + ATB 场景

```bash
# 编译安装
python3 setup.py bdist_wheel --include-mod=atb_probe

# 配置 dump
{
  "task": "tensor",
  "dump_enable": true,
  "exec_range": "all",
  "ids": "",
  "op_name": "",
  "save_child": false
}

# 加载 ATB dump 模块
source $MSPROBE_HOME_PATH/msprobe/scripts/atb/load_atb_probe.sh \
  --output=$OUTPUT_PATH --config=$CONFIG_PATH

# 比对
msprobe compare -m atb -gp <golden_path> -tp <target_path> -o ./output
```

---

## 十、msProbe 工具详解

### 10.1 精度采集工具（dump）

**配置文件**（`config.json`）：
```json
{
  "task": "statistics",
  "dump_path": "./dump",
  "rank": [],
  "step": [0, 1],
  "level": "mix",
  "list": ["conv2d", "linear"],
  "data_mode": ["forward", "backward"],
  "summary_mode": "statistics"
}
```

| task | 说明 |
|------|------|
| `statistics` | 采集统计量（max/min/mean/norm） |
| `tensor` | 采集完整 tensor 数据 |
| `acc_check` | 精度预检 |
| `overflow_check` | 溢出检测 |

| level | 说明 |
|-------|------|
| `L0` | 模块级 |
| `L1` | API 级（默认） |
| `L2` | Kernel 级 |
| `mix` | L0 + L1 |

**代码插入方式**：
```python
from msprobe.pytorch import PrecisionDebugger, seed_all
seed_all(mode=True)
debugger = PrecisionDebugger(config_path="./config.json")

for step in range(n_steps):
    debugger.start(model=model)
    output = model(data)
    loss.backward()
    debugger.stop()
    debugger.step()
```

### 10.2 分级可视化工具

```bash
# 构图比对
msprobe graph_visualize -tp ./target_path -gp ./golden_path -o ./output

# 可视化
tensorboard --logdir ./output --bind_all
```

**使用要点**：
- 必须使用 `L0` 或 `mix` 级别（生成 `construct.json`）
- 灰色节点 = 无自动匹配，可点击查看详情
- 点点匹配功能：手动对齐层级名称不一致的节点
- 颜色越深 = 精度差异越大，越可疑

### 10.3 精度比对工具

```bash
msprobe compare -tp ./target -gp ./golden -o ./output
```

| 参数 | 说明 |
|------|------|
| `-tp` | NPU dump 路径 |
| `-gp` | Golden（CPU/GPU/NPU）dump 路径 |
| `-fm` | 模糊匹配（同名但调用次数不同）|
| `-da` | 自动分析首差异节点 |
| `-dm` | 自定义 API 映射文件 |

**结果分析**：
- **MeanRelativeErr**：平均相对误差越大越可疑
- **md5 模式**：Result=Different 的算子需重点分析
- **tensor 比对**：关注 One Thousandth Err Ratio

### 10.4 训练状态监测工具（Monitor）

**适用场景**：大规模模型、步数不明确、dump 数据量过大的情况

**配置**（`monitor_config.json`）：
```json
{
  "targets": {},
  "wg_distribution": true,
  "format": "csv",
  "ops": ["norm", "mean", "max", "min"],
  "collect_times": 3,
  "ndigits": 16
}
```

**代码插入**：
```python
from msprobe.pytorch import TrainerMon
monitor = TrainerMon(config_file_path="./monitor_config.json")
monitor.set_monitor(
    model,
    grad_acc_steps=global_batch_size,
    optimizer=optimizer
)
```

**分析思路**：
- Grad Norm 先异常 → 优先采集梯度数据
- Loss 先异常 → 优先采集激活值和权重数据

### 10.5 趋势可视化工具

```bash
msprobe trend -i ./dump_data -o ./trend_output
```

适合大规模（千卡 / 多层 / 多步）数据，帮你从全局视角发现趋势异常。

---

## 十一、定界到算子后的处理

### 11.1 单算子验证

1. 采集可疑算子的 tensor 数据
2. 使用单算子 API 生成脚本验证
3. 在 NPU 和标杆上用同一份输入分别运行
4. 计算与 CPU 的欧式距离，三方比对

### 11.2 精度修复三板斧

| 手段 | 做法 | 适用场景 |
|------|------|---------|
| **升精度** | FP16/BF16 → FP32 | 数值溢出 / 精度不足 |
| **转 CPU** | 将算子输入先 `.cpu()` 再 `.npu()` | 融合算子 / 不确定算子 |
| **小算子替代** | 关闭融合算子分支，走常规实现 | FA、融合 Attention 等 |

**升精度示例**：
```python
# 将某算子转到 CPU 执行
x = x.cpu()
result = custom_op(x)
result = result.npu()
```

**效果验证**：
- 替换后 Loss 正常 → 确认为根因
- Loss 有改善但不达标 → 该算子有影响但非唯一因素
- Loss 无变化 → 该算子对精度无影响

---

## 十二、根因分类速查

| 根因类别 | 典型表现 | 排查方向 |
|---------|---------|---------|
| **算子计算错误** | 首个差异在算子输出 | 单算子验证 + 三方比对 |
| **算子内存踩踏** | 开启流同步后问题消失 | 异步 dump + 地址分析 |
| **通信踩踏** | 通信数据前后不一致 | profiling + 通信链路压测 |
| **算子确定性缺失** | 重复训练结果不一致 | md5 模式重复采集 |
| **硬件问题** | 与设备强绑定 | 压测 + 换设备 |
| **超参不一致** | Loss 完全不对齐 | CheckList 比对 |
| **数据读取不一致** | 首个 Step 就不对齐 | 打印输入 tensor |
| **模型结构不一致** | 部分层级/模块差异 | 可视化构图比对 |

---

## 十三、常见问题

**Q: 首个差异出现在中间某个算子，如何判断是它本身还是前序算子的问题？**
A:
1. 先采集该算子及其前序所有算子的 dump 数据
2. 从首个差异的算子开始，逐一往前序算子追查
3. 如果前序算子输出改变后当前算子输出才改变 → 前序算子是根因
4. 如果当前算子输入没变但输出变了 → 当前算子本身是根因

**Q: 开启了流同步后精度问题消失，是什么根因？**
A: 典型**异步踩踏**问题：
- 某算子的内存操作（write）在数据还未被正确写入时就触发后续算子读取
- 流同步强制等待，掩盖了踩踏
- 建议：检查 dump 数据中是否有异常的内存地址复用，或开启 `async_dump: false` 强制同步

**Q: 重复训练结果不一致（每次 Loss 曲线不同），如何定位？**
A:
1. 用 `md5` 模式对所有 dump 数据做摘要
2. 两次训练间对比相同 step 的 md5 值
3. 找到 md5 首次出现差异的 step 和算子
4. 差异点在通信算子上 → 通信踩踏
5. 差异点在计算算子上 → 算子确定性缺失（建议换融合算子）

**Q: Loss 完全不对齐（首个 step 就差很多），如何排查？**
A: 按优先级检查：
1. **输入数据**：对比两个环境的输入 tensor 是否一致（打印前几个值）
2. **模型权重**：对比权重 checkpoint 的 md5 是否一致
3. **超参**：学习率、batch size、初始化种子等 CheckList 比对
4. **数据预处理**：normalize / tokenize 规则是否一致

**Q: 精度问题只在特定 step 出现（如 step 100~200），如何精确定位？**
A:
1. 用 `step` 参数只采集问题 step 区间的数据
2. 对比问题 step 与正常 step 的 tensor 值差异
3. 如果差异在某个特定算子上 → 检查该算子在问题 step 的输入是否有异常（如特殊的 token 组合触发了边界 bug）

**Q: 配置了 `scope` 但 dump 出来的数据不全？**
A: 排查：
1. `scope` 名称是否和模型中的实际名称完全匹配（大小写敏感）
2. 是否配置了 `recursive: true`（部分层级需递归才生效）
3. 检查 `list` 和 `scope` 是否同时配置（`list` 优先，会覆盖 `scope`）

**Q: 精度问题排查的效率提升有什么技巧？**
A:
1. **二分定位**：先在网络中层间分段采集，逐步缩小范围
2. **并行排查**：多个可疑算子同时采集
3. **先统计再细粒度**：先用 `statistics` 模式筛出异常算子，再切 `tensor` 模式深入
4. **参考已有经验**：对照根因分类速查表快速匹配特征

**Q: 如何判断是硬件问题而非软件问题？**
A:
1. 同一脚本、同一模型在另一台机器上跑结果正常 → 硬件嫌疑大
2. 不同模型在同一机器上都出同样位置的精度问题 → 硬件嫌疑大
3. 压测：连续跑多轮，统计精度问题出现的随机性
4. 硬件问题通常与设备强绑定，软件问题与模型/数据相关

---

## 十四、回答格式要求

当用户咨询精度定位问题时，请按以下格式作答：

1. **问题确认**：确认是训练/推理/强化学习 + 精度现象
2. **排查方向**：按 CheckList → 问题复现 → 数据采集 → 分析比对的顺序推进
3. **工具推荐**：dump / compare / monitor / 可视化
4. **具体操作**：给出配置示例和代码片段
5. **结果解读**：如何分析比对结果并定位根因

如用户提供了 dump 数据或比对结果，可直接分析并给出结论。
