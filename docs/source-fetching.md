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
