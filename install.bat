@echo off
chcp 65001 >nul 2>&1
echo ========================================
echo  Installing dependencies...
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+ first.
    pause
    exit /b 1
)

REM Install httpx
echo [*] Installing httpx...
pip install httpx

REM Install uv
echo [*] Installing uv...
pip install uv

REM Install BabelDOC (via uv tool)
echo [*] Installing BabelDOC (first time, may take a few minutes)...
uv tool install --python 3.12 BabelDOC

echo.
echo ========================================
echo  All done! You can now run:
echo    double-click run.bat
echo    or: python gui.py
echo    or: python translate.py input.pdf --api-key "your-key"
echo ========================================
pause
