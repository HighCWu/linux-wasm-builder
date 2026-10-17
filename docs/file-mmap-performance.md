<!-- SPDX-License-Identifier: MIT -->

# 有界文件私有复制性能对照

distro `2706fb9` 增加标准文件候选的首轮测量，不改变默认内核、SDK 或任何容量上限。
检查名为 `mmap-benchmark-check-file-benchmark` 与
`mmap-benchmark-wasm64-check-file-benchmark`。所有目标构建/执行在公开 Actions 完成。
双位宽目标已通过，并核对完整数据、完成与 pass 标记。
首轮[原始记录与溯源](benchmarks/file-copy-node-20261018/README.md)可独立重新解析。
这轮 mmap/pread 配对耗时比约为 4.3–9.4，不能声称 mmap 比 pread 更快；仍须分解开销和重复测量。

## 测量范围

使用候选内核、一个 Linux CPU、已认证 EROFS 上固定 pattern 文件和单线程程序。
两种方式对同一来源的 offset 0 读取相同长度：

- `mmap(NULL, length, PROT_READ, MAP_PRIVATE, fd, 0)`，当前实现主动读取并复制到独立用户 backing。
- `malloc(length)` 后循环 `pread` 直到填满，消费后 `free`。

64 KiB 和 128 KiB 各测五对批次，每批 64 次；奇数对先 mmap，偶数对先 pread。
计时前分别实际运行两种方式并逐字节验证 pattern，使文件读取路径和分配路径预热。
计时包含分配、读取/复制、每 4096 字节及末字节的稀疏消费、解除映射/释放。
每批消费校验和须与已验证内容一致；请求不得改变 fd 共享文件位置。
使用 CLOCK_MONOTONIC 纳秒时间，任何失败或零耗时均拒绝完成。

这是原应用可能使用的两种加载方式对照，而不是只测 syscall 入口。两者分配方式、
内部 backing 粒度和复制次数不同；不能从耗时反推内核独占成本。
这里的“单 CPU”指 Linux 实例配置，不表示 GitHub 宿主已做物理 CPU 独占或频率固定。

不测冷缓存、浏览器、压缩比、完整应用、并发背压、RSS、memory.grow 峰值、尾页或
不同 offset 的性能。正确性和来源/权限拒绝继续由独立检查负责。
五对短批次只是初始诊断，不足以宣布普遍性能优势或默认开放候选。

## 数据与解析

每次真实执行输出 20 条 `file-copy-bench` 记录：位宽、backend、长度、trial、
迭代数、整批纳秒耗时和校验和。随后须出现完成标记与最终 pass。
只从一次新执行的完整日志生成表格：

```sh
python3 -B scripts/summarize_file_copy_benchmark.py --bits 64 < target-run.log
```

解析器核对两种长度、五对完整批次、固定迭代数、交替顺序、位宽、校验和及正耗时，
拒绝重复/缺失/未知记录、错误标记、完成后的数据，以及没有完成/pass 的日志。
报告包含各 backend 的 µs/op 中位数和五个**配对比值的中位数**，不是两个中位数相除。
比值大于 1 表示在该次条件下 mmap 批次更慢；不设置速度通过阈值。

原生 GCC/Clang 工作负载也运行共享测量函数，但使用本机真正文件映射，不能代表
Wasm 的主动复制。其输出带 `host-workload-only`，目标解析器必须明确拒绝。
宿主测试还覆盖两种位宽的合成记录、坏数据/标记及配对统计，不能把合成数据当成测量。

首次结果须关联具体源码提交、公开 run/job 和原始日志；后续正式性能记录还需补充
实际 Node/V8、runner 硬件及重复新启动信息。Nix 缓存命中只证明已有检查可复用，
不产生一次新的测量，不能用空日志或缓存成功填写新数据。

独立程序、集成、解析器和文档采用 MIT；所用组件保持各自原许可证。
