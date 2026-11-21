# SPDX-License-Identifier: Apache-2.0
# Native Windows setup with visible progress. Never unattended or silent.
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Write-Host 'tdtnext Windows setup: Python, isolated environment, and firmware extraction tools.'

$python = $null
$pythonArgs = @()
$launcher = Get-Command py.exe -ErrorAction SilentlyContinue
if ($launcher) {
    & $launcher.Source -3 -c 'import sys; assert sys.version_info >= (3, 10)' 2>$null
    if ($LASTEXITCODE -eq 0) {
        $python = $launcher.Source
        $pythonArgs = @('-3')
    }
}
if (-not $python) {
    $available = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($available) {
        & $available.Source -c 'import sys; assert sys.version_info >= (3, 10)' 2>$null
        if ($LASTEXITCODE -eq 0) { $python = $available.Source }
    }
}
if (-not $python) {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) { throw 'Python 3.10+ is missing and winget is unavailable. Install Python from python.org first.' }
    Write-Host 'Python 3.10+ is missing. Installing Python 3.12 with visible winget progress.'
    & $winget.Source install --id Python.Python.3.12 --exact --source winget
    if ($LASTEXITCODE -ne 0) { throw 'Python installation failed.' }
    Write-Host 'Python installation finished. Open a new terminal and run install-windows.cmd again so PATH is refreshed.'
    exit 2
}

$root = Join-Path $env:LOCALAPPDATA 'tdtnext'
$venv = Join-Path $root 'venv'
New-Item -ItemType Directory -Path $root -Force | Out-Null
if (-not (Test-Path (Join-Path $venv 'Scripts\python.exe'))) {
    Write-Host 'Creating isolated Python environment (no system site-packages changed)...'
    & $python @pythonArgs -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}
$venvPython = Join-Path $venv 'Scripts\python.exe'
Write-Host 'Installing tdtnext with visible pip output...'
& $venvPython -m pip install --upgrade $repo
if ($LASTEXITCODE -ne 0) { throw 'pip installation failed.' }
$scripts = Join-Path $venv 'Scripts'
$oldPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (-not $oldPath) { $oldPath = '' }
$pathParts = @($oldPath.Split(';') | Where-Object { $_ -and $_.Trim() })
if (-not (@($pathParts | Where-Object { $_.TrimEnd('\') -ieq $scripts.TrimEnd('\') }).Count)) {
    [Environment]::SetEnvironmentVariable('Path', (($pathParts + $scripts) -join ';'), 'User')
    Write-Host ('Added ' + $scripts + ' to your user PATH (new terminal sessions).')
}
$env:PATH = $scripts + ';' + $env:PATH
$tdtnext = Join-Path $scripts 'tdtnext.exe'
Write-Host 'Installing extraction dependencies (WSL may require a reboot on first setup)...'
& $tdtnext --setup-tools
if ($LASTEXITCODE -ne 0) {
    Write-Warning 'The core tdtnext program is installed, but some extraction tools still require setup. '
    Write-Warning 'If prompted, finish Ubuntu/WSL initialization or reboot Windows and run tdtnext --setup-tools again.'
    exit 3
}
Write-Host 'tdtnext installation complete.'
& $tdtnext --help
