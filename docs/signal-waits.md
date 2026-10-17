<!-- SPDX-License-Identifier: MIT -->

# 信号等待、部分 I/O 与回收边界

distro `26c0fab` 新增共享 `signal-waits.c`，经公开 SDK 编译，在原配置的双核
Linux 上运行。该测试提交没有修改内核、libc、执行 ABI 或 syscall 重启策略；
后续发现并修正的内核掩码问题见下文。

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
该提交时 `time-consumer-test.js` 共六项通过；新增 I/O fixture 后为下述八项。命令：

```console
node --test sources/distro/distro/sdk/time-consumer-test.js
```

测试程序按运行协议在 pass/fail 后驻留，宿主检查会在有界执行后终止它，并同时要求
确切末阶段文本和 pass 标记；仅观察超时不能算通过。宿主执行不证明 Wasm ABI。

新增公开 Actions 检查 `sdk-check-signal-waits-runtime` 和
`sdk-wasm64-check-signal-waits-runtime`，双位宽入口均使用两个 CPU。
浏览器共用同一 SDK 程序，严格用例名为
`runs SDK ppoll and pselect signal-mask handoff through Linux`，加入现有 wasm32/wasm64
runtime suite。固定 `26c0fab` 的四项检查均已实际运行失败，日志一致报告
`wait did not restore the exact original signal mask`：

- [Node wasm32](https://github.com/HighCWu/distro/actions/runs/38990752055)
- [Node wasm64](https://github.com/HighCWu/distro/actions/runs/38990750888)
- [Chromium wasm64](https://github.com/HighCWu/distro/actions/runs/38990753997)
- [Firefox wasm64](https://github.com/HighCWu/distro/actions/runs/38990752836)

根因在架构同步 handler：原实现保存 `current->blocked`，此时 ppoll/pselect 已安装
临时掩码；`signal_setup_done` 又会清除 restore_sigmask 标志，因此返回后遗失原掩码。
Linux `e81f9ad0e` 改为在该标志清除前复制 `*sigmask_to_save()`，与上游其他架构保存
信号帧返回掩码的选择一致。handler 执行期间仍使用临时掩码加 sa_mask/自身信号，
返回后再恢复等待之前的掩码；不改变 syscall 重启分类，也不放宽回归断言。
distro `de12442` 已接入该内核，公开
[源码预取](https://github.com/HighCWu/linux-wasm-builder/actions/runs/38993986456)
成功并提供固定 revision 的解包哈希。固定 `de12442` 的
[Node wasm32](https://github.com/HighCWu/distro/actions/runs/38994158070) 与
[Node wasm64](https://github.com/HighCWu/distro/actions/runs/38994163823) 已核对实际日志，
均输出完整末阶段文本和 pass 标记。
[Firefox wasm64](https://github.com/HighCWu/distro/actions/runs/38994159209) 已核对实际日志：
9 项通过，严格用例门禁确认零跳过、零重试。
[Chromium wasm64](https://github.com/HighCWu/distro/actions/runs/38994160445) 在源码下载阶段
遭遇 HTTP 429，未执行测试；不能声称其通过，也不是信号断言再次失败。

## 部分 I/O 与子进程回收

`e9b8308` 新增 MIT fixture `signal-io.c`，不修改内核或 libc：

- 对普通 handler 和 SA_RESTART handler，先由另一线程用 FIONREAD 确认管道已填满，
  再向写线程发送信号。没有读者腾出空间，信号必然发生在已经写入一段数据之后。
  单次 write 必须返回已提交字节数，不能返回 EINTR、丢失计数或重复重启写入。
- 读取可用前缀时，写端仍然打开，read 必须返回现有字节而不是等到请求长度或 EOF。
  逐字节核对后，由应用显式重试后缀；再次读回比较完整内容，空管道应先 EAGAIN，
  关闭写端后再得到 EOF，不能留下重复字节。
- callback clone 创建的子进程先阻塞在释放管道上；另一个线程逐次发送并确认信号，
  直到不带 SA_RESTART 的 waitpid 返回 EINTR。重试间的小延时仅用于节流，
  不以任何固定延时断言 waitpid 已注册等待。
- 子进程未退出时 WNOHANG 返回 0；释放后，两次 WNOWAIT 保留相同的退出状态 37。
  最后 waitpid 只回收一次，后续等待返回 ECHILD。

公开 SDK 提供双位宽 `signal-io-runtime` 检查；浏览器复用同一 SDK 产物，严格用例为
`runs SDK partial pipe I/O and interrupted child reaping through Linux`。
新 fixture 的 GCC/Clang 宿主检查通过；合并既有 time、thread-time、signal-waits，
宿主检查共 8 项通过。目标 Wasm 验收尚待确认，不把宿主 callback clone 当作 Wasm
克隆或标准 fork 的通过证据。固定 `e9b8308` 的双位宽 Node 检查已提交；旧版本浏览器
任务仍保持运行，不取消或重启，也不能将其结果用作新增 I/O fixture 的通过证据。

这些重复用例不是对任意并行交错的形式证明；有限超时允许把丢失唤醒暴露为失败，
并没有使无限等待的正确性自动成立。本轮没有验证内部多次重挂等待是否保留同一
deadline；新增 I/O/回收 fixture 也不证明异步 I/O 取消、副作用回滚、read 拷贝过程
中的信号交错、带 SA_RESTART 的 waitpid、futex 重启或标准 fork。
后续按这些边界独立增加用例，不以一组等待测试代替完整 POSIX 信号语义。
