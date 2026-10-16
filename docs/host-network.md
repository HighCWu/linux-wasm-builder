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
带原始原因的中止；套件强制清单增至 16 项。
[38932191496](https://github.com/HighCWu/linux-wasm-builder/actions/runs/38932191496)
已在 Chromium/Firefox 均通过，要求全部指定用例执行成功、零跳过、零重试。
网络脱离使用同一清理函数，但本轮不启动 Linux，不把共用函数当作机器退出路径
已端到端验证。

## 临时端口分配

TCP 与 UDP 的宿主端口共用每个私网实例的轮询游标，各自仍以连接元组检查占用。
候选范围是闭区间 49152–65535，共 16384 个端口。游标到上界后返回下界；完整
扫描一圈仍无空闲候选才报告耗尽，失败扫描后游标回到其原始位置。

distro `92fe7fc` 修复原扫描少尝试一个候选的问题。此前仅剩游标前一个端口空闲时
会误报耗尽；这不限于端口 65535。现提取同一生产分配函数供轻量回归直接执行，
不靠构造上万条真实流来测试边界。5 项测试覆盖最后候选、完整耗尽且无重复扫描、
释放后重用、两轮完整环绕及不同网络的独立游标；修改前其中 3 项复现失败，修改后
全通过。与 UDP 生命周期回归合计 13 项通过，类型检查通过；它不证明万连接负载
下的吞吐、内存占用或 Linux 实际端口耗尽行为。

## IPv4 接收头部校验

distro `5b86f1c` 将私网接收路径的 IPv4 解析提取为内部模块，并在重组或 TCP/UDP
分发前校验整个 IPv4 头的一补和，包括 IHL 指定的 options。当前 virtio-net 仅声明
MAC 特性，没有协商校验和卸载；不能把头部完整性验证交给一个未声明的卸载路径。
校验失败直接丢弃该帧，不发送传输层响应。仍按 IP total_length 排除 Ethernet
padding；IP 头部校验不包含正文，也不是 TCP/UDP 校验和验证、加密或身份认证。

7 项轻量回归使用已知校验向量、损坏字段和 options、奇数长度正文、空包、带偏移
的数组/Buffer 视图、截断及分片边界。临时移除校验拒绝条件时，两项损坏头部测试
复现失败；启用后全部通过，联合端口与 UDP 生命周期测试共 20 项通过，类型检查
通过。这些结果只证明解析器及宿主流回归，不代表完整 IPv4 重组或 Linux 网络验证。

Chromium/Firefox 独立套件新增已知头部与 options 校验场景，强制清单增至 17 项；
现已通过
[38936126298](https://github.com/HighCWu/linux-wasm-builder/actions/runs/38936126298)
验证：两个浏览器的实际测试与报告门禁、整个工作流均成功，17 项指定用例全部执行、
零跳过、零重试。对应轻量
[CI](https://github.com/HighCWu/linux-wasm-builder/actions/runs/38936126013)也通过。
[38935879332](https://github.com/HighCWu/linux-wasm-builder/actions/runs/38935879332)
在两个浏览器各执行了原有 16 项，全部通过，但准备目录漏拷贝新增 IPv4 测试文件，
17 项报告门禁正确拒绝通过；这不是新增解析器浏览器用例的执行结果。根仓库
`f332fef` 改为收集全部本地 `*.spec.js`，并增加轻量收集契约检查，重新运行验证。
测试入口仅在测试 bundle 导出内部解析器，不增加公开 SDK API。
distro `f1db621` 同时新增 `linux-guest-package-check-tests-networking` 定向公开检查，
复用原有 Linux 网络程序测试，覆盖 TCP 双向传输和背压、UDP 及最大长度数据报、
本地宿主桥接和运行实例之间的通信；它用于验证接收校验不会破坏正常 Linux 流量。
当前为 wasm32 系统与 Node 宿主，
[38935867946](https://github.com/HighCWu/distro/actions/runs/38935867946)
已失败，失败阶段正在核查；不能将其表述为实际 Linux 网络通过，也不能仅凭工作流
状态判定是 IPv4 校验回归。该检查不替代 wasm64 或浏览器网络端到端检查。
