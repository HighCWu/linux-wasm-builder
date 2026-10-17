<!-- SPDX-License-Identifier: MIT -->

# curl 双位宽用户态与 Linux TCP HTTPS

distro `907f64d` 为既有 curl 8.21.0 移植增加独立 `curl-wasm64`，显式选择匹配的
stdenv、平台、OpenSSL、zlib、BusyBox 和安装系统测试运行器。新增 zlib wasm64
覆盖层，原有默认 wasm32 软件源和最小根盘不变。CLI 构建后检查实际 Wasm 位宽、
唯一共享 env.memory 导入及对应平台的声明内存上限。

## 传输与信任边界

curl 使用静态 OpenSSL 后端，zlib 支持内容编码；现有 file/明文 HTTP 检查继续保留。
不启用共享库、线程 DNS resolver、HTTP/2/3 或未提供的额外协议依赖。保留既有
无默认 CA 路径的构建配置；直接 HTTPS 必须显式指定可信 CA 文件，例如
`curl --cacert /path/to/ca.pem https://server.example/`。随镜像提供系统 CA 包不等于
curl 已默认选用它，不应使用 `--insecure` 来代替正确的信任配置。

新 `https` 检查在 Linux 内生成临时 EC 证书，运行单连接 OpenSSL `s_server`，
在回环 TCP 上完成 curl HTTPS，而不是调用宿主 Fetch 或 WebCrypto：

- 强制 TLS 1.3 与 HTTP/1.1，显式信任服务端证书，要求 HTTP 200、验证结果 0
  及预期服务端响应内容。
- 改用无关的 CA 文件，必须返回 curl 验证失败码 60，并有信任失败诊断。
- 保持正确 CA、改用不匹配的主机名，必须返回 60，并有主机名失败诊断。

`--resolve` 固定名称到 127.0.0.1，`--noproxy '*'` 禁止环境代理干扰；不依赖 DNS。
监听就绪通过 `/proc/net/tcp` 的 LISTEN 状态确认，不用探测连接消耗单次 accept，
也不以固定 sleep 猜测就绪。每次请求独立启动/回收服务端，连接及传输均有超时；
只有完整三阶段成功后输出最终 pass。临时证书根据当前 Linux 时钟生成，不依赖
固定 PEM 的有效期。此用例不使用 fork。

浏览器的 `hostFetchNetwork` 是另一条明文 HTTP 到宿主 HTTPS Fetch 的适配路径，
不是原始 TCP 或 TLS 隧道；这里的 Linux 回环 TLS 成功不能证明浏览器能连接任意
外网 TLS 服务、绕过 CORS、验证公共 CA 链或具有完整的生产 TLS 策略。
软件包集成脚本和原有测试注释已区分这两条路径，详见 [Fetch 边界](host-http.md)。

## 检查与证据

公开 GitHub Actions 执行目标编译和 Linux 运行，本地不构建 LLVM、Linux 或根盘：

```sh
nix build './sources/distro#checks.x86_64-linux.curl-wasm64-check-https'
nix build './sources/distro#checks.x86_64-linux.curl-check-https'
```

现有 `curl-check-transfers` 和新增覆盖层的 `curl-wasm64-check-transfers` 保留独立的
file/HTTP 用例；不因为 HTTPS 检查接线就宣称新 wasm64 file/HTTP 检查已经运行。
新增浏览器接线见下文；OpenSSL 内存 BIO 的浏览器用例不能代替 curl 的 TCP/TLS。

```sh
node --test sources/distro/distro/curl/tests/https-host.test.js \
  sources/distro/distro/vm-test/license-layout-test.js
```

六项本地检查通过。宿主用实际 curl/OpenSSL 运行同一脚本，仅调整隔离路径、
端口、Linux 初始化和 PID 1 停留；证书、服务端、TLS 请求及断言未换成模拟结果。
关闭验证、把错误 CA 改成正确 CA、把错误主机名改成 localhost 的变体均被拒绝。
另检查位宽依赖接线，并直接执行四种运行包的许可复制/检查片段，拒绝错误路径
与空材料。宿主版本不是目标固定版本，这些结果不证明 Wasm 编译、ABI 或目标
TCP/TLS 已验收。固定 `ecd3c1f`（功能 `907f64d` 加许可夹具格式整理）的
[wasm64](https://github.com/HighCWu/distro/actions/runs/39064447319) 和
[wasm32](https://github.com/HighCWu/distro/actions/runs/39064451129) HTTPS 公开 CI
均已通过计划及派生解析、进入重型检查，尚待编译和实际 Linux 运行结果。

## 浏览器共享用例

`aa28e76` 为双位宽运行套件新增 curl HTTPS 用例，精确门禁从 19 项扩为 20 项。
`runtimeAssets` 只定义一份脚本、内容集合与临时根盘；Node 安装系统检查和
浏览器共用同一完整 HTTPS 脚本及对应位宽的 curl、OpenSSL、BusyBox 和 CA 材料，
不为浏览器换成 mock HTTP 响应或弱化证书校验。

Playwright 要求可信 TLS 1.3 成功、不受信任证书拒绝、错误主机名拒绝、完整完成
阶段及最终 pass 全部出现，且不含 fail；每个阶段缺失、仅 pass、混入 fail、
下载失败与报告漏项均由负向回归拒绝。沿用双 CPU、熵设备及最终关闭期判定。
相关原生 TLS、依赖/许可、浏览器接线与运行器共 44 项本地检查通过，不等于
Wasm 或浏览器运行通过。已提交双位宽 Chromium/Firefox 四项新检查，均需实际
构建与运行验收，不将某一组合成功扩大为整个矩阵完成。

四项公开任务均已通过计划、进入重型检查：wasm64
[Chromium](https://github.com/HighCWu/distro/actions/runs/39065145729)、
[Firefox](https://github.com/HighCWu/distro/actions/runs/39065148975)，wasm32
[Chromium](https://github.com/HighCWu/distro/actions/runs/39065212445)、
[Firefox](https://github.com/HighCWu/distro/actions/runs/39065216582)。

主仓库固定 `00e8946` 的
[轻量 CI](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39064449263)
也已成功，实际日志确认宿主 curl TCP/TLS、关闭验证/负向接受变体拒绝、位宽接线
及许可布局回归；该 CI 仍不执行 Wasm 或浏览器中的 curl。

该根盘可丢弃，直接叠加包内容，不验证包管理安装、磁盘持久化或软件升级。
即使通过，TLS 两端仍是同一个浏览器内 Linux 的回环 TCP；不使用 Fetch 桥，
不证明外部原始 TCP/TLS、CORS 或公共信任链已可用。

## 许可证材料

curl 保留上游 curl 许可证，zlib、OpenSSL、musl 和 compiler-rt 保持各自许可证。
包原样携带 curl COPYING、包含原始许可的 zlib.h、OpenSSL LICENSE.txt、musl
COPYRIGHT 和 compiler-rt LICENSE.TXT；新增自有集成/测试采用 MIT 并携带文本。
不将依赖改为 MIT，也不改变 Linux 内核的相应源码义务。这些材料不是完整发布
合规审计，亦不声称已提供可重定位的 libcurl SDK 开发包。
