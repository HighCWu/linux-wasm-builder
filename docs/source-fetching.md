<!-- SPDX-License-Identifier: MIT -->

# 固定 Linux 源码的获取

多项独立 Actions 在 `github.com/HighCWu/linux/archive/<commit>.tar.gz` 下载阶段遇到
HTTP 429；另一些相同 pin 的任务能正常编译。因此下载失败不能作为系统语义失败，
也不应取消已经运行的编译任务。

distro `50af862` 的 `distro/linux/fetch-source.nix` 改用 Nix fetchzip，按顺序尝试：

1. GitHub 的 `codeload.github.com` tar.gz 端点。
2. 原 `github.com` archive 地址。

保持完整 40 位 commit、原解包内容哈希和 `stripRoot`。任一地址返回不同内容都会被
Nix 拒绝，不能因为后备地址可用而更新或放宽哈希。没有新增第三方镜像、访问凭据、
付费服务或本地重型构建。直连端点不能保证消除 GitHub 服务端的全部限流或网络错误。

`linux-check-source` 是独立 Actions 检查，只获取、解包、验证哈希并检查基本源码文件，
不依赖 LLVM 或内核编译。可能命中已有内容缓存；仅检查成功不证明这次实际访问了
哪一个地址，必须查 source builder 日志再作网络层结论。固定 `50af862` 的
[首次公开检查](https://github.com/HighCWu/distro/actions/runs/39001858496) 已成功；实际日志
确认尝试 codeload、下载并解包归档，随后完成 source check，原内容哈希未改变。
这是一次实际获取验证，不是对未来不会再限流的保证。

新增获取配方与 package.nix 一同进入 `linux-build` 和 SHA256SUMS，发布物检查会逐字节
比较材料；空配方必须失败。宿主构建材料/源码包检查 7 项通过，pin 解析检查 3 项通过。
配方与相关集成修改使用 MIT，不改变 Linux 本身的许可证、源码 revision 或运行语义。

## 轻量内核函数检查的单文件获取

主仓库 `5d5988a` 为 named semaphore 宿主函数检查增加单文件后备下载。
CI 从 HEAD 的 Linux gitlink 取得完整 40 位提交，先请求 raw 地址；网络错误、
HTTP 错误或空内容时，再用 GitHub Contents API 请求同一文件、同一提交的原始内容。
不退回移动分支、本地文件或旧缓存；两个来源均失败则检查失败，下载成功后仍须
通过原有实际函数测试和反向控制。此路径不是 Nix 完整源码包的哈希校验替代品。

API 可使用该步骤的只读 GitHub token，raw 请求不携带凭据；禁止自动重定向，
避免 API Authorization 被转发。成功获取前不写入目标文件，不记录 token。
七项宿主回归验证精确 URL/pin、凭据范围、429 后备、无凭据的公开请求、双来源
失败、空内容拒绝和重定向拒绝。真实本地轻量下载已在 raw 不可用时走通 API，
随后原有函数检查及反向控制通过；不需要本地编译 Linux 或 LLVM。
固定 `5d5988a` 的[公开 CI](https://github.com/HighCWu/linux-wasm-builder/actions/runs/39058971480)
现已全部成功，包含该下载/函数检查及后续轻量套件；尚不据此声称此次 CI 实际命中
后备端点。只有直接检查该次下载日志才能判断使用了哪个来源。
代码采用 MIT，下载的 Linux 测试输入保留其原许可证，不进入用户程序或 SDK。
