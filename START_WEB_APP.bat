@echo off
REM Start ITS Traffic Analysis Web App
REM This script launches Streamlit on port 5173

title ITS Traffic Analysis - Streamlit Web App
echo.
echo =========================================
echo   ITS Traffic Analysis System v2.0
echo   Phan Loai Xe & Thong Ke Giao Thong
echo =========================================
echo.
echo [*] Launching Streamlit Web App...
echo [*] Port: 5173
echo [*] URL: http://localhost:5173
echo [*] Results Page: http://localhost:5173/#phan-loai-xe
echo.
echo [!] Browser will open automatically
echo [!] Press Ctrl+C to stop
echo.

REM Run Streamlit with proper Python path
"D:/hệ thống giao thông thông minh/test 3/.venv/Scripts/streamlit.exe" run traffic_web_app.py --server.port 5173 --browser.serverAddress=localhost

pause
