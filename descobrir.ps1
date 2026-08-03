$ErrorActionPreference = "Stop"
Write-Host "MODO SEGURO LOCAL: procurando a sandbox 'D:\Marina'." -ForegroundColor Cyan
& .\.venv\Scripts\python.exe tools\instrumentacao_image_manager.py discover
