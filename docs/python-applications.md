<!-- SPDX-License-Identifier: MIT -->

# 构建和交付纯 Python 应用

当前平台已在两个位宽构建并运行完整 CPython 3.13.14，以及压缩库、SQLite、
curses、TLS、subprocess 和 spawn 多进程的指定语料。浏览器运行在 Linux 内，
不是 WASI Python，也不是 JavaScript 中模拟 Python 的独立兼容层。
具体版本证据及限制见 [Python 运行记录](python-mmap.md)。

## 一个可搬移的示例

从项目根目录使用普通宿主 Python 构建，无需 LLVM、内核或 Nix 构建：

```sh
python3 -B sources/distro/distro/python/build-example.py ./application.pyz
printf 'abc' | python3 ./application.pyz
```

输出 UTF-8 资源行和 `cba`。示例从归档内读取包元数据与资源，并反转二进制 stdin，
不依赖生成目录、环境中的 PYTHONPATH、pip 或第三方包下载。归档包含入口、包源码、
资源、`.dist-info/METADATA` 和 MIT 许可证；不包含 Python 解释器、内核或工具链。
`.pyz` 是可读取源码的 ZIP 应用，不是原生扩展，也不是加密或源码保护方案。

同一纯 Python 归档可交给匹配平台的 wasm32 或 wasm64 解释器；解释器、libc 和
系统镜像本身仍必须匹配位宽与运行 ABI。不能把 `.pyz` 当作可直接交给浏览器
WebAssembly API 的二进制，也不能把它上传到只接受 Wasm 程序的示例控件。

在已安装本项目 Python 的 Linux/Wasm 根文件系统中放置归档，再执行：

```sh
python3 /path/to/application.pyz
```

下述可选独立示例已接入 `.pyz` 上传配方，首次真实浏览器验收仍待 CI；它不是
面向任意依赖的一键部署服务。自行集成根盘时还需正确提供解释器、
标准库、运行依赖、许可材料和可写临时目录，不能只复制 `/usr/bin/python3`。

## 可复用 wasm64 Python 系统根盘

distro `9572fa0` 新增 `guest-agent.nativeWasm64.rootfsPythonExt4`：256 MiB ext4
根盘配方，包含匹配位宽的 BusyBox、Python、ncurses、OpenSSL 和 CA 证书。复用
原生 agent 启动盘及公开 SDK，不更改默认 wasm32 镜像，也不把解释器测试脚本、
示例应用或构建材料混入系统根盘。256 MiB 是磁盘镜像大小，不是线性内存上限。

重型构建只在公开 GitHub Actions 运行；以下是供 CI 使用的明确入口：

```sh
nix build './sources/distro#legacyPackages.x86_64-linux.guest-agent.nativeWasm64.rootfsPythonExt4'
gh workflow run ci.yml --repo HighCWu/distro --ref codex/mmap-initialized-backing \
  -f heavy-check=guest-agent-check-python-root-wasm64
```

新检查通过公开 API 上传实际生成的 `application.pyz`，按 PATH 启动 `python3`，
核对 64 位指针、FHS 标准库、压缩/SQLite/curses 导入及 CA 加载；并严格比较
65553 字节全字节输入的逆序输出和 UTF-8 资源前缀、空 stderr 与正常退出。
同步根盘后关闭整个实例，再以保留的磁盘字节启动另一实例，复核应用归档及再次
执行。不沿用进程内存或测试 initramfs；两次均要求关键许可文本存在、测试文件缺席。
这不是断电恢复、浏览器持久化存储、交互式 PTY API 或任意应用兼容性的证明。

新增配方与接线的两项宿主检查已通过，连同当时既有相关检查共 67 项通过。
固定 `9572fa0` 的 [Node 根盘验收](https://github.com/HighCWu/distro/actions/runs/39084313946)
现已成功，实际日志确认两次独立实例的 write/read 阶段及外层检查共三项通过，
零失败、取消或跳过；包含上述字节、ABI、依赖、许可及无测试文件断言。该检查
在运行前使用 CI 构建的 kernel 声明通过完整类型门禁，不受本地旧 `dist` 的三处
`FSDirectoryEntry.type` 错误影响。此结果不覆盖随后新增的浏览器上传控件或源码导出。

这是可复用集成配方，不是已发布、合规材料完整的二进制发行版。Python 中 GNU
Readline 的实际 GPL 义务保持不变；现有 notices 和选定构建材料不能替代完整对应
源码。发布检查尚须补齐，不能将整个根盘称为 MIT。

## 可选的独立浏览器 Python 示例

distro `f8f5d05` 新增 `wasm64-python-example`，复用原独立示例、公开 SDK、原生
启动盘及上述 Python 根盘，不更改 `wasm64-example` 的最小根盘默认值。以下命令
中的重型构建由公开 CI 执行，之后可整体搬移产物到普通目录运行开发服务器：

```sh
nix build './sources/distro#wasm64-python-example' --out-link result-python-example
node result-python-example/server.mjs
```

启动 Linux 后选择 **Program type → Python .pyz application**，选择本节开头
生成的归档，再执行 Import and run。文件只进入该次 Linux 的临时根盘，不上传
HTTP 服务器；按 `/usr/bin/python3 -I /root/application.pyz` 加字面 JSON 参数执行。
没有 shell 展开、扩展名猜测、JavaScript 解包或自动依赖安装。默认最小示例禁用
Python 选项，页面明确显示所选根盘配置。

导入上限 16 MiB，目前只接受以 ZIP local-file header 开头的 `.pyz`，不接受
前置 shebang。格式头并非归档内容、解压大小、依赖或资源配额校验。Python 隔离模式
忽略 PYTHONPATH 等环境配置和当前目录导入，不是安全沙箱。只运行可信应用，
不能据此推断缺失的系统功能或原生扩展已可用。

复用文本/文件 stdin、双输出流并发消费、取消、Stop 和文件下载；页面输出仍是
最多 65536 字符的 UTF-8 预览，二进制输出须由应用写入文件后下载。停止或重载会
丢弃整个临时盘，256 MiB 镜像不是 OPFS 持久化能力，也不是线性内存上限。

相关示例/根盘接线/打包共 54 项宿主检查通过，另有既有 Python 等 65 项通过，
前端 esbuild 打包成功。新浏览器用例从真实控件验证实际示例归档、文本和全字节
文件输入、损坏归档、字面参数、退出码 37、stderr、取消后恢复及运行中 Stop/重启。
辅助控制归档仅放入检查套件，不安装进交付根盘。Chromium/Firefox 的精确单用例
报告门禁拒绝跳过、重试或额外场景；首次
[Chromium](https://github.com/HighCWu/distro/actions/runs/39084743974) 和
[Firefox](https://github.com/HighCWu/distro/actions/runs/39084746481) 均失败在辅助归档
构建阶段：Nix 源文件时间早于 1980，`zipfile.write()` 拒绝写入；尚未执行浏览器，
不是 Linux/Python 运行失败。`2d7aa94` 固定 ZIP 时间、Unix 权限和压缩元数据，
新增回归复现旧错误，并验证实际配方生成的归档内容、执行结果及两次生成一致性；
相关宿主检查增至 55 项，全部通过。修正后的
[Chromium](https://github.com/HighCWu/distro/actions/runs/39086122510) 和
[Firefox](https://github.com/HighCWu/distro/actions/runs/39086128342) 已提交，仍待真实结果，
不降低原浏览器断言或用宿主结果替代。

解释器中 Readline 及系统其它组件的实际分发义务不因增加浏览器入口而改变；当前
尚未完成整个系统的对应源码交付或长期版本发布。详细控制和限制也见
[示例 README](../sources/distro/apps/wasm64-example/README.md)。

## 公开 CI 产物与重建

主仓库轻量 CI 成功执行示例打包步骤后，上传保留 7 天的
`python-application-example-COMMIT`，包含：

- `application.pyz`：压缩应用，不含平台二进制。
- `source/example/` 与 `source/build-example.py`：实际打包输入及构建器。
- `LICENSE`：该示例的 MIT 许可证。
- `source-pins.json`：本次主仓库固定的组件 revision，不是完整 SBOM 或 GPL 对应源码包。

解包后可用 `python3 source/build-example.py rebuilt.pyz` 重建。成员顺序、时间戳与
权限元数据固定，缓存和无关本地文件不入包；不同 Python/zlib 版本的压缩字节不作
跨版本一致保证。首次 CI 上传及新版 Linux/Wasm 运行仍须分别确认，不能仅凭
本机打包成功声称公开产物或目标运行已通过。

固定主仓库 `0147f8b` 的[首次公开构建][example-ci]现已成功，打包和上传步骤均
通过。已下载实际 artifact（ID `12117989069`，5621 字节、检查时未过期），逐项
确认归档内六个应用成员与附带源码一致、固定 ZIP 元数据、LICENSE 字节，以及
清单中的 builder commit 和 distro `95ad6e5` pin。此证据不包含新版 Wasm 运行，
7 天保留期也不是长期应用发布渠道。

[example-ci]: https://github.com/HighCWu/linux-wasm-builder/actions/runs/39079565447

distro 的 `python.applicationExample` 和 `python-wasm64.applicationExample` 暴露同一
宿主构建配方；公开 Actions 可使用如下 installable，仅生成示例而不编译解释器：

```sh
nix build './sources/distro#python-wasm64.applicationExample'
```

完整解释器检查安装并搬移这份实际生成的归档，验证二进制管道、包元数据、资源和
许可证，而不是另写一份看似相同的测试应用。原有动态生成归档测试也保留。
新增本机回归核对固定元数据、源码删除后运行，并要求缺少包元数据的归档失败；
这些宿主证据不替代目标或浏览器运行。

打包器在目标的同一目录暂存完整归档，关闭 ZIP 后才以原子替换发布；缺失输入或
替换失败不会截断已有产物，失败时清理暂存文件。六项宿主回归包含无旧产物时的
输入失败、保留旧归档、注入替换失败及成功替换后的完整性和权限检查。此机制不
提供断电持久性保证、并发发布顺序控制或签名；不同构建同时成功时最后一次替换
生效。归档内部的确定性元数据和显式成员列表保持不变。

## 功能与许可边界

当前没有 pip/ensurepip、ctypes、动态原生扩展加载或 POSIX 共享内存支持承诺。
默认文件 mmap、默认 MAP_SHARED 请求和 mmap.flush 不可用；私有匿名映射须显式
选择正确参数。标准 fork 不可用，支持范围内的进程启动使用 posix_spawn；
依赖任意 fork、preexec_fn、用户/组切换或其它未支持选项的软件不能因此视为兼容。

示例代码采用 MIT，不要求开发者自己的应用统一采用 MIT。应用可以按自身代码和
依赖条款选择开源、闭源或商业发行，单纯运行在 Linux 上不会导致应用继承内核 GPL。
本项目当前 Python 静态链接 GNU Readline，分发该解释器必须遵守其实际 GPL 等义务，
不能把整个解释器重标为 MIT，也不能省略对应源码和许可材料要求。
这与独立脚本或用户程序的许可判断不同；具体产品应按实际分发、修改和链接关系审核。

Python 另提供独立 `buildMaterials` 配置/补丁输出，默认不安装进根盘。`84d5bd9`
进一步增加双位宽 `sourceBundle` 选定源码归档配方，首次真实 CI 验收仍待结果。
内容和明确排除项见[发行政策](licensing.md#python-与七项依赖的选定源码导出)；
这些材料仍不是完整对应源码交付或已完成合规的保证。
