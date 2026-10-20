# 连接、远程执行与复制文件

## 何时读取

用户需要 SSH、在已有机器运行命令或复制文件时读取。先知道目标机器或连接、操作目录和预期执行内容。

## 找到可用连接

1. 检查对应的 `workspace connection list` 或 `job connection list`。已知的 OpenSSH Host 也是连接来源；可检查 `~/.ssh/config` 及相关 Include，不搜索整个主目录，不读私钥正文。
2. 未登记的开发机可通过 `workspace ssh/exec/scp/ssh-config` 自动查询运行中的机器。`ws-` 前缀默认按 ID，其余按名称；`--by-name` 强制名称查找并跳过同名本地登记。用 context 或显式范围消歧，必要的 Creator 条件通过 `--lookup-set` 提供。
3. 训练实例需要已启用的 SSH 及平台提供的真实连接命令，使用 `job connection set` 登记。不要从 Pod IP 推测网关。
4. 两种来源均不足时，说明缺少哪项连接信息；需要控制台操作时沿用用户授权，不因为自动发现失败就擅自操作浏览器。

首次连接前平台需要登记本机 `.pub` 公钥。通过 `--identity` 指定现有私钥路径，不读取其内容。

共享开发机自动发现需要 `--shared --ssh-user "$platform_username"`，用户名必须是实际平台登录身份，不能从本地账号别名、机器创建者或邮箱猜测。缺少身份时补齐或使用已核实的登记连接；CLI 会拒绝缺少共享路由参数的连接。已登记连接优先，不能混入发现选项；确需绕过同名登记时用 `--by-name` 明确选择平台名称。

## 执行与会话选择

先用最小只读命令核对目标身份，再执行用户工作：

```bash
yicloud workspace exec "$resource" -- hostname
```

独立查询使用 exec，它继承输入输出并返回远端退出码，不保留前次 cd/export 状态。连续依赖同一 shell 环境的操作使用终端工具分配 PTY，启动 `workspace ssh`，保存会话句柄后复用。检查上一条命令的完成状态再继续；SSH 进程存在不等于命令成功。

已有明确 OpenSSH Host 可以直接使用 `ssh "$ssh_host"`，也可按 `connection set --help` 导入。自动发现默认开启 Agent 转发；不需要时使用 `--no-forward-agent`。不改写用户现有 SSH 配置或关闭主机密钥校验。

## 文件传输

`local_path`、`remote_path` 来自用户任务，`resource` 是已确认目标：

```bash
yicloud workspace scp "$local_path" "$resource:$remote_path"
yicloud workspace scp "$resource:$remote_path" "$local_path"
```

上面是上传、下载两种独立形式，按任务选择。目录增加 `--recursive`。SCP 是完整复制，不提供增量同步、断点续传或自动清除多余文件。复制后检查目标文件、大小及任务要求的内容或哈希；不能只凭连接成功报告交付完成。

## 异常与完成标准

- 连接失败：保留退出码，区分目标解析、网络、认证与远端 shell 初始化，读[排错手册](troubleshoot.md)。
- 连接断开：检查远端实际进程再重试命令，避免重复启动长任务。
- 长任务：按用户要求使用托管 Job/Ray 或已选的会话工具；SSH 保活不保证断连后继续执行。
- `connection remove` 只移除本地登记，不停止或删除远端资源。

报告实际目标、远端退出状态或传输验证结果。结束本次临时会话；不要清理用户正在使用的持久会话。
