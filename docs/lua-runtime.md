<!-- SPDX-License-Identifier: MIT -->

# Lua 双位宽用户态与异常展开验证

distro `3bdb90c` 在现有 Lua 5.4.8 移植上增加独立 `lua-wasm64`，不改变默认
wasm32 包、软件源或最小根盘。工具链、musl、compiler-rt、BusyBox、平台参数及
安装系统测试运行器均显式选择对应 wasm64 版本。

## 实际目标检查

两种位宽共用完整的 `distro/lua/language-test.sh`，不只验证解释器能打印版本号：

- Lua 模块默认搜索路径、require、算术、字符串、表和文件写入/读回。
- 两种指针宽度均使用 Lua 标准 64 位整数；检查超出浮点精确范围的整数、上下限和
  8 字节 pack/unpack 往返。
- 协程 yield/resume、pcall 字符串及表对象异常；异常展开时 `<close>` 资源逆序
  清理并保留错误对象身份，以及关闭挂起协程时清理仍存活的资源。
- os.execute 的非零状态、io.popen 输出与关闭，缺失共享模块显式失败。
- 目标 luac 生成普通及去调试信息的 core/coroutine 字节码，并由同一目标 lua
  重新运行全部断言；非法源码和截断字节码必须失败。

每次构建均对 lua、luac 检查实际 Wasm 位宽、唯一共享 env.memory 导入及平台
内存上限；最终运行标记只有在全部语料和许可证文本检查通过后才输出。
Lua 使用工具链已有的 SjLj lowering；本项不改内核、musl、执行 ABI 或 fork 约束。
字节码只承诺本次同架构、同版本往返，不声称可以跨位宽或跨 Lua 版本分发。

重型构建及 Linux 运行仅在公开 Actions 执行：

```sh
nix build './sources/distro#checks.x86_64-linux.lua-check-language'
nix build './sources/distro#checks.x86_64-linux.lua-wasm64-check-language'
```

## 宿主验证与证据边界

轻量检查命令需要原生 Lua 5.4 和 luac：

```sh
node --test sources/distro/distro/lua/language-host.test.js
```

可用 `LUA_HOST_INTERPRETER`、`LUA_HOST_COMPILER` 指定绝对路径。本地使用官方
Lua 5.4.8 源码原生构建，下载归档 SHA-256 与官方目录公布的
`4f18ddae154e793e46eeab727c59ef1c0c0c2b744e7b94219710d76f530629ae` 一致。
完整语料执行和依赖/语法接线两项检查通过；CI 宿主使用 Ubuntu 的 Lua 5.4 包，
不把该包的版本误称为目标的 5.4.8。

宿主检查只调整隔离临时路径、命令查找和 PID 1 停机循环。模块路径通过环境
显式设置，许可证文件使用测试占位文本；因此不证明目标默认路径、许可证包
内容或软件安装成功。它保留实际 Lua 断言、进程调用和 luac 编译执行，不模拟
解释器结果，但原生 setjmp/longjmp 仍不证明 Wasm SjLj 正确。

固定 `3bdb90c` 的
[wasm32](https://github.com/HighCWu/distro/actions/runs/39061282695) 和
[wasm64](https://github.com/HighCWu/distro/actions/runs/39061286995) 安装系统检查
已通过计划解析、进入重型构建，尚待实际结果。不过同期 QuickJS 目标日志暴露
共用的许可路径错误：包内 `/share/licenses` 不会被安装工具添加 `/usr` 前缀。
`d06effa` 已一并修正 Lua 脚本并增加直接执行实际复制/检查片段的两项跨包回归，
旧 `3bdb90c` 不包含修正，不能据其结果验收当前版本。固定 `d06effa` 的修正版
[wasm32](https://github.com/HighCWu/distro/actions/runs/39061566007) 和
[wasm64](https://github.com/HighCWu/distro/actions/runs/39061569694) 目标复验已提交，
尚待实际结果，未取消仍在运行的旧检查。
本轮尚未接入 Lua 的真实浏览器用例。现有静态库和头文件
安装保持不变，不据此宣称已验证任意 C 嵌入式消费者、动态模块或完整开发包重定位。

## 许可证材料

核对了固定 Lua 5.4.8 归档内 `doc/readme.html` 的 MIT 许可及原始
1994–2025 Lua.org、PUC-Rio 版权声明。包原样安装该 HTML、musl COPYRIGHT 和
compiler-rt LICENSE.TXT；自有测试和集成采用 MIT，依赖保持原许可证。
这些材料不是完整依赖审计，不改变 Linux 内核相应源码的交付义务，也不把内核
实现链接进用户程序。
