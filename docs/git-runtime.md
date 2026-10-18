<!-- SPDX-License-Identifier: MIT -->

# Git 安装系统与 wasm64 接入

distro `7967691` 在既有 Git 2.55.0 配方上增加显式 `git-wasm64`，保持默认
`git` 为 wasm32。64 位变体选择匹配的 stdenv、平台、BusyBox、zlib、curl、
OpenSSL 和 Linux 运行检查器；CA 证书数据复用原配方，不混用 32 位静态库。

两个位宽都在安装后读取 `/usr/bin/git` 和独立的
`/usr/libexec/git-core/git-remote-http` 实际字节，要求单一、匹配位宽的共享
`env.memory` 导入及平台内存上限。这是声明检查，不证明实际分配了上限容量。

## 运行检查

复用原有三组安装系统语料，不另写更弱的 64 位替代测试：

- `workflow`：提交、差异、分支、快进、冲突合并、标签、对象读回、hook 和 pager。
- `packing`：24 次提交、对象往返、双线程 repack、严格 fsck、gc 和打包后历史读回。
- `remote`：AF_UNIX credential cache 的存取/退出，以及通过 Linux loopback TCP
  和 BusyBox httpd 进行 dumb HTTP 发现、clone、对象与提交一致性检查。

重型构建和实际 Linux/Wasm 运行只在公开 GitHub Actions 执行，例如：

```sh
gh workflow run ci.yml --repo HighCWu/distro --ref codex/mmap-initialized-backing \
  -f heavy-check=git-wasm64-check-workflow
```

另有 `git-wasm64-check-packing`、`git-wasm64-check-remote`；默认 32 位对应
`git-check-workflow`、`git-check-packing`、`git-check-remote`。

新增三项宿主契约检查验证依赖选择、已安装二进制检查和共享语料接线；与 libcurl
开发包/Python 根盘相关检查合计 17 项通过，格式、工作流和仓库检查通过。
这些不是目标运行证据。首次 wasm64 workflow 与新增 ABI 门禁后的 wasm32
workflow 已提交 CI，均固定 `7967691`：
[wasm64](https://github.com/HighCWu/distro/actions/runs/39086333120)、
[wasm32](https://github.com/HighCWu/distro/actions/runs/39086335957)。结果待验收；
packing、remote 的后续验收见下文。
本阶段也未增加 Git 浏览器用例。

## 选定许可材料的安装检查

`1c0ba14` / `f9da168` 为两个位宽安装 `/usr/share/licenses/git`，保存原始
Git COPYING、SHA-1 collision-detection 与 reftable 许可证，以及六份 bundled
regex 源文件中的原始声明。另保存默认 posix_spawn 补丁、说明和检查工具 MIT
文本，并从实际链接的 curl 输出复制 libcurl、zlib、OpenSSL、musl、compiler-rt
及 libcurl 集成的选定声明。原始输入字节不被修改，清单覆盖安装文件。

三组 Linux 运行语料均先要求这份材料非空且校验匹配。新增四项宿主检查执行
实际安装脚本、逐项输入缺失/为空和安装后缺失/为空/篡改负向控制，并验证
BusyBox 校验命令；加上既有位宽契约共七项通过。配套 shellcheck、shfmt、Nix
格式、工作流和仓库检查通过。这不是目标安装或法律充分性的证明。

新版 wasm64 packing 和 wasm32 remote 已提交 CI；此前仍运行的 `7967691`
双位宽 workflow 不含这套材料门禁，不取消或重启，也不以其结果替代新版证据。
wasm64 remote 仍待另行验收。

这些是选定声明和默认补丁，不是完整对应源码。自定义 derivation overrides
必须另收集自己的修改；未自动推断所有依赖、许可证兼容性或发布资格。
特别是 `NO_OPENSSL` 只关闭 Git 的直接 OpenSSL 调用，libcurl 仍静态链接
OpenSSL；这里不为 Git 授予或推定 OpenSSL 例外，发布前须单独审查该组合。

## 保留的边界

生产内核仍为 `CONFIG_MMU=n` 和有界 direct linear memory，不加入内核 softmmu。
Git 继续使用上游 `NO_MMAP` 的读取/复制替代路径；私有匿名 mmap 不满足其对象和
索引的文件映射需求。进程启动继续使用既有 `posix_spawn` 补丁，不声称支持普通
fork；后台 daemonize 仍明确失败。上述 HTTP 检查不证明公共网络、HTTPS、SSH
传输或任意远程托管服务已经兼容。

Git 及其静态依赖保留各自实际许可证，不能把 Git 二进制或整套系统称为 MIT。
新增宿主测试采用 MIT，不改变 Git 补丁的上游许可边界。本阶段未完成 Git 的完整
对应源码包、链接许可审查或长期二进制发行，不能据运行检查推断发布义务已经满足。
