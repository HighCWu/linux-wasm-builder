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
