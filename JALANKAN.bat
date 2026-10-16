@echo off
REM ============================================
REM  Hand Gesture Mouse Controller - Launcher
REM  Klik 2x file ini untuk menjalankan program
REM ============================================
title Hand Gesture Mouse Controller

cd /d "%~dp0"

echo ============================================
echo   HAND GESTURE MOUSE CONTROLLER
echo ============================================
echo.
echo Kontrol:
echo   - Telunjuk naik           : Gerakkan pointer
echo   - Cubit jempol + manis    : Klik kiri
echo   - Cubit jempol + tengah   : Klik kanan
echo   - Cubit manis 2x + tahan    : Scroll
echo   - 3 jari + jempol-kelingking : Voice typing (on/off)
echo   - Tekan 'q' di window     : Keluar
echo.
echo Menyalakan webcam, tunggu sebentar...
echo.

python hand_mouse.py

echo.
if errorlevel 1 (
    echo [GAGAL] Program berhenti karena error. Baca pesan di atas.
) else (
    echo [SELESAI] Program ditutup normal.
)
echo.
pause
