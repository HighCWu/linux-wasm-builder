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
musl 修复和安装布局门禁；均已通过计划解析并进入构建，尚无目标运行结论。
当时仍在运行的 `0d71aef` wasm32 映射复验没有被取消，其最终结果见上文。

| 修正后目标检查 | 公开任务 |
| --- | --- |
| wasm64 完整解释器 | [构建与运行][python64-full-recheck] |
| wasm64 私有匿名映射 | [构建与运行][python64-mmap-recheck] |
| wasm32 完整解释器 | [回归检查][python32-full-recheck] |

[python64-full-recheck]: https://github.com/HighCWu/distro/actions/runs/39076153816
[python64-mmap-recheck]: https://github.com/HighCWu/distro/actions/runs/39076156858
[python32-full-recheck]: https://github.com/HighCWu/distro/actions/runs/39076159576

`3356d3f` 补齐映射测试根盘的证书依赖，不移除 OpenSSL 或放宽安装失败检查。
新增回归逐一检查两个 Python 安装集合包含所需包，并核对 OpenSSL 实际依赖声明。
Python 七项本机检查全部通过，格式与源码 pin 检查通过；这些检查不运行目标 Python。
旧 wasm32 映射任务自然失败后才启动[该版复验][certificate-recheck]；仍在运行的其他检查保持不变。

[certificate-recheck]: https://github.com/HighCWu/distro/actions/runs/39076355206

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
