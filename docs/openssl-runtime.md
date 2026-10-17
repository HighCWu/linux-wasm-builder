<!-- SPDX-License-Identifier: MIT -->

# OpenSSL 双位宽用户态与证书验证

distro `25d3789` 为既有 OpenSSL 3.5.7 移植增加独立 `openssl-wasm64`。
默认 `openssl` 仍为 wasm32，不改变最小根盘或默认软件源。两种位宽共用固定来源、
移植补丁和完整 CLI 测试，分别选择对应 stdenv、musl、compiler-rt、BusyBox 与
Linux 测试运行器。Configure 使用 `linux-generic32` 或 `linux-generic64`，采用
对应 C 整数模型和纯 C 密码实现，不把 32 位构建改名当作 64 位包。

## 产物与范围

包提供 `openssl`、静态 `libssl.a`/`libcrypto.a`、头文件及 `/etc/ssl/openssl.cnf`。
系统 CA 材料来自独立的 ca-certificates 包，默认路径为 `/etc/ssl/cert.pem`。
构建阶段检查 CLI 和两个独立 C 消费者的实际 Wasm 位宽、唯一共享 env.memory
导入及匹配的平台内存上限。

继续禁用共享库/DSO、动态 engine、基于上下文切换的 async、AF_ALG engine、
fork HTTP/OCSP 服务及 secure-memory arena。不改变内核或直接线性内存模型。
已有有界匿名 mmap 不等于提供 mlock 或页保护；普通堆回退不能称为受保护的
secure arena。此项不启用上述能力，也不声称密码实现经过独立安全审计。

## 目标检查

安装系统内执行共用 `openssl/tests/cli-test.sh`，依次检查：

- 固定版本、默认配置/CA 路径和随包许可材料。
- SHA-256 已知向量、随机字节输出形状、P-256 密钥、自签证书生成及验证。
- 原有内存 BIO TLS 握手消费者和双向应用数据；该消费者本身不校验证书。
- 新增独立 `verified-handshake`：显式信任临时证书，以 SAN 校验 localhost，
  限定 TLS 1.3，双向精确传输包含 NUL/高位字节的内容。
- 新上下文不装入信任锚时，必须以 `DEPTH_ZERO_SELF_SIGNED_CERT` 拒绝；信任
  证书但主机名错误时，必须以 `HOSTNAME_MISMATCH` 拒绝，不能用任意失败顶替。

仅在全部检查成功后输出完整阶段及最终 pass。消费者正常退出，不作为 PID 1；
测试脚本负责检查退出码和完整阶段。以上握手均使用内存 BIO，没有外部网络，
不证明浏览器网络代理、公共站点 HTTPS、系统 CA 链、吊销检查或生产 TLS 策略。
CA 包的路径/非空检查不等于实际完成公共信任链验证。

重型编译及 Linux 运行只在公开 GitHub Actions 执行：

```sh
nix build './sources/distro#checks.x86_64-linux.openssl-wasm64-check-cli'
nix build './sources/distro#checks.x86_64-linux.openssl-check-cli'
```

## 宿主证据与许可边界

轻量检查需要 GCC、Clang、pkg-config 和原生 OpenSSL 开发包：

```sh
node --test sources/distro/distro/openssl/tests/handshake-host.test.js \
  sources/distro/distro/vm-test/license-layout-test.js
```

五项检查通过：原生 GCC/Clang 均执行三个实际 TLS 场景；将证书验证或主机名检查
删除的变体均必须失败。另检查 wasm64 依赖/ABI 接线，以及直接执行三种运行包的
真实许可复制片段和许可检查，拒绝错误前缀、空文本。原生链接使用宿主开发库，
不把其版本误称为目标 3.5.7，也不作为 Wasm 密码实现或目标运行成功的证据。

已核对固定上游 `openssl-3.5.7` 的 `LICENSE.txt` 为 Apache-2.0，包原样携带该文件、
musl COPYRIGHT 和 compiler-rt LICENSE.TXT；新增自有消费者/测试采用 MIT 并携带
相应文本。不把 OpenSSL 或既有来源改为 MIT，不改变 Linux 的相应源码义务。
此处材料不是完整发布合规审计，也不是 SDK/程序的可重定位发布承诺。

固定 `25d3789` 的
[wasm64](https://github.com/HighCWu/distro/actions/runs/39063492740) 和
[wasm32](https://github.com/HighCWu/distro/actions/runs/39063496158) 公开 CI 均已
成功，实际日志确认 CLI 和两个静态库消费者的匹配位宽 ABI 门禁，以及完整
`OpenSSL: CLI defaults, entropy, digest, X.509 and verified TLS consumers complete`
阶段和最终 pass。脚本只有在三类证书验证场景及完整阶段检查通过后才输出该阶段；
不把它扩大为外网、浏览器或后续 curl TCP/TLS 检查的通过证据。OpenSSL
的浏览器接线由下述后续提交实现，不能将其它语言的浏览器检查当作本包的验收。

## 浏览器共享用例

`1823c91` 将双位宽 OpenSSL 接入浏览器运行套件，精确门禁从 18 项扩为 19 项。
`runtimeAssets` 只定义一份 CLI 脚本和内容集合：Node 安装系统检查与浏览器
initramfs 共用相同 OpenSSL、BusyBox、CA 材料和已安装静态库消费者，不为浏览器
换用弱化握手、不添加许可路径别名，也不重新构建一套测试专用 OpenSSL。

浏览器程序依次完成 CLI 检查和两个 C 消费者后，打印可信 TLS 1.3 二进制往返、
不受信任证书拒绝、错误主机名拒绝及完整完成阶段；Playwright 要求所有阶段和
最终 pass，拒绝 fail。每一条阶段缺失、下载失败、仅打印 pass 或报告漏项都由
宿主负向回归拒绝。复用用户控制台协议、双 CPU 启动、熵设备及关闭期判定，
不是调用浏览器的 WebCrypto/TLS API 执行这些密码运算。

相关原生 TLS、接线/许可、浏览器用例和运行器共 38 项本地检查通过。它们不证明
真实 Wasm 或浏览器执行。固定 `1823c91` 的 wasm64
[Chromium](https://github.com/HighCWu/distro/actions/runs/39063794108) 和
[Firefox](https://github.com/HighCWu/distro/actions/runs/39063798111) 公开 CI 均已通过
计划及派生解析、进入重型检查，实际运行尚待验收。wasm32 同样接线，但本轮
尚未提交其重型浏览器检查。

此镜像是可丢弃 initramfs，不经过软件包安装，也不包含浏览器网络代理或外部
TLS 服务。即使运行通过，也只证明该版本 Linux/Wasm 内的 CLI 和内存 BIO TLS
路径，不扩大为公共 HTTPS、磁盘持久化、软件升级或密码安全审计的证明。
