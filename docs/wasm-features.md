<!-- SPDX-License-Identifier: MIT -->

# WebAssembly 特性采用策略

本项目只把主流目标 runtime 已稳定发布、并且确实改善 Linux/Wasm 实现的能力放入正式
profile。进入标准或浏览器并不等于应立即成为默认编译选项；每项能力还必须有明确用途、
宿主协商和回归测试。

## 当前 profile

| profile | 定位 | 当前状态 |
|---|---|---|
| `wasm32` | 跨主流浏览器的默认兼容基线 | 内核、runtime、musl和发行版继续默认使用 |
| `wasm64` | Chrome、Firefox及Node等已发布Memory64宿主的实验路径 | 内核可构建；runtime、musl、SDK和发行版尚未形成完整交付闭环 |

`HighCWu/linux` 的Memory64内核路径参考了
[`joelseverin/linux-wasm`](https://github.com/joelseverin/linux-wasm)及其
[`joelseverin/linux`](https://github.com/joelseverin/linux)实现，但保留了本项目较新的
Linux 7.1基线、设备树、virtio、独立用户memory和远程uaccess架构。它不是整树合并，
也不会让wasm64取代默认wasm32构建。

当前wasm64内核使用：

- `CONFIG_MMU=n`和64位Linux数据模型；
- shared Memory64，当前链接上限为16 GiB；
- 64位memory和table索引所需的BigInt宿主边界；
- 与wasm32分离的defconfig及CI产物。

内核成功链接只证明内核侧代码生成闭环，不代表wasm64用户程序已经可运行。完整支持仍需
逐项完成宿主BigInt转换、wasm64 musl ABI、compiler-rt/sysroot、用户模块装载以及真实
浏览器启动测试。

## 已稳定但按需采用

- **Tail Calls**：只有在调度、trampoline或语言runtime基准证明有收益时才加入相应
  profile；不会仅因引擎支持而无条件打开。
- **Final Exception Handling**：当前内核仍使用Wasm SjLj路径。切换前必须验证内核、
  musl、C++异常和跨实例边界，不能只替换一个编译参数。
- **JSPI**：适合不能阻塞宿主线程的异步适配。当前Worker与`Atomics.wait`路径不依赖它，
  后续可以作为浏览器宿主的可协商适配，而不是内核ABI前提。
- **Multiple Memories**：可以用于特定宿主fast path，但在浏览器覆盖和收益验证完成前，
  不作为默认启动条件。本项目现有的内核memory与每进程用户memory分离也不要求模块
  必须使用multiple-memory指令。

## 不进入当前实现

仍处于提案阶段、尚未达到目标浏览器稳定发布条件的能力不得成为构建或运行前提，包括：

- Memory Control及`memory.discard`；
- Stack Switching；
- Custom Page Sizes；
- Shared-Everything Threads等尚未稳定的扩展。

这些能力可以在独立实验分支评估，但不能写进已发布psABI，也不能用来声称已经恢复
`mmap()`、`fork()`或MMU语义。采用状态应以
[WebAssembly Feature Status](https://webassembly.org/features/)和项目实际浏览器矩阵
为准。
