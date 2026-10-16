# 宿主私网连接生命周期

`createNetwork` 为 Linux 运行实例提供私有 IPv4 网络。宿主可通过 attachment 的
`connect({ port, transport: "udp" })` 获取数据报读写流；这不是让浏览器直接获得
互联网 UDP socket，外部访问仍取决于显式配置的适配器和浏览器安全边界。
HTTP 转换的独立约束见[宿主 HTTP 说明](host-http.md)。

## UDP 写入失败

IPv4 数据报的 UDP 正文上限是 65507 字节：65535 减去 20 字节 IPv4 头和
8 字节 UDP 头。适配器在构造/复制 UDP 数据报及编码 16 位长度之前拒绝超限输入，
写入方收到 RangeError，不先复制一份注定无法发送的正文。

WritableStream 的 sink `write` 抛错会使发送流进入错误状态，但不会自动调用
sink `abort`。因此适配器必须在写入失败路径主动移除内部流记录并结束读取端，
不能让待处理的 read 或该连接的内部端口占用一直存活；写入方仍收到原始错误。
`connection.close()` 继续保持幂等。由于发送流已终止，调用者应新建连接，而不是
把这个 JavaScript 流当作可以在 EMSGSIZE 后继续发送的 POSIX 数据报描述符。
其他发送故障也走同一清理路径；若此前已经发出部分 IP 分片，清理不能撤销它们。

distro `b348651` 的 4 项宿主回归覆盖 0/65507 字节接受和 65508/131072 字节
拒绝；两个拒绝场景在修复前均复现接收读取一直等待，修复后正常结束。测试通过
真实私网适配器和 Web Streams 执行，拒绝外部 TCP/DNS 调用；它不启动 Linux，
合法边界检查不证明数据已被 Linux 收到。隔离打包运行和 TypeScript 类型检查均
通过，与已有 Fetch 生命周期回归合计 27 项通过。

Chromium/Firefox 的独立存储/网络套件新增同一清理场景，并要求 15 项指定用例
全部执行、零跳过、零重试。
[38931469594](https://github.com/HighCWu/linux-wasm-builder/actions/runs/38931469594)
已在 Chromium/Firefox 均成功，15 项指定用例的强制门禁通过，包含 UDP 写入失败
后的清理和合法正文边界。该用例不启动 Linux，也不访问外部网络，不替代 Linux
网络程序集成证据。Linux socket ABI 的独立进展见
[SDK socket 说明](sdk-sockets.md)。

## UDP 主动关闭

显式 `connection.close()`、整个 `network.close()`、读取端取消及运行实例网络脱离
现共用流清理路径：移除内部记录、结束读取端，并使仍空闲的发送端进入错误状态，
从而让 `writer.closed` 也能结束等待。重复关闭不再改变结果；关闭后写入被拒绝。
主动关闭不是向远端发送 UDP EOF，UDP 协议本身没有这种信号。

发送端自己的正常 `writer.close()` 仍成功；`writer.abort(reason)` 保留原始 reason，
写入异常也保留原始错误，不被统一的“连接已关闭”错误覆盖。适配器无法撤销已经
交付的 IP 分片。这些是宿主 JavaScript 流的生命周期语义，不是 Linux socket
`shutdown` 的替代实现。

三个空闲发送端挂起场景在修复前均已复现。distro `f39bc66` 的 8 项私网宿主回归
以及隔离打包运行通过，联合 Fetch 与报告门禁共 37 项通过，类型检查通过。
新增真实浏览器用例覆盖显式关闭、整个网络关闭、读取取消、正常发送端关闭和
带原始原因的中止；套件强制清单增至 16 项，结果待 CI 验证。网络脱离使用同一
清理函数，但本轮不启动 Linux，不把共用函数当作机器退出路径已端到端验证。
