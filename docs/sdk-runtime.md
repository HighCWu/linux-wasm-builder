<!-- SPDX-License-Identifier: MIT -->

# C/C++ SDK运行验证

SDK支持属于Linux/Wasm主路线，不依赖私有文件映射实验。当前工具链使用
wasm32/wasm64-unknown-linux-musl目标、musl及LLVM的compiler-rt、libc++、libc++abi
和libunwind。独立测试代码采用MIT；这些依赖仍遵循各自上游许可证，不因测试采用
MIT而被重新许可。使用者可按自身代码与实际依赖的许可证开发和发布软件。

## 为什么需要独立启动检查

既有toolchain-smoke会编译并验证C/C++ Wasm模块；已有C用户程序启动检查。但
C++模块能链接且通过wasm-validate，不代表其运行库、异常清理或线程在Linux/Wasm
中已经实际工作。不能以这类编译检查替代C++启动证据。

distro提交`cc8ecee2acde42859770b50708fc5f1255c6ddca`新增
`distro/toolchain-smoke/runtime-cxx.cc`，使用普通clang++、C++17、pthread和现有
平台编译/链接参数，不调用内核私有接口。默认内核以双核raw initramfs启动同一
程序，必须输出协议pass标记；只出现内核banner或成功链接均不足以通过。

覆盖范围：

- unique_ptr/vector分配、sort及64位累加结果。
- 跨非内联函数抛出std::runtime_error，核验异常类型、what内容，以及栈上Guard的
  析构恰好执行一次，检查基本RAII异常清理。
- std::thread创建与join、工作线程独立TLS初值、修改后的主线程TLS仍不变，以及
  join之后结果可见；没有未同步的轮询。

这不是完整C++标准库或第三方软件兼容认证，不涵盖动态链接、filesystem、iostream、
线程取消时的C++析构、TLS析构、跨模块异常或sanitizer。宿主原生测试使用本机C++
运行库，不能证明Wasm的libc++/libunwind已经通过。

## 复现

从主仓库执行以下任一命令，需要Nix及足够的缓存或构建空间：

```sh
nix build './sources/distro#checks.x86_64-linux.toolchain-smoke-check-cxx-runtime'
nix build './sources/distro#checks.x86_64-linux.toolchain-smoke-wasm64-check-cxx-runtime'
```

两项检查使用不同位宽的工具链、sysroot和默认内核。heavy CI可分别指定上述
`toolchain-smoke-check-cxx-runtime`或`toolchain-smoke-wasm64-check-cxx-runtime`名称。
当前以公开GitHub Actions承担重构建；开发机可只做源代码检查，不要求本地重建LLVM。

后续SDK工作应逐步形成脱离仓库内部脚本的第三方构建与发布流程；本轮并不宣称
可重定位SDK、独立安装包或真实第三方应用已经交付。

## 双位宽开发入口

distro提交`58398eee42b99df1756578fee5d695cf79fcc67d`提供MIT的SDK包装器及
开发shell。原有default shell保持不变；新增sdk（wasm32）及sdk-wasm64，明确导出
CC、CXX、AR、RANLIB与sysroot。它们是交叉编译环境，不将宿主程序当作目标程序运行。

从主仓库进入所需profile：

```sh
nix develop './sources/distro#sdk'
# 或使用64位profile：
nix develop './sources/distro#sdk-wasm64'
```

进入shell后，可直接通过公共编译入口分离编译、链接示例，不需要复制内部Nix参数：

```sh
"$CXX" -std=c++17 -O2 -pthread -c sources/distro/distro/toolchain-smoke/runtime-cxx.cc -o runtime.o
"$CXX" -pthread runtime.o -o runtime.wasm
```

编译入口名为wasm-linux-cc和wasm-linux-c++，SDK分别使用对应profile的Clang、
sysroot及平台flags。普通Makefile可消费CC/CXX/AR/RANLIB；不保证任意构建系统的
交叉探测自动正确，尤其不能在配置阶段直接执行生成的Wasm程序。

包装器在-c/-S/-E/-M/-MM/-fsyntax-only和常见查询模式省略可执行文件链接参数，
链接时追加共享线性内存、allocator导出等已有平台参数；保留用户参数及带空格路径。
暂不支持@response-file并明确报错，避免因隐藏-c而误判阶段。它不是完整Clang
driver替代品；也不应通过额外target/sysroot参数混用另一个profile。

SDK产物可分别构建：

```sh
nix build './sources/distro#sdk'
nix build './sources/distro#sdk-wasm64'
```

这些产物仍引用Nix store中的工具链和sysroot，不可把单独复制bin目录视为可搬移
SDK。既有clang/clang++仍可直接使用；SDK包装器使用独立名称，不覆盖编译器本身。

13项本地Node契约测试检查参数传递，根仓库轻量CI也执行它们，不需要下载LLVM或
构建内核。两种profile还各有默认内核双核C++消费检查：通过SDK以-Werror分离编译
同一运行用例，再链接、启动，检查名为sdk-check-cxx-runtime及
sdk-wasm64-check-cxx-runtime。这是实际编译器/运行验证，与假编译器契约测试分开。
公开Node [wasm32](https://github.com/HighCWu/distro/actions/runs/38860562604)和
[wasm64](https://github.com/HighCWu/distro/actions/runs/38860568150)已触发，结果待确认。
尚未在本机实际进入Nix开发shell或验证浏览器执行。

## 验证状态

宿主g++ C++17严格编译及执行通过，Nix语法格式化和仓库元数据检查通过。本地没有
构建Linux或LLVM。公开Node [wasm32](https://github.com/HighCWu/distro/actions/runs/38859969295)
及[wasm64](https://github.com/HighCWu/distro/actions/runs/38859974701)已触发，结果待确认。
尚未执行本用例的浏览器检查，既有C程序浏览器结果不计为本用例通过。

本轮独立于[线程等待回归](time-abi.md)继续推进。CI运行期间可开展不依赖其结果的
文档、代码审计和SDK任务；依赖运行结论的支持声明及修复决策，仍需等待对应证据。
