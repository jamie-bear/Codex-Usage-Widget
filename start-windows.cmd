@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 codex_usage_widget.py
  goto :eof
)
where python >nul 2>nul
if %errorlevel%==0 (
  python codex_usage_widget.py
  goto :eof
)
echo Python 3 was not found. Install Python 3.10+ and run this file again.
echo Example: winget install Python.Python.3.13
pause
