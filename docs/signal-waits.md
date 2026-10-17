<!-- SPDX-License-Identifier: MIT -->

# 信号与 ppoll/pselect 的等待边界

distro `26c0fab` 新增共享 `signal-waits.c`，经公开 SDK 编译，在原配置的双核
Linux 上运行。没有修改内核、libc、执行 ABI 或 syscall 重启策略。

## 本轮断言

对 ppoll 和 pselect，分别安装普通 handler 和 SA_RESTART handler：

- 先阻塞 SIGUSR1，再排入一个确认 pending 的信号；等待时临时解除阻塞，必须
  调用 handler 并返回 EINTR，不能丢失唤醒或自动重试直到超时。
- 第二线程通过命令管道同步后向等待线程发信号，不使用 sleep 来假定已进入等待。
  信号可能先于或晚于等待注册到达；每轮只允许一个信号并等待发送确认。
- 两种交接各重复 16 轮，总计 128 次；检查 handler 次数、handler 执行时自身信号
  被阻塞、另一个 SIGUSR2 始终阻塞，以及返回后完整原始信号掩码恢复。
- 保持 SIGUSR1 阻塞时，真正的空集合定时等待必须超时，pending 信号不能被消费；
  超时不应明显提前，调用者 timespec 不能被 libc 包装器修改。
- 同一 pending 信号不能遮盖可读 fd；等待不消费管道字节，读出后零超时等待应为空。
  最后临时解阻塞，必须投递该信号并返回 EINTR。

ppoll/pselect 不属于由 SA_RESTART 自动重启的接口，所以这里即使启用该 flag，
也要求 EINTR。这不改变已有 pipe read 的 SA_RESTART 测试或各 syscall 的重启分类。

## 验证状态与边界

GCC/Clang 对该 fixture 的两项宿主检查通过；连同既有 time/thread-time fixture，
当前 `time-consumer-test.js` 共六项通过。命令：

```console
node --test sources/distro/distro/sdk/time-consumer-test.js
```

测试程序按运行协议在 pass/fail 后驻留，宿主检查会在有界执行后终止它，并同时要求
确切末阶段文本和 pass 标记；仅观察超时不能算通过。宿主执行不证明 Wasm ABI。

新增公开 Actions 检查 `sdk-check-signal-waits-runtime` 和
`sdk-wasm64-check-signal-waits-runtime`，双位宽入口均使用两个 CPU。
浏览器共用同一 SDK 程序，严格用例名为
`runs SDK ppoll and pselect signal-mask handoff through Linux`，加入现有 wasm32/wasm64
runtime suite。固定 `26c0fab` 的四项检查均已通过任务规划并进入实际重型 job，
运行结果仍待 CI：

- [Node wasm32](https://github.com/HighCWu/distro/actions/runs/38990752055)
- [Node wasm64](https://github.com/HighCWu/distro/actions/runs/38990750888)
- [Chromium wasm64](https://github.com/HighCWu/distro/actions/runs/38990753997)
- [Firefox wasm64](https://github.com/HighCWu/distro/actions/runs/38990752836)

这些重复用例不是对任意并行交错的形式证明；有限超时允许把丢失唤醒暴露为失败，
并没有使无限等待的正确性自动成立。本轮没有验证内部多次重挂等待是否保留同一
deadline，也没有覆盖部分 read/write、wait 的单次回收、futex 重启或标准 fork。
后续按这些边界独立增加用例，不以一组等待测试代替完整 POSIX 信号语义。
