#!/usr/bin/env bash
# Run a reviewed local checkout: bash install.sh --target codex
set -euo pipefail
manager=auto
target=all
source_spec=yicloud-skill
venv_dir="${HOME}/.local/share/yicloud-skill/venv"
while (($#)); do
  case "$1" in
    --manager|--target|--source|--venv)
      [[ $# -ge 2 ]] || { echo "Missing value for $1" >&2; exit 2; }
      case "$1" in --manager) manager=$2 ;; --target) target=$2 ;; --source) source_spec=$2 ;; --venv) venv_dir=$2 ;; esac
      shift 2 ;;
    --help|-h) echo 'install.sh [--manager auto|uv|pipx|venv] [--target codex|claude|all|none] [--source PACKAGE_OR_WHEEL] [--venv PATH]'; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
case "$target" in codex|claude|all|none) ;; *) echo 'Invalid target' >&2; exit 2 ;; esac
case "$manager" in auto|uv|pipx|venv) ;; *) echo 'Invalid manager' >&2; exit 2 ;; esac
[[ $source_spec != -* ]] || { echo 'Source must not be an option' >&2; exit 2; }
# Existing standalone environments take priority over newly installed managers.
if [[ $manager == auto ]]; then
  if [[ -f "$venv_dir/pyvenv.cfg" ]]; then manager=venv
  elif command -v uv >/dev/null 2>&1; then manager=uv
  elif command -v pipx >/dev/null 2>&1; then manager=pipx
  else manager=venv; fi
fi
case "$manager" in
  uv)
    command -v uv >/dev/null || { echo 'uv not found' >&2; exit 1; }
    bin_dir=$(uv tool dir --bin)
    cli="$bin_dir/yicloud" ;;
  pipx)
    command -v pipx >/dev/null || { echo 'pipx not found' >&2; exit 1; }
    bin_dir=$(pipx environment --value PIPX_BIN_DIR)
    cli="$bin_dir/yicloud" ;;
  venv)
    cli="$venv_dir/bin/yicloud" ;;
esac
existing=$(command -v yicloud || true)
if [[ -n $existing && $existing != "$cli" ]]; then
  echo "Another yicloud is on PATH at $existing. Use that installation's yicloud update, or select its original manager/environment; no second CLI installed." >&2
  exit 1
fi
case "$manager" in
  uv) uv tool install --upgrade --force "$source_spec" ;;
  pipx) pipx install --force "$source_spec" ;;
  venv)
    if [[ ! -e $venv_dir ]]; then
      command -v python3 >/dev/null || { echo 'Python 3.10+ is required' >&2; exit 1; }
      python3 -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10+ is required"'
      python3 -m venv "$venv_dir"
    fi
    [[ -f "$venv_dir/pyvenv.cfg" && -x "$venv_dir/bin/python" ]] || { echo "Not a standalone venv: $venv_dir" >&2; exit 1; }
    "$venv_dir/bin/python" -I -m pip install --upgrade "$source_spec" ;;
esac
"$cli" --version
if [[ $target != none ]]; then
  "$cli" skill install --target "$target"
  "$cli" skill status --target "$target"
fi
"$cli" doctor local
if ! command -v yicloud >/dev/null 2>&1; then
  echo "Installation verified. Add $(dirname "$cli") to PATH; then reopen your terminal. Until then, use: $cli" >&2
fi
