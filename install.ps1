[CmdletBinding()]
param(
    [ValidateSet('auto','uv','pipx')][string]$Manager = 'auto',
    [ValidateSet('codex','claude','all')][string]$Target = 'all',
    [string]$Source = 'git+https://github.com/zaidengyifenzhong/YicloudSkill.git@main'
)
$ErrorActionPreference = 'Stop'
if ($Manager -eq 'auto') {
    if (Get-Command uv -ErrorAction SilentlyContinue) { $Manager = 'uv' }
    elseif (Get-Command pipx -ErrorAction SilentlyContinue) { $Manager = 'pipx' }
    else { throw 'Install uv or pipx first, then rerun this installer.' }
}
if ($Manager -eq 'uv') {
    & uv tool install --python 3.12 --upgrade $Source
    if ($LASTEXITCODE -ne 0) { throw 'CLI installation failed' }
    $BinDir = & uv tool dir --bin
    if ($LASTEXITCODE -ne 0) { throw 'Cannot locate uv tool bin directory' }
} else {
    & pipx install --force $Source
    if ($LASTEXITCODE -ne 0) { throw 'CLI installation failed' }
    $BinDir = & pipx environment --value PIPX_BIN_DIR
    if ($LASTEXITCODE -ne 0) { throw 'Cannot locate pipx bin directory' }
}
$Cli = Join-Path $BinDir.Trim() 'yicloud.exe'
& $Cli skill install --target $Target
if ($LASTEXITCODE -ne 0) { throw 'Skill installation failed; check for an existing unmanaged skill' }
