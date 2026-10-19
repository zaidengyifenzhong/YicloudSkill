# 通用 API 与维护

适用于便利命令未覆盖的接口、复杂嵌套输入和 SDK 更新。先 list/describe，使用官方字段准备 JSON，dry-run，再执行并查询实际状态。

```bash
yicloud api list
yicloud api list --service job
yicloud api describe job CreateJob
yicloud --account research api call job CreateJob --file job.json --dry-run
yicloud --account research --json api call job CreateJob --file job.json
```

`--file -` 从 stdin 读取 JSON 对象，无请求字段可省略文件；缺失、false、0、空字符串和 null 分别保留。检查 SDK binding 的 required、oneof、嵌套类型及 SDK 常量枚举；部分必填业务条件只在 SDK 注释中出现，需结合描述和官方文档判断。仅在明确需要服务端新增字段时使用 `--allow-unknown-fields`，不会开放任意 URL。

dry-run 只做本地校验并输出方法、URL、查询字段和请求体，既不验证平台权限，也不保留容量。写请求不会自动重试；只读调用最多附加重试两次。JSON 保留平台数据，错误区分 configuration/input/authentication/network/platform/unsupported_protocol，含 request_id 和 outcome_unknown。TLS 正常校验，重定向不自动跟随。文件响应必须 --output，完成后原子替换。

基准：[官方 Go SDK v0.5.1](https://gitee.com/yicloud-team/openapi-sdk-go/tree/8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5)，提交 `8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5`，文档核对 2026-10-19。227 个公开请求操作全部收录，225 个普通 HTTP 操作实现，2 个协议暂缓（GetInferSetTerminal、GetInferSetLogsTail）。帮助显示每项状态，未验证真实平台。

已知差异：fs/alpha 的真实产品、路径与直接响应需单独处理；Ray 历史日志 SDK 未定义数据类型，保留直接 JSON；部署日志下载 SDK 使用 Empty，客户端按文件保存；标量数组统一为重复查询键，避免 SDK 编码丢失数组元素。重复键的签名排序与官方算法一致，但服务端数组兼容性仅离线验证。对象上传下载另接 S3 工具，浏览器终端不模拟为成功。

维护者需要 Go（用户运行不需要）：从固定提交干净检出后，在仓库根目录执行：

```bash
go run tools/catalog.go /path/to/openapi-sdk-go > catalog.next.json
python tools/check_catalog.py catalog.next.json
```

生成器用 Go 标准库 AST 解析真实 client.Get/Post/GetRaw、路径表达式、请求模型、JSON/form/binding 标签和常量；拒绝非固定提交、已修改 SDK、无法解析路径/类型/公开操作。特殊响应覆盖在生成器中显式标注。检查 diff 后替换 src/yicloud/data/catalog.json，并用 `python tools/render_support.py` 更新支持矩阵；运行 pytest、Ruff、Skill 验证和 wheel 安装检查。更新基准时同时调整版本、SHA、来源、测试和差异说明，不能只改目录的头部版本号。
