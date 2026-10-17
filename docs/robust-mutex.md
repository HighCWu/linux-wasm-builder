<!-- SPDX-License-Identifier: MIT -->

# Robust mutex 的线程退出恢复

这组独立 MIT 用户态用例（distro `95f8012`）使用标准 pthread 接口，检查 process-private、ERRORCHECK、
robust mutex 的所有权状态迁移；不改变 Linux、musl 或执行 ABI。

每种场景重复 4 次，所有者线程已经 join 后才开始后续恢复，不用 sleep 假定线程已退出：

- 持锁线程正常返回而不解锁；下一名所有者必须取得锁并收到 `EOWNERDEAD`。
  调用 `pthread_mutex_consistent` 后解锁，另一个线程应能成功取得并释放同一把锁。
- 取得 `EOWNERDEAD` 后不修复、直接解锁；随后 timedlock 和 trylock 均须返回
  `ENOTRECOVERABLE`，不能把它当成取得了所有权。
- 第二名所有者取得 `EOWNERDEAD` 后也不修复就退出；后继所有者仍能取得
  `EOWNERDEAD`，修复后可供其他线程正常复用。
- 所有者在持锁时请求自身 deferred cancellation，并进入 `pthread_testcancel`；
  join 必须得到 `PTHREAD_CANCELED`，随后仍可执行 owner-dead 修复及复用。

等待使用有界的 `pthread_mutex_timedlock`，防止漏掉 owner-dead 转换时无限死锁。
超时本身不是成功证据，必须核对返回码、每次 join 的结果、对象销毁和最终完成标记。

## 验证入口

`sources/distro/distro/basic-init/tests/robust-mutex.c` 通过已安装的 SDK 编译，分别接入
`sdk-check-robust-mutex-runtime` 和 `sdk-wasm64-check-robust-mutex-runtime`，均为双核。
目标完成标记为：

```text
robust mutex: owner death, consistent recovery, unrecoverable state and cancellation verified
::vm-test::pass
```

宿主入口 `node --test sources/distro/distro/sdk/time-consumer-test.js` 使用 GCC/Clang
执行相同语料。反向控制删去修复阶段的 `pthread_mutex_consistent`，必须在另一线程
复用时明确报告 `repaired mutex was not reusable`，而不能仅凭超时判为成功。
包含新增用例的宿主整组 12 项已通过，GCC/Clang 均核对了反向控制的精确失败标记。
目标 Wasm 结果与宿主 fixture 验证分开记录，新增目标验收仍待公开 CI 确认。

## 不覆盖的边界

musl 的正常 pthread 退出路径会在用户态处理 process-private robust mutex；因此这组
通过不证明内核独立遍历 robust list 的崩溃清理已经通过。它也不覆盖原始线程退出
syscall、进程被杀、process-shared、PI、robust pending 窗口、死亡前已经排队的等待者、
异步取消、应用数据自动恢复或任意并发交错。ERRORCHECK 对象成功解锁只验证当前
所有者可操作，不替代对其他线程错误解锁的完整负向测试。

浏览器套件暂不增加此用例；现有信号/futex 浏览器结果不能代替这里的目标运行结果。
