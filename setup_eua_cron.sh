#!/bin/bash
# Setup script for automated EUA price updates on headless Debian PC
# Run once: bash setup_eua_cron.sh

set -e

INSTALL_DIR="$HOME/dirtiestships-website"
REPO="git@github.com:jeroen41-hash/dirtiestships-website.git"

echo "=== DirtiestShips EUA Price Updater Setup ==="

# Clone repo if not present
if [ -d "$INSTALL_DIR" ]; then
    echo "Repo already exists at $INSTALL_DIR, pulling latest..."
    cd "$INSTALL_DIR"
    git pull
else
    echo "Cloning repo..."
    git clone "$REPO" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# Create venv and install requests
echo "Setting up Python venv..."
python3 -m venv venv
venv/bin/pip install --quiet requests

# Test the script
echo "Testing EUA price fetch..."
venv/bin/python3 update_eua_price.py

# Add cron job (daily at 18:00) if not already present
CRON_CMD="cd $INSTALL_DIR && venv/bin/python3 update_eua_price.py >> $INSTALL_DIR/eua_cron.log 2>&1"
if crontab -l 2>/dev/null | grep -qF "update_eua_price.py"; then
    echo "Cron job already exists, skipping."
else
    (crontab -l 2>/dev/null; echo "0 18 * * * $CRON_CMD") | crontab -
    echo "Cron job added: daily at 18:00"
fi

echo ""
echo "=== Setup complete ==="
echo "Install dir: $INSTALL_DIR"
echo "Cron log:    $INSTALL_DIR/eua_cron.log"
