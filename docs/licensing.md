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
| Linux内核修改 | GPL-2.0-only，按文件SPDX | 发行修改后的内核必须履行GPL义务 |
| Linux UAPI headers | GPL-2.0 WITH Linux-syscall-note等 | 正常syscall用户程序不因此成为GPL派生作品 |
| distro/rootfs内容 | 混合许可证 | 必须逐包生成清单并履行各自义务 |

“项目尽量 MIT”意味着把可独立实现的新代码放到 MIT 组件；它不意味着把 Linux、
LLVM 或第三方代码重新标成 MIT。

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

softmmu fast path应由 LLVM生成、MIT runtime或带 LLVM exception 的支持代码提供。
Linux端实现只通过 UAPI/执行 ABI与程序交互。

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

用户提供的历史私有项目也遵守同一规则。仅仅拥有本地工件或反编译产物，不代表其全部
来源都可按MIT重新发布；在版权归属、第三方成分和明确授权落档前，只能从行为观察、
接口语义和独立测试中提取需求。若后续确认代码可重新许可，仍应以单独的provenance
记录说明作者、来源、原始许可证和重新许可依据。

## 自动化要求

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
