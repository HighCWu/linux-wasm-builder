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

示例先以native: true构建一个C静态库和链接该库的代码生成器，执行生成器生成
answer.h，再使用生成的常量编译目标C++线程程序。生成器及其静态库源码都会拒绝
被编译为Wasm，避免误用目标编译器；原生库的符号必须经真实归档、链接才能运行。
这条宿主流程已通过，故意指定无效 AR_FOR_BUILD 的反例也被拒绝。下述新版 wasm64
任务包含原生静态库场景；旧 wasm32 任务不包含它。

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

反向查询也纳入宿主测试：`native: true` 必须取得同名依赖的宿主元数据，且宿主
专有依赖对原生工具仍可见；目标查询则必须拒绝该依赖。测试把普通 PKG_CONFIG
设为无效路径，分别依靠 cross file 和 PKG_CONFIG_FOR_BUILD 选择工具，并通过
PKG_CONFIG_PATH_FOR_BUILD 提供原生依赖目录。下述新版 wasm64 任务包含此扩展，
其目标构建和运行结果见下文；旧 wasm32 任务不能替代该场景的目标验证。

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
[wasm32任务](https://github.com/HighCWu/distro/actions/runs/38890441490)已进入链接阶段，
但因 `wasm-ld` 拒绝 `--start-group` 和 `--end-group` 失败。Meson 1.10.0 的
GNU 风格链接参数生成会为多个库自动加入归档组；这是构建工具适配问题，不是内核运行错误。
不能简单切换到其 Emscripten 链接器类，后者还会生成 Emscripten 专用 `-s` 参数。

SDK 现通过同一修正版 Meson 供两个开发 shell 和目标检查使用：对 wasm32/wasm64
不自动插入 GNU 归档组，其他架构保持原行为。wasm-ld 本身按需解析归档符号，不需要
GNU 的分组重扫参数。补丁保留 Meson 的 Apache-2.0 许可，独立集成与回归测试为 MIT。
回归直接调用 Meson 参数生成器，原版失败、修正版双位宽通过，并验证原生架构仍分组；
宿主完整生成器/静态库/消费程序检查通过。目标 Wasm 链接及运行已取得下文所列证据。

后续消费样例增加 A→B→A 中另一对象的循环归档依赖，并实际调用结果。宿主 Meson
消费检查通过；同一组 C 源文件用本机 Clang 22 的 wasm32/wasm64 unknown-unknown
目标无归档组链接，在 Node 中均返回 42。此无 libc 探针证明 wasm-ld 的惰性归档解析，
不替代 Linux/Wasm SDK 检查。首次
[修复验证](https://github.com/HighCWu/distro/actions/runs/38901721763)在 Nix 求值阶段因
空值字符串转换失败，未执行目标链接。override 已显式处理上游可为空的 patches 和
postPatch 字段；包含循环归档样例的 `d70882a` 已启动
[新版 wasm32 验证](https://github.com/HighCWu/distro/actions/runs/38902458547)。实际日志
确认目标链接、Linux 内运行及 `::vm-test::pass` 均完成（1 项通过），但随后缓存保存
因 `Input required and not supplied: primary-key` 失败，整个工作流仍为失败。
不能把目标程序通过误写成工作流通过，也不能将缓存失败解释成内核故障。
旧 wasm64 任务现已因同样缺少宿主归档器而失败，未进入目标运行。
已针对 `a7d45554607e6e7185524f5d35b47208acf4a6a6` 启动
[新版 wasm64 检查](https://github.com/HighCWu/distro/actions/runs/38895454756)，包含
binutils 修复、原生静态库生成器、双向依赖隔离和 C++ ABI 配置修复。
该任务已因相同 GNU 归档组参数失败；其缓存保存步骤还暴露出 primary-key 输出为空，
没有成功保存编译依赖。保存步骤现显式使用与恢复阶段一致的键。
包含 Meson 补丁、循环归档回归、Nix 空值修复及缓存键修复的 `6f168e6` 已启动
[新 wasm64 验证](https://github.com/HighCWu/distro/actions/runs/38903118046)已通过。
已核对实际日志：1 项通过，输出
`SDK Meson: build-machine generator and target C++ thread verified` 及协议 pass 标记；
整个工作流成功。包含修复的当前固定源码
`052ce84c666ca6f1e1ab8632ef566131134464d5` 已另行启动
[wasm32 补验](https://github.com/HighCWu/distro/actions/runs/39105616827)也已通过。
已核对实际日志：消费构建 1 项通过、零跳过，Linux 内输出相同完成标记与协议 pass，
整个工作流成功。这闭环了缓存键修复后的 wasm32 流程；不把上游 Meson 自身的
可选功能跳过项混同于该消费构建或 Linux 运行检查。
这些检查不是完整构建矩阵，也不意味着任意第三方 Meson 项目均兼容；后者仍需
逐项验证。
