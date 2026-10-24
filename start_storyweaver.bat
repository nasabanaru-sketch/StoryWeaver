@echo off
setlocal enabledelayedexpansion
set MODELSCOPE_OFFLINE=1
title StoryWeaver Live Launcher

cd /d "%~dp0"

echo ===================================================
echo   StoryWeaver Live 起動ランチャー
echo ===================================================
echo.

set "PYTHON_EXE=C:\Users\nasab\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
if not exist "!PYTHON_EXE!" (
    set "PYTHON_EXE=python"
)

echo [1/3] サーバーを別ウィンドウで起動しています...
start "StoryWeaver Live Server" cmd /k ""!PYTHON_EXE!" -m uvicorn server:app --host 0.0.0.0 --port 8000"

echo [2/3] サーバーとAIモデルの初期化を待機しています...
:wait_loop
ping 127.0.0.1 -n 3 > nul
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 2 -UseBasicParsing; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }"
if !ERRORLEVEL! equ 0 (
    goto server_ready
)
echo       SenseVoice と 12感情モデルをロード中... お待ちください...
goto wait_loop

:server_ready
echo.
echo [3/3] サーバー起動完了を確認しました！
echo       ブラウザ (http://127.0.0.1:8000/) を開きます...
start http://127.0.0.1:8000/

echo.
echo ===================================================
echo   StoryWeaver Live が正常に起動しました！
echo   ※ 終了する際は [StoryWeaver Live Server] ウィンドウ
echo      を閉じるか、Ctrl+C を押してください。
echo ===================================================
ping 127.0.0.1 -n 5 > nul
exit

