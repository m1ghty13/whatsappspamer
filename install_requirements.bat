@echo off
echo Installing Xivora dependencies...

:: Try different Python launchers
where py >nul 2>&1
if %errorlevel% == 0 (
    py -m pip install fastapi uvicorn[standard] httpx segno pydantic python-multipart neonize PySide6 requests python-dotenv
    goto done
)

where python >nul 2>&1
if %errorlevel% == 0 (
    python -m pip install fastapi uvicorn[standard] httpx segno pydantic python-multipart neonize PySide6 requests python-dotenv
    goto done
)

where python3 >nul 2>&1
if %errorlevel% == 0 (
    python3 -m pip install fastapi uvicorn[standard] httpx segno pydantic python-multipart neonize PySide6 requests python-dotenv
    goto done
)

echo.
echo ERROR: Python not found!
echo Please install Python from https://python.org
echo Make sure to check "Add Python to PATH" during installation.
pause
exit /b 1

:done
echo.
echo Done! You can now launch Xivora WhatsApp Sender.
pause
