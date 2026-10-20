<!-- SPDX-License-Identifier: MIT -->

# Dash：普通进程接口的真实应用接入候选

能力工作转向真实用户态程序。现有 BusyBox/Bash 使用专用 callback-clone 改造，
不能代替普通应用调用标准 `fork()` 的证据。新增显式选择的 `dash-fork` /
`dash-fork-wasm64` 包，采用与固定 nixpkgs 同版本、同内容哈希的 Dash 0.5.13.4
源归档，不做 callback 改写，不替换默认 shell、SDK 或系统镜像。

## 构建边界

- 使用现有可选 fork libc、执行对象和完整链接后的 Asyncify 变换。
- Dash 无条件调用 `vfork()`；仅给该应用添加 `-Dvfork=fork` 编译参数，明确改走
  普通 fork。没有新增 libc vfork 或共享地址空间／暂停父进程的语义。
- 源码生成工具使用构建机编译器，目标代码使用匹配位宽的 fork 编译入口。
- Dash 使用 setjmp/longjmp。其与 fork 执行现场恢复的组合必须由此候选的真实
  运行验证，不能据原有静态 C 微测试宣称任意 SjLj/C++ EH 程序已受支持。
- 自有配方、脚本及检查为 MIT；Dash 保留 BSD/GPL 上游许可与 `COPYING`，不将
  第三方源码改标 MIT。产物保留配方、配置、源码归档及 SDK 材料链接；这些是
  Nix store 中的选定材料，不是完整离线 SDK 或完整传递依赖源码交付的声明。

## 当前工作负载

`processes.sh` 由目标 Dash 解释，外部工具明确通过 BusyBox 可执行文件运行，
避免把 shell builtin 成功误认为外部 exec 成功。覆盖：

1. subshell 变量隔离、外部命令及命令替换的换行处理。
2. 三进程 pipeline、文件输出重定向、继承 fd 再重定向到标准输入。
3. 后台任务的 PID/wait 与退出码、前台执行另一份 Dash 的退出码。
4. 命令不存在的 127、不可执行的 126、子 shell 语法错误的 2，以及之后再次
   fork/exec 成功。语法错误也用于实际触发 shell 的错误展开路径。

四个阶段都完成后输出最终 pass，目标 init 保持存活，由已有运行器完成关机。
这不是交互终端、完整 job control、任意异步信号、多线程 fork 或动态链接验收。
BusyBox 工具仍沿用自身既有实现；所验证的普通 fork 调用者是 Dash。

## 验证状态

源码 `0ade881`，集成 pin `fe10de0`。下载归档的 SHA-256 与配方一致；在本机用
同一源码和 fork 替代参数构建原生 Dash 后，完整脚本以及失败依赖反向检查通过。
两项宿主检查与格式检查通过。这只证明工作负载和原生应用行为，不是 Wasm 证据。

首轮[公开 CI](https://github.com/HighCWu/distro/actions/runs/39444729143) 选择
`dash-fork-wasm64-check-runtime`，先验证主位宽的构建、变换、
Linux 内完整阶段及关机。目标结果未核实前保持候选状态；若暴露工具链或运行时
缺口，应优先定位并修正该缺口，不用 callback 重写绕过。wasm32 和浏览器需在
主路径打通后另验，不从 Node 或本机结果推定通过。

首轮 `39444729143` 在 treefmt 的 ShellCheck 门禁失败，尚未构建或运行目标 Dash。
SC2030/SC2031 指向工作负载有意保留的 subshell 变量隔离检查，不是已定位的 Wasm
运行错误。`811b2af` / 集成 pin `3a9f717` 对这两处添加说明及定点豁免，保留父子
两侧断言；本地 ShellCheck、shfmt 和两项宿主检查通过。
[新版 wasm64 复验](https://github.com/HighCWu/distro/actions/runs/39450779425)
已完成并失败：静态检查及构建机语料通过，目标编译在 `redir.c` 的
`memfd_create()` 调用处报缺失声明，尚未链接、执行完整变换或运行脚本。

musl 已存在该函数的普通 syscall 转发实现，但 `sys/mman.h` 把其 GNU 声明放在
Wasm 排除区间中。musl `c080f8e1` 将这一声明移到 Wasm 也可见的 `_GNU_SOURCE`
区间，不改签名、不新增 syscall 或 memfd 实现，不额外开放 mprotect、mremap 等
仍被隐藏的接口。新增原型编译断言先在 wasm32/wasm64 复现失败，修正后双位宽及
x86_64 对照通过；原有整数头文件、msync、源码 pin 检查和可选 fork 补丁 dry-run
也通过。声明可见不保证当前内核提供 memfd、sealing 或文件映射全部能力，调用
仍应处理内核返回的正常错误。

[源码哈希预取](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39511885807)
成功后，distro `a900f5d` 固定新 musl 精确 revision/hash，主仓库 `041ee70` 同步
两个 gitlink、头文件回归和轻量 CI。未在 Dash 中添加私有函数声明或绕过该调用。
[修正后的 wasm64 复验](https://github.com/HighCWu/distro/actions/runs/39512053823)
已派发，目标构建、变换、完整脚本及关闭结果仍待核实；不宣称 Dash 或任意
SjLj 与 fork 的组合已经受支持。

```sh
gh workflow run ci.yml --repo HighCWu/distro --ref YOUR_PUSHED_BRANCH \
  -f heavy-check=dash-fork-wasm64-check-runtime
```
