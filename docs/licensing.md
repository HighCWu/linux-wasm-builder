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

rootfs中的 BusyBox及其他 copyleft组件也必须单独处理，不能因为它们位于磁盘镜像
中而忽略。

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
