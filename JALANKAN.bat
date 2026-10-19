@echo off
REM ============================================================
REM  Hand Gesture Mouse Controller - Launcher
REM  Klik 2x file ini untuk menjalankan program.
REM  Belum pernah setup? Jalankan SETUP.bat dulu (sekali saja).
REM
REM  Catatan: dijalankan pakai Python "asli" (py/python), BUKAN copy di
REM  dalam venv -- di sebagian laptop proteksi webcam antivirus (McAfee/AVG)
REM  memblokir exe venv mengakses kamera, tapi python asli diizinkan.
REM  Paket diambil dari folder "libs" (hasil SETUP.bat) via PYTHONPATH.
REM ============================================================
title Hand Gesture Mouse Controller
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM ---------- cari interpreter Python 3.10-3.12 ----------
set "PY="
for %%V in (3.12 3.11 3.10) do if not defined PY (
    py -%%V -c "" >nul 2>nul && set "PY=py -%%V"
)
if not defined PY (
    python -c "import sys;raise SystemExit(0 if (3,10)<=sys.version_info[:2]<=(3,12) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY goto NOPY

REM ---------- cari folder paket: libs (SETUP) atau venv lama ----------
set "PKG="
if exist "%~dp0libs\mediapipe" set "PKG=%~dp0libs"
if not defined PKG if exist "%~dp0venv\Lib\site-packages\mediapipe" set "PKG=%~dp0venv\Lib\site-packages"
if not defined PKG goto NODEPS
set "PYTHONPATH=%PKG%"

REM ---------- pastikan import inti jalan ----------
!PY! -c "import cv2, mediapipe, numpy" 2>nul
if errorlevel 1 goto NODEPS

echo ============================================================
echo   HAND GESTURE MOUSE CONTROLLER
echo ============================================================
echo.
echo Kontrol:
echo   - Telunjuk naik                : Gerakkan pointer
echo   - Cubit jempol + manis         : Klik kiri
echo   - Cubit jempol + kelingking    : Klik kanan
echo   - Cubit jempol+telunjuk + usap : Scroll
echo   - 3 jari + jempol-kelingking   : Voice typing (kalau terpasang)
echo   - Tekan 'q' di window          : Keluar
echo.
echo Mencari webcam, tunggu sebentar...
echo.

!PY! hand_mouse.py

echo.
if errorlevel 1 (
    echo [GAGAL] Program berhenti karena error. Baca pesan di atas.
) else (
    echo [SELESAI] Program ditutup normal.
)
echo.
pause
exit /b 0

:NOPY
echo ============================================================
echo   [ERROR] Python 3.10-3.12 tidak ditemukan
echo ============================================================
echo.
echo Jalankan SETUP.bat dulu (dia bisa pasang Python otomatis),
echo atau pasang Python 3.12 dari https://www.python.org/downloads/
echo.
pause
exit /b 1

:NODEPS
echo ============================================================
echo   [ERROR] Kebutuhan belum terpasang
echo ============================================================
echo.
echo Jalankan SETUP.bat dulu (sekali saja) untuk mengunduh semua kebutuhan.
echo.
pause
exit /b 1
