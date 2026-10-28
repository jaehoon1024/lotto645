$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    Write-Host 'Virtual environment missing. Follow README.md to install.'
    exit 1
}
& $projectPython -m streamlit run app.py --server.address 127.0.0.1
