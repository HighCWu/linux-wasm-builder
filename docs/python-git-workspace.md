<!-- SPDX-License-Identifier: MIT -->

# Python、Git 与 SQLite 的组合工作区

`9d669e8` 增加可选的 `guest-agent.nativeWasm64.rootfsPythonGitExt4`，在同一真实
Linux 根文件系统中安装匹配位宽的 Python、Git、BusyBox、ncurses、OpenSSL 与
CA 数据。默认最小根盘及现有 Python/Git 单独根盘不变。512 MiB 是 ext4 磁盘
容量，不是线性内存上限；这不是带原生编译器的自托管开发系统。

该根盘不安装示例或测试脚本。它是可选运行配方，不是完成许可审查的二进制发行。
Python 静态 Readline 的 GPL 义务，以及 Git 经 libcurl 静态链接 OpenSSL 的兼容性
审查仍须分别处理。项目自有示例、检查和配方采用 MIT，不重新许可第三方软件。

## 可复用示例

[git-workspace-example.py](../sources/distro/distro/python/git-workspace-example.py)
可以在普通 Linux 的 Python/Git 上直接运行，不依赖本项目私有协议，不下载代码或
安装依赖。它接受 `write DIRECTORY` 或 `read DIRECTORY HEAD`，输出包含提交
HEAD、载荷 SHA-256、字节数和阶段的 JSON。目录需明确选择，write 拒绝覆盖已有
目录，read 需要 write 报告的完整 SHA-1 HEAD；read 会创建一个新的 clone 目录，
不是可以覆盖已有 clone 的幂等同步命令。

在仓库根目录中可进行本机语料验证：

```sh
workspace_root=$(mktemp -d)
workspace_report=$(python3 -I sources/distro/distro/python/git-workspace-example.py \
  write "$workspace_root/workspace")
workspace_head=$(printf '%s\n' "$workspace_report" | \
  python3 -c 'import json,sys; print(json.load(sys.stdin)["head"])')
python3 -I sources/distro/distro/python/git-workspace-example.py \
  read "$workspace_root/workspace" "$workspace_head"
```

该命令保留临时工作目录，不自动删除仓库和数据库。本机成功只验证示例，不证明
Wasm 内核、Python 的 posix_spawn 适配或浏览器行为。

实际工作流包括：

1. Python 生成 65,553 字节的全字节载荷与应用脚本，以直接 argv 调用 Git 创建、
   提交仓库并双线程 repack；只清理传给子进程的环境，不修改调用者环境。
2. Git 执行 shell hook，由它启动 Python 检查实际载荷摘要并留下标记。
3. Python 启动仓库内应用，以二进制 stdin/stdout 核对逆序输出，校对 Git 对象、
   工作文件与 HEAD，再将 HEAD、摘要和原始二进制载荷写入 SQLite。
4. 读回时校对原仓库、执行 `clone --no-local` 和严格 fsck、运行 clone 中的应用，
   以只读 SQLite URI 打开数据库，要求完整性检查和结果字节均匹配。

路径包含引号、字面 `$HOME` 和 Unicode，不拼接宿主 shell 命令字符串。只有
明确写出的 hook 使用 shell，再用引用后的参数 exec Python；这不是执行任意
不可信仓库的安全沙箱。

## Wasm 目标检查

`guest-agent-check-python-git-root-wasm64` 通过公开 SDK 导入上述原始示例，在
第一台 Linux 实例执行 write、sync 并完整关闭。仅保留 ext4 块数据，第二台新
实例校验示例源字节后执行 read；另外由 SDK 精确读回原仓库与 clone 的载荷。
它要求两个实例均发生块写入与 flush，且成功关闭，不复用进程或线性内存。

目标还核对 Python 指针位宽、安装前缀和 CA 存储，Git 的 long/size_t 位宽、
选定原始许可材料及 checksum，以及测试专用文件缺失。实际子进程由现有
posix_spawn 适配路径承载，不声称增加普通 fork、内核 softmmu 或新的 UAPI。

四项本机工作负载检查通过，含工作文件、pack、hook、SQLite、HEAD、数据库缺失
反例，拒绝覆盖与环境隔离检查；相关 Node 轻量回归共 34 项通过。格式、工作流、
仓库元数据、source pin 和缓存契约检查通过。本地完整类型门禁仍只有三项旧
kernel dist 的 `FSDirectoryEntry.type` 声明错误，未屏蔽；公开 CI 保留完整检查。

新组合的目标需要独立 CI；此前各自的 Python/Git 运行成功不替代此组合检查。
首次固定 `9d669e8` 的 [计划检查](https://github.com/HighCWu/distro/actions/runs/39089869836)
失败在 Nix env 类型校验：`AGENT_WASM64_APPLICATION` 不能直接接收 path，尚未
进入重构建或应用运行。`7eb14a2` 在公共检查边界使用字符串插值，保留 Nix 文件
输入的依赖 context，也兼容原有字符串参数；七项 Python/Git 根盘契约检查通过，
[固定版本复验](https://github.com/HighCWu/distro/actions/runs/39090006954) 的计划检查
已成功，实际目标随后也已核实成功：完整类型门禁及 write/read 两个全新实例
检查通过，分别约 6.89/7.04 秒，外层约 14.38 秒。此结果固定 `7eb14a2`，
不是后续共享检查、OPFS 或页面控件已经通过。原计划失败仍保留。

## 浏览器组合检查

`7ad998f` 将上述完整目标断言提取为 Node/浏览器共用的检查，不复制简化版本。
两者都导入原始 Python 示例，并要求嵌套子进程、hook、二进制载荷、Git 对象、
SQLite 和跨实例读回成功；摘要在运行端通过 Web Crypto 独立计算。两台实例之间
只保留 ext4 块数据；应用脚本也必须从第一台实例写入的文件逐字节读回。

新增入口为 `browser-tests-check-agent-python-git-root-wasm64-chromium` 和
`browser-tests-check-agent-python-git-root-wasm64-firefox`。每个浏览器必须完成唯一
指定用例，包含按顺序执行的 write/read 两阶段并成功关闭；独立报告门禁拒绝
遗漏、额外用例、跳过和重试。浏览器使用与 SDK 检查相同的引导盘和可选根盘，
不向系统根盘添加测试脚本。

相关 Node 轻量回归现为 40 项通过，另有四项本机 Python 示例测试通过。新增
适配器注入检查验证实际共享检查使用的浏览器断言，反例包含错误 ABI、源文件/
clone/HEAD/摘要损坏、notice 命令失败、未 flush 和关闭失败；这些不是真实内核
运行证据。浏览器模块打包、格式、工作流、仓库元数据、三项 source pin 和十项
缓存契约检查通过。完整本地类型检查仍只有前述三项旧声明错误，未绕过门禁。

第一次浏览器调度误用了缺少 `check` 的入口名，
[Chromium](https://github.com/HighCWu/distro/actions/runs/39090598339) 和
[Firefox](https://github.com/HighCWu/distro/actions/runs/39090601603) 在计划的名称
校验处结束，没有进入构建或运行；核实结束后已提交正确入口。
[Chromium 目标](https://github.com/HighCWu/distro/actions/runs/39090665965) 和
[Firefox 目标](https://github.com/HighCWu/distro/actions/runs/39090668642) 的计划检查
已成功；两项均固定 `7ad998f`，实际运行分别验收，不把计划成功记为运行成功。

其中 Chromium 随后已核实实际成功：两个应用阶段均执行，唯一指定用例通过，
总计 5.6 秒，独立报告门禁确认精确用例且零跳过/重试。Firefox 随后也已核实
实际成功，两阶段均执行，唯一用例 22.8 秒通过且精确报告门禁成功；两者均固定
`7ad998f`，不扩大为 OPFS 或新组合页面控件已通过。

## 跨页面 OPFS 恢复

`85f7f7f` 在两个独立浏览器检查入口接入 OPFS：
`browser-tests-check-agent-python-git-opfs-root-wasm64-chromium` 和
`browser-tests-check-agent-python-git-opfs-root-wasm64-firefox`。原有内存块盘检查
不被这两项取代，也不取消正在执行的旧版目标。

写阶段只初始化一个新的唯一命名磁盘；已有文件会拒绝覆盖。它启动真实 Linux，
导入示例并执行完整 write 工作流，sync 后等待整机及磁盘设备关闭，返回原始
提交 HEAD。页面重载后，检查阻断初始根盘下载，只打开已有 OPFS 文件，不传入
create、capacity 或截断参数；以原始 HEAD 执行完整 read 工作流，核对持久化的
示例源、hook、Git 对象、原始载荷及 SQLite 记录，并新建独立 clone 作二次校验。
两种存储路径共用同一个
应用检查函数，不以简化的数据库查询代替应用协作。

每个 OPFS 入口有独立的唯一用例及零跳过/重试报告门禁。测试最终仅删除它创建的
精确命名 OPFS 磁盘；不修改系统默认根盘，也不改动内核、进程协议或用户 UAPI。
这只是受控检查，不是多标签页并发创建磁盘或任意不可信仓库的安全设计。

47 项相关 Node 回归和四项本机 Python 示例测试通过；新增存储/生命周期注入
反例覆盖已有磁盘、缺失读盘、非法阶段/名称/HEAD、写入中止、应用校验失败和
关闭失败。注入检查还实际执行浏览器用例的控制流程，要求跨重载传递同一 HEAD、
阻断模板并清理精确磁盘。这些结果不代表真实浏览器 OPFS 已通过，目标结果另验。
浏览器模块打包、格式、工作流、元数据、source pin 和缓存契约检查通过；本地
完整类型检查仍只有前述三项旧声明错误，公开 CI 完整门禁不变。

固定 `85f7f7f` 的 [Chromium OPFS 检查](https://github.com/HighCWu/distro/actions/runs/39091161575)
和 [Firefox OPFS 检查](https://github.com/HighCWu/distro/actions/runs/39091164560)
现均已核实实际成功：Chromium 唯一用例 13.8 秒，Firefox 唯一用例 26.4 秒，
两者均通过精确报告门禁，零跳过/重试。这验证固定 `85f7f7f` 的受控跨页面
工作区恢复，不扩大为断电恢复或新浏览器启动器已有持久化功能。

## 可操作的浏览器配方与应用归档

`01fdab1` 新增可选 `wasm64-python-git-example`，复用已有启动、停止、Python 显式选择、
字面 JSON argv、流式输入输出、取消和文件下载控件，使用 512 MiB Python/Git
根盘。默认最小配方与 Python 单独配方不变。完整输出包含可直接导入的
`git-workspace.pyz` 和构建源 `workspace-source/`；归档内为原始示例源与 MIT
文本，不嵌入解释器或重许可第三方组件。

重资产只在公开 CI 构建：`nix build .#wasm64-python-git-example`。取得完整输出
后用其中的 `server.mjs` 服务目录，下载 `/git-workspace.pyz`，在页面选择 Python
并导入此文件。留空 stdin，传入 `["write", "/root/workspace"]`，再用报告的完整
HEAD 传入 `["read", "/root/workspace", "完整HEAD"]`。这保留了原示例的边界：
write 不覆盖已有目录，read 新建 clone，不是持续同步或连续编辑工具。

新增双浏览器控件检查要求应用 write/read 的精确报告，以及通过文件下载控件
逐字节读回 clone 的 65,553 字节载荷。组件级成功不能替代控件级验收。这个页面
在该版本中仍是临时内存根盘，停止或重载即丢失工作区；OPFS 检查没有自动赋予
该版本页面持久化。后续显式持久化控件见下文。
该配方不是已完成许可批准的二进制发行，既有 Readline、OpenSSL 链接和完整源码
交付要求不变。

固定 `01fdab1` 的
[Chromium 控件检查](https://github.com/HighCWu/distro/actions/runs/39092698046) 和
[Firefox 控件检查](https://github.com/HighCWu/distro/actions/runs/39092700345) 的计划
均已成功。Firefox 随后已核实实际日志：116 个 bundle 文件 SHA-256 校验成功，
唯一指定控件用例 14.5 秒通过，精确报告门禁确认零跳过/重试，覆盖 write/read 与
下载字节校验。Chromium 也已核实实际日志：同样 116 文件校验成功，唯一指定用例
9.9 秒通过，精确报告门禁确认零跳过/重试。两者不替代 SDK 和 OPFS 的独立结果。

五项本机工作区测试通过，包含新增的精确源码、固定 ZIP 元数据、可重复打包和
移走源目录后执行 zipapp 的 write/read。原归档构建六项回归通过；页面/进程/
打包契约 36 项通过，页面语料四项通过。页面语料在挂载盘首次发生两项 5 秒
超时（一项为既有用例）；保持超时不变，将相同轻量源码复制到本机临时目录后
四项均通过。此复验不是目标构建或浏览器运行，不能据此记为控件 CI 已通过。

主仓库轻量 CI 另接入 `python-git-workspace-example-提交SHA` 短期附件：仅收集
项目自有 MIT 应用、构建源、许可文本、源码 pin 记录和 SHA-256 清单，不包含
解释器、Git、内核或其他依赖二进制。上传前实际构建归档并以本机 Python/Git
执行 write/read，再检查复制后清单；附件保留七天，不替代长期发行渠道或系统
对应源码交付。最终上传核实结果与此前失败记录见下文。

主仓库 `75546f7` 的 [轻量 CI](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39092638192)
在旧 Python 根盘宿主检查失败，未进入新附件上传：条件化的页面说明不再是第三
个字面替换，旧检查因此得到 `2 != 3`。修复保留两项共同替换，另明确验证条件
说明的 shell 转义、两个完整标签、两个可选根盘及默认配置，不跳过或删除门禁。
这不是实际浏览器运行失败，也不把本机附件收集成功当作公开附件已上传。

测试修复 `e9abdb6` 在保留原超时的本机临时副本上通过完整 19 项相关宿主检查；
挂载盘上的两项 Python 子进程超时未通过放宽门禁处理。临时副本首次缺少一项
TypeScript 语料而出现 ENOENT，补齐原文件后 19 项全部通过；没有修改语料内容。

附件上传前还必须通过 `scripts/verify_workspace_artifact.py`：文件与目录成员必须
精确匹配约定，不接受符号链接或额外文件；应用、构建源和 MIT 文本逐字节匹配
已提交 gitlink 对应的 Git 对象（不是可能被编辑的工作目录），pin 记录匹配已提交
manifest，六文件 checksum 清单完整且无额外路径。
ZIP 必须恰好包含按序的许可与原始应用，且具有固定元数据；在同一 CI Python
环境重建后还须逐字节相同，拒绝前后夹带数据。校验器不提取或执行归档；本机
write/read 仍由独立步骤完成。七项损坏控制覆盖源码/许可、pin、清单、ZIP 内容/
元数据/重复成员/路径/夹带数据及文件集合，不代表第三方许可审查或目标运行。

本机实际执行工作流中的打包块已通过：归档 write/read 成功，65,553 字节摘要
匹配，六项 checksum 以及 Git 对象/pin 校验成功；最终校验器也对实际构建的归档
完成了 canonical ZIP 复验。工作流语法及文档检查通过。这里未执行目标重构建，
也不将本机结果记为 GitHub 附件上传成功。

源码修复已推送后，主仓库以独立提交 `4797f31` 更新 pin，再以 `8f5d93a` 接入
附件校验；[新的轻量 CI](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39093951030)
已结束失败。原先 19 项 Python 宿主检查已通过，附件也完成 write/read，但 runner
未安装 `rg`，默认 shell 又没有 pipefail，旧清单管道把空输入生成了 `-` 的摘要；
新校验器因此正确阻止上传。起初只看到校验失败而推测 locale 不同，完整日志已
否定该归因；单独固定排序并不足以修复。

最终实现用显式六文件参数调用 `sha256sum`，没有发现/排序管道、没有 `rg` 依赖，
缺失任一文件直接失败。新增回归要求工作流原命令精确包含六文件列表，并实际
执行后通过完整校验，且删除任一输入后默认 CI shell 必须失败；相关检查现为
八项通过。修复已作为 `3d466f9` 推送，
[公开复验](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39094801981)
现已核实全部成功：实际日志确认八项回归、归档 write/read、源码/许可/Git 对象/
pin/六文件 checksum 均通过，上传步骤完成且 API 确认附件存在。MIT 应用附件
ID 为 `12124202696`，大小 9,297 字节，保留七天；不是完整系统二进制发行，也
没有代替系统对应源码和依赖许可证审查。未独立下载并审计上传后的 ZIP。

## 启动器的显式 OPFS 控件

`7f8bc97` 将受控 OPFS 恢复接入独立示例页面：默认仍使用临时内存根盘；用户可以
明确创建或打开一个命名磁盘。创建拒绝覆盖已有文件，打开不创建、不重新下载
根盘模板、不截断或改变容量。磁盘名限定为 1–48 个小写 ASCII 字母、数字或连字符，
文件为当前浏览器 origin 下的 `linux-wasm64-名称.ext4`。

同 origin 页面以 Web Locks 互斥持有磁盘，直到设备关闭完成；实际 I/O 继续复用
已有独占 OPFS 同步访问句柄与块设备 Worker。不支持相关 API、配额不足、已存在/
缺失磁盘及启动失败均明确报错，不退回空白根盘，不自动删除失败初始化留下的文件。
打开旧盘必须使用相同运行配方和兼容版本；模板标签不代表检查过旧盘安装的软件。

新增“Sync and stop Linux”仅在空闲时可用：先运行原生 `/bin/sync`，失败时保留
当前 Linux 和磁盘供重试；成功后停止整机并等待输出及设备 flush/close，再允许
重启。普通 Stop 仍可中断正在运行的应用，不承诺保存所有未同步写入。关闭页面、
后台写入、浏览器清理/驱逐及断电不属于已验证的事务或崩溃恢复，需另行备份。

核对真实设备实现时发现设备公开对象只有 `closed`、没有 `.close()`；因此增加
MIT JavaScript API `closeDevice(device)`，导出已有幂等释放实现，用于未挂载设备
和整机已停止后的资源清理。它不停止 Linux、不做文件系统同步，不是热拔插 API，
也不新增内核 UAPI、softmmu 或改变 NOMMU 配置。三个真实设备检查覆盖本地成功/
失败与 MessageChannel 远端释放；页面/磁盘相关 27 项检查通过，原 Python 根盘
三项契约仍通过，之前完整页面相关 65 项检查通过后又加入两项磁盘/打包契约。
完整内核宿主回归 213 项通过，包含新公开入口在真实本地和远端设备上的释放；
格式、Nix 格式、工作流语法和文档检查通过。这些不是新 OPFS 页面目标运行证据。
另有两项主仓库跨层回归实际组合页面磁盘管理、Worker 握手、公开内核入口和真实
MessageChannel 后端：关闭确认前页面锁不释放，flush 失败仍报告错误并释放资源，
后端只关闭一次且 Worker 只终止一次。文件与锁是宿主适配器，不是真实 OPFS，
也没有启动 Linux；这两项检查已通过，并接入主仓库轻量 CI。

新增真实浏览器用例从页面创建磁盘，完成 Python/Git/SQLite 写工作流，同步停止、
拒绝覆盖、重载，再打开原盘，要求根盘模板零请求并校验原始 HEAD、SQLite、Git、
hook、应用和完整下载载荷。原临时用例保留，两个浏览器各要求精确两例且零跳过/
重试；源码接入与本机检查不构成这些新控件已经实际通过。目标构建仅在公开 CI。

源码 `7f8bc97ebe1350af144fd7fac44b02f41299dab1` 已推送，主仓库以独立提交
`e50c6126dce1e81b53234fc23fb6f2f026535d82` 更新 gitlink 并接入跨层检查。
[主仓库轻量 CI](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39097437097)
已成功，实际日志确认新增跨层回归和完整内核宿主 213 项通过；固定该源码的
[Chromium 检查](https://github.com/HighCWu/distro/actions/runs/39097480248)、
[Firefox 检查](https://github.com/HighCWu/distro/actions/runs/39097483078)
中，Chromium 已核对实际日志成功：117 个 bundle 文件 SHA-256 校验通过，两例共
18.6 秒通过，精确报告确认零跳过、零重试。Firefox 也已核实成功：同样 117 个
文件校验通过，两例共 44.9 秒通过，零跳过、零重试。该版本的两种存储控件已有
双浏览器证据，但不批准后续流式或争用扩展。跨层与公开设备释放共五项宿主检查再次通过，
仍不代表真实浏览器运行。

本阶段不覆盖断电一致性、用户主动清理存储后的恢复、存储配额保障、公共网络、pip 生态、
远程托管服务、原生编译器自托管或任意软件兼容性。

## OPFS 初始化的流式传输

后续优化将创建模式的 HTTP 响应流直接 `pipeTo` OPFS 写流，使用流的背压，
不再通过 `arrayBuffer()` 在 JavaScript 中额外持有完整根盘模板。临时模式仍需
内存根盘，打开已有盘仍不下载模板。仅在下载与写流关闭均成功后才启动磁盘 Worker。
这不消除浏览器内部缓存、OPFS 配额要求或 Linux 运行内存，也不是实测的峰值承诺。

新增宿主检查验证阻塞写入时不会拉取整个输入、八个块逐字节写入、提交后才连接
Worker，以及下载、文件创建、写流创建、写入和关闭失败时保留原始错误并释放
流与页面锁。健康写流在下载失败时被 abort；自身已报错的流不保证底层 abort
回调再次执行。失败文件仍不自动删除或覆盖。HTTP 错误和空响应体不转为空盘。
最终完整页面宿主回归 70 项通过，最终页面打包通过；尚不构成流式版本的真实
浏览器验收或内存峰值测量，源码发布和主仓库 pin 更新按原子顺序分别记录。

流式源码 `d51e2950497267437f7820304008c2a3b161b561` 已确认推送到公开 fork；
旧双浏览器检查固定在 `7f8bc97`，其结果不扩大到流式版本。
主仓库随后以独立提交 `f8c6449bc89cf6da0ec7bd53141dd7e8f418a9dc` 更新 gitlink，
已确认推送；[轻量 CI](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39098270952)
已成功，实际日志确认流式下载、背压、错误清理、两项跨层关闭及完整内核宿主
213 项通过。两项真实 MessageChannel 跨层关闭检查也在本机重新打包并通过；
它们不执行 OPFS 初始化。流式版本的双浏览器检查另行触发，不替换旧版任务。
[Chromium](https://github.com/HighCWu/distro/actions/runs/39098295965) 和
[Firefox](https://github.com/HighCWu/distro/actions/runs/39098298955) 均固定 `d51e295`，
其中 Chromium 已核实实际日志成功：117 个 bundle 文件 SHA-256 校验通过，两例
共 19.5 秒通过，精确报告确认零跳过、零重试。Firefox 也已核实实际日志成功：
同样 117 个文件校验、两例共 45.2 秒通过、零跳过／重试。这不是浏览器内存峰值
测量，也不包含后续双页面争用扩展。

## 实际双页面磁盘争用

后续测试扩展在持久化用例写入完成、原 Linux 仍运行时，通过相同浏览器 context
新建第二页，分别以 Open 和 Create 尝试相同名称。要求两次均明确报告另一页面
正在使用，第二页允许重试但没有运行中的实例，根盘模板请求为零，原页面仍运行。
第二页关闭后才继续原页面的同步停止、重载、恢复与完整数据校验；清理仍只删除
该测试 UUID 对应的文件。既有两项精确用例名称和零跳过／重试门禁不变。

这补充真实同 origin Web Locks 的跨页面验收，不改变运行时实现，不声称浏览器
崩溃后恢复或所有不遵循锁协议的外部访问安全。语法和格式检查通过；旧版浏览器
结果不包含此扩展，新增场景须在固定新源码的公开 CI 中实际执行。

争用扩展源码 `fb0c54c9e7acbf98ba4178993016d375c8b3f701` 已确认推送；
磁盘／打包宿主契约 12 项通过，不把它们当作真实双页面通过。
主仓库以独立提交 `0e717e5607ec864eacf72b3898ee1bfde9174146` 更新 gitlink，
已确认推送；[轻量 CI](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39099360739)
已成功，实际日志确认两项跨层关闭检查与完整内核宿主 213 项通过。新源码的
[Chromium](https://github.com/HighCWu/distro/actions/runs/39099390865) 与
[Firefox](https://github.com/HighCWu/distro/actions/runs/39099394181)
已核实实际日志成功：两者各有 117 个 bundle 文件校验和两例通过，Chromium
19.7 秒、Firefox 38.6 秒，精确报告均确认零跳过、零重试。这包含新增双页面
Open／Create 争用拒绝与后续原盘数据恢复，不包含后面的服务器启动校验修订。

## 开发服务器的启动校验

后续开发服务器在监听端口之前调用已有 `verifyBundle`，验证完整文件集合、大小
和 SHA-256。清单缺失／无效、文件缺失／新增／改变或符号链接均使启动失败，
不会重新生成清单、构建缺失文件或继续监听。原手动 `node integrity.mjs` 入口保留。
这增加启动时对全部载荷的一次流式读取，不是整盘 JavaScript 数组分配。

服务器及完整性检查共九项宿主回归通过，完整页面宿主回归 76 项通过、无跳过。
测试覆盖正常校验后提供隔离／MIME 响应头、六种启动拒绝情形，以及启动后新增
越界符号链接时 HTTP 路径保护仍拒绝访问。失败用例有独立超时和子进程清理。
启动校验不是持续防篡改、不可变快照、来源认证、签名或 Linux 可启动性验证；
部署后仍需保持目录不被其他写入者修改，生产托管也仍须配置正确的隔离响应头。
此前已通过的浏览器版本不包含这个启动改动，新版本需独立公开 CI。
源码 `9447391deac3c531d4a70a38d0a5fd8914cbe9c4` 已确认推送。
主仓库随后以独立提交 `e94d36a5f713b9f004136664cf859963c7f46f63` 更新 gitlink
并确认推送；[轻量 CI](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39100144106)
已核实成功，实际日志确认服务器正常／六种拒绝检查、跨层关闭及完整内核宿主
213 项通过；固定该源码的
[Chromium](https://github.com/HighCWu/distro/actions/runs/39100162955) 与
[Firefox](https://github.com/HighCWu/distro/actions/runs/39100165424)
检查另行触发。两者实际日志均显示启动校验拒绝了测试目录内新增的
`node_modules/@playwright` 符号链接，未进入浏览器用例，不能记作验收通过；
Firefox 也已自然结束，未取消任务。下文修订测试布局以保留完整性门禁。

## agent 构造失败时的磁盘回收

页面打开磁盘后，将 agent 构造也纳入启动错误清理范围，避免构造抛错时绕过
`root.close()`。构造失败不启动 Linux；页面等待磁盘清理完成才允许重新启动，
清理本身失败则报告聚合启动错误，不当作正常停止。正常运行、同步与停止路径不变。

两项故障注入检查在保留旧写法的独立临时副本上均实际失败（零次磁盘关闭），
修复后通过；20 项页面状态检查通过，最终页面打包通过。挂载盘完整回归有一项
既有 Python 子进程 5 秒超时，保持该超时不变，将相同轻量源码复制到本机临时
目录复验后完整 78 项均通过。未屏蔽或删除断言，未进行本地目标构建。
这些是宿主故障路径证据，不代表真实浏览器发生过 agent 构造失败，也不将此前
固定版本的浏览器成功泛化为本修复已经通过新的目标矩阵。

该修复源码 `b6d00ad` 已确认推送，主仓库随后以独立提交
`f2412fa484db34b4a04425926cf5df9c47fe61d9` 固定并确认推送。
[轻量 CI](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39101192697)
已成功，实际日志确认两项 agent 构造故障回收检查及完整内核宿主 213 项通过。

## 浏览器测试依赖与应用完整性边界

三个独立示例的浏览器测试入口改为导入各自原始 Nix 应用包中的 `server.mjs`，
由该服务器校验并提供原始应用目录。Playwright 依赖链接、配置和上传测试夹具
仍在包外的测试目录；不重新生成清单、不忽略链接、不放宽文件集合校验，
也不把测试文件作为应用载荷提供给 HTTP 客户端。实际发布包和服务器实现不变。
最小示例的 SDK 程序及 Python 示例的两份上传夹具改由测试进程从套件目录读取，
仍经实际文件选择控件上传并核对原有运行结果，不再通过应用 HTTP 服务读取包外夹具。
组合示例的 `git-workspace.pyz` 本来就是正式应用载荷，其下载校验保持不变。

宿主测试同时运行直接入口和包外入口，后者包含测试专用符号链接且从测试目录
启动，要求仍先校验原始包、正常提供隔离响应头，并拒绝访问测试专用文件。
配方检查覆盖全部三个入口，六种损坏包拒绝检查保留。最终相同轻量源码在本机
临时目录完整回归 80 项通过，零失败／跳过；挂载盘另有既有 Python 子进程
5 秒超时，未提高超时或跳过断言。此宿主结果不替代 Nix 集成及双浏览器验收。

测试布局源码 `6c378f6b51421e0a6f699f136e2460200bfe28ce` 和夹具上传修订
`e9a8a5e18e674d126ac9d20979fd4d7eef47dce9` 均已确认推送。夹具脚本语法和
包外相对路径检查通过；三套示例的 Chromium／Firefox 新检查以最终源码另行触发，
在实际运行完成前不声称本次浏览器验收成功。
主仓库已以独立提交 `18836aa9723837dc09f1bd770caef9f862e101d7` 固定最终源码并
确认推送；文档另以 `[skip ci]` 提交，不将文档提交作为新的运行时验收版本。

固定 `e9a8a5e` 的公开任务：

- 最小示例：[Chromium](https://github.com/HighCWu/distro/actions/runs/39102118686)、
  [Firefox](https://github.com/HighCWu/distro/actions/runs/39102121357)。
- Python 示例：[Chromium](https://github.com/HighCWu/distro/actions/runs/39102125159)、
  [Firefox](https://github.com/HighCWu/distro/actions/runs/39102127709)。
- Python＋Git 示例：[Chromium](https://github.com/HighCWu/distro/actions/runs/39102131003)、
  [Firefox](https://github.com/HighCWu/distro/actions/runs/39102133796)。
