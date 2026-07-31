$ErrorActionPreference = "Stop"

Write-Host "Instrumentation Image Manager - instalação" -ForegroundColor Cyan
py -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
Write-Host "Instalação concluída." -ForegroundColor Green
Write-Host "Teste primeiro com: .\descobrir.ps1"
