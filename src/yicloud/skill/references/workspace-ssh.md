# 开发机与标准 SSH

适用于持续开发、调试和远程同步。优先使用用户指定的现有机器和登记连接；需要新机器时再选镜像与规格、创建并等待 Running。

查询“我的开发机”时显式传已确认的平台用户名 Creator（不是本地账号别名）：

```bash
yicloud workspace list --project example-project --zone example-zone --set 'Creator="PLATFORM_USER"' --all
yicloud workspace status devbox --by-name --project example-project --zone example-zone --lookup-set 'Creator="PLATFORM_USER"'
```

实测省略 Creator 可能返回空列表，平台默认筛选语义尚未确认；不要据此认定没有开发机，也不要用本地 SSH 记录补齐平台列表。旧 CLI 不支持 `--lookup-set` 时，先用带 Creator 的列表取得唯一 WorkspaceId，再按 ID 操作。同名结果仍须消歧。

创建请求可从 [workspace.json](../assets/examples/workspace.json) 复制到用户项目后修改。模板中的资源与路径均为占位符。

```bash
yicloud workspace create --name devbox --project example-project --zone example-zone \
  --image example/image:tag --quota-group example-quota --cpu 4 --memory 16Gi --gpu 1 --dry-run
yicloud workspace create --file workspace.json
yicloud workspace wait WORKSPACE_ID --project example-project --zone example-zone
yicloud workspace processes WORKSPACE_ID --project example-project --zone example-zone
```

快捷创建生成 50Gi 系统盘；自定义系统盘、已有云盘和多挂载使用请求文件。Workspace 创建接口没有 Command 字段；启动后通过 exec 执行。支持 start/stop/restart/delete，删除前核对云盘保留策略（`api describe workspace DeleteWorkspace`）。

首次在平台「密钥管理 → SSH公钥配置」登记本机 `.pub` 公钥，然后在运行中开发机详情复制实际 SSH 命令。完整网关用户名可能含 `+`、`.` 等，必须原样保留。平台网关不支持用 ssh-copy-id 登记公钥。

```bash
yicloud workspace connection set devbox --project example-project --zone example-zone \
  --ssh-command 'ssh -p 2202 user@gateway.example' --identity ~/.ssh/id_ed25519
yicloud workspace ssh devbox --project example-project --zone example-zone
yicloud workspace exec devbox --project example-project --zone example-zone -- nvidia-smi
yicloud workspace scp ./train.py devbox:/mnt/project/train.py --project example-project --zone example-zone
yicloud workspace scp devbox:/mnt/project/result.json ./result.json --project example-project --zone example-zone
yicloud workspace ssh-config devbox --project example-project --zone example-zone
```

导入支持 `-p/-i/-l/-J`、`-C/-A/-X/-Y`（也可组合为 `-CAXY`）和已有 Host 别名，其他参数拒绝且原始命令不执行。压缩、Agent 和 X11 转发选项按导入命令显式保存；SCP 仅复用压缩与 Agent 选项。需要 ProxyJump 时传 `--proxy-jump jump-host`。ssh-config 只输出片段，用户自行合并；身份文件需存在，保留主机密钥校验。`connection list/show/remove` 管理本地登记，remove 不删除远端机器。exec 继承 stdin/stdout/stderr 并返回远端退出码；它是同步 SSH 命令，不保证断连后继续执行，不内置后台进程管理。长任务可使用平台 Job/Ray，或用户自行管理的终端会话工具。scp 使用现代 OpenSSH 的默认 SFTP 传输，支持路径空格和 `--recursive`/`-r` 目录复制；它不是增量同步，不支持自动删除目标多余文件；不启用旧 SCP shell 协议。

连接按账号/工作负载/项目/可用区/资源标识保存；名称或实例变化需重新登记。训练实例启用 SSH 且获得连接命令后，可使用相同的 `job connection set INSTANCE ...`、`job ssh/exec/scp/ssh-config`。登记的 resource 是连接键；同一任务多个实例应使用不同键。不从 API 的 Pod IP 推测网关地址。

来源：[官方 SSH 教程](https://docs.yicloud.com/4/1/1/1/5.html)、[SDK workspace](https://gitee.com/yicloud-team/openapi-sdk-go/tree/8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5/services/workspace)。

若远程登录 shell 初始化失败，用 `workspace exec ... -- uname -s` 或 `sh -c` 区分连接与镜像脚本故障；不要自动改写用户镜像。

实测同一镜像的新机也出现登录 shell 的 ssh-init.sh 语法错误和 .nv chown 错误；普通命令成功不代表登录初始化正常。SSH 的 RSA key incorrect signature 警告在 exec/scp 成功时仍可能出现，根因未确认；保留主机密钥校验，分别核验退出码和传输内容，不通过放宽校验消除警告。

只读检查用 `workspace doctor CONNECTION --project PROJECT --zone ZONE`，连接名和平台 ID 不必相同；返回基本 SSH 执行、当前工作目录所在磁盘和 NVIDIA GPU 检查，GPU unknown 不代表没有 GPU。检查最多等待 --timeout 秒/项，默认 8 秒，不自动安装依赖。
