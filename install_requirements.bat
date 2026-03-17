@echo off
echo Installing Xivora dependencies...
pip install fastapi uvicorn[standard] httpx segno pydantic python-multipart neonize PySide6 requests python-dotenv
echo.
echo Done! You can now launch Xivora WhatsApp Sender.
pause
