# 保存环境与推送镜像

先区分用户要保存平台开发机/Worker 的环境，还是上传当前执行环境里已有的 Docker 镜像。只展开对应分支；平台 registry API 管理仓库和版本元数据，没有镜像层上传接口。只要求准备或预览时不执行保存、Docker 登录、tag 或 push；Docker 推送流程没有可替代上传的 `--dry-run`。

## 准备目标

目标是已确认 registry host、命名空间、仓库和明确 tag 的完整引用。优先使用用户提供的推送信息、平台控制台或[实际镜像查询结果](query.md)；API gateway 不是 registry host，不按域名规则猜。仓库不存在时按[仓库管理](manage.md)及用户要求创建，不能把所属项目误当可见范围。

目标 tag 已存在时核对覆盖是否符合用户意图，必要时选择用户同意的新 tag。保留私有范围，推送本身不授权修改仓库可见性、开放新的外网访问能力或重设访问密码。明确目标与镜像内容授权后再写入；镜像内排除凭据、SSH 私钥和临时认证文件，不能把挂载盘数据默认当作已打入镜像。

## 保存开发机环境

已知开发机 ID 后先取得目标进程：

```bash
yicloud --json workspace processes "$workspace_id" --project "$project" --zone "$zone"
```

从真实返回选取所需环境的 ProcessId：开发机主环境对应 master，指定 Worker 则核对对应 worker。多个候选时消歧；WorkspaceId、系统 PID、展示名称都不能当 ProcessId。本路径始终使用已核实的 ProcessId，不靠本地 dry-run 判断进程选择是否正确。

```bash
yicloud --json workspace get-release-exclude-patterns --process-id "$process_id" --project "$project" --zone "$zone"
```

核对返回的默认排除项和本次实际打包范围。自定义 ExcludePatterns 是 JSON 数组；只有确认其覆盖/合并语义和最终排除内容后才提供，不猜自定义列表会自动追加默认项。

```bash
yicloud --json workspace release-process --process-id "$process_id" --zone "$zone" --image-name "$target_image" --dry-run
```

需要已确认的排除数组时加 `--exclude-patterns "$exclude_patterns_json"`。核对后移除 dry-run 提交。注意 get-release-exclude-patterns 要 Project，release-process **不接受 `--project` 或请求 Project 字段**，不能机械复用上一条命令的参数。

提交成功不等于镜像制作完成。按目标命名空间、仓库、可用区和 tag 查询本次版本，核对实际 ImageUrl、摘要或本次更新证据；旧版本同名不能代替本次完成。制作尚未完成时有限重查，不重复触发保存。需要依赖或 GPU 可用性验证时继续[环境验证](../environment.md)。

## 推送本地已有 Docker 镜像

在用户选定的执行环境确认 Docker 客户端和 daemon 可用，并核对源镜像；GPU 开发机不假定支持 Docker Engine。缺少环境时使用已授权且已验证可用的本机或 CPU 环境，不为普通上传自动安装 daemon、改网络或新建计算资源。

飞书当前说明仅支持推送 Docker 格式镜像；不能把 OCI 等其他产物格式当作已支持，也不擅自转换用户产物。外部上传的账号凭证来自平台「访问凭证」；文档有设置固定密码的步骤，已有凭证优先复用，缺失时由用户完成必要的凭证设置，不能把 API 密钥当作仓库密码。

```bash
docker image inspect --format '{{.Id}} {{.Os}}/{{.Architecture}}' "$source_image"
```

使用当前执行用户、Docker context 的既有 registry 登录；需要登录时从平台实际登录说明取得 registry 用户和凭据。registry_host 只含主机和可选端口，不含协议、项目或仓库路径：

```bash
docker login "$registry_host" --username "$registry_user"
```

密码由安全交互输入；已有安全凭据输入通道可使用 `--password-stdin`，不在命令参数、聊天、日志或资产文档中写明文密码。缺少登录信息时补齐，不擅自开启公网访问或变更权限。保持 login/tag/push 使用同一执行身份，避免混用 sudo 导致凭据位置不同。

```bash
docker image tag "$source_image" "$target_image"
docker image push "$target_image"
```

target_image 必须明确包含已确认的 registry、命名空间、仓库和 tag；不能省略后默认为 Docker Hub/latest。仅处理用户要求的 tag，不使用 `--all-tags` 扩大上传范围。

## 上传后验收

记录 push 返回的 tag 和 digest，再用[版本查询](query.md)确认平台目标版本及完整引用。索引有延迟时有限重查，不因为暂未显示就反复 push；本地 tag 或 image ls 出现目标名不证明已上传。

用户需要验证可拉取时，在指定消费环境执行 `docker image pull "$target_image"`，记录实际拉取结果与对应版本摘要；不要把本地配置 image ID 和远端 manifest digest 混为一谈。需要开发机/Job 验证时沿用已有授权环境或进入对应创建流程，不为单纯推送擅自创建测试机器。报告实际完成到上传、版本可见、拉取或运行验证的哪一层；鉴权失败不改共享范围，结果不明不报成功。

部分实例启动成功不证明镜像权限正常：飞书说明 `IfNotPresent` 缓存可造成有缓存节点能运行、无缓存节点拉取鉴权失败，应核对实际消费账号的私有仓库拉取权限。遇到上传 502 且拉取正常，按当前环境核对代理与内部 registry/对象存储的直连配置，保留既有 no_proxy 列表，不全局关闭代理或 TLS 校验。

平台规则优先依据[飞书镜像管理](https://iqeubg8au73.feishu.cn/wiki/E6aXw42RoiqM0SkdpP5cGIsJndc)（从[最新索引](https://iqeubg8au73.feishu.cn/wiki/BG9Bwc6RliG4DbkIu2OckJKZnxh)进入）；Docker 语法参考官方[登录](https://docs.docker.com/reference/cli/docker/login/)、[标签](https://docs.docker.com/reference/cli/docker/image/tag/)、[推送](https://docs.docker.com/reference/cli/docker/image/push/)与[拉取](https://docs.docker.com/reference/cli/docker/image/pull/)。保存环境的 CLI 参数经本地合同验证，生产端排除项语义和制作完成仍须实测。平台给出的实际仓库登录信息优先，不把文档示例用户名或域名作为当前账号配置。
