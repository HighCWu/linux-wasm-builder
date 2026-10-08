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
SA_RESTART行为。这里没有验证clock_settime/adjtime、定时器取消竞态、futex或
绝对时间等待，也没有据此声明完整POSIX支持。已有独立测试的结果仍按各自范围解释。

## 验证状态

宿主gcc严格语法检查、宿主Linux执行及两种long宽度的kstat/syscall轻量检查通过。
宿主测试输出pass后按测试框架保持运行，由本地8秒timeout结束；这不是Wasm运行
证明。仓库元数据和Nix格式检查通过，未在本地构建Linux或LLVM。

公开Node [wasm32](https://github.com/HighCWu/distro/actions/runs/37707485706)和
[wasm64](https://github.com/HighCWu/distro/actions/runs/37707490017)已触发，结果待确认。
尚未为该用例执行浏览器检查；既有浏览器用例不计为此测试的通过记录。
