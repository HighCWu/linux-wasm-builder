<!-- SPDX-License-Identifier: MIT -->

# QuickJS 的双位宽原生用户态

本项推进 wasm64 的真实软件覆盖，而不是把浏览器宿主 JavaScript 引擎当作 Linux
用户程序。distro `5187e55` 在既有 QuickJS-ng 0.15.1 固定源码与移植补丁上增加
独立 `quickjs-wasm64`；原 `quickjs` 仍是 wasm32，不更改默认软件源或最小根盘。
它分别选择匹配的 stdenv、musl、compiler-rt、BusyBox、内核及安装系统测试运行器。

## 产物与运行用例

两种包均提供 qjs、qjsc 及原有头文件。构建后逐个检查两个程序的 Wasm 位宽、
唯一共享 env.memory 导入和平台声明内存上限，不能凭文件名判断架构。
qjsc 是目标 Linux/Wasm 程序，不是构建机工具；本检查只验证它生成非空 C 字节码
数组，不声称当前包提供完整的嵌入式开发归档库或原地 C 编译器。

双位宽复用既有 language-test.sh，不新增一份较弱的 wasm64 语料，覆盖：

- 算术、字符串、闭包、类、JSON、BigInt 与异常消息。
- 内建模块加载、标准文件写入/读回。
- os.exec 的成功、退出码、异步 waitpid、环境/cwd、标准流重定向及 fd 关闭。
- 缺失程序和不支持的凭据选项显式报错。
- os.Worker 的 pthread 入口及跨线程消息往返，Promise/async-await 与计时器。
- qjsc 实际运行及 C 数组生成，完整阶段标记与最终 pass。

继续使用原有 posix_spawn 方案，不恢复标准 fork，不改变内核、musl 或执行 ABI。
Worker 用例不证明所有 SharedArrayBuffer/Atomics 场景或任意线程取消语义。

## 构建与证据

公开 Actions 运行以下重型检查，本地不构建 Linux、LLVM 或完整根盘：

```sh
nix build './sources/distro#checks.x86_64-linux.quickjs-check-language'
nix build './sources/distro#checks.x86_64-linux.quickjs-wasm64-check-language'
```

轻量入口为：

```sh
node --test sources/distro/distro/quickjs/language-contract.test.js
```

三项 QuickJS 轻量检查已通过：验证 shell 和三个 JavaScript 模块的语法、wasm64
覆盖层的依赖选择，以及浏览器镜像复用完整脚本和匹配产物；Node 只解析模块，
不执行 qjs:std/qjs:os，不是 QuickJS 运行证据。
固定 `5187e55` 的 [wasm32](https://github.com/HighCWu/distro/actions/runs/39060535971)
检查已失败：实际日志确认 qjs、qjsc 编译及 wasm32 ABI 门禁均通过，安装系统随后
因测试查找错误的 `/usr/share/licenses/quickjs` 路径失败，未进入语言用例。
包实际安装在 `/share/licenses/quickjs`，转换安装时不添加 `/usr` 前缀。
同批 [wasm64](https://github.com/HighCWu/distro/actions/runs/39060531254) 也已失败，
实际日志同样确认两个程序编译及 ABI 门禁通过，随后停在错误的许可路径检查。

distro `d06effa` 修正脚本路径，移除浏览器镜像里掩盖此问题的 `/usr` 许可别名，
保留原样 payload。新增两项回归直接执行 QuickJS/Lua 包的实际许可证复制片段，
再执行真实运行脚本的许可检查；错误前缀及空材料必须失败。相关轻量检查（含 Lua、
共享运行器及浏览器接线）合计 29 项通过。固定 `d06effa` 已提交修正后的
[wasm32](https://github.com/HighCWu/distro/actions/runs/39061447730) 和
[wasm64](https://github.com/HighCWu/distro/actions/runs/39061451084) Node 复验，
均通过计划解析。wasm64 已成功，实际日志确认 qjs/qjsc 的共享 memory64 ABI
门禁通过，随后输出完整 `QuickJS: language, file I/O, spawn, Worker, timers and
bytecode generation verified` 阶段及最终 pass，验证修正后的安装系统路径确实可用。
wasm32 也已成功：两个程序的 ABI 门禁、同一完整阶段标记及最终 pass 均经实际
日志核对。两次运行固定 `d06effa`，不包含后续 Lua 多输出或运行器关闭期判定修正。

## 浏览器验证接入

distro `92830ef` 为 wasm32/wasm64 浏览器运行套件增加 QuickJS，精确报告门禁
从 15 个用例扩展为 16 个。临时 initramfs 放入同位宽 BusyBox、qjs、qjsc 和
许可证文本，以原封不动的 language-test.sh 为 init，使用共享的双 CPU 启动、
用户控制台协议、超时与关闭检查。它不通过浏览器宿主 JS 引擎执行测试语料。
浏览器断言同时要求完整 QuickJS 阶段标记、最终 pass 且没有 fail；缺失阶段标记、
仅 pass、混入 fail 或漏跑用例均会被轻量负向测试拒绝。

本轮相关轻量检查合计 25 项通过，包含共享运行器的失败与关闭路径；它们不证明
真实浏览器运行成功。固定 `92830ef` 已提交 wasm64 的
[Chromium](https://github.com/HighCWu/distro/actions/runs/39060951193) 和
[Firefox](https://github.com/HighCWu/distro/actions/runs/39060954362) 公开检查。
Chromium、Firefox 均已成功，实际日志确认 QuickJS 用例执行且完整 16 项通过；
精确 JSON 报告门禁确认零漏跑、零跳过和零重试。
它们仍使用带别名的旧
`92830ef`，即使成功也不能验证后续许可布局修正。wasm32 已接线，尚未提交本轮
浏览器重型检查。Node 入口仍是安装系统检查；浏览器入口是可丢弃的内存根盘，
二者均不作为 OPFS 持久化、包管理安装验证等价性或完整发行版迁移成功的证据。

后续 `108f20a` 加入两条 Lua 用例，将双位宽浏览器门禁扩为 18 项，同时保留修正
后的 QuickJS 许可路径（没有额外别名）。固定该版本的
[wasm64 Chromium](https://github.com/HighCWu/distro/actions/runs/39062203518) 和
[Firefox](https://github.com/HighCWu/distro/actions/runs/39062207326) 均已失败，实际日志
确认同一 Lua 开发包路径迁移门禁阻止镜像构建，尚未启动浏览器；旧 16 项成功不能
替代此版本验收。修正及后续复验见 [Lua 运行记录](lua-runtime.md)。

`5eca882` 后续修正 Node/浏览器运行器在 pass 后漏记控制台失败的问题，强化到
设备关闭后才最终判定。固定该提交的
[wasm64 Node](https://github.com/HighCWu/distro/actions/runs/39062624048) 已成功，
实际日志确认两个程序 ABI、完整功能阶段及最终 pass；这次运行包含加强后的关闭
判定。完整 18 项 Chromium/Firefox 复验因上述 Lua 依赖构建失败，尚未进入浏览器，不能
把 Node 成功扩大为浏览器验收。

后续 `1823c91` 将 OpenSSL CLI/验证证书的 TLS 消费者纳入共享套件，当前精确
门禁为 19 项。含 Lua 开发包路径修正的新 wasm64 双浏览器检查已提交，待实际
结果；旧 16/18 项运行不能替代新套件的完整验收。

## 许可证材料

包安装 QuickJS 的原始 MIT LICENSE、musl COPYRIGHT 和 compiler-rt 的原始
LICENSE.TXT，运行用例要求这些文本非空。上游固定版本的 LICENSE 已核对为 MIT；
项目自有集成和测试采用 MIT，运行库保持其原许可证（包括 LLVM exception）。
这些文本不能替代完整依赖审计或 Linux 对应源码交付；新增包不把 Linux 内核实现
链接进用户程序，也不改变开发者在平台上自由选择软件许可证的原则。
