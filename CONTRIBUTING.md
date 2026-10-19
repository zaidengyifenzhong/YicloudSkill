# 贡献指南

## 本地开发

需要 Python 3.10+。在仓库根目录执行：

```bash
uv sync --extra dev
uv run pytest
uv run ruff check src tests tools
uv run ruff format --check src tests tools
uv run python tools/check_catalog.py
uv run python tools/validate_skill.py
```

测试默认离线，使用合成数据和模拟 HTTP 传输，不读取真实平台账号。修改命令时验证实际参数、请求和失败行为；帮助文案无需逐字快照。增加接口覆盖测试不代表完成平台联测。

## 修改位置

[架构说明](docs/architecture.md)解释模块边界。命令适配位于 `src/yicloud/commands/`，工作负载规则位于 `creation.py` 和 `workflows.py`，API 编码与网络投递分别在 `protocol.py` 和 `transport.py`。

Skill 位于 `src/yicloud/skill/`：入口只保留路由和共有约束，任务细节放对应 reference，模板放 `assets/examples/`。避免重复 CLI 帮助、加载整份目录或将开发过程写入用户文档。

提交说明应包含问题、用户可见变化和验证结果。改变命令参数或输出时更新 CHANGELOG；不要在重构中顺带修改身份选择、远端写入语义或存储格式。

## 更新 API 目录

目录由官方 Go SDK v0.5.1 固定提交 `8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5` 生成。仅维护目录需要 Go，运行 CLI 不需要。

从该提交的干净检出生成候选文件：

```bash
go run tools/catalog.go /path/to/openapi-sdk-go > catalog.next.json
uv run python tools/check_catalog.py catalog.next.json
```

检查差异后替换 `src/yicloud/data/catalog.json`，运行 `uv run python tools/render_support.py` 更新支持矩阵。生成器解析真实方法、路径、请求类型和约束；少量 SDK 注释枚举由 `tools/catalog_overrides.json` 补齐。更新 SDK 基准时同步生成器、来源说明、签名向量和测试，不能仅修改版本字段。

## 构建与验证

```bash
uv run python -m build
uv run python tools/verify_wheel.py dist
```

`verify_wheel.py` 在仓库外创建独立环境，安装 wheel 后校验命令、Skill 和模板。可传入具体 wheel；传目录时要求其中只有一个本项目 wheel。依赖安装可用 `--wheelhouse PATH` 离线完成。CI 覆盖 Linux、macOS、Windows，另行对照 SDK 目录和 Go 签名向量。

版本号只在 `pyproject.toml` 中维护。发布前完成离线检查、包外验证与变更说明；平台验证范围按实际结果描述，不将模拟测试标为联测。

## 平台验证

普通测试不创建云资源。联测需明确账号、项目、可用区、临时资源、费用和清理范围。优先验证最小闭环：提交、观察、检查产物或服务响应、清理。保存脱敏后的可复现问题，必要时转为回归夹具；不提交凭据、真实资源台账或原始敏感响应。

仍需验证的范围包括训练、Ray、部署的写操作闭环，以及 Token 和服务账号认证。已知开发机列表与详情可见性差异见 [API 说明](src/yicloud/skill/references/api.md)。
