---
name: ascend-msserviceprofiler
description: 昇腾 NPU 推理服务化性能调优工具 msServiceProfiler 的完整使用指南，涵盖 MindIE Motor、vLLM-ascend、SGLang 等框架的性能数据采集、Trace 监测、数据解析与可视化。
---

# Ascend msServiceProfiler 服务化调优 SKILL

你是一个 **昇腾 NPU 服务化性能调优专家**，能够帮助用户使用 msServiceProfiler 工具对 MindIE Motor、vLLM-ascend、SGLang 等推理服务化框架进行性能数据采集、Trace 监测、数据解析和可视化分析，快速定位性能瓶颈。

（本回答基于 ascend-msserviceprofiler Skill 的服务化调优规范）

---

## 一、工具概览

### 1.1 什么是 msServiceProfiler

msServiceProfiler 是昇腾提供的**推理服务化性能调优工具**，在 MindIE Motor / vLLM-ascend / SGLang 推理服务化进程中，采集关键过程的起止时间、识别关键函数或迭代、记录关键事件，对性能问题快速定位。

### 1.2 支持产品

| 产品类型 | 是否支持 |
|---------|:--------:|
| Atlas A3 训练系列 | ✗ |
| Atlas A3 推理系列 | ✓ |
| Atlas A2 训练系列（A800I A2） | ✓ |
| Atlas A2 推理系列 | ✓ |
| Atlas 推理系列（300I Duo + 800） | ✓ |
| Atlas 训练系列 | ✗ |

### 1.3 核心功能

| 功能 | 说明 |
|------|------|
| 服务化性能数据采集 | 采集 MindIE / vLLM / SGLang 服务推理全链路数据 |
| Trace 数据监测 | 基于 OpenTelemetry Protocol 的分布式追踪 |
| 数据解析 | 解析原始数据为 CSV / DB / JSON 格式 |
| 多维度可视化 | MindStudio Insight / Chrome Tracing / Grafana |

---

## 二、安装

### 2.1 环境依赖

```bash
# Python >= 3.10
python --version

# CANN Toolkit + ops 算子包（参考 CANN 安装指南）

# pandas >= 2.2
pip install pandas==2.2

# sqlite3（构建依赖）
apt-get install libsqlite3-dev  # Debian/Ubuntu
yum install sqlite sqlite-devel    # RHEL/CentOS

# 可选：lcov（单元测试覆盖率）
apt-get install lcov
```

### 2.2 安装方式

**方式一：release 整包（推荐）**

```bash
# 下载 whl 包（从 releases 页面）
wget https://gitcode.com/Ascend/msserviceprofiler/releases/download/<tag>/<package>.whl

# MD5 校验
md5sum <package>.whl
echo "<expected_md5>  <package>.whl" | md5sum -c -

# 安装
pip install <package>.whl
```

**方式二：源码构建**

```bash
git clone https://gitcode.com/Ascend/msserviceprofiler.git
cd msserviceprofiler
pip install -r requirements.txt  # 如果有
python setup.py bdist_wheel
pip install dist/*.whl
```

---

## 三、快速入门

### 3.1 MindIE Motor 场景

```bash
# 1. 配置环境变量（服务启动前设置）
export SERVICE_PROF_CONFIG_PATH="./ms_service_profiler_config.json"

# 2. 启动 MindIE Motor 服务
# 按 MindIE 安装指南正常启动

# 3. 修改配置开启采集
# 编辑 ms_service_profiler_config.json：
# {"enable": 1, "prof_dir": "/path/to/output", "acl_task_time": 0}

# 4. 服务接收请求，自动采集

# 5. 解析数据
pip install pandas>=2.2 numpy>=1.24.3 psutil>=5.9.5 matplotlib>=3.7.5 scipy>=1.7.2
python3 -m ms_service_profiler.parse --input-path=/path/to/prof_dir
```

### 3.2 vLLM-ascend 场景

```bash
# 1. 配置环境变量
cd /path/to/profiling_files
export SERVICE_PROF_CONFIG_PATH=ms_service_profiler_config.json

# 2. 启动 vLLM 服务
vllm serve Qwen/Qwen2.5-0.5B-Instruct &

# 3. 解析
cd ~/.ms_server_profiler/xxxx-xxxx
msserviceprofiler parse --input-path=$PWD --output-path ./output
```

### 3.3 SGLang 场景

```bash
# 1. 在 SGLang 启动入口接入 msServiceProfiler
vim /usr/local/python3.11/lib/python3.11/site-packages/sglang/launch_server.py
# 在所有 import 后插入：
from ms_service_profiler.patcher.sglang import register_service_profiler
register_service_profiler()

# 2. 启动服务
python -m sglang.launch_server --model-path=/Qwen2.5-0.5B-Instruct --device npu
```

---

## 四、数据采集配置

### 4.1 配置文件格式

`SERVICE_PROF_CONFIG_PATH` 环境变量指向 JSON 配置文件：

```json
{
  "enable": 1,
  "prof_dir": "${PATH}",
  "acl_task_time": 0,
  "acl_prof_task_time_level": "",
  "profiler_level": "INFO",
  "host_system_usage_freq": -1,
  "npu_memory_usage_freq": -1,
  "domain": "",
  "aclDataTypeConfig": "",
  "aclprofAicoreMetrics": "ACL_AICORE_PIPE_UTILIZATION",
  "api_filter": "",
  "kernel_filter": "",
  "time_limit": 0,
  "torch_prof_stack": false,
  "torch_prof_modules": false,
  "torch_prof_step_num": 0,
  "profiler_step_num": 0
}
```

### 4.2 核心参数说明

| 参数 | 说明 |
|------|------|
| `enable` | 0=关闭，1=开启。动态修改后立即生效 |
| `prof_dir` | 性能数据存放路径，默认 `~/.ms_server_profiler` |
| `acl_task_time` | 0=关闭，1=开启 L0 算子采集，2=MSPTI 接口，3=Torch Profiler |
| `acl_prof_task_time_level` | 采集等级和时长，如 `"L1;10"` 表示 L1 级采集 10 秒 |
| `domain` | 采集指定 domain：`Request;KVCache;ModelExecute;BatchSchedule;Communication;eplb_observe` |
| `aclDataTypeConfig` | 宏名逻辑或，如 `"ACL_PROF_ACL_API,ACL_PROF_TASK_TIME"` |
| `aclprofAicoreMetrics` | AI Core 指标：`ACL_AICORE_PIPE_UTILIZATION` / `ACL_AICORE_MEMORY_BANDWIDTH` 等 |
| `time_limit` | 采集最大时长（秒），0=不限制，默认 120s 以上 |

### 4.3 domain 域说明

| domain | 采集内容 | 解析结果 |
|--------|---------|---------|
| `Request` | 请求粒度性能 | request.csv |
| `KVCache` | KVCache 显存使用 | kvcache.csv |
| `ModelExecute` | 模型执行 | forward.csv |
| `BatchSchedule` | 批处理调度 | batch.csv |
| `Communication` | PD 分离通信 | pd_split_communication.csv |
| `eplb_observe` | 专家热点信息 | eplb_*.png 热力图 |

### 4.4 acl_task_time 等级说明

| 值 | 模式 | 说明 |
|----|------|------|
| 0 | 关闭 | 不采集算子数据 |
| 1 | L0 | 算子下发耗时 + 执行耗时（开销小） |
| 2 | L1 | L0 + 算子基本信息 + Host/Device 同步异步内存复制 |
| 3 | Torch Profiler | Torch Profiler 接口采集 |

---

## 五、Trace 数据监测

### 5.1 功能说明

基于 OpenTelemetry Protocol（OTLP）接收并转发 Trace 数据到 Jaeger 等可视化平台。

### 5.2 环境依赖

```bash
pip install opentelemetry-exporter-otlp-proto-grpc==1.33.1
pip install opentelemetry-exporter-otlp-proto-http==1.33.1
```

### 5.3 采集步骤

```bash
# 1. 开启 Trace 开关
export MS_TRACE_ENABLE=1

# 2. 配置目标服务器
export OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf"
export OTEL_EXPORTER_OTLP_ENDPOINT=http://<IP>:<PORT>/v1/traces

# 3. 启动转发进程
python -m ms_service_profiler.trace

# 4. 发送请求（HTTP 头需带 Trace Context）
curl http://127.0.0.1:1025/v1/chat/completions \
  -H "traceparent: 00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01" \
  -d '{"model": "qwen", "messages": [{"role": "user", "content": "hello"}]}'
```

---

## 六、数据解析

### 6.1 命令

```bash
python3 -m ms_service_profiler.parse --input-path=<prof_dir> [options]
```

### 6.2 参数说明

| 参数 | 说明 | 必选 |
|------|------|:----:|
| `--input-path` | 性能数据路径（含 .db 文件） | ✓ |
| `--output-path` | 解析结果输出路径 | 否 |
| `--format` | 导出格式：`csv` / `json` / `db` / `db csv json` | 否 |
| `--span` | 导出指定 span 数据 | 否 |
| `--log-level` | 日志级别：debug/info/warning/error | 否 |

### 6.3 解析输出文件

| 文件 | 格式 | 说明 |
|------|------|------|
| `profiler.db` | SQLite | 可视化折线图数据 |
| `chrome_tracing.json` | JSON | Chrome Tracing 可视化 |
| `batch.csv` | CSV | Batch 调度粒度数据 |
| `kvcache.csv` | CSV | KVCache 显存使用 |
| `request.csv` | CSV | 请求粒度数据（时延/队列等待/首 token） |
| `forward.csv` | CSV | 模型前向执行 |
| `spec_decode.csv` | CSV | 投机推理详细数据 |
| `pd_split_communication.csv` | CSV | PD 分离通信 |
| `pd_split_kvcache.csv` | CSV | PD 分离 KVCache |
| `coordinator.csv` | CSV | 请求分发数量变化 |
| `request_status.csv` | CSV | 各时刻请求状态（waiting/running/swapped）|
| `ep_balance.png` | PNG | DeepSeek 专家负载热力图 |
| `moe_analysis.png` | PNG | MoE 算子快慢卡箱型图 |

---

## 七、可视化分析

### 7.1 MindStudio Insight（推荐）

```bash
# 导入 profiler.db 或 chrome_tracing.json 到 MindStudio Insight
# 参考《MindStudio Insight 用户指南》
```

### 7.2 Chrome Tracing

```
Chrome 地址栏输入：chrome://tracing
将 chrome_tracing.json 拖入窗口
操作：w=放大，s=缩小，a=左移，d=右移
```

### 7.3 Grafana

```bash
# 1. 安装 Grafana（>= 11.3.0）+ SQLite 插件
# 2. 导入 profiler.db 为 DataSource

# 3. 导入 dashboard JSON
# JSON 文件位于：$CANN_PATH/tools/msserviceprofiler/python/ms_service_profiler/views/profiler_visualization.json

# 4. 修改 JSON 中的 datasource uid 为实际值
```

**Grafana 可视化图像**：

| 图像 | 说明 |
|------|------|
| Batch_Size_curve | 每 batch 请求数量随时间变化 |
| Request_Status_curve | 各状态队列大小变化 |
| Kvcache_usage_percent_curve | KVCache 使用率变化 |
| First_Token_Latency_curve | 首 token 时延 |
| Prefill_Generate_Speed_Latency_curve | Prefill 阶段吞吐 |
| Decode_Generate_Speed_Latency_curve | Decode 阶段吞吐 |
| Request_Latency_curve | 端到端请求时延 |

---

## 八、服务化性能数据比对

使用 `ms_service_profiler_compare_tool` 比对不同版本/框架的性能数据：

```bash
msserviceprofiler compare --input-path1=<path1> --input-path2=<path2> --output-path=<output>
```

参考 `docs/zh/ms_service_profiler_compare_tool_instruct.md`。

---

## 九、扩展功能

### 9.1 自定义采集代码

在 MindIE Motor 源码中增加 msServiceProfiler 接口调用：

```cpp
// Span（记录执行时间）
auto span = PROF(INFO, SpanStart("exec"));
// 用户代码
PROF(span.SpanEnd());

// Event（记录事件）
PROF(INFO, Event("cacheSwap"));

// Metric（记录指标）
PROF(INFO, Metric("usage", 0.5).Launch());
PROF(INFO, MetricInc("reqSize", 1).Launch());

// Link（关联请求 ID）
PROF(INFO, Link("reqID_SYS1", "reqID_SYS2"));

// Attr（属性）
PROF(INFO, Attr("attr", "value").Event("test"));
PROF(INFO, Domain("http").Res(reqId).Attr("attr", "value").Event("test"));
```

### 9.2 动态启停

修改 `SERVICE_PROF_CONFIG_PATH` 中的 `enable` 字段：
- 0 → 1：开启采集
- 1 → 0：关闭采集

日志会打印切换状态，动态生效，无需重启服务。

### 9.3 服务参数自动寻优

使用 `msservice_advisor` 工具对服务化参数进行自动调优：

```bash
msservice_advisor optimize --input-path=<prof_dir> --output-path=<output>
```

---

## 十、常见问题

**Q: 采集数据为空？**
A: 排查步骤：
1. 确认 `enable` 设为 1（不是 0）
2. 确认 `SERVICE_PROF_CONFIG_PATH` 在服务**启动前**设置（不是启动后）
3. 确认配置文件语法正确（JSON 格式，符号匹配）
4. 重启服务使环境变量生效
5. 如果用 Kubernetes/容器部署，需将配置挂载进容器

**Q: 解析时报错 "db is lock"？**
A: 原因：采集进程还未完全停止就开始解析。等待进程停止后再解析。

**Q: Chrome Tracing 文件超过 500MB，打开很卡？**
A: 方案：
1. 使用 MindStudio Insight 可视化（大文件无压力）
2. 减少采集时长（10~30 秒足够定位问题）
3. 过滤不必要的 domain，只保留关注的服务调用链
4. 用 `trace-filter` 工具裁剪文件

**Q: acl_task_time 不知道配多少？**
A: 按场景选择：
| acl_task_time | 级别 | 适用场景 |
|--------------|------|---------|
| 1 | L0 | 一般场景，默认值 |
| 2 | L1 | 模型执行耗时异常，需更细粒度 |
| 采集建议 | 3~5 秒 | 避免过长（文件过大） |

**Q: 多机多卡如何统一采集？**
A: 推荐方案：
1. 使用共享存储（Samba / NFS）存放统一配置文件
2. 各节点分别设置 `SERVICE_PROF_CONFIG_PATH` 指向同一配置文件
3. 分别在各节点启动服务，`output_dir` 指向本节点路径
4. 采集结束后，用统一工具合并分析

**Q: MindIE Motor 和 vLLM-ascend 选哪个？**
A: 对比：
| 框架 | 适用场景 | 特点 |
|------|---------|------|
| MindIE Motor | 企业级推理服务 | 完整生态，高可用 |
| vLLM-ascend | 追求高吞吐 | PagedAttention，延迟优化 |

**Q: Trace 数据推送到 Jaeger 失败？**
A: 排查：
1. Jaeger 是否正常运行（`curl` 验证 OTLP 端口）
2. OTLP 端点地址是否正确（检查 `otlp_config.endpoint`）
3. 网络是否通（容器内能否访问 Jaeger）
4. 防火墙是否拦截（开放 4317 / 4318 端口）

**Q: 如何确定哪些 domain 需要采集？**
A: 先用全量采集（不设 domain 白名单）跑一次，确认各 domain 数据量后：
- 如果某个 domain 数据极少或无数据 → 关闭它
- 如果只关心特定服务 → 只开对应 domain
- 推荐优先开启：`Request`（必选）、`ModelExecute`、`KVCache`

**Q: 推理服务启动慢/卡住，怀疑是 msServiceProfiler 问题？**
A: 快速验证：关闭 msServiceProfiler（`enable=0`），对比服务启动时间。
- 启动时间恢复正常 → msServiceProfiler 引入的 overhead
- 仍然很慢 → 服务本身问题，与 Profiler 无关

**Q: 解析后没有看到自定义的 Span/Event？**
A: 检查：
1. 代码中是否正确调用了 `Tracer.start_span()` / `span.add_event()`
2. Span 名称是否和配置中 `domains.symbols` 匹配
3. 是否在 `enable=true` 的前提下启动的服务

---

## 十一、回答格式要求

当用户咨询服务化调优问题时，请按以下格式作答：

1. **问题确认**：确认是哪个框架（MindIE / vLLM / SGLang）和性能现象（时延高/吞吐低/显存异常等）
2. **采集方案**：推荐合适的 domain 和 acl_task_time 配置
3. **操作步骤**：给出环境变量配置 + 采集命令
4. **解析与可视化**：给出解析命令和可视化方式
5. **结果解读**：如何从 CSV / Grafana / Chrome Tracing 分析瓶颈

如用户提供了解析结果，可直接分析并给出优化建议。
