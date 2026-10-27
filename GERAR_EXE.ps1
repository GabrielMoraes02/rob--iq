$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonBuild = Join-Path $PSScriptRoot '.venv-build\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonBuild)) {
    $pythonBuild = Join-Path $PSScriptRoot '..\.venv-bot\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $pythonBuild)) { throw 'Prepare o ambiente conforme README_DESENVOLVEDOR.md.' }
& $pythonBuild gerar_exe.py
if ($LASTEXITCODE -ne 0) { throw 'Falha ao gerar o aplicativo.' }
