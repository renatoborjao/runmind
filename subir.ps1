# Sobe o RunMind inteiro: backend (uvicorn) + tunel (ngrok).
# Protegido contra dupla subida: se ja esta no ar, nao duplica.

$backendDir = "C:\Users\renat\Documents\runmind\backend"
$ngrokUrl = "unopened-employed-cedar.ngrok-free.dev"

# ---------- backend ----------
$portaOcupada = $null
try { $portaOcupada = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction Stop } catch {}

if ($portaOcupada) {

    Write-Host "[backend] JA ESTA NO AR na porta 8000 - nao vou duplicar." -ForegroundColor Yellow

} else {

    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "`$Host.UI.RawUI.WindowTitle = 'RunMind Backend'; cd '$backendDir'; python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
    )

    Write-Host "[backend] subindo na porta 8000..." -ForegroundColor Green
}

# ---------- ngrok ----------
$tunelVivo = $false
try {
    $r = Invoke-WebRequest -Uri "https://$ngrokUrl/docs" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
    if ($r.StatusCode -eq 200) { $tunelVivo = $true }
} catch {}

$ngrokRodando = Get-Process ngrok -ErrorAction SilentlyContinue

if ($tunelVivo -or $ngrokRodando) {

    Write-Host "[ngrok]   tunel JA ESTA VIVO - nao vou duplicar." -ForegroundColor Yellow

} else {

    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "`$Host.UI.RawUI.WindowTitle = 'RunMind ngrok'; ngrok http --url=$ngrokUrl 8000"
    )

    Write-Host "[ngrok]   subindo tunel $ngrokUrl..." -ForegroundColor Green
}

Write-Host ""
Write-Host "RunMind no ar: http://127.0.0.1:8000/docs  |  https://$ngrokUrl" -ForegroundColor Cyan
