@echo off
REM ============================================================
REM  Hand Gesture Mouse - PEMASANG OTOMATIS (sekali jalan)
REM  Klik 2x file ini. Dia akan:
REM    1. Mencari Python 3.10-3.12 (pasang otomatis via winget kalau belum ada)
REM    2. Mengunduh semua kebutuhan ke folder "libs"
REM    3. Mengecek semuanya siap
REM  Setelah ini, cukup klik 2x JALANKAN.bat untuk memakai.
REM  Butuh internet HANYA saat setup pertama ini.
REM ============================================================
title Hand Gesture Mouse - Setup
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo   HAND GESTURE MOUSE - SETUP
echo ============================================================
echo.

REM ---------- 1. Cari interpreter Python 3.10-3.12 ----------
call :CARI_PY
if not defined PY (
    echo [INFO] Python 3.10-3.12 tidak ditemukan. Mencoba pasang otomatis...
    where winget >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] winget tidak ada, tidak bisa pasang Python otomatis.
        echo         Pasang Python 3.12 manual dari https://www.python.org/downloads/
        echo         ^(centang "Add python.exe to PATH"^), lalu jalankan SETUP.bat lagi.
        echo.
        pause
        exit /b 1
    )
    winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    echo.
    echo [INFO] Python terpasang. Mendeteksi ulang...
    call :CARI_PY
    if not defined PY (
        echo [INFO] Python sudah terpasang tapi belum kebaca di jendela ini.
        echo        TUTUP jendela ini lalu jalankan SETUP.bat SEKALI LAGI.
        echo.
        pause
        exit /b 0
    )
)
echo [OK] Memakai Python: !PY!
echo.

REM ---------- 2. Unduh semua kebutuhan ke folder "libs" ----------
set "LIBS=%~dp0libs"
echo [INFO] Mengunduh & memasang kebutuhan (gesture mouse, tanpa voice).
echo        Ukuran ~300-400MB, biarkan sampai selesai...
echo.
!PY! -m pip install --upgrade --target "%LIBS%" -r "%~dp0requirements-lite.txt"
if errorlevel 1 (
    echo.
    echo [ERROR] Pemasangan gagal ^(cek koneksi internet, lalu ulangi SETUP.bat^).
    echo.
    pause
    exit /b 1
)
echo.

REM ---------- 3. Verifikasi ----------
set "PYTHONPATH=%LIBS%"
!PY! -c "import cv2, mediapipe, numpy, pyautogui" 2>nul
if errorlevel 1 (
    echo [ERROR] Paket sudah terunduh tapi gagal di-import. Ulangi SETUP.bat.
    echo.
    pause
    exit /b 1
)

echo ============================================================
echo   [SELESAI] Semua siap!
echo   Mulai sekarang cukup klik 2x: JALANKAN.bat
echo ============================================================
echo.
pause
exit /b 0

REM ================= subrutin cari Python =================
:CARI_PY
set "PY="
for %%V in (3.12 3.11 3.10) do if not defined PY (
    py -%%V -c "" >nul 2>nul && set "PY=py -%%V"
)
if not defined PY (
    python -c "import sys;raise SystemExit(0 if (3,10)<=sys.version_info[:2]<=(3,12) else 1)" >nul 2>nul && set "PY=python"
)
goto :eof
