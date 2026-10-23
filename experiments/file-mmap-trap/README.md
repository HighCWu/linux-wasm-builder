<!-- SPDX-License-Identifier: MIT -->
# 文件初始化 trap 的清理复现

这是实际函数体的清理回归，不是完整内核或发布验收。默认命令要求 C 资源归零：

```sh
python3 -B experiments/file-mmap-trap/run.py
```

反向控制绕过异常清理钩子，须复现泄漏，再由任务退出钩子清理：

```sh
python3 -B experiments/file-mmap-trap/run.py --expect-leak
CC=clang-22 python3 -B experiments/file-mmap-trap/run.py --expect-leak
```

运行器读取当前 Linux 的 mmap_file.c，保留实际函数体，用最小原子/VFS/分配模型
编译到小型 wasm32/wasm64 模块。正常初始化和普通 ENOMEM 返回均须清理；另一个真实 Wasm 初始化器
执行 unreachable，经实际 FileMmapCopy 和 call_kernel_entry 传播异常。桥的租约
已撤销、内核 C 栈指针已恢复。新异常钩子释放请求、staging、模型分配、128 KiB
预留和模型文件引用，之后原 RuntimeError 仍必须传播；后续请求也必须恢复。
默认命令会检查两种位宽，而不是在 wasm32 失败后漏掉 wasm64。

已对 Linux `50abafbb5`、distro `2784222` 用 Clang18 和 Clang22 核实上述
两种位宽的旧缺陷；正常/errno 对照资源归零，trap 后残留请求、staging、一个
模型分配和预算。Linux `48adb6d39` 加入任务所有的堆记录及退出清理，执行桥
在重抛前调用内部 abort export 后，两种位宽资源均归零。旁路对照残留两个分配
（staging 和新增记录），由退出清理回收；重复退出清理不应双重释放。

此实验验证异常绕过 C 清理的控制流，不证明 Linux VFS、原子或调度。没有分配
大内存，不运行完整内核，不安装到 SDK，也不将预期缺陷写成 CI 的成功要求。
正确修复必须让内核清理，并保留用户 trap 的终止语义，区分内核异常和 SjLj；
不能简单吞掉异常，继续运行状态可能已损坏的用户分配器。
该模型用计数模拟调用者传入的一个文件引用，验证共用复制函数的消耗约定，
不证明真实 fget/fput/VFS 生命周期。目标验证须覆盖初始化器重入 syscall、
exec/exit 和信号非局部退出。不能在 task 已 exit 并交出 CPU 后再进入内核清理；
运行时跳过 HALT_KERNEL，实际退出清理由 exit_thread 在交出 CPU 前执行。

独立脚本和模型采用 MIT。临时测试模块包含实际 GPL 内核实现，不能作为 MIT
用户程序或 SDK 示例分发；若分享该生成模块，须遵守内核相应许可及源码义务。
