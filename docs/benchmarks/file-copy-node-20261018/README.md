<!-- SPDX-License-Identifier: MIT -->

# 首轮 Node 文件复制配对记录

数据来自 distro `2706fb97e8b48ddb95d9973c32c3e7b1abb3e7cf`：

- Linux `8bd657dcf6ebfc130d85185bf2d9cdedc1ac8399`，默认关闭文件候选，Linux CPU 数为 1。
- musl `f4ffd5e5a7a93026d3b31e1722adacba8602bf25`，初始化分配器显式导出。
- 解析器固定于主仓库 `74f34b2`；完整方法和限制见[性能说明](../../file-mmap-performance.md)。
- [wasm32 run](https://github.com/HighCWu/distro/actions/runs/39048256554)，job `117441342071`。
- [wasm64 run](https://github.com/HighCWu/distro/actions/runs/39048259765)，job `117441352410`。

两条工作流均成功。相邻 `.log` 是从真实 job 日志提取的 20 条数据、完成和 pass 标记，
保留原时间与 derivation 前缀；不是完整构建日志。每份均经严格解析器校验。
可在主仓库执行：

```sh
python3 -B scripts/summarize_file_copy_benchmark.py --bits 32 < docs/benchmarks/file-copy-node-20261018/wasm32.log
python3 -B scripts/summarize_file_copy_benchmark.py --bits 64 < docs/benchmarks/file-copy-node-20261018/wasm64.log
```

| Profile | Bytes | pread median µs/op | mmap median µs/op | Median paired mmap/pread |
|---|---:|---:|---:|---:|
| wasm32 | 65536 | 19.141 | 120.234 | 6.090 |
| wasm32 | 131072 | 15.547 | 130.859 | 9.358 |
| wasm64 | 65536 | 26.797 | 126.953 | 4.262 |
| wasm64 | 131072 | 19.453 | 157.812 | 8.397 |

当前主动复制 mmap 在这一轮中明显慢于 malloc/pread。不能只凭此数据将差距归因于
memcpy、清零、分配器、宿主跨界或调度中的任意单项；须先分解测量并重复新启动。
两种位宽运行于不同 CI 任务，不能据此判断哪种位宽本质更快。
没有采集实际 Node/V8 与完整硬件快照，本轮不作为长期可比的正式性能基线。
单轮暖缓存、稀疏消费不代表浏览器、冷缓存、RSS、压缩程序整体或长期性能。
默认发布配置仍拒绝文件映射，不因正确性成功自动开放此候选。
