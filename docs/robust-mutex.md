<!-- SPDX-License-Identifier: MIT -->

# Robust mutex 的线程退出恢复

这组独立 MIT 用户态用例（distro `95f8012`）使用标准 pthread 接口，检查 process-private、ERRORCHECK、
robust mutex 的所有权状态迁移；不改变 Linux、musl 或执行 ABI。

原有四种场景各重复 4 次，所有者线程已经 join 后才开始后续恢复，不用 sleep 假定线程已退出：

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
固定 `95f8012` 的 [Node wasm32](https://github.com/HighCWu/distro/actions/runs/39007573645)
和 [Node wasm64](https://github.com/HighCWu/distro/actions/runs/39007576621) 已成功；实际
日志均包含完整 robust mutex 完成阶段和 pass。这是标准 pthread 线程退出路径的验证，
不是内核独立 robust list 崩溃清理的验证。

## 不覆盖的边界

musl 的正常 pthread 退出路径会在用户态处理 process-private robust mutex；因此这组
通过不证明内核独立遍历 robust list 的崩溃清理已经通过。它也不覆盖原始线程退出
syscall、进程被杀、process-shared、PI、robust pending 窗口、死亡前已经排队的等待者、
异步取消、应用数据自动恢复或任意并发交错。ERRORCHECK 对象成功解锁只验证当前
所有者可操作，不替代对其他线程错误解锁的完整负向测试。

## 并发竞争后的所有者退出（待目标验证）

distro `c184e08` 追加四轮并发恢复，每轮一名所有者和四名竞争者，仍只使用标准
pthread 接口。所有者先持有 robust mutex；四名竞争者分别用 trylock 明确取得
`EBUSY`，再通过独立 mutex/condition-variable 通知已观察到活跃所有者，并尝试
有界 timedlock。所有者必须等四份通知后才带锁退出，不靠 sleep 推断重叠。

验收要求恰好一名竞争者取得 `EOWNERDEAD` 并调用 consistent，其余竞争者随后
正常取得锁；四次受保护更新必须全部完成，每个 join 结果及对象销毁都须成功。
协调等待和竞争锁使用十秒期限，外层目标 watchdog 仍保留；超时不是通过证据。
新增阶段在原完成标记之前输出：

```text
robust mutex: four contending threads serialize one owner-dead repair verified
```

GCC/Clang 的相同程序均通过，宿主整组仍为 12 项；除了原有反向控制，还分别删去
并发修复调用，必须明确报告 `contending waiter did not acquire repaired mutex`，
不能只观察到挂起。浏览器现有 robust mutex 测试额外要求新阶段，未增加或跳过用例。
双位宽 SDK 目标已提交公开 CI，尚待实际阶段与 pass 日志；旧版本 Node/浏览器通过
记录不包含此新增场景。

这里证明每个竞争者确实观察到活跃所有者并参与恢复，但通知与 timedlock 之间仍有
调度窗口，不能证明所有线程在所有者死亡前已进入内核 futex 队列。不扩大为 kernel
robust-list 崩溃清理、任意排队交错、PI、共享进程或异步取消的保证。
本轮只增加 MIT 验收语料，不修改 musl、Linux、默认配置或执行 ABI。

## 浏览器接入

distro `4db1fcc` 将同一 SDK 产物接入浏览器 runtime 套件，不重新编写或降低断言。
新增 `runs SDK robust mutex owner-death recovery through Linux`，与基础 futex/waitv
新用例一起将精确报告门禁由 11 项扩为 13 项。共享构造器按目标位宽选择 SDK 和内核，
不将 wasm32 用户程序混装进 memory64 运行路径。

页面通过独立 `/runtime-robust-mutex.cpio` 启动；必须收到完整完成阶段和 pass，且无
fail。既有总超时继续覆盖运行与整机关闭，关闭失败不能被用户程序 pass 掩盖。新增
宿主契约测试验证取对归档、下载失败会拒绝、缺少完成阶段或 pass 会拒绝、混入 fail
会拒绝，以及报告中的真实用例名称和 Nix 精确清单完全一致。
相关浏览器断言/报告门禁/关闭生命周期宿主检查共 23 项通过；Chromium、Firefox 的
新版 wasm64 验收均已成功：[Chromium](https://github.com/HighCWu/distro/actions/runs/39008215057)
与 [Firefox](https://github.com/HighCWu/distro/actions/runs/39008218961) 日志各确认 13 项通过，
精确报告门禁确认零跳过、零重试；此结果不扩大上述语义覆盖边界。
