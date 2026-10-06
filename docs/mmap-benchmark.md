<!-- SPDX-License-Identifier: MIT -->

# Direct mmap 性能基准

基准入口是`distro`的`basic-init-check-mmap-benchmark`。程序由项目工具链以`-O2`
编译，经现有测试runner启动Linux/Wasm，并使用公开的libc `mmap()`/`munmap()`接口。
默认测试profile为wasm32、4个内核CPU；输出另行记录指针宽度和实际页大小，不能把
wasm32结果当作wasm64或浏览器性能结论。

## 测量内容

- `scale`：从没有本基准映射开始，批量建立16、64、256个单页映射，再按FIFO解除。
  `mappings`表示该轮建立的数量，解除顺序可暴露链表尾部查找成本。
- `fragment`：先建立64或256个单页映射，再解除其中0%、25%、50%的交错页，最后用
  普通匿名分配补足数量。setup及最终cleanup不计入操作耗时。0%是没有解除或回填的
  控制组，没有可计算的操作延迟和吞吐。
- `concurrent`：保留16或256个映射作为背景，在1、2、4个线程中各执行32轮，每轮
  分配8页再解除。start gate同步起点，线程创建和join不在测量区间内。

每组先完整预热一次，再输出三个样本。每轮结束时释放该轮所有映射；linear memory
的高水位不会因此缩小，预热后的数据不能说明首次启动或第一次memory growth的成本。
基准始终检查页对齐、首尾字节zero-fill和存活映射内容，计时结果不设绝对通过门槛。

## 输出与解释

每行以`mmap-bench,`开头，之后按顺序包含：scenario、mappings、holes_percent、threads、
sample、operations_per_kind、mmap_ns、munmap_ns、elapsed_ns。
CSV表头把mappings字段命名为`resident`；其含义随场景分别是该轮峰值、碎片setup数量
或并发组开始时保留的背景映射数量。

`operations_per_kind`是各自的mmap和munmap调用数量；总调用数为其两倍。两个操作
耗时是批量区间总和，包含分配器内部清零、syscall、Wasm/宿主边界和锁等待。
并发时各线程区间会重叠，因此累计耗时不能等同于墙钟时间。总墙钟时间还包含映射
内容检查和调度；其吞吐描述本基准完整操作序列，而非allocator理论极限。
clock调用、循环及记录开销也在批量区间中，没有扣除时钟开销或声称测得单次调用分布。

使用以下命令在公开GitHub Actions运行：

```sh
gh workflow run ci.yml --repo HighCWu/distro --ref main \
  -f heavy-check=basic-init-check-mmap-benchmark
```

获取完成run的日志后，可从本仓库目录生成三次样本的汇总：

```sh
job_id=$(gh run view RUN_ID --repo HighCWu/distro --json jobs \
  --jq '.jobs[] | select(.name == "Heavy check / basic-init-check-mmap-benchmark") | .databaseId')
gh api "repos/HighCWu/distro/actions/jobs/$job_id/logs" \
  | python3 scripts/summarize_mmap_benchmark.py
```

脚本计算三个样本中批量平均延迟的中位数，以及各样本总吞吐的中位数。
它不是单次操作的p50/p95。缺失、重复或无效样本会报错；原始行保留在Actions日志中，
比较时应同时查看样本波动。

比较必须记录distro、musl、Linux pins及编译profile，并尽可能固定Node版本、runner规格、
内核CPU数和采样方法。公开runner的负载变化、JIT预热和多worker调度都会影响结果。
这些样本用于决定查找结构和chunk策略，不能直接转换为本机Linux或其它系统的性能比值。

## 可关闭的搜索优化基线

musl默认启用`WASM_MMAP_DEDUP_SEARCH`，普通分配对每个backing只搜索一次。
`deduplicateMmapSearch = false`的Nix override会设置
`-DWASM_MMAP_DEDUP_SEARCH=0`，同时排除去重字段和搜索标记逻辑，恢复原始搜索路径。
基线与默认构建使用同一个源码pin、相同内核和测试程序，不改变Linux UAPI或Wasm import。

以下定向检查分别覆盖默认和关闭优化的构建：

| 目的 | heavy-check |
|---|---|
| 默认正确性 | `basic-init-check-mmap` |
| 默认基准 | `basic-init-check-mmap-benchmark` |
| 关闭优化的正确性 | `mmap-search-baseline-correctness` |
| 关闭优化的基准 | `mmap-search-baseline-benchmark` |

每项都可通过前面的`gh workflow run`命令运行。获取基线日志时，应选择相应的
`Heavy check / mmap-search-baseline-benchmark` job；两种基准输出分别交给同一个汇总
脚本，不能把同名样本拼在一起计算中位数。

## 2026-10-06 首轮基线

[定向CI](https://github.com/HighCWu/distro/actions/runs/37397972606)通过全部操作校验及
仓库格式检查，并输出45个样本。原始数据见
[mmap-wasm32-20261006.csv](benchmarks/mmap-wasm32-20261006.csv)。测试环境为
GitHub `ubuntu-24.04` runner、Nix提供的Node 24.18.0、4个Linux/Wasm CPU、wasm32、
64 KiB页和`-O2`。

| 组件 | commit |
|---|---|
| distro | `b0c85393e12ee9df650f27217e245699a07aa056` |
| musl | `d7c704856eaa0d5159e498e677dd0277020e2275` |
| Linux | `4cf13832724fc0e4d895a6123869716e1c3c893e` |
| LLVM | `137009e264eb237b5f5adcbae1b7e209f79291f5` |

下表由汇总脚本生成；延迟单位为µs，吞吐包含mmap和munmap两类操作：

| Scenario | Mappings | Holes % | Threads | mmap µs/op | munmap µs/op | Operations/s |
|---|---:|---:|---:|---:|---:|---:|
| scale | 16 | 0 | 1 | 19.688 | 1.250 | 95522 |
| scale | 64 | 0 | 1 | 11.328 | 1.328 | 158025 |
| scale | 256 | 0 | 1 | 41.660 | 1.836 | 45270 |
| fragment | 64 | 0 | 1 | — | — | — |
| fragment | 64 | 25 | 1 | 11.875 | 1.562 | 148837 |
| fragment | 64 | 50 | 1 | 7.031 | 0.938 | 250980 |
| fragment | 256 | 0 | 1 | — | — | — |
| fragment | 256 | 25 | 1 | 180.781 | 1.094 | 10997 |
| fragment | 256 | 50 | 1 | 87.812 | 1.133 | 22407 |
| concurrent | 16 | 0 | 1 | 12.852 | 5.586 | 96150 |
| concurrent | 16 | 0 | 2 | 23.311 | 7.832 | 95612 |
| concurrent | 16 | 0 | 4 | 47.988 | 23.179 | 82266 |
| concurrent | 256 | 0 | 1 | 118.086 | 8.613 | 16220 |
| concurrent | 256 | 0 | 2 | 150.996 | 16.270 | 20114 |
| concurrent | 256 | 0 | 4 | 243.467 | 89.932 | 22979 |

这组数据支持优先检查已有backing的查找成本。25%空洞回填时，256个映射的mmap
批量平均延迟中位数约为64个映射时的15倍，而munmap变化较小。源码中的普通分配会
按每个live mapping重新扫描其allocation，同一满chunk可能被反复检查。因此下一步
先评估按唯一backing去重扫描，保持现有映射登记与生命周期语义，再用同一基准比较。
是否需要独立空闲区间索引或区间树，应由优化后的数据决定。

并发组中，256个背景映射下4线程吞吐约为单线程的1.42倍，尚未线性扩展；锁等待、
宿主CPU资源和调度均可能影响结果，不能仅凭这些样本断言某个锁是唯一瓶颈。
16个映射的scale组有明显波动，三个mmap样本约为8.75–42.81 µs/op，说明一次预热
仍不足以消除全部JIT或runner噪声。这批时间记录均按5 µs阶梯变化；ns字段不代表
纳秒测量精度。后续比较应重复独立run并检查原始分布，不能只看一轮的中位数。

测试runner现在先解码并输出完整LF文本行，避免借用Wasm缓冲区在Node异步输出期间
复用，以及TTY原始CRLF使Nix日志丢失内容的问题；该边界已有独立协议回归检查。

## 2026-10-06 搜索去重开关对照

同一源码分别运行[开启优化基准](https://github.com/HighCWu/distro/actions/runs/37401442856)
和[关闭优化基准](https://github.com/HighCWu/distro/actions/runs/37401450673)，并通过
[开启正确性检查](https://github.com/HighCWu/distro/actions/runs/37401438602)与
[关闭正确性检查](https://github.com/HighCWu/distro/actions/runs/37401446721)。两种构建均通过
仓库格式检查。原始样本分别见
[dedup-on CSV](benchmarks/mmap-wasm32-dedup-on-20261006.csv)和
[dedup-off CSV](benchmarks/mmap-wasm32-dedup-off-20261006.csv)，各含15组、每组三次样本。

| 组件 | commit |
|---|---|
| distro | `63246175800b5af51a2414051b3c9c8cccce9695` |
| musl | `834a0890d2ce2616ef18fc6dc092266c9014535f` |
| Linux | `4cf13832724fc0e4d895a6123869716e1c3c893e` |
| LLVM | `137009e264eb237b5f5adcbae1b7e209f79291f5` |

环境仍为公开`ubuntu-24.04` runner、Node 24.18.0、wasm32、64 KiB页、4个
Linux/Wasm CPU、测试程序`-O2`。下表延迟仍是三次批量平均值的中位数；吞吐包含两类操作。
0%空洞控制组没有操作，不列入数值比较，但保留在CSV中。

| Scenario | Mappings | Holes % | Threads | off mmap µs/op | on mmap µs/op | off Operations/s | on Operations/s |
|---|---:|---:|---:|---:|---:|---:|---:|
| scale | 16 | 0 | 1 | 17.500 | 21.875 | 104918 | 86486 |
| scale | 64 | 0 | 1 | 8.828 | 10.156 | 200000 | 174150 |
| scale | 256 | 0 | 1 | 43.418 | 17.637 | 44697 | 106445 |
| fragment | 64 | 25 | 1 | 13.125 | 5.000 | 136170 | 266667 |
| fragment | 64 | 50 | 1 | 8.438 | 4.219 | 213333 | 376471 |
| fragment | 256 | 25 | 1 | 193.438 | 31.484 | 10265 | 61244 |
| fragment | 256 | 50 | 1 | 94.805 | 16.758 | 20855 | 112775 |
| concurrent | 16 | 0 | 1 | 14.844 | 12.793 | 89276 | 99321 |
| concurrent | 16 | 0 | 2 | 29.014 | 20.908 | 58935 | 95389 |
| concurrent | 16 | 0 | 4 | 49.575 | 50.654 | 80773 | 77974 |
| concurrent | 256 | 0 | 1 | 129.688 | 34.512 | 13206 | 48902 |
| concurrent | 256 | 0 | 2 | 170.986 | 38.857 | 17203 | 53937 |
| concurrent | 256 | 0 | 4 | 173.306 | 80.542 | 25397 | 59892 |

256映射的scale组mmap延迟约降低至原来的1/2.46；256映射、25%和50%空洞组分别
约为1/6.14与1/5.66。这支持保留按唯一backing搜索的优化，但小规模scale组与16映射
四线程组本轮稍慢。重置标记仍需遍历live mapping，去重也未改变空洞搜索的数据结构。
不能由这些数据断言所有场景提速、锁竞争消除或复杂度已整体降至线性。

开关两边是不同公开runner上的各一轮采样，尚无独立重复run或统计置信区间，JIT、
调度和runner负载仍是混杂因素。下一步重复独立对照、检查小规模额外开销，并扩展
wasm64性能采样；wasm64启动检查不等于wasm64性能基准。

## 同runner配对复测

`distro`的`Paired mmap benchmark`是仅手动触发的有界工作流。它为wasm32和wasm64
各使用一个公开runner，不并行运行这两个profile。两种profile都复用现有
`basic-init/tests/mmap.c`与`mmap-benchmark.c`，使用`-O2`与对应宽度的工具链，分别链接
默认musl和关闭`WASM_MMAP_DEDUP_SEARCH`的musl。它不新增内核或编译器变更。

为避免依赖尚未齐备的wasm64安装包集合，程序作为raw initramfs中的`/init`运行。
这与此前安装式wasm32检查的rootfs布局不同，必须单独标注，不能把新旧样本拼接成
同一组统计数据。wasm32也采用相同raw initramfs路径，以减少两种宽度之间的测试差异。

```sh
gh workflow run mmap-benchmark.yml --repo HighCWu/distro --ref main
gh run download RUN_ID --repo HighCWu/distro \
  --name mmap-paired-wasm64 --dir ARTIFACT_DIRECTORY
python3 scripts/compare_mmap_benchmarks.py ARTIFACT_DIRECTORY
```

工作流先在两种模式下分别重新启动并执行完整mmap正确性检查，然后执行三轮配对：
`off/on`、`on/off`、`off/on`。每次都直接启动新的Node进程与Linux/Wasm实例，而不是
读取缓存的Nix benchmark check输出；源码和二进制构建可以复用缓存。每次启动仍
包含原有预热与每组三个样本，单profile共270条测量记录。模式顺序交替只能减轻
时间顺序偏差，并非完全随机化。

artifact保存两种正确性日志、六份benchmark日志/CSV、源码revision、Nix产物路径、
源码pins、Node版本和runner CPU信息，保留七天。CSV生成前检查pointer宽度、64 KiB
页、完整15组/45样本矩阵、操作数量、唯一sample与明确成功标记；失败记录不会作为
成功采样归档。工作流每个profile限时60分钟，每次启动限时300秒，不自动触发重型采样。

比较脚本先验证六份CSV的完整性和相同操作数量。每次启动先取三个批量平均延迟的
中位数，再分别列出三次启动中位数的中位数，以及每轮`off/on`延迟比值的中位数和
最小–最大值。比值大于1表示该轮开启优化较快，小于1表示较慢；这里的范围不是
置信区间，也不是单次操作延迟分布。

同一个runner上的三次新启动是进程级复测，不能替代多个独立workflow run的复现。
wasm32和wasm64分属不同runner，也不能据此把两者差异完全归因于指针宽度。
后续仍需跨run重复，并在比较报告中保留小规模退化和波动结果。

### 第一轮wasm32结果

[第一轮wasm32 job](https://github.com/HighCWu/distro/actions/runs/37409211822/job/112093622663)
通过两种模式的正确性检查和全部三轮配对采样。六份CSV、源码pins及环境记录见
[原始数据目录](benchmarks/mmap-paired-wasm32-run1-20261006/README.md)。distro revision为
`99cc973`，宿主是4逻辑CPU的AMD EPYC 9V74 runner，Node为setup-node提供的`v24.21.0`。
与之前Nix提供的Node `24.18.0`、安装式rootfs采样环境不同，不合并两批绝对耗时。

以下由配对汇总脚本生成。延迟列分别汇总两种模式的三次启动；比值先按每一轮配对
计算，再取中位数，因此不一定等于表中两个延迟中位数之商。

| Scenario | Mappings | Holes % | Threads | off mmap µs/op | on mmap µs/op | off/on ratio median [min–max] |
|---|---:|---:|---:|---:|---:|---:|
| scale | 16 | 0 | 1 | 14.062 | 13.438 | 1.05 [0.98–1.19] |
| scale | 64 | 0 | 1 | 7.969 | 6.406 | 1.27 [1.22–1.39] |
| scale | 256 | 0 | 1 | 33.535 | 10.371 | 3.24 [3.14–3.37] |
| fragment | 64 | 0 | 1 | — | — | — |
| fragment | 64 | 25 | 1 | 10.312 | 3.750 | 2.75 [2.75–3.08] |
| fragment | 64 | 50 | 1 | 6.094 | 3.125 | 1.95 [1.95–2.25] |
| fragment | 256 | 0 | 1 | — | — | — |
| fragment | 256 | 25 | 1 | 150.391 | 22.734 | 6.62 [6.56–6.68] |
| fragment | 256 | 50 | 1 | 69.961 | 12.305 | 5.69 [5.60–5.72] |
| concurrent | 16 | 0 | 1 | 9.863 | 9.766 | 1.10 [0.74–1.10] |
| concurrent | 16 | 0 | 2 | 16.650 | 16.602 | 1.01 [0.78–1.10] |
| concurrent | 16 | 0 | 4 | 40.215 | 33.911 | 1.04 [0.99–1.49] |
| concurrent | 256 | 0 | 1 | 98.125 | 24.199 | 4.38 [3.72–4.68] |
| concurrent | 256 | 0 | 2 | 142.725 | 32.148 | 4.67 [4.10–6.56] |
| concurrent | 256 | 0 | 4 | 145.186 | 55.029 | 2.88 [1.76–3.11] |

256映射的三类场景中，三轮比值均大于1；25%空洞组的比值范围较窄，支持该搜索
优化对较多映射的收益。16背景映射的并发组存在小于1的轮次，不能宣称小规模或
所有线程数组合都稳定加速。这里不做显著性检验；三个配对轮次共享同一个runner，
仍不能代替跨runner的复现。随后独立第二轮及wasm64的数据见下一节；目前尚未
引入generation tag或新的空闲区间索引。

### 两个独立run、两种指针宽度的完整复测

[run 1](https://github.com/HighCWu/distro/actions/runs/37409211822)与
[run 2](https://github.com/HighCWu/distro/actions/runs/37409215653)均成功，覆盖四个profile job。
每个job分别完成两种模式的完整mmap正确性检查和六次新启动，合计8次正确性启动、
24次benchmark启动、24份CSV、1080行记录。四组均使用同一个distro `99cc973`、相同
musl/Linux/LLVM pins与Node `v24.21.0`；同一宽度的Nix产物路径在两轮中完全一致。

| Profile | CPU model | 原始数据与provenance摘要 |
|---|---|---|
| wasm32/run1 | AMD EPYC 9V74 | [数据](benchmarks/mmap-paired-wasm32-run1-20261006/README.md) |
| wasm32/run2 | AMD EPYC 9V74 | [数据](benchmarks/mmap-paired-wasm32-run2-20261006/README.md) |
| wasm64/run1 | AMD EPYC 9V45 | [数据](benchmarks/mmap-paired-wasm64-run1-20261006/README.md) |
| wasm64/run2 | AMD EPYC 7763 | [数据](benchmarks/mmap-paired-wasm64-run2-20261006/README.md) |

各runner均暴露4逻辑CPU、2个core、每core 2线程，Linux/Wasm同样配置4 CPU。
每个job使用独立runner实例，但不能保证底层物理主机独立。CPU型号和负载不固定，
因此不直接比较wasm32与wasm64的绝对耗时，也不把跨run变化全部归因于指针宽度。
wasm64采样仅证明Memory64程序在这些工作负载下可运行；没有测试大于4 GiB的地址、
16 GiB容量或浏览器性能。

下表保留每个job的三轮配对比值中位数与最小–最大值，不把四组数据混合成一个统计量。
比值是`off/on`的mmap批量平均延迟，范围不是置信区间。无操作的0%空洞控制组省略，
但全部保留在原始CSV中；绝对延迟可通过前述比较脚本分别重算。

| 场景 | 映射 | 空洞% | 线程 | 32/run1 | 32/run2 | 64/run1 | 64/run2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| scale | 16 | 0 | 1 | 1.05 [0.98–1.19] | 0.90 [0.88–1.43] | 0.90 [0.84–0.95] | 1.10 [0.77–1.35] |
| scale | 64 | 0 | 1 | 1.27 [1.22–1.39] | 1.08 [1.07–1.42] | 1.00 [0.99–1.07] | 1.27 [1.17–1.50] |
| scale | 256 | 0 | 1 | 3.24 [3.14–3.37] | 3.25 [3.25–3.40] | 2.85 [2.81–3.13] | 3.03 [3.03–3.35] |
| fragment | 64 | 25 | 1 | 2.75 [2.75–3.08] | 2.62 [2.62–2.75] | 2.60 [2.27–2.80] | 2.61 [1.96–3.44] |
| fragment | 64 | 50 | 1 | 1.95 [1.95–2.25] | 1.86 [1.81–1.95] | 1.82 [1.82–2.00] | 1.90 [1.45–2.62] |
| fragment | 256 | 25 | 1 | 6.62 [6.56–6.68] | 6.66 [6.60–6.69] | 6.34 [6.30–6.36] | 6.60 [5.96–6.65] |
| fragment | 256 | 50 | 1 | 5.69 [5.60–5.72] | 5.73 [5.73–5.74] | 5.11 [4.43–5.12] | 5.34 [5.20–5.59] |
| concurrent | 16 | 0 | 1 | 1.10 [0.74–1.10] | 0.98 [0.96–1.17] | 0.98 [0.77–1.13] | 1.03 [0.84–1.03] |
| concurrent | 16 | 0 | 2 | 1.01 [0.78–1.10] | 1.17 [0.73–1.20] | 0.65 [0.52–1.07] | 0.66 [0.55–0.90] |
| concurrent | 16 | 0 | 4 | 1.04 [0.99–1.49] | 0.76 [0.74–1.00] | 0.98 [0.85–1.02] | 0.75 [0.72–1.41] |
| concurrent | 256 | 0 | 1 | 4.38 [3.72–4.68] | 4.01 [3.58–4.44] | 4.09 [3.69–4.19] | 4.31 [4.31–5.02] |
| concurrent | 256 | 0 | 2 | 4.67 [4.10–6.56] | 4.34 [3.63–4.73] | 3.31 [2.13–4.22] | 3.13 [2.31–3.43] |
| concurrent | 256 | 0 | 4 | 2.88 [1.76–3.11] | 2.22 [2.21–2.63] | 2.98 [1.57–3.06] | 3.05 [2.29–4.11] |

结论与下一步：

- 256映射下，所有非空洞控制场景在四组的每轮比值均大于1。25%空洞组的四个
  中位数为6.34–6.66，支持保留搜索去重；这是特定工作负载的复现，不是全局加速承诺。
- 小规模并发不能视作已解决。wasm64的16背景映射、2线程组在两轮中位数分别为0.65、
  0.66；第二轮三次均小于1。批量平均mmap延迟在run 1约为off 10.195/on 15.723 µs，
  run 2约为off 21.309/on 34.814 µs。需要定位额外遍历、锁竞争、JIT及调度的贡献，
  不能直接把全部差异归因于标记重置，也不能以其它组提速掩盖这一退化。
- 当前仅两个独立workflow run，不做显著性检验。下一项性能实验应在保留“关闭去重”
  和“当前重置式去重”两条基线的前提下，评估更低开销的generation tag或其它方案；
  若采用generation tag，需覆盖计数器回绕、并发、解除与backing重用的差异测试。
- 文件映射仍是后续平台能力工作；本轮数据不会开放文件请求、共享回写、透明fork
  或页保护，也不会把内核改为softmmu。

## Generation tags 受控实验（尚待验证）

实验源码位于musl的`codex/mmap-generation-tags`分支，集成位于distro的
`codex/mmap-generation-experiment`分支。默认仍是重置式去重，关闭去重的基线也保持可用。
本实验不修改Linux、LLVM、UAPI或指针访问方式。

设置musl的`generationMmapSearch = true`后，每次普通backing搜索递增epoch，
用每个backing的tag跳过本轮已搜索的对象，避免每轮先遍历全部live mappings清零标记。
epoch和tag均由原有mutex保护；候选顺序、backing生命周期和锁内zero-fill保持不变。
计数器达到`SIZE_MAX`时，先清除所有仍可达backing的tag，再从1开始，避免复用epoch时
误跳过候选。新backing的tag初始化为0；callback clone会连同分配器状态复制这些字段。

`generationEpochLimit = 3`仅用于强制回绕检查，不用于性能采样。
定向checks包括`mmap-search-generation-correctness`及其`-wasm64`版本、
`mmap-search-generation-wrap-correctness`及其`-wasm64`版本，另有
`mmap-search-generation-wrap-clone-no-vm`快照检查。mmap正确性源码同时覆盖拆分、解除、
backing重用、内容保持和并发；强制回绕复用同一源码，不用简化模拟器替代实际运行路径。

实验工作流入口：

```sh
gh workflow run mmap-benchmark.yml --repo HighCWu/distro \
  --ref codex/mmap-generation-experiment -f comparison=generation-vs-reset
```

该comparison的`off`表示重置式去重，`on`表示generation tags；原comparison
`reset-vs-disabled`仍表示off关闭去重、on重置式去重。必须读取provenance中的comparison，
不能仅凭文件名推断基线含义。两个profile分别先执行强制回绕检查，再各启动两种模式的
完整正确性测试；32位profile另执行clone快照检查，最后按原方法采样三个配对boot。
每组CSV仍可使用`compare_mmap_benchmarks.py`分析，此时off/on比值是reset/generation。

[首次实验CI](https://github.com/HighCWu/distro/actions/runs/37413862807)尚未完成。
只有正确性和完整采样通过后才能归档性能结论；若小规模并发没有稳定改善，不能把
标记重置宣称为此前退化的唯一原因，也不能仅凭大规模组收益切换默认策略。
