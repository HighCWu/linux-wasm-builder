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

当前尚无面向任意 `.pyz` 的一键浏览器上传部署流程。本次提供可复用应用产物，
不把内部浏览器检查页面称为通用应用启动器。自行集成根盘时还需正确提供解释器、
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

新增配方与接线的两项宿主检查已通过，连同既有相关检查共 67 项通过；**新根盘的
公开构建和实际运行仍待 [CI 验收](https://github.com/HighCWu/distro/actions/runs/39084313946)**。本地完整 TypeScript 检查受已有 kernel `dist`
声明落后于源码影响，报告三处既有 `FSDirectoryEntry.type` 错误；新目标检查仍保留
完整类型门禁，并使用 CI 构建的 kernel 声明。不据本机结果宣称目标通过。

这是可复用集成配方，不是已发布、合规材料完整的二进制发行版。Python 中 GNU
Readline 的实际 GPL 义务保持不变；现有 notices 和选定构建材料不能替代完整对应
源码。发布检查尚须补齐，不能将整个根盘称为 MIT。

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

Python 后续另提供独立 `buildMaterials` 配置/补丁输出，默认不安装进根盘；其
内容和明确排除项见[发行政策](licensing.md)。它不是依赖源码包或已完成合规的保证。
