<!-- SPDX-License-Identifier: MIT -->

# wasm32 generation/reset 首轮配对采样

来源：[成功的配对job](https://github.com/HighCWu/distro/actions/runs/37413862807/job/112108054648)。
完整workflow成功，包括格式检查、强制epoch回绕、两种模式正确性及六次benchmark启动。
32位profile另通过强制回绕构建的callback clone快照检查。

- off：重置式去重；on：generation tags。不是关闭去重与默认策略的比较。
- distro：`2db18cf8b2a2d7becbe693a85edb7f78b621e633`
- musl：`fe9e88b15b18d04aa6661e0c8e19b66b99cbc833`
- Linux：`4cf13832724fc0e4d895a6123869716e1c3c893e`
- LLVM：`137009e264eb237b5f5adcbae1b7e209f79291f5`
- Node v24.21.0、GitHub ubuntu-24.04、AMD EPYC 7763、4逻辑CPU（2core SMT）。
- wasm32、64 KiB页、-O2、raw initramfs、4个Linux/Wasm CPU。
- trial 1 off/on，trial 2 on/off，trial 3 off/on，全部重新启动。

长期保留全部六份CSV（270行）及原始provenance，不筛选样本。
每份CSV已用对应原始日志重新验证并逐字节比较；操作计数跨模式与配对一致。
原始artifact名为`mmap-paired-generation-vs-reset-wasm32`。
完整日志仅按Actions保留策略可用；本目录不保证Nix缓存永久存在。

重算命令（仓库根目录）：

```sh
python3 -B scripts/compare_mmap_benchmarks.py docs/benchmarks/mmap-generation-wasm32-run1-20261006
```

下表为各boot三个批量平均延迟样本的中位数，再计算三个逐pair比值的中位数和范围。
范围不是置信区间；比值大于1表示generation本组较快。不能从一轮推断普遍加速。

| Scenario | Mappings | Holes % | Threads | off mmap µs/op | on mmap µs/op | off/on ratio median [min–max] |
|---|---:|---:|---:|---:|---:|---:|
| scale | 16 | 0 | 1 | 16.562 | 17.500 | 0.95 [0.93–1.00] |
| scale | 64 | 0 | 1 | 8.516 | 8.750 | 0.97 [0.97–0.97] |
| scale | 256 | 0 | 1 | 13.105 | 13.027 | 0.99 [0.96–1.04] |
| fragment | 64 | 0 | 1 | — | — | — |
| fragment | 64 | 25 | 1 | 4.688 | 4.375 | 1.07 [0.70–1.07] |
| fragment | 64 | 50 | 1 | 3.750 | 3.750 | 1.00 [0.93–1.04] |
| fragment | 256 | 0 | 1 | — | — | — |
| fragment | 256 | 25 | 1 | 27.266 | 26.641 | 1.02 [1.01–1.03] |
| fragment | 256 | 50 | 1 | 14.961 | 14.414 | 1.04 [1.02–1.08] |
| concurrent | 16 | 0 | 1 | 13.320 | 14.043 | 0.93 [0.75–1.02] |
| concurrent | 16 | 0 | 2 | 21.748 | 22.432 | 0.96 [0.72–1.11] |
| concurrent | 16 | 0 | 4 | 38.779 | 43.843 | 0.88 [0.73–1.15] |
| concurrent | 256 | 0 | 1 | 28.574 | 27.578 | 1.05 [0.92–1.26] |
| concurrent | 256 | 0 | 2 | 53.125 | 37.471 | 1.42 [1.36–1.43] |
| concurrent | 256 | 0 | 4 | 79.976 | 64.653 | 1.03 [0.90–1.49] |
