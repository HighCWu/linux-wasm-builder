<!-- SPDX-License-Identifier: MIT -->
# 文件初始化 trap 的清理复现

这是未解决缺口的复现，不是新功能或发布验收。默认命令要求 C 资源归零，当前应失败：

```sh
python3 -B experiments/file-mmap-trap/run.py
```

诊断模式确认当前泄漏状态，可分别用 Clang18/22 执行：

```sh
python3 -B experiments/file-mmap-trap/run.py --expect-leak
CC=clang-22 python3 -B experiments/file-mmap-trap/run.py --expect-leak
```

运行器读取当前 Linux 的 mmap_file.c，保留实际函数体，用最小原子/VFS/分配模型
编译到小型 wasm32/wasm64 模块。正常初始化和普通 ENOMEM 返回均须清理；另一个真实 Wasm 初始化器
执行 unreachable，经实际 FileMmapCopy 和 call_kernel_entry 传播异常。桥的租约
已撤销、内核 C 栈指针已恢复，但 C 资源仍为一个请求、一个 staging、一个模型分配和128 KiB预留。
默认命令会检查两种位宽再报告失败，而不是在 wasm32 失败后漏掉 wasm64。

已对 Linux `50abafbb5`、distro `2784222` 用 Clang18 和 Clang22 核实上述
两种位宽的诊断；正常/errno 对照资源归零，trap 后均残留上述计数。

此实验验证异常绕过 C 清理的控制流，不证明 Linux VFS、原子或调度。没有分配
大内存，不运行完整内核，不安装到 SDK，也不将预期缺陷写成 CI 的成功要求。
正确修复必须让内核清理，并保留用户 trap 的终止语义，区分内核异常和 SjLj；
不能简单吞掉异常，继续运行状态可能已损坏的用户分配器。
该模型没有执行标准入口调用者的 fget/fput，因此不测量来源文件引用泄漏；
修复 review 仍须覆盖这一外层所有权，以及初始化器重入 syscall、exec/exit 和信号非局部退出。

独立脚本和模型采用 MIT。临时测试模块包含实际 GPL 内核实现，不能作为 MIT
用户程序或 SDK 示例分发；若分享该生成模块，须遵守内核相应许可及源码义务。
