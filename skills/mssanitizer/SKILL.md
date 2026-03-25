---
name: mssanitizer
description: MindStudio Sanitizer（msSanitizer）昇腾 AI 算子异常检测工具，支持内存越界、多核踩踏、数据竞争、未初始化访问、同步异常四大能力。触发：用户提到 msSanitizer、mssanitizer、算子异常检测、内存越界、竞争检测、未初始化、同步异常、SetFlag/WaitFlag
---

# msSanitizer 算子检测工具

## 快速启用

```bash
mssanitizer --tool=memcheck ./add_npu      # 内存检测（默认）
mssanitizer --tool=racecheck ./add_npu   # 竞争检测
mssanitizer --tool=initcheck ./add_npu  # 未初始化检测
mssanitizer --tool=synccheck ./add_npu   # 同步检测
```

## 四种检测能力

| 工具 | 场景 |
|-----|------|
| `memcheck` | 内存越界、多核踩踏、非对齐访问、内存泄漏、非法释放 |
| `racecheck` | 数据竞争（WAW/WAR/RAW） |
| `initcheck` | 脏数据读取 |
| `synccheck` | SetFlag/WaitFlag 未配对 |

## 编译选项

| 场景 | 关键选项 |
|-----|---------|
| Kernel Launch | `--cce-enable-sanitizer -g -O0 --cce-ignore-always-inline=true` |
| msOpGen | `-sanitizer` |
| Triton | `TRITON_ENABLE_SANITIZER=1` |

## 常用参数

| 参数 | 作用 |
|-----|------|
| `--tool` | 检测类型 |
| `--leak-check=yes` | 开启泄漏检测 |
| `--log-file` | 输出到文件 |
| `--kernel-name="add"` | 指定算子 |
| `--full-backtrace=yes` | 显示完整调用栈 |
| `--check-cann-heap=yes` | CANN 层内存检测 |

## 典型使用

```bash
# Kernel 直调
mssanitizer --tool=memcheck ./add_npu

# PyTorch 场景
export PYTORCH_NO_NPU_MEMORY_CACHING=1
mssanitizer -t memcheck python test_ops.py

# Triton 场景
export TRITON_ALWAYS_COMPILE=1
export PYTORCH_NO_NPU_MEMORY_CACHING=1
mssanitizer -t memcheck -- python sample.py
```

## FAQ

**Q: 提示 `<unknown>:0 或行号显示 0？**
A: 添加 `-g` 编译选项

**Q: 报 `InputSection too large`？**
A: 加 `-Xaicore-start -mcmodel=large -mllvm -cce-aicore-relelief -cce-aicore-relief -Xaicore-end`

**Q: PyTorch 场景检测不准？**
A: 设置 `PYTORCH_NO_NPU_MEMORY_CACHING=1`

**Q: Docker 中运行 'A' packet 返回 error 8？**
A: `settings set target.disable-aslr false`

**Q: 竞争检测无异常但实际有竞争？**
A: 前序算子可能有多余 SetFlag，用 `synccheck` 排查
