$ErrorActionPreference = "Stop"
$Root = "\\LABOCEANOSERVER\laboceano\Projetos"
& .\.venv\Scripts\python.exe tools\instrumentacao_image_manager.py discover $Root
