<!-- SPDX-License-Identifier: MIT -->

# wasm64 generation/reset 第二轮配对采样

来源：[成功的配对job](https://github.com/HighCWu/distro/actions/runs/37416061054/job/112114816068)。
完整workflow成功，包括格式检查、强制epoch回绕、两种模式正确性及六次benchmark启动。
32位profile另通过强制回绕构建的callback clone快照检查。

- off：重置式去重；on：generation tags。不是关闭去重与默认策略的比较。
- distro：`2db18cf8b2a2d7becbe693a85edb7f78b621e633`
- musl：`fe9e88b15b18d04aa6661e0c8e19b66b99cbc833`
- Linux：`4cf13832724fc0e4d895a6123869716e1c3c893e`
- LLVM：`137009e264eb237b5f5adcbae1b7e209f79291f5`
- Node v24.21.0、GitHub ubuntu-24.04、AMD EPYC 7763、4逻辑CPU（2core SMT）。
- wasm64、64 KiB页、-O2、raw initramfs、4个Linux/Wasm CPU。
- trial 1 off/on，trial 2 on/off，trial 3 off/on，全部重新启动。

长期保留全部六份CSV（270行）及完整原始provenance，不筛选样本。
每份CSV已用对应原始日志重新验证并逐字节比较；操作计数跨模式与配对一致。
原始artifact名为`mmap-paired-generation-vs-reset-wasm64`。
同一宽度的Nix产物路径与第一轮一致；不保证缓存永久存在或两轮底层物理宿主独立。

重算命令（仓库根目录）：

```sh
python3 -B scripts/compare_mmap_benchmarks.py docs/benchmarks/mmap-generation-wasm64-run2-20261006
```

下表为各boot三个批量平均延迟样本的中位数，再计算三个逐pair比值的中位数和范围。
范围不是置信区间；比值大于1表示generation本组较快。不能从两轮推断普遍加速。

| Scenario | Mappings | Holes % | Threads | off mmap µs/op | on mmap µs/op | off/on ratio median [min–max] |
|---|---:|---:|---:|---:|---:|---:|
| scale | 16 | 0 | 1 | 11.875 | 12.188 | 1.09 [0.76–1.13] |
| scale | 64 | 0 | 1 | 13.281 | 11.875 | 1.12 [0.89–1.38] |
| scale | 256 | 0 | 1 | 15.938 | 15.645 | 1.01 [0.99–1.08] |
| fragment | 64 | 0 | 1 | — | — | — |
| fragment | 64 | 25 | 1 | 5.625 | 5.625 | 1.00 [0.94–1.44] |
| fragment | 64 | 50 | 1 | 4.531 | 5.000 | 1.04 [0.91–1.50] |
| fragment | 256 | 0 | 1 | — | — | — |
| fragment | 256 | 25 | 1 | 33.594 | 35.312 | 0.96 [0.94–1.03] |
| fragment | 256 | 50 | 1 | 18.633 | 18.789 | 0.98 [0.97–1.14] |
| concurrent | 16 | 0 | 1 | 16.465 | 16.621 | 0.99 [0.94–0.99] |
| concurrent | 16 | 0 | 2 | 23.311 | 27.393 | 0.79 [0.63–1.10] |
| concurrent | 16 | 0 | 4 | 42.627 | 48.345 | 0.73 [0.69–1.31] |
| concurrent | 256 | 0 | 1 | 31.836 | 32.910 | 0.95 [0.88–0.98] |
| concurrent | 256 | 0 | 2 | 66.182 | 52.529 | 1.17 [0.94–1.34] |
| concurrent | 256 | 0 | 4 | 81.807 | 80.269 | 0.95 [0.94–1.19] |
