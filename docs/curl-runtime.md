<!-- SPDX-License-Identifier: MIT -->

# curl 双位宽用户态与 Linux TCP HTTPS

distro `907f64d` 为既有 curl 8.21.0 移植增加独立 `curl-wasm64`，显式选择匹配的
stdenv、平台、OpenSSL、zlib、BusyBox 和安装系统测试运行器。新增 zlib wasm64
覆盖层，原有默认 wasm32 软件源和最小根盘不变。CLI 构建后检查实际 Wasm 位宽、
唯一共享 env.memory 导入及对应平台的声明内存上限。

## 传输与信任边界

curl 使用静态 OpenSSL 后端，zlib 支持内容编码；现有 file/明文 HTTP 检查继续保留。
不启用共享库、线程 DNS resolver、HTTP/2/3 或未提供的额外协议依赖。当前配置
默认读取发行版证书包 `/etc/ssl/cert.pem`，不把构建机或 Nix store 路径编入默认
信任配置；可用 `--cacert /path/to/ca.pem` 显式覆盖。此前 `907f64d`/`aa28e76`
仍无默认 CA 路径，仅验证了显式指定 CA 的请求。新默认配置的双位宽 Linux 检查
已通过，浏览器检查另行验收；
不应使用 `--insecure` 来代替正确的信任配置。

新 `https` 检查在 Linux 内生成临时 EC 证书，运行单连接 OpenSSL `s_server`，
在回环 TCP 上完成 curl HTTPS，而不是调用宿主 Fetch 或 WebCrypto：

- 强制 TLS 1.3 与 HTTP/1.1，显式信任服务端证书，要求 HTTP 200、验证结果 0
  及预期服务端响应内容。
- 改用无关的 CA 文件，必须返回 curl 验证失败码 60，并有信任失败诊断。
- 保持正确 CA、改用不匹配的主机名，必须返回 60，并有主机名失败诊断。

`--resolve` 固定名称到 127.0.0.1，`--noproxy '*'` 禁止环境代理干扰；不依赖 DNS。
监听就绪通过 `/proc/net/tcp` 的 LISTEN 状态确认，不用探测连接消耗单次 accept，
也不以固定 sleep 猜测就绪。每次请求独立启动/回收服务端，连接及传输均有超时；
只有完整验证流程成功后输出最终 pass。临时证书根据当前 Linux 时钟生成，不依赖
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
file/HTTP 用例；后续 `81e776d` 的 wasm64 file/HTTP 也已实际通过，记录见下文。
新增浏览器接线见下文；OpenSSL 内存 BIO 的浏览器用例不能代替 curl 的 TCP/TLS。

```sh
node --test sources/distro/distro/curl/tests/https-host.test.js \
  sources/distro/distro/vm-test/license-layout-test.js
```

首轮六项本地检查通过。宿主用实际 curl/OpenSSL 运行当时同一脚本，仅调整隔离路径、
端口、Linux 初始化和 PID 1 停留；证书、服务端、TLS 请求及断言未换成模拟结果。
关闭验证、把错误 CA 改成正确 CA、把错误主机名改成 localhost 的变体均被拒绝。
另检查位宽依赖接线，并直接执行四种运行包的许可复制/检查片段，拒绝错误路径
与空材料。宿主版本不是目标固定版本，这些结果不证明 Wasm 编译、ABI 或目标
TCP/TLS 已验收。固定 `ecd3c1f`（功能 `907f64d` 加许可夹具格式整理）的
[wasm64](https://github.com/HighCWu/distro/actions/runs/39064447319) 和
[wasm32](https://github.com/HighCWu/distro/actions/runs/39064451129) HTTPS 公开 CI
均已成功。实际日志确认匹配位宽的 curl 构建及三个 TLS 阶段和最终 pass，
证明 Linux 回环 TCP 的显式 CA 路径；不包含后加的默认 CA 流程。

## 默认 CA 配置与失败边界

`81e776d` 的默认路径与现有 `ca-certificates` 包安装位置一致，file/HTTP 检查也要求
`curl-config --ca` 返回此路径且文件非空。HTTPS 用例先清除客户端/SSL 信任
环境变量，再要求实际元数据路径匹配，按下列顺序执行：

1. 原发行版公共 CA 包不能信任本次新生成的自签名证书，要求错误 60。
2. 在可丢弃根盘中临时放入对应证书，不带 `--cacert` 的请求必须成功且验证结果为 0。
3. 默认包换为无关 CA，请求必须以错误 60 拒绝。
4. 无关默认包存在时，显式正确 CA 必须覆盖它并成功；正确默认包存在时，
   显式错误 CA 仍必须拒绝，不得默默回退到默认信任。
5. 保持显式正确 CA，错误主机名必须拒绝；默认包缺失且无显式 CA 时要求错误 77。
6. 恢复并逐字节核对原证书包，全部成功后才允许最终 pass。

临时 CA 不写入发布产物。正常退出、失败和信号处理均尝试恢复原包并回收服务端，
浏览器测试复用同一脚本并逐项要求新增阶段，不只匹配旧完成标记。

相关 44 项本地检查通过。真实宿主 curl/OpenSSL 执行信任选择，并拒绝关闭验证、
忽略默认信任、接受错误默认/显式 CA、忽略显式覆盖、接受错误主机名及缺失默认包
仍成功等 7 个破坏变体。宿主测试使用临时证书包副本和 `CURL_CA_BUNDLE`，
不修改宿主系统信任库，也不声称验证了目标编译出的默认路径；该路径另由公开
Wasm CI 验收。此变更不增加外网传输、DNS、证书吊销或完整生产 TLS 策略支持。

固定 `81e776d` 的新
[wasm64 HTTPS](https://github.com/HighCWu/distro/actions/runs/39066090311)、
[wasm32 HTTPS](https://github.com/HighCWu/distro/actions/runs/39066093854) 与
[wasm64 file/HTTP](https://github.com/HighCWu/distro/actions/runs/39066097410)
公开检查均已成功，实际日志确认双位宽默认信任的全部阶段及恢复、最终 pass；
wasm64 file/HTTP 检查也完成了真实目标构建和 Linux 运行。
固定 `aa28e76` 的四项浏览器任务仍使用旧显式 CA 脚本，不能证明新默认阶段。
固定 `81e776d` 的新 wasm64
[Chromium](https://github.com/HighCWu/distro/actions/runs/39067035351) 和
[Firefox](https://github.com/HighCWu/distro/actions/runs/39067038837) 已另行提交并通过
计划及派生解析，实际浏览器结果待验收；此版未提交 wasm32 浏览器重型检查。

## 浏览器共享用例

`aa28e76` 为双位宽运行套件新增 curl HTTPS 用例，精确门禁从 19 项扩为 20 项。
`runtimeAssets` 只定义一份脚本、内容集合与临时根盘；Node 安装系统检查和
浏览器共用同一完整 HTTPS 脚本及对应位宽的 curl、OpenSSL、BusyBox 和 CA 材料，
不为浏览器换成 mock HTTP 响应或弱化证书校验。

Playwright 要求可信 TLS 1.3 成功、不受信任证书拒绝、错误主机名拒绝、完整完成
阶段及最终 pass 全部出现，且不含 fail；每个阶段缺失、仅 pass、混入 fail、
下载失败与报告漏项均由负向回归拒绝。沿用双 CPU、熵设备及最终关闭期判定。
相关原生 TLS、依赖/许可、浏览器接线与运行器共 44 项本地检查通过，不等于
Wasm 或浏览器运行通过。后续公开 CI 的运行证据另列如下。

固定 `aa28e76` 的四项公开任务均已成功：wasm64
[Chromium](https://github.com/HighCWu/distro/actions/runs/39065145729)、
[Firefox](https://github.com/HighCWu/distro/actions/runs/39065148975)，wasm32
[Chromium](https://github.com/HighCWu/distro/actions/runs/39065212445)、
[Firefox](https://github.com/HighCWu/distro/actions/runs/39065216582)。
实际日志确认 curl 用例执行，各自完整 20 项通过，严格报告零跳过/重试。
这四项仍只包含旧显式 CA 脚本，不自动覆盖 `81e776d` 的新增默认信任阶段。

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
合规审计。后续独立开发包及普通 C 应用的接入、验证与限制见
[libcurl 开发记录](libcurl-development.md)，不把 CLI 成功当成库接口已经验收。
