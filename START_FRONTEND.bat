@echo off
echo ========================================
echo  KHOI DONG FRONTEND - Streamlit Web UI
echo ========================================
echo.
echo Dang khoi dong frontend tren port 5173...
echo.

python -m streamlit run traffic_web_app_streaming.py --server.port 5173

pause
