<!-- SPDX-License-Identifier: MIT -->

# linux-wasm-builder

`linux-wasm-builder` 是持续完善 Linux-on-WebAssembly 平台的集成、开发和可复现
构建仓库。项目覆盖 Linux `arch/wasm`、LLVM/Clang/LLD、musl、用户态发行版、
浏览器与 Node 宿主、设备和存储、测试、打包以及许可证合规。

项目的核心技术目标是持续提高 Linux 在 WebAssembly 上的完整性、兼容性、稳定性
和可维护性，而不是完成某一种内存技术。内核只是平台的一层；工具链、libc、发行版、
宿主集成、设备、测试和发布能力都属于长期建设范围。

项目希望提供与普通 Linux 平台一致的用户态开发体验：任何个人、社区或组织都可以
使用这里发布的内核、工具链、libc 和 SDK 开发、构建和发布软件，并依照自身代码及
所用依赖的许可证，选择开源、闭源或商业发行。平台遵循 Linux 的 syscall/UAPI 边界；
用户程序仅仅在本平台编译或运行，不会因此被要求采用 Linux 内核的 GPL 许可证。用户
仍须遵守其实际链接或分发的库和其他组件各自的许可证。

为维持这一与普通 Linux 相同的边界，用户程序通过稳定的 Linux UAPI 和版本化 Wasm
执行 ABI 与内核交互，不链接 Linux 内核实现代码。

> 本仓库的许可证设计旨在支持上述使用方式，但不是针对具体产品的法律意见。

## 项目方向

- 尽可能复用 Linux 通用子系统，只在 `arch/wasm` 和明确的宿主边界增加必要实现。
- 让普通 Linux 源码可由标准形状的 Clang/musl 工具链构建并运行。
- 同时支持浏览器和服务器 runtime，浏览器是首要产品环境。
- 持续补齐进程、线程、信号、时间、存储、网络、设备、调试和发行能力。
- 以可复现构建、上游友好改动、兼容性测试和清晰许可证边界作为长期约束。
- 用户程序只依赖稳定 Linux UAPI 和版本化 Wasm psABI，不依赖内核私有实现。

softmmu2+TLB 是内存与地址兼容路线中的一个可替换实现里程碑，用于补足固定高地址、
稀疏映射和严格映射失效等能力。它不是项目本身，不定义平台的公共 Linux 编程模型，
也不应阻塞其他 Linux/Wasm 子系统继续演进。

```text
Linux application source
        │
        ▼
LLVM/Clang wasm-linux toolchain + musl
        │
        ▼
program.wasm
        │
        ▼
standard Linux syscall/UAPI boundary
        │
        ▼
CONFIG_MMU=n linux.wasm
  ├─ process / thread / signal / time
  ├─ VFS / block / storage / networking
  ├─ virtio / browser host integration
  └─ optional memory-compatibility facilities
```

## 文档

- [架构](docs/architecture.md)
- [当前基线](docs/baseline.md)
- [softmmu2 psABI 草案](docs/softmmu-abi.md)
- [路线图](docs/roadmap.md)
- [许可证与发行政策](docs/licensing.md)
- [贡献指南](CONTRIBUTING.md)

## 计划中的源码组成

本仓库将以 submodule 固定以下 fork。正式构建以 `distro` 中记录并发布到 GitHub 的
精确 commit pin 为准；主仓库的 submodule 指针应与这些 pin 保持一致。开发者在多个
组件尚未推送时，可以使用显式的本地源码 override，但它不是发布构建的必要条件。

```text
sources/
├── distro/          HighCWu/distro:main
├── linux/           HighCWu/linux:wasm
├── llvm-project/    HighCWu/llvm-project:wasm-linux
└── musl/            HighCWu/musl:master
```

submodule、构建脚本和测试将在文档基线评审后加入。

## 当前状态

当前阶段先建立未经改造的 Linux/Wasm 可复现基线和跨组件测试矩阵，再按独立工作流
推进内核、工具链、用户态和宿主能力。`docs/softmmu-abi.md` 是内存工作流的专项草案，
其中标记为“待验证”的内容不能被视为已稳定 UAPI。
