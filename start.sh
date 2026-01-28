#!/bin/bash
echo "========================================"
echo "  LGURT Dashboard v5.1"
echo "========================================"
echo ""

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未找到Python3，请先安装"
    exit 1
fi

# 安装依赖
echo "[1/3] 安装依赖..."
pip3 install flask pandas openpyxl werkzeug -q

# 启动服务
echo "[2/3] 启动服务..."
echo ""
echo "========================================"
echo "  访问地址: http://127.0.0.1:5001"
echo "  默认账号: demo / demo123"
echo "  按 Ctrl+C 停止服务"
echo "========================================"
echo ""

python3 app.py
