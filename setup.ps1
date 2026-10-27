# setup.ps1 - creates .venv and installs requirements (Windows, Python 3.10+).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
& $py -c "import sys; sys.exit(sys.version_info < (3, 10))" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.10+ not found. Install it from python.org (tick 'Add Python to PATH') and rerun."
}

if (-not (Test-Path .venv)) { & $py -m venv .venv }
$venvPy = ".venv\Scripts\python.exe"

& $venvPy -m pip install --upgrade pip
& $venvPy -m pip install -r requirements.txt
& $venvPy -c "import pywinauto, win32gui, keyboard, dearpygui.dearpygui, PIL"

Write-Host "Done. Run: .venv\Scripts\activate ; python main.py" -ForegroundColor Green