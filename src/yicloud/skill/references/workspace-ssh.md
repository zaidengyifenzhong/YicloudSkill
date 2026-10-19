# 开发机与标准 SSH

适用于持续开发、调试和远程同步。先选镜像与规格，再创建开发机、等待 Running，配置公钥及网关连接，执行诊断并核验文件。

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

导入支持 `-p/-i/-l/-J` 和已有 Host 别名，其他参数拒绝且原始命令不执行。需要 ProxyJump 时传 `--proxy-jump jump-host`。ssh-config 只输出片段，用户自行合并；身份文件需存在，保留主机密钥校验。exec 继承 stdin/stdout/stderr 并返回远端退出码。scp 使用现代 OpenSSH 的默认 SFTP 传输，支持路径空格；不启用旧 SCP shell 协议。

连接按账号/工作负载/项目/可用区/资源标识保存；名称或实例变化需重新登记。训练实例启用 SSH 且获得连接命令后，可使用相同的 `job connection set INSTANCE ...`、`job ssh/exec/scp/ssh-config`。登记的 resource 是连接键；同一任务多个实例应使用不同键。不从 API 的 Pod IP 推测网关地址。

来源：[官方 SSH 教程](https://docs.yicloud.com/4/1/1/1/5.html)、[SDK workspace](https://gitee.com/yicloud-team/openapi-sdk-go/tree/8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5/services/workspace)。核对日期 2026-10-19；平台 SSH 未联机验证。
