$ErrorActionPreference = "Stop"
$Root = "\\LABOCEANOSERVER\laboceano\Projetos"
Write-Host "ATENÇÃO: este comando renomeará apenas imagens classificadas com confiança suficiente." -ForegroundColor Yellow
Write-Host "Imagens marcadas REVISAR permanecerão intactas." -ForegroundColor Yellow
$ok = Read-Host "Digite APLICAR para continuar"
if ($ok -ne "APLICAR") {
    Write-Host "Cancelado."
    exit 0
}
& .\.venv\Scripts\python.exe tools\instrumentacao_image_manager.py apply $Root --manifest resultado_apply.csv
