$ErrorActionPreference = "Stop"
$Root = "\\LABOCEANOSERVER\laboceano\Projetos"
& .\.venv\Scripts\python.exe tools\instrumentacao_image_manager.py classify $Root --manifest resultado_classificacao.csv
Write-Host "Abra resultado_classificacao.csv e revise antes de usar apply." -ForegroundColor Yellow
