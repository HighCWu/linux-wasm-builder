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

新组合的目标验收仍待 CI；此前各自的 Python/Git 运行成功不替代此组合检查。
首次固定 `9d669e8` 的 [计划检查](https://github.com/HighCWu/distro/actions/runs/39089869836)
失败在 Nix env 类型校验：`AGENT_WASM64_APPLICATION` 不能直接接收 path，尚未
进入重构建或应用运行。`7eb14a2` 在公共检查边界使用字符串插值，保留 Nix 文件
输入的依赖 context，也兼容原有字符串参数；七项 Python/Git 根盘契约检查通过，
[固定版本复验](https://github.com/HighCWu/distro/actions/runs/39090006954) 的计划检查
已成功，实际目标检查仍在运行。这个计划失败不被标记为应用兼容性成功或普通
运行失败。

本阶段不覆盖浏览器组合工作流、OPFS 持久化、断电一致性、公共网络、pip 生态、
远程托管服务、原生编译器自托管或任意软件兼容性。
