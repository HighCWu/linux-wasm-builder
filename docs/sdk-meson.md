<!-- SPDX-License-Identifier: MIT -->

# 使用SDK构建Meson项目

两个SDK profile均提供Meson cross file，通过`WASM_MESON_CROSS_FILE`指向安装后的
`share/meson/linux-wasm.ini`。它选择对应的C/C++编译器、归档工具、strip及目标
pkg-config，声明Linux、wasm32或wasm64、小端序，并默认构建静态库。

```sh
nix develop './sources/distro#sdk'
# wasm64使用：nix develop './sources/distro#sdk-wasm64'
meson setup build-meson sources/distro/distro/sdk/meson-example \
  --cross-file "$WASM_MESON_CROSS_FILE" --buildtype=release --wrap-mode=nofallback
meson compile -C build-meson
```

示例产物是`build-meson/sdk-meson.wasm`，须在Linux/Wasm环境运行。不同profile应
使用独立的构建目录；SDK仍依赖Nix store。

## 构建机工具与目标程序

SDK shell中的CC/CXX选择Wasm工具链；CC_FOR_BUILD/CXX_FOR_BUILD选择构建机的
原生编译器，PKG_CONFIG_FOR_BUILD选择构建机的依赖查询工具。Meson项目需用
`native: true`声明构建期间执行的工具，目标依赖继续使用cross file中的pkg-config。
两个开发 shell 也提供宿主 binutils，并用 AR_FOR_BUILD/RANLIB_FOR_BUILD 指定
原生归档工具；普通 AR/RANLIB 仍指向目标 LLVM 工具，不应混用。

构建机还需要原生归档工具 `ar`（通常由 binutils 提供）。cross file 的 `ar`
只选择目标归档工具，并不替代 Meson 对构建机工具的探测；仅把 CC_FOR_BUILD
设为绝对路径，也不会自动把相邻工具加入 PATH。自建精简构建环境需同时提供
原生编译器、归档工具、Meson 和 Ninja，不能把“缺少构建机工具”判断为 Wasm
目标不支持。

示例先以native: true构建一个C代码生成器，执行它生成answer.h，再使用生成的
常量编译目标C++线程程序。生成器源码会拒绝被编译为Wasm，避免误用目标编译器。

cross file设置needs_exe_wrapper=true，不提供执行器。目标程序不能在配置阶段被
当作宿主程序直接运行，项目的运行探针需要明确的交叉编译处理。不能简单把Node
作为这里的exe_wrapper：产物依赖Linux/Wasm运行环境。静态库默认值也不代表显式
请求动态库的项目已经受支持。

## 验证范围

本地以Meson 1.10.0和宿主编译器使用同一cross file模板，验证交叉构建模式、禁止
直接运行目标探针、宿主代码生成器及C++消费程序。为检查工具选择，测试还把普通
CC/CXX/AR环境变量设为不可用路径，依赖cross file和
CC_FOR_BUILD/CXX_FOR_BUILD/AR_FOR_BUILD选择正确工具。该本地流程已纳入主仓库
轻量CI，不计为Wasm运行通过，也不替代 Nix 开发 shell 的实际构建验证。

配置阶段同时对C和C++执行链接探测：通过函数指针引用malloc/free，验证真实libc
符号可链接；另一个有意引用不存在函数的程序必须能编译、但不能链接。两种探测
均不执行目标程序，防止将“只编译成功”误报为接口可用。这些断言也包含在下面的
目标检查中；宿主通过不代表Wasm链接器已通过同样的检查。

依赖发现测试还向宿主PKG_CONFIG_PATH/PKG_CONFIG_LIBDIR注入同名错误元数据和
仅宿主可见的依赖，要求Meson通过SDK包装器选择WASM_PKG_CONFIG_PATH中的目标
元数据，并拒绝宿主专有依赖。本地反例绕过包装器后必须因误选宿主元数据而失败。
这验证的是pkg-config查询边界，不代表任意项目手写的绝对库路径也会被隔离。

集成测试还用Meson构建并安装两个独立静态库，再通过目标pkg-config将它们链接到
示例程序中。主库依赖辅助库，后者仅由Libs.private传递；删除这项元数据后，新的
构建目录必须在链接时因缺少sdk_helper而失败。本地正反例均通过，目标检查复用
相同流程。手动构建基础示例默认不需要这两个库；安装后可用
`-Dinstalled_answer=true`启用，并将WASM_PKG_CONFIG_PATH指向其lib/pkgconfig目录。
若安装前缀为sysroot外的绝对路径，还需设置WASM_PKG_CONFIG_SYSROOT_DIR=/。

目标检查`sdk-check-meson-runtime`及`sdk-wasm64-check-meson-runtime`已加入SDK，
使用安装后的cross file构建程序并在对应默认内核双核环境运行。
2026-10-16已针对distro提交`7d9588ebb50cb443b31e03c8571d7730bc0dcbe6`启动
[wasm32检查](https://github.com/HighCWu/distro/actions/runs/38881763620)和
[wasm64检查](https://github.com/HighCWu/distro/actions/runs/38881774291)。wasm32 已失败：
Meson 在配置构建机工具时找不到 `gcc-ar`、`ar` 或 `gar`，尚未进入目标程序运行。
`dca1a90` 为这项 Nix 检查加入宿主 binutils，修复后的
[wasm32任务](https://github.com/HighCWu/distro/actions/runs/38890441490)仍在运行。
旧 wasm64 任务也仍在运行，且不包含这项修复；不能把任一任务记为运行通过。
这些检查不是完整构建矩阵，也不意味着任意第三方 Meson 项目均兼容；后者仍需
逐项验证。
