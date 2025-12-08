@echo off
REM ═══════════════════════════════════════════════════════════════
REM Polymarket Hybrid Bot - Windows Setup Script
REM ═══════════════════════════════════════════════════════════════

echo.
echo ═══════════════════════════════════════════════════════════════
echo 🚀 POLYMARKET HYBRID BOT SETUP
echo ═══════════════════════════════════════════════════════════════
echo.
echo This script will:
echo   1. Create project structure
echo   2. Create necessary files
echo   3. Install Python dependencies
echo   4. Set up configuration
echo.

pause

REM Step 1: Create directories
echo.
echo ═══════════════════════════════════════════════════════════════
echo 📁 Creating Project Structure
echo ═══════════════════════════════════════════════════════════════
echo.

if not exist "core" mkdir core
if not exist "scripts" mkdir scripts
if not exist "utils" mkdir utils

echo ✅ Created directories: core, scripts, utils

REM Create __init__.py files
type nul > core\__init__.py
type nul > scripts\__init__.py
type nul > utils\__init__.py

echo ✅ Created __init__.py files

REM Step 2: Create .gitignore
echo.
echo ═══════════════════════════════════════════════════════════════
echo 🔒 Creating .gitignore
echo ═══════════════════════════════════════════════════════════════
echo.

(
echo # Environment
echo .env
echo .env.local
echo.
echo # Python
echo __pycache__/
echo *.py[cod]
echo *$py.class
echo *.so
echo .Python
echo env/
echo venv/
echo ENV/
echo *.egg-info/
echo.
echo # Output files
echo *.png
echo *.json
echo trades_*.json
echo report_*.txt
echo chart_*.png
echo !README*.md
echo !requirements*.txt
echo.
echo # IDE
echo .vscode/
echo .idea/
echo *.swp
echo *.swo
echo.
echo # Logs
echo *.log
echo bot.log
) > .gitignore

echo ✅ Created .gitignore

REM Step 3: Create .env from template
echo.
echo ═══════════════════════════════════════════════════════════════
echo ⚙️  Creating .env File
echo ═══════════════════════════════════════════════════════════════
echo.

if exist .env (
    echo ⚠️  .env already exists, creating .env.backup
    copy .env .env.backup >nul
)

if exist .env.template (
    copy .env.template .env >nul
    echo ✅ Created .env from .env.template
) else (
    echo ❌ .env.template not found!
    echo ℹ️  Please ensure .env.template exists in the project root
    pause
    exit /b 1
)

REM Step 4: Check Python
echo.
echo ═══════════════════════════════════════════════════════════════
echo 🐍 Checking Python Installation
echo ═══════════════════════════════════════════════════════════════
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed or not in PATH!
    echo ℹ️  Please install Python 3.8+ from python.org
    echo ℹ️  Make sure to check "Add Python to PATH" during installation
    pause
    exit /b 1
)

python --version
echo ✅ Python found

REM Step 5: Install dependencies
echo.
echo ═══════════════════════════════════════════════════════════════
echo 📦 Installing Dependencies
echo ═══════════════════════════════════════════════════════════════
echo.

if exist requirements_hybrid.txt (
    echo Installing packages from requirements_hybrid.txt...
    python -m pip install -r requirements_hybrid.txt
    if errorlevel 1 (
        echo ❌ Failed to install dependencies
        pause
        exit /b 1
    )
    echo ✅ Dependencies installed successfully
) else (
    echo ❌ requirements_hybrid.txt not found!
    pause
    exit /b 1
)

REM Step 6: Verify installation
echo.
echo ═══════════════════════════════════════════════════════════════
echo ✅ Verifying Installation
echo ═══════════════════════════════════════════════════════════════
echo.

python -c "import py_clob_client, aiohttp, asyncio, websockets; print('All imports OK')" 2>nul
if errorlevel 1 (
    echo ❌ Some packages failed to import
    echo ℹ️  Try running: pip install -r requirements_hybrid.txt
    pause
    exit /b 1
)

echo ✅ All required packages installed correctly

REM Step 7: Check for required files
echo.
echo ═══════════════════════════════════════════════════════════════
echo 📋 Checking Required Files
echo ═══════════════════════════════════════════════════════════════
echo.

set MISSING=0

if exist main_hybrid.py (echo ✓ main_hybrid.py) else (echo ✗ main_hybrid.py ^(MISSING^) & set MISSING=1)
if exist config.py (echo ✓ config.py) else (echo ✗ config.py ^(MISSING^) & set MISSING=1)
if exist core\client.py (echo ✓ core\client.py) else (echo ✗ core\client.py ^(MISSING^) & set MISSING=1)
if exist core\market_scanner.py (echo ✓ core\market_scanner.py) else (echo ✗ core\market_scanner.py ^(MISSING^) & set MISSING=1)
if exist core\pair_trader.py (echo ✓ core\pair_trader.py) else (echo ✗ core\pair_trader.py ^(MISSING^) & set MISSING=1)
if exist core\last_second_sniper.py (echo ✓ core\last_second_sniper.py) else (echo ✗ core\last_second_sniper.py ^(MISSING^) & set MISSING=1)
if exist core\monitor.py (echo ✓ core\monitor.py) else (echo ✗ core\monitor.py ^(MISSING^) & set MISSING=1)
if exist scripts\approve.py (echo ✓ scripts\approve.py) else (echo ✗ scripts\approve.py ^(MISSING^) & set MISSING=1)
if exist utils\logger.py (echo ✓ utils\logger.py) else (echo ✗ utils\logger.py ^(MISSING^) & set MISSING=1)
if exist utils\chart_generator.py (echo ✓ utils\chart_generator.py) else (echo ✗ utils\chart_generator.py ^(MISSING^) & set MISSING=1)

echo.

if %MISSING%==1 (
    echo ❌ Some files are missing!
    echo ℹ️  Please copy all required files from the artifacts
    pause
    exit /b 1
)

echo ✅ All required files present

REM Step 8: Next steps
echo.
echo ═══════════════════════════════════════════════════════════════
echo 🔐 Next Steps
echo ═══════════════════════════════════════════════════════════════
echo.
echo Setup complete! Here's what to do next:
echo.
echo 1. Edit .env file and fill in your credentials:
echo    notepad .env
echo    - Set PRIVATE_KEY ^(your wallet private key, no 0x^)
echo    - Set PROXY_ADDRESS ^(your Polymarket wallet address^)
echo.
echo 2. Verify configuration:
echo    python config.py
echo.
echo 3. Setup USDC allowance ^(REQUIRED^):
echo    python scripts\approve.py
echo.
echo 4. Test the bot ^(dry run mode^):
echo    python main_hybrid.py
echo.
echo 5. When ready to trade for real:
echo    - Edit .env and set DRY_RUN=false
echo    - Start with small amounts ^(MAX_PER_SIDE=5.0^)
echo    - Monitor carefully!
echo.
echo ═══════════════════════════════════════════════════════════════
echo ✨ Setup Complete!
echo ═══════════════════════════════════════════════════════════════
echo.
echo ✅ Bot is ready for configuration
echo ℹ️  Read README_HYBRID.md for detailed documentation
echo ⚠️  IMPORTANT: Keep your .env file secret and never share it!
echo.
echo Happy trading! 🚀📈
echo.

pause