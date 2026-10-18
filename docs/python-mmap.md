<!-- SPDX-License-Identifier: MIT -->

# Python mmap 模块恢复与运行边界

`09c6c78` 移除 CPython 3.13.14 配方中的 `py_cv_module_mmap=n/a`，让上游根据
实际 sysroot 检测模块。当前 musl 安装包含 `sys/mman.h`；旧配方中“缺少头文件”
的禁用理由已经过时。未新增 Python 映射模拟层，也不把固定地址映射的配置探测
强行改为成功。

最初模块恢复只涉及现有 wasm32 Python 包。后续 `886e7bd` 已接入完整 wasm64
依赖和独立检查，但尚不代表完整 Python 已构建或运行通过，见下文。

## 应用调用方式

默认内核仅接受有界线性内存内的私有匿名读写映射，Python 应显式选择：

```python
import mmap

with mmap.mmap(-1, 65536, flags=mmap.MAP_PRIVATE,
               prot=mmap.PROT_READ | mmap.PROT_WRITE) as buffer:
    buffer[:4] = b"data"
```

上游 `mmap.mmap(-1, size)` 默认使用 `MAP_SHARED`，当前内核拒绝该请求；模块
可导入不等于默认构造调用可用。默认内核同样拒绝文件映射。不能据此推导共享
内存、跨进程映射、写回、写保护、固定地址替换、resize 或 flush 已获得支持。
实验性 `WASM_FILE_MMAP` 仍关闭，不为 Python 检查启用它。

保持 `--without-mimalloc`、`--with-ensurepip=no` 和 `_posixshmem` 禁用策略：
匿名映射并未验证分配器的 reserve/commit/protection 需求、pip 的安装/文件映射
路径或 POSIX 共享内存。第三方 Python 源码与许可保持不变，自有夹具采用 MIT。

## 验证与证据

独立 `python-check-mmap` 安装系统检查运行同一份 `mmap-test.py`，验证初始清零、
跨页二进制读写、查找和重叠移动、`memoryview` 导出时禁止关闭、释放视图后关闭、
关闭幂等及重复分配。额外要求默认共享请求和普通文件映射以 `EINVAL` 失败。
不靠捕获错误后跳过来报告成功，不修改内核配置以迁就模块。

```sh
nix build './sources/distro#checks.x86_64-linux.python-check-mmap'
```

两项本机检查通过，包含相同 Python 数据操作及目标检查接线；原生 Linux 不执行
Wasm 的拒绝边界断言，不能替代真实目标模块构建和运行。重型构建仅使用公开
GitHub Actions。目标结果尚待验收，不宣称 CPython 文件映射、pip 或浏览器通过。
固定 `d4fafc8` 的[公开目标检查][target-check]已触发，计划与派生解析通过，实际构建/运行仍在进行。

[target-check]: https://github.com/HighCWu/distro/actions/runs/39074334178

## 完整 wasm64 Python 构建接线

`886e7bd` 新增独立 `python-wasm64`，保留同一 CPython 3.13.14 来源和进程补丁，
复用原完整解释器检查，不用更小的解释器或只导入模块的检查替代。新增匹配位宽
的 bzip2、xz、ncurses、readline 包；SQLite 使用既有 `sqlite3-wasm64.dev` 的
静态归档与头文件，zlib、OpenSSL、工具链、BusyBox 和安装系统运行器也均选择
wasm64 实例。目标构建不允许拿 wasm32 归档或宿主库补齐。

SQLite 保持现有禁止 WAL、文件 mmap 和动态扩展加载的配置。Python 的 pip、
ctypes、POSIX 共享内存和 mimalloc 策略不因此改变；完整解释器并不表示所有
上游 CPython 功能均可用。没有加入内核 softmmu 或启用实验文件映射。

构建后检查实际解释器的 Wasm 位宽、共享内存导入和平台声明上限；运行时进一步
检查指针、size_t、long、sys.maxsize 与 sysconfig 一致，wasm64 指针打包往返需
保留超过 4 GiB 的整数。这不是实际分配超过 4 GiB 内存的容量验证。
两个位宽的完整解释器和映射检查都必须先通过运行 ABI 断言。

完整用例仍覆盖压缩库、SQLite、curses、OpenSSL TLS、subprocess、命名同步与
multiprocessing 的 Queue、Pool、Executor、Manager 和嵌套 spawn。

```sh
nix build './sources/distro#checks.x86_64-linux.python-wasm64-check-interpreter'
nix build './sources/distro#checks.x86_64-linux.python-wasm64-check-mmap'
nix build './sources/distro#checks.x86_64-linux.python-check-interpreter'
```

五项本机检查通过，覆盖匿名映射夹具、原生 ABI 正反例、依赖接线和完整检查
保持接入；这不执行目标 CPython、Wasm SjLj、进程恢复或目标库运行。重型构建
继续仅在公开 GitHub Actions 执行，目标和浏览器结果分别验收。

固定 `1870d56`（包含安装许可材料的运行检查）的下列公开任务均已通过计划和
派生解析，随后均在编译 `mmapmodule.c` 时失败：musl 没有公开 `msync` 声明。
三项日志均已核实，没有产生解释器运行成功的证据；与下节首次 wasm32 映射
失败同因。旧任务均自然结束，没有为新检查取消或重启。

| 目标检查 | 公开任务 |
| --- | --- |
| wasm64 完整解释器 | [构建与运行][python64-full] |
| wasm64 私有匿名映射 | [构建与运行][python64-mmap] |
| wasm32 完整解释器 | [回归检查][python32-full] |

[python64-full]: https://github.com/HighCWu/distro/actions/runs/39074719257
[python64-mmap]: https://github.com/HighCWu/distro/actions/runs/39074722651
[python32-full]: https://github.com/HighCWu/distro/actions/runs/39074726138

## 解释器及静态依赖许可材料

安装输出保存 CPython、bzip2、xz、ncurses、readline、zlib、SQLite、OpenSSL、
musl 和 compiler-rt 的原始许可材料，完整运行检查要求关键文件存在。材料来自
该次构建实际依赖，不以宿主样本文本代替，也不宣称这是完整的发布合规审计。

本配置静态链接 GNU Readline，分发该解释器时必须评估并遵守其 GPL 等依赖条款，
包括适用的对应源码提供要求；不能把整个解释器重标为 MIT。这不同于把平台上
独立开发的应用或 Python 脚本一概改为 GPL。SDK、自有集成、运行组件和开发者
应用仍需按各自实际代码与链接关系分别判断，不能仅凭平台支持闭源商业软件来
免除特定依赖的义务。若未来提供不链接 Readline 的变体，应单独设计和验收，
不在此处悄悄移除现有 REPL 功能来规避问题。

## 安装后 sysconfig 门禁

`09f19d0` 为两个位宽的完整解释器和映射检查加入 `--installed-layout`。实际运行
解释器后查询 `sysconfig`，要求标准库、site-packages、头文件、scripts 和 data
目录符合 `/usr` 安装布局，prefix/exec_prefix 同样为 `/usr`。操作性 `CC`、`CXX`、
`AR`、`CFLAGS`、`CPPFLAGS`、`LDFLAGS`、`LIBS` 不能引用 `/nix/store/`，缺失字段
也不能静默跳过。失败时保留字段名和值，便于后续针对真实构建结果修正。

不因这一检查新增编译器、动态加载器或扩展构建支持；历史 `CONFIG_ARGS` 等来源
记录不被当作运行搜索路径，也不为让测试通过而删除来源信息。尚未替换未知路径
或声称所有 sysconfig 字段均已完全搬移。

Python 六项轻量检查通过，其中布局夹具含六个 unittest 用例，分别验证合法布局、
错误安装目录、缺失目录、操作参数路径泄漏、缺失操作字段及错误 prefix。
SDK CMake 三项回归也通过。合成配置仅验证断言，真实目标仍查询实际安装的
CPython；固定 `1870d56` 的三项重型检查不包含本次新门禁，不能替代其验收。
在这些任务终态前不重复提交同一目标检查，也不取消或重启现有任务。

主仓库固定 `011f090` 的[轻量 CI][python-host-ci]已成功，实际日志确认 Python
原有五项夹具、完整 wasm64 接线、libcurl 许可复制回归、原生 CMake 安装以及 RPATH
正反例执行。这是加入新布局门禁前的宿主证据，不代表目标 CPython 或布局已通过。

[python-host-ci]: https://github.com/HighCWu/linux-wasm-builder/actions/runs/39074757317

## 首次实际构建失败与 msync 符号恢复

固定 `d4fafc8` 的[首次 wasm32 映射检查][target-check]已失败结束。实际日志确认
上游启用了 `mmap` 模块，但编译 `Modules/mmapmodule.c` 的 `flush` 方法时找不到
`msync` 声明。当前 musl 虽安装了 `sys/mman.h`，仍对 Wasm 同时隐藏该声明和
包装源码，不能把“头文件存在”等同于该模块所需接口完整。没有进入 Python
安装、导入、映射运行或 ABI 验证，也不是映射运行语义失败。

musl `4776ccd0` 仅恢复上游 `msync` 声明与原有 cancellation-point 系统调用
转发函数；保留 musl 的 MIT 许可，不改变 Linux。默认内核没有实现这项写回
调用，应返回 `ENOSYS`，不是加入无条件成功的空实现。distro `0d71aef` 固定新
musl 来源及解包哈希，并要求真实 Python 私有匿名映射的 `flush()` 报 `ENOSYS`，
且失败后已有字节不变。内核和实验文件映射配置保持不变。

新增两项轻量检查覆盖 wasm32/wasm64 公共声明语法，以及 GCC/Clang 编译实际
musl 包装源码的调用转发。后者重命名公共符号，避免缺失包装时意外调用宿主
libc；模拟 syscall 返回失败和成功，验证指针、原生 size_t、flags 与返回值，
并不证明目标 syscall 已成功运行。原整数头文件检查和 Python 六项轻量检查
同时通过。哈希计算先对旧已固定树复核一致，再计算新提交的 NAR 哈希；实际
fetch、目标链接和运行仍须修正后的公开 CI 验收。

旧映射任务终态后才重新触发 `python-check-mmap`，新版本同时包含安装布局门禁。
其他仍在运行的目标任务不取消、不重启，其旧版本结果也不能替代这两项新增验证。
固定 `0d71aef` 的[修正后 wasm32 映射复验][msync-recheck]已通过计划和派生解析，
实际完成 Python 构建与安装，越过原 `msync` 编译错误；随后在测试根盘组装失败：
OpenSSL 声明依赖 `ca-certificates`，映射测试的安装集合却漏了该包。尚未启动
Linux，不能据此宣称安装布局或运行断言通过。

[msync-recheck]: https://github.com/HighCWu/distro/actions/runs/39075438707

旧 `1870d56` 三项检查确认自然失败后，固定 `91480f7` 启动了对应复验，包含
musl 修复和安装布局门禁；均通过计划解析并进入构建，当时尚无目标运行结论。
当时仍在运行的 `0d71aef` wasm32 映射复验没有被取消，其最终结果见上文。

| 修正后目标检查 | 公开任务 |
| --- | --- |
| wasm64 完整解释器 | [构建与运行][python64-full-recheck] |
| wasm64 私有匿名映射 | [构建与运行][python64-mmap-recheck] |
| wasm32 完整解释器 | [回归检查][python32-full-recheck] |

[python64-full-recheck]: https://github.com/HighCWu/distro/actions/runs/39076153816
[python64-mmap-recheck]: https://github.com/HighCWu/distro/actions/runs/39076156858
[python32-full-recheck]: https://github.com/HighCWu/distro/actions/runs/39076159576

随后该版 wasm32 完整解释器检查成功，实际日志确认 `Python ABI` 的 32 位
指针、size_t、long 与 sysconfig 检查，以及 `Python layout` 的安装路径和
操作参数检查，最终输出 `::vm-test::pass`。原完整脚本要求压缩、SQLite、curses、
TLS、subprocess 与 multiprocessing 检查通过后才能到达该标记。
这不包含后续归档应用、启动异常修正或匿名映射专用检查，也不替代 wasm64 验收。

同版 wasm64 完整检查随后也成功，独立日志确认 `Python ABI` 的 64 位指针、
size_t、long 与 sysconfig，以及相同安装布局门禁和最终 pass。至此固定
`91480f7` 的完整解释器原有功能语料获得双位宽 Node 驱动运行证据；后续新增
应用、启动异常语料、映射专用检查和浏览器仍分别验收。

`3356d3f` 补齐映射测试根盘的证书依赖，不移除 OpenSSL 或放宽安装失败检查。
新增回归逐一检查两个 Python 安装集合包含所需包，并核对 OpenSSL 实际依赖声明。
Python 七项本机检查全部通过，格式与源码 pin 检查通过；这些检查不运行目标 Python。
旧 wasm32 映射任务自然失败后才启动[该版复验][certificate-recheck]；仍在运行的其他检查保持不变。

[certificate-recheck]: https://github.com/HighCWu/distro/actions/runs/39076355206

固定 `3356d3f` 的该次 wasm32 映射复验已成功，实际日志确认目标 32 位 ABI、
安装布局、私有匿名字节与缓冲区生命周期、flush 的 ENOSYS、默认共享/文件映射
拒绝，最终输出 pass。旧 `91480f7` 的 wasm64 映射检查也已自然失败，日志确认
同为证书依赖缺失，尚未启动 Linux；不拿 wasm32 结果替代 wasm64。

## 纯 Python 应用分发验收

`a14ce29` 为完整解释器检查加入独立应用流程：生成带 `.dist-info` 元数据及
二进制资源的包，以标准 `zipapp` 制成压缩 `.pyz`，搬到新目录后删除全部源文件。
随后以安装的解释器启动该归档，不继承 `PYTHON*` 环境，实际校验
`importlib.metadata` 版本查询、`importlib.resources` 资源读取、正常退出、空
stderr 和含全部 256 种字节值的双向管道内容。归档及临时安装目录在检查结束后清理。

该流程与原压缩、SQLite、TLS、进程和多进程检查并存，没有以简化解释器替代。
Python 八项本机检查通过，包含真实原生归档启动；源码接线使后续双位宽完整
检查执行同一流程。当前仍在运行的旧提交不含它，尚无目标运行验收结论。
这只覆盖纯 Python 归档分发，不代表 pip、wheel 安装、原生扩展或任意第三方包
均已兼容；`ensurepip` 与动态扩展的现有边界保持不变。

## 无 fork 启动失败的异常兼容

`1a7e57a` 修正 PATH 搜索失败时的公开异常：保留首个非 ENOENT/ENOTDIR 错误
的优先级，同时让 `OSError.filename` 保持调用方传入的程序名，而不是暴露内部
搜索候选路径；字符串与字节程序名分别保持原类型。没有改为 shell 启动或忽略错误。

新增共享语料覆盖缺失目录、不可执行文件和非目录 PATH 项，分别改变顺序，要求
errno、原程序名和类型与普通 Linux subprocess 一致。本机同时运行标准 subprocess
及从实际补丁提取的 PATH 分支，九项 Python 检查通过；恢复旧异常行为的反例确实
因候选路径泄漏失败。补丁格式、Nix、Shell 与 JavaScript 格式检查通过。
提取分支使用原生 posix_spawn，只验证搜索与异常逻辑，不证明目标 fd 动作或
运行时已经通过。完整解释器的双位宽测试已接入同一语料，目标仍需新版 CI 验收；
不据此承诺所有 cwd、权限或并发启动错误都与其他 Linux 架构完全一致。

旧 wasm32 完整检查成功结束后，固定该修正与归档应用语料的
[新版完整解释器复验][spawn-errors-recheck]已通过计划解析并进入构建。
没有取消或重复启动仍在运行的 wasm64 和映射检查。

[spawn-errors-recheck]: https://github.com/HighCWu/distro/actions/runs/39077152138

该任务随后在全仓 treefmt 门禁失败，日志确认是 SDK configure 包装器条件中的
多余引号，而不是 Python 编译、异常或归档应用运行失败；这些新增目标断言尚未
执行。`2bec3ff` 按 CI 的 `shfmt -s` 修正格式后启动[新版 wasm32 完整检查][format-recheck]，
计划解析已通过；仍保留正在运行的 wasm64 与映射检查。

[format-recheck]: https://github.com/HighCWu/distro/actions/runs/39077432857

## 独立浏览器验收

`417d8d0` 为双位宽各注册 Chromium/Firefox 的独立 Python 检查：
`browser-tests-check-python-wasm32-chromium`、`browser-tests-check-python-wasm32-firefox`、
`browser-tests-check-python-wasm64-chromium`、`browser-tests-check-python-wasm64-firefox`。
每项严格要求完整解释器和私有匿名映射两条用例，零跳过、零重试；不改动已有的
libcurl 等 21 项运行套件，也不以 Node 结果代替浏览器报告。

运行器只新增暴露原 Node 检查的 initramfs 与磁盘输入，不以 Node 检查输出作为
浏览器成功证据。浏览器直接复用相同的完整已安装 ext4 根盘、原脚本与匹配位宽
内核；每次启动重新加载为可写内存磁盘，不是另造简化解释器或临时替换用户态。
完整检查继续包括 TLS、进程、多进程、搬移的压缩应用与启动错误语料；映射检查
保留默认内核的不支持边界。页面核对实际 ABI 位宽、布局、各阶段与最终 pass，
还必须等待整机关闭成功，不能只凭启动日志通过。

相关整组 57 项本机检查通过，包含根盘读写隔离、镜像缺失时不启动、阶段缺失、
错误位宽、失败标记和报告缺失用例反例。格式与源码 pin 检查通过。它们仅验证
编排与门禁，不实际启动浏览器；新浏览器验收仍须公开 CI 运行。
内存磁盘的 flush 仅完成内存层操作，不证明 OPFS 持久化或断电恢复；Python 的
Readline 等实际依赖许可证和原始许可材料保持不变。

固定 `417d8d0` 的 [wasm64 Chromium 首轮][python-browser64-chromium]与
[wasm64 映射修正版][python-mmap64-repair]均已通过计划及派生解析并进入重型检查；
尚无实际浏览器或新版 wasm64 映射运行结论。

[python-browser64-chromium]: https://github.com/HighCWu/distro/actions/runs/39077864542
[python-mmap64-repair]: https://github.com/HighCWu/distro/actions/runs/39077861545

同版其余三项浏览器检查也已通过计划及派生解析并进入重型检查，全部实际结果
仍待验收：

| 位宽 | Chromium | Firefox |
| --- | --- | --- |
| wasm64 | [两项验收][python-browser64-chromium] | [两项验收][python-browser64-firefox] |
| wasm32 | [两项验收][python-browser32-chromium] | [两项验收][python-browser32-firefox] |

[python-browser64-firefox]: https://github.com/HighCWu/distro/actions/runs/39077925776
[python-browser32-chromium]: https://github.com/HighCWu/distro/actions/runs/39077928522
[python-browser32-firefox]: https://github.com/HighCWu/distro/actions/runs/39077930733

旧 `91480f7` 完整解释器检查确认成功结束后，固定 `417d8d0` 的
[wasm64 完整解释器复验][python64-current-full]也已启动，以补验后续归档应用与
启动错误语料；不替换仍在运行的 wasm32 完整检查。

[python64-current-full]: https://github.com/HighCWu/distro/actions/runs/39078081460

## 连续启动失败的资源生命周期

`a83c7b0` 扩展同一启动错误语料：连续 64 次请求不存在的程序，每次同时创建
stdin/stdout/stderr 管道并传入一个非继承 fd。每次失败后核对父进程已打开 fd
集合与基线完全一致、传入 fd 的 FD_CLOEXEC 未被修改；全部失败后要求 waitpid
报告无子进程，不以偷偷回收残留 helper 的方式通过。

本机额外注入真实管道 fd 泄漏和父进程继承标志错误，两项反例均被对应断言拒绝，
注入资源由反例清理。这些注入仅在原生 `--patch-logic` 模式执行，目标运行不注入。
实际成功语料接入双位宽完整解释器，浏览器完整用例新增对应阶段要求；整组
57 项本机回归通过，零跳过。仍在运行的 `417d8d0` 检查不含这项后续语料，
后续目标与浏览器需独立验收，不把原生 fork 后端通过当作 Wasm spawn 清理证据。
本项不证明并发打开 fd、信号中断或资源耗尽情况下的全部清理行为。

固定 `2bec3ff` 的 [wasm32 完整复验][format-recheck]现已成功，实际日志确认
32 位 ABI、安装布局、搬移的压缩归档应用、元数据/资源与二进制管道，以及
PATH 错误优先级和原始 str/bytes 文件名断言均通过，最终输出 `::vm-test::pass`。
这项证据不含后续 `a83c7b0` 的连续失败资源清理测试，也不是浏览器通过证明。
资源清理语料及定向缓存修正另在固定 `47cc982` 的 wasm32 完整检查中复验；
已有 `417d8d0` 的 wasm64 和四项浏览器任务继续运行，不以旧版结果替代新版断言。

## wasm64 浏览器与映射实测

固定 `417d8d0` 的 [wasm64 Chromium][python-browser64-chromium]现已成功，重型日志
确认精确执行完整解释器/搬移应用与私有匿名 mmap 两项用例，2 项通过、零跳过、
零重试。该版页面断言实际 64 位 ABI、安装布局、应用与启动错误阶段及最终 pass，
运行器等待成功关闭。它不包含 `a83c7b0` 之后新增的资源清理语料，不据此宣称
Firefox、wasm32、OPFS 持久化或最新版资源清理已通过。

同版 [wasm64 独立映射检查][python-mmap64-repair]也已成功。实际 Linux 输出确认
64 位 ABI 与布局、私有匿名字节/缓冲区生命周期/关闭，以及 flush 明确不支持、
默认共享与文件映射明确拒绝，最后输出 `::vm-test::pass`。此前缺少证书包依赖的
构建失败不再阻塞这项验收，但此结果不扩大默认 NOMMU 的映射能力。

## 描述符耗尽时的启动清理

`8a189fe` 在同一完整解释器语料中增加 RLIMIT_NOFILE 软限制检查，不改变硬限制。
使用少量 `/dev/null` fd 填满可用槽，再分别留出 1、3、5、7 个槽，要求三组标准
管道创建或启动错误通道分配期间明确返回 EMFILE。每轮在 finally 中恢复限制并
关闭占位 fd，随后要求父进程 fd 集合与基线一致，waitpid 报告没有残留子进程。
不通过跳过错误或悄悄回收 helper 掩盖问题。

原生模式故意在启动失败后泄漏一个真实 fd，清理断言必须拒绝，注入 fd 随后
关闭；该故障注入不在目标运行执行。相关 57 项本机回归全部通过、零跳过，格式
与 pin 检查通过。浏览器完整解释器用例新增必须出现的耗尽清理阶段，缺少阶段
的模拟报告继续被拒绝；不是新增一个可以仅凭宿主模拟通过的浏览器用例。

新版已启动 wasm64 Chromium 公开复验；仍在运行的 `47cc982` wasm32 完整检查
不含此项后续耗尽语料。尚无新版实际目标/浏览器结论，也不证明并发 fd 打开、
信号中断、全系统文件表耗尽或内存不足时的全部清理行为。

固定 `417d8d0` 的 [wasm32 Chromium][python-browser32-chromium]和
[wasm32 Firefox][python-browser32-firefox]也已成功，均已核对重型日志：精确执行
完整解释器/搬移应用与私有匿名 mmap 两条用例，各 2 项通过、零跳过/重试。
该版页面核对 32 位 ABI、布局、对应阶段及最终 pass；这些证据仍不包含后续
连续启动失败、fd 耗尽或下面的超时/终止语料。

## 子进程超时、终止与回收

`fa9c5d0` 增加独立的 `process-lifecycle-test.py`，由同一双位宽完整解释器根盘
安装并执行，保留原有应用、线程、多进程、TLS 与映射验收。子进程先完成二进制
stdout/stderr 写入和 SIGTERM 处置，再通过专用管道告知父进程就绪，不用启动
延迟猜测子进程是否已运行。

父进程分别要求 wait 和 communicate 对仍运行的子进程报告 TimeoutExpired；
异常携带原样二进制输出，超时本身不能杀死子进程。随后检验默认 SIGTERM 终止，
以及明确忽略 SIGTERM 后仍超时、再由 SIGKILL 终止两条路径。重试 communicate
必须返回完整且没有重复的输出，两种负信号退出码必须准确；重复 wait 稳定，
直接 waitpid 必须报告已无该子进程。失败路径也主动终止并回收子进程、关闭流。

原生检查另注入一次真实 communicate 结果重复，字节断言必须拒绝。相关整组
58 项本机检查通过、零跳过，Nix/JS/Shell 格式与 pin 检查通过；宿主原生进程
后端不能代替 Wasm 的信号、等待与管道实现证据。浏览器完整用例强制核对新增
阶段，缺失阶段的报告被反例拒绝。新版 [wasm32 Firefox 公开复验][python32-lifecycle]
已通过计划及派生解析并进入重型检查，正在
运行的 `8a189fe` wasm64 Chromium 不含此项后续语料，不重启或取消该任务。

这些短超时只用于确定仍运行的就绪子进程不会被错误回收，不是性能指标；本项
不证明信号处理器重入、整个进程组终止、并发取消或任意信号负载的兼容性。

[python32-lifecycle]: https://github.com/HighCWu/distro/actions/runs/39079272845

## 可交付的示例应用

`95ad6e5` 提供独立纯 Python 压缩应用与源码、资源、包元数据和 MIT 许可证，
通过 `applicationExample` 暴露宿主构建；完整解释器检查实际安装并搬移同一归档。
原有临时生成应用、进程与映射语料保持接入，浏览器完整用例强制要求新阶段。
本机共 59 项相关检查通过，包含归档固定元数据/显式成员、源码删除后运行和缺少
元数据必须失败的三项新增 Python 检查；不作为目标运行或发布上传成功的证明。
使用方式、实际依赖和交付限制见 [纯 Python 应用指南](python-applications.md)。

固定 `417d8d0` 的 [wasm64 完整解释器][python64-current-full]现已成功，实际日志
确认 64 位 ABI、布局、搬移归档应用与启动错误优先级/文件名，以及最终 pass。
同版 [wasm64 Firefox][python-browser64-firefox]也已核对成功：精确两项完整解释器
与映射用例通过，零跳过/重试。至此该版四个双位宽浏览器组合各有独立运行证据；
它们均不覆盖后续资源清理、耗尽、超时/终止或可交付示例的新增断言。

旧版 Firefox 成功结束后才启动固定 `95ad6e5` 的 wasm64 Firefox 复验，用于运行
最新完整语料及示例。不取消或重复启动其它正在运行的检查，也不预告新版结果。

固定 `47cc982` 的 [wasm32 完整检查][python32-resource-cleanup]现已成功，实际
Linux 日志核对了 32 位 ABI、布局、搬移归档、PATH 异常，以及连续 64 次启动
失败后的父进程 fd、FD_CLOEXEC 和无残留子进程断言，最后输出 `::vm-test::pass`。
这首次提供该连续失败清理语料的 Wasm 运行证据，不覆盖后续 fd 耗尽、超时/终止
或发布示例。旧任务自然成功结束后才启动固定 `7b8b4ec` 的 wasm32 完整复验，
以运行全部最新语料并验收多输出采集；不替换其它仍在运行的浏览器检查。

[python32-resource-cleanup]: https://github.com/HighCWu/distro/actions/runs/39078913478

## 超过实际管道容量的双向二进制 I/O

`24e7076` 扩展同一进程生命周期脚本：父进程通过 communicate 输入超过 512 KiB
的完整字节语料，子进程先分别写出超过 512 KiB 的 stdout 和 stderr，再开始读取
stdin，最后输出反转输入及实际字节数。父进程须并行处理管道，否则先写完输入
再读取输出的实现会卡住。三条流都要求精确字节一致，正常退出后必须已回收。

测试请求 `pipesize=4096`，再以 F_GETPIPE_SZ 核对每条实际容量小于对应语料，
不根据宿主默认值或 Linux 页大小猜测已经产生背压。不跳过管道容量接口失败。
communicate 最多等待 20 秒；失败后终止/回收并关闭全部流。原生外层 watchdog
留出清理时间，这些期限不是吞吐率承诺或浏览器性能指标。

原生反例故意截掉一个输入字节，必须被完整输出断言拒绝。相关整组 60 项检查
通过，浏览器完整用例新增强制阶段及缺失阶段反例；仍保留已有超时恢复、信号
终止和启动失败语料。最新 wasm64 完整解释器公开复验已触发，尚无该语料的
实际 Wasm 或浏览器结论；正在运行的旧版检查不包含这项后续压力场景。
本项不证明任意数量并发子进程、无限流量、取消期间的全部清理或内存耗尽行为。

## 新版浏览器失败与诊断恢复

固定 `8a189fe` 的 [wasm64 Chromium 资源复验][python64-cleanup-failure]和固定
`fa9c5d0` 的 [wasm32 Firefox 生命周期复验][python32-lifecycle]现已失败结束。
完整重型日志确认两者均实际进入页面：完整解释器用例报告失败，独立映射用例
仍通过，各为 1 失败、1 通过。这不是获取、格式或编译阶段失败，也不由旧版
`417d8d0` 的四路成功覆盖。尚不能确定失败发生在耗尽、生命周期还是其它断言。

原浏览器运行器只把失败标记转换为通用错误，虽已收集 Python 控制台，却未把
此前 traceback 带入异常。`92c92d5` 修复此诊断缺口：程序失败保留完整已收集
运行输出，包括跨 chunk 的失败标记之前的阶段和 traceback。外部关闭错误的
身份、首个失败优先级、watchdog 与关闭生命周期语义保持不变。

新增回归及相关整组 61 项本机检查通过。两项旧任务终态后才启动最新源码的
同组合重放，以取得具体失败证据；不放宽应用断言、不将失败改为跳过，也不
宣称底层运行问题已经修复。其它仍在运行的检查继续保留。

[python64-cleanup-failure]: https://github.com/HighCWu/distro/actions/runs/39079103562

## 多输出安装布局修复

固定 `7b8b4ec` 的 wasm32 完整解释器任务 `39080192723` 与固定 `6c8cffc` 的
wasm32 材料任务 `39080394738` 均已失败结束。日志确认格式门禁通过，但 Python
安装目录变为 `$out/nix/store/.../bin`，随后 FHS 安装断言失败；尚未运行应用，
也未开始材料采集。这与前述实际进入浏览器后的运行失败是两个独立问题。

`f2cad73` 为显式填充的 buildMaterials 输出关闭通用多输出目录改写和开发文件
搬移，保持 `--prefix=/usr` 与 DESTDIR 安装方式，并为缺少解释器/标准库增加
明确错误消息。宿主契约同时约束两项钩子开关、前缀、暂存路径与诊断，相关
整组 61 项检查和源码 pin、缓存契约检查通过；这不替代实际 Nix 安装验证。

修复推送后复验已结束的两项 wasm32 检查，仍在运行的 wasm64 和浏览器任务
不取消、不重启。固定 `95ad6e5` 的 wasm64 Firefox 任务 `39079632810` 也已确认
完整解释器运行失败、独立映射检查通过；它早于诊断恢复，具体 traceback 仍缺失。
不以本次安装修复宣称已经解决这些实际运行失败。

固定 `92c92d5` 的 wasm32 Firefox 诊断重放 `39080865891` 随后也失败在 Python
构建依赖，未进入页面；它仍不包含安装布局修复。该任务终态后，以包含 `f2cad73`
修复的 `050ff03` 再次重放同组合。新版同时把宿主示例打包改为同目录暂存后原子
替换，六项打包回归和整组 61 项宿主检查通过；不改变目标进程或 mmap 的运行语义。
仍在运行的其它检查不重启，浏览器根因继续等待实际运行诊断。

## 完整无 fork 分支原生重放与设备初始化

`d145132` 增加 `python[-wasm64]-check-forkless-host`：从同一固定 CPython 源码
复制实际补丁涉及的文件，应用完整 process-posix-spawn 补丁，再用构建平台
Python 3.13 强制禁止导入 _posixsubprocess。它执行 PATH 错误、连续启动失败清理、
超时/信号恢复、双向管道和泄漏/字节错误反向控制，外层有 90 秒期限。不编译内核、
LLVM 或目标解释器；这是原生 POSIX 重放，不是 musl 或 Wasm 验收。glibc 不需要
musl 的内部错误管道，因此不把原生重放用于证明该管道的 fd 耗尽语义。

本机以 CPython 3.13.3 执行从 v3.13.14 取得并应用对应补丁的 subprocess 模块，
上述实际路径和反向控制通过；完整 Nix 检查仍待公开 CI。一次本机整组检查在示例
打包的 20 秒外层期限超时，未改期限或断言，重跑后 62 项通过。

固定 `f2cad73` 的 [wasm32 完整解释器][python32-device-failure]现已实际进入 Linux，
核对了 ABI、安装布局、两种搬移归档及连续失败清理，然后在 fd 耗尽测试打开
`/dev/null` 时报告 ENOENT。引导层在 switch_root 前卸载自己的 /dev，而该检查
PID 1 此前只挂载 proc，未挂载运行设备文件系统。因此不能把这次失败当成
posix_spawn 的 EMFILE 清理缺陷，也不能用原生测试通过覆盖它。

修正检查 PID 1，在解释器运行前挂载 devtmpfs、devpts，创建 fd 链接前挂载 proc，
并明确要求 /dev/null 为字符设备。仍保留原 fd 耗尽和生命周期全部断言；新增启动
顺序契约后整组 63 项宿主检查通过，ShellCheck 和简化模式 shfmt 检查通过。
本次仅修复安装测试入口，不更改产品 PID 1、内核或 libc，也不预告目标复验成功。

[python32-device-failure]: https://github.com/HighCWu/distro/actions/runs/39081246749

## 独立原生 CI 与浏览器诊断证据

固定 `050ff03` 的 wasm32 Firefox 重放 `39081528761` 已实际进入页面，恢复的
Runtime console 包含完整 traceback，确认同样在打开 /dev/null 时得到 ENOENT。
它不包含 `6af4307` 的设备初始化修复。固定 `92c92d5` 的 wasm64 Chromium 重放
`39080862032` 则失败于 Python 构建依赖，未进入页面；不能把二者混记为同一运行结果。

`223938a` 为现有 ci.yml 增加独立 `python-forkless-host` 布尔模式，只运行前述
原生补丁重放检查，并跳过默认计划及目标构建矩阵。该 job 只有 contents:read，
没有发布凭据或 LLVM/内核大缓存，外层 15 分钟期限；与 heavy-check 同时指定时
明确失败。普通 push/PR 和既有重型定向模式保持不变。

可以显式触发：

```sh
gh workflow run ci.yml --repo HighCWu/distro --ref codex/mmap-initialized-backing \
  -f python-forkless-host=true
```

相关本机回归增至 64 项并通过，工作流 YAML、actionlint 和十项缓存契约检查通过。
独立模式的实际公开执行仍需确认，不以配置检查代替运行，也不将原生成功泛化为
Wasm 信号、设备或 musl 内部错误管道语义。已结束的浏览器组合可在包含安装及设备
初始化修复后复验，其它仍运行的任务继续保留。

固定 `223938a` 的[独立原生检查][python-native-replay-success]现已成功。实际日志
确认五个源码文件应用补丁，PATH/连续失败清理、超时恢复、双向管道及三类反向
控制均执行，并输出最终重放完成行。任务 API 确认仅原生 job 成功，计划、默认
构建、重型矩阵、站点部署及发布均跳过；不是目标检查被跳过后误计为 Wasm 成功。
同版 wasm32 Firefox 与 wasm64 Chromium 修正版重放已分别启动，尚待运行结果。

[python-native-replay-success]: https://github.com/HighCWu/distro/actions/runs/39082515524

## 安装系统完整运行恢复与 PTY 覆盖

固定 `6af4307` 的 [wasm32 完整解释器][python32-device-repaired]现已成功。实际
Linux 日志确认 ABI/安装布局、搬移归档及发布示例、连续启动失败清理、fd 耗尽、
超时恢复/信号终止和大管道背压均执行，最后输出 pass。这提供设备初始化修复后
的完整语料证据，不等于 wasm64、浏览器或后续 PTY 扩展已经通过。

`299cd6e` 新增独立 pty-test.py，经完整解释器安装并在最终 pass 前运行；浏览器也强制要求
其完成阶段。它分配自己的 master/slave，检查字符设备、slave 的 /dev/pts 路径、
双端 CLOEXEC、关闭 echo 的 canonical 输入、raw 模式双向完整字节及两方向窗口
大小 ioctl。非阻塞 select 传输有五秒期限，退出时关闭两端；不借用测试进程的
控制终端，不调用 fork，也不启动交互 shell。

原生反向控制故意损坏一个 raw 输入字节，必须被逐字节断言拒绝；宿主实际运行及
整组 65 项检查通过，格式、ShellCheck、shfmt、源码 pin 和缓存契约检查通过。
该项是对 Python/termios 与实际 devpts 的新增验收，目标运行尚待公开 CI；不承诺
pty.fork、控制终端会话、前后台作业控制、任意 termios 选项或交互 shell 已经完备。
此前仍在运行的浏览器任务不包含本项，不取消或重启。

[python32-device-repaired]: https://github.com/HighCWu/distro/actions/runs/39082233830

## exec 后建立控制终端的会话

`658223a` 扩展同一 PTY 语料，通过 Popen 传递 slave fd，exec 后由程序自身调用
login_tty 创建会话、取得控制终端并绑定三个标准流。没有 fork、preexec_fn 或新的
内核接口；既有 subprocess start_new_session 属性测试仍保留，不以此路径替换它。
父进程独立核对返回的 PID、SID、进程组、前台终端组全部等于该子进程 PID，并
要求 /dev/tty 和三个标准流确实是终端。读取准备记录后才发送全字节输入，核对
逆序输出，完成握手后再允许子进程退出，确认正常状态及单次回收。

准备及传输均有期限，失败路径终止/回收并关闭句柄；login_tty 后的错误会写往
PTY 而非 Popen 原 stderr 管道，因此清理时保留最多 64 KiB 未读终端诊断。基本
PTY 和会话都注入一个字节损坏作为反向控制。该会话同时加入实际补丁的无 fork
原生重放，确保不仅依赖宿主默认 fork 路径的 Popen 成功。

本机完整补丁原生重放和相关 65 项检查通过；新版独立原生公开检查已触发。
仍运行的 `299cd6e` 双位宽完整解释器和 `223938a` 浏览器任务不包含这一扩展，
不取消或重启。目标会话执行、完整 shell 作业控制、终端信号和挂断语义仍须
分别验证，不因基础 PTY 或原生重放成功而泛化。

固定 `223938a` 的 [wasm32 Firefox 修正版][python32-firefox-devices-success]现已
成功。重取同一任务日志后核对完整解释器与私有匿名映射精确两项通过，报告门禁
确认零跳过、零重试；完整解释器断言包含设备初始化后的耗尽、生命周期和大管道
语料。一次日志下载超时不是任务失败，没有因此重跑该任务。此证据不覆盖后续
PTY 扩展；旧任务成功结束后才触发固定 `658223a` 的同组合会话复验，其它运行
中的目标任务继续保留。

[python32-firefox-devices-success]: https://github.com/HighCWu/distro/actions/runs/39082520107
