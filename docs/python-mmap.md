<!-- SPDX-License-Identifier: MIT -->

# Python mmap 模块恢复与运行边界

`09c6c78` 移除 CPython 3.13.14 配方中的 `py_cv_module_mmap=n/a`，让上游根据
实际 sysroot 检测模块。当前 musl 安装包含 `sys/mman.h`；旧配方中“缺少头文件”
的禁用理由已经过时。未新增 Python 映射模拟层，也不把固定地址映射的配置探测
强行改为成功。

这一阶段只涉及现有 wasm32 Python 包，不代表完整 Python 已移植到 wasm64。
主要 wasm64 目标保持不变，后续需要匹配位宽的完整依赖和独立运行验收。

## 应用调用方式

默认内核仅接受有界线性内存内的私有匿名读写映射，Python 应显式选择：

```python
import mmap

with mmap.mmap(-1, 65536, flags=mmap.MAP_PRIVATE,
               prot=mmap.PROT_READ | mmap.PROT_WRITE) as buffer:
    buffer[:4] = b"data"
```

上游 `mmap.mmap(-1, size)` 默认使用 `MAP_SHARED`，当前内核拒绝该请求；模块
可导入不等于默认构造调用可用。默认内核同样拒绝文件映射。不能据此推导共享
内存、跨进程映射、写回、写保护、固定地址替换、resize 或 flush 已获得支持。
实验性 `WASM_FILE_MMAP` 仍关闭，不为 Python 检查启用它。

保持 `--without-mimalloc`、`--with-ensurepip=no` 和 `_posixshmem` 禁用策略：
匿名映射并未验证分配器的 reserve/commit/protection 需求、pip 的安装/文件映射
路径或 POSIX 共享内存。第三方 Python 源码与许可保持不变，自有夹具采用 MIT。

## 验证与证据

独立 `python-check-mmap` 安装系统检查运行同一份 `mmap-test.py`，验证初始清零、
跨页二进制读写、查找和重叠移动、`memoryview` 导出时禁止关闭、释放视图后关闭、
关闭幂等及重复分配。额外要求默认共享请求和普通文件映射以 `EINVAL` 失败。
不靠捕获错误后跳过来报告成功，不修改内核配置以迁就模块。

```sh
nix build './sources/distro#checks.x86_64-linux.python-check-mmap'
```

两项本机检查通过，包含相同 Python 数据操作及目标检查接线；原生 Linux 不执行
Wasm 的拒绝边界断言，不能替代真实目标模块构建和运行。重型构建仅使用公开
GitHub Actions。目标结果尚待验收，不宣称 CPython 文件映射、pip 或浏览器通过。
固定 `d4fafc8` 的[公开目标检查][target-check]已触发，计划与派生解析通过，实际构建/运行仍在进行。

[target-check]: https://github.com/HighCWu/distro/actions/runs/39074334178
