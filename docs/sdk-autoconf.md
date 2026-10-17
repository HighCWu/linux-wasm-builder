<!-- SPDX-License-Identifier: MIT -->

# 使用SDK构建Autoconf项目

wasm32和wasm64的SDK都提供`wasm-linux-configure`。它运行指定的Autoconf configure
脚本，自动传入构建机器的`--build`和所选Wasm平台的`--host`，并选择对应的CC、CXX、
AR、RANLIB、NM及PKG_CONFIG。参数中的host遵循Autoconf术语，表示最终运行程序的
目标平台；build表示执行编译器的机器。

例如，在主仓库进入一个SDK shell，然后为第三方源码建立独立构建目录：

```sh
nix develop './sources/distro#sdk'
# wasm64使用：nix develop './sources/distro#sdk-wasm64'
mkdir build-library
cd build-library
wasm-linux-configure /absolute/path/to/source/configure \
  --prefix=/absolute/path/to/target-install --disable-shared --enable-static
make
make install
```

静态库开关须以项目自身的configure帮助为准。SDK目前提供静态目标库，仍依赖Nix
store。两个profile应使用各自的构建目录、安装目录和缓存；无需手动覆盖wrapper
提供的build/host参数。依赖查询及sysroot外安装方式见[SDK说明](sdk-runtime.md)。

SDK shell包含Autoconf，可为仓库内的`sources/distro/distro/sdk/autoconf-example`
示例执行`autoconf`生成configure。第三方项目若需要其他bootstrap工具，按该项目的
构建要求准备。旧版config.sub可能不认识wasm32/wasm64，需要使用支持这些架构的
GNU config脚本。zlib的手写configure不是Autoconf，不接受build/host参数，应继续
使用[已有zlib构建流程](sdk-runtime.md#使用sdk构建上游zlib)。

## 配置探测

除下述已知不支持的能力外，编译和链接探测仍实际执行，不预填“函数存在”等答案。
Autoconf运行探针由项目的
交叉编译分支处理；若项目没有相应分支，可能需要为该项目补充实现或经过目标验证的
结果。wrapper不会自动执行Wasm程序，也不会把所有运行探针改为成功。

`91480f7` 起默认 CONFIG_SITE 指向 SDK 安装的 `share/linux-wasm-sdk/config.site`，
与 distro/stdenv 共用同一源码，不继承宿主站点文件。它仅给出已知不支持能力的
负向答案：fork/vfork 及 works 探测、完整固定/文件 mmap、dlopen 搜索/链接与
sigaltstack。匿名私有读写映射不被禁用，普通 `mmap`/`msync` 链接探测和未知能力
仍不预填；标准符号存在也不等于内核支持全部语义。

原因是 `AC_FUNC_MMAP` 对 Linux 交叉编译会默认回答成功，musl 的动态加载 stub
也可能链接成功；两者都不足以证明所需运行语义。SDK 先前默认 `/dev/null` 没有
保护外部项目避开这些误判，而 distro 配方早已有相同负向约束。

确实需要目标站点配置时，显式设置 `WASM_CONFIG_SITE=/absolute/path/to/target.site`；此文件会作为
shell代码由configure加载，应只选择适用于当前profile的文件。其余configure参数
原样传递，包括项目选项、CFLAGS等。不要把-Werror强加给所有configure探针：某些
生成的函数探针使用简化原型，会触发编译器诊断；实际软件构建可独立采用严格检查。
显式 `WASM_CONFIG_SITE=/dev/null` 会绕过默认策略，是调用方主动选择，不是兼容
修复或能力证明。Autoconf 将 CONFIG_SITE 视为空白分隔的文件列表，文件路径不应
包含空白。SDK 配置记录新增 `paths.configSite`，安装检查比较其内容与共享源文件。

`27a16a1` 起包装器在调用 configure 前验证该路径：缺失、不可读或指向目录时
退出 66，含空白时退出 64。这个入口只接受单个站点文件，不接受 Autoconf 的
可选文件列表；否则不存在的路径可能被 Autoconf 静默忽略，使负向策略失效。
`/dev/null` 仍是显式绕过的有效选择，不把写错路径当作绕过意图。

## 验证范围

本地使用真实Autoconf和Make验证交叉编译模式、malloc存在、缺失函数不存在、运行
探针延后，以及宿主站点文件隔离和显式目标站点文件加载。随后构建并运行宿主版本的
示例。该流程已纳入主仓库轻量CI；宿主执行不计为Linux/Wasm运行通过。

示例还通过CC_FOR_BUILD/CFLAGS_FOR_BUILD编译宿主代码生成器，先生成头文件，再
使用CC构建目标程序。SDK shell提供原生CC_FOR_BUILD；目标Nix检查也显式选择原生
编译器。生成器拒绝被编译为Wasm，Make规则显式依赖生成的头文件，支持并行构建。
这些变量需要项目自身的构建规则配合，wrapper不会自动识别或改写第三方代码生成器。
生成头文件先写入临时文件，成功后再替换；普通生成失败会清理临时文件并保留已有
完整头文件。回归覆盖部分输出后失败、首次生成失败、恢复重建及无修改时的增量检查；
不将此规则表述为断电或SIGKILL后的持久化保证。

另有反例使用未提供交叉编译分支的AC_RUN_IFELSE：configure必须以非零状态退出，
报告无法在交叉编译期间运行测试程序，且不能进入运行成功或运行失败分支。这个检查
也由目标SDK验证流程复用。遇到此错误时，应定位config.log中的探针，为上游项目
补充适当的交叉编译处理，或提供有目标验证依据的配置答案；不要把它一律改成成功。

目标检查已加入SDK，名称为`sdk-check-autoconf-runtime`和
`sdk-wasm64-check-autoconf-runtime`。它们使用安装后的wrapper构建同一示例，再由
相应默认内核运行。最初记录时尚未触发这两项重型检查；当前复验状态见下节，
不能据此宣称任意Autoconf项目已经兼容。

## 共享能力策略验证

新增真实 Autoconf 探针检查默认策略得到五组不支持答案，显式绕过后复现 Linux
交叉编译的 `mmap=yes` 假设；继续验证继承的宿主站点文件不会加载、显式目标文件
可加载，以及没有交叉回退分支的运行探针必须失败。宿主数据生成器、部分输出
失败后保留完整头文件和增量构建检查保持不变。

共享策略与包装器接线、真实 Autoconf、Clang 参数转发及 CMake 相关 22 项本机
检查全部通过，未跳过；这不执行 Wasm 程序。目标双位宽 Autoconf 运行检查还需
公开 CI 验收，不把站点答案本身当作新的系统功能已经实现。

固定 `91480f7` 的 [wasm64 目标检查][autoconf64]和 [wasm32 目标检查][autoconf32]
均已通过计划与派生解析。wasm32 已成功，实际日志确认安装后的 SDK 包装器完成
真实 Autoconf 回归，1 项通过、零跳过；构建产物在 Linux/Wasm 内输出
`SDK Autoconf: cross configuration and allocation verified` 和 `::vm-test::pass`。
因此该版本的 wasm32 配置、宿主生成器、目标编译与分配运行路径已有证据。
同版 wasm64 随后也成功，独立日志确认相同 Autoconf 回归 1 项通过、零跳过，
以及 Linux 内相同分配运行标记和最终 pass。因此双位宽均有该版目标运行证据，
仍不宣称任意项目已兼容。

[autoconf64]: https://github.com/HighCWu/distro/actions/runs/39075979454
[autoconf32]: https://github.com/HighCWu/distro/actions/runs/39075983153

路径校验的回归还使用标记脚本证明三种无效配置均在 configure 启动前失败；
有效目标文件、默认策略、宿主隔离及 `/dev/null` 覆盖继续通过。相关 22 项本机
检查全部通过；上述 `91480f7` 检查不包含这项后续校验，不能替代新版验收。
旧 wasm32 任务成功结束后，固定 `27a16a1` 的[新版 wasm32 复验][site-path-recheck]
已启动；不取消、替换或重复启动仍在运行的 wasm64 任务。

[site-path-recheck]: https://github.com/HighCWu/distro/actions/runs/39076874833

旧 wasm64 检查成功结束后，[新版 wasm64 复验][site-path64-recheck]固定 `1a7e57a`
启动，包含同一 `27a16a1` 路径修复；计划解析通过，目标构建仍在进行。

[site-path64-recheck]: https://github.com/HighCWu/distro/actions/runs/39077156157
