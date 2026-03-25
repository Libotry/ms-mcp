---
name: msdebug
description: MindStudio Debugger（msDebug）昇腾 NPU 算子调试工具，支持断点、变量打印、单步、寄存器读取、核切换、Core Dump 解析。触发：用户提到 msDebug、断点调试、变量打印、单步调试、核切换、Core Dump、寄存器
---

# msDebug 算子调试工具

## 快速启用

```bash
msdebug ./add_npu          # 加载可执行文件
msdebug python3 test.py     # 加载 Python 脚本
msdebug --core corefile xxx.o # 解析 Core Dump
```

## 核心命令

| 命令 | 说明 |
|-----|------|
| `b <file>:<line>` | 设置断点 |
| `run` / `r` | 运行至断点 |
| `c` | 继续运行 |
| `n` / `next` | 单步（不进入函数）|
| `s` / `step` | 单步（进入函数）|
| `finish` | 跳出当前函数 |
| `p <var>` | 打印变量值 |
| `var` | 打印所有局部变量 |
| `x -m GM -f float32[] <addr> -s 256 -c 1` | 读 GM 内存 |
| `ascend aiv <id>` | 切换 Vector 核 |
| `ascend aic <id>` | 切换 Cube 核 |
| `register read -a` | 读取所有寄存器 |
| `ascend info cores` | 查看所有核 PC |
| `bt` | 调用栈（仅 Core Dump）|

## 关键准备

**调试开关**：`echo 1 > /proc/debug_switch`（需 root）
**编译选项**：`-g -O0 --cce-ignore-always-inline=true`

> GPU 场景需加 `--cce-ignore-always-inline=true`
> PyTorch 场景设置 `LAUNCH_KERNEL_PATH` 指向 kernel .o 文件

## 内存类型

`-m GM` / `UB` / `L0A` / `L0B` / `L0C` / `L1` / `FB`

## 常见问题

**Q: 提示未找到 `/dev/drv_debug`？**
A: 容器加 `--privileged --device=/dev/drv_debug`

**Q: Tensor 按值传递打印失败？**
A: 改为引用传递 `const Tensor&`

**Q: 内存池干扰？**
A: `PYTORCH_NO_NPU_MEMORY_CACHING=1`
