# SSH 连接、远程命令与文件复制

## 先查缓存，后连接

先用对应的 `yicloud job connection list` 或 `yicloud workspace connection list` 查缓存，并带上当前 `--project`、`--zone`。缓存按账号、项目、可用区和本地名称区分。

找到当前实例及所需身份后，直接用该名称调用 `ssh` / `exec` / `scp`。没有缓存时，查询真实资源，生成完整 SSH 命令，**先用 `connection set` 持久化，再连接**。不要因为 `No SSH connection` 就要求用户提供命令。

普通用户与 root 分别命名为 `<实例名>-user`、`<实例名>-root`，避免互相覆盖。有项目运行记录时，同步记录缓存名和完整 SSH 命令，便于恢复。重提 Job 或替换实例后，重新查询并缓存新实例；不要复用旧 Pod 的命令。

## 查实例和连接字段

- Job：用 `job status` 和 `job replicas` 取得运行中的真实副本 Name，确认 SSH 已启用。SSH 使用副本名，不是 Job ID。
- Workspace：用 `workspace status` 取得 WorkspaceId、Creator、QuotaGroup。普通用户也可通过 `workspace ssh-config` 自动发现连接，再将结果登记缓存。
- 平台用户名：复用已确认的登录身份。查询个人 Job 可用 `job list --all --set 'Self=true'`，由唯一且无 RealCreator 冲突的 Creator 确认；不要借用其他人的资源创建者或从本地用户名猜测。
- 当前 yicloud.com.cn 部署的网关为 `ssh.gate.yicloud.com.cn`，端口 `2202`。其他部署从控制台 `app.config.js` 的 `VITE_SSH_BASE_URL` 和其 SSH 命令确认；不要从 Pod IP 猜网关。

## 普通用户和 root 的连接规则

完整命令为 `ssh -p <端口> <下表用户名>@<网关>`。

| 资源 | 普通用户 | root |
|---|---|---|
| Job 副本 | `<replica>.<user>.<project>.pod` | `<replica>.<user>+root.<project>.pod` |
| 普通开发机 | `<workspace_id>.<creator>.<project>.ws` | `<workspace_id>.<creator>+root.<project>.ws` |
| 共享开发机 | `<user>+<workspace_id>.group-<project>-<quota>.<project>.ws` | `<user>+<workspace_id>.group-<project>-<quota>+root.<project>.ws` |

`quota` 取 QuotaGroup 并把 `_` 换成 `-`。注意共享开发机的 `+root` 加在配额组后面。Workspace worker 使用真实 worker 名和 `.pod`，不要拿 WorkspaceId 当 worker 名。

以上规则来自该部署控制台；Job 两种身份均已实连。CLI 自动发现没有 `--root` 参数；root 连接按表生成并缓存。共享开发机自动发现使用 `--shared --ssh-user "$platform_username"`，不要在 `--ssh-user` 中拼入 `+root`。

## 先缓存完整命令

下列变量先赋为真实查询值。Job 示例：

```bash
user_command="ssh -p ${ssh_port} ${replica_name}.${platform_username}.${project}.pod@${ssh_host}"
root_command="ssh -p ${ssh_port} ${replica_name}.${platform_username}+root.${project}.pod@${ssh_host}"

yicloud job connection set "${replica_name}-user" --project "$project" --zone "$zone" \
  --ssh-command "$user_command"
yicloud job connection set "${replica_name}-root" --project "$project" --zone "$zone" \
  --ssh-command "$root_command"
```

Workspace 同样先按表生成完整命令，再用 `workspace connection set` 保存对应的 `-user` / `-root` 名称。`connection set` 只解析、保存连接，不执行 SSH。已有 `-CAXY`、`-i`、`-J` 的真实命令可直接登记；不要为了连接默认添加 Agent 转发或 X11。

首次连接后用 `id -un` 和 `hostname` 核对身份与目标。后续复用缓存名称，无需反复拼长命令或重新读取控制台代码：

```bash
yicloud job exec "${replica_name}-user" --project "$project" --zone "$zone" -- id -un
yicloud job exec "${replica_name}-user" --project "$project" --zone "$zone" -- hostname
yicloud job ssh "${replica_name}-user" --project "$project" --zone "$zone"
```

需要 root 时改用已缓存的 `-root` 名称。`connection show` 可查看记录，`ssh-config` 可导出 OpenSSH 配置；不改写用户现有 SSH 配置。

## 远程执行与文件复制

独立命令使用 `exec`，其返回远端退出码，不保留前次 `cd/export`。需持续 shell 状态时分配 PTY，运行 `ssh` 并复用会话句柄。SSH 断开后先确认远端进程是否仍在运行，不重复启动长任务。

文件复制复用缓存名称；Workspace 将下面的 `job` 改为 `workspace`：

```bash
yicloud job scp "$local_path" "$connection_name:$remote_path" --project "$project" --zone "$zone"
yicloud job scp "$connection_name:$remote_path" "$local_path" --project "$project" --zone "$zone"
```

目录用 `--recursive`；复制后检查目标大小或哈希。公钥需已在平台注册；私钥只传路径，不读取正文。不关闭主机密钥校验。连接或 GPU 环境异常时读取[排错手册](troubleshoot.md)。
