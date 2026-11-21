@echo off
setlocal
chcp 65001 >nul
TITLE tdtnext for Windows - interactive setup
ECHO ===============================================
ECHO   tdtnext - Windows setup
ECHO ===============================================
ECHO.
ECHO The setup window will show package download and install progress.
ECHO Windows may request admin approval to enable WSL when needed.
ECHO.
powershell.exe -NoProfile -File "%~dp0scripts\setup_windows.ps1"
set "RESULT=%ERRORLEVEL%"
ECHO.
if not "%RESULT%"=="0" (
    ECHO Setup exited with code %RESULT%. See messages above.
) else (
    ECHO Setup complete. Open a new Command Prompt and run tdtnext --help.
)
ECHO.
pause
exit /b %RESULT%
