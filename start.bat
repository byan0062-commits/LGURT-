@echo off
echo ========================================
echo   LGURT Dashboard v5.1
echo ========================================
echo.

REM 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请先安装Python 3.8+
    pause
    exit /b 1
)

REM 安装依赖
echo [1/3] 安装依赖...
pip install flask pandas openpyxl werkzeug -q

REM 启动服务
echo [2/3] 启动服务...
echo.
echo ========================================
echo   访问地址: http://127.0.0.1:5001
echo   默认账号: demo / demo123
echo   按 Ctrl+C 停止服务
echo ========================================
echo.

python app.py
pause
