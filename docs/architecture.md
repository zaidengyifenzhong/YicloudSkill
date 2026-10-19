# 架构

YicloudSkill 将命令行、同步 Python 客户端和 Agent 操作资料一起发布。命令行是平台 API 的便捷入口，复杂请求通过同一客户端直接调用。

## 依赖方向

```text
cli.py → commands/ → creation.py / workflows.py
              ↓                  ↓
        cli_support.py → client.py
                            ├── protocol.py → catalog.py
                            └── transport.py → auth.py → HTTPX
```

`cli.py` 负责命令装配。下层不反向依赖 CLI，业务与协议层不依赖 Click，也不读取交互输入或打印结果。SSH 使用本机 OpenSSH，与 HTTP 请求分开。

## 模块边界

| 模块 | 职责 |
|---|---|
| `commands/` | 按操作声明参数，适配业务函数和输出 |
| `cli_support.py` | CLI 输入、账号选择、脱敏和错误呈现 |
| `creation.py` | 快捷创建参数转为平台请求，校验资源规格组合 |
| `workflows.py` | 能力映射、资源定位、分页、请求构造、等待与日志轮询 |
| `client.py` | 公共调用接口、执行顺序和资源关闭 |
| `protocol.py` | 请求校验与编码、响应解释和文件写入 |
| `transport.py`、`auth.py` | HTTP 生命周期、有限重试和逐次签名 |
| `catalog.py`、`data/catalog.json` | 固定 SDK 的操作、字段、类型和协议支持状态 |
| `context.py`、`time_input.py` | 命名范围解析与无浮点纳秒转换，CLI context 不进入 Python 客户端 |
| `diagnostics.py` | 只读本地/API/SSH 检查，返回有界证据，不自动修复 |
| `config.py`、`ssh.py` | 账号与连接配置、本机 SSH 进程 |
| `skill_install.py` | 包内 Skill 的安装、冲突检查和卸载 |

## 一次请求

命令解析参数，业务层按平台字段构造请求；Python 使用者直接调用 `YicloudClient`。`prepare_request` 校验字段并生成查询字符串和请求体字节，dry-run 在此返回。按名称定位需要先执行只读查询，按 ID 则无需查询。

传输层使用同一份查询和请求体签名、投递。只读请求最多附加重试两次，写请求不自动重试。响应层分别处理平台信封、直接 JSON、空响应和文件下载，错误保留请求 ID 及结果未知标记。CLI 输出脱敏；Python 调用者自行处理成功数据和原始响应。

## 设计取舍

- **目录驱动 API，显式设计命令。** 目录覆盖公开接口，常用命令只展示当前操作支持的选项，避免为每个接口写一套客户端方法。
- **复用业务规则。** 命令层不决定批量删除格式、字段大小写或状态终态；这些规则可独立测试。
- **保留平台差异。** Ray 使用 JobName，部署使用 ID；不假设不同服务共享响应结构，也不从 Pod IP 推导 SSH 网关。
- **同步客户端与原生 SSH。** 当前工作流无需异步框架；原生 SSH 保留主机密钥校验、stdin 和远端退出码。
- **Skill 按任务加载。** 入口提供路由，参考资料保存平台特有知识，模板随安装包携带。接口描述只展开请求引用的类型。

## 边界与兼容

公共入口为 `yicloud`、`python -m yicloud` 和 `from yicloud import YicloudClient, Result, YicloudError`。账号和 SSH 配置格式与 JSON 信封需要兼容；用户可见变化记录在 CHANGELOG。

文件下载目前先读取完整 HTTP 响应，再原子写入目标，不是流式下载。Skill 安装先预检所有目标再逐目标替换，不提供磁盘故障下的跨目标事务。日志轮询不是可靠归档通道。真实平台验证范围见 [API 说明](../src/yicloud/skill/references/api.md)。

开发、目录生成和包外安装检查见 [贡献指南](../CONTRIBUTING.md)。

Context 仅注入便利命令缺失的范围，不改写请求文件或 api call。使用方式见[开发工具](../src/yicloud/skill/references/developer-tools.md)。
