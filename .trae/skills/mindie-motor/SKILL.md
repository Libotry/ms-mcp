---
name: mindie-motor
description: MindIE Motor PD 分离推理框架的完整使用指南，覆盖 PD 分离架构、单机/多机部署、Coordinator/Controller 组件配置、服务化接口调用、FAQ 故障排查和性能指标解读。
---

# MindIE Motor SKILL

你是一个 **MindIE Motor 推理框架专家**，能够帮助用户理解和使用 MindIE Motor 完成 PD 分离推理服务的部署、调试和故障排查。

---

## 一、工具概览

### 1.1 什么是 MindIE Motor

**MindIE Motor** 是面向 LLM PD 分离推理的请求调度框架，通过开放、可扩展的推理服务化平台架构提供推理服务化能力，向下对接 MindIE LLM，满足大语言模型高性能推理需求。

### 1.2 核心能力

| 能力 | 说明 |
|-----|------|
| **PD 分离调度** | 将 Prefill 和 Decode 阶段分离开，实现负载均衡 |
| **RAS** | 可靠性、可用性、可服务性（故障管理 + 实例自愈） |
| **多框架兼容** | 支持 vLLM / TGI / Triton / OpenAI 接口 |
| **多节点集群** | 支持单机和多机 PD 分离部署 |

### 1.3 核心组件

| 组件 | 作用 |
|-----|------|
| **Coordinator** | 请求入口，负载均衡调度，请求监控 |
| **Controller** | 集群状态管控，故障管理，实例身份决策 |
| **MindIE LLM** | 单个模型服务实例（Prefill/Decode）|
| **ClusterD** | 故障诊断，全局 RankTable 下发 |

---

## 二、PD 分离原理

### Prefill vs Decode

| 阶段 | 特点 | 计算性质 |
|-----|------|---------|
| **Prefill** | 处理初始 Prompt，生成初始隐藏状态 | 计算密集，单次 |
| **Decode** | 基于隐藏状态逐步生成 token | 计算稀疏，迭代 |

### PD 分离优势

- **资源利用优化**：Prefill 计算密集，Decode 稀疏，分离后更好利用 NPU
- **吞吐量提升**：Prefill 和 Decode 同时处理不同请求
- **延迟降低**：减少两类请求互相干扰

### 支持的模型

| 模型系列 | 说明 |
|---------|------|
| LLaMA3-8B | PD 单机/多机 |
| Qwen2.5-7B | PD 单机/多机 |
| Qwen3-8B | PD 单机/多机 |
| DeepSeek 系列 | PD 多机 |

---

## 三、部署模式

### 3.1 单机 PD 分离部署

- Controller / Coordinator / Server 全部运行在**同一个 Pod 内**
- 适用于单台服务器场景
- 通过 K8s Service 开放推理入口

### 3.2 多机 PD 分离部署

- Controller / Coordinator / Server **分别运行在独立 Pod 内**
- 适用于多台服务器集群场景
- P 节点和 D 节点必须**相同型号、相同 NPU 卡数**

### 3.3 硬件环境

| 服务器 | 内存 | 支持部署模式 |
|--------|-----|------------|
| Atlas 800I A2 | 32GB / 64GB | 单机 + 多机 PD |
| Atlas 800I A3 | 64GB | 单机 PD |

---

## 四、服务部署前提条件

### 环境要求

- **Python**：3.10（必须，不支持其他版本）
- **CANN**：配套版本 CANN Toolkit + ops 算子包
- **NPU**：Ascend NPU 驱动正常
- **HTTPS**：生产环境必须开启 HTTPS（HTTP 有安全风险）

### 部署前检查

```bash
# 1. 确认 Python 版本（必须是 3.10）
python --version   # 必须显示 3.10.x

# 2. 确认 pip 对应 Python 3.10
pip --version

# 3. 确认 NPU 驱动正常
npu-smi

# 4. 建议使用预检工具校验配置文件
# 参考 msprechecker 工具
```

---

## 五、服务启动

### 启动方式

```bash
# 方式一（推荐）：后台进程方式启动
cd /{MindIE安装目录}/latest/mindie-service
nohup ./bin/mindieservice_daemon > output.log 2>&1 &

# 方式二：直接启动
./bin/mindieservice_daemon

# 验证启动成功
# 查看 output.log 是否包含：Daemon start success!
```

### 注意事项

> ⚠️ bin 目录权限为 550，没有写权限。推理过程中会在**当前目录**生成 `kernel_meta` 文件夹，因此不能在 bin 目录内启动，必须在有写权限的目录下启动。

> ⚠️ 如切换用户，先执行 `rm -f /dev/shm/*` 删除共享文件，避免权限问题导致推理失败。

---

## 六、接口调用

### 基础接口

```bash
# 列出当前模型
curl -X GET https://127.0.0.1:1025/v1/models \
  --cacert ca.pem --cert client.pem --key client.key.pem

# v1/chat 流式推理
curl -X POST https://127.0.0.1:1025/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "your-model", "messages": [{"role": "user", "content": "hello"}], "stream": true}'
```

### 接口说明

| 参数 | 说明 |
|------|------|
| `--cacert` | CA 证书路径 |
| `--cert` | 客户端证书路径 |
| `--key` | 客户端私钥路径 |

---

## 七、组件配置

### Coordinator 配置

| 参数 | 说明 |
|------|------|
| `ipAddress` | 服务监听 IP |
| `port` | 服务监听端口 |
| `Endpoint` | RESTful 接口（如 OpenAI 接口）|
| `Metrics` | 整体 Metrics 统计汇总 |
| `LoadBalancer` | 负载均衡策略 |

### Controller 配置

| 参数 | 说明 |
|------|------|
| `FaultManager` | 故障检测、隔离、自愈 |
| `InsManager` | PD 实例身份分配和调整 |
| `InsMonitor` | 心跳、负载监控 |

---

## 八、PD 分离约束

### 单机 PD 限制

- 仅 Atlas 800I A2 / A3 支持
- P、D 节点 NPU 卡数必须相同
- 不支持与 Prefix Cache、稀疏量化、KV Cache int8 量化同时使用
- 暂不支持 `n`、`best_of`、`use_beam_search`、`logprobs` 等多序列参数

### 多机 PD 限制

- 仅 Atlas 800I A2 支持
- NPU 网口必须互联（200Gbps）
- 不支持 Multi LoRA、并行解码、SplitFuse、Prefix Cache、Function Call
- P 节点与 D 节点必须是相同型号、相同 NPU 卡数

---

## 九、性能指标

### AISBench 评测指标

| 指标 | 全称 | 说明 |
|------|------|------|
| TTFT | Time To First Token | 首 token 延迟 |
| ITL | Inter-token Latency | token 间隔延迟 |
| TPOT | Time Per Output Token | 每输出 token 延迟 |
| E2EL | End-to-End Latency | 端到端延迟 |
| PrefillTokenThroughput | - | prefill 阶段吞吐 |
| OutputTokenThroughput | - | decode 阶段吞吐 |
| Concurrency | - | 平均并发数 |
| Request Throughput | - | 请求吞吐量 |

### 性能/精度测试

使用 AISBench 工具进行评测，参考 ais-bench SKILL。

---

## 十、常见问题

**Q: 出现 "LLMPythonModel initializes fail"？**
A: ibis 缺少 Python 依赖。进入 `/_Service安装路径_/logs` 目录查看 Python 日志，根据报错安装缺失依赖。

**Q: 加载模型时出现 "out of memory"？**
A: 权重太大，内存不足。将 config.json 中 `ModelConfig` 的 `npuMemSize` 调小（如设为 8）。

**Q: 出现 "atb_llm.runner 无法 import"？**
A: Python 版本不是配套的 3.10。用 `python --version` 和 `pip --version` 确认；参考 FAQ 重新配置环境。

**Q: 切换用户后推理失败？**
A: 执行 `rm -f /dev/shm/*` 删除之前用户的共享文件，解决权限问题。

**Q: 模型加载耗时过长（大模型 > 1300B）？**
A: 参考 FAQ 中的"加载大模型耗时过长"章节优化。

**Q: HTTP 请求报错？**
A: HTTP 缺乏安全机制，建议生产环境使用 HTTPS。检查证书和 key 文件路径是否正确。

**Q: 多机 PD 部署时请求路由错误？**
A: 检查 Controller / Coordinator / Server 的 IP 配置是否在统一网段；确认 ClusterD 的 RankTable 是否正确下发。

**Q: PD 分离后吞吐反而下降？**
A: 确认 Prefill 和 Decode 实例数配比是否合理；检查 PD 请求调度是否正确路由到对应实例。

**Q: Controller 报故障但实例实际正常？**
A: 检查网络互通性；确认心跳配置是否正确；查看 Controller 日志定位误报原因。

**Q: 服务启动成功但无法接受请求？**
A: 检查 Coordinator 的 `ipAddress` 和 `port`；用 `curl` 本地验证服务是否可达；检查 K8s Service 是否正确暴露端口。

---

## 十一、回答格式

当用户咨询 MindIE Motor 问题时，请按以下格式作答：

1. **确认场景**：单机/多机 PD 部署 + 具体组件（Coordinator/Controller）
2. **配置建议**：给出关键配置参数
3. **操作步骤**：启动命令 / API 调用示例
4. **故障排查**：如有问题，给出排查方向和关键日志位置
</parameter>
