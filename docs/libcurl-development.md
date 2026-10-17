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
[wasm32](https://github.com/HighCWu/distro/actions/runs/39067797747) 公开检查均失败于
开发安装的 `libcurl.pc` 路径校验；curl 本身已构建，但尚未执行普通 C 消费者编译、
ABI 检查和运行，不能归因为应用或 TLS 运行失败。旧日志未打印具体未识别路径。
该固定版本不含这个 C 应用的浏览器用例。

主仓库固定 `f5e5516` 的
[轻量 CI](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39067978082)
已成功，实际日志确认 Ubuntu 上 GCC/Clang 的真实 libcurl 示例、TLS 破坏变体、
元数据搬移与依赖缺失检查均执行；宿主库版本为原生环境提供的版本，不替代上述
Wasm 静态库与运行验收。

## 浏览器共享 C 应用

`2f75050` 将双位宽精确浏览器门禁从 20 项扩为 21 项。包的 `runtimeAssets` 仅定义
一份 C 应用初始化脚本和运行包集合，Node 安装系统检查与浏览器 initramfs 共用；
浏览器只加入同一个编译后的应用及 BusyBox、OpenSSL、CA 运行材料，不带开发
头文件、静态归档或工具链，不用 JavaScript Fetch 模拟 C 回调或 TLS。

Playwright 要求二进制文件回调/正常退出、显式 CA TLS 1.3、默认 CA、显式错误 CA
拒绝、错误主机名拒绝、完整完成标记及最终 pass 全部出现，且无 fail。每个阶段
缺失、仅 pass、混入 fail、根盘下载失败及报告漏项都有负向回归。

`c66e1a6` 的元数据处理补入已知 lib/include 路径的冗余斜杠支持、目录名边界检查和逐行
错误诊断；仍拒绝未知绝对路径，并在整组验证后才改写文件。新增回归覆盖单/双/三
斜杠、未知目录及失败不写入；这是待目标 CI 确认的修正，不声称已经查明旧失败
路径或通过 Wasm 构建。

固定 `c66e1a6` 的
[wasm64](https://github.com/HighCWu/distro/actions/runs/39070094997) 和
[wasm32](https://github.com/HighCWu/distro/actions/runs/39070098304) 开发包检查均已通过
计划及派生解析并进入隔离构建，目标构建和运行尚待验收。为避免重复提交已知失败，
新的四路浏览器 21 项矩阵暂待双位宽开发包验收，不沿用旧 20 项结果。

相关原生 TLS、元数据、共享接线、报告和关闭期运行器共 52 项本地检查通过，
不等于 Wasm 或真实浏览器通过。旧 20 项套件不含这个普通 C 应用，不能替代新
21 项的验收。该镜像是可丢弃的内存根盘，不验证安装升级或持久化；TLS 两端仍为
浏览器内 Linux 的回环 TCP，不增加外部原始 TCP/TLS 能力。

该示例不是完整 HTTP 客户端或生产 TLS 策略。HTTP 状态只报告，不自动转换成
传输失败；证书吊销、外部网络传输、持久化安装/升级和完整发布合规审计不在本轮
验收范围。自有示例/集成采用 MIT，第三方组件保持原许可证，用户程序不链接
Linux 内核实现代码；分发静态应用时仍需保留相应依赖声明与许可证材料。

## 定向构建的缓存位宽

`92284c2` 修正 CI 对 `memory64` 浏览器检查名的分类：缓存恢复/保存、源码材料
选择和重型输入保留共七处同时识别 `wasm64` 与 `memory64`。旧判断只识别前者，
会把 memory64 浏览器检查分到 wasm32 缓存；此修正不改变编译目标，也不把缓存
命中当作运行证据。主仓库六项轻量回归覆盖真实检查名及分类不一致的反向控制；
尚不声称测得构建提速。
