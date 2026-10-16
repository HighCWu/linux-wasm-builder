# SDK socket 运行验证

目标是让用 SDK 构建的软件使用标准 Linux socket 接口，而不是要求程序改用
JavaScript 网络 API。当前新增验证先隔离内核、musl 和 SDK ABI：在同一 Linux
运行实例内运行 Unix stream socketpair 及 IPv4 TCP 回环，不依赖外部服务器、
virtio-net、宿主代理或浏览器 Fetch。

## 共用用例

`sources/distro/distro/sdk/socket-example.c` 使用项目自有 MIT 许可，同一源码由
wasm32/wasm64 SDK 分别构建，覆盖：

- `SOCK_NONBLOCK`、`F_GETFL`，空接收返回 EAGAIN/EWOULDBLOCK。
- `poll` 和 `epoll_create1/ctl/wait`：初始无数据、可读、排空后不再可读。
- `epoll_event.data.u64` 保留 `9007199254740993`，不经 JavaScript 浮点数转换。
- 包含 NUL、高位字节的双向数据，允许短读/短写，处理 EINTR 和暂时不可读写。
- `shutdown(SHUT_WR)`、EPOLLRDHUP 和 EOF；半关闭后反方向仍能发送与接收。
- TCP 非阻塞 connect、poll 可写、`SO_ERROR`、内核分配端口与 `accept4`。

裸 initramfs 中的测试仅把自身 Linux 实例的 `lo` 接口置为 UP。原生宿主运行不
执行接口配置，只使用已有回环网络及内核分配的临时端口，不需要 root 权限。
每次等待有 5 秒限时，外层运行器也有 watchdog；最终通过标记在所有检查及关闭
描述符后输出。浏览器复用已有运行/关闭检查，不能在机器关闭失败时报告通过。

## 入口与证据

在已安装 Nix 的环境可执行：

```sh
nix build ./sources/distro#sdk-check-socket-runtime
nix build ./sources/distro#sdk-wasm64-check-socket-runtime
nix build ./sources/distro#browser-tests-check-memory64-chromium
```

重型构建在公开 GitHub Actions 执行，不在本机编译 LLVM 或 Linux。
浏览器 wasm32/wasm64 运行套件都加入同一 socket 用例，并把强制指定用例清单从
5 项扩为 6 项，缺失或跳过该用例不能通过门禁。

distro `5d6e68d` 的原生 GCC/Clang 严格编译及各 5 次运行通过；Wasm 条件分支也
通过宿主语法检查。15 项运行协议/关闭生命周期宿主回归通过。这些仅验证测试源码
和运行器，不是 Wasm 目标支持的证据。
[SDK wasm32](https://github.com/HighCWu/distro/actions/runs/38929881855) 与
[Chromium wasm64](https://github.com/HighCWu/distro/actions/runs/38929879587)
检查已完成 Nix 检查发现及求值，正在执行重型构建/运行，结果待确认。

## 边界

本用例不证明 UDP、DNS、外部 TCP、TLS、监听端口转发、跨实例网络或全部 epoll
边沿触发/单次触发语义。浏览器对任意原始网络连接仍有安全限制；外部网络路径
必须单独验证，见[宿主 HTTP 说明](host-http.md)。也不将一个运行实例内的回环通信
表述为浏览器已获得任意互联网 socket 能力。
