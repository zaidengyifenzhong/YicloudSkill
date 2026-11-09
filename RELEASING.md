# Release maintenance

`pyproject.toml` 中的版本同时标识 SDK、CLI 和内置 Skill。正式版本为 `X.Y.Z`，tag 为 `vX.Y.Z`；发布构建拒绝不一致、预发布或非规范版本。`0.4.0` 是本次改造准备的版本号，不表示已经上线。

## One-time configuration

1. 确认 PyPI 项目名 `yicloud-skill` 可用且由维护者控制。尚未建项目时可使用 PyPI pending publisher；不要向同名的第三方项目上传。
2. 在 GitHub 创建 `pypi` environment，设置 required reviewers、只允许正式 tag 部署，并保护 `v*` tag 的创建权限和发布工作流修改权限。
3. 在 PyPI 配置 GitHub Trusted Publisher：owner `zaidengyifenzhong`，repository `YicloudSkill`，workflow filename `release.yml`，environment `pypi`。不配置长期 PyPI Token。
4. 允许 GitHub Actions 运行可复用 CI，以及发布 job 的 `id-token: write` 和 GitHub Release job 的 `contents: write`。发布使用同一工作流构建出的 artifact，上传/下载失败会阻断后续步骤。
5. 首次可在单独的测试工作流及 TestPyPI 项目配置对应 publisher 进行演练；本仓库正式工作流默认目标是生产 PyPI，没有静默跳过上传的开关。

参考 [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/) 与 [安全模型](https://docs.pypi.org/trusted-publishers/security-model/)。

## Preparing a release

更新版本、README 中的固定版本示例及相关发行说明。先确认没有同版本的发行产物，再执行：

```sh
python -m pip install -e '.[dev]' twine
python -m ruff check src tests tools
python -m ruff format --check src tests tools
python -m pytest -q
python tools/check_catalog.py
python tools/validate_skill.py
python tools/evaluate_skill.py
python -m build
python tools/check_release.py --tag v0.4.0
python -m twine check dist/*
```

`dist` 应只包含本次版本的一个 wheel 和一个 sdist；旧产物应先移至其他目录。用新的隔离环境验证从 sdist 构建的 wheel。完整 CI 还检查三种操作系统的独立安装与更新；离线管理器回归可执行：

```sh
python -m pip download --dest wheelhouse dist/yicloud_skill-0.4.0-py3-none-any.whl
python tools/verify_wheel.py dist --wheelhouse wheelhouse
python tools/check_installer.py dist --wheelhouse wheelhouse --manager uv
python tools/check_installer.py dist --wheelhouse wheelhouse --manager pipx
python tools/check_installer.py dist --wheelhouse wheelhouse --manager venv
python tools/check_updater.py dist --wheelhouse wheelhouse
```

回归需要已有 uv/pipx；测试不下载管理器、不使用云凭据。更新 fixture 是当前代码改写版本元数据到 0.3.1，验证的是旧版本环境到新发行包的交接协议。历史 0.3.1 本身不含 `update`，真实用户须按 README 做一次引导升级。

通过评审并获维护者正式发布授权后：

```sh
git tag -a v0.4.0 -m 'Release 0.4.0'
git push origin v0.4.0
```

这些命令是维护者操作说明，代码改造不执行它们。

## Workflow and failures

`release.yml` 按 tag 触发，先完整运行可复用 CI，再构建 wheel/sdist、校验版本和 Skill 内容、运行 Twine 检查，上传构建 artifact。PyPI job 仅以 OIDC 获取短期凭据。PyPI 成功后才创建 GitHub Release 并上传同一批 wheel/sdist；没有配置 publisher 时工作流明确失败，不伪造发布成功。

如果 PyPI 已成功而 GitHub Release 步骤失败，修复权限后仅重跑失败的 GitHub job，或由维护者从原 artifact 手动补齐 Release。不要重传 PyPI 同版本，不移动已发布 tag。PyPI 上传一部分产物后失败也必须先审查公开文件及 artifact，不能通过 `skip-existing` 隐藏不完整发行。

更新器优先 PyPI，仅在 PyPI 项目 404 时回退官方 GitHub Release 的稳定 tag。如果选择仅 GitHub 发布，需要维护者另行明确操作及验证；本工作流不会在 PyPI 失败后自动降级发布。

发布后从 PyPI 安装、执行 `--version`、`doctor local`、安装 Skill，再从上一个正式版本运行 `update --check` / `update`，核对版本和本地 Skill。生产 PyPI、GitHub Release 及跨机升级都需要实际执行后才能记录为通过。
