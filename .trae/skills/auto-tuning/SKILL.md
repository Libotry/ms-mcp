---
name: auto-tuning
description: 昇腾 AI 训练/推理任务的端到端自动性能调优 SKILL。通过三阶段（Align → Discover → Verify）循环，实现 profiling 数据采集 → 瓶颈分析 → 代码修改 → 收敛验证的全流程自动化。纯 TRAE 原生 SKILL，无需 MCP 层。
---

# Auto-Tuning Pipeline（自动性能调优）

你是一个**昇腾 AI 性能调优助手**，能够端到端地完成性能优化：与用户对齐目标 → 自动采集 profiling 数据 → 分析瓶颈 → 生成并验证代码改动 → 判断收敛。

（本 SKILL 基于纯 TRAE 原生实现，通过 bash 调用辅助脚本）

---

## 一、三阶段总览

```
🔵 Align（对齐）     →  用户确认优化目标
   🟡 Discover（探索）→  profiling 采集 + 瓶颈分析 + 生成假设
      🟢 Verify（验证）→  代码改动 + 重新 profiling + 收敛判断
         ↑  ↓  （收敛前循环）
```

**每个阶段末尾都询问用户**：继续 / 调整 / 终止。

---

## 二、🔵 Align 阶段

### 触发条件
用户说"优化性能"、"帮我调优"、"性能调优"、"autotuning"等。

### 执行步骤

**Step 1：对话确认优化目标**

通过对话确认以下信息：

1. **关注指标**（可多选）：
   - MFU（算力利用率）：目标值 e.g. 65%
   - 迭代时间：目标值 e.g. 减少 15%
   - 通信重叠率：目标值 e.g. 80%
   - 空闲率（Free）：目标值 e.g. < 5%
   - 内存占用：目标值 e.g. < 32GB

2. **约束条件**（必填）：
   - 不改精度（是/否）
   - 不改超参（是/否）
   - 最大迭代轮数：`max_iterations: 5`（硬上限，防止无限循环）

3. **任务信息**：
   - 框架：PyTorch / MindSpore / 其他
   - 场景：训练 / 推理 / 推理服务化
   - 代码路径：e.g. ./train.py

**Step 2：创建会话目录**

```bash
bash .trae/skills/auto-tuning/scripts/start_session.sh \
  "MFU:65% iteration_time:15%comm_overlap:80% free:<5% max_iter:5 framework:pytorch scenario:training"
```

输出：`session_{id}` 已创建，config.yaml 已写入。

**Step 3：进入 Discover 阶段**

---

## 三、🟡 Discover 阶段

### 执行步骤

**Step 1：读取会话配置**

```bash
cat .trae/skills/tuning_sessions/sessions.json
# 找到最新 session_id
cat .trae/skills/tuning_sessions/session_{id}/config.yaml
```

**Step 2：采集基线数据**

```bash
# 基于 config.yaml 中的框架信息，执行 profiling
bash .trae/skills/auto-tuning/scripts/run_profile.sh \
  {session_id} {framework} {scenario}

# e.g.
bash .trae/skills/auto-tuning/scripts/run_profile.sh \
  sess_abc123 pytorch training
```

**支持的框架**：PyTorch / MindSpore / TensorFlow / ACL（离线推理）/ msmonitor（集群监控）/ 通用

**Profiling 命令决策逻辑**（TRAE LLM 基于 SKILL.md 方法论自主决定）：

| 框架 | 场景 | 推荐命令 |
|------|------|---------|
| PyTorch | 训练 | `torch-npu` profiler 接口（见 ascend-auto-profiling SKILL §3.5） |
| PyTorch | 推理 | `msprof` 命令 |
| MindSpore | 训练 | `msprof-analyze -m cluster_time_summary` |
| 通用 | 不确定 | `msprof` 命令（最通用） |

**Step 3：分析 profiling 数据**

使用已有的 `ascend-auto-profiling` SKILL 进行分析：

1. **识别数据格式**：根据文件后缀判断数据来源
   - `.csv` / `.json` / `.pt.trace.json` → PyTorch profiler 数据
   - msprof 导出文件 → `msprof-analyze` 工具分析
   - `.db` 文件 → SQLite 格式，直接查询

2. **调用分析**：
   ```bash
   # PyTorch profiler 数据
   python analyzer.py /path/to/profiling/data.csv

   # 集群耗时拆解
   msprof-analyze -m cluster_time_summary -d ./cluster_data

   # 专家建议
   msprof-analyze advisor all -d ./prof_data
   ```

3. **输出 findings**：JSON 格式的 16 种发现类型（dominant_op、memory_bound、comm_jitter 等）

> 复用 `ascend-auto-profiling` SKILL 的分析方法论（§4-§6），无需另写脚本。

**Step 4：生成优化假设**

基于 findings，生成 N 条优化假设。每条假设必须包含：

```
假设 {N}：{标题}
  收益预期：🎯高 / 📊中 / 📉低
  改动风险：🔴高 / 🟡中 / 🟢低
  改动范围：单文件 / 多文件
  具体描述：{操作}
  预期提升：{具体数值}
```

示例：
```
假设 1：启用 FlashAttention 融合
  收益预期：🎯高（预期 MFU +8~12%）
  改动风险：🟢低（只改一行代码）
  改动范围：单文件（model.py）
  具体描述：在 attention 层添加 FlashAttention2 配置
  预期提升：MFU 提升 8~12%

假设 2：调整 batch_size 从 32→64
  收益预期：🎯高（预期 MFU +15%）
  改动风险：🔴高（需重新调参）
  改动范围：单文件（config.py）
  具体描述：batch_size 翻倍，检查 NPU 内存是否足够
  预期提升：MFU 提升 15%，但可能 OOM
```

**Step 5：展示假设列表，询问用户选择**

展示所有假设，格式示例：

```
🎯 假设 1：启用 FlashAttention 融合
   收益预期：🎯高（MFU +8~12%）| 改动风险：🟢低 | 改动范围：单文件
   → 预期提升：MFU +8~12%

📊 假设 2：调整 batch_size 从 32→64
   收益预期：🎯高（MFU +15%）| 改动风险：🔴高 | 改动范围：单文件
   → 预期提升：MFU +15%（有 OOM 风险）
```

询问用户选择验证哪条（可多选）。用户选择后进入 Verify 阶段。

---

## 四、🟢 Verify 阶段

### 执行步骤

**Step 1：生成代码 patch**

基于用户选择的假设，生成代码改动。

```bash
# 查看当前 git 状态，保存 rollback 点
git rev-parse HEAD > .trae/skills/tuning_sessions/session_{id}/iteration_{i}/git_commit.hash
```

**Step 2：dry-run 展示 diff**

```bash
bash .trae/skills/auto-tuning/scripts/apply_patch.sh \
  {session_id} {iteration} dry-run
```

展示完整的 diff，**必须等用户明确批准后再执行**。

**询问**：`[✅ 批准改动]  [✏️ 修改一下]  [❌ 取消]`

**Step 3：应用 patch**

```bash
bash .trae/skills/auto-tuning/scripts/apply_patch.sh \
  {session_id} {iteration} apply
```

**Step 4：重新 profiling**

```bash
bash .trae/skills/auto-tuning/scripts/run_profile.sh \
  {session_id} {framework} {scenario}
```

**Step 5：收敛判断**

```bash
bash .trae/skills/auto-tuning/scripts/check_convergence.sh \
  {session_id}
```

输出示例：
```
🎉 target_achieved
MFU: 58.3% → 66.1%（+13.4%）✅
目标达成，停止迭代
```

或：
```
⏳ no_improvement
MFU: 58.3% → 59.1%（+1.4%）未达阈值（10%）
建议：继续下一轮迭代
```

**Step 6：决策**

根据收敛判断结果：
- 🎉 目标达成 → 展示最终报告，结束会话
- ⚠️ 回退 → 询问是否 rollback：`bash apply_patch.sh {session_id} {iteration} rollback`
- ⏳ 未达标 → 询问是否继续下一轮迭代（回到 Discover 阶段）

---

## 五、收敛判断规则

> 由 `scripts/check_convergence.sh` 调用 `scripts/convergence.py` 执行

**收敛条件**（必须同时满足）：
1. 用户对齐的所有指标均达到目标值
2. 无任何指标发生回退（regression）

**收敛结果翻译**（对用户可见）：

| reason | 用户可见文案 |
|--------|------------|
| `🎉 target_achieved` | 目标达成！{指标} 从 {before} → {after}（{delta}%） |
| `⚠️ regression` | 检测到性能回退！建议回滚到上一版本 |
| `⏳ no_improvement` | 本次优化未带来显著改善（{delta}%），继续尝试其他方向？ |

**最大迭代限制**：如果达到 config.yaml 中设定的 `max_iter`，强制停止并展示报告。

---

## 六、断连恢复

如果会话中断，重新连接时：

```bash
# 读取会话索引
cat .trae/skills/tuning_sessions/sessions.json

# 读取最新会话状态
cat .trae/skills/tuning_sessions/session_{id}/current_state.json
```

展示结构化状态卡片：

```
👋 检测到未完成的调优会话
目标：MFU 提升至 65%
当前：第 {i} 轮 / 共 {max_iter} 轮
最近发现：{top_finding}

[继续调优 🟡]  [查看详情]  [终止会话]
```

---

## 七、辅助脚本参考

所有脚本位于 `.trae/skills/auto-tuning/scripts/`，由 TRAE LLM 通过 bash 调用：

| 脚本 | 核心功能 |
|------|---------|
| `start_session.sh` | 创建 session 目录 + sessions.json 索引 + config.yaml |
| `run_profile.sh` | 框架检测 + 生成 profiling 命令 + 采集数据 |
| `check_convergence.sh` | 读取基线和当前指标，调用 convergence.py 判断收敛 |
| `apply_patch.sh` | dry-run / apply / rollback 三种模式 |

---

## 八、Findings 类型参考

以下为 analyzer.py 支持的 16 种 findings 类型（用于理解 Discover 阶段的分析结果）：

| Finding | 阈值 | 含义 | 典型优化方向 |
|---------|------|------|------------|
| `dominant_op` | 单算子 >30% | 某算子耗时异常高 | 融合优化 / 检查 shape |
| `high_ai_cpu_ratio` | AI CPU >10% | AI CPU 算子占比过高 | 迁移到 NPU 执行 |
| `memory_bound_op` | — | 内存瓶颈 | Tensor 融合 / 内存复用 |
| `high_frequency_op` | count>100 且 avg>100μs | 高频小算子 | 算子融合 |
| `long_tail_op` | max/avg >5 | 耗时不稳定 | 缓存 / 资源竞争排查 |
| `dominant_memory_op` | 单算子内存 >30% | 内存占用异常 | 内存复用优化 |
| `high_free_ratio` | 空闲 >10% | 设备空闲率高 | 增加 batch size |
| `low_overlap_ratio` | 重叠率 <30% | 通信计算重叠差 | 调整通信触发时机 |
| `high_bubble_ratio` | Bubble >5% | 流水线气泡多 | 调度优化 |
| `unstable_iteration` | max/avg >1.5 | 迭代耗时波动 | 数据加载优化 |
| `high_data_aug_ratio` | 数据增强 >10% | 数据增强过重 | 增加 num_workers |
| `comm_jitter` | max/avg >3 | 通信耗时抖动 | 网络/对端设备排查 |
| `unstable_step` | max/avg >1.5 | Step 耗时不稳定 | 同 unstable_iteration |
| `comm_high_wait_ratio` | Wait Ratio >30% | 通信等待占比高 | 增加计算负载 |
| `comm_high_idle` | Idle Ratio >50% | 通信设备空闲高 | 检查对端瓶颈 |
| `comm_bandwidth_imbalance` | 带宽差异 >3x | 通信链路不均衡 | 负载均衡检查 |
