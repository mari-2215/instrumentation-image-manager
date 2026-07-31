$ErrorActionPreference = "Stop"
Write-Host "ATENÇÃO: este comando atua SOMENTE na sandbox local 'Dados e Marina'." -ForegroundColor Yellow
Write-Host "Imagens marcadas REVISAR permanecerão intactas." -ForegroundColor Yellow
$ok = Read-Host "Digite APLICAR para permitir renomes na cópia local"
if ($ok -ne "APLICAR") {
    Write-Host "Cancelado."
    exit 0
}
& .\.venv\Scripts\python.exe tools\instrumentacao_image_manager.py apply --allow-rename --manifest resultado_apply.csv
