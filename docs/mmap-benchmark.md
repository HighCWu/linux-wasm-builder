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
