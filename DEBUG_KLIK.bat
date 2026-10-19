@echo off
REM Jalankan program dengan logger klik-kanan AKTIF (buat diagnosa).
REM Lakukan gesture jempol+kelingking beberapa kali, lalu tekan 'q'.
REM Hasilnya tersimpan di debug_klik.log
title Hand Gesture Mouse - DEBUG klik kanan
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PY="
for %%V in (3.12 3.11 3.10) do if not defined PY (
    py -%%V -c "" >nul 2>nul && set "PY=py -%%V"
)
if not defined PY (
    python -c "import sys;raise SystemExit(0 if (3,10)<=sys.version_info[:2]<=(3,12) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY ( echo [ERROR] Python tidak ketemu, jalankan SETUP.bat dulu. & pause & exit /b 1 )

set "PKG="
if exist "%~dp0libs\mediapipe" set "PKG=%~dp0libs"
if not defined PKG if exist "%~dp0venv\Lib\site-packages\mediapipe" set "PKG=%~dp0venv\Lib\site-packages"
if not defined PKG ( echo [ERROR] Paket belum ada, jalankan SETUP.bat dulu. & pause & exit /b 1 )
set "PYTHONPATH=%PKG%"

set "HGM_DEBUG=1"
echo ====================================================
echo   MODE DEBUG KLIK KANAN
echo   1. Tunggu window kamera muncul.
echo   2. Cubit jempol + kelingking 5-10x (coba klik kanan).
echo   3. Tekan 'q' untuk keluar.
echo   4. Kirim isi file debug_klik.log
echo ====================================================
echo.
!PY! hand_mouse.py
echo.
echo Selesai. Log ada di: %~dp0debug_klik.log
pause
