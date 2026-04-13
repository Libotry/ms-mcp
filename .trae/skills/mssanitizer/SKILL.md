---
name: mssanitizer
description: MindStudio Sanitizer（msSanitizer）昇腾 AI 算子异常检测工具完整指南，覆盖内存检测、竞争检测、未初始化检测、同步检测四种能力，支持 Kernel 直调、aclnn API、PyTorch、Triton 等多种场景，包含安装配置、编译选项、FAQ 故障排查和 API 参考。
---

# msSanitizer SKILL

你是一个 **msSanitizer 昇腾算子异常检测工具专家**，能够帮助用户理解和使用 msSanitizer 完成昇腾 AI 处理器的算子异常检测、报告解读和故障排查。

---

## 一、工具概览

### 什么是 msSanitizer

**MindStudio Sanitizer**（msSanitizer）是面向昇腾 AI 处理器的单算子异常检测工具，提供四大检测能力：

| 检测工具 | 解决的问题 | 快速启用命令 |
|---------|---------|------------|
| `memcheck`（默认） | 内存越界、多核踩踏、非对齐访问、内存泄漏、非法释放、分配未使用 | `mssanitizer --tool=memcheck ./application` |
| `racecheck` | 数据竞争（WAW / WAR / RAW） | `mssanitizer --tool=racecheck ./application` |
| `initcheck` | 读取未初始化内存导致的脏数据 | `mssanitizer --tool=initcheck ./application` |
| `synccheck` | SetFlag / WaitFlag 未配对导致的同步失败 | `mssanitizer --tool=synccheck ./application` |

### 适用场景

| 开发场景 | 参考章节 |
|---------|---------|
| 通过 `<<<>>>` 直接调用 Kernel 函数 | Kernel 直调场景 |
| 调用 `aclnn` 系列单算子 API | 单算子 API 调用场景 |
| PyTorch 框架接入算子（TorchAir 图模式） | PyTorch 框架适配场景 |
| Triton-Ascend 算子 | Triton 算子调用场景 |

### 建议检测顺序

> 💡 建议先运行 **memcheck**（内存检测），确认算子程序无内存异常后，再按需运行 racecheck / initcheck / synccheck。

---

## 二、安装指南

### 方式一：二进制安装（CANN 包）

msSanitizer 集成在 CANN 包中发布，请参考 [CANN 安装官方文档](https://www.hiascend.com/document/detail/zh/canncommercial/850/softwareinst) 或使用 [CANN 官方容器镜像](https://www.hiascend.com/developer/ascendhub/detail/17da20d1c2b6493cb38765adeba85884)。

### 方式二：源码安装

```bash
# 1. 下载源码
git clone https://gitcode.com/Ascend/mssanitizer.git

# 2. 准备开发环境（参考 https://gitcode.com/Ascend/msot/blob/master/docs/zh/common/dev_env_setup.md）

# 3. 一键编译打包
python build.py

# 4. 安装
cd output
chmod +x mindstudio-sanitizer_*.run
./mindstudio-sanitizer_*.run --run

# 卸载
./mindstudio-sanitizer_*.run --uninstall
```

### 方式三：分步骤编译

```bash
# 下载依赖
python download_dependencies.py

# 编译
mkdir build
cd build
cmake ../cmake
make -j$(nproc)

# debug 版本（支持 gdb 断点调试）
cmake ../cmake -DCMAKE_BUILD_TYPE=Debug
```

### 安装后配置

```bash
export ASCEND_HOME_PATH=$HOME/Ascend  # 或自定义安装路径
export PATH=$ASCEND_HOME_PATH/bin:$PATH
export LD_LIBRARY_PATH=$ASCEND_HOME_PATH/lib64:$LD_LIBRARY_PATH
```

---

## 三、算子编译选项配置

### 快速定界（不修改编译选项）

- **指令检测范围**：仅 GM 相关搬运指令
- **异常检测范围**：非法读写、非对齐访问（不显示调用栈）
- **适用场景**：快速定界算子内存异常

> ⚠️ 限制：算子优化等级需为 O2，链接阶段需加 `-q` 保留符号重定位信息；不适用 Atlas 推理系列；仅适用于 Kernel 直调场景。

### 全量检测（添加编译选项）

需要根据不同场景配置编译选项：

#### 模板库场景

修改 `examples/CMakeLists.txt`：
```text
set(BISHENG_COMPILER_OPTIONS -g --cce-enable-sanitizer)
```

#### 内核调用符场景（Kernel Launch）

编辑 `cmake/npu/CMakeLists.txt`：
```cmake
target_compile_options(${smoke_testcase}_npu PRIVATE
    -O2
    -std=c++17
    --cce-enable-sanitizer
    -g
)
```

编辑 `cmake/Modules/CMakeCCEInformation.cmake`：
```cmake
if(NOT CMAKE_CCE_LINK_EXECUTABLE)
set(CMAKE_CCE_LINK_EXECUTABLE
    "<CMAKE_CCE_COMPILER> ${CMAKE_LIBRARY_CREATE_CCE_FLAGS} ${_CMAKE_COMPILE_AS_CCE_FLAG} <FLAGS> <CMAKE_CCE_LINK_FLAGS> <LINK_FLAGS> <OBJECTS> -o <TARGET> <LINK_LIBRARIES>${__IMPLICIT_LINKS}")
endif()
```

链接阶段需增加：
```cmake
target_link_options(${smoke_testcase}_npu PRIVATE
    --cce-fatobj-link
    --cce-enable-sanitizer
)
```

> ⚠️ `--cce-enable-sanitizer` 和 `-O0` 同时开启时需增加 `--cce-ignore-always-inline=false`

#### msOpGen 算子工程场景

编辑 `op_kernel/CMakeLists.txt`：
```cmake
add_ops_compile_options(ALL OPTIONS -sanitizer)
```

#### Triton 算子调用场景

```bash
export TRITON_ENABLE_SANITIZER=1
```

---

## 四、使用指南

### 4.1 Kernel 直调场景

```bash
mssanitizer --tool=memcheck ./add_npu
```

> ⚠️ PyTorch 内存池场景下检测前需关闭内存池：
> ```bash
> export PYTORCH_NO_NPU_MEMORY_CACHING=1
> ```

### 4.2 单算子 API 调用场景（aclnn）

```bash
mssanitizer --tool=memcheck bash run.sh
```

> ⚠️ 调用 aclnn API 时需通过 `aclInit` 传入 `acl.json`（内容为 `{"dump":{"dump_scene":"lite_exception"}}`）以保证内存检测准确性。

### 4.3 PyTorch 框架场景

```bash
mssanitizer --tool=memcheck python your_script.py
```

- 仅支持不添加编译选项的图模式检测
- 需禁用内存池：
  ```bash
  export PYTORCH_NO_NPU_MEMORY_CACHING=1
  ```

### 4.4 Triton 算子场景

```bash
export TRITON_ALWAYS_COMPILE=1
export PYTORCH_NO_NPU_MEMORY_CACHING=1
mssanitizer -t memcheck -- python sample.py
```

> ⚠️ 不支持 Atlas 推理系列产品。

### 4.5 CANN 软件栈内存检测

```bash
# Device 侧内存泄漏检测
mssanitizer --check-device-heap=yes --leak-check=yes ./add_npu

# ACL 层内存泄漏检测
mssanitizer --check-cann-heap=yes --leak-check=yes ./add_npu
```

> ⚠️ Device 侧和 CANN 软件栈检测不能同时使能。

---

## 五、命令与参数参考

### 通用参数

| 参数 | 作用 | 示例 |
|-----|------|------|
| `-t, --tool` | 指定检测子工具 | `-t racecheck` |
| `--leak-check=yes` | 开启内存泄漏检测 | `--leak-check=yes` |
| `--check-unused-memory=yes` | 开启分配内存未使用检测 | `--check-unused-memory=yes` |
| `--log-file` | 将报告输出到文件 | `--log-file=result.log` |
| `--kernel-name` | 只检测指定名称算子（支持模糊匹配） | `--kernel-name="add"` |
| `--block-id` | 单 block 调试模式 | `--block-id=0` |
| `--full-backtrace=yes` | 显示完整调用栈 | `--full-backtrace=yes` |
| `--log-level` | 报告输出等级（info/warn/error） | `--log-level=warn` |
| `--cache-size` | 单 block 的 GM 内存大小（MB） | `--cache-size=200` |
| `--check-device-heap=yes` | 使能 Device 侧内存检测 | `--check-device-heap=yes` |
| `--check-cann-heap=yes` | 使能 CANN 软件栈内存检测 | `--check-cann-heap=yes` |

### 检测功能组合

```bash
# 多种检测同时开启
mssanitizer -t memcheck -t racecheck ./application

# 默认等价于
mssanitizer -t memcheck ./application
```

---

## 六、异常报告解读

### 报告级别说明

| 级别 | 说明 |
|-----|------|
| **WARNING** | 不确定风险，如多核踩踏、内存分配未使用等 |
| **ERROR** | 确定性错误，如非法读写、内存泄漏、非对齐访问、未初始化、竞争异常等 |

### 6.1 内存检测异常

#### 非法读写
```
====== ERROR: illegal read of size 224
======    at 0x12c0c0015000 on GM in add_custom_kernel
======    in block aiv(0) on device 0
======    code in pc current 0x77c (serialNo:10)
======    #0 .../kernel_operator_data_copy_impl.h:58:9
======    #1 .../inner_kernel_operator_data_copy_intf.cppm:58:9
======    #2 .../inner_kernel_operator_data_copy_intf.cppm:443:5
======    #3 add_custom.cpp:18:5
```

#### 多核踩踏
```
====== WARNING: out of bounds of size 256
======    at 0x12c0c00150fc on GM when writing data in add_custom_kernel
======    in block aiv(9) on device 0
======    code in pc current 0x7b8 (serialNo:22)
======    #0 .../kernel_operator_data_copy_impl.h:103:9
======    #1 .../inner_kernel_operator_data_copy_intf.cppm:155:9
======    #2 add_custom.cpp:21:5
```

#### 非对齐访问
```
====== ERROR: misaligned access of size 13
======    at 0x6 on UB in add_custom_kernel
======    in block aiv(0) on device 0
```

#### 内存泄漏
```
====== ERROR: LeakCheck: detected memory leaks
======    Direct leak of 100 byte(s)
======      at 0x124080013000 on GM allocated in add_custom.cpp:14 (serialNo:37)
======    Direct leak of 1000 byte(s)
======      at 0x124080014000 on GM allocated in add_custom.cpp:15 (serialNo:55)
====== SUMMARY: 1100 byte(s) leaked in 2 allocation(s)
```

#### 非法释放
```
====== ERROR: illegal free()
======    at 0x124080013000 on GM
======    code in add_custom.cpp:84 (serialNo:63)
```

### 6.2 竞争检测异常

#### RAW 竞争示例
```
====== ERROR: Potential RAW hazard detected at GM in kernel_float on device 0:
======    PIPE_MTE2 Write at RAW()+0x0 in block 0 (aiv) on device 0 at pc current 0xa98 (serialNo:14)
======    #0 .../kernel_operator_data_copy_impl.h:58:9
======    #1 .../inner_kernel_operator_data_copy_intf.cppm:58:9
======    #2 add_custom.cpp:17:5
======    PIPE_MTE3 Read at RAW()+0x0 in block 0 (aiv) on device 0 at pc current 0xad4 (serialNo:17)
======    #0 .../kernel_operator_data_copy_impl.h:103:9
======    #1 .../inner_kernel_operator_data_copy_intf.cppm:155:9
======    #2 add_custom.cpp:22:5
```

### 6.3 未初始化检测异常
```
====== ERROR: uninitialized read of size 224
======    at 0x12c0c0015000 on GM in add_custom_kernel
======    in block aiv(0) on device 0
======    code in pc current 0x77c (serialNo:10)
======    #0 add_custom.cpp:18:5
```

### 6.4 同步检测异常
```
====== WARNING: Unpaired set_flag instructions detected
======    from PIPE_S to PIPE_MTE3 in kernel
======    in block aiv(0) on device 1
======    code in pc current 0x2c94 (serialNo:31)
======    #0 kernel.cpp:26:9
```

---

## 七、API 参考

### sanitizer 接口（上报代码行号）

将 `acl/acl.h` 替换为 `${ASCEND_HOME_PATH}/tools/mssanitizer/include/acl/acl.h`，链接 `libascend_acl_hook.so`，重新编译后可定位到具体代码行。

| 接口 | 对应 ACL 接口 | 功能 |
|-----|-------------|------|
| `sanitizerRtMalloc` | `aclrtMalloc` | 分配内存并上报分配位置 |
| `sanitizerRtFree` | `aclrtFree` | 释放内存并上报释放位置 |
| `sanitizerRtMemset` | `aclrtMemset` | 初始化内存并上报位置 |
| `sanitizerRtMemcpy` | `aclrtMemcpy` | 拷贝内存并上报位置 |
| `sanitizerRtMemcpyAsync` | `aclrtMemcpyAsync` | 异步拷贝内存并上报位置 |
| `sanitizerReportMalloc` | - | 手动上报 GM 内存分配 |
| `sanitizerReportFree` | - | 手动上报 GM 内存释放 |

### mstx 扩展接口（内存池精确检测）

用于自定义算子内存池地址范围，实现更精确的内存检测：

| 接口 | 功能 |
|-----|------|
| `mstxDomainCreateA` | 创建域 |
| `mstxMemHeapRegister` | 注册内存池 |
| `mstxMemHeapUnregister` | 注销内存池 |
| `mstxMemRegionsRegister` | 注册内存池二次分配 |
| `mstxMemRegionsUnregister` | 注销内存池二次分配 |

---

## 八、架构简介

### 四大模块

| 模块 | 职责 |
|-----|------|
| **框架模块（Framework）** | 命令行解析、进程拉起、进程间通信 |
| **运行时模块（Runtime）** | 劫持运行时接口，收集行为数据（LD_PRELOAD） |
| **信息处理模块（Processor）** | 执行检测算法，生成异常报告 |
| **检测插件模块（Plugin）** | 编译器插桩，提供静态/动态插桩能力 |

### 技术要点

- **进程间通信**：Unix Domain Socket（全双工、多客户端）
- **插桩方式**：静态插桩（编译期，完整调用栈）+ 动态插桩（运行时，无需重编译）
- **检测并行**：生产者-消费者模型，每种 ToolType 独立消费者线程

---

## 九、限制与注意事项

1. msSanitizer 不支持多线程算子及使用掩码的向量类计算指令检测
2. 启用 `--check-device-heap` 或 `--check-cann-heap` 后不再对 Kernel 内部检测
3. Device 侧和 CANN 软件栈内存检测不可同时使能
4. 使用 sanitizer API 头文件编译的程序仅适用于 ACL 接口的泄漏检测
5. 建议使用普通用户权限安装执行，不要用 root
6. 生成的 `.run` 包需与 msSanitizer 工具配套使用，不建议单独使用

---

## 十、常见问题（FAQ）

**Q: 异常报告中文件名和行号显示为 `<unknown>:0`？**
A: 
- 启用 `--check-cann-heap=yes` 时：需引入 Sanitizer API 头文件并重新编译（参见基础案例 > 检测 CANN 软件栈内存）
- 算子检测场景：可能是未启用 `-g` 编译选项

**Q: 文件名显示正确但行号显示为 `0`？**
A: 使用了 `-O2` 或 `-O3` 优化选项导致代码行变化，使用 `-O0` 禁用编译器优化。

**Q: 编译时报错 `InputSection too large`？**
A: 算子代码段过大。增加编译选项：
```cmake
-Xaicore-start -mcmodel=large -mllvm -cce-aicore-relax -Xaicore-end
```

**Q: 工具提示 `--cache-size` 异常？**
A: 算子执行信息大小超过默认 GM 内存（100MB）。按提示调整 `--cache-size` 值重新运行。

**Q: 编译时执行 make 没有生成 .run 包？**
A: cmake 命令用错了。使用 `cmake ../cmake` 而不是 `cmake ..`，后者只编译不打包。

**Q: PyTorch 场景检测结果不准确？**
A: 需关闭 PyTorch 内存池：`export PYTORCH_NO_NPU_MEMORY_CACHING=1`

**Q: Triton 算子检测失败？**
A: 确保配置 `TRITON_ALWAYS_COMPILE=1` 和 `PYTORCH_NO_NPU_MEMORY_CACHING=1`，且不支持 Atlas 推理系列。

**Q: 如何定位内存泄漏的具体代码行？**
A: 将用户代码中的 `#include <acl/acl.h>` 替换为工具提供的 `acl.h`，链接 `libascend_acl_hook.so`，重新编译后再检测。

**Q: 竞争检测无异常但算子存在竞争现象？**
A: 可能是前序算子存在多余 SetFlag 指令导致后续算子同步配对错误，使用 `synccheck` 对前序算子进行检查。

---

## 十一、回答格式

当用户咨询 msSanitizer 相关问题时，请按以下格式作答：

1. **确认场景**：memcheck / racecheck / initcheck / synccheck + 具体调用方式
2. **检测命令**：给出正确的 `mssanitizer` 启动命令
3. **配置要点**：编译选项、环境变量、acl.json 等前置条件
4. **报告解读**：如果已有异常报告，给出异常原因和修复方向
5. **故障排查**：如有问题，给出排查步骤和关键日志位置

---

## 附录：源码信息

- **仓库**：`https://gitcode.com/Ascend/mssanitizer`
- **文档目录**：`docs/zh/`（overview / user_guide / install_guide / development_guide / api_reference / best_practices / support）
- **发布信息**：2025.12.30 首次上线
- **贡献者**：华为公司计算产品线
