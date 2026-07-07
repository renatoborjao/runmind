# start.ps1 - sobe backend (uvicorn) + tunel ngrok em janelas separadas.
# Uso: na raiz do projeto, rodar  .\start.ps1

$ErrorActionPreference = 'Stop'

$backend = 'C:\Users\renat\Documents\runmind\backend'
$ngrokDomain = 'unopened-employed-cedar.ngrok-free.dev'
$port = 8000

Write-Host 'Subindo RunMind (backend + ngrok)...' -ForegroundColor Cyan

# Terminal 1: backend FastAPI
Start-Process powershell -ArgumentList @(
    '-NoExit', '-Command',
    "cd '$backend'; python -m uvicorn app.main:app --reload --host 0.0.0.0 --port $port"
)

# Terminal 2: tunel ngrok no dominio estatico
Start-Process powershell -ArgumentList @(
    '-NoExit', '-Command',
    "ngrok http --url=$ngrokDomain $port"
)

Write-Host ''
Write-Host 'Duas janelas abriram:' -ForegroundColor Green
Write-Host "  1) backend  -> http://127.0.0.1:$port"
Write-Host "  2) ngrok    -> https://$ngrokDomain"
Write-Host ''
Write-Host 'Teste rapido: curl.exe http://127.0.0.1:8000/api/v1/health'
