#!/bin/bash
# ============================================
# Discord Music Bot - Oracle Cloud Auto Setup
# ============================================
set -e
echo "=========================================="
echo "  Discord Music Bot - Auto Setup"
echo "=========================================="

echo "[1/7] Updating system..."
sudo apt-get update -y && sudo apt-get upgrade -y

echo "[2/7] Installing Python, FFmpeg, Git..."
sudo apt-get install -y python3 python3-pip python3-venv ffmpeg git curl

echo "[3/7] Cloning bot code..."
cd ~
if [ -d "discord-music-bot" ]; then
    cd discord-music-bot && git pull
else
    git clone https://github.com/BuiMinhWin/discord-music-bot.git
    cd discord-music-bot
fi

echo "[4/7] Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "[5/7] Configuring bot..."
if [ ! -f ".env" ]; then
    echo "==> Enter your bot tokens:"
    read -p "DISCORD_TOKEN: " DISCORD_TOKEN
    read -p "GENIUS_API_TOKEN (press Enter to skip): " GENIUS_TOKEN
    cat > .env << ENVEOF
DISCORD_TOKEN=${DISCORD_TOKEN}
GENIUS_API_TOKEN=${GENIUS_TOKEN}
FFMPEG_PATH=ffmpeg
COOKIES_FILE=cookies.txt
ENVEOF
    echo "==> Created .env file"
else
    echo "==> .env already exists, skipping."
fi

echo "[6/7] Setting up auto-restart service..."
sudo tee /etc/systemd/system/music-bot.service > /dev/null << SVCEOF
[Unit]
Description=Discord Music Bot
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/venv/bin/python bot.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
SVCEOF

sudo systemctl daemon-reload
sudo systemctl enable music-bot
sudo systemctl start music-bot

echo "[7/7] Checking status..."
sleep 3
sudo systemctl status music-bot --no-pager

echo ""
echo "=========================================="
echo "  SETUP COMPLETE!"
echo "=========================================="
echo ""
echo "Useful commands:"
echo "  View logs:    sudo journalctl -u music-bot -f"
echo "  Restart bot:  sudo systemctl restart music-bot"
echo "  Stop bot:     sudo systemctl stop music-bot"
echo "  Status:       sudo systemctl status music-bot"
echo ""
