# 开发机与标准 SSH

适用于持续开发、调试和远程同步。优先使用用户指定的现有机器和登记连接；未登记的开发机可自动解析 SSH 连接。需要新机器时再选镜像与规格、创建并等待 Running。

## 连接来源与目标确认

先检查当前账号/context 及与任务相关的 CLI 登记。标准 `~/.ssh/config` 中与目标对应的 Host 也是现有连接来源：只读该已知文件及其相关 Include 路径，不扩大为主目录搜索。已有明确 Host 时可直接 `ssh HOST 'COMMAND'`，无需先导入；需要通过 CLI 统一调用时可用 `connection set ... --ssh-command 'ssh HOST'`，由 OpenSSH 解析该 Host。不要只因本地登记为空便反复索要连接命令。

用目标匹配的配置及最小只读命令（如 hostname）核对身份，再开展诊断。连接成功、目标一致、GPU 状态确认是不同证据；不能用一台 CPU 机器替代另一台 GPU 机器。私钥只使用路径，不读取正文，不改写现有 SSH 配置或放宽主机密钥校验。

当前 CLI 支持自动发现时可按平台 ID/名称连接；版本不支持或发现失败时，仍可使用已有 Host。只有这些来源都不足时才说明具体缺口，请用户提供平台 SSH 命令，或在用户明确授权后使用控制台。没有尝试过的连接应标记“尚未验证”，不能写成“连接失败”。

## 连续会话与一次性执行

连续在同一机器上诊断、修改、验证，或依赖 cd、export、环境激活时，优先复用已确认有效的同一 SSH shell。在终端工具中分配 PTY（如 `tty=true`），运行 `yicloud workspace ssh RESOURCE ...` 或已有 Host：

```bash
ssh -tt -o BatchMode=yes -o ConnectTimeout=10 \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 HOST
```

保存终端工具返回的运行会话句柄，后续向同一会话写入命令（如 `write_stdin`），不为每条命令重建连接。等待上一条命令完成并及时检查结果或 `$?`，再执行依赖它的下一步；SSH 进程仍在运行不代表上一条命令成功。复用前核对目标、目录及必要环境；旧句柄不跨工具重启或聊天自动有效，任务结束或用户要求断开时退出。

独立短查询、需要独立退出码或检验新登录环境时用 `workspace exec ... -- COMMAND` 或 `ssh HOST 'COMMAND'`；它们不保留前次 shell 状态。API 查询直接用 CLI，无需 SSH。连接复用（如 ControlMaster）不等于复用同一 shell；ServerAlive 只检测连接，不自动重连。断线后检查实际状态再恢复环境；长任务按用户目标使用 tmux、Job 或既有管理工具，保持 SSH 不保证断线后继续运行。

## 平台查询与自动发现

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

首次仍需在平台登记本机 `.pub` 公钥。开发机 `ssh`、`exec`、`scp`、`ssh-config` 和 `doctor` 优先使用本地登记；未登记时查询运行中的开发机，按已核对的控制台规则生成连接，无需复制 SSH 命令。自动结果仅用于本次调用，不自动写入配置。训练实例仍使用手动登记。

```bash
yicloud workspace ssh WORKSPACE_ID --project PROJECT --zone ZONE --identity ~/.ssh/id_ed25519
yicloud workspace exec devbox --project PROJECT --zone ZONE --lookup-set 'Creator="PLATFORM_USER"' -- nvidia-smi
yicloud workspace scp ./src devbox:/work/src --recursive --project PROJECT --zone ZONE --lookup-set 'Creator="PLATFORM_USER"'
yicloud --json workspace ssh-config WORKSPACE_ID --project PROJECT --zone ZONE
```

未登记的 `ws-` 前缀按 ID 处理，其他值按精确名称查询；`--by-name` 强制平台名称查找并跳过同名本地登记，可用于以 `ws-` 开头的显示名。名称查找可用 `--lookup-set` 传 Creator 等列表过滤，拒绝同名多结果。显式指定项目和可用区或使用 context；连接前核对返回范围和 Running 状态。

普通用户名由 WorkspaceId、Creator、Project 组成，不使用本地账号别名或 Pod IP。共享开发机需加 `--shared --ssh-user PLATFORM_USER`，使用实际登录用户名；检测到共享身份但未明确参数时拒绝自动连接。公开 API 没有可靠的当前登录用户名接口，不猜测该身份。网关从已知部署的公开控制台配置读取（不携带 API 凭据，不执行 JavaScript），默认端口 2202；自定义部署或配置不可用时可传 `--ssh-host` / `--ssh-port` 或手动登记。

自动连接默认启用 SSH Agent 转发（`-A`），允许远端在连接期间借用本机 agent 身份；`--no-forward-agent` 可关闭，不自动开启 X11。已有登记默认保留原转发设置，可用 `--forward-agent` / `--no-forward-agent` 单次覆盖。`--identity` 单次选择私钥，不复制私钥到远端；不指定时由本机 OpenSSH 查找默认密钥或 agent。Agent 转发需要本机可用的 ssh-agent 及已加载身份；`--identity` 不会自动向 agent 添加密钥。以上覆盖不改变登记内容。已有登记与发现专用参数冲突时会报错，不静默忽略。

需要自定义连接、root 登录或自动发现不适用时，优先使用已确认的 Host 或用户提供的实际 SSH 命令；控制台操作遵循上文授权范围。完整网关用户名可能含 `+`、`.` 等，必须原样保留；平台网关不支持用 ssh-copy-id 登记公钥。

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

手动连接按账号/工作负载/项目/可用区/资源标识保存；名称或实例变化需重新登记。训练实例启用 SSH 且获得连接命令后，可使用相同的 `job connection set INSTANCE ...`、`job ssh/exec/scp/ssh-config`。登记的 resource 是连接键；同一任务多个实例应使用不同键。不从 API 的 Pod IP 推测网关地址。

来源：[官方 SSH 教程](https://docs.yicloud.com/4/1/1/1/5.html)、[SDK workspace](https://gitee.com/yicloud-team/openapi-sdk-go/tree/8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5/services/workspace)。

## SSH 与 GPU 环境排错

若远程登录 shell 初始化失败，用 `workspace exec ... -- uname -s` 或 `sh -c` 区分连接与镜像脚本故障；不要自动改写用户镜像。

在已确认的目标 GPU 机器上保留原始报错和退出状态，再按错误层次检查：`command not found` 先查实际 PATH、`command -v nvidia-smi` 及 `/usr/local/nvidia/bin/nvidia-smi`；绝对路径执行仍提示 `libnvidia-ml.so` 缺失，再查 LD_LIBRARY_PATH 和 `/usr/local/nvidia/lib{,64}` 中的实际库文件。设备或驱动问题则结合平台 GPU 分配、`/dev/nvidia*` 和 `/proc/driver/nvidia/version` 判断，不用 CPU 机器的结果替代，也不递归搜索整个文件系统。

`/etc/environment` 声明变量不代表当前 SSH shell 已加载。程序、设备和驱动信息存在时，先在单次命令或子 shell 中补充实际存在的 NVIDIA 程序/库目录，保留原有 PATH、LD_LIBRARY_PATH 并避免空路径元素。覆盖后成功只证明本次路径问题可修复；`nvidia-smi` 正常不等于训练框架已验证，其 CUDA Version 字段也不证明已安装对应 Toolkit。

用户要求持久修复时，按实际 shell 与启动文件定位：Bash 的非交互提前 return 可能跳过路径设置，但不能将 `.bashrc` 规则套用到其他 shell。先备份，对暂存修改做对应语法检查，再写回；只添加存在的目录、保留旧变量并避免重复。用新建非交互 SSH、交互登录和重复加载分别验收，说明已有终端如何刷新。路径修复不顺带安装驱动或重启机器；剩余初始化警告单独记录。

实测同一镜像的新机也出现登录 shell 的 ssh-init.sh 语法错误和 .nv chown 错误；普通命令成功不代表登录初始化正常。SSH 的 RSA key incorrect signature 警告在 exec/scp 成功时仍可能出现，根因未确认；保留主机密钥校验，分别核验退出码和传输内容，不通过放宽校验消除警告。

只读检查用 `workspace doctor RESOURCE --project PROJECT --zone ZONE`，RESOURCE 可为登记连接、平台 ID 或名称；返回基本 SSH 执行、当前工作目录所在磁盘和 NVIDIA GPU 检查，GPU unknown 不代表没有 GPU。--timeout 为每项 SSH 检查的时限，默认 8 秒，不包括前置 API 查询和网关发现；不自动安装依赖。
