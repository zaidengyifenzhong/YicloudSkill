# Run a reviewed local checkout: .\install.ps1 -Target codex
[CmdletBinding()]
param(
    [ValidateSet('auto','uv','pipx','venv')][string]$Manager = 'auto',
    [ValidatePattern('^[a-z][a-z0-9-]*$')][string]$Target = 'auto',
    [string]$Source = $PSScriptRoot,
    [string]$Venv = (Join-Path $HOME '.local/share/yicloud-skill/venv')
)
$ErrorActionPreference = 'Stop'
function Assert-Native([string]$Message) {
    if ($LASTEXITCODE -ne 0) { throw $Message }
}
if ($Source.StartsWith('-')) { throw 'Source must not be an option' }
if ($Manager -eq 'auto') {
    if (Test-Path (Join-Path $Venv 'pyvenv.cfg')) { $Manager = 'venv' }
    elseif (Get-Command uv -ErrorAction SilentlyContinue) { $Manager = 'uv' }
    elseif (Get-Command pipx -ErrorAction SilentlyContinue) { $Manager = 'pipx' }
    else { $Manager = 'venv' }
}
if ($Manager -eq 'uv') {
    $BinDir = & uv tool dir --bin
    Assert-Native 'Cannot locate uv tool bin directory'
    $Cli = Join-Path $BinDir.Trim() 'yicloud.exe'
} elseif ($Manager -eq 'pipx') {
    $BinDir = & pipx environment --value PIPX_BIN_DIR
    Assert-Native 'Cannot locate pipx tool bin directory'
    $Cli = Join-Path $BinDir.Trim() 'yicloud.exe'
} else {
    $Cli = Join-Path $Venv 'Scripts/yicloud.exe'
}
$Existing = Get-Command yicloud -ErrorAction SilentlyContinue
if ($Existing -and ([IO.Path]::GetFullPath($Existing.Source) -ne [IO.Path]::GetFullPath($Cli))) {
    throw "Another yicloud is on PATH at $($Existing.Source). Use its yicloud update or select its original manager/environment; no second CLI installed."
}
if ($Manager -eq 'uv') {
    & uv tool install --upgrade --force --reinstall $Source
    Assert-Native 'CLI installation failed'
} elseif ($Manager -eq 'pipx') {
    & pipx install --force $Source
    Assert-Native 'CLI installation failed'
} else {
    if (-not (Test-Path $Venv)) {
        & python -c 'import sys; assert sys.version_info >= (3, 10)'
        Assert-Native 'Python 3.10+ is required'
        & python -m venv $Venv
        Assert-Native 'Cannot create standalone venv'
    }
    if (-not (Test-Path (Join-Path $Venv 'pyvenv.cfg'))) { throw "Not a standalone venv: $Venv" }
    $Python = Join-Path $Venv 'Scripts/python.exe'
    & $Python -I -m pip install --upgrade --force-reinstall $Source
    Assert-Native 'CLI installation failed'
}
& $Cli --version
Assert-Native 'CLI entry point verification failed'
if ($Target -ne 'none') {
    & $Cli skill install --target $Target
    Assert-Native 'Skill installation failed; check local edits or directory conflicts'
    & $Cli skill status --target $Target
    Assert-Native 'Skill status failed'
}
& $Cli doctor local
Assert-Native 'Local installation validation failed'
if (-not (Get-Command yicloud -ErrorAction SilentlyContinue)) {
    Write-Warning "Installation verified. Add $(Split-Path $Cli) to PATH and reopen the terminal. Until then use: & '$Cli'"
}
