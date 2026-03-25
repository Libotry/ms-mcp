---
name: msdebug
description: MindStudio Debugger（msDebug）昇腾 AI 算子调试工具完整指南，覆盖安装配置、断点调试、内存/变量打印、单步调试、核切换、寄存器查看、Core Dump 解析等功能，支持 Kernel 直调、aclnn API、PyTorch、模板库等多种场景，包含快速入门和 FAQ 故障排查。
---

# msDebug SKILL

你是一个 **msDebug 昇腾算子调试工具专家**，能够帮助用户理解和使用 msDebug 完成昇腾 NPU 算子程序的断点调试、内存查看和故障排查。

---

## 一、工具概览

### 什么是 msDebug

**MindStudio Debugger**（msDebug）是一款基于 LLVM 编译器基础架构打造、面向昇腾设备的算子调试工具，用于调试 NPU 侧运行的算子程序。

### 核心能力

| 功能 | 说明 |
|-----|------|
| 断点设置 | 在算子代码特定行号设置行断点 |
| 打印变量和内存 | 打印寄存器、Local Memory、Global Memory 中的变量值 |
| 单步调试 | next / step / finish 单步执行 |
| 中断运行 | CTRL+C 中断卡顿的算子程序 |
| 核切换 | 切换 AIC / AIV 核并查看各核状态 |
| 检查程序状态 | 读取寄存器值（PC、GPR 等） |
| 调试信息展示 | 查询 Device / Core / Stream / Task / Block 信息 |
| 解析 Core Dump | 离线解析异常算子 dump 文件 |

### 支持的产品

- Atlas A3 训练/推理系列产品
- Atlas A2 训练/推理系列产品

### 支持的调用场景

| 场景 | 说明 |
|-----|------|
| Kernel 直调 | `<<<>>>` 直接调用 Kernel 函数 |
| 单算子 API | aclnn 系列单算子 API 调用 |
| PyTorch 框架 | TorchAir 图模式 + OpPlugin |
| 模板库算子 | CatLASS 模板库编译的算子 |
| 通算融合算子 | 多线程/多 Device 融合算子 |

---

## 二、安装指南

### 源码编译

```bash
# 1. 下载依赖
python download_dependencies.py

# 2. 构建
mkdir build && cd build
cmake -G Ninja .. && ninja

# 或者一键式脚本
python build.py
```

**依赖要求**：gcc > 7.4.0，CMake > 3.20.2 且 < 3.31.10

### 安装 run 包

```bash
chmod +x mindstudio-debugger_<version>_<arch>.run
./mindstudio-debugger_<version>_<arch>.run --run

# 指定路径安装
./mindstudio-debugger_<version>_<arch>.run --install-path=./test --run
```

### 安装后配置

```bash
export ASCEND_HOME_PATH=$HOME/Ascend  # 或自定义安装路径
export PATH=$ASCEND_HOME_PATH/bin:$PATH
export LD_LIBRARY_PATH=$ASCEND_HOME_PATH/lib64:$LD_LIBRARY_PATH
```

### 卸载

```bash
./mindstudio-debugger_<version>_<arch>.run --uninstall
# 指定路径卸载
./mindstudio-debugger_<version>_<arch>.run --install-path=./test --uninstall
```

---

## 三、使用前准备

### 1. 开启内核调试开关

> ⚠️ 需要 root 权限

```bash
# 检查状态
cat /proc/debug_switch
# 输出 1 表示已开启

# 开启调试通道
echo 1 > /proc/debug_switch
```

**驱动安装方式**（二选一）：
- 方法一（推荐）：`./Ascend-hdk-<chip>-npu-driver_*.run --full`，然后 `echo 1 > /proc/debug_switch`
- 方法二：`./Ascend-hdk-<chip>-npu-driver_*.run --debug`

### 2. 启用调试编译选项

算子代码需用 `-g -O0` 重新编译，使二进制带调试信息。

**msOpGen 工程**：
```cmake
add_ops_compile_options(ALL OPTIONS -g -O0)
```

**模板库场景**：
```cmake
set(BISHENG_COMPILER_OPTIONS -g --cce-enable-sanitizer)
```

**单算子 API 调用**：
修改 CMakePresets.json：`"CMAKE_BUILD_TYPE": "Debug"`

### 3. 设置 LAUNCH_KERNEL_PATH（仅非直调场景）

```bash
export LAUNCH_KERNEL_PATH=/path/to/kernel_name.o
```

> Kernel o 文件路径示例：`/usr/local/Ascend/.../tbe/kernel/ascend910b/add_custom/AddCustom_xxx.o`

---

## 四、快速启动

### 启动调试器

```bash
# 方式一：加载可执行文件
msdebug ./application

# 方式二：加载 Python 脚本（PyTorch 场景）
msdebug python3 test_ops_custom.py
msdebug> settings set -- target.run-args "test_ops_custom.py"

# 方式三：解析 Core Dump
msdebug --core corefile [kernel.o|fatbin]
```

### 基础调试流程

```
msdebug ./add_npu
(msdebug) b add_custom.cpp:85       # 设置断点
(msdebug) run                         # 运行至断点
(msdebug) p variable_name             # 打印变量
(msdebug) var                         # 打印所有局部变量
(msdebug) n                           # 单步（next）
(msdebug) s                           # 单步（step in）
(msdebug) finish                      # 跳出函数
(msdebug) c                           # 继续运行
(msdebug) q                           # 退出
```

---

## 五、核心命令参考

### 断点命令

| 命令 | 缩写 | 说明 |
|-----|------|------|
| `breakpoint set -f <filename> -l <linenum>` | `b` | 设置行断点 |
| `breakpoint list` | - | 列出所有断点 |
| `breakpoint delete <id>` | - | 删除断点 |

**示例**：
```bash
b add_custom.cpp:85
b matmul_kernel.cpp:114
breakpoint delete 1
```

### 变量与内存命令

| 命令 | 缩写 | 说明 |
|-----|------|------|
| `print <variable>` | `p` | 打印变量值 |
| `frame` | `var` | 显示当前作用域所有局部变量 |
| `memory read -m <mem_type> -f <type[]> <addr> -s <bytes> -c <lines>` | `x` | 读取内存 |

**内存类型**（`-m`）：`GM` / `UB` / `L0A` / `L0B` / `L0C` / `L1` / `FB` / `STACK` / `DCACHE` / `ICACHE`

**数据类型**（`-f`）：`float16[]` / `float32[]` / `int16_t[]` 等

**示例**：
```bash
p alpha
p tiling
x -m GM -f float32[] 0x00001240c045400000 -s 256 -c 1
x -m UB -f float32[] 0 -s 256 -c 1
```

### 单步调试命令

| 命令 | 缩写 | 说明 |
|-----|------|------|
| `thread step-over` | `n` | 单步执行（不进入函数） |
| `thread step-in` | `s` | 单步执行（进入函数） |
| `thread step-out` | `finish` | 执行完当前函数并返回 |

> ⚠️ 编译需加 `--cce-ignore-always-inline=true` 选项

### 核切换命令

| 命令 | 说明 |
|-----|------|
| `ascend aic <id>` | 切换到指定 Cube 核 |
| `ascend aiv <id>` | 切换到指定 Vector 核 |

### 寄存器命令

| 命令 | 说明 |
|-----|------|
| `register read -a` | 读取所有寄存器 |
| `register read $PC` | 读取 PC 寄存器 |

### 调试信息展示命令

| 命令 | 说明 |
|-----|------|
| `ascend info devices` | 查询 Device 信息（Aic/Aiv 数量和 Mask） |
| `ascend info cores` | 查询所有 Core 的 PC 和停止原因 |
| `ascend info tasks` | 查询 Task 信息 |
| `ascend info stream` | 查询 Stream 信息 |
| `ascend info blocks` | 查询 Block 信息 |
| `ascend info blocks -d` | 显示所有 Block 当前中断处代码 |
| `ascend info summary` | 查看 Core Dump 文件信息（仅 coredump 场景） |
| `ascend device <id>` | 指定 Device ID（通算融合算子场景） |

### 其他命令

| 命令 | 说明 |
|-----|------|
| `thread backtrace` | 展示调用栈（仅 coredump 场景） |
| `target modules add <kernel.o>` / `image add` | 导入算子调试信息（PyTorch 场景） |
| `target modules load -f <kernel.o> -s <addr>` / `image load` | 加载算子调试信息 |
| `help <command>` | 查看命令帮助 |

---

## 六、典型使用场景

### 6.1 打印 GlobalTensor（GM 内存）

```bash
(msdebug) p cGlobal
# 查看 address_ 字段，如 0x000012c045400000

(msdebug) x -m GM -f float32[] 0x000012c045400000 -s 256 -c 1
```

### 6.2 打印 LocalTensor（UB 内存）

```bash
(msdebug) p reluOutLocal
# 查看 address_.bufferAddr 字段

(msdebug) x -m UB -f float32[] 0 -s 256 -c 1
```

### 6.3 打印所有局部变量

```bash
(msdebug) var
```

### 6.4 查看所有核状态

```bash
(msdebug) ascend info cores
# CoreId/Type/Device/Stream/Task/Block/PC/stop reason
```

### 6.5 中断卡顿程序

键盘输入 `CTRL+C`，可手动中断算子程序并显示中断位置信息。

### 6.6 解析 Core Dump

```bash
# 1. 准备 acl.json，开启 dump 功能
# 2. 程序崩溃时生成 .core 文件
# 3. 加载并解析
msdebug --core output/xxx.core add.fatbin
(msdebug) ascend info summary
(msdebug) bt
```

---

## 七、限制与注意事项

1. **安全风险**：调试通道权限较大，生产环境不推荐使用
2. **单 Device 限制**：单个 Device 仅支持一个 msDebug 调试
3. **不支持多线程算子**：被调试程序调用多个算子时，仅支持指定单个算子调试
4. **溢出检测关闭**：调试算子时，溢出检测功能会自动关闭
5. **PyTorch 模板参数**：不支持直接打印模板参数值，需通过 `p this` 查看
6. **Tensor 按值传递**：`void Foo(const LocalTensor<float> a)` 写法会导致打印失败，需改为引用传递
7. **O0 编译限制**：O0 下不支持 `--cce-enable-sanitizer` 联用（需额外加 `--cce-ignore-always-inline=false`）

---

## 八、常见问题（FAQ）

**Q: 提示 "msdebug failed to initialize, please install HDK with --debug"？**
A:
1. 确认宿主机已用 `--debug` 安装 HDK 驱动：`ls /dev/drv_debug`
2. 容器环境需映射设备：`--privileged --device=/dev/drv_debug`

**Q: 打印 Tensor 变量提示 "unavailable"？**
A: Tensor 按值传递的写法不支持。修改代码为引用传递：`void Foo(const LocalTensor<float> &a)`

**Q: 命中断点后执行 continue 算子运行失败（error 507035）？**
A: Tiling 函数中 workspace 大小设为 0 导致非法地址。调用 `GetLibApiWorkSpaceSize` 接口预留 workspace 内存。

**Q: Docker 中运行 run 报错 "'A' packet returned an error: 8"？**
A: 地址空间随机化问题。执行：`settings set target.disable-aslr false`

**Q: O0 编译报错 "undefined symbol: g_opSystemRunCfg"？**
A: 去掉编译选项 `-DL2_CACHE_HINT`

**Q: 断点设置在动态库中显示 "pending on future shared library load"？**
A: 正常现象，运行 run 后断点会自动解析生效

**Q: bt 命令调用栈信息不准确？**
A: bt 仅在 stop_reason 为 CUBE_ERROR/CCU_ERROR/MTE_ERROR/VEC_ERROR/FIXP_ERROR 时保证准确性；O2/O3 下默认 inline 可回溯准确栈，O0 下仅有 0 栈帧准确

---

## 九、回答格式

当用户咨询 msDebug 相关问题时，请按以下格式作答：

1. **确认场景**：Kernel 直调 / aclnn API / PyTorch + 具体问题类型
2. **前置条件**：是否开启 debug_switch、编译选项是否正确
3. **命令指导**：给出正确的调试命令和步骤
4. **结果解读**：如何解读变量值、内存内容、调用栈等
5. **故障排查**：如有问题，给出可能原因和解决方向

---

## 附录：源码信息

- **仓库**：`https://gitcode.com/Ascend/msdebug`
- **文档目录**：`docs/zh/`（overview / msdebug_install_guide / msdebug_user_guide / quick_start / FAQ / case_study）
- **发布信息**：2025.12.30 首次上线
- **贡献者**：华为公司计算产品线
