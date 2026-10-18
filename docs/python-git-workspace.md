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
的计划检查均已成功并进入实际重检查，真实运行尚未验收。不以本机注入检查或
旧版内存根盘结果替代这些目标。

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
仍是临时内存根盘，停止或重载即丢失工作区；OPFS 检查没有自动赋予页面持久化。
该配方不是已完成许可批准的二进制发行，既有 Readline、OpenSSL 链接和完整源码
交付要求不变。

五项本机工作区测试通过，包含新增的精确源码、固定 ZIP 元数据、可重复打包和
移走源目录后执行 zipapp 的 write/read。原归档构建六项回归通过；页面/进程/
打包契约 36 项通过，页面语料四项通过。页面语料在挂载盘首次发生两项 5 秒
超时（一项为既有用例）；保持超时不变，将相同轻量源码复制到本机临时目录后
四项均通过。此复验不是目标构建或浏览器运行，不能据此记为控件 CI 已通过。

主仓库轻量 CI 另接入 `python-git-workspace-example-提交SHA` 短期附件：仅收集
项目自有 MIT 应用、构建源、许可文本、源码 pin 记录和 SHA-256 清单，不包含
解释器、Git、内核或其他依赖二进制。上传前实际构建归档并以本机 Python/Git
执行 write/read，再检查复制后清单；附件保留七天，不替代长期发行渠道或系统
对应源码交付。当前上传结果尚待独立核实。

本阶段不覆盖断电一致性、用户主动清理存储后的恢复、存储配额保障、公共网络、pip 生态、
远程托管服务、原生编译器自托管或任意软件兼容性。
