@echo off
REM Double-click this to open the iPad Second Screen control panel.
REM Finds Python automatically: prefers the "py" launcher, then "python" on PATH.
cd /d "%~dp0"

REM 1) Try the Windows "py" launcher (installed with python.org Python).
where py >nul 2>nul
if %errorlevel%==0 (
    py launcher.py
    goto :end
)

REM 2) Fall back to "python" on PATH.
where python >nul 2>nul
if %errorlevel%==0 (
    python launcher.py
    goto :end
)

REM 3) Nothing found: tell the user how to fix it.
echo.
echo Python was not found on your PATH.
echo Install Python 3 from https://www.python.org/downloads/ and be sure to
echo tick "Add python.exe to PATH" during installation, then run this again.
echo.
pause
goto :eof

:end
if errorlevel 1 pause
