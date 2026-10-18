<!-- SPDX-License-Identifier: MIT -->

# 许可证与发行政策

## 政策目标

项目支持开源社区、个人开发者、研究和商业使用。架构和发行流程应让第三方像在普通
Linux 用户态上一样，根据自身代码及所用依赖的许可证选择开发与发行方式，包括：

- 使用工具链编译、运行和发布开源或闭源程序；
- 在浏览器或其他 Wasm runtime 中运行这些程序；
- 仅仅使用 Linux syscall/UAPI 不会使用户程序自动继承内核的 GPL 许可证；
- 修改并重新发行宽松许可的宿主、runtime、musl 和工具；
- 在遵守 GPL 的情况下修改并发行 `linux.wasm`。

许可证结论取决于具体组合和发行方式。本文件是工程政策，不替代法律意见。

## 组件许可证

| 组件 | 目标许可证 | 使用和发行边界 |
|---|---|---|
| 本集成仓库自有内容 | MIT | 可被开源或闭源项目复用 |
| 独立 runtime、host SDK及内存兼容支持 | MIT | 可用于不同许可证的程序或宿主 |
| musl修改 | MIT | 用户程序可静态或动态链接 |
| LLVM/Clang/LLD修改 | Apache-2.0 WITH LLVM-exception | 编译输出不因工具链本身被要求采用同一许可证 |
| Meson及其源码补丁 | Apache-2.0 | 保留上游声明；使用构建工具本身不要求应用采用同一许可证 |
| Linux内核修改 | GPL-2.0-only，按文件SPDX | 发行修改后的内核必须履行GPL义务 |
| Linux UAPI headers | GPL-2.0 WITH Linux-syscall-note等 | 正常syscall用户程序不因此成为GPL派生作品 |
| distro/rootfs内容 | 混合许可证 | 必须逐包生成清单并履行各自义务 |

“项目尽量 MIT”意味着把可独立实现的新代码放到 MIT 组件；它不意味着把 Linux、
LLVM 或第三方代码重新标成 MIT。

SDK 的 Meson 归档组修复位于 `sources/distro/distro/sdk/meson-wasm-archive-groups.patch`，
修改上游 `mesonbuild/compilers/mixins/clike.py`，因此保留 Apache-2.0，而不是改标 MIT。
独立的 Nix 集成和行为回归测试采用 MIT。Nix override 继承上游 Meson 包的元数据；
发行含修正版 Meson 的 SDK 时仍应随包保留上游许可证、版权及适用的 NOTICE，标明修改。
这不改变所编译应用自身或其链接依赖的许可边界，也不代表完整 SDK 许可清单已经生成。

SDK 另有独立的选定构建材料归档，保存实际安装入口、配置、原始许可文本、选定
配方和 flake 文件，并通过独立输入逐成员核验。材料收集／核验工具采用 MIT；
被收集的上游内容不被重新许可。这不包含完整上游源码、构建机依赖或全部 Nixpkgs
变换，不是 SBOM、完整对应源码或发行许可批准，也不改变用户程序的链接许可边界。
命令、内容与待验收状态见 [SDK 构建材料](sdk-runtime.md#选定-sdk-构建材料归档)。

另提供 SDK 的选定完整源码输入归档，保存实际选择的 Linux、musl、LLVM 和 Meson
源码树，并与原 SDK 材料共同逐成员核验；相同 LLVM 源码根去重。这是原始输入，
不是任意 post-patch 构建目录快照，仍缺完整依赖及发行审计，不能当作全部对应源码
义务已履行的证明。原始组件许可证保持不变，收集工具采用 MIT。命令与范围见
[SDK 源码输入](sdk-runtime.md#选定-sdk-完整源码输入)。

SDK 源码 CI 还接入对应提交的完整 distro 配方归档，逐项对照 Git 对象校验，补齐
选定源码包之外的配方 checkout 获取路径。它不含完整 Nixpkgs／构建机依赖，也不是
离线构建环境、来源签名或长期源码发布；需实际验收后再计入发行材料。

SDK 的 SQLite 检查复用固定的 SQLite 3.51.0 上游源码，不修改或重新许可 SQLite。
SQLite 核心由上游声明为 public domain，项目自有的构建集成及运行用例采用 MIT。
这不是将其他发行版软件包或它们的依赖统一改为 MIT；发行时仍需逐项记录来源和许可。

## 用户程序的许可证边界

预期结构与普通 Linux 用户态相同：程序通过 syscall/UAPI 使用内核，而不链接内核
实现。开发者可以选择与自身代码及依赖相容的许可证，并按开源、闭源、非商业或商业
方式发布程序。

```text
user program.wasm
  ├─ links MIT musl/runtime
  └─ uses Linux syscall UAPI + versioned Wasm psABI
                    │
                    ▼
              GPL linux.wasm
```

为了保持这一边界，用户程序不得：

- 包含 Linux kernel object code；
- 链接 Linux 内部函数；
- 把内核私有结构布局作为应用 ABI；
- 将 GPL 库误当作仅因生成 `.wasm` 就不再附带原有许可证义务；
- 依赖把许可证不兼容的紧耦合模块拆成不同文件来规避许可证。

用户态JIT或应用为被模拟程序自行实现的地址翻译，应保持在其适用许可证边界内。
Linux端只通过UAPI/执行ABI与程序交互，不把内核实现链接进用户程序。

## Linux发行义务

向浏览器用户发送 `linux.wasm` 通常是在发行对象代码，而不是单纯服务器内部使用。
每个发行版本都应同时准备：

- 生成该二进制的精确 Linux 源码和本项目补丁；
- `.config`；
- 构建和链接脚本；
- 必要的生成工具说明；
- GPL许可证文本和版权声明；
- 对应版本可长期访问的 source bundle或合规书面要约方案。

仅给出一个会继续变化的 GitHub分支链接，不应作为唯一合规机制。

内核构建现新增 `linux-build/`：在 `make vmlinux.wasm` 之后保存实际最终 `.config`
为 `kernel.config`，复制该源码的原始 COPYING / 完整 LICENSES，记录所选源码和
LLVM 工具链 store 身份、位宽及 debug/test profile，并附构建配方、材料脚本和说明。
这些 store 身份使用拆分 hash，避免仅因身份字符串保留完整构建输入。
`SHA256SUMS` 同时覆盖内核字节和材料；从产物根目录执行
`sha256sum --check linux-build/SHA256SUMS`。npm 内核包将携带此目录，打包解包后
再次核验，不能只验证打包前的源码树。原 npm Linux 许可表达式保留，syscall
exception 依据 Linux 官方 COPYING，不把内核实现改标为 MIT。
5 项宿主测试验证实际材料复制脚本、所需文件缺失/为空或内核不匹配时拒绝，以及
npm 归档往返和篡改检测。新增独立 `kernel-check-build-materials` /
`kernel-wasm64-check-build-materials` 会重新解包实际 npm 产物，逐字节比较所选
Linux 输出中的内核和整套材料，同时核对宿主 MIT 原文及包的名称、版本和许可
声明。宿主故障注入还验证替换配置并重算校验和、改写 MIT 文本或将包声明改成
仅 MIT 均会失败；不能只因某份自带校验和通过就认定来源匹配。
随后 distro `2a21e3a` 的
[wasm64 npm 材料检查](https://github.com/HighCWu/distro/actions/runs/38926460986)
已成功：实际目标构建/检查与整个工作流均通过。该检查强制依赖 Linux 材料/profile
检查，并重新解包真实 npm 包验证字节与声明；它不包含后续完整源码归档功能。
首轮内核材料检查
[38925328081](https://github.com/HighCWu/distro/actions/runs/38925328081)
失败于新 shell 脚本的 treefmt/shfmt 格式门禁，未进入内核编译，不能作为内核功能
失败或材料包通过的证据。已按仓库规则修正格式。npm 定向检查还强制依赖对应的
Linux 材料检查，让内核 profile、原始材料和最终 npm 包在同一构建依赖图中验证，
共享内核构建而不重复安排同一内核的独立作业。
这些只是构建与许可材料，不包含完整 Linux 源码、全套依赖或所有补丁来源，不代表
完整 GPL 对应源码包或已履行全部发行义务；公开源码交付仍需继续建设。

另提供独立 `kernel.sourceBundle` / `kernel-wasm64.sourceBundle`：把选中的完整
Linux 源码输入放入 `linux/`，同一内核的实际配置、原始许可证和构建材料放入
`build-materials/`，流式生成 `linux-source.tar.gz`，不额外复制源码或生成未压缩
tar。源码链接目标保留，归档排序、时间、所有者和 gzip 头固定；宿主测试验证相同
输入生成相同压缩字节、隐藏文件和链接保留、符号链接源码根解析及缺失配置拒绝。
可用 `nix build ./sources/distro#kernel-wasm64.sourceBundle` 构建，外层 SHA256SUMS
校验源码归档与说明，内层材料校验和仍描述对应 npm 二进制，不把内核字节重复打入
源码包。产物设置 Nix 零引用约束，不因生成归档而让运行时继续引用整棵源码。

`kernel[-wasm64]-check-source-bundle` 会执行原内核材料/profile 检查，核验归档
校验和及所选源码 COPYING、实际配置的字节。成功后 CI 上传保留 3 天的源码验证
artifact，关闭二次压缩；它不是长期源码托管。distro `61d552a` 的
[wasm64 源码归档检查](https://github.com/HighCWu/distro/actions/runs/38928012549)
已成功：实际 Nix 归档检查、收集和 artifact 上传均通过，整个工作流成功。
API 确认存在对应提交的约 250 MiB 源码 artifact；仍只保留 3 天，不替代正式
发行所需的长期源码获取渠道，也不代表 wasm32 或完整发行的对应源码已获验证。
源码包不包含完整 distro/LLVM/Nix 依赖和可独立离线重建环境；显式 `patches` 非空时
拒绝导出，避免静默遗漏补丁。其他自定义 hook/override 仍需发行者审查，这不是任意
修改后的最终构建工作树快照，也不代表完整发行的 GPL 义务已经满足。

rootfs中的 BusyBox及其他 copyleft组件也必须单独处理，不能因为它们位于磁盘镜像
中而忽略。

### BusyBox 构建材料与选定源码

distro `aa33c39` 为双位宽 BusyBox 增加独立 `buildMaterials` 输出，保存最终配置、
原始许可证、配方、ABI 检查器及源码/运行库/编译器/内核头文件的 Nix 输入身份；
默认仅安装 `out`，不把这些构建材料复制进根盘。`sourceBundle` 将实际选定的
BusyBox 源码与材料流式归档，并另给最终安装、strip 后的 `bin/busybox` 生成校验和。
配置缺失或材料校验失败时拒绝导出，显式补丁列表非空时也拒绝导出，避免静默遗漏。

源码及材料的宿主测试通过，涵盖重复归档字节一致、特殊目录名、源码链接/硬链接、
配置缺失和材料篡改；该结果不是目标 BusyBox 构建或 Nix 多输出打包已通过的证据。
`busybox[-wasm64]-check-source-bundle` 另核对实际安装字节、内存 ABI、配置和源码
许可证，成功后上传保留 3 天的验证 artifact。复现命令与排除项见源码 BusyBox README。

这仍不是完整对应源码交付：归档未含 musl/compiler-rt、编译器及全部 Nix 依赖源码，
也不是离线重建环境或 SBOM。正式发布还需匹配的 distro checkout/flake.lock、完整
依赖审计和长期源码获取渠道。导出器自有代码采用 MIT，BusyBox 继续遵循 GPL-2.0-only。

首批实际检查固定 `cb275c7`，三项均失败；已核对 wasm64 源码任务日志，失败在
格式门禁的 `package.nix` 和 shell 空白处理，未进入目标构建。`6585871` 修正脚本
格式，`0314774` 规范化 Nix 元数据并使后续格式门禁输出实际 diff，宿主归档回归
重新通过。针对新固定版本的双位宽归档与 wasm64 smoke 复验现均成功。
以下保留首批失败记录，不作为归档已通过的证据：

- [wasm64 源码归档](https://github.com/HighCWu/distro/actions/runs/38968663096)
- [wasm32 源码归档](https://github.com/HighCWu/distro/actions/runs/38968669994)
- [wasm64 安装 smoke](https://github.com/HighCWu/distro/actions/runs/38968677130)

修正后的[wasm32 源码归档检查](https://github.com/HighCWu/distro/actions/runs/38969210975)
固定 `0314774`，现已成功：实际目标检查、源码收集和 artifact 上传步骤均通过。
API 确认存在对应提交、未过期的 3,169,074 字节 artifact，仍只保留 3 天。
同版本的 [wasm64 源码归档](https://github.com/HighCWu/distro/actions/runs/38969203487)
也已成功，日志确认配置、源码包和最终二进制校验和通过，并确认共享 wasm64
`env.memory` 的 16 GiB 声明上限；API 确认对应未过期 artifact 为 3,169,075 字节。
[wasm64 安装 smoke](https://github.com/HighCWu/distro/actions/runs/38969217828)
同样成功，实际日志包含 `::vm-test::pass`。这些结果不代表完整发行依赖、长期源码
发布或发行合规已完成；临时 artifact 仍只保留 3 天。

### 原生 wasm64 SQLite 应用包

distro `8af0f0d` 的 `sqlite3-wasm64` 使用既有固定 SQLite 源码，保留上游
public-domain 声明（随包原始 `sqlite3.h`），并安装所链接 musl 和 compiler-rt
许可文本。APK 元数据明确组合 SQLite blessing、MIT 及 Apache-2.0 WITH LLVM-exception，
不把 MIT 构建脚本的声明当作 SQLite 或链接组件的重新许可。

独立 SQLite ext4 根盘仍包含 GPL-2.0-only BusyBox；镜像不是单一 MIT 作品，分发者
须继续分别履行各组件义务。此包不会将内核实现链接进 SQLite 或其他用户程序。
随包声明和定向检查不等于完整发行依赖清单、对应源码交付或法律合规认证。

## 洁净实现政策

参考其他软件 MMU实现时：

- 先记录来源、许可证和可参考范围；
- 只从文档、公开行为和兼容性测试提取需求；
- 若复用 MIT/BSD代码，保留所需版权和许可证；
- 不从专有实现复制代码；
- 不把 GPL实现复制进 MIT runtime或LLVM；
- 对算法重新实现时保留设计来源说明，避免错误声称完全原创。

## 自动化要求

SDK 现安装 `share/linux-wasm-sdk/licenses/`，并由 `wasm-linux-sdk-info` 的
`paths.licenseTexts` 字段提供位置。材料包括实际选中的 musl COPYRIGHT、Linux
COPYING/完整 LICENSES 目录，以及工具链和运行库对应 LLVM 子项目的 LICENSE.TXT，
另附 SDK 自有代码的 MIT 文本。原始文件不改写，SHA256SUMS 可在该目录核验。
`sources.json` 以 `hashParts` 和 `name` 记录源码 store 身份：先连接两个 hash 片段，
再附加连字符及名称即可还原 basename。不能直接保留裸 store hash，因为 Nix 同样
会把它扫描为引用。材料构建设置 `allowedReferences = []`，由 Nix 拒绝意外的运行
引用；SDK profile 检查还会对安装后的许可目录执行 SHA256SUMS 核验。
来源通过所选 sysroot/工具链传递，不硬编码成与 wasm64 或 override 无关的默认源码。

独立 `sdk-check-licenses` / `sdk-wasm64-check-licenses` 检查只构建许可材料，不要求
编译 LLVM/Linux；仍需获取固定源码。缺失或空的许可文件会失败。宿主故障注入测试
验证复制原文、缺失/空文件拒绝及校验和发现篡改。
[首轮固定源码 CI](https://github.com/HighCWu/distro/actions/runs/38916863482)已通过，
对应 distro `2aac5a0`；它不包含后来加入的拆分来源 hash、零引用约束及安装校验，
不能替代后续约束的验证。
[收紧后的材料 CI](https://github.com/HighCWu/distro/actions/runs/38917758703)
也已通过（distro `13596d0`），包含拆分来源 hash 和 Nix 零引用约束；这证明材料包
本身未引用完整源码树。随后 distro `88a5ce1` 的 SDK C++ 消费
[wasm32](https://github.com/HighCWu/distro/actions/runs/38918153433) 和
[wasm64](https://github.com/HighCWu/distro/actions/runs/38918154357) CI 均通过，
其强制 profile 依赖包含实际 SDK 安装视图中的 SHA256SUMS 校验。这是所选材料
完整性的验证，不证明未纳入材料的依赖许可清单完整。

后续材料包还收录实际 SDK 所选 Meson 源码的原始 `COPYING`，存在时同时收录
`NOTICE`，并附带本项目的 archive-group 补丁及修改说明。来源使用 `meson.src`，
而不是另行选择一个可能不同版本的上游副本。宿主测试执行真实复制配方，覆盖 Meson
许可证缺失/为空时失败、可选 NOTICE 原文保留，以及补丁/说明和校验和完整性；
对应 distro `94bd9c6` 的
[固定源码 Nix 检查](https://github.com/HighCWu/distro/actions/runs/38921710474)
已通过：新增材料构建、校验和与 `allowedReferences = []` 约束均由该检查执行。
它只验证材料包，不证明后来 SDK 安装视图或完整依赖许可清单已通过审计。

这是部分许可材料包，不是完整 SBOM、依赖许可清单、合规结论或 GPL 对应源码包。
宿主动态依赖、Meson 的 Python 依赖与继承的 Nixpkgs 补丁、附加库及各源文件自身
的声明仍须单独审计，不能据此宣布 SDK
已经完成发行合规。仅记录源码 store 身份也不替代提供可获得的对应源码。

发行管线最终应自动生成：

- SPDX SBOM；
- 每个二进制和镜像的许可证清单；
- NOTICE/attribution；
- Linux和其他 copyleft组件的对应源码包；
- 编译器/runtime/kernel ABI版本清单；
- 用户程序样例的链接组成记录，确认实际组成与声明的许可证边界一致。

## Python 配置与补丁材料

distro `f389394` 为双位宽 Python 增加独立 `buildMaterials` 输出，保存该次构建
实际的 `pyconfig.h`、原始 Makefile、config.log、生成的 Modules 配置、CPython
许可证、配方和所有配置补丁。补丁按应用顺序编号，不因相同文件名而互相覆盖。
JSON 记录位宽、声明内存上限、编译器/源码身份、配置参数，以及七组直接静态
依赖的输出和源码身份；不把这个选定清单当作完整传递依赖 SBOM。

默认只安装 `out`，不把这些材料放入运行根盘。采集脚本要求配置及补丁非空并
生成校验和；三项宿主回归涵盖逐字节保存、缺失配置/空补丁拒绝和篡改检测。
相关整组 60 项本机检查通过，Nix 多输出和目标构建尚待公开 CI 验收。

`python[-wasm64]-check-build-materials` 要求实际构建后核对配置指针宽度、JSON、
全部补丁和 CPython 许可证，成功后上传保留 3 天的验证材料。
[wasm64 首轮](https://github.com/HighCWu/distro/actions/runs/39079878041)已启动。
这不是完整对应源码包：未包含完整 Python/Readline 等依赖源码、完整工具链环境
或长期源码托管；配置仍可能包含实际构建 store 路径。不得用临时 artifact 或
这些配置材料替代正式发行时适用的 GPL 对应源码和其它组件许可义务。

首轮 `f389394` 随后失败在 treefmt 门禁，未进入目标构建：Statix 要求配置字段
使用 `inherit`，ShellCheck 对包含 SHA256SUMS 名称的 find/输出管道报告 SC2094。
`7b8b4ec` 改用显式材料文件列表生成校验和，并采用要求的 Nix 写法；三项材料
回归及相关整组 60 项本机检查继续通过，ShellCheck、简化模式 shfmt 和 nixfmt
检查通过。没有删掉配置、补丁或校验来规避门禁。旧任务结束后启动修正版 wasm64
复验；尚未把真实 Nix 构建、材料上传或实际 Python 运行记为通过。

`6c8cffc` 进一步把材料与最终安装、fixup/strip 完成后的解释器字节关联。
检查直接读取安装输出的 `usr/bin/python3.13` 验证共享内存 Wasm ABI、位宽与
声明上限，再导出 `verification/BINARY_SHA256SUMS`；它的路径相对安装根目录，
不校验构建树中尚未 strip 的临时 Python。`MATERIALS_SHA256SUMS` 是同次配置材料
清单的逐字节副本，两份清单另有共同 SHA256SUMS。CI 复制后再次核对全部材料
及清单，避免只上传一组与最终安装文件没有明确关联的配置。

材料宿主回归增至五项，拒绝缺失解释器、被修改的配置、被替换的最终文件和
被篡改的二进制清单；它使用合成字节，不声称宿主运行过目标解释器。
相关整组 60 项检查及格式/缓存契约检查通过。首轮新版 wasm32 材料验收已启动，
正在运行的 `7b8b4ec` wasm64 材料检查不含这项后续关联，不替换或重启该任务。

校验和只检测相对于已知可信清单的字节变化，不提供签名、发布者身份认证或
独立的构建来源证明。临时 artifact 仍不含解释器本体或完整对应源码，不能据此
宣称完成可重现构建证明、长期发行或全部许可证义务。

后续 wasm32 完整解释器任务 `39080192723` 和材料任务 `39080394738` 虽通过格式
门禁，但均在材料采集前失败：通用多输出钩子将安装目录改成 store 前缀，再被
DESTDIR 嵌套，破坏原有 FHS 布局。`f2cad73` 关闭该目录改写及开发文件搬移，
保持运行输出和手动采集材料分离。61 项相关宿主检查通过，实际修正版材料输出
仍待公开 CI 验收；不能将此次构建失败记为材料已上传或发行合规已完成。

固定 `f2cad73` 的 [wasm32 材料复验][python32-materials-success]现已成功。已检查
重型任务实际日志，确认配置材料、最终安装的 usr/bin/python3.13、二进制清单与
材料清单的校验通过，并确认最终解释器为 wasm32 共享内存、4 GiB 声明上限。
复制后的材料再次校验通过，临时 artifact 上传成功，ID `12118908591`、134180
字节，API 检查时尚未过期。此处没有声称重新下载并独立验证该 artifact，也不以
wasm32 成功代替 wasm64、浏览器运行或完整对应源码交付。

[python32-materials-success]: https://github.com/HighCWu/distro/actions/runs/39081251655

随后已独立下载同一 artifact，确认十四个归档成员，重新核对全部配置材料校验和、
两份 verification 清单的共同校验和及材料清单副本一致；配方与固定 `f2cad73` 的
Git 内容一致，补丁也逐字节一致。pyconfig 确认指针宽度 4，JSON 确认 32 位、
4 GiB 声明上限、七组直接依赖和一个配置补丁。二进制清单只包含预期安装路径及
SHA256；归档不含解释器本体，因此本次下载复核不能独立重算解释器哈希，最终
文件的实际校验仍依据上述 CI 日志。这仍不是完整对应源码包或签名验证。

固定 `050ff03` 的 [wasm64 材料复验][python64-materials-success]也已成功。实际
日志确认配置及两份验证清单、最终安装解释器哈希均通过，最终文件为 wasm64
共享内存，声明上限 17179869184 字节（16 GiB）。该值不是实际已分配内存，
也不证明本任务访问过 4 GiB 以上地址。复制后复验及上传成功；artifact ID
`12119353136`、135064 字节，API 检查时未过期。尚未独立下载复核此 wasm64
归档；它同样不含完整对应源码，也不替代应用运行或后续版本的验收。

[python64-materials-success]: https://github.com/HighCWu/distro/actions/runs/39081599044

## Python 与七项依赖的选定源码导出

distro `84d5bd9` 增加 `python.sourceBundle` / `python-wasm64.sourceBundle`，将
该解释器实际选定的 CPython、zlib、bzip2、xz、SQLite、Readline、ncurses 和
OpenSSL 源码输入归档，而不是重新下载某个移动分支。另附本地集成目录、实际
配置的有序补丁、解释器原始构建材料，以及平台/源码身份/补丁顺序索引。
输入是 patch 前源码；不将任意 postPatch 工作区冒充上游输入。

导出前要求八项源码身份和位宽/内存声明与解释器的构建材料一致，核对材料校验值、
Python 配方和实际补丁字节。普通文件独立归档，不受 Nix store 跨输入硬链接去重
影响；源码符号链接保留目标文本、不追踪外部文件，补丁符号链接则收集实际字节。
归档元数据固定，失败时不替换旧归档，并拒绝把输出放进被收集的目录。

重型 `python[-wasm64]-check-source-bundle` 检查验证伴随校验值、最终已安装
`usr/bin/python3.13` 的校验值与 Wasm ABI，并从真实归档比对原始 Python 许可证、
构建材料清单、集成配方及有序补丁。成功后工作流上传保留三天的
`python-selected-sources-CHECK-COMMIT`，包括 `python-selected-sources.tar.gz`、
README、`BINARY_SHA256SUMS` 和 `SHA256SUMS`；复制后再次核验。
包内没有解释器二进制，也不默认安装进运行根盘。

五项宿主测试覆盖双位宽声明、完整八项输入、同名补丁顺序、硬链接/符号链接、
可重复归档、材料损坏及写入/替换失败清理。真实源码构建、归档和上传的公开
CI 结果见下文，不能仅据这些合成测试宣称成功。

这缩小了对应源码交付缺口，**仍不是完整对应源码包、SBOM、离线重建环境或合规
认证**：没有收齐 musl/compiler-rt/工具链/内核源码闭包、所有 Nixpkgs hooks、
宿主依赖及全系统所需的构建安装信息。自定义 hooks/overrides 必须单独审查。
Readline 等上游组件保留实际许可证，导出器的 MIT 不覆盖它们；短期 artifact 也
不替代长期可获取的版本化源码发行。发布解释器或整套系统前仍须完成实际义务审查。

`e493ecb` 进一步将原抽查升级为独立、完整成员验证：只读枚举八棵源码树、全部
集成目录及构建材料，逐项比对文件字节/模式、符号链接目标、有序补丁和公开索引。
文件按至多 1 MiB 块比较，不解压、不追踪源码树中的符号链接；重复、缺失和额外
成员、材料之外的路径、gzip CRC 错误及追加归档均拒绝。输入目录不可读也明确失败，
不悄悄把遗漏的目录当作完整清单。

源码导出整组八项宿主测试通过，包含多种故障注入、跨输入硬链接去重、外部目录
符号链接、大文件末尾损坏与实际输入变化；另有 68 项既有相关检查通过。
固定 `e493ecb` 的 [wasm32 完整验证](https://github.com/HighCWu/distro/actions/runs/39085695570)
已成功，实际日志确认 13,909 个成员与精确输入逐项一致，并通过伴随校验、最终
解释器校验和 4 GiB 声明 ABI 门禁；上传 artifact `12120478769`，98,210,060 字节。
固定 `84d5bd9` 的 [wasm64 抽查](https://github.com/HighCWu/distro/actions/runs/39085331529)
也已成功，确认 16 GiB 声明 ABI 和最终解释器校验，上传 artifact `12120693069`，
98,205,578 字节；该旧检查不含完整成员校验。日志确认上传成功，尚未独立下载
这两个 artifact。固定 `7967691` 的新版
[wasm64 完整校验](https://github.com/HighCWu/distro/actions/runs/39086338314)
也已成功，实际日志确认 13,909 个成员与精确输入一致、伴随及最终解释器校验，
并通过 16 GiB 声明 ABI 门禁。新版 artifact `12121715304` 为 98,211,832 字节，
日志确认上传成功，尚未独立下载该 artifact；它补充完整校验，不沿用旧抽查结论。
完整成员匹配仍只证明归档与选定输入一致，不证明选定输入已满足全套重建或许可证要求。

## Git 的选定许可材料

Git 双位宽配方从 `1c0ba14` / `f9da168` 起安装选定的原始声明、默认进程启动
补丁与校验清单；四项新增宿主检查覆盖实际复制及失败语义。材料不等于完整
对应源码或链接许可批准，尤其不能因 `NO_OPENSSL` 忽略 libcurl 到 OpenSSL 的
静态链接关系。具体目录、检查与未完成边界见 [Git 运行记录](git-runtime.md)。

`e6f20b8` 另保存独立的选定构建材料，并接入验证后公开 CI 附件；其早期程序摘要
在双位宽目标 CI 均因晚执行的 Wasm strip hook 而失配。`b5b6506` 明确区分
构建阶段摘要与在独立 derivation 中读取完成后输出的最终摘要，不隐瞒原失败。
`ce88973` 再提供 Git、zlib、curl、OpenSSL 的选定源输入、配方、有序补丁和
实际归档工具，并接入逐成员完整性检查；新的目标验收仍待 CI。
它们记录实际配方、配置、补丁顺序和选定库身份，不包含完整源码闭包或离线
工具链，也不构成 Git/libcurl/OpenSSL 链接组合的许可兼容性批准。短期 CI 附件
不能取代满足适用许可证要求的长期源码交付渠道。

固定 `ce88973` 的 wasm32 材料复验与选定源包 CI 已成功，日志确认最终程序摘要、
ABI 与全部 15,748 个选定源/归档成员匹配，两个短期附件上传成功。未独立下载
附件，也不把该技术完整性结果当作完整源码或 Git/libcurl/OpenSSL 链接许可批准；
wasm64 的相同两项检查随后也成功，最终摘要、ABI 与全部选定成员验证及附件上传
均已核实，仍保留相同的交付与许可边界。具体证据见 [Git 记录](git-runtime.md)。

## Python 归档工具与项目 MIT 文本

`cfaacae26e6bc41a2f2d3e63163b41d18692ac84` 在 Python 选定源码配方中显式加入
`archive-tools/exporter.py`、`verifier.py` 和完整 `LICENSE-MIT.txt`，与 Git 包一致。
完整成员验证同时校对三者实际字节和公开索引；缺失、篡改或仅提供部分工具均失败。
旧 schema-v1 Python 输入未声明工具时仍兼容；当前配方明确声明完整三项，不能
将旧格式兼容当作允许当前包遗漏许可文本。工具的 MIT 不覆盖上游组件。

Python 10 项与 Git 5 项宿主归档回归通过；按 Nix 宿主检查的独立目录布局复验，
Python 同样 10 项通过。新测试从归档复制三个已知常规文件，在隔离 Python 模式
执行 verifier/exporter 并重建逐字节相同归档，不使用批量解压。执行仍依赖明确
提供的原始 spec、输入树及构建材料，不是自包含的离线重建环境或可信来源认证。
Nix 格式与差异检查通过；新目标归档及上传尚待公开 CI，不据此宣布完整合规发行。

源码已推送后，主仓库以独立提交 `af310c35202dc9f0a96a8d645da76ff3b95a7765`
更新 gitlink 并确认推送；
[轻量 CI](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39099749259)
已核实成功，实际日志确认 Python 十项及 Git 五项源码归档宿主回归通过，
完整内核宿主 213 项也通过。固定该源码的
[wasm32 选定源码检查](https://github.com/HighCWu/distro/actions/runs/39099787210) 与
[wasm64 选定源码检查](https://github.com/HighCWu/distro/actions/runs/39099791307)
另行触发，结果需核对实际成员验证及上传日志。

这两项固定 `cfaacae` 的目标检查现均已核实成功：伴随清单和最终安装解释器
摘要通过，分别确认为 wasm32／wasm64 shared memory，声明上限为 4 GiB／16 GiB
（不是实际分配或本次访问量）。每个真实归档均逐项匹配 13,914 个成员，未解压，
复制后的校验及上传成功。API 确认 wasm32 artifact `12125884045` 为 98,226,688
字节，wasm64 artifact `12125952687` 为 98,227,990 字节，检查时均未过期。
未独立下载复核上传后的 ZIP；这些技术完整性结果不构成完整对应源码、长期发行
渠道或 Python／Readline 等组件的许可兼容性批准。

## 对外表述

推荐表述：

> 本系统遵循普通 Linux用户态程序通过 syscall/UAPI使用 GPL Linux内核的边界。
> 项目提供 MIT musl/runtime及带 LLVM exception的工具链；开发者可以根据自身代码
> 和依赖的许可证选择开源、闭源及商业发行方式。仅仅在本平台编译或运行，不会使用户
> 程序自动继承 Linux内核的 GPL许可证。发行者仍须审查实际链接和分发的组件，并履行
> 各组件相应的许可证义务。

不应使用“绝对没有许可证风险”“任何组合都可随意改许可证”或“任何组合都可闭源”
这样的无条件保证。
