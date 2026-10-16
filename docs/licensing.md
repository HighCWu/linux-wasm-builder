<!-- SPDX-License-Identifier: MIT -->

# 许可证与发行政策

## 政策目标

项目支持开源社区、个人开发者、研究和商业使用。架构和发行流程应让第三方像在普通
Linux 用户态上一样，根据自身代码及所用依赖的许可证选择开发与发行方式，包括：

- 使用工具链编译、运行和发布开源或闭源程序；
- 在浏览器或其他 Wasm runtime 中运行这些程序；
- 仅仅使用 Linux syscall/UAPI 不会使用户程序自动继承内核的 GPL 许可证；
- 修改并重新发行宽松许可的宿主、runtime、musl 和工具；
- 在遵守 GPL 的情况下修改并发行 `linux.wasm`。

许可证结论取决于具体组合和发行方式。本文件是工程政策，不替代法律意见。

## 组件许可证

| 组件 | 目标许可证 | 使用和发行边界 |
|---|---|---|
| 本集成仓库自有内容 | MIT | 可被开源或闭源项目复用 |
| 独立 runtime、host SDK及内存兼容支持 | MIT | 可用于不同许可证的程序或宿主 |
| musl修改 | MIT | 用户程序可静态或动态链接 |
| LLVM/Clang/LLD修改 | Apache-2.0 WITH LLVM-exception | 编译输出不因工具链本身被要求采用同一许可证 |
| Meson及其源码补丁 | Apache-2.0 | 保留上游声明；使用构建工具本身不要求应用采用同一许可证 |
| Linux内核修改 | GPL-2.0-only，按文件SPDX | 发行修改后的内核必须履行GPL义务 |
| Linux UAPI headers | GPL-2.0 WITH Linux-syscall-note等 | 正常syscall用户程序不因此成为GPL派生作品 |
| distro/rootfs内容 | 混合许可证 | 必须逐包生成清单并履行各自义务 |

“项目尽量 MIT”意味着把可独立实现的新代码放到 MIT 组件；它不意味着把 Linux、
LLVM 或第三方代码重新标成 MIT。

SDK 的 Meson 归档组修复位于 `sources/distro/distro/sdk/meson-wasm-archive-groups.patch`，
修改上游 `mesonbuild/compilers/mixins/clike.py`，因此保留 Apache-2.0，而不是改标 MIT。
独立的 Nix 集成和行为回归测试采用 MIT。Nix override 继承上游 Meson 包的元数据；
发行含修正版 Meson 的 SDK 时仍应随包保留上游许可证、版权及适用的 NOTICE，标明修改。
这不改变所编译应用自身或其链接依赖的许可边界，也不代表完整 SDK 许可清单已经生成。

SDK 的 SQLite 检查复用固定的 SQLite 3.51.0 上游源码，不修改或重新许可 SQLite。
SQLite 核心由上游声明为 public domain，项目自有的构建集成及运行用例采用 MIT。
这不是将其他发行版软件包或它们的依赖统一改为 MIT；发行时仍需逐项记录来源和许可。

## 用户程序的许可证边界

预期结构与普通 Linux 用户态相同：程序通过 syscall/UAPI 使用内核，而不链接内核
实现。开发者可以选择与自身代码及依赖相容的许可证，并按开源、闭源、非商业或商业
方式发布程序。

```text
user program.wasm
  ├─ links MIT musl/runtime
  └─ uses Linux syscall UAPI + versioned Wasm psABI
                    │
                    ▼
              GPL linux.wasm
```

为了保持这一边界，用户程序不得：

- 包含 Linux kernel object code；
- 链接 Linux 内部函数；
- 把内核私有结构布局作为应用 ABI；
- 将 GPL 库误当作仅因生成 `.wasm` 就不再附带原有许可证义务；
- 依赖把许可证不兼容的紧耦合模块拆成不同文件来规避许可证。

用户态JIT或应用为被模拟程序自行实现的地址翻译，应保持在其适用许可证边界内。
Linux端只通过UAPI/执行ABI与程序交互，不把内核实现链接进用户程序。

## Linux发行义务

向浏览器用户发送 `linux.wasm` 通常是在发行对象代码，而不是单纯服务器内部使用。
每个发行版本都应同时准备：

- 生成该二进制的精确 Linux 源码和本项目补丁；
- `.config`；
- 构建和链接脚本；
- 必要的生成工具说明；
- GPL许可证文本和版权声明；
- 对应版本可长期访问的 source bundle或合规书面要约方案。

仅给出一个会继续变化的 GitHub分支链接，不应作为唯一合规机制。

内核构建现新增 `linux-build/`：在 `make vmlinux.wasm` 之后保存实际最终 `.config`
为 `kernel.config`，复制该源码的原始 COPYING / 完整 LICENSES，记录所选源码和
LLVM 工具链 store 身份、位宽及 debug/test profile，并附构建配方、材料脚本和说明。
这些 store 身份使用拆分 hash，避免仅因身份字符串保留完整构建输入。
`SHA256SUMS` 同时覆盖内核字节和材料；从产物根目录执行
`sha256sum --check linux-build/SHA256SUMS`。npm 内核包将携带此目录，打包解包后
再次核验，不能只验证打包前的源码树。原 npm Linux 许可表达式保留，syscall
exception 依据 Linux 官方 COPYING，不把内核实现改标为 MIT。
5 项宿主测试验证实际材料复制脚本、所需文件缺失/为空或内核不匹配时拒绝，以及
npm 归档往返和篡改检测。新增独立 `kernel-check-build-materials` /
`kernel-wasm64-check-build-materials` 会重新解包实际 npm 产物，逐字节比较所选
Linux 输出中的内核和整套材料，同时核对宿主 MIT 原文及包的名称、版本和许可
声明。宿主故障注入还验证替换配置并重算校验和、改写 MIT 文本或将包声明改成
仅 MIT 均会失败；不能只因某份自带校验和通过就认定来源匹配。
随后 distro `2a21e3a` 的
[wasm64 npm 材料检查](https://github.com/HighCWu/distro/actions/runs/38926460986)
已成功：实际目标构建/检查与整个工作流均通过。该检查强制依赖 Linux 材料/profile
检查，并重新解包真实 npm 包验证字节与声明；它不包含后续完整源码归档功能。
首轮内核材料检查
[38925328081](https://github.com/HighCWu/distro/actions/runs/38925328081)
失败于新 shell 脚本的 treefmt/shfmt 格式门禁，未进入内核编译，不能作为内核功能
失败或材料包通过的证据。已按仓库规则修正格式。npm 定向检查还强制依赖对应的
Linux 材料检查，让内核 profile、原始材料和最终 npm 包在同一构建依赖图中验证，
共享内核构建而不重复安排同一内核的独立作业。
这些只是构建与许可材料，不包含完整 Linux 源码、全套依赖或所有补丁来源，不代表
完整 GPL 对应源码包或已履行全部发行义务；公开源码交付仍需继续建设。

另提供独立 `kernel.sourceBundle` / `kernel-wasm64.sourceBundle`：把选中的完整
Linux 源码输入放入 `linux/`，同一内核的实际配置、原始许可证和构建材料放入
`build-materials/`，流式生成 `linux-source.tar.gz`，不额外复制源码或生成未压缩
tar。源码链接目标保留，归档排序、时间、所有者和 gzip 头固定；宿主测试验证相同
输入生成相同压缩字节、隐藏文件和链接保留、符号链接源码根解析及缺失配置拒绝。
可用 `nix build ./sources/distro#kernel-wasm64.sourceBundle` 构建，外层 SHA256SUMS
校验源码归档与说明，内层材料校验和仍描述对应 npm 二进制，不把内核字节重复打入
源码包。产物设置 Nix 零引用约束，不因生成归档而让运行时继续引用整棵源码。

`kernel[-wasm64]-check-source-bundle` 会执行原内核材料/profile 检查，核验归档
校验和及所选源码 COPYING、实际配置的字节。成功后 CI 上传保留 3 天的源码验证
artifact，关闭二次压缩；它不是长期源码托管。distro `61d552a` 的
[wasm64 源码归档检查](https://github.com/HighCWu/distro/actions/runs/38928012549)
已成功：实际 Nix 归档检查、收集和 artifact 上传均通过，整个工作流成功。
API 确认存在对应提交的约 250 MiB 源码 artifact；仍只保留 3 天，不替代正式
发行所需的长期源码获取渠道，也不代表 wasm32 或完整发行的对应源码已获验证。
源码包不包含完整 distro/LLVM/Nix 依赖和可独立离线重建环境；显式 `patches` 非空时
拒绝导出，避免静默遗漏补丁。其他自定义 hook/override 仍需发行者审查，这不是任意
修改后的最终构建工作树快照，也不代表完整发行的 GPL 义务已经满足。

rootfs中的 BusyBox及其他 copyleft组件也必须单独处理，不能因为它们位于磁盘镜像
中而忽略。

### BusyBox 构建材料与选定源码

distro `aa33c39` 为双位宽 BusyBox 增加独立 `buildMaterials` 输出，保存最终配置、
原始许可证、配方、ABI 检查器及源码/运行库/编译器/内核头文件的 Nix 输入身份；
默认仅安装 `out`，不把这些构建材料复制进根盘。`sourceBundle` 将实际选定的
BusyBox 源码与材料流式归档，并另给最终安装、strip 后的 `bin/busybox` 生成校验和。
配置缺失或材料校验失败时拒绝导出，显式补丁列表非空时也拒绝导出，避免静默遗漏。

源码及材料的宿主测试通过，涵盖重复归档字节一致、特殊目录名、源码链接/硬链接、
配置缺失和材料篡改；该结果不是目标 BusyBox 构建或 Nix 多输出打包已通过的证据。
`busybox[-wasm64]-check-source-bundle` 另核对实际安装字节、内存 ABI、配置和源码
许可证，成功后上传保留 3 天的验证 artifact。复现命令与排除项见源码 BusyBox README。

这仍不是完整对应源码交付：归档未含 musl/compiler-rt、编译器及全部 Nix 依赖源码，
也不是离线重建环境或 SBOM。正式发布还需匹配的 distro checkout/flake.lock、完整
依赖审计和长期源码获取渠道。导出器自有代码采用 MIT，BusyBox 继续遵循 GPL-2.0-only。

首批实际检查固定 `cb275c7`，结果待确认；后续 `6585871` 仅修正材料导出脚本的
shfmt 空白格式，已更新固定版本，宿主归档回归重新通过：

- [wasm64 源码归档](https://github.com/HighCWu/distro/actions/runs/38968663096)
- [wasm32 源码归档](https://github.com/HighCWu/distro/actions/runs/38968669994)
- [wasm64 安装 smoke](https://github.com/HighCWu/distro/actions/runs/38968677130)

## 洁净实现政策

参考其他软件 MMU实现时：

- 先记录来源、许可证和可参考范围；
- 只从文档、公开行为和兼容性测试提取需求；
- 若复用 MIT/BSD代码，保留所需版权和许可证；
- 不从专有实现复制代码；
- 不把 GPL实现复制进 MIT runtime或LLVM；
- 对算法重新实现时保留设计来源说明，避免错误声称完全原创。

## 自动化要求

SDK 现安装 `share/linux-wasm-sdk/licenses/`，并由 `wasm-linux-sdk-info` 的
`paths.licenseTexts` 字段提供位置。材料包括实际选中的 musl COPYRIGHT、Linux
COPYING/完整 LICENSES 目录，以及工具链和运行库对应 LLVM 子项目的 LICENSE.TXT，
另附 SDK 自有代码的 MIT 文本。原始文件不改写，SHA256SUMS 可在该目录核验。
`sources.json` 以 `hashParts` 和 `name` 记录源码 store 身份：先连接两个 hash 片段，
再附加连字符及名称即可还原 basename。不能直接保留裸 store hash，因为 Nix 同样
会把它扫描为引用。材料构建设置 `allowedReferences = []`，由 Nix 拒绝意外的运行
引用；SDK profile 检查还会对安装后的许可目录执行 SHA256SUMS 核验。
来源通过所选 sysroot/工具链传递，不硬编码成与 wasm64 或 override 无关的默认源码。

独立 `sdk-check-licenses` / `sdk-wasm64-check-licenses` 检查只构建许可材料，不要求
编译 LLVM/Linux；仍需获取固定源码。缺失或空的许可文件会失败。宿主故障注入测试
验证复制原文、缺失/空文件拒绝及校验和发现篡改。
[首轮固定源码 CI](https://github.com/HighCWu/distro/actions/runs/38916863482)已通过，
对应 distro `2aac5a0`；它不包含后来加入的拆分来源 hash、零引用约束及安装校验，
不能替代后续约束的验证。
[收紧后的材料 CI](https://github.com/HighCWu/distro/actions/runs/38917758703)
也已通过（distro `13596d0`），包含拆分来源 hash 和 Nix 零引用约束；这证明材料包
本身未引用完整源码树。随后 distro `88a5ce1` 的 SDK C++ 消费
[wasm32](https://github.com/HighCWu/distro/actions/runs/38918153433) 和
[wasm64](https://github.com/HighCWu/distro/actions/runs/38918154357) CI 均通过，
其强制 profile 依赖包含实际 SDK 安装视图中的 SHA256SUMS 校验。这是所选材料
完整性的验证，不证明未纳入材料的依赖许可清单完整。

后续材料包还收录实际 SDK 所选 Meson 源码的原始 `COPYING`，存在时同时收录
`NOTICE`，并附带本项目的 archive-group 补丁及修改说明。来源使用 `meson.src`，
而不是另行选择一个可能不同版本的上游副本。宿主测试执行真实复制配方，覆盖 Meson
许可证缺失/为空时失败、可选 NOTICE 原文保留，以及补丁/说明和校验和完整性；
对应 distro `94bd9c6` 的
[固定源码 Nix 检查](https://github.com/HighCWu/distro/actions/runs/38921710474)
已通过：新增材料构建、校验和与 `allowedReferences = []` 约束均由该检查执行。
它只验证材料包，不证明后来 SDK 安装视图或完整依赖许可清单已通过审计。

这是部分许可材料包，不是完整 SBOM、依赖许可清单、合规结论或 GPL 对应源码包。
宿主动态依赖、Meson 的 Python 依赖与继承的 Nixpkgs 补丁、附加库及各源文件自身
的声明仍须单独审计，不能据此宣布 SDK
已经完成发行合规。仅记录源码 store 身份也不替代提供可获得的对应源码。

发行管线最终应自动生成：

- SPDX SBOM；
- 每个二进制和镜像的许可证清单；
- NOTICE/attribution；
- Linux和其他 copyleft组件的对应源码包；
- 编译器/runtime/kernel ABI版本清单；
- 用户程序样例的链接组成记录，确认实际组成与声明的许可证边界一致。

## 对外表述

推荐表述：

> 本系统遵循普通 Linux用户态程序通过 syscall/UAPI使用 GPL Linux内核的边界。
> 项目提供 MIT musl/runtime及带 LLVM exception的工具链；开发者可以根据自身代码
> 和依赖的许可证选择开源、闭源及商业发行方式。仅仅在本平台编译或运行，不会使用户
> 程序自动继承 Linux内核的 GPL许可证。发行者仍须审查实际链接和分发的组件，并履行
> 各组件相应的许可证义务。

不应使用“绝对没有许可证风险”“任何组合都可随意改许可证”或“任何组合都可闭源”
这样的无条件保证。
