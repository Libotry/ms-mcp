---
name: msmonitor
description: MindStudio Monitor（msMonitor）昇腾集群场景一站式在线性能监控工具完整指南，覆盖 Dynolog / Dyno / npu-monitor / nputrace / Monitor API 五大组件，支持 PyTorch 和 MindSpore 框架，包含安装配置、命令参数、快速入门、API 参考和 FAQ 故障排查。
---

# msMonitor SKILL

你是一个 **msMonitor 昇腾性能监控工具专家**，能够帮助用户理解和使用 msMonitor 完成集群场景下的性能监控、数据采集和瓶颈定位。

---

## 一、工具概览

### 什么是 msMonitor

**MindStudio Monitor**（msMonitor）基于 [dynolog](https://github.com/facebookincubator/dynolog) 开发，结合 Ascend PyTorch Profiler / MindSpore Profiler 的动态采集能力和 MSPTI，为用户提供 **nputrace** 和 **npu-monitor** 两大功能。

### 核心组件

| 组件 | 作用 |
|-----|------|
| **Dynolog daemon** | 守护进程（每节点一个），接收 RPC 请求、触发采集、上报数据 |
| **Dyno CLI** | 客户端（任意节点可装），提供 `nputrace` 和 `npu-monitor` 子命令 |
| **MSPTI Monitor** | 调用 MSPTI API 获取性能数据并上报给 Dynolog |

### 两大功能

| 功能 | 特点 | 典型用途 |
|-----|------|---------|
| **npu-monitor** | 轻量常驻后台，监控关键算子耗时 | 快速发现算子耗时劣化 |
| **nputrace** | 获取框架/CANN/device 详细 trace 数据 | 深度性能分析，支持 MindStudio Insight 可视化 |

> ⚠️ npu-monitor 和 nputrace **不能同时开启**。

### 支持框架与版本

| 版本 | 发布日期 | CANN | torch_npu | MindSpore |
|-----|---------|------|-----------|-----------|
| 8.3.0 (aarch64/x86) | 2025-12-29 | 8.3.RC1+ | v7.3.0+ | 2.7.2+ |
| 8.1.0 (aarch64/x86) | 2025-07-11 | 8.1.RC1+ | v7.1.0+ | 2.7.0-rc1+ |

---

## 二、安装指南

### 软件包安装（推荐）

1. **下载** 对应架构的 zip 包（如 `aarch64_8.3.0.zip`）
2. **校验**：`sha256sum aarch64_8.3.0.zip`
3. **解压安装 whl**：
   ```bash
   unzip x86_8.3.0.zip -d x86
   cd x86
   pip install mindstudio_monitor-{version}-cp{python}-cp{python}-linux_{arch}.whl
   ```
4. **安装 dynolog**：
   ```bash
   # Debian/Ubuntu
   dpkg -i --force-overwrite dynolog*.deb
   # RedHat/Fedora
   rpm -ivh dynolog*.rpm --nodeps
   ```

### 编译安装

```bash
# 1. 安装依赖
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env
sudo apt install -y cmake ninja-build protobuf-compiler libprotobuf-dev

# 2. 编译 dynolog
bash scripts/build.sh -t deb   # 或 -t rpm 或直接 bash scripts/build.sh

# 3. 安装 dynolog
dpkg -i --force-overwrite dynolog*.deb

# 4. 编译 mindstudio_monitor whl
chmod +x plugin/build.sh && ./plugin/build.sh
```

### 安装后配置

```bash
# 日志路径（可选）
export MSMONITOR_LOG_PATH=/tmp/msmonitor_log
```

---

## 三、快速入门

### 整体流程

```
1. 启动 Dynolog daemon
2. 配置 MSMONITOR_USE_DAEMON=1
3. 设置 LD_PRELOAD 加载 MSPTI
4. 拉起训练/推理任务
5. 用 Dyno 触发 npu-monitor 或 nputrace
```

### npu-monitor 快速使用

```bash
# 1. 启动 dynolog
dynolog --enable-ipc-monitor --certs-dir /home/server_certs

# 2. 配置环境变量
export MSMONITOR_USE_DAEMON=1

# 3. 设置 LD_PRELOAD
export LD_PRELOAD=<CANN_PATH>/lib64/libmspti.so

# 4. 拉起任务
bash run_ai_task.sh

# 5. 开启监控（30s 上报周期，Kernel 类型）
dyno --certs-dir /home/client_certs npu-monitor \
  --npu-monitor-start \
  --report-interval-s 30 \
  --mspti-activity-kind Kernel

# 6. 关闭监控
dyno --certs-dir /home/client_certs npu-monitor --npu-monitor-stop
```

### nputrace 快速使用

```bash
# 从第 10 个 step 开始采集，采集 2 个 step，自动解析，数据不精简
dyno --certs-dir /home/client_certs nputrace \
  --start-step 10 \
  --iterations 2 \
  --activities CPU,NPU \
  --analyse \
  --data-simplification false \
  --log-file /tmp/profile_data
```

---

## 四、Dynolog daemon

每节点只需启动一个，负责接收 Dyno 请求并触发采集。

### 启动方式

```bash
# 命令行启动
dynolog --enable-ipc-monitor --certs-dir /home/server_certs

# 或 systemd 启动
echo "--enable_ipc_monitor" | sudo tee -a /etc/dynolog.gflags
sudo systemctl start dynolog
```

### 参数说明

| 参数 | 说明 | 必选 |
|-----|------|:----:|
| `--enable-ipc-monitor` | 启用 IPC 监控功能 | N |
| `--port` | 监听端口，默认 1778 | N |
| `--certs-dir` | TLS 证书路径，`NO_CERTS` 表示不认证 | Y |
| `--metric_log_dir` | TensorBoard 数据落盘路径 | N |
| `--use_JSON` | JSON 格式记录 metric 日志 | N |

---

## 五、Dyno CLI

Dyno 是客户端，负责发送 RPC 请求到 Dynolog。

### 全局参数

| 参数 | 说明 | 必选 |
|-----|------|:----:|
| `--hostname` | Dynolog 主机名，默认 localhost | N |
| `--port` | Dynolog 端口，默认 1778 | N |
| `--certs-dir` | TLS 证书路径，`NO_CERTS` 表示不认证 | Y |

### 子命令

| 子命令 | 说明 |
|-----|------|
| `status` | 查询 nputrace / npu-monitor 执行状态 |
| `nputrace` | 触发 trace 数据采集 |
| `npu-monitor` | 触发 npu-monitor 监控 |
| `version` | 查询 Dynolog daemon 版本 |

---

## 六、npu-monitor 详解

轻量常驻后台，监控关键算子耗时，基于 MSPTI 实现。

### 核心参数

| 参数 | 说明 | 默认值 |
|-----|------|-------|
| `--npu-monitor-start` | 开启监控 | - |
| `--npu-monitor-stop` | 停止监控 | - |
| `--report-interval-s` | 数据上报周期（秒） | 60 |
| `--duration` | 采集时长（秒），0 表示不限制 | 0.0 |
| `--mspti-activity-kind` | 上报数据类型（逗号分隔） | Marker |
| `--log-file` | 数据落盘路径 | - |
| `--export-type` | 落盘格式：`DB` 或 `Jsonl` | DB |
| `--filter` | 按数据类型:数据名筛选（分号分隔） | - |

### 数据类型可选值

`Marker` / `Kernel` / `API` / `Hccl` / `Memory` / `MemSet` / `MemCpy` / `Communication` / `AclAPI` / `NodeAPI` / `RuntimeAPI`

### TensorBoard 可视化

```bash
pip install tensorboard
tensorboard --logdir=<metric_log_dir>
# 浏览器访问 http://localhost:6006
```

### 状态查询

```bash
dyno --certs-dir <CERT_DIR> status
# {"current_step":1,"npumonitor":"Idle","nputrace":"Ready","start_step":5,"stop_step":10}
```

**nputrace 状态**：Uninitialized → Idle → Ready → Running
**npumonitor 状态**：Uninitialized → Idle → Running

---

## 七、nputrace 详解

获取框架/CANN/device 详细 trace 数据，支持 MindStudio Insight 可视化。

### 核心参数

| 参数 | 必选 | 说明 |
|-----|:----:|------|
| `--start-step` | Y | 开始采集的迭代数，-1 表示从下一个 step 开始 |
| `--iterations` | Y | 采集的总迭代数 |
| `--log-file` | Y | 采集数据落盘路径 |
| `--activities` | N | 采集范围：`CPU` / `NPU`，默认 `CPU,NPU` |
| `--analyse` | N | 采集后自动解析 |
| `--async-mode` | N | 开启异步解析 |
| `--data-simplification` | N | 数据精简模式，默认 true |
| `--record-shapes` | N | 采集算子 InputShapes/InputTypes |
| `--profile-memory` | N | 采集算子内存信息 |
| `--with-stack` | N | 采集 Python 调用栈 |
| `--with-modules` | N | 采集 modules 层级的 Python 调用栈 |
| `--with-flops` | N | 采集算子 flops |
| `--l2-cache` | N | 采集 L2 Cache 数据 |
| `--op-attr` | N | 采集算子属性信息 |
| `--msprof-tx` | N | 采集 mstx 打点数据 |
| `--mstx-domain-include` | N | 采集指定 domain 范围 |
| `--mstx-domain-exclude` | N | 排除指定 domain 范围 |
| `--profiler-level` | N | 采集等级：Level_none / Level0 / Level1 / Level2 |
| `--aic-metrics` | N | AI Core 指标：`PipeUtilization` / `ArithmeticUtilization` / `Memory` 等 |
| `--export-type` | N | 导出格式：`Text`（json/csv/db）或 `Db`（仅 db） |
| `--host-sys` | N | Host 侧系统数据：`cpu` / `mem` / `disk` / `network` / `osrt` |
| `--sys-io` | N | NIC/ROCE 数据采集 |
| `--sys-interconnection` | N | HCCS/PCIe 片间带宽数据采集 |

### Profiler Level 说明

| Level | 说明 |
|-----|------|
| Level0 | 上层应用 + 底层 NPU + AI Core 算子信息 |
| Level1 | Level0 + CANN AscendCL 数据 + AI Core 性能指标 + `communication.json` |
| Level2 | Level1 + CANN Runtime 数据 + AI CPU 数据 |

### 使用约束

- `nputrace` 和 `npu-monitor` **不能同时开启**
- PyTorch 有效采集范围：`[start_step, stop_step)`（含 start_step，不含 stop_step）
- MindSpore 有效采集范围：`[start_step, stop_step]`（含两端）

---

## 八、Monitor API 详解

提供轻量化的 Python 接口，直接在模型脚本中采集性能数据。

### 核心接口

```python
from msmonitor import Monitor, ActivityKind

# 开启监控
monitor = Monitor()
monitor.start(kinds=[ActivityKind.API, ActivityKind.Kernel, ActivityKind.Marker])

# ... 模型运行代码 ...

# 停止监控
monitor.stop()

# 获取性能数据
result = monitor.get_result()
for kind, data in result.items():
    for item in data:
        print(f"kind: {kind}, name: {item.name}, duration: {item.endNs - item.startNs}ns")

# 保存为 Excel
monitor.save("monitor_result.xlsx")
```

### ActivityKind 可选类型

`Marker` / `Kernel` / `Communication` / `API` / `AclAPI` / `NodeAPI` / `RuntimeAPI`

### MindSpore 场景（DynamicProfilerMonitor）

```python
from mindspore.profiler import DynamicProfilerMonitor

dp = DynamicProfilerMonitor()
for i in range(step_num):
    train(model)
    dp.step()  # 每次训练后调用
```

---

## 九、API 参考（mindstudio_monitor）

### PyDynamicMonitorProxy（用户无需直接调用）

| 接口 | 说明 |
|-----|------|
| `init_dyno(npu_id)` | 向 Dynolog 发送注册请求 |
| `poll_dyno()` | 获取 Profiler 控制参数 |
| `enable_dyno_npu_monitor(cfg_map)` | 开启 MSPTI 监控 |
| `finalize_dyno()` | 释放资源 |
| `update_profiler_status(status)` | 上报 Profiler 状态 |

### Monitor API

| 接口 | 说明 |
|-----|------|
| `Monitor.start(kinds)` | 开启指定类型的性能数据采集 |
| `Monitor.stop()` | 停止采集 |
| `Monitor.get_result()` | 在线获取性能数据，返回 `Dict[ActivityKind, List[ActivityData]]` |
| `Monitor.save(file_path)` | 将数据保存为 Excel 文件 |

### 性能数据结构

**Marker**：`name` / `startNs` / `endNs` / `sourceKind` / `domain` / `pid` / `tid` / `deviceId` / `streamId`
**Kernel**：`name` / `startNs` / `endNs` / `deviceId` / `streamId` / `correlationId` / `type`
**Communication**：`name` / `startNs` / `endNs` / `deviceId` / `streamId` / `count` / `dataType` / `commName` / `algType` / `correlationId`
**API**：`name` / `startNs` / `endNs` / `pid` / `tid` / `correlationId`

---

## 十、常见问题（FAQ）

**Q: dyno CLI 发送 npu-monitor 命令后没有数据上报？**
A: 检查 LD_PRELOAD 是否正确设置了 `libmspti.so` 路径；检查 Dynolog 日志确认是否收到 RPC 请求。

**Q: npu-monitor 和 nputrace 可以同时使用吗？**
A: 不可以，两个功能互斥，不能同时开启。

**Q: TensorBoard 没有数据展示？**
A: 确认 Dynolog 启动时传入了 `--metric_log_dir` 参数；确认 `tensorboard --logdir` 路径正确。

**Q: 如何查看采集的 trace 数据？**
A: 使用 MindStudio Insight 工具打开 `.db` 文件（`--export-type Db`）进行可视化；或查看 `--log-file` 路径下的 `.json` / `.csv` 文件。

**Q: PyTorch 和 MindSpore 的采集范围有什么区别？**
A: PyTorch：`[start_step, stop_step)`；MindSpore：`[start_step, stop_step]`（含 stop_step）。MindSpore 没有 Ready 状态。

**Q: 数据落盘选择 DB 还是 Jsonl？**
A: DB 格式可使用 MindStudio Insight 可视化；Jsonl 格式每行一条完整 Json，支持大数据量场景，可通过环境变量调节 RingBuffer 大小和落盘策略。

---

## 十一、回答格式

当用户咨询 msMonitor 相关问题时，请按以下格式作答：

1. **确认场景**：npu-monitor / nputrace / Monitor API + PyTorch / MindSpore
2. **安装方式**：软件包 / 源码编译
3. **配置步骤**：Dynolog 启动 → 环境变量 → LD_PRELOAD → 任务拉起
4. **命令指导**：给出 `dynolog` / `dyno` 命令及关键参数
5. **结果解读**：TensorBoard / MindStudio Insight / Excel 数据的查看方式

---

## 附录：源码信息

- **仓库**：`https://gitcode.com/Ascend/msmonitor`
- **文档目录**：`docs/zh/`（overview / install_guide / quick_start / dynolog_instruct / dyno_instruct / npumonitor_instruct / nputrace_instruct / monitor_feature / mindspore_adapter_instruct / mindstudio_monitor_api_reference / faq / dir_structure）
- **版本**：8.3.0（2025-12-29）/ 8.1.0（2025-07-11）
- **贡献者**：华为公司昇腾计算 MindStudio 开发部
