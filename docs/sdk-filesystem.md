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
使用宿主 C++ 运行库，不证明 Wasm 的 libc++、musl 或内核已通过。固定 `52b6003` 的
[wasm32 SDK](https://github.com/HighCWu/distro/actions/runs/39057897448) 已成功，
实际 Node/Linux 日志确认完整文件系统完成阶段及 `::vm-test::pass`；
[wasm64 SDK](https://github.com/HighCWu/distro/actions/runs/39057893423) 也已成功，
实际 Node/Linux 日志同样确认完整阶段和 pass。双位宽 Node 的结果不替代浏览器验证。

## 浏览器集成

distro `e733bfb` 将相同 SDK 产物通过独立 `runtime-filesystem.cpio` 接入浏览器
运行套件，按位宽选择 SDK 和内核。既有共用运行器负责启动、结果与整机关闭，新增
用例要求完整文件系统阶段、用户控制台 pass 且无 fail。精确报告清单从 14 项增至
15 项，缺失、跳过或重试均不能作为通过。

新增宿主契约验证归档请求、下载失败传播，以及缺少完成阶段/通过标记或混入失败
记录必须拒绝。连同报告门禁和共享关闭生命周期共 39 项宿主检查通过。固定 distro
`e733bfb` 的 wasm64 [Chromium](https://github.com/HighCWu/distro/actions/runs/39058087980)
和 [Firefox](https://github.com/HighCWu/distro/actions/runs/39058091975) 均已成功：
实际日志包含此新增 C++ 文件系统用例，各 15 项通过，精确报告门禁确认零跳过、
零重试。此前 14 项套件不包含此程序；宿主检查不替代 Linux 在浏览器中的实际运行。
wasm32 旧版 14 项的两浏览器成功也不替代此新增程序；固定 `de86fb3` 的新版
[Chromium](https://github.com/HighCWu/distro/actions/runs/39059055736) 和
[Firefox](https://github.com/HighCWu/distro/actions/runs/39059060075) 独立补验均已成功：
实际日志包含新增 C++ 文件系统用例，各 15 项通过，精确报告门禁确认零跳过、
零重试。因此该程序已分别有双位宽 Node 与双位宽两浏览器的实际成功证据；
各自源码提交仍以上述固定版本为准，不泛化到后续变更。

测试只验证默认内核中的临时文件系统，不挂载 NodeFS/BrowserFS，不操作 OPFS，
不验证持久化、原子替换、跨文件系统移动、目录并发、文件 mmap 或完整 C++ 标准库。
独立宿主 virtio-fs 测试与此程序的 Linux VFS 路径不同，结果不能相互替代。

示例、集成和测试采用 MIT；libc++、musl、LLVM 和 Linux 保持各自原许可证。
这不是对任何第三方程序或任意依赖组合的兼容性、许可合规认证。
