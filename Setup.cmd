@echo off
rem Quick start on Windows: finds MSYS2 (or offers to install it) and runs
rem setup.sh inside it, which does everything else. See README.md.
setlocal
set BASH=C:\msys64\usr\bin\bash.exe
if exist "%BASH%" goto run

echo battlepod builds with MSYS2 (a C compiler, make and SDL2 for Windows).
echo It isn't installed. winget can install it: about 500 MB, into C:\msys64.
choice /m "Install MSYS2 now"
if errorlevel 2 goto nomsys
winget install --id MSYS2.MSYS2 -e --accept-package-agreements --accept-source-agreements
if not exist "%BASH%" goto nomsys

:run
set MSYSTEM=MINGW64
set CHERE_INVOKING=1
cd /d "%~dp0"
"%BASH%" -lc "./setup.sh"
echo.
pause
exit /b

:nomsys
echo.
echo Setup stopped: install MSYS2 from https://www.msys2.org/ into C:\msys64, then run Setup.cmd again.
pause
exit /b 1
