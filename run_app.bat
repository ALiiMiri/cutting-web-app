@echo off
cd /d "%~dp0"
echo Starting Cutting Web App...
"..\.venv\Scripts\python.exe" cutting_web_app.py
pause
