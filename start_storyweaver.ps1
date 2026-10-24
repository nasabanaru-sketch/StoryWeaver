# StoryWeaver Live Launcher (PowerShell版)
$ErrorActionPreference = "Stop"

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  StoryWeaver Live 起動ランチャー (PowerShell)" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$PythonExe = "C:\Users\nasab\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python"
}

Write-Host "[1/3] サーバーを別ウィンドウで起動しています..." -ForegroundColor Yellow
Start-Process cmd.exe -ArgumentList "/k", "`"$PythonExe`" -m uvicorn server:app --host 0.0.0.0 --port 8000"

Write-Host "[2/3] サーバーとAIモデルの初期化を待機しています..." -ForegroundColor Yellow
$maxAttempts = 30
$attempt = 0
$serverReady = $false

while ($attempt -lt $maxAttempts) {
    Start-Sleep -Seconds 2
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 2 -UseBasicParsing
        if ($resp.StatusCode -eq 200) {
            $serverReady = $true
            break
        }
    } catch {
        Write-Host "      SenseVoice と 12感情モデルをロード中... お待ちください..." -ForegroundColor Gray
    }
    $attempt++
}

if ($serverReady) {
    Write-Host ""
    Write-Host "[3/3] サーバー起動完了を確認しました！" -ForegroundColor Green
    Write-Host "      ブラウザ (http://127.0.0.1:8000/) を開きます..." -ForegroundColor Green
    Start-Process "http://127.0.0.1:8000/"

    Write-Host ""
    Write-Host "===================================================" -ForegroundColor Cyan
    Write-Host "  StoryWeaver Live が正常に起動しました！" -ForegroundColor Green
    Write-Host "  ※ 終了する際は [cmd.exe] のサーバーウィンドウで" -ForegroundColor Gray
    Write-Host "     Ctrl+C を押すかウィンドウを閉じてください。" -ForegroundColor Gray
    Write-Host "===================================================" -ForegroundColor Cyan
} else {
    Write-Host "エラー: サーバーの起動待機がタイムアウトしました。" -ForegroundColor Red
}
