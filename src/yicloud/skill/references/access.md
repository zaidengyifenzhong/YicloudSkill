# 账号与操作范围

## 何时读取

首次配置认证、切换账号或项目，或发现资源不属于预期环境时读取。已有上下文且目标明确时无需重新配置。

## 确定当前来源

按缺口选择查询，不必全部执行：

```bash
yicloud account list
yicloud account current
yicloud context show
```

账号别名不等于平台用户名。context 保存账号别名、项目和可用区；显式命令参数优先于 context。`account use` 不清除已选 context，切换账号后检查实际来源；临时忽略 context 使用根级 `--no-context`。

显式 `--account` 与认证环境变量冲突时 CLI 拒绝执行。根据用户选择，在本次进程清除冲突变量或改用环境认证；不要打印变量值，也不要自动删除用户的永久配置。未显式指定账号时，环境认证仍可覆盖上下文或当前账号。

## 配置与验证

1. 从用户实际控制台确定网关：`.com.cn` 控制台对应 `https://gate.yicloud.com.cn`，`.com` 对应 `https://gate.yicloud.com`，不能跨环境试发凭据。
2. 需要新账号时使用 `account add`；凭据由隐藏交互输入，不能写在命令参数、请求模板或项目资产文档中。

```bash
yicloud account add "$alias" --auth hmac --host "$gateway"
```

`alias` 是用户选择的本地名称，`gateway` 来自已确认的环境。认证方式可选 hmac、service、token；token 输入需要的完整 Authorization 值。

3. 需要复用范围时保存 context，值来自用户指定或已核实的平台资源：

```bash
yicloud context set "$context_name" --account "$alias" --project "$project" --zone "$zone"
yicloud context use "$context_name"
yicloud account check
```

`account check` 是只读认证检查，不能证明创建或管理权限。完整请求文件不自动填充项目、可用区；项目总列表不受当前项目过滤。

## 异常与完成标准

- `Public Key 不存在`：先核对网关环境，再检查凭据，不自动切换域名。
- 401/403 或平台权限拒绝：区分身份与操作权限，不切换到更高权限账号绕过错误。
- HMAC 时间错误：检查本机时间；不伪造平台时间或请求头。
- context 与意图不一致：修正本次选择后再执行目标任务。

报告实际账号别名、网关、项目与可用区，不报告密钥。只有认证查询成功才能称“认证验证通过”；其他权限仍按实际任务检查。

配置默认位于 `~/.config/yicloud/config.json`，为本地明文凭据；`YICLOUD_CONFIG` 可指定隔离文件。移除本地账号不删除平台用户或远端资源。
