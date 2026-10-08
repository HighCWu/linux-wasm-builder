<!-- SPDX-License-Identifier: MIT -->

# 默认内核的时间ABI回归

时间接口是Linux/Wasm基础支持的一部分，不依赖文件mmap实验、私有系统调用或
softmmu。wasm32使用Linux的time64兼容入口，wasm64使用原生64位时间入口；两者
均由musl向用户程序提供64位time_t。相关stat与utimensat修正及通过记录见
[stat回归记录](file-mmap-plan.md#wasm64原生时间接口对齐)。

## 定时器与等待测试

distro提交`6704aa03568eaff03f248eaefb9187ba88411c31`新增MIT
`distro/basic-init/tests/time-abi.c`。两种位宽共用测试源码，使用默认内核和raw
initramfs。复用现有交叉编译包，因此CI名称为`mmap-benchmark-check-time`及
`mmap-benchmark-wasm64-check-time`，并不依赖文件映射实现。

覆盖范围：

- CLOCK_REALTIME/CLOCK_MONOTONIC的clock_gettime及clock_getres，检查合法秒/纳秒。
- timerfd和SIGEV_NONE POSIX timer的set/get，3000000000秒定时值与周期超过有符号
  32位范围；周期纳秒精确读回，剩余秒值保持超过32位范围。解除时检查old_value。
- timerfd解除后值归零；真实1毫秒单次到期，ppoll最多等待5秒，读回一次到期计数，
  消费后非阻塞读取返回EAGAIN。
- 已就绪的timerfd配合3000000000秒超时，执行ppoll/pselect及信号mask参数，检查
  fd就绪和调用者timeout保持不变。没有实际等待多年，也不调整系统时钟。
- 零超时ppoll/pselect及clock_nanosleep；后者遵循直接返回错误码的libc约定。

SIGEV_NONE不测试信号递送；ready-fd检查不能证明阻塞状态中的长等待、EINTR或
SA_RESTART行为。这里没有验证clock_settime/adjtime、定时器取消竞态或futex，
也没有据此声明完整POSIX支持。已有独立测试的结果仍按各自范围解释。

## 绝对时间扩展

distro提交`2cffdb3b8a8ea9cdcf9ac7139bf1cb650a6a1021`扩展同一MIT测试，在
CLOCK_REALTIME和CLOCK_MONOTONIC上分别验证：

- timerfd及SIGEV_NONE POSIX timer以当前时间加3000000000秒设置绝对截止时间，
  剩余秒值和周期仍超过有符号32位范围，解除时读回old_value。
- 两类定时器拒绝1000000000纳秒，返回EINVAL；拒绝后原长定时器仍保持有效。
- 使用非零但已经过去的绝对时间，使单次timerfd到期，限定5秒等待读取一次计数；
  不用零值，因为零会解除定时器，而不是使其到期。
- clock_nanosleep的过去绝对截止时间成功返回，非法纳秒直接返回EINVAL。

保持当前时钟不变，不实际等待未来截止时间。未来定时器的合法剩余值按范围检查，
不要求动态读数纳秒完全相同。过去截止时间检查不能证明超出2038年的阻塞睡眠
成功完成，也不能替代信号或时钟跳变测试。宿主运行通过并不等于Wasm运行通过。

## 验证状态

宿主gcc严格语法检查、宿主Linux执行及两种long宽度的kstat/syscall轻量检查通过。
宿主测试输出pass后按测试框架保持运行，由本地8秒timeout结束；这不是Wasm运行
证明。仓库元数据和Nix格式检查通过，未在本地构建Linux或LLVM。

公开Node [wasm32](https://github.com/HighCWu/distro/actions/runs/37707485706)和
[wasm64](https://github.com/HighCWu/distro/actions/runs/37707490017)均通过初始相对时间、
timerfd到期及ready-fd等待用例。
绝对时间扩展的Node [wasm32](https://github.com/HighCWu/distro/actions/runs/37712312324)和
[wasm64](https://github.com/HighCWu/distro/actions/runs/37712315836)均已通过。
尚未为该用例执行浏览器检查；既有浏览器用例不计为此测试的通过记录。

## 线程条件变量的time64截止时间

distro提交`41c37ec078b0da87c7b887f946f1e1be4561c70f`新增MIT
`distro/basic-init/tests/thread-time-abi.c`，通过默认内核双核raw initramfs检查
`mmap-benchmark-check-thread-time`和`mmap-benchmark-wasm64-check-thread-time`执行。
不修改内核、libc或公开UAPI，也不依赖私有映射入口。

两种位宽分别覆盖默认realtime及显式monotonic条件变量：

- 当前时间加3000000000秒的绝对截止时间下，各执行8轮pthread_cond_timedwait和
  工作线程signal。主线程持锁创建工作线程，后者只有在timedwait释放锁后才能
  设置predicate并signal，不以sleep建立先后关系；循环允许spurious wake。
- 短截止时间在没有生产者时返回ETIMEDOUT；过去截止时间返回ETIMEDOUT；非法纳秒
  返回EINVAL，遵循pthread接口直接返回错误码的约定。
- 使用ERRORCHECK互斥锁在每类返回后unlock/relock，核验调用线程仍拥有锁；检查
  长截止时间参数保持不变、工作线程join结果及对象销毁。

这是libc条件变量行为回归，不是原始futex所有操作的验证，也没有证明工作线程
signal发生前主线程已经进入内核futex队列。特别地，唤醒竞争和成功返回不能单独
证明原始futex完整地保存了超长超时；未来截止时间没有实际等待至到期。尚不覆盖
取消、信号中断、process-shared条件变量、跨进程同步或时钟跳变。

宿主严格C语法、执行pass、kstat/syscall及仓库元数据检查通过。宿主pass后由8秒
timeout结束框架的常驻循环，不作为Wasm执行证据。公开Node
[wasm32](https://github.com/HighCWu/distro/actions/runs/37762025680)和
[wasm64](https://github.com/HighCWu/distro/actions/runs/37762031463)已触发，结果待确认。
