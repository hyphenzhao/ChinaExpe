#!/bin/bash
# 玄学助手启动脚本
# Start the FastAPI backend

cd "$(dirname "$0")"

# Add local pip bin to PATH
export PATH="$HOME/.local/bin:$PATH"

# Check if virtual environment exists
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "[✓] Virtual environment activated"
fi

# Ensure data directories exist
mkdir -p data/sessions

echo "[→] Starting 玄学助手 on http://127.0.0.1:8765"
echo "[→] Apache will proxy from http://0.0.0.0:8888"
echo ""

# Start uvicorn
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload
