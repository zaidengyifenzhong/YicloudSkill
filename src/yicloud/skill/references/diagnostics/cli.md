# CLI 安装、上下文与诊断

## 何时读取

命令缺失、参数不被接受、Skill 与 CLI 不一致或需要定位本地/API/SSH 故障时读取。

## 按故障选择检查

| 问题 | 检查 |
|---|---|
| 命令参数不接受 | 对应子命令 `--help`，全局选项放在子命令之前 |
| Skill 与当前 CLI 不一致 | `skill status --target all` |
| 包、配置、工具路径 | `doctor local`，不访问平台或 SSH |
| 当前 API 访问与项目读取 | `doctor api`，不证明写权限或实时容量 |
| 具体远端机器异常 | `workspace doctor` 或 `job doctor`，见[远程排错](../workspace/troubleshoot.md) |

根据缺口选择，不要求每次执行所有诊断。context show 用于检查来源，认证冲突时仍可显示安全的冲突信息；账号配置见[访问手册](../access.md)。

## 输出判断

根级 `--json` 成功信封是 ok/data/meta；错误信封写 stderr。诊断单项状态是 pass/fail/unknown/skipped，有 fail 时退出 1，没有 fail 不代表 unknown/skipped 已通过。

普通平台命令退出 0/1；Ctrl-C 返回 130；SSH/SCP 保留原生流和退出码。不要从“有输出”推断成功，检查退出状态和实际结果。

## 同步 Skill

CLI 更新后运行 `skill install --target all` 同步受管理安装。status 的 matching 表示文件匹配；different 可能是旧包，local_edits/conflict 需要保留用户修改，不能强行覆盖。安装器负责移除旧版受管理文件，不自行清空技能目录。

## 完成标准

分别报告本地工具、API、SSH 和目标环境的结果。修复语法或同步 Skill 后重试受影响的最小命令，不把参数错误当成认证错误，不顺带修改用户无关配置。
