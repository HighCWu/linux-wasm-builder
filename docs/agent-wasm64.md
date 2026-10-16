<!-- SPDX-License-Identifier: MIT -->

# 高层 agent 的 wasm64 接入

目标是在已有 wasm64 内核、SDK 和浏览器用户程序路径上，继续提供匹配位宽的
进程、文件、挂载及网络 API。当前 `@lowland/guest` 会话仍使用 wasm32 ABI；
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
已启动，结果待确认；宿主通过不证明目标头文件编译通过。

## 后续接入顺序

1. 完成目标检查；头文件与描述不一致时，以真实目标 ABI 为准修正。
2. 显式识别会话协议版本和目标 ABI，定义不支持或不匹配时的失败行为，不从地址
   大小或 JavaScript 环境猜测。保持原有 wasm32 会话兼容性。
3. 让 syscall 层依会话选择 seek、truncate、stat 的参数和结构；审计 bigint、
   signed scalar 与公开 number API 的边界，不静默截断不可表示的值。
4. 构建匹配位宽的 agent、启动镜像和用户态，不混用 wasm32 BusyBox/rootfs。
   wasm64 SDK 不等于整个发行版 scope 已转换为 wasm64。
5. 在 Node 和真实 Chromium/Firefox 验证启动、进程/标准流、metadata、大 offset、
   删除后打开描述符、挂载、网络及关闭，同时保留 wasm32 回归。

这些增量不改变 Linux UAPI 或组件许可证。新增自有描述器、测试和构建检查采用 MIT；
内核、libc 和工具链仍遵循各自上游许可证。
