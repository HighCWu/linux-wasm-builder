<!-- SPDX-License-Identifier: MIT -->

# SDK 的 C++ 文件系统消费验证

distro `52b6003` 增加 MIT `distro/sdk/filesystem-example.cc`。它通过公开
`wasm-linux-c++` 入口构建普通 C++17 程序，不调用私有系统调用，也不启用文件
mmap 实验。分别使用 wasm32/wasm64 SDK、对应默认内核和 raw initramfs 运行。

## 覆盖范围

- 创建唯一临时工作目录及子目录，以 ofstream 写入 65539 字节二进制内容。
- copy_file、已存在目标的错误、覆盖复制、rename 及 ifstream 逐字节核对。
- 硬链接等价性、相对符号链接解析，以及 dangling symlink 的 status 区分。
- last_write_time 设置/读回当前文件时钟加 3000000000 秒的时间，用普通 stat
  确认对应 Unix 秒数超过有符号 32 位范围；不改变系统时钟或实际等待。
- permissions、directory_iterator 的完整名称集合、error_code 及 filesystem_error
  的错误类别与路径信息。
- remove_all 精确清理七个对象，确认工作目录不存在。

程序会在失败时尽量清理唯一临时目录并输出 fail；成功时要求完整阶段和 pass。
Wasm init 在成功后保持运行，由已有验收运行器执行整机关闭；宿主程序正常退出。
临时路径与测试数据不应作为持久化 API 或生产文件布局使用。

## 构建与验证

在所需 SDK shell 中可直接构建：

```sh
nix develop './sources/distro#sdk-wasm64'
wasm-linux-c++ -std=c++17 -O2 -Wall -Wextra -Werror \
  sources/distro/distro/sdk/filesystem-example.cc -o filesystem.wasm
```

产物是 Linux/Wasm 程序，不能直接当作本机 ELF 执行。双位宽完整运行入口为：

```sh
nix build './sources/distro#checks.x86_64-linux.sdk-check-filesystem-runtime'
nix build './sources/distro#checks.x86_64-linux.sdk-wasm64-check-filesystem-runtime'
```

重型交叉构建和 Linux 执行交给公开 GitHub Actions；开发机轻量入口为：

```sh
node --test sources/distro/distro/sdk/filesystem-test.js
```

GCC/Clang 两项宿主检查已经通过，核对完整阶段、正常退出和临时目录清理；这些
使用宿主 C++ 运行库，不证明 Wasm 的 libc++、musl 或内核已通过。双位宽 SDK
公开检查已调度，尚待实际目标结果。当前还没有此程序的真实浏览器运行证据。

测试只验证默认内核中的临时文件系统，不挂载 NodeFS/BrowserFS，不操作 OPFS，
不验证持久化、原子替换、跨文件系统移动、目录并发、文件 mmap 或完整 C++ 标准库。
独立宿主 virtio-fs 测试与此程序的 Linux VFS 路径不同，结果不能相互替代。

示例、集成和测试采用 MIT；libc++、musl、LLVM 和 Linux 保持各自原许可证。
这不是对任何第三方程序或任意依赖组合的兼容性、许可合规认证。
