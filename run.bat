@echo off
chcp 65001 >nul 2>&1
echo ========================================
echo  BabelDOC Xiaomi MiMo PDF Translator
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+ first.
    pause
    exit /b 1
)

REM Install httpx if needed
python -c "import httpx" >nul 2>&1
if errorlevel 1 (
    echo [*] Installing httpx...
    pip install httpx
)

REM Launch GUI
echo [*] Starting GUI...
python "%~dp0gui.py"
