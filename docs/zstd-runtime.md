<!-- SPDX-License-Identifier: MIT -->

# 原生 Zstandard：双位宽构建与字典加载

状态更正：固定 `73cf891` 的 [wasm64 检查](https://github.com/HighCWu/distro/actions/runs/38987437765)
和 [wasm32 检查](https://github.com/HighCWu/distro/actions/runs/38987438669) 均已失败，
不能作为可用包或字典映射的通过证明。wasm64 实际日志明确为字典压缩时 error 34 /
Invalid argument，随后触发运行失败标记。生产内核 mmap wrapper 仍拒绝文件映射；
专用文件映射测试路径不能等同于默认配置已开放该能力。
`fa3eaa7` 已修正此错误验收假设，改为验证 malloc/read 字典与明确拒绝强制文件映射；
该轮双位宽均已通过前置字典断言，但随后失败在二进制语料生成，仍不能宣称包通过。
根盘切换时卸载了启动 devtmpfs，测试没有重新挂载便读取 `/dev/zero`；`79bd2b3`
补上显式设备挂载并保留 dd 的错误输出，新双位宽验收已提交。

distro `73cf891` 增加显式 `zstd-wasm64`，默认 `zstd` 仍为 wasm32。
两者复用固定的 Zstandard 1.5.6 源码、静态 CLI 构建与同一安装系统运行语料。
wasm64 覆盖 stdenv、BusyBox、musl、compiler-rt、platform 和测试镜像构造器，
不将 wasm32 二进制装进 wasm64 根盘。暂不启用 Zstandard 多线程压缩，也不发布
开发用 libzstd 头文件/静态库；本次交付对象是 CLI。

## 字典加载与文件映射边界

普通字典默认使用上游 malloc/read 路径，`--no-mmap-dict` 也显式选择该路径，
无需恢复早期排除所有 Wasm POSIX 映射代码的补丁。当前仅保留失败检查修正：
mmap 失败应比较 `MAP_FAILED`，不能比较 NULL。
`--mmap-dict` 仍发起真实文件映射请求，默认生产内核返回 EINVAL，Zstandard 报错退出；
不能静默改为 malloc 再把它称作映射成功。

此修正没有开放内核文件映射、不引入 softmmu，也不承诺按需分页、只读保护或零拷贝。
大字典 patch-from 模式可能自动选择映射；本轮不将其列为已支持场景，必要时应显式
指定 `--no-mmap-dict` 并确保有足够线性内存。

## 检查与证据边界

构建时检查实际 CLI 的共享 `env.memory` 导入、32/64 位宽及平台声明上限。
双位宽安装系统语料检查：

- 普通文件压缩/解压逐字节往返，以及截断压缩流必须失败。
- 默认与显式 malloc 字典交叉压缩/解压，逐字节比较。
- 强制映射压缩与解压均须退出 34、报告 Invalid argument，且不输出数据。
- 超过 1 MiB、含 NUL 和非 UTF-8 尾部的二进制文件与管道往返。
- 安装后的 Zstandard、musl、compiler-rt 许可证文本非空。

公开 Actions 的检查名为 `zstd-check-roundtrip` 和 `zstd-wasm64-check-roundtrip`；
旧 `73cf891` 两项均失败，新 `fa3eaa7` 的
[wasm32](https://github.com/HighCWu/distro/actions/runs/38993962502) 和
[wasm64](https://github.com/HighCWu/distro/actions/runs/38993963650) 均失败在 binary generation，
此前已执行到字典验证完成标记；不代表整个运行通过。
它们在 Node 承载的真实 Linux
安装系统运行，不是浏览器 Zstandard 工作负载验收。

轻量宿主检查可运行：

```console
node --test sources/distro/distro/zstd/roundtrip-host.test.js
```

需要宿主 Node 和 Zstandard CLI。八项检查已通过，验证共享工作负载及故障断言，
包括普通字典失败、错误映射退出码/诊断、静默 fallback、拒绝后输出和损坏流。
宿主真实执行普通字典及二进制/管道往返，模拟强制映射拒绝，因为宿主支持文件映射。
宿主 mount 由受控 fixture 截获，不会挂载或覆盖开发机器的 `/dev`，另验设备准备失败
必须阻止继续执行压缩语料。
宿主 CLI 不来自本项目工具链，许可文件是编排 fixture，不能作为 Wasm 映射 ABI、
目标失败分支或发布许可完整性的证明。
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
