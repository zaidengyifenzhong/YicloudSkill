# 账号与认证

适用于首次配置、切换租户和认证排错。先检查别名与 API 地址，再检查地域与平台权限。凭据在交互输入中隐藏，不写入请求示例、日志或 YICLOUD.md。

```bash
yicloud account add research --auth hmac
yicloud account add automation --auth service
yicloud account list
yicloud account use research
yicloud --account research account current
yicloud --account research account check
```

`account add --auth token` 接受完整 Authorization 值。Token 优先于密钥；失败后不会切换身份。服务账号使用 Basic 公钥/私钥。HMAC 使用毫秒时间戳，检查本机时间偏移。

按实际控制台选择 API 地址；`.com` 与 `.com.cn` 不是可互换的同一环境：

| 控制台 | OpenAPI |
|---|---|
| console.yicloud.com | https://gate.yicloud.com |
| console.yicloud.com.cn | https://gate.yicloud.com.cn |

`.com.cn` 环境首次创建账号时使用 `yicloud account add research --auth hmac --host https://gate.yicloud.com.cn`。全局 `--host` 可临时验证地址。HTTP 400 的 `Public Key 不存在` 可能是网关环境不匹配，应先核对控制台域名，再检查凭据；不自动跨环境重发认证请求。[官方域名说明](https://docs.yicloud.com/8/1.html)。

默认配置 `~/.config/yicloud/config.json`，可用 `YICLOUD_CONFIG` 指定隔离路径；原子写入，POSIX 文件权限 0600。配置为本地明文凭据，应使用受信任的本机账户。`account remove ALIAS` 删除该别名并保留 SSH 配置。

地址/地域优先级：全局 `--host` / `--region` → `YICLOUD_API_HOST` / `YICLOUD_REGION_ID` → 账号 → `https://gate.yicloud.com` / `cn-shanghai`。认证环境变量为 `YICLOUD_AUTHN_TOKEN`、`YICLOUD_PUBLIC_KEY`、`YICLOUD_SECRET_KEY`、`YICLOUD_IS_SERVICE_ACCOUNT`。只要其中任何一个变量存在，就整组覆盖账号认证，不能只给公钥并期望沿用账号私钥。Token 始终优先。

默认超时 30 秒，Python 客户端支持 timeout 参数。首版不读取 SDK 的 YICLOUD_MAX_RETRIES/YICLOUD_TIMEOUT，避免覆盖只读最多两次附加重试的边界。HTTP 401/403 检查认证和权限，业务失败保留平台 Code 与请求 ID，网络写失败先检查远端状态。

CLI 正常响应中的密钥字段默认脱敏；确实需要读取接口新建密钥时显式使用全局 `--show-secrets`。已加载账号的凭据始终隐藏。JSON 成功信封为 `ok/data/meta`，业务和输入等失败为 `ok:false/error`，错误写入 stderr，退出非零。本地 Ctrl-C/交互取消返回 130；`--json` 使用失败信封（kind=interrupted），普通模式输出文字说明。取消时保守标记结果未知，不能证明远端写入未执行。Python 成功数据及原始响应仍由脚本处理；客户端会清理错误消息和元数据中的已知凭据，并抑制可能包含秘密的底层传输异常链。

来源：[SDK 认证](https://gitee.com/yicloud-team/openapi-sdk-go/tree/8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5/base/auth)、[官方文档入口](https://docs.yicloud.com/)。核对日期 2026-10-19；已在 `.com.cn` 环境实测 HMAC 认证和部分只读接口，Token 与服务账号认证尚未联测。
