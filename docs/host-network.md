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
全部执行、零跳过、零重试。真实浏览器结果仍待 CI；不能把宿主测试当作浏览器
或 Linux 挂载、网络程序集成的证据。Linux socket ABI 的独立进展见
[SDK socket 说明](sdk-sockets.md)。
