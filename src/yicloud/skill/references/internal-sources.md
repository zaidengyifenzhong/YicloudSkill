# 离线环境与内部源

用于 H200/GPU 离线环境、CPU 联网准备、内部源补包和镜像固化。具体包源地址按需读取项目 YICLOUD.md 引用的本地指引；不要从其他平台的源地址推测本平台入口。

## 先选准备位置

| 需求 | 准备位置与交付方式 |
| --- | --- |
| 公网代码、权重、数据或内部源未覆盖的包 | 可联网 CPU 开发机下载，写入共享存储或固化环境镜像 |
| 内部 APT、pip 等已覆盖的依赖 | 确认源可达后，在目标 GPU 环境安装验证，随后保存镜像复用 |
| 已有镜像需要提取环境 | 支持 Docker 的 CPU 开发机提取，再经共享存储给 GPU 验证 |

镜像保存运行环境；代码、模型权重、数据、Checkpoint 和产物使用明确的共享存储路径。需要长期复用的镜像版本、构建配方、路径及适用项目写回 YICLOUD.md；动态状态和测试过程不写入资产记录。

## 内部包源入口

Dependency Gateway 仅在平台内网使用；`INTERNAL_GATEWAY` 由用户或环境管理员提供，不预置真实地址。先在实际消费环境查询 `/healthz` 和 `/v1/status`，确认本次所需源可达且已启用。

| 类型 | Gateway 路径与使用边界 |
| --- | --- |
| pip / PyPI | `/v1/cache/pypi-simple`，下载链接由 Gateway 重写 |
| PyTorch wheels | `/v1/cache/pytorch/cu<version>`，CUDA 通道按目标环境选择 |
| Ubuntu APT | `/v1/cache/ubuntu`，源行的发行版必须匹配镜像 |
| 其他包管理器或 Git | 按使用说明和服务启用情况配置，不把 Gateway 当成任意地址代理 |

临时 APT 源与 Gateway 是不同入口，按用户提供的信息选择，不保证长期有效。APT 保留原发行版签名校验；第三方公钥先核验来源和指纹。优先使用单次命令参数或当前构建环境配置包源，避免无关的全局改动。HTTP 包源需要客户端信任设置时，只针对用户确认的内网主机配置，不全局关闭 TLS 校验。

## 离线 GPU 环境准备

H200 默认不连外网，其他 GPU 集群也不应假定可访问公网。在可联网 CPU 开发机准备环境，保存为自定义镜像，再让 H200 开发机或任务使用该镜像。优先复用已有合适镜像；需要定制时采用以下流程。

1. 选择与目标 CPU 架构一致、CUDA/Python/框架版本适配目标 GPU 的基础镜像，在可联网 CPU 开发机安装固定版本依赖。没有 GPU 不代表应安装 CPU-only 框架；涉及 CUDA 编译的扩展需核对工具链和目标架构，CPU 上安装成功不证明 GPU 上可运行。
2. 将需随镜像携带的环境放在实际制作镜像的文件系统内。先查看默认排除规则，确认虚拟环境、用户目录和缓存是否被保存；不要假定挂载的云盘或共享目录会打包进镜像。大型模型和数据可提前放入目标 GPU 可读的存储，运行时使用本地路径。
3. 从开发机进程列表取得真实 ProcessId，通过控制台“制作镜像”或 `yicloud api call workspace ReleaseProcess` 保存到有写权限的镜像仓库，使用新版本标签。WorkspaceId、SSH 连接名、系统 PID 均不能替代 ProcessId。保存前排除凭据、SSH 私钥和临时认证文件。
4. 查询目标镜像标签及摘要，确认目标项目/可用区可见且能够拉取，再在 GPU 上验证框架识别设备、最小 GPU 运算及依赖导入。检查启动时的隐式下载；需要 GPU 才能完成的编译应预备离线源码、工具链和依赖。验证完成前保留环境准备机或可复现构建记录。

CLI 已提供制作镜像接口入口，无需假定 CPU 开发机预装 Docker：

```bash
yicloud workspace processes WORKSPACE_ID --project PROJECT --zone ZONE
yicloud api describe workspace GetReleaseExcludePatterns
yicloud api describe workspace ReleaseProcess
yicloud api call workspace ReleaseProcess --file release-image.json --dry-run
yicloud api call workspace ReleaseProcess --file release-image.json
yicloud api describe registry ListCustomImages
```

`release-image.json` 的字段示例（全部标识须替换为实际值）：

```json
{
  "ZoneId": "ZONE",
  "ProcessId": "PROCESS_ID",
  "ImageName": "registry.example.com/PROJECT/environment:VERSION"
}
```

`ReleaseProcess` 不接受 Project 字段；`GetReleaseExcludePatterns` 则需要 Project、ZoneId 及进程定位。可用 `ExcludePatterns` 提交自定义排除规则，具体匹配和合并语义需核对平台，不能假定它自动过滤全部秘密。请求成功只说明提交成功，需另查镜像结果；网关身份缺失或鉴权失败时核对账号及接口支持，不伪造身份请求头。制作镜像接口及 CPU→H200 迁移尚未真实联测，以上流程不代表已经完成兼容性验证。

### 临时补包与已有镜像

平台 GPU 开发机不能按 CPU 开发机的方式运行 Docker，可能被 unshare 权限拦截；同一镜像不代表相同运行权限。需要 Docker 的 load/create/cp 操作放在支持 Docker 的 CPU 开发机执行，不尝试通过提权绕过 GPU 限制。

- 已有镜像归档：在 CPU 上 `docker load`，确认镜像名后 `docker create`（不启动容器），再 `docker cp` 提取所需环境到共享存储。确认复制完成后删除自己创建的临时容器；GPU 上直接使用提取环境。仅复制 `/usr/local` 不会携带全部系统库，需核对 CPU 架构、Python ABI、glibc/CUDA 依赖及硬编码路径；按实际目录设置 PATH、PYTHONPATH、LD_LIBRARY_PATH，不提供通用的“激活即兼容”承诺。
- 临时补包：使用用户提供且当前可达的内部 APT/pip 或 Dependency Gateway。先核对 `/etc/os-release`、架构与源是否启用；jammy 源只用于 Ubuntu 22.04，不能混入 noble 等发行版。保留 APT 签名校验和经核验的仓库公钥，不为用户态依赖安装或替换宿主 NVIDIA 驱动。
- 内部源缺包或失效：在可联网 CPU 上下载匹配目标 Linux/Python/架构的 wheel、deb、源码及其依赖，经共同可挂载且有权限的存储转移后离线安装。macOS 的 dmg 不能作为 Linux 安装包；仅复制一个 wheel 或 deb 不保证依赖齐全。
- 大型镜像传输：按当前平台能力，不依赖本地到镜像仓库上传的断点续传；优先在平台 CPU 侧准备或使用可校验的离线依赖，避免把一次长时间上传当成唯一交付路径。

[Dependency Gateway 使用说明](https://github.com/sii-system/dependency-gateway/blob/main/docs/user-guide.md)提供各包管理器的接入方式。使用环境管理员提供的地址，先查 healthz 和 v1/status，再选择匹配的命名源；它不是通用公网代理，prebuild 动态下载路由不用于手动调用。内部源可能临时失效，下载成功也可能是 BYPASS，不能据此声称已经缓存。具体包源地址只放在项目的私有记录中。
