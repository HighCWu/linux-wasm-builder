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
以上记录为原始 initramfs 路径；后续 SDK 与浏览器的独立验证见下一节。

## SDK 与真实浏览器接入

distro `a177370` 复用上述 MIT `time-abi.c`，通过 SDK 的 `wasm-linux-cc`
分别构建 wasm32/wasm64 程序，而不是新增一份内容相近的测试。新增定向检查入口
为 `sdk-check-time-runtime` 与 `sdk-wasm64-check-time-runtime`，使用默认内核与
raw initramfs，不开启文件映射实验，也不修改内核、musl、公开 UAPI 或许可证边界。

双位宽的 Chromium/Firefox 运行套件增加同一程序，必须看到完整时间 ABI 阶段、
最终通过标记及成功机器关闭。强制指定用例清单由 6 项增至 7 项；缺失、跳过或
重试均不能作为通过。
[wasm64 SDK](https://github.com/HighCWu/distro/actions/runs/38937536594) 和
[Firefox wasm64](https://github.com/HighCWu/distro/actions/runs/38937543746)
均已成功，固定 distro `a177370`：前者日志包含完整时间 ABI 最终阶段，后者实际
执行全部 7 项浏览器用例，包含新增 time64 程序及成功机器关闭；目标检查和整个
工作流均通过。尚不将其外推为 wasm32 SDK 或 Chromium 的新增 time64 用例通过。

新增 2 项宿主回归通过 GCC/Clang 严格构建同一源码，并核对完整阶段及通过标记。
共享测试框架在标记后保持 sched_yield，因此宿主进程由 3 秒限时强制结束；必须
同时核对标记、无失败记录及预期终止方式，超时本身不算成功。这些只验证测试
源码，不证明 Wasm time64 可用。另有 22 项运行协议、关闭生命周期和浏览器报告
门禁宿主回归通过。仍不修改系统时钟、不实际等待多年，也不增加时钟跳变、
任意阻塞等待的 EINTR/SA_RESTART 或完整浏览器定时精度的保证。

## 线程条件变量的time64截止时间

### SDK 与浏览器验证入口

distro `0316709` 将同一 MIT `thread-time-abi.c` 接入 SDK，使用
`wasm-linux-cc -pthread` 构建，不再仅依靠底层测试程序包。双位宽定向入口为
`sdk-check-thread-time-runtime` 和 `sdk-wasm64-check-thread-time-runtime`，均使用
默认内核、双核和 raw initramfs，不启用实验性映射功能。

Chromium/Firefox 双位宽运行套件复用 SDK 产物，强制用例清单由 7 项增至 8 项。
新增用例要求完整的条件变量最终阶段、用户控制台通过标记及成功机器关闭；覆盖范围
沿用下文的长截止时间、取消、广播、超时与锁所有权测试，不扩大为完整 futex 保证。

[wasm64 SDK 定向检查](https://github.com/HighCWu/distro/actions/runs/38943652523)
已通过，固定 distro `0316709`：实际运行日志包含完整条件变量最终阶段与
`::vm-test::pass`，目标检查和整个工作流均成功。
[Chromium wasm64 检查](https://github.com/HighCWu/distro/actions/runs/38943658455)
已启动，结果待确认；不能据此声明浏览器 pthread 检查通过。此前 7 项 Firefox
通过记录也不包含新增 pthread 用例。
本地 GCC/Clang 对定时器与线程两份源码的严格构建及最终标记检查共 4 项通过，
连同运行关闭协议与报告门禁共 22 项轻量检查通过；宿主限时终止约定与上一节相同，
不能替代 Wasm 或浏览器运行结果。

### 原始 initramfs 检查范围

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
信号中断、process-shared条件变量、跨进程同步或时钟跳变。取消扩展见下节。

宿主严格C语法、执行pass、kstat/syscall及仓库元数据检查通过。宿主pass后由8秒
timeout结束框架的常驻循环，不作为Wasm执行证据。公开Node
[wasm32](https://github.com/HighCWu/distro/actions/runs/37762025680)和
[wasm64](https://github.com/HighCWu/distro/actions/runs/37762031463)均已通过初始条件变量
唤醒、超时及锁所有权用例。

## 条件变量等待的延迟取消

distro提交`3dc2f8eaf09da646f875c1fe96c4fac56698c080`扩展上述MIT测试，沿用
默认内核双核检查。realtime和monotonic各执行8轮超长截止时间下的延迟取消：

- 工作线程持锁注册cleanup，设置ready并通过独立条件变量通知主线程，然后进入
  目标条件变量的timedwait。目标条件变量没有生产者，允许spurious wake后继续等待。
- 主线程取得同一互斥锁并观察ready，证明工作线程已在timedwait释放过锁；在持锁
  时请求pthread_cancel，随后解锁使清理继续。没有sleep或私有内核队列观测接口。
- cleanup以ERRORCHECK互斥锁的unlock检查锁所有权；join结果必须为PTHREAD_CANCELED，
  cleanup计数必须恰好为1。重新取得互斥锁、signal条件变量，再执行后续轮次和
  短超时检查，最终销毁对象。

该握手不证明已进入内核futex队列，也不区分请求取消时线程已经阻塞还是取消请求
在进入阻塞前被处理。这里验证的是POSIX延迟取消、锁重获及对象复用行为，不涵盖
异步取消、取消与signal/broadcast同时发生、process-shared或任意取消点的通用保证。
没有修改Linux或musl实现，没有改变生产配置。

宿主严格语法和执行pass、轻量ABI及仓库元数据检查通过。扩展后的Node
[wasm32](https://github.com/HighCWu/distro/actions/runs/37770600646)和
[wasm64](https://github.com/HighCWu/distro/actions/runs/37770606285)均已通过延迟取消扩展。
宿主验证不作为Wasm运行证据，亦尚未新增浏览器执行记录。

## 多等待者取消后的广播

distro提交`a532b65faafefdbe3b5e89fb2e449b20421ae69a`继续扩展同一MIT测试和
默认内核双核检查。realtime和monotonic各4轮，每轮4个工作线程使用超长截止时间
等待同一条件变量。所有predicate、计数和握手均由同一ERRORCHECK互斥锁保护。

主线程等待4个ready通知并重新持锁，随后取消第一个工作线程。先解锁、join并
确认PTHREAD_CANCELED及一次cleanup，再设置release并broadcast。其余3个线程
必须正常返回各自join结果，wake计数为3，cleanup计数仍为1。循环复用条件变量，
最后继续执行原有短超时及对象销毁检查。

这是“完成一个取消后再广播”的顺序行为验证，不涵盖取消与broadcast同时发生、
唤醒公平性或内核队列排列。ready握手证明等待者释放过锁，不证明均已进入内核
futex队列；不把长截止时间下的正常唤醒当作实际等待多年或完整futex语义的证据。
没有修改Linux、musl实现、公开UAPI或生产配置。

宿主严格C语法、执行pass、轻量ABI及仓库元数据检查通过。公开Node
[wasm32](https://github.com/HighCWu/distro/actions/runs/38844561358)和
[wasm64](https://github.com/HighCWu/distro/actions/runs/38844566099)均已通过顺序取消后广播用例。
尚未为该扩展执行浏览器检查。

## 取消请求与广播交错

distro提交`54d15a2ba9e1b8c967c2095a05ec35e96e8c9b50`保留“取消并join之后
广播”的基线，新增两种请求顺序：同一持锁区间内先cancel后broadcast，以及先
broadcast后cancel。两种时钟、每种顺序各4轮，每轮4个等待者。release predicate
在广播前设置；主线程解锁前，等待者无法重新持有该锁并完成返回。

这两种场景不在广播前join取消目标。允许该线程join返回PTHREAD_CANCELED或
正常fixture指针：libc可能处理取消，也可能消费唤醒并正常完成。其余三个线程
必须正常返回；cleanup计数必须等于实际取消数（0或1），wake计数必须为4减去
取消数。保留ERRORCHECK锁所有权检查及对象跨轮复用，输出每种时钟和顺序的目标
取消/正常完成轮数，不要求一次运行必须观察到两种结果。

这是持锁下发出两种顺序请求后的交错验证，不是两个发送线程在同一时刻操作，也
没有穷举调度、证明内核队列入队点或验证signal只能唤醒一个等待者的语义。没有
新增pthread_testcancel来强行让取消获胜，也没有修改Linux、musl或生产配置。

宿主严格C语法、执行pass、轻量ABI和仓库元数据检查通过。公开Node
[wasm64](https://github.com/HighCWu/distro/actions/runs/38859238903)已通过；
[wasm32](https://github.com/HighCWu/distro/actions/runs/38859233374)也已通过。
没有新增浏览器执行记录。
