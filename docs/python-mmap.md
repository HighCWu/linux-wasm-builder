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
派生解析，进入隔离构建；尚不作为真实解释器运行成功的证据。此前 `d4fafc8`
的 wasm32 映射检查继续自行运行，没有为新检查取消或重启旧任务。

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
