@echo off
chcp 65001 >nul
title Referencia Certa - Servidor
cd /d "%~dp0"
echo.
echo ================================================
echo   REFERENCIA CERTA - INTERFACE WEB
echo ================================================
echo.
echo Iniciando o servidor local...
echo A interface sera aberta em http://127.0.0.1:8000
echo.
start "" powershell -NoProfile -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8000'"
python run.py
pause
