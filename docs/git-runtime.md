<!-- SPDX-License-Identifier: MIT -->

# Git 安装系统与 wasm64 接入

distro `7967691` 在既有 Git 2.55.0 配方上增加显式 `git-wasm64`，保持默认
`git` 为 wasm32。64 位变体选择匹配的 stdenv、平台、BusyBox、zlib、curl、
OpenSSL 和 Linux 运行检查器；CA 证书数据复用原配方，不混用 32 位静态库。

两个位宽都在安装后读取 `/usr/bin/git` 和独立的
`/usr/libexec/git-core/git-remote-http` 实际字节，要求单一、匹配位宽的共享
`env.memory` 导入及平台内存上限。这是声明检查，不证明实际分配了上限容量。

## 运行检查

复用原有三组安装系统语料，不另写更弱的 64 位替代测试：

- `workflow`：提交、差异、分支、快进、冲突合并、标签、对象读回、hook 和 pager。
- `packing`：24 次提交、对象往返、双线程 repack、严格 fsck、gc 和打包后历史读回。
- `remote`：AF_UNIX credential cache 的存取/退出，以及通过 Linux loopback TCP
  和 BusyBox httpd 进行 dumb HTTP 发现、clone、对象与提交一致性检查。

重型构建和实际 Linux/Wasm 运行只在公开 GitHub Actions 执行，例如：

```sh
gh workflow run ci.yml --repo HighCWu/distro --ref codex/mmap-initialized-backing \
  -f heavy-check=git-wasm64-check-workflow
```

另有 `git-wasm64-check-packing`、`git-wasm64-check-remote`；默认 32 位对应
`git-check-workflow`、`git-check-packing`、`git-check-remote`。

新增三项宿主契约检查验证依赖选择、已安装二进制检查和共享语料接线；与 libcurl
开发包/Python 根盘相关检查合计 17 项通过，格式、工作流和仓库检查通过。
这些不是目标运行证据。首次 wasm64 workflow 与新增 ABI 门禁后的 wasm32
workflow 已提交 CI，均固定 `7967691`：
[wasm64](https://github.com/HighCWu/distro/actions/runs/39086333120)、
[wasm32](https://github.com/HighCWu/distro/actions/runs/39086335957)。wasm32 已成功，
实际日志确认 Git 主程序及 HTTP helper 的共享 memory32 / 4 GiB 声明门禁，以及
workflow 的最终 pass。wasm64 也已成功，实际日志确认两个 Git 程序的共享
memory64 / 16 GiB 声明门禁与 workflow 最终 pass；不代表实际分配 16 GiB。
两项结果均不覆盖随后新增的许可材料检查；
packing、remote 的后续验收见下文。
`7967691` 尚未提供 Git 浏览器用例；后续入口见下文。

## 选定许可材料的安装检查

`1c0ba14` / `f9da168` 为两个位宽安装 `/usr/share/licenses/git`，保存原始
Git COPYING、SHA-1 collision-detection 与 reftable 许可证，以及六份 bundled
regex 源文件中的原始声明。另保存默认 posix_spawn 补丁、说明和检查工具 MIT
文本，并从实际链接的 curl 输出复制 libcurl、zlib、OpenSSL、musl、compiler-rt
及 libcurl 集成的选定声明。原始输入字节不被修改，清单覆盖安装文件。

三组 Linux 运行语料均先要求这份材料非空且校验匹配。新增四项宿主检查执行
实际安装脚本、逐项输入缺失/为空和安装后缺失/为空/篡改负向控制，并验证
BusyBox 校验命令；加上既有位宽契约共七项通过。配套 shellcheck、shfmt、Nix
格式、工作流和仓库检查通过。这不是目标安装或法律充分性的证明。

新版 [wasm64 packing](https://github.com/HighCWu/distro/actions/runs/39086736753)
和 [wasm32 remote](https://github.com/HighCWu/distro/actions/runs/39086740378)
已提交 CI，均固定 `f9da168`；此前 `7967691` 的双位宽 workflow 不含这套材料
门禁，不以其结果替代新版证据；仍运行的任务不取消或重启。
原 workflow 成功后，也以同一 `f9da168` 提交
[wasm64 remote](https://github.com/HighCWu/distro/actions/runs/39086895924)。

上述 wasm32 remote、wasm64 packing 和 remote 均已失败在材料检查入口，三份
实际日志均为 `sh: set: -eu:
invalid option`，尚未运行 credential cache 或 HTTP 传输。默认 shell 是 hush，
固定的 BusyBox 源码中没有 nounset (`-u`) 支持；宿主的 BusyBox ash 并不能证明
该选项在目标 hush 可用。`979c403` 改为逐项显式失败检查，保留全部文件非空及
checksum 断言，不把失败重分类成已通过，也不靠删除检查放行。新增轻量防回退
契约，目标复验随下述新版提交；保留旧失败记录，不以新版本覆盖旧结果。

这些是选定声明和默认补丁，不是完整对应源码。自定义 derivation overrides
必须另收集自己的修改；未自动推断所有依赖、许可证兼容性或发布资格。
特别是 `NO_OPENSSL` 只关闭 Git 的直接 OpenSSL 调用，libcurl 仍静态链接
OpenSSL；这里不为 Git 授予或推定 OpenSSL 例外，发布前须单独审查该组合。

## 浏览器安装系统验收入口

`d5bc3bb` 新增四个独立检查入口：`browser-tests-check-git-wasm32-chromium`、
`browser-tests-check-git-wasm32-firefox`、`browser-tests-check-git-wasm64-chromium`
和 `browser-tests-check-git-wasm64-firefox`。例如公开 CI 调用：

```sh
gh workflow run ci.yml --repo HighCWu/distro --ref codex/mmap-initialized-backing \
  -f heavy-check=browser-tests-check-git-wasm64-chromium
```

浏览器复用三组 Node 检查的相同 initramfs、完整 ext4 安装根盘与匹配位宽内核，
每组独立启动、修改临时内存盘，并等待成功关闭。不是运行浏览器宿主 Git，也不
以临时 initramfs 内的替代程序冒充安装产物。不会复用上一组内存或提供持久化承诺。

共享脚本先核对 Git 自报的 `long`、`size_t` 与固定平台位宽，再核对选定材料，
完成对应 workload 后才输出阶段及 pass。该自报不替代构建时对主程序和 HTTP
helper 的实际 Wasm 内存声明检查，也没有额外宣称指针运行时自检。
浏览器必须看到正确位宽、材料、对应场景和最终 pass，且没有 fail；精确三项
报告门禁拒绝缺项、额外用例、跳过或重试。

新增宿主检查覆盖真实共享脚本的位宽/材料失败、三个镜像加载失败、场景/ABI/
材料/pass 缺失、失败标记及报告损坏；Git 相关 15 项通过，连同 Python 浏览器及
关闭生命周期回归共 36 项通过。另有既有运行与报告检查整组 34 项通过；这些
分组有重叠，不能相加当作独立测试数。格式、语法、shellcheck、工作流、仓库与
轻量前端打包通过，实际浏览器和新脚本的目标执行仍须另验。

首轮 [wasm64 Chromium](https://github.com/HighCWu/distro/actions/runs/39087516919)、
[Firefox](https://github.com/HighCWu/distro/actions/runs/39087519457) 与修正后的
[wasm32 remote](https://github.com/HighCWu/distro/actions/runs/39087522099) 已提交，
均固定 `d5bc3bb`，计划解析均已成功。wasm32 remote 已失败，实际日志为
`fatal: could not open '/dev/null' for reading and writing: No such file or directory`；
预检发生在 devtmpfs 挂载前，尚未进入远程工作负载。`3723338` 把三组预检移至
设备初始化后，并添加顺序防回退断言。两项旧浏览器任务随后均已失败，各三项
用例失败，实际日志同样显示预检无法打开 `/dev/null`，尚不构成应用场景验收；
wasm32 浏览器入口本轮尚未触发。不用旧 workflow 的成功替代
这套带位宽与材料门禁的新版本证据，也不以本机回归宣称浏览器已通过。

## 可复用 wasm64 Git 根盘

`348d428` 增加可选的 `guest-agent.nativeWasm64.rootfsGitExt4`：复用原生启动盘，
只安装匹配位宽的 BusyBox、Git 和 CA 证书，不混入上述测试脚本，也不改变默认
最小根盘。`256M` 是 ext4 磁盘容量，不是线性内存上限或 Git 可用内存保证。
这是运行配方，不是已完成许可审查的二进制发行版。

`guest-agent-check-git-root-wasm64` 使用公开 SDK，在第一台 Linux 实例中初始化
仓库、提交含全部字节值的 65,553 字节文件、执行 hook 和双线程 repack，然后
sync 并完整关闭。仅保留 ext4 块数据，第二台新实例校对 HEAD、工作文件、对象
及 hook 标记，再通过 `clone --no-local` 执行子进程传输、严格 fsck 和精确字节读回。
路径包含引号、字面 `$HOME` 和 Unicode，不经宿主 shell 展开。

同时要求测试专用文件不存在、Git 自报 long/size_t 为 8 字节、选定许可文件非空
且 checksum 匹配、CA 数据存在、两个实例均发生块写入和 flush，并成功关闭。
不验证断电一致性、公共远程服务或 HTTPS 握手，也不代表 SDK 提供 PTY。

共享工作负载在宿主真实 Git 上通过正向及五类反例：工作文件改变、HEAD 改变、
pack 损坏、hook 标记改变、仓库缺失。连同根盘接线、材料与浏览器契约共 23 项
轻量检查通过。新增代码没有引入类型错误；完整本地类型门禁仍因旧 kernel dist
声明缺少 `FSDirectoryEntry.type` 的三项既有错误失败，不隐瞒或跳过它们，公开 CI
仍执行使用新构建声明的完整类型检查。实际 Wasm 根盘验收另由公开 CI 执行。

以下三项均固定 `348d428`，已经触发，验收状态如下；旧浏览器任务确认终态后，
也以同一版本提交 Chromium/Firefox 复验，不取消或重启仍在运行的任务：

- [Git SDK 跨实例根盘](https://github.com/HighCWu/distro/actions/runs/39088291953)
- [wasm32 remote 修复复验](https://github.com/HighCWu/distro/actions/runs/39088294722)
- [wasm64 packing 修复复验](https://github.com/HighCWu/distro/actions/runs/39088297352)

其中 wasm32 remote 已成功，实际日志确认主程序和 HTTP helper 的共享 memory32 /
4 GiB 声明、32 位 long/size_t、选定材料校验、credential cache 与 Linux 回环 HTTP
发现/clone 阶段标记及最终 pass。结果固定 `348d428`，不包括下述新增构建材料，
不扩大为浏览器、公共网络、HTTPS 或任意远程服务已通过。wasm64 packing 也已
成功，实际日志确认两个 Git 程序的共享 memory64 / 16 GiB 声明、64 位 long/size_t、
材料校验、对象往返、双线程 repack、严格 fsck、gc、打包历史及最终 pass；
不代表实际分配 16 GiB。根盘和双浏览器任务仍待验收，不因等待取消或重启。

## 选定构建材料与公开 CI 附件

`e6f20b8` 为两个位宽增加独立的 `git.buildMaterials` /
`git-wasm64.buildMaterials` 输出；默认安装仍只选 `out`，保持 `/usr` 运行布局，
材料不进入根盘。留存实际生成的 Makefile 跟踪文件、原始 COPYING、集成配方、
按顺序应用的全部配置补丁、编译器版本、静态选项和选定源/库身份。
`sourceIdentity` 取最终 derivation 的源输入，补丁序列取最终配置而不是硬编码默认补丁。

以 NUL 分隔数据保留传给 make 的额外参数，以及白名单中的
`NIX_CFLAGS_COMPILE`、`NIX_CFLAGS_LINK`、`NIX_LDFLAGS`；不导出整个构建环境，
也不执行生成的 `GIT-BUILD-OPTIONS`。上游在有效 `ALL_LDFLAGS` 为空时可能不生成
`GIT-LDFLAGS`，因此另用状态文件明确记录存在或缺失，不伪造上游内容。
最终程序与 HTTP helper 的摘要在 fixup 后生成，避免将中间产物当作安装字节。

新增 `git-check-build-materials` 和 `git-wasm64-check-build-materials`：
检查材料清单、最终程序摘要、平台元数据、原始许可及配置补丁字节、实际 Wasm
内存 ABI，并要求材料不泄漏到运行输出。公开 CI 只在该检查成功后复制材料与
验证清单，再次校验复制结果并上传三天有效的附件。附件不包含 Git 二进制，也
不是长期源码分发渠道。

新增六项宿主检查覆盖真实收集脚本、必需输入逐项缺失/为空、编译器失败/空输出、
补丁顺序、材料/程序篡改和真实 CI 收集 shell 的双位宽及失败分支。连同既有
Git 与浏览器轻量回归共 29 项通过；shellcheck、Nix/JS 格式、工作流语法、仓库
元数据、source pin 和十项缓存契约检查通过。目标构建和附件上传仍须公开 CI 验收。

这些是选定配置记录和二进制摘要，仍非完整对应源码、SBOM、离线重构环境或
静态链接许可批准。特别是 Git/libcurl/OpenSSL 的既有审查边界没有因留存材料而消失。

固定 `e6f20b8` 的 [wasm32 材料验证](https://github.com/HighCWu/distro/actions/runs/39088834446)
与 [wasm64 材料验证](https://github.com/HighCWu/distro/actions/runs/39088837826)
已提交公开 CI，实际构建、验证及附件上传仍待验收，不用宿主结果替代。

## 保留的边界

生产内核仍为 `CONFIG_MMU=n` 和有界 direct linear memory，不加入内核 softmmu。
Git 继续使用上游 `NO_MMAP` 的读取/复制替代路径；私有匿名 mmap 不满足其对象和
索引的文件映射需求。进程启动继续使用既有 `posix_spawn` 补丁，不声称支持普通
fork；后台 daemonize 仍明确失败。上述 HTTP 检查不证明公共网络、HTTPS、SSH
传输或任意远程托管服务已经兼容。

Git 及其静态依赖保留各自实际许可证，不能把 Git 二进制或整套系统称为 MIT。
新增宿主测试采用 MIT，不改变 Git 补丁的上游许可边界。本阶段未完成 Git 的完整
对应源码包、链接许可审查或长期二进制发行，不能据运行检查推断发布义务已经满足。
