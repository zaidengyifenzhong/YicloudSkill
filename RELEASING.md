# GitHub distribution

项目通过 GitHub 分发。默认安装与 `yicloud update` 跟踪 `main`，普通代码提交即可供安装和更新；版本快照是可选流程。

更新器按 [GitHub commit API](https://docs.github.com/en/rest/commits/commits#get-a-commit) 获取 `main` 的完整 SHA，从该 SHA 读取项目元数据，再安装同一 SHA。通过标准 [direct_url.json](https://packaging.python.org/en/latest/specifications/direct-url-data-structure/) 核对安装提交，因此版本相同、提交变化时仍能更新。

## Normal changes

提交代码并通过 CI 后即可通过 GitHub 源码安装和更新。`pyproject.toml` 的版本同时标识 SDK、CLI 和内置 Skill；提交 SHA 标识同版本下的精确代码。无需为每次提交创建版本。

## Optional version snapshots

需要固定快照和可下载 wheel/sdist 时，使用 `vX.Y.Z` tag；tag 必须与 `pyproject.toml` 版本完全一致。先执行：

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

`dist` 只能包含本次版本的一个 wheel 和一个 sdist；旧产物先移至其他目录。构建工具默认从 sdist 构建 wheel，内容检查覆盖版本、入口和 Skill 资产。

真实管理器的受控安装与更新检查需要 Git、uv、pipx，以及预先下载的运行/构建依赖：

```sh
python -m pip download --dest wheelhouse dist/yicloud_skill-0.4.0-py3-none-any.whl 'setuptools>=77' pip
python tools/verify_wheel.py dist --wheelhouse wheelhouse
python tools/check_installer.py dist --wheelhouse wheelhouse --manager uv
python tools/check_installer.py dist --wheelhouse wheelhouse --manager pipx
python tools/check_installer.py dist --wheelhouse wheelhouse --manager venv
python tools/check_updater.py dist --wheelhouse wheelhouse
```

测试使用临时本地 Git 仓库，构造同一包版本的两个提交，并调用真实管理器和 CLI；验证提交升级、多 Agent 同步、编辑保护、配置保持及重复更新跳过。准备依赖后无需外网，不使用云凭据或用户 Agent 目录。

通过审核并获得维护者发布授权后，可创建快照：

```sh
git tag -a v0.4.0 -m 'Release 0.4.0'
git push origin v0.4.0
```

这些是维护者操作说明，普通代码推送不会创建 tag 或 Release。

## GitHub workflow

`release.yml` 在 `v*` tag 上触发，复用跨平台 CI，构建 wheel/sdist、校验版本和内容、执行 Twine 检查，再创建 GitHub Release 并上传同一批产物。任何步骤失败都阻断后续发布，不静默忽略缺失产物。

需要启用 GitHub Actions，并允许 Release job 的 `contents: write`。建议保护 `v*` tag 及发布工作流；无需配置第三方包发布服务。若 Release 创建或上传失败，维护者检查原 artifact 与 Release 状态后补齐，不移动已公开的 tag。

默认更新始终跟踪 `main`。固定版本用户可以手动安装 tag，并避免运行自动更新；本地 wheel 和 editable 安装继续通过原安装流程维护。
