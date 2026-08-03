$ErrorActionPreference = "Stop"
Write-Host "MODO SEGURO LOCAL: classificando somente a sandbox 'D:\Marina'." -ForegroundColor Cyan
& .\.venv\Scripts\python.exe tools\instrumentacao_image_manager.py classify --manifest resultado_classificacao.csv
Write-Host "Abra resultado_classificacao.csv e revise antes de qualquer apply." -ForegroundColor Yellow
