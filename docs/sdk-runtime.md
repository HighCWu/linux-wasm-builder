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

初版包装器区分编译与链接模式并拒绝@response-file；后续已改用Clang配置机制，
支持响应文件，见下节。它不是完整Clang driver替代品；也不应通过额外target/sysroot
参数混用另一个profile。

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
[wasm64](https://github.com/HighCWu/distro/actions/runs/38860568150)均失败；后续诊断及
异常生成修正见下文“C++异常处理生成”。
尚未在本机实际进入Nix开发shell或验证浏览器执行。

## CMake交叉编译入口

distro提交`8df4a96dd2e931fc71d618c9a79a7471e6ae2605`在两个SDK中安装
`share/cmake/linux-wasm.cmake`，开发shell同时导出WASM_CMAKE_TOOLCHAIN_FILE。
工具链文件选择对应profile的C/C++包装器、LLVM ar/ranlib和sysroot，设置Linux
目标及wasm32/wasm64处理器。构建工具从宿主查找，目标库、头文件和包限制到目标
root路径，避免静默混入宿主库。当前仅提供静态目标库。

进入上一节的sdk或sdk-wasm64 shell后，在主仓库目录执行：

```sh
cmake -S sources/distro/distro/sdk/cmake-example -B build-sdk -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$WASM_CMAKE_TOOLCHAIN_FILE" -DCMAKE_BUILD_TYPE=Release
cmake --build build-sdk
```

不同profile应使用不同build目录，不能复用含另一工具链的CMake cache。示例产物为
`build-sdk/sdk-example.wasm`；它是目标Linux/Wasm程序，不可当作本机ELF直接执行。

示例是独立的CMake项目：将C函数编译为静态archive，再由C++程序通过extern C
调用，并在线程中使用vector，join后核验结果。CMakeLists选择C11/C++17，使用
Threads::Threads，不手工传递内部平台链接参数；示例目标显式设置.wasm后缀。

工具链保持CMake默认的可执行文件try_compile：配置探针会编译并链接，但不在宿主
执行Wasm。缺失符号应使链接失败，避免把仅能编译的函数声明误认为库中已有实现。
try_run仍需要目标运行环境或项目提供经过验证的结果；编译、链接通过不等于函数
运行语义已受支持。动态库及任意CMake第三方包兼容性仍不在本轮承诺范围。
升级工具链后应使用新构建目录，避免旧CMake缓存保留此前的探测误判。

本地宿主CMake/Ninja配置、C archive与C++构建、执行pass，以及工具链模板语法
检查通过；轻量CI重复这些检查而不下载LLVM。宿主构建没有使用Wasm工具链，不计
作交叉编译通过。实际双位宽消费检查使用安装在SDK中的工具链文件配置和构建示例，
随后在对应默认内核双核环境执行，CI名称为sdk-check-cmake-runtime和
sdk-wasm64-check-cmake-runtime。
公开Node [wasm64](https://github.com/HighCWu/distro/actions/runs/38860960964)已通过；
[wasm32](https://github.com/HighCWu/distro/actions/runs/38860955154)结果待确认。
这轮不修改Linux、musl或LLVM实现，没有新增浏览器执行记录。

## 由Clang管理响应文件和链接阶段

distro提交`e2cafe9c925f5382af42c4ad29902d6e059d4af3`移除包装脚本的阶段判断和
响应文件拒绝逻辑。SDK通过--config传入profile参数；共享内存、导出、stack等链接
选项使用Clang配置的$前缀，仅在链接阶段生效。响应文件、嵌套文件、引用规则及
缺失文件诊断由Clang自身处理，不由shell展开或eval用户参数。

依据是固定LLVM提交`137009e264eb237b5f5adcbae1b7e209f79291f5`的
clang/docs/UsersManual.rst配置说明，以及clang/lib/Driver/Driver.cpp的
readConfigFile/BuildCompilation实现。已有默认配置先于显式配置加载，因此保留
工具链clang++.cfg的libc++及异常支持选择；本轮没有修改LLVM源码。

本地13项包装契约测试及1项本机Clang 22驱动测试通过。后者实际编译包含配置宏的
C源文件，经嵌套响应文件传递-c/-Werror及带空格路径，检查编译dry-run没有链接
标记，链接dry-run包含标记，以及缺失响应文件被拒绝。该测试不在宿主实际链接
和运行产物，不依赖宿主libc，也不替代Wasm运行证明。

轻量CI在存在clang-22时运行驱动测试，否则明确skip；SDK消费CI显式指定固定fork
编译器，不允许因找不到编译器而跳过。CMake消费检查新增
`-DCMAKE_NINJA_FORCE_RESPONSE_FILE=ON`，覆盖实际Wasm编译、归档和链接的响应文件
消费，随后仍需默认内核输出运行pass。

该版本公开CI的结果：

- SDK直接消费：[wasm32](https://github.com/HighCWu/distro/actions/runs/38861602519)、
  [wasm64](https://github.com/HighCWu/distro/actions/runs/38861607869)均在用户程序运行时
  失败，编译和链接已完成；异常生成修正见下文。
- CMake强制响应文件：[wasm32](https://github.com/HighCWu/distro/actions/runs/38861614651)、
  [wasm64](https://github.com/HighCWu/distro/actions/runs/38861620256)已通过，wasm32结果待确认。

支持当前Clang的响应文件语法，不等于支持任意编译器或构建系统；没有修改内核、
musl、公开UAPI或浏览器配置。SDK仍依赖Nix store，不是可重定位发行包。

## 目标依赖元数据查询

两个SDK shell均提供`wasm-linux-pkg-config`，并将`PKG_CONFIG`指向对应profile的
包装工具；CMake工具链也默认选择该工具。它在宿主运行pkg-config，但仅查询目标
sysroot下的`lib/pkgconfig`和`share/pkgconfig`，覆盖继承的PKG_CONFIG_LIBDIR、
PKG_CONFIG_SYSROOT_DIR及PKG_CONFIG_PATH，避免将宿主库误当成Wasm库。
当前SDK只支持静态目标库，因此查询默认附加`--static`以包含Libs.private。

```sh
"$PKG_CONFIG" --cflags --libs mylibrary
# 可选：添加自行安装的目标 .pc 元数据目录，不要填写宿主库目录。
export WASM_PKG_CONFIG_PATH=/absolute/path/to/target/pkgconfig
```

这不代表SDK已经包含示例中的mylibrary，也不会自动编译、安装第三方依赖。
额外目录必须由使用者保证与所选wasm32/wasm64 profile匹配；绝对路径或自定义
变量写法复杂的.pc文件仍需审查，搜索路径隔离不是安全沙箱。CMake默认关闭
FindPkgConfig从CMAKE_PREFIX_PATH追加搜索路径，避免绕过该边界；自行覆盖工具链
选项的项目需自行保证一致性。

本地真实pkg-config夹具测试通过：宿主同名库及仅宿主存在的包不被选中，目标
include/lib路径经sysroot重定位，静态私有依赖保留，share目录和显式目标附加
目录可查询，版本及错误退出码保持正常。连同既有包装及Clang驱动测试共15项
通过，已纳入轻量CI和SDK包装契约检查。这里验证的是依赖发现行为，不是第三方库
在Wasm中的编译或运行。本轮没有追加重型构建；前述已触发的Wasm运行检查继续
验证各自固定提交，不包含本次新增的pkg-config集成。

## 单独安装静态依赖再构建程序

`dependency-example`是独立的C静态库项目，安装公开头文件、sdk-answer和sdk-helper
两个archive及sdk-answer.pc。sdk-answer调用sdk-helper，后者只列在Libs.private。
`cmake-example`增加可选的SDK_USE_INSTALLED_ANSWER模式，通过FindPkgConfig导入
目标，而不是把依赖源码再次加入程序构建。默认模式仍保留原来的自包含示例。

在sdk或sdk-wasm64 shell中，可以把目标依赖安装到独立前缀：

```sh
cmake -S sources/distro/distro/sdk/dependency-example -B build-dependency -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$WASM_CMAKE_TOOLCHAIN_FILE" \
  -DCMAKE_INSTALL_PREFIX="$PWD/sdk-dependency"
cmake --build build-dependency
cmake --install build-dependency
export WASM_PKG_CONFIG_PATH="$PWD/sdk-dependency/lib/pkgconfig"
export WASM_PKG_CONFIG_SYSROOT_DIR=/
cmake -S sources/distro/distro/sdk/cmake-example -B build-consumer -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$WASM_CMAKE_TOOLCHAIN_FILE" \
  -DCMAKE_STAGING_PREFIX="$PWD/sdk-dependency" -DSDK_USE_INSTALLED_ANSWER=ON
cmake --build build-consumer
```

这里.pc使用安装前缀的绝对路径。WASM_PKG_CONFIG_SYSROOT_DIR=/显式禁止再为这些
路径添加SDK sysroot；CMAKE_STAGING_PREFIX声明这处目标库目录不应被CMake再次
重定位到SDK sysroot。编译器本身的sysroot没有改变。该覆盖适合所有目标依赖均以
真实绝对路径安装的场景，不适合混用需要sysroot重定位的.pc文件。完成后应unset
这两个WASM_PKG_CONFIG变量，或在独立shell中操作；不同位宽不得共享依赖或构建目录。
默认不设置覆盖时，仍按上一节的SDK sysroot进行重定位，也不继承宿主PKG_CONFIG_PATH。

本地集成测试实际执行配置、构建、安装、独立消费及宿主运行，并覆盖强制响应文件；
删去Libs.private后要求链接失败且报告sdk_helper，避免仅验证查询输出。与既有测试
合计16项通过，新增流程纳入轻量CI。宿主通过不计为Wasm通过。

SDK的cmake-runtime检查已改为执行这条两阶段消费流程，产物仍需在对应默认内核
运行。此前已触发的CI固定在旧提交，不包含本节变更；本轮没有追加重型任务，也没有
Linux、musl、LLVM或浏览器实现变更。示例验证构建接口，不代表任意第三方库已兼容。

## 使用SDK构建上游zlib

SDK新增真实第三方库消费检查：复用`distro/zlib/package.nix`固定的zlib 1.3.1源码及
fetchzip校验值，通过SDK的CC、AR、RANLIB运行上游configure --static、make及install。
随后独立的`zlib-example`项目使用FindPkgConfig导入安装后的zlib.pc，通过SDK CMake
工具链构建程序。没有复用发行版已经编译好的zlib库，也没有修改zlib源码。

程序核验头文件与库的版本一致，执行8 KiB数据的压缩/解压并逐字节比较，最后破坏
校验和并要求返回Z_DATA_ERROR。此检查覆盖静态库消费、内存分配与zlib内存压缩接口；
不覆盖gz文件接口、所有压缩参数或性能指标。项目新增测试和集成代码采用MIT，zlib
本身继续遵循上游zlib许可证。

在对应SDK shell中，准备解包的固定zlib源码后可复现构建：

```sh
mkdir -p build-sdk-zlib
SDK_TEST_ZLIB_SOURCE=/absolute/path/to/zlib-1.3.1 \
  SDK_TEST_CMAKE_TOOLCHAIN="$WASM_CMAKE_TOOLCHAIN_FILE" \
  SDK_TEST_PKG_CONFIG="$PKG_CONFIG" \
  SDK_TEST_OUTPUT_DIRECTORY="$PWD/build-sdk-zlib" \
  node --test sources/distro/distro/sdk/zlib-consumer-test.js
```

该命令需要宿主Node和Make，产物为`build-sdk-zlib/sdk-zlib.wasm`。脚本在临时目录
构建和安装依赖，使用显式目标元数据路径及CMake staging前缀，保留产物后清理临时
构建目录；不会修改输入源码。目标程序须在Linux/Wasm运行，构建脚本不在宿主执行它。

本地使用同一上游版本完成configure/Make、安装、CMake消费和宿主程序运行。目标检查
名称为`sdk-check-zlib-runtime`和`sdk-wasm64-check-zlib-runtime`，使用各自默认内核
及raw initramfs；Node宿主收到程序pass才算运行成功。固定distro提交
`90e0fdb3d2ad298f481de84e4ac8195280b97782`的公开
[wasm32](https://github.com/HighCWu/distro/actions/runs/38865687673)和
[wasm64](https://github.com/HighCWu/distro/actions/runs/38865697512)均在前置treefmt检查
失败：pkg-config.sh中的条件表达式引号被shfmt规范化。两次任务尚未进入zlib编译和
运行阶段，不能据此判断zlib兼容性。该格式问题已修正，重跑记录见下节。

## CMake链接探测修正

早期工具链把CMAKE_TRY_COMPILE_TARGET_TYPE固定为STATIC_LIBRARY，导致
CheckFunctionExists只归档对象文件，不核验符号是否能够链接。宿主复现显示，一个
刻意不存在的linux_wasm_sdk_missing_function也被报告为找到。

工具链现已移除该覆盖，恢复默认的可执行文件链接探测。示例同时要求malloc存在、
上述测试符号不存在；本地使用工具链模板及宿主编译器的交叉编译模式验证修正，
独立安装静态依赖的消费回归也通过。轻量CI新增同一模板检查，实际Wasm编译器的
探测由两种位宽的cmake-runtime检查覆盖。该修正不提供try_run执行器。

修复后的distro提交`5ad3a970b12b47f83334782d8cbbf9c2205af886`已触发：

- zlib：[wasm32](https://github.com/HighCWu/distro/actions/runs/38866455970)、
  [wasm64](https://github.com/HighCWu/distro/actions/runs/38866462004)。
- CMake已安装依赖及符号探测：[wasm32](https://github.com/HighCWu/distro/actions/runs/38866467060)、
  [wasm64](https://github.com/HighCWu/distro/actions/runs/38866472989)。

其中wasm32 zlib已在默认内核通过压缩、解压及损坏数据检查。其余三项结果待确认。

## C++异常处理生成

双位宽直接SDK消费检查均已完成编译、链接并启动用户程序，但在运行期间有
WebAssembly.Exception逃出用户模块，导致init退出。早期C++运行检查同样失败；
成功的CMake线程示例不包含主动抛出异常，不能替代异常路径的验证。

检查固定Clang源码及实际Wasm汇编发现，原配置只有-mexception-handling和已有的
SjLj选项，没有启用C++异常处理的-wasm-enable-eh转换。简单try/catch及RAII探针
在旧配置下生成的Wasm没有C++异常tag和catch处理代码。

现将clang++.cfg及LLVM运行库的C/C++编译选项统一为-fwasm-exceptions，由Clang
开启完整的Wasm异常生成；运行库汇编输入仍保留指令特性选项。没有修改LLVM源码或
Linux内核，也没有移除或放宽原异常运行用例。

新增MIT无标准库头文件的代码生成探针，在本地Clang 22上覆盖wasm32/wasm64，验证
C++异常tag和catch处理仍存在。旧配置会失败，修正后通过；SDK CI使用固定fork
编译器及安装后的clang++.cfg执行同一检查。完整异常、RAII、线程和TLS运行结果
仍须以修正后的目标CI为准。

修正后的distro提交`ee6a09e980dfe8fda4602ad2d291c68d3c995e5c`已触发
[wasm32](https://github.com/HighCWu/distro/actions/runs/38873696135)及
[wasm64](https://github.com/HighCWu/distro/actions/runs/38873703134)直接SDK运行检查，
结果待确认。这会重建对应C++运行库；已有旧配置的通过记录不能覆盖本次变更。

## 验证状态

Autoconf项目可使用SDK的`wasm-linux-configure`入口，使用方式、配置探测及验证
边界见[Autoconf构建说明](sdk-autoconf.md)。
Meson项目可使用安装后的cross file及显式构建机工具，见[Meson构建说明](sdk-meson.md)。

宿主g++ C++17严格编译及执行通过，Nix语法格式化和仓库元数据检查通过。本地没有
构建Linux或LLVM。公开Node [wasm32](https://github.com/HighCWu/distro/actions/runs/38859969295)
及[wasm64](https://github.com/HighCWu/distro/actions/runs/38859974701)均失败，见上述
C++异常生成诊断。后续修复尚待完整目标运行确认。
尚未执行本用例的浏览器检查，既有C程序浏览器结果不计为本用例通过。

本轮独立于[线程等待回归](time-abi.md)继续推进。CI运行期间可开展不依赖其结果的
文档、代码审计和SDK任务；依赖运行结论的支持声明及修复决策，仍需等待对应证据。
