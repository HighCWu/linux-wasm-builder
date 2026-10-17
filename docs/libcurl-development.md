<!-- SPDX-License-Identifier: MIT -->

# libcurl 安装后开发包与普通 C 应用

`685b195` 把 curl CLI 之外的静态库接口接入 SDK：`curl.development` 和
`curl-wasm64.development` 提供独立、可复制的开发安装，不改变现有 curl 运行包
布局。开发安装包含匹配位宽的 curl、OpenSSL、zlib 头文件、静态归档、上游
pkg-config 元数据、完整依赖许可材料及 MIT 示例源码。

它不是完整、独立可搬移的编译器发行包：编译仍需匹配位宽的 SDK、libc sysroot
和工具链。也不等于已经实现动态链接或新增浏览器外网 TCP。

## 搬移与链接约束

构建保留上游 `Requires`、`Requires.private`、`Libs.private` 及版本，不用一串
手写 `-lcurl` 替代实际依赖图。元数据路径统一相对于 `pcfiledir`，已知运行时 FHS
标志也指向同一开发安装；未知绝对 include/library 路径、残留 Nix store 路径或
缺失的依赖元数据会使构建失败，不允许悄悄拿宿主库补齐。

实际消费者先复制整个开发安装、再改名，调用 SDK 的隔离 pkg-config 包装器获取
静态编译/链接标志，拒绝原安装或 store 路径泄漏。仅用复制安装中的 `fetch.c`
和匹配 SDK 编译，之后检查实际 Wasm 位宽、共享 `env.memory` 导入和平台内存上限。

公开 CI 使用的目标检查为：

```sh
nix build './sources/distro#checks.x86_64-linux.curl-wasm64-check-development'
nix build './sources/distro#checks.x86_64-linux.curl-check-development'
```

重型目标构建仍放在公开 GitHub Actions，本地不构建 LLVM、Linux 或根盘。
开发包内的 `share/doc/libcurl/examples/README.md` 提供应用构建与运行说明。

## 普通进程与运行验证

示例是普通 C 应用，回调将二进制响应写到 stdout，诊断写到 stderr，最后正常
返回；没有 PID 1 专用循环或测试协议。支持 file/HTTP/HTTPS，限制超时、关闭
代理和重定向、显式启用证书及主机名验证；本示例 HTTPS 固定 TLS 1.3。

外层 Linux 检查才有测试协议，先要求子进程正常退出并逐字节比较含 NUL、高位
字节的文件，再在真实回环 TCP 上检查：显式 CA 成功、默认 CA 成功、正确默认
信任不能掩盖显式错误 CA、正确 CA 不能掩盖错误主机名。每次请求新建/回收服务端，
监听就绪不靠 sleep；临时默认 CA 仅写入可丢弃检查系统，完成或失败时尝试恢复。

## 证据边界

相关本地回归共 48 项通过。元数据夹具验证搬移和静态依赖解析、缺失依赖不能
回退到宿主、未知路径在改写前被拒绝。GCC/Clang 使用真实宿主 libcurl 执行同一
C 示例和 TLS 检查，并拒绝关闭验证、关闭主机名检查及把错误 CA 换成正确 CA
的破坏变体；另检查缺失文件和参数错误的非零退出。

宿主 libcurl 不是目标固定版本，也不保证静态链接。宿主仅对默认 CA 那一次请求
显式传入临时 CA 文件，绝不修改宿主信任库；这不能证明目标编译出的默认路径。
复制真实开发包、目标静态链接、Wasm ABI 和目标默认信任仍需对应公开 CI 验收。
现有 curl CLI 的 20 项浏览器套件不包含这个 C 应用，不得替代其运行证据。

固定 `685b195` 的
[wasm64](https://github.com/HighCWu/distro/actions/runs/39067794350) 和
[wasm32](https://github.com/HighCWu/distro/actions/runs/39067797747) 公开检查均已通过
计划及派生解析，重型任务已启动或排队；真实构建与运行结果待验收。本轮尚未
将此 C 应用加入浏览器套件。

该示例不是完整 HTTP 客户端或生产 TLS 策略。HTTP 状态只报告，不自动转换成
传输失败；证书吊销、外部网络传输、持久化安装/升级和完整发布合规审计不在本轮
验收范围。自有示例/集成采用 MIT，第三方组件保持原许可证，用户程序不链接
Linux 内核实现代码；分发静态应用时仍需保留相应依赖声明与许可证材料。
