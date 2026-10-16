<!-- SPDX-License-Identifier: MIT -->

# C/C++ SDK运行验证

SDK支持属于Linux/Wasm主路线，不依赖私有文件映射实验。当前工具链使用
wasm32/wasm64-unknown-linux-musl目标、musl及LLVM的compiler-rt、libc++、libc++abi
和libunwind。独立测试代码采用MIT；这些依赖仍遵循各自上游许可证，不因测试采用
MIT而被重新许可。使用者可按自身代码与实际依赖的许可证开发和发布软件。

## 识别当前 SDK 配置

在相应 SDK shell 中运行 `wasm-linux-sdk-info` 可输出 JSON 配置记录；同一内容随包
安装在 `share/linux-wasm-sdk/profile.json`。记录包含目标位宽、triple、编译/链接默认
参数、C++ 配置原文，以及工具链、sysroot、编译配置和修正版 Meson 的 Nix store 路径。
排查问题或归档构建时，应同时保存此记录与应用自身的构建参数。

distro `f5417ce` 增加 `linearMemory.maximumBytes`，与 profile 的
`--max-memory` 链接参数共用一个定义：当前 wasm32 为 4294967296 字节（4 GiB），
wasm64 为 17179869184 字节（16 GiB）。这是生成模块声明的线性内存上限，不是
可用用户堆大小、内核参数、`RLIMIT_AS` 或宿主一定能分配的内存。64 位指针也不表示
当前模块能访问整个 64 位地址空间；有效访问仍必须落在实际已增长的线性内存中。
该字段为 schemaVersion 1 的增量信息，旧版记录可能没有它；它不引入地址转换或
softmmu。SDK profile 检查同时核对字段值与链接参数，
[wasm64 安装验证](https://github.com/HighCWu/distro/actions/runs/38944051448)
已通过，固定 distro `f5417ce`：实际构建 `sdk-profile-wasm64`，CLI/安装文件比较、
配置路径、线性内存上限及链接参数断言、错误参数处理和许可证校验均完成；目标检查
与整个工作流成功。这不证明 wasm32 新字段的安装检查或可重定位 SDK 已通过。

`schemaVersion` 只表示 JSON 格式版本，不是 Linux/Wasm ABI 版本。此记录不是 SBOM、
源码清单或兼容性认证，也不能检测用户手动覆盖参数或混入的第三方库。特别是 C++ ABI
配置变更后仍须重建依赖，不能仅凭目标位宽相同就混用旧产物。wasm64 安装入口的
Nix 集成结果见上述固定提交；更早运行的旧提交不覆盖此入口。

配置记录可通过独立的 `sdk-check-profile` / `sdk-wasm64-check-profile` 检查验证，
无需构建和启动 Linux 内核；仍需要对应工具链、sysroot 和 SDK 的 Nix 依赖。
检查比较 CLI 与安装文件、目标位宽及默认参数，检查实际配置路径，并验证错误参数
返回非零状态且不输出 JSON。C++ 消费检查仍强制依赖此检查，未降低运行验证要求。
例如：

```sh
nix build './sources/distro#checks.x86_64-linux.sdk-wasm64-check-profile'
```

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
线程取消时的C++析构、主线程退出时的TLS析构、跨模块异常或sanitizer。宿主原生测试使用本机C++
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
[wasm32](https://github.com/HighCWu/distro/actions/runs/38860955154)也已通过；对应
`sdk-check-cmake-runtime` 的 Build isolated check 和整个工作流均成功。
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
  [wasm64](https://github.com/HighCWu/distro/actions/runs/38861620256)均已通过；wasm32
  对应 `e2cafe9c925f5382af42c4ad29902d6e059d4af3`，不是后续 SDK 元数据或异常扩展的验证。

支持当前Clang的响应文件语法，不等于支持任意编译器或构建系统；没有修改内核、
musl、公开UAPI或浏览器配置。SDK仍依赖Nix store，不是可重定位发行包。

## 目标依赖元数据查询

SDK 包装器还清空宿主继承的 `PKG_CONFIG_SYSTEM_INCLUDE_PATH` 和
`PKG_CONFIG_SYSTEM_LIBRARY_PATH`：这些过滤设置会在查询成功后删除目标必需的
`-I` / `-L` 参数，不能只隔离 `.pc` 搜索路径。真实 pkg-config 回归测试覆盖这一
情况，确保目标路径仍保留；这不是对任意第三方 `.pc` 内容的安全审查。

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

目标 pkg-config 回归检查覆盖 `Requires.private` 的传递依赖、缺失依赖不能回退到
宿主库，以及显式替换 sysroot 后的编译/链接参数。本机 pkgconf 1.8.1 对含空格的
sysroot 覆盖值会生成错误参数；外部 sysroot 暂使用不含空格的路径。这是该查询路径的
已知限制，不应与编译器响应文件已支持含空格路径混为一谈；固定 SDK 版本的对应行为
仍需另行验证。

本地集成测试实际执行配置、构建、安装、独立消费及宿主运行，并覆盖强制响应文件；
删去Libs.private后要求链接失败且报告sdk_helper，避免仅验证查询输出。与既有测试
合计16项通过，新增流程纳入轻量CI。宿主通过不计为Wasm通过。

SDK的cmake-runtime检查已改为执行这条两阶段消费流程，产物仍需在对应默认内核
运行。此前已触发的CI固定在旧提交，不包含本节变更；本轮没有追加重型任务，也没有
Linux、musl、LLVM或浏览器实现变更。示例验证构建接口，不代表任意第三方库已兼容。

## 使用SDK构建上游SQLite

`sdk-check-sqlite-runtime` 和 `sdk-wasm64-check-sqlite-runtime` 复用发行版已经固定的
SQLite 3.51.0 源码，分别用对应 SDK 编译上游 amalgamation、建立静态归档，再链接独立
C 程序。wasm64 不复用 wasm32 发行版库，也不需要构建 readline 或 SQLite CLI。

检查覆盖内存数据库、prepared statement、64 位整数和包含零字节的 BLOB、事务提交及
回滚；文件数据库使用 DELETE journal 和 FULL synchronous，关闭后以只读方式重新
打开，检查提交的数据与 `integrity_check`。程序通过正常 SQLite Unix VFS 使用 Linux
文件接口，不引入自定义浏览器 VFS。

首轮沿用现有发行版的 `SQLITE_OMIT_WAL=1` 和 `SQLITE_MAX_MMAP_SIZE=0`，并明确
启用线程安全、关闭动态扩展加载；这不是 WAL、mmap、多进程锁竞争或崩溃恢复支持的
证明。文件检查运行于临时 initramfs，也不证明浏览器退出后的磁盘持久性。

```sh
nix build './sources/distro#checks.x86_64-linux.sdk-check-sqlite-runtime'
nix build './sources/distro#checks.x86_64-linux.sdk-wasm64-check-sqlite-runtime'
```

本机已用 SQLite 3.51.0 源码及上述宏配置完成静态构建与用例运行；这只验证用例和
构建配方，不能单独证明 Wasm 目标通过。随后 distro
`ad366f026ffae099156ef721579d42d2e6766160` 的
[wasm64 定向 CI](https://github.com/HighCWu/distro/actions/runs/38914592060)
已完整成功：默认 Linux 内核在 Node 中启动 `/init`，日志确认内存绑定/回滚、文件
提交/回滚/重新打开/完整性两阶段均通过，并输出用户程序 `::vm-test::pass`。
[wasm32 定向 CI](https://github.com/HighCWu/distro/actions/runs/38914591743)
仍待确认，不能用 wasm64 结果替代。

真实浏览器 runtime 套件也已接入相同 SDK 产物，作为独立 initramfs 启动，并要求
上述两阶段及最终通过标记。每种位宽的 Chromium/Firefox 门禁现要求精确执行五项
runtime 测试，不允许跳过或重试；新增 SQLite 浏览器结果尚待验证。这里仍只测试
临时 Linux 文件系统，未连接 OPFS 磁盘，不证明页面重新加载后的数据库持久性。

后续用例增加跨进程写锁检查：父进程持有 `BEGIN IMMEDIATE` 事务，通过
`posix_spawnp` 独立执行同一程序的锁探测模式，要求第二个进程获得 `SQLITE_BUSY`。
父进程回滚释放锁后，再次启动的进程必须能够提交新记录，父进程随后读回并核对
记录数和总和。子进程不输出测试通过标记，只有父进程核验退出状态与数据后才允许
整项通过。此扩展已通过宿主 GCC/Clang 及固定 SQLite 3.51.0 静态库运行；上述旧
wasm64 成功记录不含这一扩展。随后 distro
`e2c3da272f32929bbf5f0046fc5aa850f135e300` 的
[wasm64 锁检查](https://github.com/HighCWu/distro/actions/runs/38916072625)已完整成功，
日志确认独立子进程写锁排斥、释放后的提交及父进程数据验证，并输出最终通过标记。
这仍是 Node/Linux-Wasm 临时文件系统上的验证，不覆盖任意多进程并发、WAL、
浏览器数据库持久性或崩溃恢复。

后续再增加未提交事务的异常退出恢复：独立子进程更新已有记录，调用
`sqlite3_db_cacheflush` 将未提交脏页写出，然后 `_exit(23)`，刻意不调用
`sqlite3_close` 或回滚。父进程核验该专用退出码，并在重新打开前检查 journal
文件的大小和 SQLite hot-journal 魔数，避免把“脏页从未离开子进程”的情况误算
为恢复通过。随后经 SQLite 正常 Unix VFS 重新打开，要求已提交的记录数与总和
保持原值、`integrity_check` 为 `ok`，并确认 DELETE journal 被移除，最后才输出
恢复阶段与整体通过标记。浏览器套件也要求这一新阶段。
宿主 GCC/Clang 严格编译及执行已通过；上述旧 Wasm 成功记录不包含这一扩展。
随后 distro `3ef7c3f` 的
[wasm64 恢复检查](https://github.com/HighCWu/distro/actions/runs/38922352954)
已通过：`sdk-wasm64-check-sqlite-runtime` 的实际构建/运行检查及整个工作流均成功。
该固定提交将恢复检查放在最终用户程序通过标记之前；此处依据工作流和检查代码
确认结果，尚未另行提取该运行的逐阶段控制台日志。wasm32 与浏览器结果仍待验证。
这只覆盖进程在现存 Linux 文件系统内异常退出后的回滚恢复，不模拟内核、浏览器、
页面或设备崩溃，不证明 OPFS 重载持久性、断电安全或 WAL 支持。

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

上述四项CI均已通过：双位宽zlib在默认内核完成压缩、解压及损坏数据检查；
双位宽CMake检查通过已安装静态依赖消费及符号链接探测。这些结果对应上述固定
提交，不代表后续C++异常修复或其他SDK构建入口已经完成运行验证。

## C++异常处理生成

### 标准 `try_table` 应用生成试验

原生 wasm64 OPFS 的 Firefox 实际运行日志报告旧式 Wasm `try` 指令已弃用，
建议改为标准 `try_table`。该批运行本身成功，不能把警告记为运行失败，也不能
仅关闭警告而声称已迁移。当前固定 LLVM 提交 `137009e264eb` 的
`llvm/test/CodeGen/WebAssembly/exception.ll` 明确覆盖
`-wasm-use-legacy-eh=false` 和 wasm64。

distro `cc72990` 增加 `sdk-check-cxx-modern-eh-runtime` 与
`sdk-wasm64-check-cxx-modern-eh-runtime`，复用完整 `runtime-cxx.cc`，不缩减为
只抛出一个整数的样例。通过公开 SDK 为应用显式添加
`-mllvm -wasm-use-legacy-eh=false`，先检查实际汇编包含 `try_table`、引用捕获及
C++ tag，且不混入旧式 try/catch/rethrow/delegate；再独立编译、链接当前已安装
C++ 运行库，核验最终模块共享内存位宽/上限，双核启动 Linux 并要求完整完成标记。
这包含 RAII、跨线程 exception_ptr、继承异常/RTTI、线程/TLS 等既有语料。

三项宿主门禁回归通过，验证缺失处理器、缺失 tag、混入旧指令等情况均被拒绝。
这不是 LLVM 实际代码生成或目标运行证据；首项目标检查先由 wasm64 公开 CI 执行。
[首项 wasm64 检查](https://github.com/HighCWu/distro/actions/runs/38975246019)
固定 `cc72990`，结果待确认。
该 wasm64 检查现已成功：实际日志确认应用汇编的标准处理器门禁、最终共享
memory64 ABI/16 GiB 声明上限，以及 RAII、跨线程 exception_ptr、继承异常/RTTI、
TLS 析构、条件变量和完整运行通过标记。它证明新应用生成方式与现有运行库在此
Node/Linux 路径下互操作，不把 Node 当作浏览器证据。
固定 `ad839be` 的 [wasm32 补验](https://github.com/HighCWu/distro/actions/runs/38976857074)
也已成功：实际日志确认标准 `try_table` 汇编门禁、共享 memory32 ABI/4 GiB 声明
上限，以及类型化 catch/RAII、跨线程 exception_ptr、继承异常/RTTI、TLS 析构、
条件变量和完整运行标记。
未切换默认配置或重建运行库/内核，最终程序仍可能含运行库的旧 EH 指令，浏览器
警告也可能继续存在。通过此检查也不等于全新 EH 运行库、内核 SjLj、浏览器执行
均已迁移；这些必须分别验证后才能决定默认策略。

### 析构函数ABI后续修复

修正异常生成选项后的wasm64任务
[38873703134](https://github.com/HighCWu/distro/actions/runs/38873703134)
已通过编译与异常处理代码生成检查，但运行在`__cxa_end_catch`报告
`null function or function signature mismatch`。固定LLVM源码中的Linux target选择
通用Itanium ABI，析构函数返回void；libc++abi的`__wasm__`分支则通过返回对象指针的
函数类型调用析构函数，两者不一致。

应用clang++配置与运行库CXX_FLAGS现均显式使用`-fc++-abi=webassembly`。本地Clang 22
对双位宽的IR检查确认析构函数返回指针，显式切回Itanium的反例返回void；本地使用
unknown-unknown目标，安装后的SDK检查使用实际Linux target。此ABI选择要求重建
C++库及应用，不能混用旧的Itanium ABI产物。完整运行结果仍以定向CI为准：
[wasm32](https://github.com/HighCWu/distro/actions/runs/38887844197)、
[wasm64](https://github.com/HighCWu/distro/actions/runs/38887850625)，提交
`ba7bf7faf3460c4a7613451efe23101ddf491bb6`。wasm64 已于2026-10-16通过：
日志确认默认内核以双核启动 `/init`，输出容器、RAII异常清理、线程与TLS验证完成，
并产生 `::vm-test::pass`。此前 `__cxa_end_catch` 的函数签名陷阱未再出现。
wasm32 的上述运行现也已通过，日志确认容器、RAII 异常、线程及 TLS 用户程序输出
最终通过标记。两种位宽的这些结果不证明浏览器 C++、跨模块异常或后续扩展已通过。

后续 [Chromium wasm64 运行](https://github.com/HighCWu/distro/actions/runs/38896599293)
在 distro `80528ae2feb9b4fc214764d296ae298084e15c41` 上实际完成四项浏览器测试，
其中 C++ 用例覆盖容器、RAII、跨线程 `exception_ptr` 和线程/TLS；目标构建步骤
成功，整个工作流只在随后旧缓存保存步骤因缺少 `primary-key` 失败。该运行不包含
后来的 RTTI、工作线程 TLS 析构、条件变量或仅接受用户控制台通过标记的修正。

后续运行样例另加入std::exception_ptr生命周期检查：离开原catch后保留异常，在另一
线程重抛并按原类型捕获，join后释放最后一个引用，要求异常对象恰好析构一次。宿主
C++17严格编译和执行通过；上面两个已启动任务不包含这项后续扩展，其目标运行结果
仍待另行验证。阶段日志区分普通catch清理与跨线程异常清理，便于定位后续陷阱。
已针对 `b8b4557d078951ad0d1670967dd71c51248add3b` 启动包含此扩展的
[wasm64 定向检查](https://github.com/HighCWu/distro/actions/runs/38895974365)。该运行的
目标构建及执行步骤已成功，日志逐项确认普通 catch/RAII、跨线程保留异常对象清理及
最终 `::vm-test::pass`。整个工作流显示失败是其后缓存保存缺少 primary-key，
不是用户程序失败；缓存配置已另行修复。这一证据仍只覆盖 Node 上的该固定提交。

后续样例再加入多重继承异常检查：按 `std::exception` 基类捕获派生异常，使用
`dynamic_cast` 回到完整派生对象及另一基类，检查消息、成员值与恰好一次派生析构。
此用例覆盖基础 catch 之外的类型匹配和指针调整；宿主 C++17 严格编译及运行通过，
浏览器套件也要求其阶段标记。上面的已启动运行不包含此新增用例，Wasm 结果仍待验证。
包含此扩展的 [wasm64 SDK 检查](https://github.com/HighCWu/distro/actions/runs/38903701981)
对应 `6f168e675e65379c559ee8b719d739a0b7067c04`，目标构建和运行检查、缓存保存及
整个工作流现均已成功。这证明该固定提交的 Node/Linux-Wasm 多重继承 RTTI 用例
通过，不代表浏览器或后续扩展已通过；它不包含后来增加的 `wasm-linux-sdk-info`
安装入口、工作线程 TLS 析构及条件变量用例。

后续样例加入工作线程的非平凡 `thread_local` 对象退出清理：连续创建两个线程，
每个线程初始化两个对象，要求逆序且恰好一次析构，并在 `join` 后检查清理完成。
计数器存活至线程结束，不以未同步轮询判断结果。GCC/Clang 宿主严格编译及运行通过，
浏览器用例要求对应阶段标记；上述旧提交均不覆盖此扩展，后续目标结果见下文。

包含 TLS 析构的 [wasm32 检查](https://github.com/HighCWu/distro/actions/runs/38907748752)
（distro `7c5cc50`）已确认在链接时失败，尚未执行用户程序：libc++abi 强引用了 musl
未实现的 `__cxa_thread_atexit_impl`。原因是运行库的 CMake 使用 STATIC_LIBRARY
try-compile，`check_library_exists` 没有真正链接可执行程序，因此误报符号存在。
运行库现显式配置 `LIBCXXABI_HAS_CXA_THREAD_ATEXIT_IMPL=OFF`，选择 libc++abi
上游已有的 pthread TSD 析构队列回退，不在应用中伪造符号或忽略链接错误。
宿主回归重现了缺失符号的静态库探测误报，并验证显式关闭生效；这不是目标运行
证据。随后固定 distro `88a5ce1abdd87ddb6dea76151130de2557719e90` 的
[wasm32](https://github.com/HighCWu/distro/actions/runs/38918153433) 和
[wasm64](https://github.com/HighCWu/distro/actions/runs/38918154357) 定向 CI 均已完整
成功，覆盖 C++ 链接、Node/Linux-Wasm 运行、工作线程 TLS 析构及条件变量。
检查依赖的新版 SDK profile 也包含安装后许可目录的 SHA256SUMS 核验。
这不代表浏览器或任意其他构建配置通过。回退对主线程析构顺序及动态卸载存在上游
已说明的限制，不能据此声称完整 C++ 生命周期兼容。

再后续样例增加 `std::mutex` / `std::condition_variable` 双向交接，验证工作线程
等待任务、主线程等待完成，以及锁保护下的结果可见性。等待使用谓词并有 10 秒
故障上限，不依赖固定 sleep 或未同步轮询；宿主 GCC/Clang 通过。较早重型运行
不包含这项新增用例；上节 `88a5ce1` 的双位宽 SDK 运行检查已覆盖，
但不能将其结果视为浏览器验证。

### 先前异常生成问题

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
两项均已结束且失败，失败步骤为 Build isolated check，不能作为异常支持通过的证据。
这些是后续 WebAssembly C++ ABI 修复之前的历史运行；ABI 修复后的通过记录及
跨线程异常用例的覆盖范围见上文，不能将不同提交的结果相互替代。

## 验证状态

Autoconf项目可使用SDK的`wasm-linux-configure`入口，使用方式、配置探测及验证
边界见[Autoconf构建说明](sdk-autoconf.md)。
Meson项目可使用安装后的cross file及显式构建机工具，见[Meson构建说明](sdk-meson.md)。

宿主g++ C++17严格编译及执行通过，Nix语法格式化和仓库元数据检查通过。本地没有
构建Linux或LLVM。公开Node [wasm32](https://github.com/HighCWu/distro/actions/runs/38859969295)
及[wasm64](https://github.com/HighCWu/distro/actions/runs/38859974701)早期检查均失败，见上述
C++异常生成诊断。后续 wasm64 ABI 修复已在 Node 中运行通过，具体提交及覆盖边界见上文；
跨线程异常生命周期检查也已在 wasm64 Node 目标通过，见上文独立步骤与日志证据。

浏览器运行套件现为两个位宽分别构建 C++ initramfs，使用匹配的内核和工具链。
Chromium/Firefox 的 memory64 及 runtime-wasm32 检查均保留原 C 用例，并新增 C++
容器、类型化 catch、RAII、跨线程 exception_ptr 清理及线程/TLS 用例。测试必须收到
各阶段日志和最终通过标记，内核启动成功不计为用户程序通过。复用现有超时、失败检测
及机器关闭逻辑。distro `2dad046` 的
[Chromium wasm64 检查](https://github.com/HighCWu/distro/actions/runs/38923713778)
实际目标构建/检查及整个工作流已成功，包含上述 C/C++ 扩展、SQLite 锁与热日志
恢复以及下述关闭判定。此结果不替代 Firefox 或 wasm32 的对应验证。

浏览器 runtime 检查现在要求机器关闭也成功，不能只收到用户程序通过标记后忽略
`machine.closed` 的拒绝。原有总超时同时覆盖运行和关闭阶段；关闭卡住不能产生
成功结果，也不无限等待。若程序、启动或 watchdog 已先失败，保留原始原因，而
不让后续关闭错误覆盖它。11 项宿主生命周期回归覆盖延迟关闭、关闭拒绝、关闭
超时、原始失败保留及超时后迟到机器的清理；加上协议检查共 15 项通过。
这些宿主回归强化测试判定，不会强制终止卡住的存储操作；真实 Chromium wasm64
集成结果见上文，不据此宣称跨浏览器存储恢复已经验证。

本轮独立于[线程等待回归](time-abi.md)继续推进。CI运行期间可开展不依赖其结果的
文档、代码审计和SDK任务；依赖运行结论的支持声明及修复决策，仍需等待对应证据。
