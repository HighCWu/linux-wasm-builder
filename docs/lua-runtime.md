<!-- SPDX-License-Identifier: MIT -->

# Lua 双位宽用户态与异常展开验证

distro `3bdb90c` 在现有 Lua 5.4.8 移植上增加独立 `lua-wasm64`，不改变默认
wasm32 包、软件源或最小根盘。工具链、musl、compiler-rt、BusyBox、平台参数及
安装系统测试运行器均显式选择对应 wasm64 版本。

## 实际目标检查

两种位宽共用完整的 `distro/lua/language-test.sh`，不只验证解释器能打印版本号：

- Lua 模块默认搜索路径、require、算术、字符串、表和文件写入/读回。
- 两种指针宽度均使用 Lua 标准 64 位整数；检查超出浮点精确范围的整数、上下限和
  8 字节 pack/unpack 往返。
- 协程 yield/resume、pcall 字符串及表对象异常；异常展开时 `<close>` 资源逆序
  清理并保留错误对象身份，以及关闭挂起协程时清理仍存活的资源。
- os.execute 的非零状态、io.popen 输出与关闭，缺失共享模块显式失败。
- 目标 luac 生成普通及去调试信息的 core/coroutine 字节码，并由同一目标 lua
  重新运行全部断言；非法源码和截断字节码必须失败。

每次构建均对 lua、luac 检查实际 Wasm 位宽、唯一共享 env.memory 导入及平台
内存上限；最终运行标记只有在全部语料和许可证文本检查通过后才输出。
Lua 使用工具链已有的 SjLj lowering；本项不改内核、musl、执行 ABI 或 fork 约束。
字节码只承诺本次同架构、同版本往返，不声称可以跨位宽或跨 Lua 版本分发。

重型构建及 Linux 运行仅在公开 Actions 执行：

```sh
nix build './sources/distro#checks.x86_64-linux.lua-check-language'
nix build './sources/distro#checks.x86_64-linux.lua-wasm64-check-language'
```

## 宿主验证与证据边界

轻量检查命令需要原生 Lua 5.4 和 luac：

```sh
node --test sources/distro/distro/lua/language-host.test.js
```

可用 `LUA_HOST_INTERPRETER`、`LUA_HOST_COMPILER` 指定绝对路径。本地使用官方
Lua 5.4.8 源码原生构建，下载归档 SHA-256 与官方目录公布的
`4f18ddae154e793e46eeab727c59ef1c0c0c2b744e7b94219710d76f530629ae` 一致。
完整语料执行和依赖/语法接线两项检查通过；CI 宿主使用 Ubuntu 的 Lua 5.4 包，
不把该包的版本误称为目标的 5.4.8。

宿主检查只调整隔离临时路径、命令查找和 PID 1 停机循环。模块路径通过环境
显式设置，许可证文件使用测试占位文本；因此不证明目标默认路径、许可证包
内容或软件安装成功。它保留实际 Lua 断言、进程调用和 luac 编译执行，不模拟
解释器结果，但原生 setjmp/longjmp 仍不证明 Wasm SjLj 正确。

固定 `3bdb90c` 的
[wasm32](https://github.com/HighCWu/distro/actions/runs/39061282695) 和
[wasm64](https://github.com/HighCWu/distro/actions/runs/39061286995) 安装系统检查
曾通过计划解析、进入重型构建，但同期 QuickJS 目标日志暴露
共用的许可路径错误：包内 `/share/licenses` 不会被安装工具添加 `/usr` 前缀。
`d06effa` 已一并修正 Lua 脚本并增加直接执行实际复制/检查片段的两项跨包回归，
旧 `3bdb90c` 不包含修正，不能据其结果验收当前版本。固定 `d06effa` 的修正版
[wasm32](https://github.com/HighCWu/distro/actions/runs/39061566007) 和
[wasm64](https://github.com/HighCWu/distro/actions/runs/39061569694) 目标复验已提交，
现已全部成功，实际日志确认两个程序的匹配位宽 ABI 检查通过，并在 Linux 输出
完整整数64、模块、I/O、协程清理、spawn、字节码往返阶段及最终 pass。它们固定
`d06effa`，不包含后续开发输出拆分、C 嵌入消费者或 pass 后失败判定修正，不扩大
为这些后续变更或浏览器运行的证据。
现有静态库和头文件在下述后续提交中拆为独立开发输出，浏览器用例也已接线但
尚待实际验收；不据此宣称已验证动态模块或任意应用。

## 安装后的 C 开发路径

distro `a4a8c76` 将两种位宽的头文件和 `liblua.a` 移入独立 `dev` 输出，提供相对
`${pcfiledir}` 的 `lib/pkgconfig/lua.pc`，并复制原始许可证材料。默认安装只选 `out`，
不把开发归档装进运行根盘。原先使用 `${lua}/include` 或 `${lua}/lib` 的构建应改用
`lua.dev`；wasm64 使用 `lua-wasm64.dev`，不能混用另一位宽的归档。

```sh
nix build './sources/distro#lua-wasm64.dev' --out-link result-lua-dev
export WASM_PKG_CONFIG_PATH="$PWD/result-lua-dev/lib/pkgconfig"
export WASM_PKG_CONFIG_SYSROOT_DIR=/
wasm-linux-cc app.c $(wasm-linux-pkg-config --cflags --libs lua) -o app.wasm
```

上例应使用匹配的 wasm64 SDK。`wasm-linux-pkg-config` 强制查询静态依赖，元数据
包含 `-lm`。普通 `.lua` 模块搜索路径仍为 `/usr/share/lua/5.4`；开发文件搬移不改变
用户程序内的 Lua 模块布局，不启用 dlopen 或第三方共享模块。

新增 `sdk/lua-example.c` 是 MIT C 消费者：创建 Lua 状态，注册带上下文指针的
C 闭包及返回错误对象的 C 函数，通过脚本检查64位整数精度、受保护调用、跨 C/Lua
错误传播时的资源清理、协程恢复，再由 C 读回精确结果。目标开发检查先复制已安装
`dev` 到新前缀，仅使用该前缀的头文件和归档构建这个程序，不重编 Lua 源码；随后
校验消费者的 Wasm ABI 并启动 Linux 检查完整完成标记。

```sh
nix build './sources/distro#checks.x86_64-linux.lua-wasm64-check-development'
nix build './sources/distro#checks.x86_64-linux.lua-check-development'
```

两项新增宿主检查验证元数据搬移/删除后禁止宿主回退，并实际以 GCC、Clang 链接
复制的原生 Lua 头文件/归档后执行同一 C 消费者；连同语言和许可布局共 6 项通过。
这不证明 Wasm 归档、目标回调签名或 SjLj。固定 `a4a8c76` 的
[wasm64](https://github.com/HighCWu/distro/actions/runs/39061875688) 和
[wasm32](https://github.com/HighCWu/distro/actions/runs/39061878991) 开发检查均通过
计划解析，但随后失败。双位宽实际日志确认 Lua/luac 的 ABI 检查成功，消费者
构建在 `Lua metadata did not relocate` 处停止，尚未编译运行 C 消费者。
此前解释器检查不包含此次多输出变更，不能代替开发包验收。

### 可分发的独立示例与正常退出

`35f9e21` 修正上述整理问题：固定 nixpkgs 的 `_multioutDevs` 会把 `.pc` 的相对
`includedir` 改成绝对开发输出路径。Lua 已显式安装头文件/归档/元数据，因此关闭
该包的自动开发文件整理，并将 `outputDoc` 指向 `dev`，避免示例文档移到运行包。
不改全局 Nix 整理行为，也不删除消费者的迁移拒绝检查。

开发输出现携带 `share/doc/lua/examples/embedding.c`、构建说明与自有 MIT 文本。
用户可从复制后的完整开发包构建示例，无需检出本仓库；源码默认正常返回状态 0。
仅作为 Linux 测试 PID 1 的变体定义 `LINUX_WASM_TEST_INIT`，成功后保持存活，
避免 init 退出引发内核 panic。两个变体都从开发包内安装的源码编译并检查目标 ABI。

```sh
export LUA_DEV=/absolute/path/to/copied-lua-dev
export WASM_PKG_CONFIG_PATH="$LUA_DEV/lib/pkgconfig"
export WASM_PKG_CONFIG_SYSROOT_DIR=/
wasm-linux-cc -O2 "$LUA_DEV/share/doc/lua/examples/embedding.c" \
  $(wasm-linux-pkg-config --cflags --libs lua) -o lua-example.wasm
```

必须使用对应位宽 SDK，生成的是 Linux/Wasm 程序而非 WASI 程序。新增目标检查由
BusyBox 启动普通示例，要求超时前成功退出、完整阶段标记及 pass，拒绝 fail；子程序
输出仅写入临时文件，不能在退出前被运行器误认作整项测试成功。根盘还检查随包
携带的 Lua、musl、compiler-rt 和示例许可文本。

```sh
nix build './sources/distro#checks.x86_64-linux.lua-wasm64-check-application'
nix build './sources/distro#checks.x86_64-linux.lua-check-application'
```

相关 39 项本地检查通过，包括从迁移后的源码/头文件/归档经 GCC、Clang 编译执行，
以及退出非零、漏阶段、漏 pass、显式 fail、打印 pass 后卡住等负向场景。对 Nix
整理选项的宿主检查属于接线检查，不证明实际目标打包。固定 `35f9e21` 的新
[wasm64](https://github.com/HighCWu/distro/actions/runs/39063135640) 与
[wasm32](https://github.com/HighCWu/distro/actions/runs/39063138847) 公开 Actions
均已成功，实际日志确认解释器和两个 C 消费者的匹配位宽 ABI 门禁，以及
`Lua application: installed example exits normally through Linux verified` 和最终 pass。
这验证了从复制安装的开发包源码/头文件/归档构建普通应用并在 Linux 正常退出，
不是仅以宿主编译结果推断目标可用。

### 宿主开发包路径发现修正

主仓库固定 `630f34d` 的
[轻量 CI](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39063493557)
失败于原生 C 消费者的头文件发现：Ubuntu 的 `lua5.4.pc` 可将 `includedir` 指向
`/usr/include`，实际通过 `Cflags` 选取 `/usr/include/lua5.4`；不能将父目录变量
直接当作头文件安装目录。此失败不同于目标包的 Nix 路径迁移错误。

distro `08dffcb` 优先使用原生 pkg-config 的 `-I`/`-L` 目录，并验证头文件/静态
归档实际存在，变量值仅作为候选；允许系统目录标志显式输出，保留配置原生路径
的环境变量。新增版本化头文件/多架构归档布局及缺失头文件拒绝回归。本地相关
46 项通过。固定主仓库 `4152244` 的
[轻量 CI](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39064029545)
现已成功，实际 Ubuntu 日志确认原生路径发现、语言语料和 C 消费者检查通过；
不再仅依靠显式配置本地原生路径绕过发行版布局。
这只修正宿主测试发现逻辑，不修改目标 Lua、SDK 或 Wasm 执行语义。

## 浏览器共享用例

distro `108f20a` 为 wasm32/wasm64 浏览器套件各增加两个用例，精确报告门禁
从 16 项扩为 18 项：

- 解释器：使用原始 `language-test.sh`、对应位宽的运行包和 BusyBox；与安装系统
  检查共用唯一一份模块夹具，不额外添加许可路径别名或重写脚本断言。
- C 嵌入：与 Node 开发检查使用同一个从搬移后的安装头文件/归档构建的程序，
  不在浏览器路径中换成重新编译 Lua 源码的简化程序。

两条路径分别要求完整阶段标记、最终 pass 且没有 fail，并复用用户控制台协议、
启动/关闭看门狗。轻量负向检查验证下载错误、缺失阶段或 pass、混入 fail 和报告
漏跑均被拒绝。相关 33 项本地轻量检查通过（含原生 Lua 语料、GCC/Clang C 消费者、
许可布局与共享运行器）；这些不是目标浏览器执行证据。

固定 `108f20a` 的 wasm64
[Chromium](https://github.com/HighCWu/distro/actions/runs/39062203518) 和
[Firefox](https://github.com/HighCWu/distro/actions/runs/39062207326) 完整 18 项检查
均已失败，实际日志确认 Lua 开发包因上述迁移路径错误被拒绝，尚未进入浏览器。
固定 `5eca882` 的 Chromium/Firefox 严格运行器复验也在同一依赖处失败，并非关闭期运行
失败。`35f9e21` 包含开发包修正；固定后续 `25d3789` 的
[Chromium](https://github.com/HighCWu/distro/actions/runs/39063499422) 和
[Firefox](https://github.com/HighCWu/distro/actions/runs/39063502379) 完整套件复验均已
通过计划及派生解析。Firefox 已成功，实际日志确认 QuickJS、Lua 语言和安装后
C 嵌入用例均执行，完整 18 项通过，严格报告零跳过/重试；包含迁移修正和加强后
的关闭期判定，不含后加 OpenSSL。同批 Chromium 也已成功，实际日志确认相同
QuickJS/Lua 用例和完整 18 项通过，严格报告零跳过/重试。wasm32
已接线，此固定版本未提交 wasm32 浏览器重型检查。新套件同时使用
修正后的 QuickJS `/share/licenses` 检查，不沿用先前镜像的额外许可别名。

后续 `1823c91` 增加 OpenSSL，套件扩为 19 项；其双浏览器均已通过，
见 [OpenSSL 运行记录](openssl-runtime.md)。`aa28e76` 再加入 curl
TCP/TLS，当前双位宽门禁为 20 项；旧 18/19 项不能替代新增项的实际验收，见
[curl 运行记录](curl-runtime.md)。

解释器浏览器根盘为可丢弃 initramfs，不是安装系统的 ext4 根盘；C 消费者根盘只
包含编译后的用户程序。两者不证明软件包安装、OPFS 持久化、完整根盘升级或浏览器
进程重启恢复；这些仍应由各自的实际检查验收。

## 许可证材料

核对了固定 Lua 5.4.8 归档内 `doc/readme.html` 的 MIT 许可及原始
1994–2025 Lua.org、PUC-Rio 版权声明。包原样安装该 HTML、musl COPYRIGHT 和
compiler-rt LICENSE.TXT；自有测试和集成采用 MIT，依赖保持原许可证。
这些材料不是完整依赖审计，不改变 Linux 内核相应源码的交付义务，也不把内核
实现链接进用户程序。
