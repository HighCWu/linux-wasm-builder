<!-- SPDX-License-Identifier: MIT -->

# 原生 Zstandard：双位宽构建与文件映射

状态更正：固定 `73cf891` 的 [wasm64 检查](https://github.com/HighCWu/distro/actions/runs/38987437765)
和 [wasm32 检查](https://github.com/HighCWu/distro/actions/runs/38987438669) 均已失败，
不能作为可用包或字典映射的通过证明。wasm64 实际日志明确为字典压缩时 error 34 /
Invalid argument，随后触发运行失败标记。生产内核 mmap wrapper 仍拒绝文件映射；
专用文件映射测试路径不能等同于默认配置已开放该能力。下面记录的是接入尝试与目标，
其中“当前平台已经提供私有文件映射”的原判断不成立，需修正集成后再验收。

distro `73cf891` 增加显式 `zstd-wasm64`，默认 `zstd` 仍为 wasm32。
两者复用固定的 Zstandard 1.5.6 源码、静态 CLI 构建与同一安装系统运行语料。
wasm64 覆盖 stdenv、BusyBox、musl、compiler-rt、platform 和测试镜像构造器，
不将 wasm32 二进制装进 wasm64 根盘。暂不启用 Zstandard 多线程压缩，也不发布
开发用 libzstd 头文件/静态库；本次交付对象是 CLI。

## 恢复上游文件映射路径

原补丁因早期 Wasm musl 不声明 mmap/munmap，强制字典使用 malloc fallback。
该次接入尝试不再排除 `__wasm__` 的 POSIX 字典路径，但默认生产配置并不支持该请求。
仅保留对上游失败检查的修正：mmap 失败应比较 `MAP_FAILED`，不能比较 NULL。
`--mmap-dict` 显式进入该路径，`--no-mmap-dict` 仍保留原始 malloc 路径。

这使用真实 linear-memory 指针和现有 NOMMU 文件映射，不引入 softmmu，
不承诺原生硬件 MMU 的按需分页、只读保护或零拷贝性能。

## 检查与证据边界

构建时检查实际 CLI 的共享 `env.memory` 导入、32/64 位宽及平台声明上限。
双位宽安装系统语料检查：

- 普通文件压缩/解压逐字节往返，以及截断压缩流必须失败。
- 映射字典压缩和解压，以及同一压缩数据由 malloc 字典解压。
- 超过 1 MiB、含 NUL 和非 UTF-8 尾部的二进制文件与管道往返。
- 安装后的 Zstandard、musl、compiler-rt 许可证文本非空。

公开 Actions 的检查名为 `zstd-check-roundtrip` 和 `zstd-wasm64-check-roundtrip`；
两项新版均已运行失败，实际字典路径没有通过。它们在 Node 承载的真实 Linux
安装系统运行，不是浏览器 Zstandard 工作负载验收。

轻量宿主检查可运行：

```console
node --test sources/distro/distro/zstd/roundtrip-host.test.js
```

需要宿主 Node 和支持 `--mmap-dict` 的 Zstandard CLI。三项检查已通过，验证共享
工作负载及故障断言；宿主 CLI 不来自本项目工具链，测试中的许可文件是编排 fixture，
不能作为 Wasm 映射 ABI、目标失败分支或发布许可完整性的证明。
补丁已对上游固定版本的 fileio.c 验证无 fuzz 应用。

## 浏览器使用方向

待原生检查通过后，可从公开 CI 构建 `.#zstd-wasm64`，将静态 `bin/zstd` 命名为
`zstd.wasm`，通过独立示例的程序选择器导入。使用文件 stdin 和参数
`["-q", "-f", "-o", "/root/result.zst"]` 可以把输入压缩到临时 Linux 文件，再用
下载控件取回；输出下载仍受示例的 16 MiB 上限约束。此流程尚未专门完成浏览器验收，
不能把示例自有 C 程序的通过结果推广到 Zstandard。

Zstandard 保持上游双许可证，包选择 BSD-3-Clause 分支，并随静态 CLI 安装所用
musl 和 compiler-rt 的许可证文本。新增集成/测试采用 MIT，不将 MIT 声明用于
重新许可上游源码。文本和元数据不替代完整对应源码、SBOM 或发布合规审计。
