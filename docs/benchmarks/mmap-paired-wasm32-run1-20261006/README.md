<!-- SPDX-License-Identifier: MIT -->

# wasm32第一轮配对采样

来源：[Paired wasm32 job](https://github.com/HighCWu/distro/actions/runs/37409211822/job/112093622663)。
该job成功；归档时同一workflow的wasm64 job尚未完成，不能把本数据当作整个workflow成功。

- distro：`99cc973215246d651163d339bc3da626b28ce3ff`
- musl：`834a0890d2ce2616ef18fc6dc092266c9014535f`
- Linux：`4cf13832724fc0e4d895a6123869716e1c3c893e`
- LLVM：`137009e264eb237b5f5adcbae1b7e209f79291f5`
- 宿主：GitHub `ubuntu-24.04` runner，Node `v24.21.0`（setup-node提供）。
- CPU：AMD EPYC 9V74，4个逻辑CPU，2个core、每core 2线程；Linux/Wasm配置4 CPU。
- 系统：宿主Linux `6.17.0-1022-azure`，程序为wasm32，64 KiB页，`-O2`，raw initramfs。
- 顺序：trial 1 `off/on`，trial 2 `on/off`，trial 3 `off/on`；每次重新启动。
- 正确性：两种模式各独立启动完整mmap检查并成功；六次benchmark均输出成功标记。
- 样本：每份CSV含15组、每组三次，共45行；六份合计270行，操作数量逐项一致。

工作流artifact原名为`mmap-paired-wasm32`，其中完整日志与`provenance.txt`保留七天。
本目录长期保存全部六份原始CSV，不筛选或合并样本。

Nix产物路径（供识别构建，不假设外部缓存永久可用）：

```text
on: /nix/store/bjfayy53vsj85rmmxzisaz3hc2i2xzmr-mmap-benchmark-artifacts-wasm32
off: /nix/store/3639bzzqsn4v67ya0cln1y5npfw7a5wc-mmap-benchmark-artifacts-wasm32
kernel: /nix/store/akdls93h171fxhf225q3qcdz96nml2kr-lowland-kernel-0.0.0
```

汇总方法及解释见[性能基准文档](../../mmap-benchmark.md)。重算命令：

```sh
python3 scripts/compare_mmap_benchmarks.py docs/benchmarks/mmap-paired-wasm32-run1-20261006
```
