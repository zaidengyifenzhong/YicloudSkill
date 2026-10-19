#!/usr/bin/env bash
set -euo pipefail
manager=auto
target=all
source_url='git+https://github.com/zaidengyifenzhong/YicloudSkill.git@main'
while (($#)); do
  case "$1" in
    --manager|--target|--source)
      [[ $# -ge 2 ]] || { echo "Missing value for $1" >&2; exit 2; }
      case "$1" in --manager) manager=$2 ;; --target) target=$2 ;; --source) source_url=$2 ;; esac
      shift 2 ;;
    --help|-h) echo 'install.sh [--manager auto|uv|pipx] [--target codex|claude|all] [--source GIT_URL]'; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
case "$target" in codex|claude|all) ;; *) echo 'Invalid target' >&2; exit 2 ;; esac
if [[ $manager == auto ]]; then
  if command -v uv >/dev/null 2>&1; then manager=uv
  elif command -v pipx >/dev/null 2>&1; then manager=pipx
  else echo 'Install uv or pipx first, then rerun this installer.' >&2; exit 1; fi
fi
case "$manager" in
  uv)
    command -v uv >/dev/null || { echo 'uv not found' >&2; exit 1; }
    uv tool install --python 3.12 --upgrade "$source_url"
    "$(uv tool dir --bin)/yicloud" skill install --target "$target" ;;
  pipx)
    command -v pipx >/dev/null || { echo 'pipx not found' >&2; exit 1; }
    pipx install --force "$source_url"
    "$(pipx environment --value PIPX_BIN_DIR)/yicloud" skill install --target "$target" ;;
  *) echo 'Invalid manager; choose auto, uv or pipx' >&2; exit 2 ;;
esac
