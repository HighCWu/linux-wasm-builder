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

两项轻量检查已通过：验证 shell 和三个 JavaScript 模块的语法，以及 wasm64
覆盖层的依赖选择；Node 只解析模块，不执行 qjs:std/qjs:os，不是 QuickJS 运行证据。
固定 `5187e55` 的 [wasm32](https://github.com/HighCWu/distro/actions/runs/39060535971)
和 [wasm64](https://github.com/HighCWu/distro/actions/runs/39060531254) 目标检查正在
公开 CI 中运行，尚待实际编译、ABI 门禁和运行结果。当前入口为 Node
安装系统检查，不作为浏览器运行、OPFS 持久化或完整发行版迁移成功的证据。

## 许可证材料

包安装 QuickJS 的原始 MIT LICENSE、musl COPYRIGHT 和 compiler-rt 的原始
LICENSE.TXT，运行用例要求这些文本非空。上游固定版本的 LICENSE 已核对为 MIT；
项目自有集成和测试采用 MIT，运行库保持其原许可证（包括 LLVM exception）。
这些文本不能替代完整依赖审计或 Linux 对应源码交付；新增包不把 Linux 内核实现
链接进用户程序，也不改变开发者在平台上自由选择软件许可证的原则。
