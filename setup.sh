#!/bin/bash
# 玄学助手 - 一键设置脚本
# 需要 sudo 权限

set -e

echo "========================================="
echo "  玄学助手 设置脚本"
echo "========================================="

# 1. Install Python dependencies
echo ""
echo "[1/5] 安装 Python 依赖..."
pip3 install --user fastapi uvicorn sse-starlette python-multipart 2>&1 || {
    echo "  使用镜像源重试..."
    pip3 install --user -i https://pypi.tuna.tsinghua.edu.cn/simple fastapi uvicorn sse-starlette python-multipart
}
echo "  ✓ Python 依赖安装完成"

# 2. Enable Apache modules
echo ""
echo "[2/5] 启用 Apache 模块..."
sudo a2enmod proxy proxy_http 2>/dev/null || true
echo "  ✓ Apache 模块已启用"

# 3. Copy Apache config
echo ""
echo "[3/5] 配置 Apache 虚拟主机..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
sudo cp "$SCRIPT_DIR/xuanxue-apache.conf" /etc/apache2/sites-available/xuanxue.conf
sudo a2ensite xuanxue.conf 2>/dev/null || true
echo "  ✓ Apache 虚拟主机已配置"

# 4. Reload Apache
echo ""
echo "[4/5] 重载 Apache..."
sudo systemctl reload apache2
echo "  ✓ Apache 已重载"

# 5. Configure nftables
echo ""
echo "[5/5] 配置防火墙 (nftables)..."
if command -v nft &> /dev/null; then
    # Check if rule already exists
    if ! sudo nft list ruleset 2>/dev/null | grep -q "tcp dport 8888 accept"; then
        sudo nft add rule inet filter input tcp dport 8888 accept 2>/dev/null || {
            echo "  ! 无法自动添加 nftables 规则，请手动执行:"
            echo "    sudo nft add rule inet filter input tcp dport 8888 accept"
        }
    else
        echo "  ✓ 端口 8888 规则已存在"
    fi
else
    echo "  - nftables 未安装，跳过"
fi

echo ""
echo "========================================="
echo "  设置完成！"
echo ""
echo "  启动后端:"
echo "    cd $SCRIPT_DIR && bash start.sh"
echo ""
echo "  访问地址:"
echo "    http://localhost:8888"
echo "========================================="
