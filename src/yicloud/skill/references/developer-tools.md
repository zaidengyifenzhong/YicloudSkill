# 开发工具、上下文与诊断

遇到旧参数、缺失模板或版本不一致，先执行 `yicloud skill status --target all`。它只读比较当前包与安装目录的内容摘要，区分 missing、matching、different 和 conflict；列出本地修改。CLI 更新后用 `skill install` 同步，不能覆盖用户修改来掩盖冲突。

命名上下文只保存账号别名、项目和可用区，不保存凭据或执行脚本：

```bash
yicloud context set lab --account research --project PROJECT --zone ZONE
yicloud context use lab
yicloud context show
yicloud --context lab workspace list
yicloud --no-context account current
```

显式账号/项目/可用区优先于上下文。环境认证变量仍按原规则覆盖账号凭据；context show 显示来源。没有目录自动发现；api call、创建/列表的请求文件不注入项目与可用区。project list 不被当前项目过滤。移除 context 只移除本地范围配置；account use 不清除已选 context，必要时用 --no-context 或 context remove。

诊断按需要选择，已有证据足够时无需全部运行：

- `doctor local`：包版本、配置、工具位置、Skill 安装；不调用平台或 SSH。
- `doctor api`：可用区、已选项目的只读查询；不检查实时容量，不保证写权限。
- `workspace doctor CONNECTION` / `job doctor CONNECTION`：使用登记 SSH 连接检查基本执行、当前目录磁盘及 NVIDIA GPU；每项有超时，不修改环境。

检查结果为 pass/fail/unknown/skipped，含证据。有 fail 时 CLI 退出 1；没有 fail 只表示未确认失败，不代表 unknown/skipped 已通过。GPU 工具缺失、权限不足或探测超时不等于资源不存在。不自动修复镜像、重启机器或放宽主机密钥验证。

输出约定：--json 成功信封为 ok/data/meta（stdout）；命令异常为 ok/error（stderr），诊断中的单项失败仍在 data.checks 并退出 1。平台命令成功/失败退出 0/1，用户中断 130；SSH/SCP 保持原生流和退出码。JSON meta 可包含实际账号、网关、地域及项目/可用区的来源。--show-secrets 不是查看普通 token 计数指标的必要条件。
