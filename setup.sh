#!/bin/bash
set -e

echo "=== AsoBot セットアップ ==="

# Python 3.11+ 確認
python3 --version

# 仮想環境作成
python3 -m venv venv
source venv/bin/activate

# 依存インストール
pip install --upgrade pip
pip install -r requirements.txt

# .env 確認
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "⚠️  .env を作成しました。DISCORD_TOKEN を設定してから再実行してください。"
    exit 1
fi

# systemd サービス登録
BOT_DIR=$(pwd)
USER=$(whoami)

sudo tee /etc/systemd/system/aso-bot.service > /dev/null <<EOF
[Unit]
Description=AsoBot Discord Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$BOT_DIR
ExecStart=$BOT_DIR/venv/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable aso-bot
sudo systemctl start aso-bot

echo ""
echo "=== 起動完了 ==="
echo "ログ確認: journalctl -u aso-bot -f"
echo "停止:     sudo systemctl stop aso-bot"
echo "再起動:   sudo systemctl restart aso-bot"
echo "更新:     git pull && sudo systemctl restart aso-bot"
