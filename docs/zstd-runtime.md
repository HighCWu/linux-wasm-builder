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
补上显式设备挂载并保留 dd 的错误输出，新双位宽验收均已通过并核对实际日志。

distro `73cf891` 增加显式 `zstd-wasm64`，默认 `zstd` 仍为 wasm32。
两者复用固定的 Zstandard 1.5.6 源码、静态 CLI 构建与同一安装系统运行语料。
wasm64 覆盖 stdenv、BusyBox、musl、compiler-rt、platform 和测试镜像构造器，
不将 wasm32 二进制装进 wasm64 根盘。暂不启用 Zstandard 多线程压缩，也不发布
开发用 libzstd 头文件/静态库；本次交付对象是 CLI。

## 下一阶段：文件 mmap 真实软件目标

当前 distro `7134a84` 的候选演进增加普通磁盘与可写文件字典的强制标准 mmap，
五种合规尺寸须成功、超限仍拒绝；实际新目标尚待验收。默认配置仍不开放文件
映射，不将下文历史不可变来源通过自动扩大到新范围。详见
[普通文件复制](file-mmap-candidate.md#当前演进普通文件-nommu-私有复制)。

Zstandard 被选为[文件 mmap 就绪度阶段](file-mmap-readiness.md)的真实软件目标。
`b662d58` 新增安装系统边界语料覆盖 64 KiB 和 128 KiB 两侧共六种字典尺寸；普通/read 路径
必须成功，可变文件的强制 mmap 仍须明确拒绝，不把应用回退算作文件映射成功。
扩展后的宿主 10 项检查已通过，包含边界加载失败和只在边界静默映射成功的反向控制；
[wasm64 检查](https://github.com/HighCWu/distro/actions/runs/39009756964) 已成功，日志确认
六种边界尺寸及最终 pass。[首次 wasm32 检查](https://github.com/HighCWu/distro/actions/runs/39009753274)
失败在源码下载 HTTP 429，并未运行应用；[重试](https://github.com/HighCWu/distro/actions/runs/39010264830)
已成功，实际日志确认六种边界及最终 pass。此前记录的两条运行链接位宽标注反了，
此处已按实际 heavy job 名称更正。
原先成功的 `79bd2b3` 不包含本次扩展。
生产内核与 libc 不变，不承诺已支持原 Zstd 的 PROT_READ 文件映射。

### 认证不可变字典候选验收

distro `910c438` 增加 `zstd-check-file` / `zstd-wasm64-check-file` 聚合检查，
不更改默认 `zstd` / `zstd-wasm64` 的链接导出、默认内核或 SDK。测试变体仅通过
`overrideAttrs` 添加 `-Wl,--export=__wasm_mmap_init_v1`；保留原 Zstandard 源码和
现有 MAP_FAILED 检查补丁，不将 PROT_READ 改成 RW，不替换应用 syscall 或解引用。

聚合包含两种真实 Linux/Wasm 执行环境：

- 候选内核、原始 initramfs 中的 CLI/BusyBox，以及两个内容相同的 EROFS 字典盘。
  只有第一个盘是认证私有快照；第二个虽只读且内容相同，也必须拒绝映射。
- 默认内核和带初始化导出的 CLI，重新运行完整普通/read 字典及映射拒绝基线。
  不能仅因增加链接导出就改变默认准入。

候选工作负载对 65535、65536、65537、131071、131072 字节字典，分别强制 mmap
压缩和解压，并与 malloc/read 交叉解码逐字节比较。131073 字节须报 ENOMEM；
普通只读盘和可变 initramfs 文件须报 EOPNOTSUPP，超限时先报 ENOMEM。
拒绝请求的压缩/解压均须退出 34、匹配 musl 诊断且不输出数据。既有默认基线还
要求默认内核返回 EINVAL，防止上游强制路径静默 fallback 后被当成映射成功。
这仍是有界主动复制，不是零拷贝、按需分页或可强制执行的只读保护。

新增 11 项宿主检查，加上原基线共 21 项已通过。正向操作使用本机原生 Zstandard
真实 mmap，认证来源、容量拒绝和挂载由受控 fixture 模拟；反向控制覆盖压缩/解压
失败、交叉解码损坏、错误退出码/诊断、拒绝后输出，以及仅放行超限可变来源。
它们不证明本项目 Wasm CLI、执行 ABI、VFS 来源认证或内核准入已可用。

首次双位宽 CI（distro `7cd56aa`）均止于 Nix 计划检查：内部 finalPackage 没有
callPackage 外层的 `.override`。`910c438` 改用 `.overrideAttrs`；首轮未运行应用，
不能当作映射成功或失败证据。修正后的
[wasm32](https://github.com/HighCWu/distro/actions/runs/39025307814) 和
[wasm64](https://github.com/HighCWu/distro/actions/runs/39025311008) 均已成功。
已核对两个 heavy job 的实际日志，均包含五个强制映射尺寸、131073 字节超限拒绝、
普通/可变来源拒绝和候选最终 pass；默认配置还包含 malloc/read、六个尺寸拒绝及最终 pass。
因此可以确认该有界候选在 Node 承载的真实 Wasm/Linux CLI 上工作，不是宿主 mock
或应用 malloc fallback 的结果；默认发布配置仍不开放文件映射。
标准入口自身的结果见[候选文档](file-mmap-candidate.md)。所有重型构建均在公开 Actions 进行。

distro `0d473c2` 进一步增加双位宽 Chromium/Firefox 的候选验收：直接复用同一
字典盘、CLI 和 shell initramfs，不在页面 JavaScript 重写压缩/映射逻辑。
每个浏览器检查须实际通过标准 mmap 和 Zstd 两项测试，并校验五个尺寸和来源/容量拒绝
完成标记；精确报告门禁拒绝额外/缺失测试、跳过、预期失败和重试。
四组浏览器结果均已成功，实际日志确认五个强制映射尺寸、容量/来源拒绝和两个最终 pass，
各 2 项测试通过，精确报告门禁确认零跳过、零重试。固定 Chromium 149.0.7827.55、
Firefox 151.0；链接见[候选记录](file-mmap-candidate.md)。不泛化到其他版本、默认配置
或超过首批限制的来源/容量。性能另见[配对诊断](file-mmap-performance.md)。

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

固定 `79bd2b3` 的 [wasm32](https://github.com/HighCWu/distro/actions/runs/38995246467)
与 [wasm64](https://github.com/HighCWu/distro/actions/runs/38995247423) 均成功，实际日志
包含 `zstd: malloc dictionaries verified; forced file mapping rejected` 和最终 pass 标记，
说明上述默认字典、显式 malloc 字典、映射拒绝、二进制文件/管道、损坏流及许可证
断言全部执行完成。实际 CLI 共享 env.memory 和位宽检查也通过，wasm32 上限 4 GiB，
wasm64 声明上限 16 GiB；这不是对应容量已全部分配的证明。

轻量宿主检查可运行：

```console
node --test sources/distro/distro/zstd/roundtrip-host.test.js
```

需要宿主 Node 和 Zstandard CLI。原基线十项检查已通过，验证共享工作负载及故障断言，
包括普通字典失败、错误映射退出码/诊断、静默 fallback、拒绝后输出和损坏流。
宿主真实执行普通字典及二进制/管道往返，模拟强制映射拒绝，因为宿主支持文件映射。
宿主 mount 由受控 fixture 截获，不会挂载或覆盖开发机器的 `/dev`，另验设备准备失败
必须阻止继续执行压缩语料。
宿主 CLI 不来自本项目工具链，许可文件是编排 fixture，不能作为 Wasm 映射 ABI、
目标失败分支或发布许可完整性的证明。
补丁已对上游固定版本的 fileio.c 验证无 fuzz 应用。

## 浏览器使用方向

原生 Node 检查已通过，可从公开 CI 构建 `.#zstd-wasm64`，将静态 `bin/zstd` 命名为
`zstd.wasm`，通过独立示例的程序选择器导入。使用文件 stdin 和参数
`["-q", "-f", "-o", "/root/result.zst"]` 可以把输入压缩到临时 Linux 文件，再用
下载控件取回；输出下载仍受示例的 16 MiB 上限约束。此流程尚未专门完成浏览器验收，
不能把示例自有 C 程序的通过结果推广到 Zstandard。

Zstandard 保持上游双许可证，包选择 BSD-3-Clause 分支，并随静态 CLI 安装所用
musl 和 compiler-rt 的许可证文本。新增集成/测试采用 MIT，不将 MIT 声明用于
重新许可上游源码。文本和元数据不替代完整对应源码、SBOM 或发布合规审计。
