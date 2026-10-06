<!-- SPDX-License-Identifier: MIT -->

# wasm64第二轮配对采样

来源：[Paired wasm64 job](https://github.com/HighCWu/distro/actions/runs/37409215653/job/112097913458)。
该job和所属完整配对workflow均成功；此目录仅记录本profile的数据。

- distro：`99cc973215246d651163d339bc3da626b28ce3ff`
- musl：`834a0890d2ce2616ef18fc6dc092266c9014535f`
- Linux：`4cf13832724fc0e4d895a6123869716e1c3c893e`
- LLVM：`137009e264eb237b5f5adcbae1b7e209f79291f5`
- 宿主：GitHub `ubuntu-24.04` runner，setup-node提供的Node `v24.21.0`。
- CPU：AMD EPYC 7763 64-Core Processor，4个逻辑CPU，2个core、每core 2线程。
- 系统：宿主Linux `6.17.0-1022-azure`，Linux/Wasm配置4 CPU，wasm64、64 KiB页、`-O2`。
- 启动：raw initramfs；trial 1 `off/on`，trial 2 `on/off`，trial 3 `off/on`，每次重新启动。
- 正确性：两种模式分别通过完整mmap检查，六次benchmark均输出成功标记。
- 样本：六份CSV各含15组、每组三次，合计270行；操作数量逐项一致。

artifact原名为`mmap-paired-wasm64`，完整日志和`provenance.txt`保留七天；
本目录长期保存全部六份原始CSV，不筛选或合并样本。

Nix产物路径用于识别构建，不保证外部缓存永久可用：

```text
on: /nix/store/x9winvfj0rkbx1ymngqcsbpqqgwbf887-mmap-benchmark-artifacts-wasm64
off: /nix/store/6jlmvfm0dg023m0dwb6l0dvs62l7jcjy-mmap-benchmark-artifacts-wasm64
kernel: /nix/store/p3hgwmxw2872lzc1b2kwy5gnk7is60qm-lowland-kernel-0.0.0
```

汇总方法及解释见[性能基准文档](../../mmap-benchmark.md)。重算命令：

```sh
python3 scripts/compare_mmap_benchmarks.py docs/benchmarks/mmap-paired-wasm64-run2-20261006
```
