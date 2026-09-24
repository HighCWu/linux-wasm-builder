<!-- SPDX-License-Identifier: MIT -->

# 贡献指南

## 许可证边界

提交前必须先确定变更所属组件，不能把一个组件的许可证假设套到另一个组件。

| 位置 | 新增代码的默认许可证 | 原因 |
|---|---|---|
| 本集成仓库、独立 runtime、宿主、测试和文档 | MIT | 便于社区与商业场景广泛复用 |
| `sources/musl` | MIT | 与 musl 上游保持一致 |
| `sources/distro` 中项目自有 TS/JS/Nix | MIT，除非原文件另有声明 | 保持宿主层宽松许可 |
| `sources/llvm-project` | Apache-2.0 WITH LLVM-exception | 必须服从 LLVM 项目许可与贡献规则 |
| `sources/linux` | 文件现有 SPDX，通常 GPL-2.0-only | Linux 派生修改无法改为 MIT |

以下做法禁止合入：

- 把 Linux GPL 实现代码复制到 MIT runtime、musl、LLVM 或非 GPL 用户态支持库。
- 删除或弱化第三方版权、SPDX、NOTICE 或 source-offer 义务。
- 在没有来源和许可证记录的情况下从 Boxedwine、CheerpX、v86、QEMU 等项目复制
  实现。
- 让用户程序链接内核内部对象文件或依赖未声明的内核 C 结构布局。
- 对某个具体产品的许可证组合给出无条件合规保证；项目文档只能说明设计边界和发行
  义务。

## 代码归属规则

新功能应放在允许它以宽松许可证发布的最外层位置：

1. 能作为独立 MIT runtime 实现的，不放进 Linux。
2. 能通过现有 Linux UAPI表达的，不新增应用可见 syscall。
3. 必须修改代码生成的，放在 LLVM，并遵循 LLVM exception。
4. 必须修改 libc 的，优先放在 MIT musl。
5. 只有 Linux 进程、文件、信号或 syscall 语义不可避免时才修改 Linux。

“尽量 MIT”不是修改第三方许可证，而是通过组件边界让新代码尽量诞生在 MIT
组件中。

## 平台变更纪律

每项变更必须说明它改善的是内核、工具链、libc、发行版、宿主、设备、兼容性或发布
中的哪一项能力，并给出相应层级的测试。不得把某个应用成功启动当作语义完整性的唯一
证据，也不得让一个专项实验无意中成为其他工作流的强制依赖。

涉及 syscall 行为或跨组件契约的变更必须先以标准 Linux 可观察语义为基准，再记录
Wasm 限制、明确的降级行为和版本兼容策略。

### softmmu2 专项 ABI

softmmu psABI 的变更必须同时包含：

- ABI 文档更新；
- 版本或 feature bit 的变化；
- LLVM codegen 测试；
- loader 兼容性测试；
- musl/runtime 测试；
- Linux/宿主 slow-path 测试；
- 旧版本拒绝或兼容行为测试。

已经进入发行版的 TLB entry 布局、custom section、import 签名和 pointer-domain
规则不能静默改变。

## 提交要求

- 新文件必须带正确的 SPDX 标记；`LICENSE` 正文除外。
- 一个提交只跨越必要的组件边界，并在提交信息中说明 ABI 影响。
- 不提交构建缓存、大型二进制和来源不明的生成物。
- Linux、LLVM、musl 的修改应尽可能保持可独立审阅和可上游化。
- 每项性能优化都必须保留可关闭的正确性基线，并提供差异测试。

## 本地与 CI 验证

贡献者本地至少运行与改动直接相关的轻量检查。LLVM、Linux、完整rootfs和浏览器矩阵
等占用大量磁盘的验证由公开仓库的GitHub Actions承担；除非正在诊断特定问题，不要求
贡献者在本地构建全部组件。

新增或修改工作流时，应保持最小`GITHUB_TOKEN`权限，避免无界矩阵和无界缓存，并为
测试artifact设置与用途相称的较短保留期。发布任务必须与运行不受信任fork代码的任务
隔离。
