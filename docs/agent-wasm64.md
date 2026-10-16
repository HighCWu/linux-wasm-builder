<!-- SPDX-License-Identifier: MIT -->

# 高层 agent 的 wasm64 接入

目标是在已有 wasm64 内核、SDK 和浏览器用户程序路径上，继续提供匹配位宽的
进程、文件、挂载及网络 API。当前 `@lowland/guest` 公开启动路径仍使用 wasm32；
内部会话已能选择原生 wasm64 syscall 编码，但尚无真实 wasm64 agent 运行证明。
已有 wasm64 C/C++ 通过记录不代表 agent 或完整发行版通过。
保持 `CONFIG_MMU=n` 和真实线性内存指针，不引入内核 softmmu。

## ABI 前置工作

distro `7e8eeb7` 新增内部 `abi-wasm64.ts`，不切换现有会话，不增加公开包导出。
原有 `abi.ts` 保留 wasm32 默认行为。两者复用结构描述器和已检查的公共 flags、
errno、signals、目录记录及 wait 宏，避免复制另一套独立常量。

wasm64 使用原生 `lseek/newfstatat/fstat/ftruncate`，不暴露 ILP32 的
`llseek/fstatat64/fstat64/ftruncate64` 名称。相同 syscall 数字不意味着相同参数
约定：原生 lseek 接收一个有符号 64 位 offset 并直接返回结果，而不是拆分高低位
及输出指针。原生内核 `struct stat` 为 128 字节，时间秒和纳秒字段为 64 位，
以 bigint 保存；它不是 wasm32 的 104 字节 `struct stat64`，也不是 musl 的公开结构。

新增 `guest-agent-check-abi-wasm64` 用 wasm64 SDK 编译由描述器生成的 C 静态断言，
核对 syscall、字段 offset/size、结构大小及 pointer/long 位宽，同时将 agent C
源码编译为目标对象。它不启动 agent、不提供可用的 wasm64 系统镜像，也不能代替
端到端行为检查。重型编译由公开 CI 承担：

```sh
gh workflow run ci.yml --repo HighCWu/distro --ref YOUR_PUSHED_BRANCH \
  -f heavy-check=guest-agent-check-abi-wasm64
```

4 项宿主回归及同套独立打包检查通过，覆盖原生别名、128 字节布局、大于 2^53 的
字段、负秒、带偏移视图、wasm32 描述不受影响及 C 断言生成。类型检查通过。
[目标编译检查](https://github.com/HighCWu/distro/actions/runs/38945796060)
已通过，固定 distro `7e8eeb7`：日志确认构建 `linux-agent-abi-wasm64`，生成的
原生 ABI 静态断言和当时的 agent C 源码均成功编译，目标检查和整个工作流成功。
这仍不是 agent 启动、镜像或完整发行版的运行证明。

## 显式会话身份

distro `943aae8` 保持默认 v3/wasm32 会话，新增内部显式 ABI 的 v4 握手。
8 字节头的末尾 u16 在 v3 必须为 0，在 v4 为 32 或 64；agent 按实际 pointer/long
位宽校验，不把请求中的任意值盲目回显。原生 LP64 executor 拒绝 v3，避免继续接受
没有目标身份的 ILP32 请求。session 确定版本后，agent 对每条 lane 要求相同版本；
宿主也要求相同版本及 ABI 回显，lane 不一致会使会话失败并关闭连接，不自动降级。

内部 `GuestSession.connect(device, { abi })` 使用 v4；不指定 abi 时保留 v3，
因此现有合规 wasm32 镜像保持原握手。高层公开 API 尚未选择 wasm64 镜像。
该提交曾在原生 syscall adapter 接入前禁止 wasm64 请求；下节的后续提交已移除
这项临时保护，改为按已协商的会话 ABI 编码。

11 项宿主回归及同套独立打包检查、类型检查通过，覆盖两种 ABI 的 v4、默认 v3、
短回复、错误身份、lane 不一致、关闭及当时的 syscall 保护。GCC/Clang 通过本地
socket pair 执行真实 C 握手，包括拒绝 native LP64 的 v3、错误 ABI 和错误 lane
版本；没有启动 PID 1，也不计作 Wasm 执行证明。更新后的
[目标编译](https://github.com/HighCWu/distro/actions/runs/38947236148) 已通过，
日志确认构建 `linux-agent-abi-wasm64`，包括 v4 agent C 与 ABI 静态断言。
[默认 wasm32 完整 agent 集成检查](https://github.com/HighCWu/distro/actions/runs/38947242982)
仍在运行；两项均固定 distro `943aae8`，不包含下述后续 syscall 改动。

## 按会话选择 syscall 布局

distro `70ad41c` 将 seek、truncate、路径与描述符 stat 接入已协商的会话 ABI。
wasm32 保留拆分参数与 104 字节结构；wasm64 使用原生参数与 128 字节结构。
原始 seek 结果保持 bigint，超出有符号 64 位的 offset/length 在发送前拒绝。
公开 number 字段不可精确表示时抛出 RangeError，不静默舍入；公开 seek 若收到
不可表示的结果，会在内核已改变文件位置后拒绝。调用者应留意这一副作用。
时间先以 bigint 合并秒与纳秒，再转换为毫秒；超过 JS Date 范围返回 null。

13 项新增 syscall/精度回归与更新后的 11 项会话回归均通过，独立打包执行也通过。
加上已有 stat 与 ABI 描述检查，共 30 项宿主测试及类型检查通过。覆盖负 offset、
两种参数布局、带偏移视图、errno、整数精度与 Date 正负边界。它们验证的是宿主
编码和解码，不能代替真实 wasm64 Linux 上的 agent syscall 运行。

## 最小原生运行检查

distro `165bdfd` 新增 `guest-agent-check-runtime-wasm64` 重型检查：用 wasm64 SDK
编译 `runtime-init.c`，以最小 initramfs 在 wasm64 内核中启动。测试外壳包含并调用
现有 agent 的 session worker；v4 校验、clone 后启动线程、vsock lane 与 syscall
执行器均为真实实现，没有复制另一套协议或在宿主模拟 syscall。

测试要求原生 executor 拒绝 v3 和显式 wasm32 身份，然后用 v4/wasm64 建立会话。
文件回归包含超过 4 GiB 的 seek、负相对 offset、非法负绝对 offset 的 EINVAL、
小文件 truncate/read/stat，以及 unlink/recreate 后原描述符的内容与 inode 分离。
两个并发 stat 请求也经过独立 lane。大 offset 检查只移动文件位置，不分配大文件，
不能作为大文件容量、内存分配或超过 4 GiB truncate 支持的证明。

GCC/Clang 的本地语法检查、TypeScript 检查和 Nix 格式检查通过；目标编译及实际
运行交给[公开 CI](https://github.com/HighCWu/distro/actions/runs/38949325409)，
固定上述提交，结果待确认。检查不属于默认 wasm32 测试自动发现范围，必须显式运行：

```sh
gh workflow run ci.yml --repo HighCWu/distro --ref YOUR_PUSHED_BRANCH \
  -f heavy-check=guest-agent-check-runtime-wasm64
```

该外壳不执行生产环境的 root discovery/pivot，不启动用户子程序，不安装 wasm32
BusyBox，也不依赖完整 wasm64 rootfs。即使本项通过，也只证明 Node 上的最小
agent 请求链；生产镜像、进程/标准流、浏览器及高层公开镜像选择仍需分别验证。

## 后续接入顺序

1. 保持目标 ABI 编译检查，并验证新增 v4 代码的目标编译及现有 wasm32 会话回归；
   头文件与描述不一致时，以真实目标 ABI 为准修正。
2. 优先以最小 initramfs 启动真实 wasm64 agent，验证 v4 会话及 seek、truncate、
   stat 的完整请求链，避免以宿主模拟测试代替执行证据。
3. 在运行验证基础上接入高层镜像选择，保持现有 wasm32 会话兼容性。
4. 构建匹配位宽的完整启动镜像和用户态，不混用 wasm32 BusyBox/rootfs。
   wasm64 SDK 不等于整个发行版 scope 已转换为 wasm64。
5. 在 Node 和真实 Chromium/Firefox 验证启动、进程/标准流、metadata、大 offset、
   删除后打开描述符、挂载、网络及关闭，同时保留 wasm32 回归。

这些增量不改变 Linux UAPI 或组件许可证。新增自有描述器、测试和构建检查采用 MIT；
内核、libc 和工具链仍遵循各自上游许可证。
