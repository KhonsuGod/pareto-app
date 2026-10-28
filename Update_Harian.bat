@echo off
setlocal
title PROSES-MONITOR / Bolang
cd /d "%~dp0"
chcp 65001 >nul

echo ========================================
echo  PROSES-MONITOR - Proses 1 ^& Proses 2
echo ========================================
echo.

rem --- Cari interpreter Python 3.12 yang benar (punya openpyxl/pandas/yaml) ---
set "PYEXE="
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PYEXE if exist "%ProgramFiles%\Python312\python.exe" set "PYEXE=%ProgramFiles%\Python312\python.exe"
if defined PYEXE goto :run
for /f "delims=" %%I in ('where python 2^>nul') do (
    set "PYEXE=%%I"
    goto :run
)

echo [ERROR] Python tidak ditemukan di komputer ini.
echo         Install Python 3.12 lalu jalankan: pip install -r requirements.txt
echo.
if not defined MONITOR_NO_OPEN pause
exit /b 1

:run
echo Interpreter: %PYEXE%
echo.
if "%~1"=="" goto :menu
"%PYEXE%" app.py %*
if errorlevel 1 goto :fail
goto :done

:menu
"%PYEXE%" app.py
if errorlevel 1 goto :fail

:done
echo.
echo Selesai.
if not defined MONITOR_NO_OPEN pause
exit /b 0

:fail
echo.
echo [UPDATE GAGAL] - baca pesan error di atas, workbook LATEST tidak diubah.
if not defined MONITOR_NO_OPEN pause
exit /b 1
