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

编译和链接探测仍实际执行，不预填“函数存在”等答案。Autoconf运行探针由项目的
交叉编译分支处理；若项目没有相应分支，可能需要为该项目补充实现或经过目标验证的
结果。wrapper不会自动执行Wasm程序，也不会把所有运行探针改为成功。

默认CONFIG_SITE为/dev/null，避免继承宿主站点文件的能力判断。确实需要目标站点
配置时，显式设置`WASM_CONFIG_SITE=/absolute/path/to/target.site`；此文件会作为
shell代码由configure加载，应只选择适用于当前profile的文件。其余configure参数
原样传递，包括项目选项、CFLAGS等。不要把-Werror强加给所有configure探针：某些
生成的函数探针使用简化原型，会触发编译器诊断；实际软件构建可独立采用严格检查。

## 验证范围

本地使用真实Autoconf和Make验证交叉编译模式、malloc存在、缺失函数不存在、运行
探针延后，以及宿主站点文件隔离和显式目标站点文件加载。随后构建并运行宿主版本的
示例。该流程已纳入主仓库轻量CI；宿主执行不计为Linux/Wasm运行通过。

目标检查已加入SDK，名称为`sdk-check-autoconf-runtime`和
`sdk-wasm64-check-autoconf-runtime`。它们使用安装后的wrapper构建同一示例，再由
相应默认内核运行。当前尚未触发这两项重型检查，现有C++与其他目标CI继续运行；
不能据此宣称任意Autoconf项目已经兼容。
